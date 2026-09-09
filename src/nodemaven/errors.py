"""Errors this package raises.

Every message says what will happen to the caller, not that a value is invalid.
A gateway parameter that is wrong is not a style problem: the request usually
still succeeds, on settings nobody asked for.

The classes here are part of the cross-language contract, not an implementation
detail. A golden vector says which error an invalid input must produce, so the
taxonomy has to keep agreeing across four SDKs even where the shape does not -
Rust has one enum where this has a class tree. The rule used to decide whether
something earns its own class is narrow on purpose: **a caller has to plausibly
write different code for it.** 401 means fix your key, 429 means wait, 404 in a
CRUD call means the row is gone; a 400 means fix your program and there is
nothing to branch on, so it stays on the base class.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "NodeMavenError",
    "ParamError",
    "CredentialsError",
    "ProviderError",
    "ApiError",
    "AuthError",
    "NotFoundError",
    "RateLimitError",
    "CheckError",
]


class NodeMavenError(Exception):
    """Base class, so a caller can catch everything from this package at once."""


class ParamError(NodeMavenError, ValueError):
    """Input the gateway would silently ignore, misreport, or hang on."""


class CredentialsError(NodeMavenError, ValueError):
    """No login or password was given and none was found in the environment."""


class ProviderError(NodeMavenError, ValueError):
    """A provider definition is missing or does not describe a gateway."""


class ApiError(NodeMavenError):
    """The account API answered with an error, or answered something unreadable.

    ``status`` is the HTTP status, or ``None`` when the request never got an
    answer at all. ``body`` is whatever came back, decoded if it was JSON and
    left as text if it was not - an HTML error page from a proxy or a load
    balancer in front of the API is a real answer and throwing it away is how
    "the API is broken" gets reported for a captive portal.

    The API key is **never** in here. It travels in a header and not in the URL
    precisely so that an exception carrying the URL cannot carry the credential,
    and nothing in this module formats it.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class AuthError(ApiError):
    """401 or 403: the API key is missing, wrong, or not allowed to do this.

    Separate from :class:`CredentialsError`, which is about the *proxy* login
    and is raised before anything is sent. This one has been to the server.
    Worth keeping apart in your own code as well: the two credentials are
    different strings from different places, and a program that treats them as
    one will tell you to fix the key when the password is the problem.
    """


class NotFoundError(ApiError):
    """404: the thing addressed does not exist, or never did."""


class RateLimitError(ApiError):
    """429: too many requests.

    ``retry_after`` is the server's own number in seconds when it sent one, and
    ``None`` when it did not. It is exposed rather than slept on, because this
    package does not retry - see the note in ``__init__.py`` for the measurement
    behind that, which is about the proxy pool rather than about this API, and
    for the same reason applies less here. Waiting the number the server gave
    you is not the behaviour that measurement warns about; a loop that ignores
    it is.

    **``nodemaven.api.Client`` never fills it in, so from that client it is
    always ``None``**, said here from 2026-09-09. The reason is structural
    rather than an oversight to be worked around: ``api.Transport`` returns
    ``(status, bytes)`` and discards the response headers, so ``Retry-After``
    is gone before anything could read it. The paragraph above described the
    attribute as though the client populated it, and the 429 message told
    callers to go and read it - an instruction that could not be followed on
    any 429 this package raises. The attribute stays, because it is part of
    this class rather than of that one transport and a caller raising it by
    hand can set it; what was wrong was the promise, not the field.

    Surfacing the header means widening the ``Transport`` return type, which is
    a public protocol implemented in four languages. That is a version's worth
    of change and it is not made here.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        body: Any = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message, status=status, body=body)
        self.retry_after = retry_after


class CheckError(NodeMavenError):
    """:meth:`Proxy.check` could not reach the gateway at all.

    Deliberately not raised for a gateway that answered and refused. A 407 is an
    answer and is reported as one in the returned :class:`~nodemaven.check.Check`,
    because the status code is the diagnostic the caller came for. This error is
    for the cases where nothing came back: DNS, a refused connection, a timeout,
    a truncated status line.
    """
