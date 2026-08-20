"""Errors this package raises.

Every message says what will happen to the caller, not that a value is invalid.
A gateway parameter that is wrong is not a style problem: the request usually
still succeeds, on settings nobody asked for.
"""

from __future__ import annotations

__all__ = ["NodeMavenError", "ParamError", "CredentialsError", "ProviderError"]


class NodeMavenError(Exception):
    """Base class, so a caller can catch everything from this package at once."""


class ParamError(NodeMavenError, ValueError):
    """Input the gateway would silently ignore, misreport, or hang on."""


class CredentialsError(NodeMavenError, ValueError):
    """No login or password was given and none was found in the environment."""


class ProviderError(NodeMavenError, ValueError):
    """A provider definition is missing or does not describe a gateway."""
