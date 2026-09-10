"""nodemaven - build and validate proxy connection strings.

This package builds the username a proxy gateway expects, refuses the input that
gateway would mishandle, and hands the result to whatever HTTP client you
already use. It opens no socket, holds no session and retries nothing.

    >>> from nodemaven import Proxy
    >>> proxy = Proxy(login="user", password="pass", country="us", filter="medium")
    >>> requests.get("https://api.ipify.org", proxies=proxy.requests())

There is no retry policy here on purpose. Retrying a refused request is the one
thing that reliably makes the next one worse: measured over 1464 attempts, the
chance the next attempt succeeds falls from 75% with no prior failure to 5.8%
after five and 0.5% after seven, and 294 attempts spent past six consecutive
failures returned three pages - 98 attempts per delivered page against 1.7 in a
healthy session. A library that hid that behind a default would be spending a
shared pool's reputation on your behalf.

Two things here do touch the network, and they are the only two. Both are
explicit calls and neither happens on import:

    >>> proxy.check()                 # one CONNECT, and what the gateway said
    >>> Client().me()                 # the account API: quota, usage, sub-users

``Proxy`` itself still opens nothing. Keeping those on separate objects is what
lets the whole string-building half of this package stay testable with no socket
and no account - see ``nodemaven.check`` and ``nodemaven.api``.
"""

from .api import Client, Page
from .check import Check
from .errors import (
    ApiError,
    AuthError,
    CheckError,
    CredentialsError,
    NodeMavenError,
    NotFoundError,
    ParamError,
    ProviderError,
    RateLimitError,
)
from .providers import Provider, available, load, load_file
from .proxy import Proxy

__version__ = "0.1.4"

__all__ = [
    "Proxy",
    "Provider",
    "Client",
    "Page",
    "Check",
    "load",
    "load_file",
    "available",
    "NodeMavenError",
    "ParamError",
    "CredentialsError",
    "ProviderError",
    "ApiError",
    "AuthError",
    "NotFoundError",
    "RateLimitError",
    "CheckError",
    "__version__",
]
