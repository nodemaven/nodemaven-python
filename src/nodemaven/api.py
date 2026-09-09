"""The account API: quota, usage, sub-users, whitelisted addresses, locations.

Separate from :class:`~nodemaven.Proxy` and separately credentialled, because
they are two different products with two different secrets. A proxy login and
an API key are different strings from different places, and a package that
blurred them would tell you to fix the key when the password is wrong.

**Zero required dependencies, on purpose.** The transport is
:mod:`urllib.request` from the standard library. A proxy SDK that pulled in an
HTTP client would be dictating one to a caller who already has one - and these
calls are made once at start-up, so there is nothing here that pays for the
dependency. If you want your own client, pass ``transport=``; the signature is
one function and :class:`Client` never touches a socket itself.

**No async, and that is a decision rather than an omission.** ``users/me`` is
called once per process. Shipping a second code path for it means two sets of
bugs to keep in agreement for a call nobody makes in a loop. When somebody
shows a use that needs it, the transport seam above is already the place it
goes.

Where the paths come from
-------------------------

**The vendor publishes an OpenAPI 3.0.3 document and it is unauthenticated.**
``https://dashboard.nodemaven.com/documentation/v2/``, fetched 2026-09-09,
179194 bytes, sha256 beginning ``cc958d79a68d58d0``, 24 paths. A copy is kept at
``lab/notes/nodemaven_openapi_v2_20260909.json`` so that every claim below has a
fixed thing to be checked against rather than a live URL that moves.

This module's paths were **transcribed from the vendor's Python client** on
2026-09-07 until that fetch, and five of them were wrong. What the mistake
looked like from the inside: the transcription was treated as a reading of the
API because it came from the vendor, and three sweeps of the dashboard's own
JavaScript bundles were then written to discover routes - while
``/documentation`` sat in the sweep's own output, twice, and was probed as if it
were an API resource instead of being opened. The general form is the one this
tree keeps recording: **a source that looks authoritative was allowed to stand
in for a measurement, and then a hard method was chosen over an easy one because
nobody asked what the cheapest check was.**

**The spec is documentation and is wrong in at least two places**, so it is not
promoted to the status the vendor's client wrongly held:

* ``info.description`` says requests go to
  ``https://api.nodemaven.com/v2/base/<tag>/<method_name>``. Measured
  unauthenticated 2026-09-09: that host answers ``users/me`` with **404
  text/html, 146 bytes, from nginx**, byte-identical to a deliberately
  nonexistent path on it, while ``https://dashboard.nodemaven.com/api/v2/base/
  users/me`` answers **403 application/json**,
  ``{"detail":"Authentication credentials were not provided."}``. A 403 is
  routing succeeding and authentication refusing, so the route is there.
  :data:`DEFAULT_BASE_URL` is right and the spec's description is the defect.
* ``statistics/*`` document their dates as ``"dd-mm-yyyy"`` in prose while
  typing them ``format: date``, which is ``yyyy-mm-dd``. **The machine-readable
  half is the wrong half**, measured 2026-09-09 by ``--phase 10``:
  ``start=20-08-2026`` answers **200 with 21 data points**, ``start=2026-08-20``
  answers **400**, and the body of that 400 is byte-identical to the body for
  ``start=not-a-date``. So ``format: date`` is not a second spelling the server
  declines - it is a string the server cannot parse at all, and every client
  generated from this document sends the one form that fails.

  This line said "unresolved; nothing here validates a date, so nothing here
  depends on the answer" until that run. The second half was true and the first
  was a reason not to look. What it cost is small here and would not be small in
  a generated client: this module passes a date through untouched, so a caller
  who reads the spec rather than this file writes the ISO form and gets a 400
  whose body says nothing about which of its three arguments was refused.

And in one place the spec disagrees with a live run, which the run wins: the
location schemas name a field ``effective_availability``, and the 2026-09-08
run read ``availability`` off ``regions`` and ``cities``. Nothing in this module
reads either.

What was measured, and when
---------------------------

Sent to the live API on **2026-09-08** by ``lab/probes/probe_account_api.py``,
from a connection that does not route through this tree's VPN gateway:
``users/me``, ``locations/countries``, ``.../regions``, ``.../cities`` and
``.../isps``.

Sent on **2026-09-09**, same probe, phase 4: the five paths this module had
never called. **Four of the five did not exist.**

* ``locations/zip-codes/``, ``statistics/`` and ``whitelist-ips/`` answered
  **200, text/html, 6415 bytes, byte-identical to a deliberately nonexistent
  path**. Those three paths were inventions. The real ones are
  ``locations/zipcodes/`` - solid, no separator - ``statistics/data/``,
  ``statistics/requests/``, ``statistics/domains/``, and ``whitelist/ips``.
* ``statistics/domains/`` is real and answered 404 JSON for a missing argument.
* ``sub-users/`` is real and answers an **envelope** -
  ``{success, description, errors, payload}`` - with no ``count`` and no
  ``next``, so the ``rows_key="results"`` this module used could not read it and
  :meth:`Client.iterate` could not walk it. That envelope is the spec's declared
  200 schema and not a server defect, which is how it was first written down
  here.

**That host answers an unregistered dashboard path with 200 and the front
end's HTML.** So *calling a path cannot tell you whether the path exists*, and
every probe against it compares a digest against a negative control. This is the
same defect as the gateway answering 200 to an unknown username parameter and
dropping it, which is what put ``norotate`` in this package.

What is still not measured
--------------------------

* **The six write endpoints have never been called** - creating, updating,
  deleting and resetting a sub-user, upserting a whitelist address, deleting
  one - because each costs a real object on a production account. Their paths,
  methods and body fields are the spec's, cross-checked against nothing.
* **The page-number base.** ``sub-users/`` and ``whitelist/ips`` page by page
  number rather than by row offset, and neither the spec nor any run says
  whether the first page is 0 or 1. This module refuses to guess - see
  :class:`Paging` and :meth:`Client.iterate`.

Twenty-four paths are in the spec and this module wraps nineteen of them. Not
wrapped, deliberately: ``locations/all-doc/``, ``notifications/``,
``llm/submit/``, ``llm/results/{id}/`` and ``llm/balance/``. The first is a
documentation dump, the second is dashboard furniture, and the last three are a
different product that happens to share a host. Listed rather than left out
silently, so the omission is a decision somebody can disagree with.
"""

from __future__ import annotations

import functools
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .errors import ApiError, AuthError, CredentialsError, NotFoundError, RateLimitError

__all__ = [
    "Client",
    "Page",
    "Paging",
    "Transport",
    "DEFAULT_BASE_URL",
    "API_ROOT",
    "DEFAULT_PAGE_SIZE",
    "BY_OFFSET",
    "BY_PAGE_NUMBER",
    "WHITELIST_PAGING",
]

#: The dashboard host the API lives on. Overridden by ``NODEMAVEN_BASE_URL``.
#:
#: **Not ``api.nodemaven.com``**, which the vendor's own OpenAPI description
#: names. Measured 2026-09-09: that host 404s ``users/me`` from nginx with the
#: same 146 bytes it gives a nonexistent path, and this one answers 403 JSON.
#: See the module docstring.
DEFAULT_BASE_URL = "https://dashboard.nodemaven.com"

#: Every path below hangs off this. Kept as one constant so a version bump is
#: one edit rather than nineteen.
API_ROOT = "/api/v2/base"

#: Rows asked for per request on the ``limit``/``offset`` endpoints.
#:
#: It is sent rather than left to the server for two measured reasons, both
#: 2026-09-08. ``locations/isps`` **refuses** a request without ``limit`` and
#: ``offset`` - ``{'limit': 'This field is required.'}`` - and the spec marks
#: both required on that path alone, so omitting them is not a working default,
#: it is a broken endpoint. And the three location endpoints that do answer
#: without them returned exactly 50 rows and reported no total, which is a page
#: presented as if it were the whole collection.
#:
#: **1000 rather than 50, and the number is the largest one measured accepted by
#: all four endpoints.** ``limit=1000`` answers 200 everywhere; ``limit=10000``
#: is refused with 400 by ``isps``, and on ``cities`` it returns exactly the
#: same 1000 rows that ``limit=1000`` does.
#:
#: **1000 is a hard server ceiling on ``limit``, and it truncates ``cities``.**
#: ``limit=1000&offset=1000`` returns a further 965 rows, so the US city
#: collection is 1965 and a single default call sees the first 1000 of them with
#: nothing in the answer saying so. Raising the default from 50 did not remove
#: that failure, it moved it one order of magnitude further out.
#: :meth:`Client.iterate` is the only call that returns all 1965; a bare
#: ``cities()`` is a page and has to be read as one.
#:
#: This comment claimed the ceiling, then withdrew it, then measured it. The
#: withdrawal was right: arms C and D both asked for more than they got, so a
#: ceiling at 1000 and a 1000-row collection looked identical, and the sentence
#: was resting on a reading the data could not carry. **Being right by luck is
#: not the same as being justified** - the claim came back only because arm H
#: was run, and it is the arm, not the guess, that it now rests on.
#:
#: The value was 50 for one day, taken from the size the server chose for
#: itself. At 1000 the whole country catalogue (194 rows on 2026-09-08) and a
#: country's regions (51) arrive in one request instead of four and two.
#: ``cities`` does not fit and needs :meth:`Client.iterate`. Pass ``limit=`` to
#: override it.
DEFAULT_PAGE_SIZE = 1000

#: What a transport has to be: ``(method, url, headers, body) -> (status, bytes)``.
#:
#: Note that it returns the status rather than raising on it. Error mapping is
#: this module's job, so a caller who plugs in ``requests`` does not have to
#: reproduce it - and, more to the point, so that a caller who plugs in something
#: that raises on 4xx does not turn a :class:`~nodemaven.errors.NotFoundError`
#: into their own library's exception halfway up the stack.
#:
#: There is no ``timeout`` in the signature. The default transport gets the
#: client's timeout bound into it at construction, and a caller who supplies
#: their own transport already has a timeout configured on whatever client they
#: built it from - passing ours in as well would give them two, of which only one
#: would take effect, and nothing in the signature would say which.
Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Tuple[int, bytes]]

_REDACTED = "***"
_USER_AGENT = "nodemaven-python"


@dataclass(frozen=True)
class Paging:
    """How one endpoint numbers its pages.

    **This API uses three conventions and they are not interchangeable**, read
    off the spec on 2026-09-09: ``limit``/``offset`` on the nine location
    endpoints, ``page``/``per_page`` on ``sub-users/``, and ``page``/
    ``page_size`` on ``whitelist/ips``. A single hard-coded pair would silently
    do nothing on two thirds of the surface, because an unknown query parameter
    is ignored by every REST framework there is - the caller would get page one
    back forever and no error.

    ``first_cursor`` is the number the first page carries. ``limit``/``offset``
    has an unambiguous origin at 0; a page *number* can start at 0 or at 1 with
    nothing in the response telling you which, and the two readings are not
    symmetric, because guessing 1 against a 0-based server drops the first page
    in silence.

    **Both page-number endpoints are 1-based, measured 2026-09-09** by
    ``lab/probes/probe_account_api.py --phase 9``, asking each for pages 0, 1, 2
    and 9999 at a size of one row. On ``sub-users/`` the evidence is where the
    rows are: page 0 came back with **none** and page 1 with the account's single
    sub-user, which a 0-based server cannot produce. On ``whitelist/ips`` the
    collection is empty, so the reading is the weaker one - page 1 is the only
    number answered ``200`` at all, while 0, 2 and 9999 are answered ``404``, and
    a 0-based server would have answered page 0.

    This field was ``None`` on both until that run, and :meth:`Client.iterate`
    refused to walk them rather than guess. The refusal was right for the day it
    shipped and it is the measurement that retires it, not a second opinion about
    what servers usually do.

    ``default_size`` is ``None`` where no size has been measured as safe to
    send. It is set on ``whitelist/ips`` because the spec states the numbers
    outright - default 5, maximum 100 - and a default of 5 is a truncation
    nobody would notice.

    ``ends_with_not_found`` says the server marks the end of this collection by
    refusing the page rather than answering it empty. **The two endpoints that
    number their pages do not agree**, measured in the same run on 2026-09-09:
    ``sub-users/`` answers ``200`` with an empty payload past the end, and
    ``whitelist/ips`` answers ``404``. So one rule cannot cover both, and
    :meth:`Client.iterate` treats a ``404`` as the end only where this is set -
    everywhere else a ``404`` stays an error, because it is also what a wrong
    path looks like.

    The measured half is that ``whitelist/ips`` answers ``404`` for pages 0, 2
    and 9999 while page 1 is answered ``200``. That the same holds *after a full
    page of rows* is an inference: the account holds no whitelist entries, so
    nothing here has ever seen this endpoint end anywhere but at page 1. Put one
    address on the account and it becomes a measurement.
    """

    size_key: str
    cursor_key: str
    cursor_counts_rows: bool
    default_size: Optional[int] = None
    first_cursor: Optional[int] = None
    ends_with_not_found: bool = False


#: The nine ``locations/*`` endpoints, and the only convention with a measured
#: origin: ``offset=0`` is the start of the collection by definition.
BY_OFFSET = Paging(
    size_key="limit",
    cursor_key="offset",
    cursor_counts_rows=True,
    default_size=DEFAULT_PAGE_SIZE,
    first_cursor=0,
)

#: ``sub-users/``. No size is sent: the spec gives ``per_page`` no default and
#: no maximum, so any number here would be this package inventing a limit and
#: then reading the server's refusal of it as an empty account.
BY_PAGE_NUMBER = Paging(
    size_key="per_page",
    cursor_key="page",
    cursor_counts_rows=False,
    first_cursor=1,
)

#: ``whitelist/ips``. ``page_size`` is sent at the spec's stated maximum,
#: because its stated default is **5** and five addresses arriving where the
#: account has forty is the failure this module exists to avoid.
WHITELIST_PAGING = Paging(
    size_key="page_size",
    cursor_key="page",
    cursor_counts_rows=False,
    default_size=100,
    first_cursor=1,
    ends_with_not_found=True,
)


@dataclass(frozen=True)
class Page:
    """One page of a list endpoint.

    Iterating a ``Page`` iterates its ``results``, so the common case reads as
    ``for country in client.countries():``. **That is one page and not the
    collection** - use :meth:`Client.iterate` for the rest.

    ``count`` is the total the server reports behind all pages, and it is
    ``None`` when the server reported none. **Measured 2026-09-08 and confirmed
    against the spec 2026-09-09: it is always ``None`` here.** Not one of the
    three paging envelopes the spec declares has a ``count`` field -
    ``PaginatedCountryList`` and its siblings are ``{"results": [...]}`` and
    nothing else, and ``SubUserManyResponse`` is ``{success, description,
    errors, payload}``. So ``len(page)`` is the only number there is, and a page
    exactly as long as the size that was asked for is indistinguishable from a
    complete collection by looking at it. That is why :meth:`Client.iterate`
    asks for one more page rather than trusting a missing ``next``.

    ``next`` and ``previous`` are not in any declared schema either and have
    never been seen populated. They are still read, because a server may send
    more than its own document promises and following a link the server wrote is
    better than arithmetic - but nothing here waits for them.

    ``request_path``, ``request_params`` and ``paging`` record the call this page
    came from, so ``iterate`` can advance the cursor on a server that sends no
    ``next`` url. They are ``None`` on a page that was built from following one.

    ``rows_key`` is the field the rows came out of. **Six** values are in use:
    ``results`` on the paginated catalogue and the whitelist, ``isps`` on
    ``locations/isps/``, ``regions`` on the two ``*/regions/`` groupings,
    ``cities`` on the two ``*/cities/`` groupings, ``payload`` on ``sub-users/``
    and ``data`` on ``statistics/domains/``. It is recorded rather than
    re-derived so ``iterate`` reads the second page the same way it read the
    first.

    All six were measured against the server on 2026-09-09 and every one of them
    named a populated list: ``isps`` 359 rows, ``regions`` 51, ``cities`` 1000,
    ``results`` 1000 on ``locations/zipcodes/`` and 17 and 805 on its two
    groupings, ``payload`` 1 on ``sub-users/``. Only ``isps`` had been measured
    before that, on 2026-09-08; the rest were read off the spec's own response
    schemas. ``data`` on ``statistics/domains/`` is still schema-only, because
    that endpoint needs a ``proxy_username`` and a date window to answer at all.

    A wrong value here yields an empty page rather than raising, so that is the
    failure mode to expect if a grouping endpoint reports no rows on an account
    that has them.
    """

    results: List[Any]
    count: Optional[int] = None
    next: Optional[str] = None
    previous: Optional[str] = None
    request_path: Optional[str] = None
    request_params: Optional[Dict[str, Any]] = None
    rows_key: str = "results"
    paging: Optional[Paging] = None

    def __iter__(self) -> Iterator[Any]:
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


class Client:
    """Talks to the account API. One instance, one API key.

    ::

        from nodemaven import Client

        client = Client()                      # NODEMAVEN_APIKEY from the environment
        me = client.me()
        print(me["data"])                      # traffic left, measured 2026-09-08

    The key falls back to ``NODEMAVEN_APIKEY`` and the base url to
    ``NODEMAVEN_BASE_URL``. Both names are the vendor's own, so a ``.env`` written
    for their client works here unchanged - which is worth more than a name of
    our choosing, because the alternative is a developer with two ``.env`` files
    that disagree.
    """

    __slots__ = ("_key", "_base", "_timeout", "_transport")

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        transport: Optional[Transport] = None,
    ) -> None:
        self._key = api_key if api_key is not None else os.environ.get("NODEMAVEN_APIKEY")
        if not self._key:
            raise CredentialsError(
                "no API key: pass api_key= to Client() or set NODEMAVEN_APIKEY in "
                "the environment. This is the dashboard API key and not the proxy "
                "password - they are different secrets and the API will answer 401 "
                "to the wrong one."
            )
        base = base_url if base_url is not None else os.environ.get("NODEMAVEN_BASE_URL")
        self._base = (base or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        # The timeout is bound here rather than passed per call, so that
        # `Transport` stays a four-argument function - see the note on it above.
        # `timeout=` therefore applies to the default transport only, and a
        # caller who passes their own owns theirs.
        self._transport: Transport = (
            transport
            if transport is not None
            else functools.partial(_urllib_transport, timeout=timeout)
        )

    def __repr__(self) -> str:
        """Never carries the key. Same reasoning as ``Proxy.__repr__``.

        An API key in a repr reaches CI logs and pasted bug reports without
        anyone choosing to print it, because tracebacks and ``pytest
        --showlocals`` print reprs of locals.
        """
        return f"Client(base_url={self._base!r}, api_key={_REDACTED!r})"

    # -- the account --------------------------------------------------------

    def me(self) -> Dict[str, Any]:
        """The account: traffic left, subscription, and the proxy credentials.

        Returns the server's own object, unmodelled. The six fields it answered
        with on 2026-09-08, all six of them also the spec's required list for
        ``UsersRetrieveResponse``:

        ============================ ========================================
        field                        what came back
        ============================ ========================================
        ``data``                     ``int``. Traffic left. Not ``traffic_left``
        ``email``                    ``str``
        ``is_traffic_frozen``        ``str``, **not a bool** - see below
        ``proxy_password``           ``str``. The proxy password, not the key
        ``proxy_username``           ``str``
        ``subscription_status``      ``str``
        ============================ ========================================

        **``is_traffic_frozen`` is a string.** So ``if me["is_traffic_frozen"]:``
        is true whichever way it reads, and a caller who treats it as a flag
        gets a branch that never takes its other arm. Compare it against the
        value, not for truth. This was written down here as a server defect on
        2026-09-08; the spec types it ``string`` on purpose, so it is a design
        decision to work around rather than a bug to report.

        **Deliberately not parsed into a dataclass**, and this response is the
        argument for that rather than against it. A dataclass is a claim about
        field names and types, and written a day earlier from the vendor's
        client it would have declared ``traffic_left``, which does not exist,
        and typed ``is_traffic_frozen`` as ``bool``, which it is not. The raw
        dict was wrong about nothing, because it claimed nothing.

        **This response carries the proxy password in clear text.** Do not log
        it whole. That is not a rule about this method, it is a rule about the
        endpoint - the same field arrives from :meth:`sub_users` for every
        sub-user on the account.
        """
        return self._get(f"{API_ROOT}/users/me")

    # -- where you can exit from --------------------------------------------
    #
    # The catalogue. Two things it is for, and the second is the interesting one.
    #
    # It answers "what can I ask for", which is otherwise guesswork: a bad
    # `country` is answered 407, a bad `region` 406, any `city` 500 and a bad
    # `isp` 410, and not one of them names the parameter that was wrong. And it
    # is the data that would fill the `values` table in the
    # provider TOML, which ships empty because "the data to fill it with does not
    # exist here" - true of this tree and not true of the product.
    #
    # The `city` row is the one this catalogue changed the reading of. Measured
    # 2026-09-08: `cities()` returns real codes in the gateway's own wire form -
    # `alexander_city`, `altamonte_springs` - so the 500 that every city value
    # drew is not a spelling problem, which was one of the two live readings
    # until then. What it is instead - the account, the pool, or the gateway -
    # is not established, and the codes to settle it are now in hand.
    #
    # Also measured that day, and it constrains what a city check could look
    # like: **city codes repeat across regions.** `aberdeen`, `albany` and
    # `alexandria` each appeared twice in one 50-row page. So a city identifies
    # a place only together with its region, and any future `validate()` city
    # check has to match the triple rather than the code.
    #
    # It is deliberately **not** frozen into that TOML. A snapshot of a live
    # catalogue is a false refusal waiting for the day a country is added: the
    # SDK would reject a place the gateway serves, loudly, with our name on the
    # error. `validate()` below checks against the catalogue as it is now
    # instead, which cannot go stale and cannot ship a refusal.
    #
    # `country__code` is marked required by the spec on every one of these
    # except `countries`. It is not enforced here: the server answers a missing
    # one with a 400 naming the field, which is a better message than any this
    # package would write, and a client-side copy of a server-side rule is a
    # second thing to keep in agreement.

    def countries(self, **filters: Any) -> Page:
        """Countries available for proxy connections.

        ``connection_type`` defaults to ``residential`` **on the server**, not
        here, so pass ``connection_type="mobile"`` to see the mobile pool. That
        default is the vendor client's and is repeated by every method below;
        this package does not add one of its own, because a default sent is a
        default that shows up in a support ticket as something the caller chose.
        """
        return self._list(f"{API_ROOT}/locations/countries/", filters)

    def regions(self, **filters: Any) -> Page:
        """Regions. Filter with ``country__code="us"`` - two underscores.

        The double underscore is Django's field-lookup separator and it is the
        server's spelling, not a typo here. It is passed through untranslated:
        renaming it to ``country_code`` would be one alias to maintain, one thing
        for the docs to disagree about, and one more place a caller's filter can
        be dropped silently, because an unknown query parameter is ignored by
        every REST framework there is.
        """
        return self._list(f"{API_ROOT}/locations/regions/", filters)

    def cities(self, **filters: Any) -> Page:
        """Cities. Filter with ``country__code`` and ``region__code``.

        **This is the one list endpoint a single call does not finish.** The
        server ceiling on ``limit`` is 1000 and ``country__code="us"`` has 1965
        rows, measured 2026-09-08, so a bare call here returns a page that looks
        exactly like a complete answer and is not one. Use
        :meth:`iterate` when you want the collection.
        """
        return self._list(f"{API_ROOT}/locations/cities/", filters)

    def isps(self, **filters: Any) -> Page:
        """ISPs. Filter with ``country__code``, ``region__code``, ``city__code``.

        **This endpoint uses a different envelope from the others and the rows
        are under ``isps``.** Measured 2026-09-08 with ``country__code="us"``:
        the 200 is an object keyed ``city``, ``country``, ``isps`` and
        ``region``, with no ``results`` at all, and ``isps`` is a list - 50 rows
        at ``limit=50``, 358 at ``limit=1000``, 0 at an offset past the end. The
        spec declares exactly that as ``LocationsISPsResponse``, with the other
        three fields typed ``string``: they are the query echoed back, not rows,
        and this method does not return them.

        For a day this method was broken, returning a :class:`Page` of exactly
        one row - the envelope itself - whatever the account held. No release
        carried it. It was documented rather than fixed on purpose, because the
        first probe printed the key *names* and not the values, and unwrapping a
        key because its name looks right is the move that put ``norotate`` in
        this package and ``traffic_left`` in its README. The fix waited for one
        command. That is the whole difference between this and those two: the
        same edit, made after the measurement instead of before it.
        """
        return self._list(f"{API_ROOT}/locations/isps/", filters, rows_key="isps")

    def isp_regions(self, **filters: Any) -> Page:
        """Regions that have ISPs, grouped. Needs ``country__code``.

        Rows are under ``regions`` and each carries its own ISP list. Spec
        shape, never called.
        """
        return self._list(
            f"{API_ROOT}/locations/isps/regions/", filters, rows_key="regions"
        )

    def isp_cities(self, **filters: Any) -> Page:
        """Cities that have ISPs, grouped. Needs ``country__code``.

        Rows are under ``cities``. Spec shape, never called.
        """
        return self._list(
            f"{API_ROOT}/locations/isps/cities/", filters, rows_key="cities"
        )

    def zip_codes(self, **filters: Any) -> Page:
        """ZIP codes. Needs ``country__code``.

        **The path is ``locations/zipcodes/``, solid and with no separator.**
        This method sent ``locations/zip-codes/`` until 2026-09-09, transcribed
        from the vendor's client, and that path does not exist: it answered 200
        with 6415 bytes of the dashboard's HTML, byte-identical to a path nobody
        ever registered. There is no naming rule to extrapolate from on this
        API - ``sub-users`` is hyphenated, ``zipcodes`` is not, ``users/me``
        carries no trailing slash where everything around it does - so a
        spelling that was not read off the spec or a run is a lottery ticket.

        Note what this is **not**: ``zip_code`` is not in any ``known_params``
        list in this package, so the gateway may or may not accept it as a
        targeting parameter. The catalogue existing says the product knows about
        ZIP codes; it does not say the proxy username carries them. That is a
        name to probe and not a name to add.
        """
        return self._list(f"{API_ROOT}/locations/zipcodes/", filters)

    def zip_code_regions(self, **filters: Any) -> Page:
        """Regions that have ZIP codes, grouped. Needs ``country__code``.

        Rows are under ``regions``. Spec shape, never called.
        """
        return self._list(
            f"{API_ROOT}/locations/zipcodes/regions/", filters, rows_key="regions"
        )

    def zip_code_cities(self, **filters: Any) -> Page:
        """Cities that have ZIP codes, grouped. Needs ``country__code``.

        Rows are under ``cities``. Spec shape, never called.
        """
        return self._list(
            f"{API_ROOT}/locations/zipcodes/cities/", filters, rows_key="cities"
        )

    # -- what you used ------------------------------------------------------
    #
    # Three endpoints, not one. This module had a single `statistics()` on
    # `/statistics/`, transcribed, and that path does not exist - it answered
    # 200 with the dashboard's HTML on 2026-09-09, the same 6415 bytes a
    # nonexistent path gets.
    #
    # All three require `proxy_username`, which is why it is a positional
    # argument here rather than one more entry in `**filters`: it is the
    # difference between a 400 at run time and a TypeError at the call site.
    # The value is the sub-user's proxy login - `me()["proxy_username"]` for the
    # account's own.
    #
    # The shared optional filters, from the spec: `timezone` (default "UTC"),
    # `start` and `end` dates, `period` in {"today", "hours24"} and
    # `request_source` in {"proxy", "browser"}.
    #
    # **Dates are `dd-mm-yyyy`**, measured 2026-09-09 by `--phase 10`:
    # `start=20-08-2026` answers 200 with 21 data points, `start=2026-08-20`
    # answers 400, and that 400's body is byte-identical to the one for
    # `start=not-a-date`. The spec writes it both ways - "dd-mm-yyyy" in prose
    # against `format: date` in the type - and the typed half is the wrong half,
    # so anything generated from the document sends the form that fails.
    #
    # Nothing here validates or reformats a date, and that is deliberate rather
    # than unfinished: the server checks them anyway, this module cannot tell a
    # naive `date` from a string, and a client-side reformat would have to guess
    # a caller's intent for `01-02-2026`. What the measurement buys is the
    # docstrings below saying which form to write.
    #
    # All three answer **500**, not 400, when `start`, `end` and `period` are all
    # omitted, though the document marks all three optional. So there is no
    # "just give me everything" call here; send a `period` or a date range.

    def statistics_data(self, proxy_username: str, **filters: Any) -> Dict[str, Any]:
        """Traffic over time. Returns ``{"labels": [...], "data": [...]}``.

        Two parallel arrays rather than a list of points, so ``labels[i]`` names
        ``data[i]``. Not zipped here: the caller who wants a chart wants the
        arrays, and the caller who wants pairs writes one ``zip``.

        Dates are ``dd-mm-yyyy`` and **not** ISO - ``start="20-08-2026"``, not
        ``"2026-08-20"``, which is answered 400. Send a ``period`` or a range;
        omitting ``start``, ``end`` and ``period`` together answers 500. Both
        measured 2026-09-09, see the comment above this block.
        """
        return self._get(
            f"{API_ROOT}/statistics/data/",
            dict(filters, proxy_username=proxy_username),
        )

    def statistics_requests(self, proxy_username: str, **filters: Any) -> Dict[str, Any]:
        """Request counts over time. Same two-array shape as
        :meth:`statistics_data`, and the same filters: ``start`` and ``end`` in
        ``dd-mm-yyyy``, or a ``period``, and a 500 if all three are missing."""
        return self._get(
            f"{API_ROOT}/statistics/requests/",
            dict(filters, proxy_username=proxy_username),
        )

    def domain_statistics(self, proxy_username: str, **filters: Any) -> Page:
        """Usage split by target domain. Rows carry ``domain_name``,
        ``requests`` and ``data``.

        **Not paginated**, whatever its previous docstring here said. The
        response is ``{"data": [...]}`` with no cursor of any kind, and ``limit``
        is a top-N cut rather than a page size - there is no ``offset`` in the
        spec's parameter list. So the :class:`Page` this returns carries no
        paging convention and :meth:`iterate` over it yields exactly these rows
        and stops. It is a ``Page`` at all only so that iterating the result
        reads the same as iterating the catalogue.

        Send a ``period`` or a ``start``/``end`` range here too: this endpoint
        is in the same 500 as the other two when all three are omitted. The
        warning is repeated on each of the three rather than written once on
        :meth:`statistics_data`, because the README showed
        ``domain_statistics("acct-1")`` bare until 2026-09-09 - the docstring
        carrying it was not the docstring anybody read.
        """
        return self._list(
            f"{API_ROOT}/statistics/domains/",
            dict(filters, proxy_username=proxy_username),
            rows_key="data",
            paging=None,
        )

    # -- sub-users ----------------------------------------------------------
    #
    # How agencies and resellers actually use a proxy account: one plan, many
    # credentials, a traffic cap on each. This is the part of the API with side
    # effects, and the five methods below are the only ones in this package that
    # change anything anywhere. **None of the five has ever been called** - each
    # costs a real object on a production account - so their bodies are the
    # spec's and nothing more.
    #
    # Every one of them answers with the same envelope:
    # `{success, description, errors, payload}`. `payload` is a list on the
    # collection reads and a single object on create and update. It is unwrapped
    # here rather than handed to the caller, because a caller who has to know
    # about `payload` has to know about it at nine call sites.

    def sub_users(self, **filters: Any) -> Page:
        """The sub-users on this account. Pass ``id=`` for one of them.

        **Rows arrive under ``payload``, not ``results``.** Measured 2026-09-09
        and declared by the spec as ``SubUserManyResponse``: the 200 is
        ``{success, description, errors, payload}``, with no ``count`` and no
        ``next``. This module read ``results`` until that run, so this method
        returned an empty page against a populated account and said nothing.

        **Every row carries ``proxy_password`` in clear text.** That is the
        spec's own required field list, not an accident of one account. Anything
        that logs, prints or serialises these rows whole is publishing working
        credentials for every sub-user at once. A probe in this tree did exactly
        that on 2026-09-09 and the account's password had to be rotated.

        Pages by ``page``/``per_page``, from **page 1**, measured 2026-09-09:
        page 0 came back with no rows and page 1 with the account's single
        sub-user. Past the end it answers ``200`` with an empty payload, which is
        what :meth:`iterate` stops on. No ``per_page`` is sent - see
        :class:`Paging`.
        """
        return self._list(
            f"{API_ROOT}/sub-users/",
            filters,
            rows_key="payload",
            paging=BY_PAGE_NUMBER,
        )

    def create_sub_user(
        self,
        proxy_username: str,
        proxy_password: str,
        *,
        traffic_limit: Optional[int] = None,
        is_traffic_limited: Optional[bool] = None,
        **extra: Any,
    ) -> Any:
        """Create a sub-user. Returns the created object.

        The two credentials are positional because there is no sensible default
        for either and a keyword-only signature would let a caller create one
        with an empty password by forgetting an argument.

        **The field names are ``proxy_username`` and ``proxy_password``.** They
        were ``username`` and ``password`` here until 2026-09-09, transcribed;
        the spec marks both of the real names required, so the old body would
        have been refused with a 400 naming two fields that were in fact sent
        under other names - a message that reads as "you forgot these" when what
        happened is "we called them something else".

        ``**extra`` is passed through untouched, which is now a smaller promise
        than it was: the spec's field list is closed at four, so an extra field
        is a bet on the server accepting one it does not document.

        **Sent live 2026-09-09** with the two credentials and nothing else, and
        the two field names are no longer transcription: the server answered
        **201** - not the 200 the rest of this API answers with - and a read-back
        of the collection found the username. The payload carried ``id``,
        ``is_default_user``, ``is_traffic_limited``, ``proxy_password``,
        ``proxy_username`` and ``traffic_limit``, which measures the thing the
        credential rule was written from: **the create response hands back a live
        proxy password**, so its body is a credential and not a receipt.
        """
        body: Dict[str, Any] = {
            "proxy_username": proxy_username,
            "proxy_password": proxy_password,
        }
        if traffic_limit is not None:
            body["traffic_limit"] = traffic_limit
        if is_traffic_limited is not None:
            body["is_traffic_limited"] = is_traffic_limited
        body.update(extra)
        return self._envelope("POST", f"{API_ROOT}/sub-users/", body=body)

    def update_sub_user(self, sub_user_id: Any, **changes: Any) -> Any:
        """Change a sub-user. Returns the updated object.

        **PUT to the collection with the id in the body**, not PATCH to a path
        segment. That is what the spec declares - there is no
        ``sub-users/{id}/`` path at all - and it is what this method sent until
        2026-09-09. The old spelling would have been a 404 or, on a server that
        answers unknown paths with its front end, a 200 carrying HTML.

        The body fields are ``proxy_username``, ``proxy_password``,
        ``is_traffic_limited``, ``traffic_limit``, ``used_traffic`` and
        ``traffic_limit_increment_bytes``. Only ``id`` is required, so this
        behaves like a PATCH despite the verb: unlisted fields are left alone.

        Refuses an empty change set rather than sending a body of nothing but an
        id, which a server can answer 200 to - and a call that reports success
        while changing nothing is the failure mode this whole package is
        organised against.

        **Sent live 2026-09-09** and it is the one write here where the status was
        not the evidence. ``traffic_limit`` was set to 777000111, a number nothing
        else on the account would produce, the server answered 200, and a
        *separate read of the collection* came back with 777000111 in the row. So
        PUT-to-the-collection both is accepted and takes effect. The response
        payload also carries ``used_traffic``, which the create response does not,
        so the two differ in shape and neither is a subset of the row the listing
        returns.
        """
        if not changes:
            raise ApiError(
                f"update_sub_user({sub_user_id!r}) was given nothing to change. "
                f"A body carrying only an id can be answered 200, so this would "
                f"look like it worked and do nothing."
            )
        body = dict(changes)
        body["id"] = sub_user_id
        return self._envelope("PUT", f"{API_ROOT}/sub-users/", body=body)

    def delete_sub_user(self, sub_user_id: Any) -> Any:
        """Delete a sub-user. Irreversible, and nothing here asks twice.

        **The id is a query parameter and not a path segment**, which is the
        spec's shape and was not this module's until 2026-09-09.

        **Sent live 2026-09-09**: 200, with a JSON body where the document
        declares 204. The query-parameter shape is therefore measured rather than
        read off the document, which matters more here than on the other writes -
        a DELETE aimed at a path this host does not serve is answered 200 with
        the dashboard's HTML, so the wrong spelling would have looked exactly
        like a successful delete that left the sub-user in place.

        **The row being gone rests on a later read, not on that run.** This
        docstring said "a read-back of the collection no longer found the
        username" and offered it as the proof; the whitelist delete in the same
        phase produced the identical pair - 200, then a listing that did not show
        the row - and five minutes later the server refused to re-create that
        address as already whitelisted, so the pair had been believed once
        already and had been wrong once already.

        What the mistake looked like from the inside: the read-back *was* the
        control - it is what this file added precisely because a status code is
        not evidence on this host - so once it agreed there was nothing left to
        doubt. The gap is that it runs one second after the write and answers
        "what does the listing say now", while the claim being made is "the
        object no longer exists".

        The second question was asked at 16:15 by
        ``lab/probes/probe_account_api.py --phase 12``, an hour after the write,
        and no ``proxy_username`` on the account begins ``probe_delete_me_``. The
        whitelist half of the same worry then resolved as a stale uniqueness
        check rather than a surviving row - see :meth:`delete_whitelist_ip` - so
        the mechanism that would have hidden a live sub-user from a listing is
        the one that was ruled out. This is still a listing read and not a
        guarantee about storage; it is one taken far enough after the write that
        the failure mode above cannot account for it.
        """
        return self._envelope(
            "DELETE", f"{API_ROOT}/sub-users/", params={"id": sub_user_id}
        )

    def reset_sub_user_usage(self, ids: List[Any]) -> Any:
        """Zero the recorded traffic of one or more sub-users.

        Takes a list because the endpoint does - ``ids`` is the spec's only
        required field and it is an array. A single id still goes in a list, so
        that the one-and-many cases cannot diverge.

        **Sent live 2026-09-09** with one id: 200, and the payload is a **list**
        where every other envelope on this API carries an object. :meth:`_envelope`
        returns it as it comes, so a caller indexing it by key gets a
        ``TypeError`` rather than a ``KeyError``. What that list holds was not
        read - the response body of an endpoint that touches usage records is not
        something to print - so treat the return value as unknown-shaped.
        """
        return self._envelope(
            "POST", f"{API_ROOT}/sub-users/reset/usage", body={"ids": list(ids)}
        )

    # -- authorising by address instead of by password ----------------------

    def whitelist_ips(self, **filters: Any) -> Page:
        """The addresses allowed to use this account without a password.

        **The path is ``whitelist/ips`` with no trailing slash.** This module
        sent ``whitelist-ips/`` until 2026-09-09; that path does not exist and
        answered 200 with 6415 bytes of dashboard HTML, which :func:`_page`
        would have refused as "neither a page nor a list" - the one of the four
        invented paths that would have failed loudly rather than quietly.

        Pages by ``page``/``page_size``, from **page 1**. ``page_size`` is sent
        at 100 because the spec's stated default is **5**.

        **This endpoint ends its collection with a ``404``**, not with an empty
        page, measured 2026-09-09 on an account whose whitelist is empty: page 1
        answers ``200`` with no rows while pages 0, 2 and 9999 answer ``404``.
        :meth:`iterate` therefore treats a ``404`` here - and only here - as the
        end of the walk. See :class:`Paging` for which half of that is measured
        and which is inference.
        """
        return self._list(
            f"{API_ROOT}/whitelist/ips", filters, paging=WHITELIST_PAGING
        )

    def whitelist_ip(self, ip_id: Any) -> Dict[str, Any]:
        """One whitelisted address by id."""
        return self._get(f"{API_ROOT}/whitelist/ip/{_segment(ip_id)}")

    def upsert_whitelist_ip(
        self,
        ip: str,
        ports_count: int,
        *,
        name: Optional[str] = None,
        protocol: str = "HTTP",
        sticky: Optional[bool] = None,
        ttl: Optional[int] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Add or update a whitelisted address. Returns ``{"ip_id", "message"}``.

        **Named for what it does.** It was ``add_whitelist_ip`` posting to
        ``whitelist-ips/`` with a body of ``ip_address`` and ``description``;
        the endpoint is ``whitelist/ip/upsert``, its required fields are ``ip``
        and ``ports_count``, and passing ``id=`` updates an existing row instead
        of adding one. A method called ``add`` that silently updates is a worse
        bug than a wrong path, because the wrong path fails.

        ``ports_count`` has no default here. It is required by the spec and it
        decides how many proxy ports the address gets, which is not a number
        this package can pick on a caller's behalf.

        ``protocol`` is ``HTTP`` or ``SOCKS5`` and is always sent - see below.
        The other documented fields are ``id``, ``type`` (``residential`` or
        ``mobile``), ``quality_filter_enabled``, ``country``, ``region``,
        ``city`` and ``isp``; pass them through ``**extra``.

        **The two fields the spec marks required are not enough**, measured
        2026-09-09: a body of ``ip`` and ``ports_count`` alone is refused ``400``
        with ``{"error": "Please enter a valid protocol(HTTP or SOCKS5)."}``. A
        body carrying every documented field at its documented default is accepted
        ``201``, and a read of ``whitelist/ips`` afterwards found the address. So
        the endpoint works and the document's ``required`` list is short.

        The same run killed the likelier of the two explanations. ``not-an-ip``
        sent as the address drew that message byte for byte, so ``protocol`` is
        validated before ``ip`` is looked at, and "the reserved test address was
        rejected" is dead - the accepted body used ``192.0.2.7``, which makes the
        address positively fine rather than merely unexamined.

        **The missing field is ``protocol``, measured 2026-09-09 at 16:18** by a
        one-field-at-a-time ladder in ``lab\\probes\\probe_account_api.py``. This
        docstring said until then that the accepted body varied six fields at
        once, so which one was short was the server's word rather than a
        measurement; that was right to say and it was one call away from being
        settled. Adding ``protocol: "HTTP"`` and nothing else flipped ``400`` to
        ``201``, ``95`` bytes, and the read-back found the address.

        So the server does not apply the ``default: "HTTP"`` its own document
        declares for that field, and ``protocol`` is sent here on every call
        rather than added to the caller's burden - this default is a client-side
        compensation for a server-side defect, not a convenience.

        What the ladder held fixed: every rung carried ``name``, including the
        one the probe labels "the spec's required pair", which therefore was not
        the pair. Whether ``name`` is also required is untested, and so is
        whether ``ip``, ``ports_count`` and ``protocol`` are a *complete* body.

        **Returns ``{"ip_id": ..., "message": ...}``**, measured in the same run.
        The identifier is ``ip_id`` and not ``id`` as everywhere else here, and
        neither key is in the document: the spec binds both ``200`` and ``201`` on
        this path to ``SuccessResponse``, whose only property is ``message``. Pass
        ``ip_id`` to :meth:`delete_whitelist_ip`.

        Worth knowing what this changes about everything else in this package:
        with an address whitelisted, the gateway accepts requests from it without
        proxy credentials. :class:`~nodemaven.Proxy` still requires a login and
        password to construct, because the username is where every targeting
        parameter travels - the login half is load-bearing even when
        authentication is not.
        """
        body: Dict[str, Any] = {
            "ip": ip,
            "ports_count": ports_count,
            "protocol": protocol,
        }
        if name is not None:
            body["name"] = name
        if sticky is not None:
            body["sticky"] = sticky
        if ttl is not None:
            body["ttl"] = ttl
        body.update(extra)
        return self._get_object(
            "POST", f"{API_ROOT}/whitelist/ip/upsert", body=body
        )

    def delete_whitelist_ip(self, ip_id: Any) -> Any:
        """Remove an address from the whitelist.

        The id is the ``ip_id`` :meth:`upsert_whitelist_ip` returns, or the ``id``
        of a row from :meth:`whitelist_ips` - the create response and the listing
        spell the same identifier differently.

        **Sent live 2026-09-09**: ``200``, ``{"message": ...}``. The document
        declares ``200``, ``404`` and ``500`` here, so this one matches.

        **The delete is real and the uniqueness check lags behind it**, settled
        2026-09-09 at 16:18. Two earlier versions of this paragraph were wrong in
        opposite directions and both are worth keeping.

        The first said "a read of ``whitelist/ips`` afterwards no longer found
        the address", offered as proof the object was gone. At 15:18 the server
        refused to whitelist that same ``192.0.2.7`` with
        ``400 IP is already whitelisted.``, before anything in that run had been
        written - so the delete at 15:13 plus a clean listing one second later
        had proved nothing.

        The second read that refusal as evidence the delete might be soft or
        uncommitted, and named an invisible surviving row as one of two live
        candidates. At 16:18 the same address was accepted ``201``. A row the
        listing cannot see and the uniqueness check can would still have blocked
        it, so that candidate is dead: the object was removed, and what was stale
        is the uniqueness check.

        What is measured about the lag is only its bounds, and they are loose.
        It was still refusing at 5 minutes and was over by 62 minutes; nothing
        here narrows that, because the only two writes against the address were
        an hour apart. The rule for a caller is unchanged by the resolution: a
        ``200`` from here means the row is gone from the listing, and re-adding
        the same address within the hour may still be refused as a duplicate.
        """
        return self._request(
            "DELETE", f"{API_ROOT}/whitelist/ip/{_segment(ip_id)}"
        )

    # -- paging -------------------------------------------------------------

    def iterate(self, page: Page, *, max_pages: int = 100) -> Iterator[Any]:
        """Every item from ``page`` onward, across pages.

        Two ways forward, because this API might use both. A ``next`` url is
        followed when the server sends one. When it does not - and no declared
        schema in the spec has a ``next`` field, so it never does - the walk
        continues by asking the same call again at the next cursor, which is
        ``offset + limit`` on the catalogue and ``page + 1`` on the two
        page-number endpoints.

        **The walk stops on an empty page and not on a short one.** That rule
        changed on 2026-09-09 and the old one was unsafe against this server in
        particular. It used to stop on a page shorter than the size that had
        been asked for, which is wrong wherever the server caps the size below
        the request: ``cities(limit=10000)`` is answered with 1000 rows out of
        1965, and "shorter than asked" reads those 1000 as the end of the
        collection. The measurement that says so was already written in this
        file - ``limit=10000`` returning the same 1000 rows as ``limit=1000`` -
        and the stop rule was never checked against it. **A measurement sitting
        in a docstring is not a measurement anyone applied.**

        Stopping on empty costs one extra request per walk and cannot truncate.

        **The offset advances by the rows returned, not by the limit asked
        for**, corrected 2026-09-09 from the same measurement and some hours
        after it. Advancing by the limit skips whatever the cap withheld:
        ``cities(limit=10000)`` asked for offset 10000 next, which is 8035 rows
        past the end, so the walk collected 1000 rows of 1965 - the exact
        truncation the stop rule above had just been rewritten to prevent, by a
        different route. The suite hid it. ``test_the_capped_page_that_the_old_
        rule_truncated`` counted rows and never read the query string, and the
        fake transport replays its queue whatever the offset says, so it passed
        under both rules; the two tests that did read the offsets asserted the
        wrong ones, one of them in its own name.

        **An empty ``next`` is not read as the end of the collection** either,
        and that is the point of this method rather than a detail of it. A full
        page with no total and no next url is byte-for-byte what a complete
        answer looks like, so treating it as complete is a truncation the caller
        cannot detect.

        The tempting exception is to trust an empty ``next`` when it arrives
        *inside a paging envelope*, on the reasoning that there the server has
        answered the question rather than stayed silent. This method deliberately
        does not, and the reason is now stronger than the measurement it was
        first written from: **no envelope the spec declares has a ``next`` field
        at all**, so a ``None`` there is a key that was never going to be filled.

        That exception was in fact implemented for a few hours on 2026-09-08,
        gated on a ``Page.enveloped`` flag, after a unit test built on a
        hand-written Django REST Framework envelope failed against it. The test
        was pinning an inferred shape, the flag then met the real one, and the
        result would have been every catalogue read stopping after one page.

        **A page-number endpoint is walked from page 1**, measured 2026-09-09 -
        see :class:`Paging`. Until that run this method *refused* to walk
        ``sub-users/`` and ``whitelist/ips`` at all unless the caller named a
        page, because guessing 1 against a 0-based server drops the first page in
        silence and nothing said which this server was. What retired the refusal
        is the measurement and not a second opinion about what servers usually
        do; ``Paging.first_cursor`` carries it and the refusal is gone from the
        code rather than left behind a flag.

        **A ``404`` ends the walk only on ``whitelist/ips``.** The two
        page-number endpoints mark the end differently - ``sub-users/`` with an
        empty page, that one with a refusal - so there is no single rule, and
        treating ``404`` as an ending everywhere would swallow a wrong path. It
        is not ambiguous where it is allowed: the same url answered this walk's
        previous page, so the path exists and only the number changed.

        Three further refusals, none of them tuning knobs:

        * ``max_pages`` bounds the walk. A server returning a ``next`` that
          points at the page you are on turns ``while next:`` into an infinite
          loop of real requests, whose first symptom is a rate limit rather than
          a hang. Reaching the bound raises rather than returning a truncated
          list.
        * A ``next`` already returned is a loop, and raises.
        * A page identical to the one before it means the cursor was accepted
          and ignored, and raises. **Cursor paging is an inference on every
          endpoint here**: ``offset`` was measured honoured on ``countries``,
          ``regions`` and ``cities`` on 2026-09-08 - ``offset=50`` returns rows
          disjoint from ``offset=0`` - and on ``isps`` only the weaker half is
          measured, that an offset past the end returns zero rows. On the two
          page-number endpoints nothing at all is measured. Without this guard,
          a server that ignores the cursor yields the same page a hundred times
          and calls it a collection.

        **A ``next`` pointing at another host is refused rather than followed**,
        in :func:`_is_same_origin`, because the request that follows it carries
        the API key in a header. That guard and the loop guard answer different
        questions and neither covers the other: one is about a server that
        repeats itself, the other about a server - or something answering in its
        place - that sends the reader somewhere else.
        """
        pages = 0
        current: Optional[Page] = page
        seen_urls = set()
        while current is not None:
            for item in current.results:
                yield item

            url = current.next
            step = None if url else _next_step(current)
            if not url and step is None:
                return

            pages += 1
            if pages >= max_pages:
                raise ApiError(
                    f"stopped after {max_pages} pages, which is the bound in "
                    f"iterate(max_pages=). Raise it deliberately if the "
                    f"collection really is this large, rather than letting a "
                    f"paging bug run."
                )

            if url:
                if url in seen_urls:
                    raise ApiError(
                        f"the API returned a next page url it had already "
                        f"returned ({url!r}), so following it is a loop. "
                        f"Stopped after {pages} pages."
                    )
                seen_urls.add(url)
                current = _page(self._request("GET", url), current.rows_key)
                continue

            path, asked = step  # type: ignore[misc]
            try:
                body = self._request("GET", path, params=asked)
            except NotFoundError:
                if not current.paging.ends_with_not_found:  # type: ignore[union-attr]
                    raise
                return
            following = _page(body, current.rows_key)
            if following.results and following.results == current.results:
                cursor = current.paging.cursor_key  # type: ignore[union-attr]
                raise ApiError(
                    f"asking {path} for {cursor}={asked[cursor]} returned the "
                    f"same {len(following.results)} rows as {cursor}="
                    f"{current.request_params[cursor]}, so the server is "  # type: ignore[index]
                    f"accepting `{cursor}` and ignoring it. Every further page "
                    f"would repeat these rows. Ask for the whole collection in "
                    f"one request instead."
                )
            current = replace(
                following,
                request_path=path,
                request_params=asked,
                paging=current.paging,
            )

    # -- checking a Proxy against the live catalogue ------------------------

    def validate(self, proxy: Any) -> List[str]:
        """Check a :class:`~nodemaven.Proxy`'s location against the catalogue.

        Returns a list of complaints, empty if everything resolved. This is the
        gap the ``values`` table in the provider TOML leaves open: the SDK
        refuses a parameter *name* it does not know, and passes any *value*
        through, so ``country="zz"`` builds a username and gets a 407 that reads
        as a credentials problem and does not name the cause.

        It is a method on the client rather than a check inside ``Proxy``, and
        the reason is the one recorded against ``values``: a refusal that ships
        in a release is a refusal that can be wrong forever, and the catalogue
        moves. Asking the live catalogue cannot go stale, and it costs a network
        call, so it has to be the caller's decision to make and not a hidden one.

        Two things are checked today - the country against the catalogue, and
        ``city`` without ``region``, which needs no network at all::

            problems = client.validate(proxy)
            if problems:
                raise SystemExit("\\n".join(problems))

        **``city`` requires ``region``.** Measured 2026-09-08 by
        ``probe_gateway_city_from_catalogue.py``, six CONNECTs holding the login,
        the password, the target, the gateway host and port and the parameter
        order fixed: ``country=us, region=louisiana, city=abbeville`` answers
        200, and the same city with the region removed answers **500**. A second
        city in a second region, ``maryland/aberdeen``, answers 200 as well, so
        it is not one pool. This check is here rather than in ``Proxy`` for the
        reason above - it is a shipped rule that can change, and it can be wrong
        forever if a release refuses on it.

        ``region``, ``city`` and ``isp`` values are still **not** matched against
        the catalogue, and the reason is no longer that the field names are
        unknown. Measured 2026-09-08: ``regions`` answers ``availability, code,
        country, name`` and ``cities`` answers ``availability, code, country,
        name, region``, so a region check is now the same one line the country
        check is. The spec calls that field ``effective_availability`` on all
        three schemas, which is a disagreement nobody has resolved and which
        nothing here depends on.

        What stops the city one is in that field list. City codes repeat across
        regions - ``aberdeen``, ``albany`` and ``alexandria`` each twice in a
        single page - so matching a bare code would pass a city that exists in
        some other state, which is a check that reports success and means
        nothing. It needs the ``region`` field beside it. That the gateway
        resolves a city the same way is now known: an invented name sent with a
        real region answers **406**, the code a bad ``region`` and a bad ``isp``
        also get, so the gateway does look the name up and does distinguish one
        it holds from one it does not.
        """
        problems: List[str] = []
        params = proxy.params
        if params.get("city") and not params.get("region"):
            problems.append(
                f"city={params['city']!r} was sent without a region. The gateway "
                f"answers that with 500 Internal Server Error, which reads as a "
                f"fault on their side and is not one - the same city with its "
                f"own region answers 200. Measured 2026-09-08."
            )
        wanted = params.get("country")
        if not wanted:
            return problems
        page = self.countries(connection_type=params.get("type") or "residential")
        codes = {
            str(item.get("code", "")).lower()
            for item in self.iterate(page)
            if isinstance(item, dict)
        }
        if not codes:
            problems.append(
                "the country catalogue came back with no readable codes, so "
                "nothing was checked. This is a bug here rather than a problem "
                "with your parameters - do not treat it as a pass."
            )
        elif wanted != "any" and wanted.lower() not in codes:
            problems.append(
                f"country={wanted!r} is not in the catalogue for "
                f"connection_type={params.get('type') or 'residential'!r}. The "
                f"gateway answers this with 407 Proxy Authentication Required, "
                f"which reads as a credentials problem and is not one."
            )
        return problems

    # -- transport ----------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._get_object("GET", path, params=params)

    def _get_object(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        answer = self._request(method, path, params=params, body=body)
        if not isinstance(answer, dict):
            raise ApiError(
                f"{method} {path} answered with {type(answer).__name__} where an "
                f"object was expected. The API's shape has changed or something "
                f"other than the API answered.",
                body=answer,
            )
        return answer

    def _envelope(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """One sub-user call, with ``{success, ..., payload}`` unwrapped.

        A 204 arrives as ``{}`` from :func:`_interpret` and is returned as is:
        an empty body carries no envelope to unwrap and no success flag to
        check, and inventing one would be this function claiming to know what
        the server meant.
        """
        answer = self._request(method, path, params=params, body=body)
        if not isinstance(answer, dict) or "payload" not in answer:
            return answer
        if answer.get("success") is False:
            raise ApiError(
                f"{method} {path} answered 2xx with success=false: "
                f"{_detail(answer) or 'no reason given'}. A success flag inside "
                f"a 2xx is the server disagreeing with its own status line, and "
                f"reading the status alone would report this as done.",
                body=answer,
            )
        return answer["payload"]

    def _list(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        rows_key: str = "results",
        paging: Optional[Paging] = BY_OFFSET,
    ) -> Page:
        """One list request, with paging stated rather than left implied.

        The size and the cursor go on every call whose convention has measured
        values for them, and a caller's own values win - so
        ``countries(limit=200)`` is one request for 200 and ``cities(offset=50)``
        starts halfway, both reachable because the names are the server's own.

        ``paging=None`` is for an endpoint that does not page at all; the only
        one is :meth:`domain_statistics`.
        """
        asked = dict(params or {})
        if paging is not None:
            if paging.default_size is not None:
                asked.setdefault(paging.size_key, paging.default_size)
            if paging.first_cursor is not None:
                asked.setdefault(paging.cursor_key, paging.first_cursor)
        page = _page(self._request("GET", path, params=asked), rows_key)
        return replace(
            page, request_path=path, request_params=asked, paging=paging
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if path.startswith("http"):
            # The only caller that passes an absolute url is `iterate`, and the
            # url it passes is one the *server* wrote. The check belongs here
            # rather than there because this is the function that attaches the
            # key: a second caller added later would otherwise reopen the hole.
            if not _is_same_origin(self._base, path):
                raise ApiError(
                    f"refusing to send the API key to {path!r}, which is not "
                    f"{self._base}. This url came back from the API as a paging "
                    f"link, so either the account API is pointing somewhere else "
                    f"or something answered in its place - and the request that "
                    f"would follow it carries your key in a header."
                )
            url = path
        else:
            url = f"{self._base}{path}"
        if params:
            # None means "not set" and is dropped, so `countries(name=None)`
            # sends nothing rather than the string "None" - which a filter would
            # match against zero rows and report as an empty catalogue.
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                joiner = "&" if "?" in url else "?"
                url = f"{url}{joiner}{urllib.parse.urlencode(clean, doseq=True)}"

        headers = {
            # `Authorization: x-api-key <key>` and not an `X-API-Key` header.
            # Unusual, and it is what the server wants: measured 2026-09-08,
            # this form answers 200 where `Bearer` and `Token` answer 403, and
            # the spec's own securityScheme spells it out - an apiKey in the
            # `Authorization` header, "in the following format - 'x-api-key
            # <your-api-key>'". Do not tidy it into the conventional spelling.
            "Authorization": f"x-api-key {self._key}",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        status, raw = self._transport(method, url, headers, payload)
        return _interpret(status, raw, method, url)


def _is_same_origin(base: str, url: str) -> bool:
    """Whether ``url`` goes to the same scheme, host and port as ``base``.

    The rule an API key travels under, and it was missing until 2026-09-08. The
    paging loop followed the ``next`` the server sent, verbatim, and
    :meth:`Client._request` attaches ``Authorization: x-api-key <key>`` to
    whatever it is given: measured that day through the transport seam, a
    ``next`` of ``https://evil.example/api/v2/base/x`` received the key in a
    header. Nothing in the module was wrong about paging - the loop guard and
    the page bound both worked - and the credential still left for a host
    nobody configured.

    Scheme is compared and not just the host, because ``http://`` to the right
    host is the same leak on a wire instead of to a stranger: the key is a
    header and a header is plaintext.

    The default port is filled in on both sides rather than compared as text.
    ``https://host`` and ``https://host:443`` are one origin, and a server that
    builds paging links from its own absolute URI may well emit the explicit
    form behind a proxy - so comparing ``netloc`` as a string would refuse a
    legitimate page, which is the expensive direction to be wrong in for a check
    that has never run against the live API.

    ``urlsplit(...).port`` raises ``ValueError`` on a port that is not a number,
    so a hostile ``next`` could otherwise crash the paging loop from inside the
    function meant to make it safe. That is caught here and answered as "not the
    same origin", which is both true and the safe reading.
    """
    try:
        here = urllib.parse.urlsplit(base)
        there = urllib.parse.urlsplit(url)
        if there.scheme != here.scheme:
            return False
        if (there.hostname or "").lower() != (here.hostname or "").lower():
            return False
        default = {"https": 443, "http": 80}.get(here.scheme)
        return (there.port or default) == (here.port or default)
    except ValueError:
        return False


def _interpret(status: int, raw: bytes, method: str, url: str) -> Any:
    """Turn a status and some bytes into a value or the right exception.

    ``url`` appears in messages and the key does not, because the key travels in
    a header. That is not an accident of this function - it is why the key is a
    header in the first place.
    """
    text = raw.decode("utf-8", "replace").strip()
    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = text

    if 200 <= status < 300:
        # 204 and an empty 200 are both real answers to a DELETE. An empty dict
        # rather than None, so a caller can index the result of every method
        # without branching on which one they called.
        return parsed if text else {}

    detail = _detail(parsed) or f"HTTP {status}"
    where = f"{method} {url}"
    if status in (401, 403):
        # The key this API takes is a JWT with an `exp` claim - measured
        # 2026-09-09, a live one had 1723 seconds left mid-run - so a refusal has
        # a third cause besides a wrong key and a wrong header form: a key that
        # was valid when the `Client` was built and is not any more. All three
        # look identical from here, which is why the clock is named in the
        # message. Nothing in this module reads `exp` or renews on its own: that
        # would mean decoding a credential to make a control-flow decision, and
        # what the token's real lifetime is has not been measured, only how much
        # of one instance was left.
        raise AuthError(
            f"{where} was refused: {detail}. This is the dashboard API key, not "
            f"the proxy password - check NODEMAVEN_APIKEY. If the key worked "
            f"earlier in the same process, check its expiry: the key is a JWT "
            f"and an expired one is refused exactly like a wrong one.",
            status=status,
            body=parsed,
        )
    if status == 404:
        raise NotFoundError(
            f"{where} found nothing: {detail}.", status=status, body=parsed
        )
    if status == 429:
        # This said "wait the server's own interval if it gave one, in
        # retry_after" until 2026-09-09, and `retry_after` is always `None`
        # here: `Transport` hands back `(status, bytes)` and the headers are
        # discarded before this function sees them, so a `Retry-After` the
        # server did send cannot reach the attribute the message points at.
        # A test one file over pinned it as `None` the whole time.
        raise RateLimitError(
            f"{where} was rate limited: {detail}. Nothing here retries, and this "
            f"client cannot tell you the server's interval - it reads no "
            f"response headers, so retry_after is always None. Back off on your "
            f"own schedule.",
            status=status,
            body=parsed,
        )
    if status >= 500:
        raise ApiError(
            f"{where} failed on the server: {detail}. Retrying immediately is "
            f"the thing this package declines to do for you; a 5xx that repeats "
            f"is worth reporting rather than hammering.",
            status=status,
            body=parsed,
        )
    raise ApiError(f"{where} was refused: {detail}.", status=status, body=parsed)


def _detail(parsed: Any) -> str:
    """The most useful sentence in an error body, whatever shape it arrived in.

    **This API speaks three error dialects and the spec names all three.**
    ``ErrorResponse`` is ``{"detail": "..."}``, which is Django REST Framework's;
    ``BadRequestErrorResponse`` is ``{"errors": {field: message}}``, a nested
    object under a fixed key; and the sub-user envelope is ``{"success": false,
    "description": "...", "errors": [...]}``. Only the first was handled until
    2026-09-09, so a 400 from any write endpoint came out as the literal text
    ``errors: {'proxy_username': 'This field is required.'}`` - Python syntax
    shown to somebody debugging an HTTP call.

    A bare list and a bare string are handled too, because they cost one line
    each and a wrong guess about which shape arrives is what this function is
    for.
    """
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, list):
        return "; ".join(str(item) for item in parsed)
    if not isinstance(parsed, dict):
        return ""

    for key in ("detail", "message", "error", "description"):
        value = parsed.get(key)
        if isinstance(value, str) and value:
            return value

    nested = parsed.get("errors")
    if isinstance(nested, (dict, list)) and nested:
        return _flatten(nested)
    if isinstance(nested, str) and nested:
        return nested

    return _flatten(parsed)


def _flatten(body: Any) -> str:
    """``{field: message}`` and ``[message]`` as one readable line."""
    if isinstance(body, list):
        return "; ".join(str(item) for item in body)
    if isinstance(body, dict):
        parts = []
        for key, value in body.items():
            if isinstance(value, (list, dict)):
                parts.append(f"{key}: {_flatten(value)}")
            else:
                parts.append(f"{key}: {value}")
        return ", ".join(parts)
    return str(body)


def _next_step(page: Page) -> Optional[Tuple[str, Dict[str, Any]]]:
    """The request that would follow ``page``, or ``None`` to stop.

    ``None`` on four conditions, and each is an ending rather than a guess:

    * the page carries no record of the call it came from, which is the case for
      a page built by following a ``next`` url - and a server that sends ``next``
      sends it until the collection ends, so there is nothing to do by hand;
    * the endpoint does not page at all, which is :meth:`Client.domain_statistics`;
    * the page came back **empty**, which is the one end-of-collection signal
      this server gives: measured 2026-09-08, an offset past the end answers 200
      with zero rows rather than repeating the last page;
    * the cursor or the size in that call was not a usable whole number.

    **A short page is deliberately not an ending.** It was until 2026-09-09, and
    that rule truncates against a server that caps the size below the request -
    which this one does, at ``limit=1000`` on ``cities``, where the collection is
    1965. See :meth:`Client.iterate`.

    **The cursor advances by the rows that came back, not by the size that was
    asked for**, and that is the same measurement applied a second time. It was
    ``cursor + size`` until 2026-09-09, which is only the same number while the
    server never returns fewer rows than requested; against the ceiling above,
    ``cities(limit=10000)`` walked 0 then 10000, landed 8035 rows past the end of
    the collection, and returned 1000 of 1965. Both halves of this function were
    written from one measurement in one sitting and only one of them was
    changed, so the docstring stating the ceiling sat directly above the code
    ignoring it.

    ``size`` is still read, and only to refuse a walk whose size key is missing
    or not a positive whole number. It no longer takes part in the arithmetic.
    """
    path = page.request_path
    asked = page.request_params
    paging = page.paging
    if path is None or not asked or paging is None:
        return None
    if not page.results:
        return None

    try:
        cursor = int(asked[paging.cursor_key])
    except (KeyError, TypeError, ValueError):
        return None
    if cursor < 0:
        return None

    following = dict(asked)
    if paging.cursor_counts_rows:
        try:
            size = int(asked[paging.size_key])
        except (KeyError, TypeError, ValueError):
            return None
        if size <= 0:
            return None
        following[paging.cursor_key] = cursor + len(page.results)
    else:
        following[paging.cursor_key] = cursor + 1
    return path, following


def _page(body: Any, rows_key: str = "results") -> Page:
    """A ``Page`` from whichever shape the endpoint used.

    Accepts the paginated object and a bare list, and refuses anything else with
    a message naming what came back. The alternative is ``body["results"]``,
    which raises ``KeyError: 'results'`` - a message describing this package's
    assumption rather than the server's answer.

    **Which branch runs was got wrong once, and the wrong answer was written
    down as a measurement.** This docstring said "the bare-list branch is the one
    that runs" for part of 2026-09-08, on the strength of a probe that printed
    ``count`` and nothing else - and ``count`` is ``None`` for a bare array and
    for an envelope that does not fill it, so the two readings were never
    separated. ``probe_catalogue_paging.py`` prints the shape, and the answer is
    the **envelope**: ``countries``, ``regions`` and ``cities`` all answer with
    an object whose ``results`` is the list.

    The bare-list branch has therefore never run against this server. It stays,
    because it was written for the reason "this is an inference and inferences
    are wrong" rather than because anything suggested that shape - which is the
    same reason it is worth keeping now that the inference has been wrong twice
    in opposite directions.

    ``rows_key`` is named by the caller and never guessed. Six values are in
    use and they are per-endpoint knowledge: ``results``, ``isps``, ``regions``,
    ``cities``, ``payload``, ``data``. The alternative was to look for whichever
    value in the object
    happens to be a list, which reads as robustness and is a guess - an envelope
    carrying two lists would be resolved by dict order, silently and differently
    per server version, and ``LocationsISPsResponse`` and ``SubUserManyResponse``
    both carry other fields beside their rows.

    The single-object branch is for a filter that matches one row. Whether this
    server ever takes it is unknown.
    """
    if isinstance(body, list):
        return Page(results=body, rows_key=rows_key)
    if isinstance(body, dict):
        if isinstance(body.get(rows_key), list):
            return Page(
                results=body[rows_key],
                count=body.get("count"),
                next=body.get("next"),
                previous=body.get("previous"),
                rows_key=rows_key,
            )
        # A single object where a list was expected is a real thing servers do
        # for a filter that matches one row. Wrapping it is friendlier than
        # refusing, and it is visible in `count is None`.
        if body:
            return Page(results=[body], rows_key=rows_key)
        return Page(results=[], rows_key=rows_key)
    raise ApiError(
        f"a list endpoint answered with {type(body).__name__}, which is neither a "
        f"page nor a list. Either the API changed shape or something other than "
        f"the API answered - a captive portal and a corporate proxy both do this, "
        f"and so does this API's own host, which answers an unregistered path "
        f"with 200 and the dashboard's HTML.",
        body=body,
    )


def _segment(value: Any) -> str:
    """One path segment, escaped.

    ``quote`` with an empty ``safe`` set, so an id containing ``/`` or ``?``
    cannot rewrite the path into a different endpoint. Ids come from the server,
    which makes this look unnecessary - and the day one comes from a config file
    or a command line argument instead, it is the difference between a 404 and a
    DELETE against something else.
    """
    return urllib.parse.quote(str(value), safe="")


def _urllib_transport(
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[bytes],
    *,
    timeout: float = 30.0,
) -> Tuple[int, bytes]:
    """The default transport: the standard library, and no third-party anything.

    ``urllib.request.urlopen`` raises ``HTTPError`` on 4xx and 5xx, and that
    object *is* the response - it has a status and a readable body. Catching it
    and returning the pair is what lets :func:`_interpret` see the server's own
    error message, which is the difference between "HTTP 400" and
    "proxy_username: This field is required."

    ``ProxyHandler({})`` is passed explicitly, and it is the load-bearing part of
    this function. Left out, ``urlopen`` reads ``http_proxy`` and ``https_proxy``
    from the environment - so on any machine where those are set, and they are
    set on exactly the machines that use proxies, an API call would be routed
    through a proxy nobody asked to route it through. The empty dict disables
    that. A caller who does want it can pass their own transport.
    """
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:  # a response, not a failure
        return int(exc.code), exc.read()
    except urllib.error.URLError as exc:
        raise ApiError(
            f"{method} {url} never reached the API: {exc.reason}. No status came "
            f"back, so this says nothing about the API key."
        ) from exc
