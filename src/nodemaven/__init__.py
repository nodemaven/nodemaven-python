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
"""

from .errors import (
    CredentialsError,
    NodeMavenError,
    ParamError,
    ProviderError,
)
from .providers import Provider, available, load, load_file
from .proxy import Proxy

__version__ = "0.1.0"

__all__ = [
    "Proxy",
    "Provider",
    "load",
    "load_file",
    "available",
    "NodeMavenError",
    "ParamError",
    "CredentialsError",
    "ProviderError",
    "__version__",
]
