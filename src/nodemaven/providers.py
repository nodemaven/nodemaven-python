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

from .check import _port_number
from .errors import ProviderError

if sys.version_info >= (3, 11):  # pragma: no cover - version dependent
    import tomllib
else:  # pragma: no cover - version dependent
    import tomli as tomllib

__all__ = ["Provider", "load", "load_file", "available", "ASCII_WHITESPACE"]

DEFAULT_PROVIDER = "nodemaven"

_REQUIRED = ("label", "known_params")

#: The six characters treated as whitespace in a parameter value.
#:
#: Spelled out rather than delegated to ``str.isspace`` or ``str.strip()`` with
#: no argument, because neither means the same thing in four languages:
#: ``str.isspace`` is Unicode-wide and also true of a no-break space, while
#: Rust's ``is_ascii_whitespace`` excludes the vertical tab that Python's
#: includes. A value carrying any of these is refused, so the set is part of the
#: cross-language contract and has to be a list somebody can copy.
ASCII_WHITESPACE = " \t\n\r\v\f"

# ASCII case folding and nothing wider. ``str.lower()`` is Unicode-aware, so it
# maps characters like the Turkish dotted capital I in a way Rust and Go do not
# reproduce, and a golden vector that depended on it would fail in one SDK for
# reasons that have nothing to do with proxies.
_ASCII_LOWER = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz",
)


def _fold(value: str) -> str:
    """A value in its wire form: strip, ASCII lower-case, spaces to ``_``.

    Module-level from 2026-09-09 so that ``load_file`` folds a configured
    ``values`` list through the same three steps ``Provider.normalized`` folds a
    caller's input through. It was inline in that method, and the two sides of
    the comparison were therefore folded by one implementation and none: a
    definition that both normalized ``region`` and listed
    ``values.region = ["District of Columbia"]`` refused ``District of
    Columbia``, because the input arrived at the check as
    ``district_of_columbia`` and the legal list had never been touched.
    """
    return value.strip(ASCII_WHITESPACE).translate(_ASCII_LOWER).replace(" ", "_")


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
    normalize: FrozenSet[str] = frozenset()
    connect_reactions: Dict[str, str] = field(default_factory=dict)
    exit_ip_header: Optional[str] = None
    source: str = ""
    source_read: str = ""
    notes: str = ""

    def spell(self, name: str) -> str:
        """The name this gateway uses on the wire for a canonical parameter."""
        return self.aliases.get(name, name)

    def reaction(self, status: int) -> Optional[str]:
        """What a CONNECT status means **on this gateway**, or None if unrecorded.

        This is dialect and not HTTP. The shipped gateway answers a bad ``filter``
        value with 407 Proxy Authentication Required, which is a lie about the
        cause in the most expensive direction available: it sends the caller to
        check credentials that are correct. A status code alone is therefore not
        a diagnosis here, and the translation is per-gateway, so it lives in the
        TOML beside the separators rather than in a dict in this module.
        """
        return self.connect_reactions.get(str(status))

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

    def normalizes(self, name: str) -> bool:
        """Whether this gateway wants the value of ``name`` folded.

        The parameters that say yes carry a human place name - a region, a city,
        an ISP - and the gateway wants ``district_of_columbia`` where a caller
        naturally writes ``District of Columbia``. See ``normalized()``.
        """
        return name in self.normalize

    def normalized(self, name: str, value: str) -> str:
        """The wire form of a value, or the value unchanged if it is not folded.

        The fold is three steps, in this order, and **it is part of the
        cross-language contract** - a golden vector pins the username a set of
        parameters produces, so four SDKs have to agree on it character for
        character:

        1. strip leading and trailing ``ASCII_WHITESPACE``
        2. lower-case ASCII ``A-Z`` only
        3. replace each space with ``_``

        Which parameters this applies to is declared in the provider TOML, as
        data, for the same reason ``known_params`` is: the public API must never
        name a gateway's parameters in its own code, and the next gateway will
        fold a different set or none at all.
        """
        if name not in self.normalize:
            return value
        return _fold(value)

    @property
    def is_measured(self) -> bool:
        """Whether traffic has actually gone through this gateway.

        False covers both "transcribed from documentation" and any status
        nobody has defined, which is the safe way round: a definition is
        unverified until something says otherwise.
        """
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

    # Which parameters are folded to their wire form before anything else looks
    # at them. One list and one rule, deliberately: the vendor's own client
    # applies two - lower-case for `country` and `type`, lower-case plus
    # space-to-underscore for `region`, `city` and `isp` - and the difference
    # cannot be observed, because a country code and a pool name have no spaces
    # in them to convert. One rule that four languages have to agree on beats
    # two.
    raw_normalize = raw.get("normalize")
    if raw_normalize is not None and not isinstance(raw_normalize, list):
        # `normalize = 1` raised a bare `TypeError: 'int' object is not
        # iterable` until 2026-09-09, and `normalize = "region"` was worse than
        # that: a string iterates into its characters, so it reached the check
        # below and was reported as five unknown parameter names.
        raise ProviderError(
            f"{path} gives normalize as {raw_normalize!r}. It has to be a list "
            f"of parameter names."
        )
    normalize = frozenset(str(name) for name in (raw_normalize or ()))
    unknown_normalize = sorted(normalize - known)
    if unknown_normalize:
        raise ProviderError(
            f"{path} normalizes {unknown_normalize} which are not in "
            f"known_params, so those parameters are refused by name and the "
            f"fold can never run."
        )

    # A legal-values list for a folded parameter is folded too, from 2026-09-09.
    # The caller's value is folded before it is checked, so an unfolded list
    # refuses exactly the values a definition went to the trouble of declaring
    # legal. Doing it here rather than at the comparison keeps one folded form
    # in the object, so the message that lists the legal values quotes what the
    # check actually compared against.
    values = {
        name: tuple(_fold(item) for item in allowed) if name in normalize else allowed
        for name, allowed in values.items()
    }

    # What each CONNECT status means on this gateway. Keys are the status code as
    # a string, because TOML has no integer keys and JSON has none either - and
    # the golden vectors are JSON, so a schema that used integers here would
    # already have to be stringified to be shared.
    #
    # Any status may be described and none has to be: an entry is a sentence a
    # human wrote after watching the gateway do it, so a gateway nobody has
    # probed simply has none and `check()` reports the bare status. There is no
    # validation to do beyond "it is a table of strings" - unlike `values`, an
    # entry here cannot refuse anything, so a wrong one is a misleading sentence
    # and not a blocked request.
    connect_reactions: Dict[str, str] = {}
    raw_reactions = raw.get("connect_reactions")
    if raw_reactions is not None and not isinstance(raw_reactions, dict):
        raise ProviderError(
            f"{path} gives connect_reactions as {raw_reactions!r}; it has to be a table."
        )
    for status, meaning in (raw_reactions or {}).items():
        if not isinstance(meaning, str) or not meaning:
            raise ProviderError(
                f"{path} describes CONNECT status {status!r} as {meaning!r}. It has "
                f"to be a non-empty string: this text is shown to a caller as the "
                f"reason their connection was refused."
            )
        connect_reactions[str(status)] = meaning

    separator = str(raw.get("separator", "-"))
    pair_separator = str(raw.get("pair_separator", "-"))

    # A normalized value can never contain the separator, because the fold does
    # not introduce one and a value carrying it is refused either way. But a
    # separator of "_" would make the fold *produce* one - `city="New York"`
    # becoming `new_york` and then being cut in half - so the definition that
    # declares both is refused here rather than at the call site, where the
    # caller would be blamed for input that is correct.
    if normalize:
        for candidate in (separator, pair_separator):
            if candidate == "_":
                raise ProviderError(
                    f"{path} separates parameters with {candidate!r} and also "
                    f"normalizes {sorted(normalize)}, and the fold turns a "
                    f"space into {candidate!r}. A value with a space in it "
                    f"would be cut at the separator the fold had just "
                    f"inserted. Pick one."
                )

    # Through `check._port_number`, the same one `Proxy` uses, and for the same
    # reason a comment in `proxy.py` gives at length: a rule with two
    # implementations is how the two languages here drifted apart once already.
    #
    # This check did not exist until 2026-09-09. It was `int(port)`, which
    # accepts `70000` and `-1` and raises a bare `ValueError` on `"abc"` instead
    # of this module's `ProviderError`. A definition carrying `port = 70000`
    # loaded without complaint and `Proxy` then built `gateway.example:70000`,
    # because the branch taking the provider's port as a fallback was the one
    # branch that skipped the port rule. That branch was corrected the same day;
    # correcting it there alone would have left the wrong layer reporting it -
    # the value comes from this file, so the error has to name this file.
    port = raw.get("port")
    if port is not None:
        checked = _port_number(str(port))
        if checked is None:
            raise ProviderError(
                f"{path} gives port as {port!r}. It has to be a whole number "
                f"from 1 to 65535; 0 means 'any free port' when binding and is "
                f"meaningless when connecting."
            )
        port = checked
    return Provider(
        id=provider_id or path.stem,
        label=str(raw["label"]),
        known_params=known,
        status=str(raw.get("status", "documented")),
        prefix=str(raw.get("prefix", "{login}")),
        separator=separator,
        pair_separator=pair_separator,
        session_param=session_param,
        host=raw.get("host"),
        port=port,
        aliases=aliases,
        values=values,
        normalize=normalize,
        connect_reactions=connect_reactions,
        exit_ip_header=raw.get("exit_ip_header"),
        source=str(raw.get("source", "")),
        source_read=str(raw.get("source_read", "")),
        notes=str(raw.get("notes", "")),
    )
