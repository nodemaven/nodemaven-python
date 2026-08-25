"""A gateway dialect is data, never code.

Every proxy vendor sells the same thing and spells it differently: its own
separators, its own parameter names, its own reaction to a mistake. That
difference is the whole of what a provider is from this package's point of view,
so it is one TOML file rather than one Python module.

The reason is not tidiness. A module invites a single ``if provider == ...``
somewhere nobody reviews, and from then on two gateways are no longer going
through the same code path. A data file cannot branch.

``load()`` reads a definition shipped inside the package. ``load_file()`` reads
one from disk, which is how this SDK talks to a gateway we do not ship a
definition for - your own, or one you wrote yourself - without this package
having to make any claim about it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Tuple

from .errors import ProviderError

if sys.version_info >= (3, 11):  # pragma: no cover - version dependent
    import tomllib
else:  # pragma: no cover - version dependent
    import tomli as tomllib

__all__ = ["Provider", "load", "load_file", "available"]

DEFAULT_PROVIDER = "nodemaven"

_REQUIRED = ("label", "known_params")


@dataclass(frozen=True, eq=False)
class Provider:
    """One gateway's username dialect.

    ``status`` is load-bearing and not documentation. ``measured`` means traffic
    has actually gone through this gateway and the dialect was read off the
    wire. ``documented`` means it was transcribed from a vendor's own
    documentation on ``source_read`` and has never been exercised. The
    distinction matters because a wrong username is invisible: at least one
    gateway answers an unrecognised parameter name with 200 and the setting
    silently dropped, so the connection succeeds on settings that were never
    applied and nothing the gateway replies can tell you.
    """

    id: str
    label: str
    known_params: FrozenSet[str]
    status: str = "documented"
    prefix: str = "{login}"
    separator: str = "-"
    pair_separator: str = "-"
    session_param: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    aliases: Dict[str, str] = field(default_factory=dict)
    values: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    exit_ip_header: Optional[str] = None
    source: str = ""
    source_read: str = ""
    notes: str = ""

    def spell(self, name: str) -> str:
        """The name this gateway uses on the wire for a canonical parameter."""
        return self.aliases.get(name, name)

    def allowed(self, name: str) -> Optional[Tuple[str, ...]]:
        """The legal values for a parameter, or None if they are not known.

        None and an empty tuple are deliberately different answers. None means
        nobody has established what this gateway accepts, so the value is
        passed through unchecked - the caller is no worse off than before.
        Filling this in is a change to a data file and to nothing else, which
        is the entire reason the key exists before there is anything to put in
        it: four language SDKs read this schema, and adding a key to it later
        is four parsers, while adding data to a key they already read is one
        file.
        """
        return self.values.get(name)

    @property
    def is_measured(self) -> bool:
        return self.status == "measured"


def _data_dir() -> Path:
    return Path(__file__).resolve().parent / "data" / "providers"


def available() -> list:
    """Ids of the definitions shipped inside this package."""
    return sorted(p.stem for p in _data_dir().glob("*.toml")
                  if not p.stem.startswith("_"))


def load(provider_id: str = DEFAULT_PROVIDER) -> Provider:
    """A definition shipped with this package."""
    path = _data_dir() / f"{provider_id}.toml"
    if not path.is_file():
        raise ProviderError(
            f"no provider definition {provider_id!r} is shipped here, so no "
            f"username can be built for it. Shipped: {available()}. To use a "
            f"gateway that is not in that list, write a .toml for it and pass "
            f"it to load_file()."
        )
    return load_file(path, provider_id=provider_id)


def load_file(path, provider_id: Optional[str] = None) -> Provider:
    """A definition read from an arbitrary path.

    This is the seam that lets the package address a gateway it ships no
    definition for. Nothing about it is special-cased: a file loaded from disk
    goes through the same validation and the same builder as a shipped one.
    """
    path = Path(path)
    try:
        with path.open("rb") as handle:
            raw: Dict[str, Any] = tomllib.load(handle)
    except OSError as exc:
        raise ProviderError(f"cannot read the provider definition {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ProviderError(f"{path} is not valid TOML: {exc}") from exc

    missing = [key for key in _REQUIRED if key not in raw]
    if missing:
        raise ProviderError(
            f"{path} is missing {missing}, so it does not describe a gateway. "
            f"Without known_params nothing can be validated, and an unknown "
            f"parameter name is the one mistake a gateway does not report."
        )

    known = frozenset(str(name) for name in raw["known_params"])
    aliases = {str(k): str(v) for k, v in (raw.get("aliases") or {}).items()}
    unknown_alias = sorted(set(aliases) - known)
    if unknown_alias:
        raise ProviderError(
            f"{path} aliases {unknown_alias} which are not in known_params, so "
            f"those parameters would be refused before the alias was ever used."
        )

    session_param = raw.get("session_param") or None
    if session_param and session_param not in known:
        raise ProviderError(
            f"{path} declares session_param {session_param!r} which is not in "
            f"known_params, so every sticky session would be refused."
        )

    # Legal values, when anybody has established them. A closed list and
    # nothing else: no regular expressions. A pattern in this file would have
    # to mean the same thing to Python, Go, Rust and JavaScript, and their
    # engines disagree on enough of the syntax that the contract would be
    # about the regex dialect rather than about the gateway. A list of strings
    # is the same in every language there is.
    values: Dict[str, Tuple[str, ...]] = {}
    for name, allowed in (raw.get("values") or {}).items():
        name = str(name)
        if name not in known:
            raise ProviderError(
                f"{path} lists legal values for {name!r}, which is not in "
                f"known_params, so that parameter is refused by name before "
                f"its value is ever looked at."
            )
        if not isinstance(allowed, list) or not allowed:
            raise ProviderError(
                f"{path} gives the legal values of {name!r} as {allowed!r}. It "
                f"has to be a non-empty list of strings. Leave the entry out "
                f"entirely to mean 'nobody has established these' - an empty "
                f"list would mean 'every value is refused', which is not a "
                f"thing anybody wants to say."
            )
        values[name] = tuple(str(item) for item in allowed)

    port = raw.get("port")
    return Provider(
        id=provider_id or path.stem,
        label=str(raw["label"]),
        known_params=known,
        status=str(raw.get("status", "documented")),
        prefix=str(raw.get("prefix", "{login}")),
        separator=str(raw.get("separator", "-")),
        pair_separator=str(raw.get("pair_separator", "-")),
        session_param=session_param,
        host=raw.get("host"),
        port=int(port) if port is not None else None,
        aliases=aliases,
        values=values,
        exit_ip_header=raw.get("exit_ip_header"),
        source=str(raw.get("source", "")),
        source_read=str(raw.get("source_read", "")),
        notes=str(raw.get("notes", "")),
    )
