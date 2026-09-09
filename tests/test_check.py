"""``check()`` against a socket we control, on loopback only.

The one module in this package that opens a socket is the one hardest to test
honestly. These cases run a real TCP listener on ``127.0.0.1`` that speaks the
CONNECT half of the exchange and then hangs up, so every assertion below is
about bytes that actually crossed a socket - and no live host is touched, no
traffic is spent, and nothing routes through whatever tunnel the machine happens
to be behind.

The fake gateway is scripted rather than clever: each test says exactly what
status line and headers to answer with. That is what lets a 407 and a
``Connection established`` carrying ``X-Proxy-Exit-IP`` be tested at all - the
real gateway answers what it feels like answering, and two of its documented
reactions cannot be provoked on demand.
"""

from __future__ import annotations

import socket
import threading

import pytest

from nodemaven import Check, CheckError, Proxy
from nodemaven.check import connect

REACTIONS = {
    "200": "the tunnel opened; a 200 does not mean every parameter was applied.",
    "407": "usually NOT your credentials, despite what the status says.",
}


class FakeGateway:
    """A one-shot CONNECT responder on loopback.

    Records the request head it was sent, so a test can assert on what the
    client emitted as well as on what it parsed. ``answer=None`` means accept
    the connection and close it without replying, which is a real failure mode
    and one of the two that must raise rather than return.
    """

    def __init__(self, answer, *, answer_bytes=None):
        self.answer = answer
        self.answer_bytes = answer_bytes
        self.received = b""
        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.address = "%s:%d" % self._sock.getsockname()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(5.0)
            try:
                while b"\r\n\r\n" not in self.received:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    self.received += chunk
            except OSError:
                return
            payload = self.answer_bytes
            if payload is None and self.answer is not None:
                payload = self.answer.encode("latin-1")
            if payload is None:
                return
            try:
                conn.sendall(payload)
            except OSError:
                # The bounded-read test deliberately answers with more than
                # `check` will read, so the client closes mid-send. That is the
                # behaviour under test, not a failure of the fake.
                return

    def close(self):
        self._sock.close()
        self._thread.join(timeout=5.0)


@pytest.fixture
def gateway(request):
    made = []

    def make(answer=None, *, answer_bytes=None):
        server = FakeGateway(answer, answer_bytes=answer_bytes)
        made.append(server)
        return server

    yield make
    for server in made:
        server.close()


ESTABLISHED = (
    "HTTP/1.1 200 Connection established\r\n"
    "X-Proxy-Exit-IP: 203.0.113.7\r\n"
    "\r\n"
)


class TestWhatTheGatewaySaid:
    def test_a_200_with_the_exit_header_yields_the_exit_address(self, gateway):
        server = gateway(ESTABLISHED)
        result = connect(
            server.address, "acct-country-us", "pw",
            exit_ip_header="X-Proxy-Exit-IP", reactions=REACTIONS,
        )
        assert result.ok
        assert result.status == 200
        assert result.exit_ip == "203.0.113.7"
        # One CONNECT and nothing else: the exit address arrived on the reply
        # itself, so it cost no target traffic. That is the whole reason this
        # module exists rather than a GET through the tunnel.
        assert result.elapsed >= 0.0

    def test_the_reason_phrase_is_kept_verbatim(self, gateway):
        # Measured 2026-08-13: on the shipped gateway a 200 carrying the exit
        # header arrives as `Connection established`, while the ones arriving as
        # `OK` or `Connection Established` do not carry it. The phrase labels
        # which back end answered, so normalising it - even just its case -
        # destroys the only key any per-implementation figure can be split on.
        server = gateway("HTTP/1.1 200 Connection Established\r\n\r\n")
        result = connect(server.address, "acct", "pw")
        assert result.reason == "Connection Established"
        assert result.exit_ip is None

    def test_a_missing_exit_header_is_normal_and_not_an_error(self, gateway):
        server = gateway("HTTP/1.1 200 OK\r\n\r\n")
        result = connect(
            server.address, "acct", "pw", exit_ip_header="X-Proxy-Exit-IP"
        )
        assert result.ok
        assert result.exit_ip is None

    def test_headers_are_lowercased_and_kept(self, gateway):
        server = gateway(
            "HTTP/1.1 200 Connection established\r\n"
            "X-Proxy-Exit-IP: 203.0.113.7\r\n"
            "Via: 1.1 something\r\n"
            "\r\n"
        )
        result = connect(server.address, "acct", "pw")
        assert result.headers["x-proxy-exit-ip"] == "203.0.113.7"
        assert result.headers["via"] == "1.1 something"

    def test_a_header_name_is_lowercased_ascii_only(self, gateway):
        # Not a bug that was ever reachable in production - the shipped
        # gateway's header is `X-Proxy-Exit-IP` and every byte of it is ASCII -
        # but a portability trap, found 2026-09-07 while writing the Rust port,
        # and of the kind that surfaces as one SDK finding a header the other
        # cannot.
        #
        # The head is decoded latin-1 on purpose, so byte 0xC0 arrives as
        # 'A-grave'. `str.lower()` folds that to 'a-grave' and Rust's
        # `to_ascii_lowercase` leaves it alone, so two SDKs would key one
        # response two ways. RFC 9110 makes a field name a token and a token is
        # ASCII, so ASCII-only is the correct rule as well as the portable one -
        # the same decision, for the same reason, as the ASCII-only fold in
        # `Provider.normalized`.
        server = gateway(
            None, answer_bytes=b"HTTP/1.1 200 OK\r\n\xc0-Vendor: yes\r\n\r\n"
        )
        result = connect(server.address, "acct", "pw")
        assert "\xc0-vendor" in result.headers
        assert "\xe0-vendor" not in result.headers


class TestARefusalIsAResultAndNotAnException:
    def test_a_407_comes_back_as_a_value(self, gateway):
        # Raising here would push the status - the thing the caller came for -
        # into a traceback. `requests` does exactly that, and the code survives
        # only as text inside a nested exception.
        server = gateway("HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
        result = connect(server.address, "acct", "pw", reactions=REACTIONS)
        assert isinstance(result, Check)
        assert result.status == 407
        assert not result.ok

    def test_the_meaning_comes_from_the_provider_and_not_from_the_status(
        self, gateway
    ):
        # The point of the table: two of the gateway's seven documented
        # reactions are 407, and neither is a credentials problem. A caller
        # reading the status alone goes and checks a password that is correct.
        server = gateway("HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
        result = connect(server.address, "acct", "pw", reactions=REACTIONS)
        assert result.meaning is not None
        assert "NOT your credentials" in result.meaning
        assert result.meaning in str(result)

    def test_a_status_with_no_entry_has_no_meaning_rather_than_a_wrong_one(
        self, gateway
    ):
        server = gateway("HTTP/1.1 502 Bad Gateway\r\n\r\n")
        result = connect(server.address, "acct", "pw", reactions=REACTIONS)
        assert result.status == 502
        assert result.meaning is None

    def test_a_200s_meaning_is_not_shown_because_it_is_not_a_diagnosis(
        self, gateway
    ):
        server = gateway(ESTABLISHED)
        result = connect(server.address, "acct", "pw", reactions=REACTIONS)
        assert result.meaning is not None
        assert result.meaning not in str(result)


class TestWhenNothingCameBack:
    def test_an_immediate_close_raises_and_says_it_is_worth_reporting(
        self, gateway
    ):
        server = gateway(None)
        with pytest.raises(CheckError, match="without answering"):
            connect(server.address, "acct", "pw")

    def test_something_that_is_not_a_status_line_raises(self, gateway):
        # A captive portal, or something other than a proxy on that port.
        server = gateway("<html>You must sign in</html>\r\n\r\n")
        with pytest.raises(CheckError, match="not an HTTP status line"):
            connect(server.address, "acct", "pw")

    def test_a_non_numeric_status_raises_rather_than_crashing_on_int(
        self, gateway
    ):
        server = gateway("HTTP/1.1 OK Fine\r\n\r\n")
        with pytest.raises(CheckError, match="not an HTTP status line"):
            connect(server.address, "acct", "pw")

    @pytest.mark.parametrize("byte", [b"\xb9", b"\xb2", b"\xb3"])
    def test_a_latin1_superscript_status_raises_and_does_not_crash_on_int(
        self, gateway, byte
    ):
        # A real defect, found 2026-09-07 while porting this module to Rust and
        # fixed the same day. The gate here was `parts[1].isdigit()`, which is
        # True for these three bytes and for which `int()` raises: `'\xb2'` is
        # SUPERSCRIPT TWO, `'\xb2'.isdigit()` is True, `int('\xb2')` is a
        # `ValueError`. So an uncaught `ValueError` left a module whose docstring
        # promises only `CheckError` comes out of it.
        #
        # And it was reachable only because of a deliberate decision two
        # functions away: the head is decoded latin-1 on purpose, so that any
        # byte a proxy is entitled to send is accepted rather than raising. The
        # widening of the input alphabet is what made the narrow check unsound.
        # Sent as bytes, not as a str, because the payload is not ASCII.
        server = gateway(
            None, answer_bytes=b"HTTP/1.1 " + byte + b" something\r\n\r\n"
        )
        with pytest.raises(CheckError, match="not an HTTP status line"):
            connect(server.address, "acct", "pw")

    @pytest.mark.parametrize("status", ["20", "2000", "99999"])
    def test_a_status_that_is_not_three_digits_is_refused(self, gateway, status):
        # Three digits and not "one or more" because RFC 9110 calls the status
        # code a three-digit integer, and because it is the rule a Rust `u16`
        # holds without diverging from Python's arbitrary-precision `int` -
        # `99999` parsed fine here and overflows there, which is a port that
        # disagrees with its original on a real input.
        server = gateway("HTTP/1.1 %s something\r\n\r\n" % status)
        with pytest.raises(CheckError, match="not an HTTP status line"):
            connect(server.address, "acct", "pw")

    def test_a_status_line_with_no_http_version_is_refused(self, gateway):
        # The review's case, reproduced on loopback 2026-09-08: this answered
        # `status=200 ok=True reason='OK'`. `_parse_head` split the line and
        # looked only at the second token, so the first was whatever the peer
        # felt like sending.
        server = gateway("garbage 200 OK\r\n\r\n")
        with pytest.raises(CheckError, match="not an HTTP status line"):
            connect(server.address, "acct", "pw")

    def test_a_faked_status_line_cannot_supply_an_exit_address(self, gateway):
        # Worse than the status alone and not in the review: whatever is
        # listening also gets to name the exit, and the caller reports that
        # address as the one its traffic left from. `ok` is what a caller
        # branches on and `exit_ip` is what it then prints.
        server = gateway("garbage 200 OK\r\nX-Proxy-Exit-IP: 1.2.3.4\r\n\r\n")
        with pytest.raises(CheckError, match="not an HTTP status line"):
            connect(server.address, "acct", "pw", exit_ip_header="X-Proxy-Exit-IP")

    @pytest.mark.parametrize(
        "version", ["HTTP/1", "HTTP/11", "http/1.1", "HTTP/1.1x", "HTTPS/1.1", ""]
    )
    def test_a_version_token_that_is_not_the_grammar_is_refused(
        self, gateway, version
    ):
        # RFC 9112 section 2.3: `HTTP-name "/" DIGIT "." DIGIT`, with the name
        # case-sensitive. Eight characters exactly - a CONNECT answered over a
        # socket this module opened itself is HTTP/1.x by construction, so there
        # is no version negotiation here to be liberal about. `http/1.1` is in
        # the list because being liberal about case is the single most likely
        # way a port diverges from this one.
        server = gateway(version + " 200 OK\r\n\r\n")
        with pytest.raises(CheckError, match="not an HTTP status line"):
            connect(server.address, "acct", "pw")

    @pytest.mark.parametrize("version", ["HTTP/1.1", "HTTP/1.0", "HTTP/0.9"])
    def test_the_versions_a_proxy_may_answer_with_are_accepted(
        self, gateway, version
    ):
        # The control the rule above needs, and it is what stops the check from
        # being tightened into something that refuses a real gateway. Without
        # it, "refuse anything that is not HTTP/1.1" passes every test above
        # and breaks against a proxy answering 1.0.
        server = gateway(version + " 200 OK\r\n\r\n")
        assert connect(server.address, "acct", "pw").status == 200

    def test_a_refused_connection_says_the_gateway_was_never_reached(self):
        # Bound and immediately closed, so the port is free and nothing is
        # listening. Loopback refuses rather than hanging, which is why this is
        # a test and not a 15 s timeout.
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        address = "%s:%d" % sock.getsockname()
        sock.close()
        with pytest.raises(CheckError, match="never reached"):
            connect(address, "acct", "pw", timeout=2.0)

    def test_an_address_without_a_port_is_refused_before_anything_is_sent(self):
        with pytest.raises(CheckError, match="Nothing was sent"):
            connect("gate.example.com", "acct", "pw")

    def test_a_non_numeric_port_is_refused_before_anything_is_sent(self):
        with pytest.raises(CheckError, match="host:port"):
            connect("gate.example.com:eight", "acct", "pw")

    @pytest.mark.parametrize("port", ["\xb9", "\xb2", "\xb3"])
    def test_a_latin1_superscript_port_raises_checkerror_and_not_valueerror(
        self, port
    ):
        # The same `isdigit()` defect as the status-line case above, in the
        # caller-facing half of the module, and it survived the first fix
        # because that fix corrected the predicate where the bug was noticed
        # rather than everywhere it was used. Measured 2026-09-07:
        # `connect("127.0.0.1:\xb2", "acct", "pw")` raised
        # `ValueError: invalid literal for int() with base 10: '2'` from
        # check.py, past a docstring promising only `CheckError` leaves here.
        #
        # `pytest.raises(CheckError)` is the whole assertion: `ValueError` is
        # not a `CheckError`, so the old code fails this test by raising the
        # wrong class rather than by raising nothing.
        with pytest.raises(CheckError, match="host:port"):
            connect("127.0.0.1:" + port, "acct", "pw", timeout=2.0)

    def test_a_port_too_large_for_a_socket_raises_checkerror_and_not_overflow(
        self
    ):
        # Measured 2026-09-07: this raised `OverflowError: Python int too large
        # to convert to C long`, from inside `socket.create_connection`. That
        # one does not derive from `OSError` - it is an `ArithmeticError` - so
        # it walked straight past the handler whose entire job is turning
        # everything the socket layer raises into a `CheckError`. `isdigit()`
        # was True, `int()` succeeded, and the failure happened one layer
        # further down than the two above it.
        with pytest.raises(CheckError, match="host:port"):
            connect("127.0.0.1:99999999999999999999", "acct", "pw", timeout=2.0)

    @pytest.mark.parametrize("port", ["0", "65536", "70000"])
    def test_a_port_outside_1_to_65535_is_refused_before_anything_is_sent(
        self, port
    ):
        # These three already produced a `CheckError` before the fix, so this
        # is not a regression pin - it is pinning *where* the refusal happens.
        # Measured 2026-09-07, all on this host: `:0` reached the socket layer
        # and came back `[WinError 10049]`, and `:70000` came back `timed out`
        # after the full timeout. Both are the right exception class carrying
        # the wrong explanation, and the second spends 15 s by default to say
        # it. Refusing in the parse means the message names the actual mistake
        # and costs nothing - and it removes a platform-specific errno from a
        # cross-language contract, since Linux answers `:0` with ECONNREFUSED.
        with pytest.raises(CheckError, match="Nothing was sent"):
            connect("127.0.0.1:" + port, "acct", "pw", timeout=2.0)


class TestTheCredentialNeverAppears:
    def test_no_message_on_any_failure_path_carries_the_password(self, gateway):
        # `connect` holds the request bytes - which contain the base64
        # credential - in scope inside its own except block. An f-string that
        # happened to include them would put a working credential into every
        # traceback, every CI log and every pasted bug report.
        password = "s3cr3t-do-not-print"
        cases = [
            gateway(None).address,
            gateway("<html>portal</html>\r\n\r\n").address,
        ]
        for address in cases:
            with pytest.raises(CheckError) as caught:
                connect(address, "acct", password)
            assert password not in str(caught.value)
            assert "Basic" not in str(caught.value)

    def test_the_result_carries_no_credential_anywhere(self, gateway):
        server = gateway(ESTABLISHED)
        result = connect(server.address, "acct", "s3cr3t-do-not-print", reactions=REACTIONS)
        assert "s3cr3t" not in str(result)
        assert "s3cr3t" not in repr(result)
        assert "s3cr3t" not in str(result.headers)


class TestWhatIsActuallySentOnTheWire:
    def test_the_request_is_a_conditioned_connect(self, gateway):
        server = gateway(ESTABLISHED)
        connect(server.address, "acct-country-us", "pw", target="example.test:443")
        server.close()
        head = server.received.decode("latin-1")
        assert head.startswith("CONNECT example.test:443 HTTP/1.1\r\n")
        assert "Host: example.test:443\r\n" in head
        assert "Proxy-Authorization: Basic YWNjdC1jb3VudHJ5LXVzOnB3\r\n" in head
        assert head.endswith("\r\n\r\n")

    def test_the_target_is_a_parameter_because_there_is_no_null_connect(
        self, gateway
    ):
        # The gateway has to be asked for some target, and whatever is named
        # here sees a TCP connection from the exit address. That makes it the
        # caller's business, not a constant buried in the module.
        server = gateway(ESTABLISHED)
        connect(server.address, "acct", "pw", target="10.254.254.254:443")
        server.close()
        assert b"CONNECT 10.254.254.254:443" in server.received

    def test_a_target_carrying_crlf_is_refused_before_anything_is_sent(self):
        # Measured 2026-09-08: this reached the socket. `target` is interpolated
        # into `f"CONNECT {target} HTTP/1.1"`, so the gateway received a request
        # line of `CONNECT example.com:443` - no version token at all - and
        # `X-Injected: yes HTTP/1.1` as a header of our own request. Header
        # injection is the obvious half; the request line losing its version to
        # a caller's string is the half that is easy to miss.
        with pytest.raises(CheckError, match="Nothing was sent"):
            connect(
                "127.0.0.1:1", "acct", "pw",
                target="example.com:443\r\nX-Injected: yes",
                timeout=2.0,
            )

    @pytest.mark.parametrize(
        "target",
        ["", "a b:443", "a\nb:443", "a\tb:443", "a\x00b:443", "ex\xc3mple:443"],
    )
    def test_a_target_that_is_not_one_token_of_visible_ascii_is_refused(
        self, target
    ):
        # Deliberately wider than the characters that hurt. The request line is
        # built by interpolation and the set of bytes that change its shape is
        # not a thing to enumerate from memory - a space alone splits the line
        # into a different request. The address is a port nothing listens on,
        # so a test that fails does so by hanging on connect rather than by
        # quietly passing.
        with pytest.raises(CheckError, match="Nothing was sent"):
            connect("127.0.0.1:1", "acct", "pw", target=target, timeout=2.0)

    def test_the_credential_is_not_the_injection_surface_and_is_left_alone(
        self, gateway
    ):
        # The control on the rule above: a login containing CRLF cannot inject
        # anything, because it goes through base64 whose output alphabet is
        # A-Za-z0-9+/= and holds neither CR nor LF. Validating it would be
        # cargo-culting the fix onto the field that was already safe - and the
        # actual shape of the defect was the reverse of that. `Provider`
        # refuses CRLF in `country`, which is base64-encoded, while `target`,
        # which lands in the request line in the clear, was unchecked.
        server = gateway(ESTABLISHED)
        result = connect(server.address, "acct\r\nX-Injected: yes", "pw")
        server.close()
        assert result.ok
        head = server.received.decode("latin-1")
        assert "X-Injected" not in head
        assert head.count("\r\n\r\n") == 1


class TestTheHeadIsBounded:
    def test_a_long_header_block_does_not_read_forever(self, gateway):
        # A gateway that answers with a stream would otherwise be a memory
        # exhaustion bug. Bounded at 16 KiB; a real response head is a few
        # hundred bytes.
        #
        # This test asserted `result.status == 200` until 2026-09-08 and that
        # assertion was pinning the defect next door. The bound was enforced by
        # `break`, so the truncated buffer went to `_parse_head`, which found a
        # valid status line at the top of it and reported a complete answer
        # assembled from however many headers happened to fit. The bound is the
        # feature; parsing what the bound cut off is not.
        padding = "X-Pad: " + ("a" * 200) + "\r\n"
        server = gateway(
            "HTTP/1.1 200 Connection established\r\n" + padding * 200 + "\r\n"
        )
        with pytest.raises(CheckError, match="no end to the response head"):
            connect(server.address, "acct", "pw")


class TestAnUnfinishedHeadIsNotAnAnswer:
    """Truncation reported as a 200 was the second half of the CONNECT review.

    Found 2026-09-08 in an external review of both SDKs and reproduced the same
    day on a loopback socket. All three cases below returned a ``Check`` rather
    than raising, and the first two returned one whose ``ok`` was True.
    """

    def test_a_head_cut_off_mid_block_is_refused_rather_than_reported_as_ok(
        self, gateway
    ):
        # Measured 2026-09-08: this exact payload gave `status=200 ok=True
        # headers={}`. Both parts are wrong and the second is the quieter one -
        # the exit header is *in* the bytes and `_parse_head` drops it, because
        # a header line only enters the table when the blank line that ends the
        # block proves it arrived whole.
        server = gateway(
            "HTTP/1.1 200 Connection established\r\nX-Proxy-Exit-IP: 1.2.3.4"
        )
        with pytest.raises(CheckError, match="part-way through"):
            connect(server.address, "acct", "pw", exit_ip_header="X-Proxy-Exit-IP")

    def test_a_status_line_with_no_blank_line_after_it_is_refused(self, gateway):
        # The minimal case: everything a caller needs is present and the head
        # still never ended, so there is no way to know whether a header was on
        # its way. A gateway that means to answer 200 sends the blank line.
        server = gateway("HTTP/1.1 200 Connection established\r\n")
        with pytest.raises(CheckError, match="part-way through"):
            connect(server.address, "acct", "pw")

    def test_the_message_separates_truncation_from_an_immediate_close(
        self, gateway
    ):
        # Two different failures with two different causes: nothing at all is a
        # documented reaction of the shipped gateway - an empty parameter value
        # hangs and then closes - while a head that starts and stops is not, and
        # is worth reporting. One message for both would lose that.
        cut = gateway("HTTP/1.1 200 OK\r\nX-Pad: a")
        with pytest.raises(CheckError) as truncated:
            connect(cut.address, "acct", "pw")
        silent = gateway(None)
        with pytest.raises(CheckError) as nothing:
            connect(silent.address, "acct", "pw")
        assert "part-way through" in str(truncated.value)
        assert "without answering" in str(nothing.value)


#: Exactly what the shipped gateway answered on 2026-09-08, byte for byte,
#: read off `gate.nodemaven.com:8080` with a raw dump rather than off formatted
#: output. The success path frames its head with CRLF and every refusal frames
#: it with bare LF, so these are three payloads and one framing question.
#:
#: The exit address is the only edit: TEST-NET-3 per RFC 5737 in place of the
#: address the gateway returned. Everything else including the header *names* is
#: reproduced, because this back end sends `X-Exit-IP` and not the
#: `X-Proxy-Exit-IP` a caller may be looking for.
LIVE_407 = (
    b"HTTP/1.1 407 Proxy Authentication Required\n"
    b'Proxy-Authenticate: Basic realm="Invalid credentials"\n'
    b"Connection: close\n"
    b"\n"
)
LIVE_406 = b"HTTP/1.1 406 Not Acceptable\nConnection: close\n\n"
LIVE_200 = (
    b"HTTP/1.1 200 OK\r\n"
    b"X-Exit-IP: 203.0.113.104\r\n"
    b"X-Exit-Country: US\r\n"
    b"X-Exit-Timezone: America/Los_Angeles\r\n"
    b"X-Exit-ASN: 6167\r\n"
    b"\r\n"
)


class TestTheRealGatewaysBytes:
    """The three replies the shipped gateway actually sends.

    RFC 9112 section 2.2 lets a recipient treat a bare LF as a line terminator
    and ignore any preceding CR. That is permission rather than obligation
    everywhere except here: this gateway frames every refusal with LF and
    carries `Connection: close`, so a CRLF-only reader sees the peer hang up
    with no blank line, calls it a truncated head, and can report no refusal
    code at all - which is the one thing this module exists to do.
    """

    def test_the_407_that_a_bad_filter_value_produces(self, gateway):
        server = gateway(None, answer_bytes=LIVE_407)
        result = connect(
            server.address, "acct", "pw", reactions=REACTIONS
        )
        assert result.status == 407
        assert result.reason == "Proxy Authentication Required"
        assert not result.ok
        assert result.headers["connection"] == "close"
        assert result.headers["proxy-authenticate"] == (
            'Basic realm="Invalid credentials"'
        )
        # The whole point of carrying the table: the status says credentials and
        # the cause is a value the gateway would not take.
        assert result.meaning == REACTIONS["407"]

    def test_the_406_that_a_bad_region_produces(self, gateway):
        server = gateway(None, answer_bytes=LIVE_406)
        result = connect(server.address, "acct", "pw")
        assert result.status == 406
        assert result.reason == "Not Acceptable"
        assert result.headers == {"connection": "close"}

    def test_the_200_is_framed_the_other_way_and_still_parses(self, gateway):
        server = gateway(None, answer_bytes=LIVE_200)
        result = connect(server.address, "acct", "pw")
        assert result.ok
        assert result.reason == "OK"
        assert result.headers["x-exit-ip"] == "203.0.113.104"
        assert result.headers["x-exit-asn"] == "6167"

    def test_the_header_this_back_end_omits_reads_as_absent(self, gateway):
        # A caller asking for a name this reply does not carry gets None, not a
        # wrong address and not an error. The 200 above proves the address was
        # on the wire under another name; resolving that is a provider
        # definition question and not this function's.
        server = gateway(None, answer_bytes=LIVE_200)
        result = connect(
            server.address, "acct", "pw", exit_ip_header="X-Proxy-Exit-IP"
        )
        assert result.exit_ip is None


class TestABlankLineHasFourSpellings:
    @pytest.mark.parametrize(
        "terminator", [b"\r\n\r\n", b"\n\n", b"\r\n\n", b"\n\r\n"]
    )
    def test_every_spelling_ends_the_head(self, gateway, terminator):
        # Once a bare LF is a terminator, the blank line is any of these four,
        # including the two mixed ones - which are what a gateway assembling a
        # reply from a template and a variable body produces.
        head = b"HTTP/1.1 200 OK\r\nX-Exit-ASN: 6167"
        server = gateway(None, answer_bytes=head + terminator)
        result = connect(server.address, "acct", "pw")
        assert result.status == 200
        assert result.headers == {"x-exit-asn": "6167"}

    def test_body_bytes_in_the_same_segment_are_not_parsed_as_headers(
        self, gateway
    ):
        # The head ends at the blank line and the read stops there. Anything
        # after it belongs to the tunnel, and a header table assembled from
        # tunnel bytes would be a security bug rather than a parsing one.
        server = gateway(
            None,
            answer_bytes=LIVE_200 + b"\x16\x03\x01\x00\x01X-Exit-IP: 10.0.0.1\r\n",
        )
        result = connect(server.address, "acct", "pw")
        assert result.headers["x-exit-ip"] == "203.0.113.104"
        assert len(result.headers) == 4

    def test_a_cr_that_is_not_before_the_lf_stays_in_the_value(self, gateway):
        # Only a CR immediately before the LF is a line terminator. One in the
        # middle of a value is part of the value, and repairing it would be
        # this function inventing a reply the gateway did not send.
        server = gateway(None, answer_bytes=b"HTTP/1.1 200 OK\nX-Pad: a\rb\n\n")
        result = connect(server.address, "acct", "pw")
        assert result.headers == {"x-pad": "a\rb"}


class TestLfFramingDoesNotUndoTheTruncationGuard:
    """The fix widens what counts as a complete head and nothing else.

    Both halves have to hold at once: an LF-framed refusal is an answer, and an
    LF-framed head that stops without its blank line is still not one. A fix
    that got only the first half would report every truncation as a 200 again.
    """

    def test_an_lf_framed_head_with_no_blank_line_is_still_refused(
        self, gateway
    ):
        server = gateway(
            None,
            answer_bytes=b"HTTP/1.1 407 Proxy Authentication Required\n"
            b"Connection: close\n",
        )
        with pytest.raises(CheckError, match="part-way through"):
            connect(server.address, "acct", "pw")

    def test_a_bare_lf_status_line_alone_is_still_refused(self, gateway):
        server = gateway(None, answer_bytes=b"HTTP/1.1 200 OK\n")
        with pytest.raises(CheckError, match="part-way through"):
            connect(server.address, "acct", "pw")

    def test_a_single_lf_is_not_a_blank_line(self, gateway):
        # The one case that separates "ends a line" from "ends the head": a
        # head whose last line ended and whose blank line never came.
        server = gateway(None, answer_bytes=b"HTTP/1.1 406 Not Acceptable\n")
        with pytest.raises(CheckError, match="part-way through"):
            connect(server.address, "acct", "pw")


class TestProxyCheckWiresTheProviderIn:
    def test_check_passes_the_providers_reaction_table(self, gateway):
        # The bug this pins: the meaning depends on the status, and the status
        # is not known until the connect returns. Passing a single resolved
        # `reaction` from the call site would always be None, which would leave
        # the whole table unread while every other test still passed.
        server = gateway("HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
        host, _, port = server.address.rpartition(":")
        proxy = Proxy(
            login="acct", password="pw", host=host, port=int(port), country="us"
        )
        result = proxy.check(timeout=5.0)
        assert result.status == 407
        assert result.meaning is not None
        assert "NOT your credentials" in result.meaning

    def test_check_reads_the_exit_header_the_provider_declares(self, gateway):
        server = gateway(ESTABLISHED)
        host, _, port = server.address.rpartition(":")
        proxy = Proxy(login="acct", password="pw", host=host, port=int(port))
        result = proxy.check(timeout=5.0)
        assert result.exit_ip == "203.0.113.7"

    def test_check_sends_the_built_username_and_not_the_bare_login(self, gateway):
        server = gateway(ESTABLISHED)
        host, _, port = server.address.rpartition(":")
        proxy = Proxy(
            login="acct", password="pw", host=host, port=int(port),
            country="us", filter="medium",
        )
        proxy.check(timeout=5.0)
        server.close()
        import base64

        head = server.received.decode("latin-1")
        token = head.split("Basic ", 1)[1].split("\r\n", 1)[0]
        assert base64.b64decode(token).decode() == "acct-country-us-filter-medium:pw"


class TestSessions:
    def test_every_identity_is_distinct(self):
        proxy = Proxy(login="acct", password="pw", country="us")
        batch = proxy.sessions(25)
        assert len({p.username for p in batch}) == 25

    def test_the_ids_are_hex_and_that_is_load_bearing(self):
        # Measured 2026-08-20: the gateway cuts a value at the separator, so an
        # id containing one collapses every id sharing a prefix onto a single
        # exit - silently, because the connection succeeds. `token_urlsafe`
        # emits `-` and `_`, `uuid4` emits `-`, base64 emits `+` and `/`, and
        # every one of those is a separator on some gateway.
        proxy = Proxy(login="acct", password="pw")
        for child in proxy.sessions(10, length=8):
            session_id = child.params["sid"]
            assert len(session_id) == 16
            assert all(c in "0123456789abcdef" for c in session_id)

    def test_the_parent_is_untouched(self):
        proxy = Proxy(login="acct", password="pw", country="us", sid="seed")
        proxy.sessions(3)
        assert proxy.params["sid"] == "seed"

    def test_a_nonsense_count_is_refused(self):
        proxy = Proxy(login="acct", password="pw")
        with pytest.raises(Exception, match="no identities"):
            proxy.sessions(0)

    def test_a_nonsense_length_is_refused(self):
        proxy = Proxy(login="acct", password="pw")
        with pytest.raises(Exception, match="length"):
            proxy.sessions(2, length=0)

    def test_more_ids_than_exist_is_refused_rather_than_looped_forever(self):
        # Measured 2026-09-08, from an external review: `sessions(257,
        # length=1)` did not return in 4 s and `sessions(200, length=1)` built
        # 200 immediately. Rejection sampling cannot produce more distinct
        # values than the space holds, so the 257th draw is an unbounded loop
        # holding the CPU - not a slow call, a call that never ends.
        #
        # This test would hang rather than fail against the old code, which is
        # the reason it is written against `length=1`: the failure is cheap to
        # provoke at 256 values and impossible to provoke at 2**48.
        proxy = Proxy(login="acct", password="pw")
        with pytest.raises(Exception, match="at least the whole space"):
            proxy.sessions(257, length=1)

    def test_the_whole_space_is_refused_and_one_less_is_not(self):
        # Where the boundary is put and why. `count.bit_length() > 8 * length`
        # is exactly `count >= 2**bits`, which refuses 256 here and allows 255 -
        # one comparison, no exponentiation, the same answer in a language whose
        # integers overflow. Asking for the entire space would draw every value
        # that exists and leave none for the next process, which is the failure
        # the docstring's second paragraph is about.
        #
        # The message was "asks for more distinct ids than exist" until
        # 2026-09-08, and at this exact boundary that sentence is false: 256 of
        # them do exist, and the refusal is because taking all of them is a
        # coupon-collector loop that leaves the space empty, not because they
        # are missing. The guard was right and its explanation was not - caught
        # by writing the same bound into the README and finding the two
        # sentences could not both be true.
        proxy = Proxy(login="acct", password="pw")
        with pytest.raises(Exception, match="at least the whole space"):
            proxy.sessions(256, length=1)
        assert len({p.params["sid"] for p in proxy.sessions(255, length=1)}) == 255

    def test_the_default_length_refuses_nothing_anybody_would_ask_for(self):
        # The control on the guard: a bound that bites a real caller is a
        # regression dressed as a fix. The default is 6 bytes, so the ceiling is
        # 2**48 identities and no call anyone writes comes near it.
        proxy = Proxy(login="acct", password="pw")
        assert len(proxy.sessions(64)) == 64
