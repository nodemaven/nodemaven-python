"""One proxy identity, and the strings a client needs to use it.

This module opens no socket. It builds a username in the gateway's dialect,
refuses input the gateway would mishandle, and hands the result to whatever HTTP
client you already have.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote

from .errors import CredentialsError, ParamError
from .providers import Provider, load

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
        self._port = int(raw_port) if raw_port not in (None, "") else self._provider.port

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
    package ships a definition for answers seven kinds of bad input seven
    different ways and none of them names the cause: a bad country or region
    gives 406, a bad city 500, a bad filter or ttl value gives 407 - which sends
    you to check credentials that are fine - an empty value hangs the connection
    for about twenty seconds, and an unknown parameter name is answered with
    **200 and the setting silently dropped**. That last one is why this function
    exists: the request succeeds, and nothing that comes back can tell you the
    setting was never applied.
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
        if value is None or value == "":
            raise ParamError(
                f"empty value for {key!r}: the gateway does not reply to this, "
                f"the connection hangs for about 20 s and then fails. Drop the "
                f"parameter instead of passing an empty value."
            )
        if isinstance(value, bool):
            value = "true" if value else "false"
        text = str(value)
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
