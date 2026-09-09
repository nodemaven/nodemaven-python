"""One CONNECT, and what the gateway said about it.

This is the only module in the package that opens a socket, and it does it in
the smallest form there is: a raw ``CONNECT`` and the status line that comes
back. No TLS, no HTTP client, no target traffic, no dependency.

The reason it is written by hand rather than delegated to an HTTP library is
that **the diagnosis is in the status line and libraries throw it away.**
``requests`` reports a failed tunnel as
``ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed:
407 Proxy Authentication Required'))`` - the code survives as text inside a
nested exception, and the reason phrase and every response header do not. On
this gateway the reason phrase identifies which back end answered and one of
the headers carries the exit address, so both are worth more than the
convenience of not writing this file.

There is also a failure mode this shape makes impossible. The vendor's own
client has a ``get_current_ip(proxies=...)`` whose fallback path - taken
whenever ``requests`` is not installed - builds a plain
``urllib.request.Request`` and never installs a ``ProxyHandler``, so the
``proxies`` argument is silently discarded and the function returns **your own
address** while reporting it as the proxy's exit. Read in
``nodemavencom/proxy``, ``python/nodemaven/utils.py``, on 2026-09-07. Here
there is no code path that does not go through the proxy socket, because the
socket is the whole implementation.
"""

from __future__ import annotations

import base64
import socket
import time
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from .errors import CheckError

__all__ = ["Check", "connect"]

#: What a CONNECT is opened *to*. The gateway has to be asked for some target,
#: there is no null CONNECT, so this is a real host that will see a TCP
#: connection from the exit address. It is a parameter on every entry point and
#: this is only the default.
#:
#: Port 443 and not 80 because a gateway may treat plaintext differently, and
#: because 443 is what a caller's real traffic will use.
DEFAULT_TARGET = "api.ipify.org:443"

#: What this client *sends*. Reading is deliberately laxer - see
#: :func:`_head_end` - because being strict about what you send and liberal
#: about what you accept are the same rule, not opposite ones.
_CRLF = "\r\n"
_MAX_HEAD = 16384


@dataclass(frozen=True)
class Check:
    """What one CONNECT produced.

    A refusal is a **result and not an exception**: the status code is the thing
    the caller came for, and raising would push the useful part into a traceback.
    :class:`~nodemaven.errors.CheckError` is reserved for the cases where nothing
    came back at all.
    """

    #: The CONNECT status, e.g. 200 or 407.
    status: int
    #: The reason phrase, verbatim and not normalised. On the shipped gateway
    #: this identifies which back end answered: measured 2026-08-13, a 200
    #: carrying ``X-Proxy-Exit-IP`` arrives as ``Connection established``, while
    #: the ones that arrive as ``OK`` or ``Connection Established`` do not carry
    #: it. Any per-implementation number has to be split on this rather than
    #: pooled, so it is preserved byte for byte.
    reason: str
    #: ``host:port`` of the gateway, with no credentials in it.
    server: str
    #: Wall-clock seconds from the first byte sent to the status line parsed.
    #: Includes DNS and the TCP handshake, and is not comparable against a
    #: number measured on a different network path.
    elapsed: float
    #: The response headers, lower-cased keys, in the order they arrived.
    headers: Dict[str, str]
    #: The exit address, when the gateway sent one on the header its provider
    #: definition declares. ``None`` is normal rather than an error - on the
    #: shipped gateway only one of at least three back ends sends it.
    exit_ip: Optional[str] = None
    #: What this status means on this gateway, from the provider definition, or
    #: ``None`` if that gateway has no entry for it. This is where a 407 gets
    #: told not to go and check its password.
    meaning: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Whether the tunnel opened.

        True means the gateway accepted the credentials and every parameter it
        recognised. It does **not** mean every parameter was applied: an
        unrecognised name is answered 200 and dropped. That is why this package
        refuses unknown names before sending, and why ``ok`` cannot be the whole
        answer on its own.
        """
        return self.status == 200

    def __str__(self) -> str:
        head = f"{self.status} {self.reason} via {self.server} in {self.elapsed:.2f}s"
        if self.exit_ip:
            head += f", exit {self.exit_ip}"
        if self.meaning and not self.ok:
            head += f"\n{self.meaning}"
        return head


def connect(
    server: str,
    username: str,
    password: str,
    *,
    target: str = DEFAULT_TARGET,
    timeout: float = 15.0,
    exit_ip_header: Optional[str] = None,
    reactions: Optional[Mapping[str, str]] = None,
) -> Check:
    """Open one CONNECT through ``server`` and report what came back.

    ``username`` and ``password`` go into a ``Proxy-Authorization`` header.
    **That header is never logged, never put in an exception message and never
    returned**: it is base64 and not encryption, so anything that prints one has
    put a working credential into a terminal history, a CI log and whatever bug
    report gets pasted next.

    ``timeout`` defaults to 15 s rather than to something small, because one of
    the gateway's documented reactions is *no reply at all* - an empty parameter
    value hangs the connection for about 20 s. A 5 s timeout would report that
    as a network problem. This package refuses empty values before sending, so
    the case should be unreachable through :class:`~nodemaven.Proxy`; the
    default is set for the caller who assembles a username by hand.

    ``reactions`` is the provider's ``connect_reactions`` table, keyed by the
    status code as a string. It is passed in as plain data rather than looked up
    through a ``Provider``, so this module needs nothing from the rest of the
    package except one exception class - which is what makes it testable against
    a socket on loopback and reusable by anyone assembling a username by hand.

    Raises :class:`~nodemaven.errors.CheckError` in two situations. Before
    anything is sent, when ``server`` or ``target`` cannot make a well-formed
    request line - those messages end in *Nothing was sent*. After sending, when
    there was no usable answer: DNS failure, refused connection, timeout, a head
    that never ended, or a status line that is not one.
    """
    host, _, port_text = server.rpartition(":")
    port = _port_number(port_text)
    if not host or port is None:
        raise CheckError(
            f"{server!r} is not a gateway address: it has to be host:port, with "
            f"a port from 1 to 65535. Nothing was sent."
        )
    if not _is_request_target(target):
        raise CheckError(
            f"{target!r} cannot go in a request line: a target is visible ASCII "
            f"with no spaces, so that it lands in the CONNECT as one token. "
            f"Nothing was sent."
        )

    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = (
        f"CONNECT {target} HTTP/1.1{_CRLF}"
        f"Host: {target}{_CRLF}"
        f"Proxy-Authorization: Basic {token}{_CRLF}"
        f"Proxy-Connection: close{_CRLF}"
        f"{_CRLF}"
    ).encode("utf-8")

    started = time.monotonic()
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.sendall(request)
        head = _read_head(sock, timeout)
    except OSError as exc:
        # Deliberately not chained into the message with the request bytes in
        # scope. `request` holds the credential and an f-string that happened to
        # include it would leak it into every traceback.
        raise CheckError(
            f"no answer from {server}: {exc}. Nothing here can tell you whether "
            f"the credentials are right, because the gateway was never reached."
        ) from exc
    finally:
        if sock is not None:
            sock.close()
    elapsed = time.monotonic() - started

    status, reason, headers = _parse_head(head, server)
    exit_ip = headers.get(_ascii_lower(exit_ip_header)) if exit_ip_header else None
    return Check(
        status=status,
        reason=reason,
        server=server,
        elapsed=elapsed,
        headers=headers,
        exit_ip=exit_ip,
        meaning=(reactions or {}).get(str(status)),
    )


def _head_end(buffer: bytes) -> int:
    """Index just past the blank line that ends a response head, or ``-1``.

    A blank line has four spellings once a bare LF is allowed as a terminator -
    ``\\r\\n\\r\\n``, ``\\n\\n``, ``\\r\\n\\n`` and ``\\n\\r\\n`` - and searching
    for the earlier of ``\\n\\n`` and ``\\n\\r\\n`` covers all four, because
    every one of them ends in one of those two.

    LF is accepted because RFC 9112 section 2.2 says a recipient may recognise a
    single LF as a line terminator and ignore any preceding CR, and because this
    gateway needs it: a 200 is framed CRLF and every refusal - 406, 407, 500 -
    is framed with bare LF. A CRLF-only reader cannot report any refusal code
    from it, which is the one thing :func:`check` exists to do.
    """
    end = -1
    for terminator in (b"\n\n", b"\n\r\n"):
        found = buffer.find(terminator)
        if found >= 0 and (end < 0 or found + len(terminator) < end):
            end = found + len(terminator)
    return end


def _read_head(sock: socket.socket, timeout: float) -> bytes:
    """Read up to and including the blank line that ends the response head.

    Reads no further, so nothing is consumed from the tunnel body even when the
    tunnel opened, and any body bytes that arrived in the same segment are cut
    off rather than parsed as headers. Bounded at 16 KiB: a response head is a
    few hundred bytes, so an unbounded read here is a memory exhaustion bug
    waiting for a gateway that answers with a stream.

    **An unterminated head is refused rather than returned.** A peer that sends
    ``HTTP/1.1 200 OK\\r\\nX-Proxy-Exit-IP: 1.2.3.4`` and then hangs up mid-head
    would otherwise parse as ``status=200``, ``ok=True``, ``headers={}``: the
    caller is told the tunnel opened and the one field it would have read off
    the reply has silently gone missing. The message names which of the two
    truncations happened, because they have different causes and different
    fixes.

    An immediate close with nothing at all is not truncation - it is a
    documented reaction of this gateway - so it returns empty and
    :func:`_parse_head` has the sentence for it.
    """
    sock.settimeout(timeout)
    buffer = bytearray()
    while True:
        end = _head_end(buffer)
        if end >= 0:
            return bytes(buffer[:end])
        if len(buffer) > _MAX_HEAD:
            raise CheckError(
                f"{len(buffer)} bytes from the gateway with no end to the "
                f"response head. A head is a few hundred bytes, so this is a "
                f"stream and not a reply, and reading further is how a client "
                f"runs out of memory."
            )
        chunk = sock.recv(4096)
        if not chunk:
            if not buffer:
                return b""
            raise CheckError(
                f"the connection closed after {len(buffer)} bytes, part-way "
                f"through the response head. Whatever came before the cut is "
                f"not an answer - a status line without its blank line may be "
                f"missing headers that had not arrived yet."
            )
        buffer.extend(chunk)


def _is_ascii_digits(text: str) -> bool:
    """Whether ``text`` is one or more of ``0``-``9`` and nothing else.

    Spelled out rather than ``str.isdigit()``, which is the thing this module
    got wrong twice. ``isdigit()`` answers a question about Unicode categories
    and every caller here is asking a question about ``int()``: the two disagree
    on ``'\\xb2'``, where ``isdigit()`` is True and ``int()`` raises
    ``ValueError``. ``str.isascii() and str.isdigit()`` would also work and is
    3.7+; the comparison is written out because this is a rule four SDKs have to
    hold identically, and a comparison ports where a standard-library predicate
    does not.
    """
    return bool(text) and all("0" <= character <= "9" for character in text)


def _is_status_code(text: str) -> bool:
    """Whether ``text`` is an HTTP status code: exactly three ASCII digits.

    ``str.isdigit()`` was the obvious spelling and it was a bug, found on
    2026-09-07 while porting this module to Rust. It is True for characters
    ``int()`` refuses - ``'\\xb2'.isdigit()`` is True and ``int('\\xb2')`` raises
    ``ValueError`` - and this function is reachable with exactly those
    characters, because the head above is decoded **latin-1 on purpose** so that
    any byte a proxy is entitled to send is accepted. So the deliberate widening
    of the input alphabet is what made the narrow check unsound: bytes 0xB9,
    0xB2 and 0xB3 in a status line produced an uncaught ``ValueError``, past a
    docstring promising that only :class:`~nodemaven.errors.CheckError` comes
    out of here.

    Three digits and not "one or more" because that is what the specification
    says - RFC 9110 calls the status code a three-digit integer - and because it
    is the rule the Rust port can hold in a ``u16`` without diverging. A gateway
    answering anything else is the case the caller's error message already
    describes: something other than a proxy is listening, or a middlebox
    answered instead.
    """
    return len(text) == 3 and _is_ascii_digits(text)


def _is_http_version(text: str) -> bool:
    """Whether ``text`` is an HTTP version token: ``HTTP/`` and two digits.

    RFC 9112 section 2.3 spells it ``HTTP-name "/" DIGIT "." DIGIT`` and makes
    ``HTTP`` case-sensitive, so this is the grammar and not a house rule. Eight
    characters exactly, because a CONNECT answered over a TCP socket this module
    opened itself is HTTP/1.x by construction - there is no version negotiation
    to be liberal about.

    It exists because it was missing, found 2026-09-08 in an external review and
    reproduced the same day on a loopback socket. ``_parse_head`` split the
    status line and looked only at the *second* token, so the first was accepted
    whatever it was: ``garbage 200 OK`` came back as ``status=200``, ``ok=True``
    - and with ``exit=1.2.3.4`` when the same non-proxy also sent the exit
    header. That is the worst available failure, because ``ok`` is what a caller
    branches on and the exit address is what it then reports as its own.

    What the mistake looked like from the inside: the rules this module states in
    words all ported to Rust exactly - three digits, ASCII digits, ASCII
    lower-casing are each a paragraph here and each landed there intact. This
    rule was never written down anywhere, so ``check.rs`` reproduced the hole
    line for line: ``let _version = parts.next();``, discarded on purpose,
    reviewed by nobody. **A cross-language contract is only the part that was
    written down**; whatever is left implicit is re-implemented by hand in every
    port, and re-implemented the same way, because the same reading produced it.
    """
    return (
        len(text) == 8
        and text.startswith("HTTP/")
        and _is_ascii_digits(text[5])
        and text[6] == "."
        and _is_ascii_digits(text[7])
    )


def _is_request_target(text: str) -> bool:
    """Whether ``text`` can go into a request line as a single token.

    Visible ASCII with no space: bytes 0x21 to 0x7E. It is deliberately narrow
    rather than a check for the specific characters that hurt, because the
    request line is assembled by string interpolation and the set of characters
    that change its shape is not something to enumerate from memory.

    The case that motivated it, measured 2026-09-08 on a loopback socket:
    ``target="example.com:443\\r\\nX-Injected: yes"`` was interpolated straight
    into ``f"CONNECT {target} HTTP/1.1"``, so the gateway received a request line
    of ``CONNECT example.com:443`` with **no version token at all**, and
    ``X-Injected: yes HTTP/1.1`` as a header of our own request. Header
    injection is the obvious half; the request line losing its version to a
    caller-supplied string is the half that is easy to miss.

    Two things this deliberately does not do, worth stating so the next port does
    not add them by guesswork. It does not check that ``target`` is
    ``host:port`` - the gateway is entitled to its own opinion about what it will
    tunnel to, and a client that refuses a target the server would have accepted
    is a client that has to be worked around. And it does not touch ``username``
    or ``password``, which cannot inject anything at all: they go through
    ``base64`` two lines below, whose output alphabet is ``A-Za-z0-9+/=`` and
    contains neither CR nor LF. The package validating what gets base64-encoded
    while leaving the one field that lands in the clear unvalidated was the
    actual shape of this defect.
    """
    return bool(text) and all(" " < character <= "~" for character in text)


def _port_number(text: str) -> Optional[int]:
    """``text`` as a TCP port, or ``None`` if it is not one.

    The same defect as ``_is_status_code`` above, in the other half of the
    module and found the same day: the gate here was ``port_text.isdigit()``,
    and ``connect("127.0.0.1:\\xb2", ...)`` raised an uncaught ``ValueError``
    from the ``int()`` two lines below it. The first fix caught one of the two
    occurrences, which is the ordinary shape of this mistake - a predicate is
    corrected where it was noticed rather than everywhere it is used.

    The length guard is not the same rule twice. ``isdigit()`` also accepts a
    digit string of any length, so ``'99999999999999999999'`` reached ``int()``,
    succeeded there, and raised ``OverflowError`` inside ``create_connection``
    - and ``OverflowError`` derives from ``ArithmeticError``, not ``OSError``,
    so it walked straight past the handler that exists to turn everything from
    the socket layer into a ``CheckError``. Refusing more than five characters
    means ``int()`` is only ever called on something that fits, which also
    sidesteps CPython 3.11+ refusing ``int()`` on a string of over 4300 digits.

    Port 0 is refused. It is legal in ``bind`` and means "any free port", and it
    is meaningless in ``connect``: on Windows it fails with WinError 10049 and
    on Linux it is answered ``ECONNREFUSED``, so refusing it here replaces a
    platform-specific errno with the sentence that says what to fix.
    """
    if not _is_ascii_digits(text) or len(text) > 5:
        return None
    port = int(text)
    return port if 1 <= port <= 65535 else None


def _parse_head(head: bytes, server: str) -> "tuple":
    """Split a response head into status, reason phrase and headers.

    A status line is accepted only when its **first two tokens** are an HTTP
    version and a three-digit status code, per :func:`_is_http_version` and
    :func:`_is_status_code`. Only the second was checked until 2026-09-08, which
    is how ``garbage 200 OK`` parsed as a 200.

    Lines are split on LF with one optional preceding CR stripped, which accepts
    a head framed either way for the reason given in :func:`_head_end`. A CR
    anywhere else in a line is left alone: it is part of the value, and this
    function does not repair a malformed reply.

    Decoded as latin-1 and never as utf-8. A header value is bytes by
    specification and a gateway is free to put anything in a reason phrase; utf-8
    would raise on a byte a proxy is entitled to send, turning a readable
    diagnosis into a decode error. latin-1 cannot fail, and the reason phrase is
    something a human reads rather than something this package matches on.
    """
    if not head:
        raise CheckError(
            f"{server} accepted the connection and then closed it without "
            f"answering. That is not one of the reactions this gateway is known "
            f"to have, so it is worth reporting with the parameters that produced "
            f"it."
        )
    text = head.decode("latin-1")
    lines = [
        line[:-1] if line.endswith("\r") else line for line in text.split("\n")
    ]
    parts = lines[0].split(" ", 2)
    if (
        len(parts) < 2
        or not _is_http_version(parts[0])
        or not _is_status_code(parts[1])
    ):
        raise CheckError(
            f"{server} answered {lines[0]!r}, which is not an HTTP status line. "
            f"Either something other than a proxy is listening on that port, or "
            f"a middlebox answered instead of the gateway."
        )
    status = int(parts[1])
    reason = parts[2] if len(parts) > 2 else ""

    headers: Dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            break
        name, sep, value = line.partition(":")
        if sep:
            headers[_ascii_lower(name.strip())] = value.strip()
    return status, reason, headers


def _ascii_lower(text: str) -> str:
    """Lower-case ``A``-``Z`` and leave every other character alone.

    ``str.lower()`` was here and it is a portability trap rather than a bug
    today, found 2026-09-07 while writing the Rust port. Both languages have a
    Unicode-aware lower-casing and an ASCII-only one, and they do not agree:
    this head is decoded latin-1 on purpose, so a field name containing byte
    ``0xC0`` reaches here as ``'\\xc0'``, Python's ``.lower()`` makes it
    ``'\\xe0'`` and Rust's ``to_ascii_lowercase`` leaves it as ``'\\xc0'``. Two
    SDKs would then key the same response header two ways.

    ASCII-only is not merely the portable choice, it is the correct one: RFC 9110
    says a field name is a token and a token is ASCII, so a non-ASCII byte in one
    is already malformed and nothing is served by folding it. This is the same
    decision, for the same reason, as the ASCII-only fold in
    ``Provider.normalized`` - and that one is pinned by a test in both SDKs
    because ``str.lower()`` and Rust's ``to_lowercase`` disagree with each other
    on the Turkish dotted capital I as well.
    """
    return "".join(
        chr(ord(character) + 32) if "A" <= character <= "Z" else character
        for character in text
    )
