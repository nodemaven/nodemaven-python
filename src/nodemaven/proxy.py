"""One proxy identity, and the strings a client needs to use it.

This module opens no socket. It builds a username in the gateway's dialect,
refuses input the gateway would mishandle, and hands the result to whatever HTTP
client you already have.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import quote

from .check import DEFAULT_TARGET, Check
from .check import _port_number
from .check import connect as _connect
from .errors import CredentialsError, ParamError
from .providers import ASCII_WHITESPACE, Provider, load

__all__ = ["Proxy"]

# Constructor names that are ours rather than the gateway's. A definition whose
# known_params collide with one of these is refused at construction, because the
# alternative is a parameter silently arriving as a credential or the reverse.
_RESERVED = frozenset({"login", "password", "host", "port", "provider"})

_REDACTED = "***"


class Proxy:
    """A set of gateway parameters plus the credentials to use them.

    ::

        proxy = Proxy(login="user", password="pass", country="us", sid="a1")
        requests.get(url, proxies=proxy.requests())

    Credentials fall back to the environment when not passed, under the
    provider's id in upper case: ``NODEMAVEN_LOGIN``, ``NODEMAVEN_PASSWORD``,
    ``NODEMAVEN_HOST``, ``NODEMAVEN_PORT``.

    **One instance is one identity.** On the gateway this package ships a
    definition for, the sticky session key is the whole recognised parameter
    set and not the session id alone: ``country=us, sid=A`` and
    ``country=us, sid=A, filter=medium`` are two different sessions, and adding
    or removing any parameter moves you to a different exit address without
    saying so. Build the object once and reuse it; use :meth:`replace` when you
    intend to move, so that the move is written down.
    """

    __slots__ = ("_provider", "_login", "_password", "_host", "_port", "_params")

    def __init__(
        self,
        *,
        login: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        provider: Optional[Provider] = None,
        **params: Any,
    ) -> None:
        self._provider = provider if provider is not None else load()

        collision = sorted(self._provider.known_params & _RESERVED)
        if collision:
            raise ParamError(
                f"provider {self._provider.label} names {collision} as gateway "
                f"parameters, and this constructor already uses those names for "
                f"credentials. Pass those settings through replace() on a "
                f"provider whose definition renames them, or rename them with "
                f"an alias."
            )

        env = self._provider.id.upper().replace("-", "_")
        self._login = login if login is not None else os.environ.get(f"{env}_LOGIN")
        self._password = (
            password if password is not None else os.environ.get(f"{env}_PASSWORD")
        )
        raw_host = host if host is not None else os.environ.get(f"{env}_HOST")
        raw_port = port if port is not None else os.environ.get(f"{env}_PORT")

        self._host = raw_host or self._provider.host
        # Through `check._port_number` and not `int()`, and the import across
        # modules is the point rather than a shortcut. That function already
        # holds the rule - ASCII digits only, at most five of them, 1 to 65535 -
        # with the three defects that produced it written down beside it. A
        # second `int()` here is a second implementation of the same rule, and a
        # rule with two implementations is the thing that let `check.rs` ship
        # the missing `HTTP/` check that `check.py` also had.
        #
        # Measured 2026-09-08, both from an external review: `port='abc'` raised
        # `ValueError: invalid literal for int() with base 10: 'abc'`, which is
        # neither of this package's exception types and mentions nothing a
        # caller can act on; and `port='0'` raised `CredentialsError` saying
        # "pass host= and port=", although the port *was* passed. The first was
        # the wrong class, the second the wrong sentence - both from `int()`
        # accepting more than a port is and then a truthiness test standing in
        # for a range check.
        #
        # The provider's own port went through this rule from 2026-09-09; until
        # then that fallback was assigned unchecked, so a definition carrying
        # `port = 70000` built `host:70000` and nothing refused it. The value is
        # now also checked in `providers.load_file`, which is the layer that can
        # name the file it came from - this branch stays because `Provider` is a
        # public dataclass and can be built in code without going through the
        # loader.
        #
        # **Which of the two it was has to be said**, and the first version of
        # this fix did not say it: one message served both, so a bad port in a
        # TOML file was reported as `port=70000 is not a TCP port` followed by
        # `the gateway's own ports are 70000`, blaming a `port=` argument the
        # caller never passed and quoting the bad value back as the good one.
        from_provider = raw_port in (None, "")
        if from_provider:
            raw_port = self._provider.port
        self._port = None if raw_port is None else _port_number(str(raw_port))
        if raw_port is not None and self._port is None:
            if from_provider:
                raise CredentialsError(
                    f"the {self._provider.label} definition gives its port as "
                    f"{raw_port!r}, which is not a TCP port: it has to be a "
                    f"whole number from 1 to 65535. Nothing was built. You "
                    f"passed no port=, so this is the provider definition and "
                    f"not your call - fix the definition, or pass port= to "
                    f"override it."
                )
            raise CredentialsError(
                f"port={raw_port!r} is not a TCP port: it has to be a whole "
                f"number from 1 to 65535. Nothing was built. The gateway's "
                f"own ports are {self._provider.port} and the ones its "
                f"documentation lists; 0 is not one of them - it means 'any "
                f"free port' when binding and is meaningless when connecting."
            )

        if not self._login or not self._password:
            missing = [
                name
                for name, value in (("login", self._login), ("password", self._password))
                if not value
            ]
            raise CredentialsError(
                f"no {' and no '.join(missing)} for {self._provider.label}: pass "
                f"it to Proxy() or set {env}_LOGIN and {env}_PASSWORD in the "
                f"environment. Nothing was built, so nothing will connect."
            )
        if not self._host or not self._port:
            raise CredentialsError(
                f"no gateway address for {self._provider.label}: pass host= and "
                f"port= or set {env}_HOST and {env}_PORT."
            )

        self._params = _validate(self._provider, params)

    # -- what a client needs ------------------------------------------------

    @property
    def provider(self) -> Provider:
        """The gateway definition this identity was built against.

        Exposed because it answers the two questions a caller cannot otherwise
        ask: ``provider.known_params`` is what this object will accept, and
        ``provider.is_measured`` is whether anyone has confirmed the dialect
        against the gateway or only read it out of documentation.
        """
        return self._provider

    @property
    def params(self) -> Dict[str, str]:
        """The gateway parameters, as they will be sent. A copy."""
        return dict(self._params)

    @property
    def server(self) -> str:
        """``host:port``, with no credentials in it."""
        return f"{self._host}:{self._port}"

    @property
    def username(self) -> str:
        """The proxy username carrying every parameter, in the gateway's dialect."""
        provider = self._provider
        parts = [provider.prefix.format(login=self._login)]
        for key, value in self._params.items():
            parts.append(f"{provider.spell(key)}{provider.pair_separator}{value}")
        return provider.separator.join(parts)

    def url(self, scheme: str = "http") -> str:
        """``http://user:pass@host:port``, for requests, httpx, curl and aiohttp.

        Both credentials are percent-encoded with an empty ``safe`` set. A URL
        has structure, and the structure is made of the characters ``: @ / ? #``;
        a password containing any of them cuts the string in the wrong place and
        the client connects somewhere else entirely. ``pa/ss`` unencoded ends the
        authority at the slash, so the host becomes ``pa``.

        That failure is worse than an exception, because at least one browser
        engine answers a proxy URL it cannot parse by connecting **directly**
        without reporting it - the request then leaves from your own address
        while everything downstream believes it went through the pool.

        Note the asymmetry with :meth:`playwright`, which must not encode:
        there the fields are passed separately and the library encodes them
        itself, so encoding here as well turns ``pa/ss`` into ``pa%252Fss`` and
        authentication fails while blaming the credentials.
        """
        user = quote(self.username, safe="")
        secret = quote(self._password, safe="")
        return f"{scheme}://{user}:{secret}@{self.server}"

    def requests(self, scheme: str = "http") -> Dict[str, str]:
        """A ``proxies=`` mapping for requests. Also works for aiohttp's ``proxy=``
        via :meth:`url`."""
        url = self.url(scheme)
        return {"http": url, "https": url}

    def httpx(self, scheme: str = "http") -> Dict[str, str]:
        """A ``mounts``-style mapping for httpx. Modern httpx also takes
        ``proxy=proxy.url()`` directly."""
        url = self.url(scheme)
        return {"http://": url, "https://": url}

    def playwright(self) -> Dict[str, str]:
        """A ``proxy=`` dict for Playwright, Patchright and Puppeteer.

        Deliberately not percent-encoded - see :meth:`url`.
        """
        return {
            "server": f"http://{self.server}",
            "username": self.username,
            "password": self._password,
        }

    # -- moving deliberately ------------------------------------------------

    def replace(self, **changes: Any) -> "Proxy":
        """A new identity with parameters added, changed, or removed with ``None``.

        This returns a new object rather than mutating, because on a gateway
        whose session key is the whole parameter set, changing a parameter is
        not an adjustment to one identity - it is a different identity on a
        different exit address. A method that returned ``self`` would hide that.
        """
        params: Dict[str, Any] = dict(self._params)
        for key, value in changes.items():
            if value is None:
                params.pop(key, None)
            else:
                params[key] = value
        return Proxy(
            login=self._login,
            password=self._password,
            host=self._host,
            port=self._port,
            provider=self._provider,
            **params,
        )

    def session(self, session_id: str) -> "Proxy":
        """The same parameters, pinned to one sticky session.

        A provider that declares no session parameter gets none, and the id is
        dropped rather than sent under a guessed name: a name this gateway does
        not know is answered with 200 and ignored, so every request would draw a
        fresh exit while your code believed it was holding one.
        """
        if not self._provider.session_param:
            raise ParamError(
                f"{self._provider.label} declares no session parameter, so "
                f"{session_id!r} cannot be sent and every request will leave "
                f"from whichever exit the gateway picks."
            )
        return self.replace(**{self._provider.session_param: session_id})

    def sessions(self, count: int, *, length: int = 6) -> List["Proxy"]:
        """``count`` identities with the same parameters and distinct session ids.

        The thing everybody writes by hand, and the two details that are easy to
        get wrong when writing it by hand are why it is here.

        The ids are **hexadecimal**, from :mod:`secrets`. Hex because a session id
        must not contain the gateway's separator - a value carrying one is cut and
        every id sharing a prefix collapses onto one exit, measured 2026-08-20 -
        and the alphabets people reach for first do not have that property:
        :func:`secrets.token_urlsafe` emits ``-`` and ``_``, ``uuid4()`` emits
        ``-`` four times, and base64 emits ``+`` and ``/``. Every one of those is
        a separator on some gateway. The constructor would refuse them, loudly,
        which is the safe failure - but only after the caller had written the
        code.

        They come from :mod:`secrets` and not :mod:`random` because
        :func:`random.random` is seeded from the clock and its stream is
        reproducible: two processes started in the same millisecond would get the
        same ids, so two workers meant to hold two exits would share one.

        ``length`` is in bytes, so the default is 12 hex characters and 2**48
        possible ids.

        **This paragraph used to end "so a very short ``length`` costs time and
        not correctness", and that was wrong in two ways.** It was written about
        the rejection loop below, which does guarantee distinctness within one
        call, and it read the guarantee as free.

        The first way is a hang. Rejection sampling cannot produce more distinct
        values than exist, so ``count`` above the size of the space is a loop
        with no exit - measured 2026-09-08 in an external review and reproduced
        here the same day: ``sessions(257, length=1)`` did not return in 4 s,
        while ``sessions(200, length=1)`` built 200 immediately. The loop is not
        slow there, it never finishes, and it does it while holding the CPU. So
        ``count`` is now checked against the space, and the bound is strict:
        asking for the whole space would draw every value that exists and leave
        none for the next caller.

        The second way is not fixed by any check here and is the reason the
        sentence was worth correcting rather than deleting. ``seen`` is local to
        one call, so distinctness holds **inside a call and nowhere else**. Two
        processes drawing 8-bit ids collide with each other about as often as
        they do not, and a collision does not raise - it hands two workers one
        exit and looks like a working program. That is the failure the default
        length is set to make impossible rather than unlikely.
        """
        if count < 1:
            raise ParamError(
                f"sessions({count!r}) asks for no identities. Nothing would be "
                f"returned and the call is a mistake somewhere upstream."
            )
        if length < 1:
            raise ParamError(f"length={length!r} would produce an empty session id.")
        # Compared in bits and not by computing 16**(2*length), which is a
        # bignum for a large `length` in Python and an overflow in three of the
        # four languages this has to hold in. `count.bit_length() > bits` is
        # exactly `count >= 2**bits`, so the whole space is refused along with
        # everything past it - one comparison, same answer everywhere.
        bits = 8 * length
        if count.bit_length() > bits:
            raise ParamError(
                f"sessions({count!r}, length={length!r}) asks for at least the "
                f"whole space: {2 * length} hex characters make 2**{bits} "
                f"distinct ids, and drawing without repeating is what this does. "
                f"Raise length= rather than count=, and note that ids are only "
                f"unique within one call - the space has to be large enough for "
                f"every process that draws from it, not just for this one."
            )

        # Rejection rather than trust. 12 hex characters make a collision within
        # a handful of draws vanishingly unlikely, and "vanishingly unlikely" is
        # the wrong standard here: a collision does not raise, it hands two
        # workers one exit and looks like a working program. Since a duplicate is
        # detectable in one line, it is detected.
        seen = set()
        out: List["Proxy"] = []
        while len(out) < count:
            session_id = secrets.token_hex(length)
            if session_id in seen:
                continue
            seen.add(session_id)
            out.append(self.session(session_id))
        return out

    # -- asking the gateway -------------------------------------------------

    def check(
        self,
        *,
        target: str = DEFAULT_TARGET,
        timeout: float = 15.0,
    ) -> Check:
        """Open one CONNECT with these parameters and report what the gateway said.

        The one method here that touches the network, and it is a deliberate
        exception to "this package opens no socket" rather than a retreat from
        it. That rule is about **transport** - connection pools, timeouts, retry
        semantics, four sets of bugs in four languages - and this is one socket,
        opened when asked, closed before returning, holding no state.

        Returns a :class:`~nodemaven.check.Check`. A refused connection is a
        return value and not an exception, because the status code is the reason
        anyone calls this, and it arrives carrying the provider's own reading of
        that code::

            >>> result = proxy.check()          # doctest: +SKIP
            >>> result.ok, result.status        # doctest: +SKIP
            (False, 407)
            >>> print(result.meaning)           # doctest: +SKIP
            usually NOT your credentials, despite what the status says...

        That last line is the whole point. 407 Proxy Authentication Required is
        what this gateway answers to a bad ``filter`` value and to a bad ``ttl``
        value as well as to a wrong password, measured 2026-08-10, so the status
        alone sends people to re-check credentials that are correct.

        **``ok`` is not "my settings were applied."** It means the gateway
        accepted the request. An unrecognised parameter name is also answered
        with 200 and dropped, which is why this package refuses unknown names
        before sending; ``check()`` cannot recover that for you and does not
        pretend to.

        ``target`` is the host the tunnel is opened to. It is a real third party
        that sees a TCP connection from the exit address - there is no null
        CONNECT - so it is a parameter and not a constant. Nothing is sent
        through the tunnel: the exit address, when it arrives, comes back on the
        CONNECT reply itself, so this costs one handshake and no target traffic.
        """
        return _connect(
            self.server,
            self.username,
            self._password,
            target=target,
            timeout=timeout,
            exit_ip_header=self._provider.exit_ip_header,
            reactions=self._provider.connect_reactions,
        )

    # -- output that is not a credential ------------------------------------

    def __repr__(self) -> str:
        """Never carries the password.

        The default repr of a container calls ``__repr__`` on its elements, and
        tracebacks, ``pytest --showlocals`` and most logging setups print reprs
        of locals. A password in here reaches CI logs and pasted bug reports
        without anyone ever choosing to print it. :meth:`url` is the one place
        the secret appears, and it is named so that it is obvious.
        """
        shown = "".join(f", {k}={v!r}" for k, v in self._params.items())
        return (
            f"Proxy(provider={self._provider.id!r}, server={self.server!r}, "
            f"login={self._login!r}, password={_REDACTED!r}{shown})"
        )


def _validate(provider: Provider, params: Mapping[str, Any]) -> Dict[str, str]:
    """Refuse client-side what the gateway will not report.

    This is not politeness, it is the only check available. The gateway this
    package ships a definition for answers a value it will not take five
    different ways and none of them names the parameter: a bad region gives 406,
    a bad city 500, a bad isp 410, and a bad country, filter, ttl, type or speed
    value gives 407 - which sends you to check credentials that are fine. An
    empty value hangs the connection for about twenty seconds, and an unknown
    parameter name is answered with **200 and the setting silently dropped**.
    That last one is why this function exists: the request succeeds, and nothing
    that comes back can tell you the setting was never applied. See
    ``connect_reactions`` in the gateway definition for the sentence a caller is
    shown next to each code.
    """
    out: Dict[str, str] = {}
    for key, value in params.items():
        if key not in provider.known_params:
            raise ParamError(
                f"{provider.label} does not know the parameter {key!r}: it is "
                f"answered with 200 and dropped, so the connection would succeed "
                f"and your setting would NOT be applied. "
                f"Known: {sorted(provider.known_params)}"
            )
        if isinstance(value, bool):
            value = "true" if value else "false"
        text = "" if value is None else str(value)

        # Fold before every remaining check, so that a refusal quotes the string
        # that would actually have gone on the wire rather than the one that was
        # typed. The folded value is what gets stored, so ``params``,
        # ``username`` and the sticky-session identity all agree - a Proxy that
        # reported ``New York`` while sending ``new_york`` would make two callers
        # with the same visible configuration land on different exits.
        text = provider.normalized(key, text)

        if not text:
            raise ParamError(
                f"empty value for {key!r}: the gateway does not reply to this, "
                f"the connection hangs for about 20 s and then fails. Drop the "
                f"parameter instead of passing an empty value."
            )

        # Whitespace inside a value, for a parameter nothing folds. There is no
        # form of this that can be right: a username is one token on the CONNECT
        # line, so the space either malforms the line or cuts the value short,
        # and ``url()`` would percent-encode it to ``%20`` while a browser driver
        # taking the fields separately would not - three spellings of one value,
        # at most one of which any gateway accepts. Refusing it is loud, and loud
        # beats a connection that succeeds with the setting quietly wrong.
        whitespace = [c for c in text if c in ASCII_WHITESPACE]
        if whitespace:
            raise ParamError(
                f"the value of {key!r} is {text!r} and contains whitespace "
                f"({whitespace[0]!r}), which cannot be sent: a proxy username "
                f"is a single token, so the value would be malformed or cut "
                f"short. {provider.label} folds a space to an underscore for "
                f"{sorted(provider.normalize)} and for nothing else, so pass "
                f"{key!r} without whitespace."
            )

        separators = sorted({provider.separator, provider.pair_separator} - {""})
        bad = sorted({c for c in separators if c in text})
        if bad:
            raise ParamError(
                f"the value of {key!r} is {text!r} and contains {bad}, which "
                f"{provider.label} uses to separate parameters. The username "
                f"would be split into different settings than you asked for. "
                f"Session ids in particular cannot carry a {bad[0]!r} - use "
                f"{text.replace(bad[0], '')!r} or another character."
            )
        allowed = provider.allowed(key)
        if allowed is not None and text not in allowed:
            raise ParamError(
                f"{text!r} is not a value {provider.label} accepts for "
                f"{key!r}. Allowed: {list(allowed)}. This one is worth "
                f"catching here because the gateway answers a bad value for "
                f"some parameters with 407 Proxy Authentication Required, "
                f"which reads as a credentials problem and is not one."
            )
        out[key] = text
    return out
