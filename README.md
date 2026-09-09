<div align="center">

<!-- Absolute, permanently, and pointing at `nodemaven/.github`. This file is the
     PyPI long description and PyPI resolves nothing relative, so a relative src
     is a broken image on the package page whatever this repository's visibility
     is. `.github` is public, so its raw URL answers 200 to a logged-out visitor.
     Verified with readme_renderer, the renderer PyPI itself runs: `div align`,
     `img src`, `height` and the badges all survive its sanitiser. -->
<a href="https://go.nodemaven.com/ghpython"><img src="https://raw.githubusercontent.com/nodemaven/.github/main/profile/assets/nodemaven-mark.svg" alt="NodeMaven" height="56"></a>

# NodeMaven Python SDK

**Builds the proxy username a gateway expects, and refuses the input it would silently drop.**

<!-- The first three read live off PyPI, so none of them can drift from the
     release. The CI badge reads `.github/workflows/ci.yml` on `main` and needs
     the repository to be public to resolve; unlike the other three it can go red
     by itself, which is the point of having it. -->

[![pypi](https://img.shields.io/pypi/v/nodemaven?style=flat-square)](https://pypi.org/project/nodemaven/)
[![python](https://img.shields.io/pypi/pyversions/nodemaven?style=flat-square)](https://pypi.org/project/nodemaven/)
[![ci](https://img.shields.io/github/actions/workflow/status/nodemaven/nodemaven-python/ci.yml?branch=main&style=flat-square&label=tests)](https://github.com/nodemaven/nodemaven-python/actions/workflows/ci.yml)
<!-- The badge points at opensource.org because it is a claim about the licence
     rather than about this repository. The file itself is linked from the
     License section at the bottom, absolutely: a relative `](LICENSE)` resolves
     against pypi.org/project/nodemaven/ on the package page and 404s there. -->
[![license](https://img.shields.io/pypi/l/nodemaven?style=flat-square)](https://opensource.org/licenses/MIT)

<!-- In file order, so the line doubles as a table of contents. `test_readme.py`
     checks every anchor here against a heading that exists; it does not check
     the order, which is why this comment does. -->

[Quickstart](#quickstart) · [Reference](#reference) · [Parameters](#parameters) · [Errors](#errors) · [Sticky sessions](#sticky-sessions) · [Why the validation is the point](#why-the-validation-is-the-point) · [Asking the gateway](#asking-the-gateway) · [Account API](#account-api) · [What it does not do](#what-this-library-does-not-do) · [Other gateways](#other-gateways) · [Docs](https://docs.nodemaven.com?utm_source=github&utm_medium=sdk_python&utm_campaign=readme)

</div>

`Proxy` opens no socket. It builds the username a proxy gateway expects, refuses
the input that gateway would mishandle, and hands the result to whatever HTTP
client you already use.

Two calls do reach the network, both by name and neither on import:
[`proxy.check()`](#asking-the-gateway) opens one CONNECT and tells you what the
gateway said about it, and [`Client`](#account-api) talks to the dashboard API.

**Works with** requests · httpx · aiohttp · Playwright · Patchright · Puppeteer ·
curl - and anything else that takes a proxy URL, because that is all it hands
back.

```
pip install nodemaven
```

## Quickstart

`login` and `password` are the **Proxy Username and Proxy Password** assigned under
Proxy Setup in the [dashboard](https://dashboard.nodemaven.com) - a separate pair from
the account you sign in with. The other option there is IP whitelisting, which needs no
credentials in the username at all; both are described in
[authentication methods](https://docs.nodemaven.com/en/articles/9979031-authentication-methods).

```python
import requests
from nodemaven import Proxy

proxy = Proxy(login="your-login", password="your-password",
              country="us", filter="medium")

r = requests.get("https://api.ipify.org", proxies=proxy.requests())
print(r.text)
```

```
203.0.113.42
```

**If that is not your own address, it worked.** If it is your own, the request
never went through the proxy.

### Why not just write the URL yourself?

Because the gateway does not tell you when you get it wrong. A misspelt
parameter is not refused - the tunnel opens, the setting is dropped, and the
traffic you are paying to route through a medium-quality US pool goes out
wherever the gateway felt like:

```python
# by hand: a typo the gateway answers 200 to, and never mentions again
"http://user-country-us-filtr-medium:pass@gate.nodemaven.com:8080"

# with this library: refused before anything is sent
Proxy(login="user", password="pass", country="us", filtr="medium")
```

```
ParamError: NodeMaven does not know the parameter 'filtr': it is answered with
200 and dropped, so the connection would succeed and your setting would NOT be
applied. Known: ['city', 'country', 'filter', 'ipv4', 'isp', 'region', 'sid',
'speed', 'ttl', 'type']
```

That is the whole reason the package exists, and
[why the validation is the point](#why-the-validation-is-the-point) has the
measurements behind it.

Credentials can come from the environment instead, so nothing is in your source:

```python
# NODEMAVEN_LOGIN and NODEMAVEN_PASSWORD
proxy = Proxy(country="us", filter="medium")
```

The same identity, for other clients:

```python
proxy.url()          # http://user:pass@gate.nodemaven.com:8080  - httpx, aiohttp, curl
proxy.requests()     # {"http": ..., "https": ...}
proxy.httpx()        # {"http://": ..., "https://": ...}
proxy.playwright()   # {"server": ..., "username": ..., "password": ...}
proxy.username       # the username on its own
proxy.server         # host:port, no credentials
```

With Playwright, Patchright or Puppeteer:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(proxy=proxy.playwright())
```

## Reference

<!-- The rule this section is held to: nothing below this heading explains a
     decision. Every "why" belongs further down, or in the docstring. If a
     sentence here would survive the decision being reversed, it does not belong
     here. -->

What every public name takes, returns and raises. Nothing in this section needs
the ones after it; those carry the measurements the refusals were built on.

### `Proxy`

```python
Proxy(*, login=None, password=None, host=None, port=None, provider=None, **params)
```

Keyword-only. Builds a username and opens nothing.

| argument | falls back to | refused when |
|---|---|---|
| `login` | `NODEMAVEN_LOGIN` | missing → `CredentialsError` |
| `password` | `NODEMAVEN_PASSWORD` | missing → `CredentialsError` |
| `host` | `NODEMAVEN_HOST`, then the definition's own | - |
| `port` | `NODEMAVEN_PORT`, then the definition's own | not a whole number 1 to 65535 → `CredentialsError` |
| `provider` | the shipped `nodemaven` definition | - |
| `**params` | - | a name outside `known_params`, or a value that is empty, carries a separator, carries whitespace the definition does not fold, or is outside a list the definition declares → `ParamError` |

The environment names come from the definition's id in upper case, so a gateway
of your own reads its own pair - see [Other gateways](#other-gateways).

| attribute | is |
|---|---|
| `.username` | the username, in the gateway's dialect |
| `.server` | `host:port`, with no credentials in it |
| `.params` | the parameters as they will be sent, already folded. A copy |
| `.provider` | the `Provider` behind it |

| call | returns |
|---|---|
| `.url(scheme="http")` | `http://user:pass@host:port`, both credentials percent-encoded |
| `.requests(scheme="http")` | `{"http": ..., "https": ...}` |
| `.httpx(scheme="http")` | `{"http://": ..., "https://": ...}` |
| `.playwright()` | `{"server": ..., "username": ..., "password": ...}`, credentials **not** encoded |
| `.session(session_id)` | a new `Proxy` pinned to that sticky session |
| `.sessions(count, *, length=6)` | a list of `count` new `Proxy` objects, ids distinct |
| `.replace(**changes)` | a new `Proxy`; a value of `None` removes that parameter |
| `.check(*, target="api.ipify.org:443", timeout=15.0)` | a `Check`. **The only call here that opens a socket** |

`session()` raises `ParamError` on a definition that declares no session
parameter. `sessions()` ids are `2 * length` hexadecimal characters, so the
default holds 2\*\*48; it raises `ParamError` when `count` asks for more distinct
ids than `length` bytes can hold, rather than looping forever looking for them.

### `Check`

Returned by `proxy.check()`. Frozen, and a refusal arrives as one of these
rather than as an exception.

| attribute | is |
|---|---|
| `.ok` | `True` only on 200 |
| `.status` | the CONNECT status, an `int` |
| `.reason` | the reason phrase, verbatim - it labels which back end answered |
| `.server` | the `host:port` that was asked |
| `.elapsed` | seconds, including DNS and the TCP handshake |
| `.headers` | every response header, keys lower-cased |
| `.exit_ip` | the exit address, or `None` when the gateway did not send one |
| `.meaning` | what this status means **on this gateway**, or `None` |

`CheckError` is raised only when nothing usable came back at all: DNS failure, a
refused connection, a timeout, a response head that never ended, or a first line
that is not a status line. Refusals that happen before anything is sent are
`CheckError` too, and those messages end in *Nothing was sent.*

### `Client` and `Page`

```python
Client(api_key=None, *, base_url=None, timeout=30.0, transport=None)
```

`api_key` falls back to `NODEMAVEN_APIKEY` and raises `CredentialsError` when
neither is set. `transport` is `(method, url, headers, body) -> (status, bytes)`
and defaults to `urllib.request`.

| call | returns |
|---|---|
| `.me()` | the account object, the server's own field names |
| `.countries()` `.regions()` `.cities()` | a `Page` |
| `.zip_codes()` `.zip_code_regions()` `.zip_code_cities()` | a `Page` |
| `.isps()` `.isp_regions()` `.isp_cities()` | a `Page` - `isps()` has an [envelope that is not the usual one](#the-isp-catalogue-answers-a-different-shape) |
| `.statistics_data(proxy_username, **filters)` / `.statistics_requests(...)` | a `dict` |
| `.domain_statistics(proxy_username, **filters)` | a `Page` that does not page - the whole answer is one object |
| `.sub_users()` `.whitelist_ips()` | a `Page`, numbered by page rather than by offset |
| `.whitelist_ip(id)` | a `dict` |
| `.create_sub_user(username, password, *, traffic_limit=None, is_traffic_limited=None, **extra)` | a `dict` |
| `.update_sub_user(id, **changes)` / `.delete_sub_user(id)` | a `dict` |
| `.reset_sub_user_usage(ids)` | a `dict`. Takes a list, not one id |
| `.upsert_whitelist_ip(ip, ports_count, *, name=None, protocol="HTTP", sticky=None, ttl=None, **extra)` | a `dict`. Creates **or replaces**. [`protocol` is always sent](#the-whitelist-needs-a-field-the-spec-marks-optional) |
| `.delete_whitelist_ip(id)` | a `dict` |
| `.iterate(page, *, max_pages=100)` | an iterator over the rest of the collection, page by page |
| `.validate(proxy)` | a list of problem strings, empty when the catalogue agrees |

Every list call takes `**filters`, passed through as query parameters in the
server's own spelling - `country__code="us"`.

**Paging differs by endpoint and the difference is not cosmetic.** The nine
location endpoints take `limit` and `offset`, both **always sent**: `limit`
defaults to `DEFAULT_PAGE_SIZE`, 1000, and `offset` to 0. `sub_users()` takes
`page` and `per_page`; `whitelist_ips()` takes `page` and `page_size`, whose
documented default is 5 and maximum 100. An unknown query parameter is ignored
rather than refused, so one hard-coded pair would silently do nothing on two
thirds of this surface.

1000 is the largest limit the location endpoints accept: `limit=10000` is
refused outright by `isps`, and on `cities` it returns the same 1000 rows
`limit=1000` does.

**That 1000 is a ceiling on the answer, not a count of the rows behind it.**
Asking `cities` for the next offset at the same limit returns a further 965, so
one call sees about half that collection and nothing in the reply says so -
`count`, `next` and `previous` all come back `None`. Use `iterate()` there. The
other catalogues do fit in one request.

A `Page` iterates its own rows and has a `len()`. `.count`, `.next` and
`.previous` are the server's, and are `None` everywhere - no schema in the
vendor's own specification declares either field, so this is the API's shape and
not a gap in one endpoint. `.request_path`, `.request_params` and `.paging`
record the call the page came from, which is what lets `iterate()` ask for the
next one.

`iterate()` raises `ApiError` rather than looping in four cases: more than
`max_pages` pages, a next-page url that has already been returned, a page
identical to the one before it - the server accepted the cursor and ignored it -
and a next-page url pointing at a different scheme, host or port than
`base_url`. The host check is there because the request that would follow the
url carries the API key in a header.

**Both page-numbered endpoints start at page 1**, measured 2026-09-09 by
`lab/probes/probe_account_api.py --phase 9`. On `sub-users/` the evidence is
where the rows are - page 0 came back with none and page 1 with the account's
only sub-user, which a 0-based server cannot produce. On `whitelist/ips` the
collection is empty, so the reading is weaker: page 1 is the only number
answered `200` at all, while 0, 2 and 9999 are answered `404`.

**The two endpoints do not end their collections the same way.** Past the last
page `sub-users/` answers `200` with an empty payload and `whitelist/ips`
answers `404`, so a `404` is treated as the end of the walk on the whitelist and
nowhere else - everywhere else it is still an error, because a `404` is also
what a wrong path looks like.

### `Provider` and the module functions

| call | returns |
|---|---|
| `load(provider_id="nodemaven")` | a shipped definition |
| `load_file(path, provider_id=None)` | a definition from a TOML file; the id is the filename unless named |
| `available()` | the ids of every shipped definition, as a list |

A `Provider` is a frozen description of one gateway: `id`, `label`,
`known_params`, `status`, `prefix`, `separator`, `pair_separator`,
`session_param`, `host`, `port`, `aliases`, `values`, `normalize`,
`connect_reactions`, `exit_ip_header`, `source`, `source_read`, `notes`. Only
`id`, `label` and `known_params` are required. `.is_measured` is `True` when
`status` is `measured`.

## Parameters

<!-- The right-hand column is values measured to work and is deliberately not
     called "allowed" - see the note under the table. The date and the probe
     behind each row are in CHANGELOG.md, not here: this file is read to use the
     library, and a provenance trail in every cell of it reads as noise. -->

What the shipped NodeMaven definition accepts. Every name here was confirmed
against the gateway rather than transcribed:

| parameter | what it selects | values measured to work |
|---|---|---|
| `country` | country code, or `any` | `us`, `de`, ... |
| `region` | area inside the country | a name |
| `city` | city inside the country | a name, with a `region` beside it |
| `isp` | the exit's ISP | a name |
| `type` | mobile or residential exits | `mobile`, `residential` |
| `sid` | the sticky session - see below | any string with no `-` |
| `ttl` | how long that session is held | `1m`, `10m`, `10h`, `24h` |
| `filter` | IP quality | `low`, `medium`, `high` |
| `speed` | claims a connection speed class - see below | `fast`, `slow` |
| `ipv4` | claims to force IPv4 - see below | `True` |

`type` picks a different pool rather than a filter over one pool. Five requests
per arm with a fresh `sid` and `country=us`:
`type=mobile` drew T-Mobile and Verizon Wireless ASNs, while `type=residential`
and leaving it unset drew Comcast, Charter, Windstream and other wireline
carriers, with no mobile ASN among them.

**`ipv4` and `speed` are confirmed names whose effects are unmeasured**, and the
table says `claims to` for that reason. For `ipv4` the name took a different
method to confirm: a junk value on it is answered `200`, so it cannot be told
apart from an unimplemented name that way. What tells them apart is the sticky
session, whose key is the parsed parameter set - over two
independent session ids with both controls holding, `ipv4=True` moves the exit
and an unknown name does not. `ipv4=False` lands on the same exit as leaving it
out, which is what a default would do and also what a dropped value would do.

**Names are validated. Values, on this gateway, are not.** Passing a name that is
not in this table raises before anything is sent, because the gateway answers an
unknown name with 200 and drops the setting. Values are passed through, because
what is known is which ones have been observed to work - and that is not the same
as the set the gateway accepts. Refusing on a guessed list would block a setting
that would have worked, which is the worse mistake of the two. The schema does
carry a per-parameter list of legal values and refuses anything outside it; the
shipped definition leaves that list empty for every parameter, deliberately, and
a definition you write yourself gets the check as soon as you fill it in.

### Case and spacing

`country`, `region`, `city`, `isp` and `type` are folded before they are sent:
surrounding whitespace trimmed, ASCII `A-Z` lowered, each remaining space turned
into `_`. `country="US"` and `country="us"` are therefore the same request, and

```python
Proxy(login="u", password="p", region="District of Columbia").username
# u-region-district_of_columbia
```

`region-district_of_columbia` is the form this gateway generates for itself - it
appears in a username the dashboard issued - and the vendor's own client applies
the same transformation. Without the fold a space reaches the username, which
cannot carry one: the CONNECT line is a single token, so the value is either
malformed or cut short.

**`sid`, `filter`, `ttl` and `speed` are sent with their case unchanged.** `sid`
is yours, and folding an identifier a caller chose would rename their session, so
it is left alone whatever the gateway does with it.

For the other three, **pass lower case**, and for `ttl` that is not advice:
`ttl-10m` opens the tunnel and `ttl-10M` is answered `407`,
which reads as a credentials problem and is not one. `filter` and `speed` were
not refused in either case, and this library still does not fold them - what the
gateway accepts today and what it will accept next month are different claims,
and the fold list is data in the gateway definition rather than a decision in
this package.

Which parameters fold is declared in the gateway definition, as data, so a
gateway you describe yourself folds what you say it folds and nothing else.

**Every other value is refused if it contains whitespace.** There is no spelling
of a space that works here - `username` would emit it raw, `url()` would
percent-encode it to `%20`, and `playwright()` would hand over a third thing -
so between the fold and the refusal, no value with whitespace in it can reach
the wire by any path.

Credentials come from `NODEMAVEN_LOGIN` and `NODEMAVEN_PASSWORD` when not passed
in, and the gateway address from `NODEMAVEN_HOST` and `NODEMAVEN_PORT`.

## Errors

Everything inherits from `NodeMavenError`, so one `except` catches everything
this library raises.

| exception | raised when |
|---|---|
| `ParamError` | a parameter name is unknown, a value is empty, a value contains whitespace or the gateway's separator, or a value is outside a list the definition declares |
| `CredentialsError` | no login, no password, no gateway address, or no API key, from arguments or environment |
| `ProviderError` | a gateway definition is missing, unreadable, or internally inconsistent |
| `CheckError` | `check()` got no answer at all - DNS, a refused connection, a timeout, or something that is not a proxy on that port |
| `ApiError` | the account API refused a call, or answered a shape this library cannot read. Carries `.status` and `.body` |
| `AuthError` | the API key was rejected - `ApiError` with a 401 or 403 |
| `NotFoundError` | the row is gone - `ApiError` with a 404 |
| `RateLimitError` | too many calls - `ApiError` with a 429, and a `.retry_after` |
| `NodeMavenError` | the base, never raised on its own |

`ParamError` also covers the two structural cases: `session()` on a definition
that declares no session parameter, and a definition whose parameter names
collide with `login`, `password`, `host`, `port` or `provider`.

The first three are found **before a socket exists** - they are failures in what
you asked for, not in what happened. The next five have been to the network and
back. That split is why they are separate classes: retrying a `ParamError` can
only produce the same `ParamError`.

Two credentials, two exceptions, and they are not interchangeable.
`CredentialsError` from `Proxy` is the **proxy password**, refused before
anything is sent; `AuthError` from `Client` is the **dashboard API key**, and it
has been to the server. A library that reported both as one would tell you to fix
the key when the password is wrong.

## Sticky sessions

One `Proxy` is one identity. Pin it to a sticky session:

```python
held = proxy.session("order4417")
```

**A session id cannot contain the character the gateway separates parameters
with**, which for this one is `-`, and passing one raises rather than connecting.
That is measured and not a precaution: a probe opened tunnels with
`sid-order8e3bf9-4417` and with `sid-order8e3bf9`, four rounds each, interleaved,
and both landed on **one exit address** while a third arm spelled
`sid-order8e3bf94417` held a different one throughout. The gateway cuts the value
at the separator and reads the rest as something else, so every order id
beginning `order` would quietly share one session and one exit.

**The same cut applies to every parameter, not just `sid`,** which is why a
separator in any value is refused. `isp-verizon` opens the
tunnel, a junk `isp` is answered `406`, and `isp-verizon-zzqqx-zzqqx` is answered
`200` - so the gateway took `verizon` as the ISP and read the tail as a parameter
name it does not know, which it drops silently.

**The session key is the whole parameter set, not the session id.**
`country=us, sid=A` and `country=us, sid=A, filter=medium` are two different
sessions on the gateway, so adding or removing any parameter moves you to a
different exit address. That is why parameters change through a method that
returns a new object rather than by assignment - the move is a different
identity, and the code should say so:

```python
germany = proxy.replace(country="de")   # a new identity, a new exit
plain   = proxy.replace(filter=None)    # also a new identity
```

**The set, not the order.** Measured over 20 rounds a side: the canonical
parameter order and a shuffled one drew the same exit 20 times each, while a
control differing by one parameter *value* drew a different exit 20 times. So
the order this library emits parameters in cannot change which exit you get.

### Many sessions at once

For a worker pool, one identity per worker:

```python
for identity in proxy.sessions(50):
    queue.put(identity)                 # each one a different exit
```

Each id is `2 * length` hexadecimal characters from `secrets`, `length=6` by
default, and the ids are distinct **within one call**. Asking for the whole
space or more raises `ParamError` - `sessions(256, length=1)` wants every one of
the 256 ids an eight-bit space holds, and drawing them without repeating is a
loop that either never finishes or leaves nothing for the next caller.

Hex, and not the alphabets people reach for first, because the gateway cuts a
value at its separator and every id sharing a prefix then collapses onto one
exit - silently, since the connection still succeeds. `secrets.token_urlsafe`
emits `-` and `_`, `uuid4()` emits `-` four times, base64 emits `+` and `/`, and
each of those is a separator on some gateway. From `secrets` and not `random`
because `random` is seeded from the clock: two workers starting in the same
millisecond would draw the same ids.

## Why the validation is the point

<!-- Everything below this heading is a measurement, and none of it carries a
     date. The dates and the probes are in CHANGELOG.md, which is linked from the
     next paragraph and is where a reader asking "is this still true" should be
     sent. Putting a date on every claim here was tried and read as noise: this
     file is opened to use the library, not to audit it. -->

Every gateway behaviour below was measured against the live gateway rather than
transcribed from documentation, and each one carries its date and the probe
behind it in [CHANGELOG.md](https://github.com/nodemaven/nodemaven-python/blob/main/CHANGELOG.md).

A gateway is bad at telling you that you got the username wrong. One class of
mistake - a value it will not take - comes back five different ways, and not one
of them names the parameter. Read by raw CONNECT, one arm per row:

| you sent | the gateway answers |
|---|---|
| bad `country` value | `407 Proxy Authentication Required` |
| bad `region` value | `406 Not Acceptable` |
| bad `city` value | `406 Not Acceptable` |
| `city` sent without `region` | `500 Internal Server Error` |
| bad `isp` value | `406 Not Acceptable`, and `410 Gone` for `comcast` |
| bad `filter` value | `407 Proxy Authentication Required` |
| bad `ttl` value | `407 Proxy Authentication Required` |
| bad `type` or `speed` value | `407 Proxy Authentication Required` |
| empty value | nothing, the connection hangs about 20 s |
| **unknown parameter name** | **`200`, and the parameter is ignored** |

Every `407` there sends you to check credentials that are correct, and the `406`
does not even say which of the two parameters it refused: a bad `region`, a bad
`isp` and `charter` - a real ISP - all answer it, so it separates neither the
parameter nor a misspelling from a pool you cannot have. `comcast` is the one
value measured to answer `410` instead, which reads as a name the gateway knows
and a pool this account cannot reach - one ISP, so read it that narrowly.

**The two `city` rows are one rule: send `city` with its `region`.** Measured
over six CONNECTs holding the login, the password, the target, the
gateway host and port and the parameter order fixed. `country=us`,
`region=louisiana`, `city=abbeville` answers `200`, and so does a second city in
a second region. The same city with the region left out answers `500`, and an
invented name sent with a real region answers `406` - so the gateway does look
the name up, and the `500` is a request it could not resolve rather than a fault
on their side. `Client.validate()` refuses that combination before it goes out.

The last row is worse than any of them: the request succeeds, your code carries
on, and the setting you asked for was never applied. Nothing that comes back
over the wire can tell you.

`ttl` counts in minutes and hours - `1m`, `10m`, `10h` and `24h` connect, while
`10s`, `10d` and a bare `10` are answered `407`. It is also the one parameter
whose value case matters: `10M` is refused where `10m` is accepted. Parameter
*names* are case-insensitive at the gateway; this library folds values for
`country`, `region`, `city`, `isp` and `type` to the wire form anyway, so a space
or a capital in a place name is not your problem.

So this library checks before anything is sent:

```python
>>> Proxy(login="u", password="p", contry="us")
ParamError: NodeMaven does not know the parameter 'contry': it is answered with
200 and dropped, so the connection would succeed and your setting would NOT be
applied. Known: ['city', 'country', 'filter', 'ipv4', 'isp', 'region', 'sid',
'speed', 'ttl', 'type']
```

## Asking the gateway

Validation catches everything knowable without sending anything. For the rest -
a wrong password, a country the pool does not have, a value the gateway dislikes
- there is one call that opens a single CONNECT and reports what came back:

```python
result = proxy.check()
```

<!-- 203.0.113.7 is RFC 5737 TEST-NET-3, reserved for documentation, so nobody
     reads it as a real exit address. The two blocks below are compared against
     `str(Check(...))` by `test_readme.py`, word for word, after collapsing
     whitespace - so re-wrapping the prose is allowed and changing it is not. -->

```
200 Connection established via gate.nodemaven.com:8080 in 0.42s, exit 203.0.113.7
```

The exit address arrives **on the CONNECT reply itself**, on a header the gateway
definition names, so knowing where you came out costs one handshake and no
traffic through the tunnel.

**Do not build anything on it being there.** More than one implementation
answers behind this hostname, which one you reach is decided by your username,
and they do not agree about the header: one measured `200` carried
`X-Exit-IP` where the shipped definition names `X-Proxy-Exit-IP`, and others
send no address at all. So `result.exit_ip` is `None` more often than the
definition suggests, and that is normal rather than an error. If you need the
address every time, read it through the tunnel from a service that echoes it.

**A refusal is a return value, not an exception.** The status code is the thing
you came for, and raising would bury it in a traceback - which is what a general
HTTP client does. So a failed tunnel comes back as an object, carrying the
gateway's own reading of its own status code:

```
407 Proxy Authentication Required via gate.nodemaven.com:8080 in 0.19s
usually NOT your credentials, despite what the status says. A value the gateway
will not take on `country`, `filter`, `ttl`, `type` or `speed` answers 407, and
so does a wrong password. Check the values before the password - and check the
case of `ttl`, which is the one value that is case-sensitive: `10M` is refused
where `10m` is accepted.
```

That second paragraph is data in the gateway definition, not a string in this
library, because what a status code means is per-gateway. The fields a `Check`
carries are in the [reference](#check); `CheckError` and when it is raised are
there too.

**`ok` does not mean your parameters were applied.** An unrecognised parameter
name is also answered `200` and dropped, which is the whole reason the section
above refuses unknown names before sending. No call can recover that after the
fact, and this one does not pretend to.

`check()` names the host it tunnels to - `api.ipify.org:443` by default - and
whatever you name will see a TCP connection from your exit address. There is no
CONNECT to nowhere, so this is a parameter rather than a constant:

```python
proxy.check(target="example.com:443", timeout=15.0)
```

The timeout defaults to 15 seconds rather than something brisk, because one of
this gateway's measured reactions is no reply for about 20 seconds. A 5-second
timeout would report that as a network problem.

## Account API

Quota, usage, sub-users and the location catalogue. Separately credentialled,
because the API key and the proxy password are different secrets from different
places.

**Every path here now comes from the vendor's own OpenAPI specification**, read
2026-09-09. Five of the calls have also been sent against a live account and
answered: `users/me`, `countries`, `regions`, `cities` and `isps`, measured
2026-09-08. **The rest are still transcribed** - from the specification now
rather than from the vendor's client at `github.com/nodemavencom/proxy`,
`python/nodemaven/client.py`, where four paths were wrong. The five write calls
have still never been called, on purpose: probing one costs a real object on a
production account.

<!-- The paragraph below is a live property of this server, not a note about
     how it was found: it is the reason a transcribed path here is not
     self-correcting, and `test_the_account_api_separates_what_was_called_from_what_was_not`
     pins it. -->

**A wrong path is not answered `404` here**, measured 2026-09-09.
`locations/zip-codes/`, `statistics/` and `whitelist-ips/` - three paths this
package sent before the specification was read - are answered `200`,
`text/html`, 6415 bytes, byte-identical to a path invented on the spot as a
negative control. The dashboard serves its front end for anything it does not
route, so **calling a path cannot tell you whether the path exists.** If you
wrap a path of your own against this API, compare its response against a path
nobody could have implemented rather than against a status code.

The real paths are `locations/zipcodes/` (solid, no separator),
`statistics/data/`, `statistics/requests/`, `statistics/domains/` and
`whitelist/ips`. `sub-users/` was real all along but was being read under
`results`, where the rows are under `payload`.

Calling `isps` is how its [different envelope](#the-isp-catalogue-answers-a-different-shape)
was found; the other four came out of the specification.

```python
from nodemaven import Client

client = Client()                       # NODEMAVEN_APIKEY from the environment
me = client.me()
print(me["data"])                       # traffic left
```

`me()` returns the server's own object with its own field names, unrenamed and
unmodelled. It answers six fields:

| field | type | |
|---|---|---|
| `data` | `int` | traffic left. **Not** `traffic_left` |
| `email` | `str` | |
| `is_traffic_frozen` | `str` | **not a bool** - see below |
| `proxy_password` | `str` | the proxy password, not your API key |
| `proxy_username` | `str` | |
| `subscription_status` | `str` | |

**`is_traffic_frozen` is a string, so `if me["is_traffic_frozen"]:` is true
whichever way it reads.** Compare it against the value rather than for truth.

Not modelling this into a dataclass is deliberate, and the response above is the
argument for it. Written a day earlier from the vendor's client, a dataclass
would have declared `traffic_left`, which does not exist, and typed
`is_traffic_frozen` as a bool, which it is not. The raw dict was wrong about
nothing, because it claimed nothing.

```python
client.countries()                      # the catalogue, paginated
client.regions(country__code="us")      # Django's field lookup, the server's spelling
client.cities(country__code="us", region__code="dc")
client.isps(country__code="us")         # a different envelope, see below
client.zip_codes(country__code="us")

# Which regions and cities the ISP and zip-code catalogues actually cover.
# Separate endpoints, not filters on the two above.
client.isp_regions(country__code="us")
client.isp_cities(country__code="us", region__code="dc")
client.zip_code_regions(country__code="us")
client.zip_code_cities(country__code="us", region__code="dc")

# Statistics are per proxy username, and the username is required.
client.statistics_data("acct-1", start_date="2026-09-01", end_date="2026-09-07")
client.statistics_requests("acct-1", start_date="2026-09-01")
client.domain_statistics("acct-1")

client.sub_users(page=1)
client.create_sub_user("worker-1", "a-password", traffic_limit=1024)
client.update_sub_user(id, traffic_limit=2048)
client.delete_sub_user(id)
client.reset_sub_user_usage([id])       # a list, even for one

client.whitelist_ips(page=1)
client.whitelist_ip(id)
client.upsert_whitelist_ip("203.0.113.7", 10, name="the office")
client.delete_whitelist_ip(id)
```

The dates go as `yyyy-mm-dd`. The vendor's documentation says `dd-mm-yyyy` in
its prose and types the same fields as ISO dates two lines below; the type is
what the server parses.

**`sub_users()` returns each sub-user's `proxy_password` in clear text**, on
every row, by the specification's own required-field list. So does `me()`. Do
not print a row of either, and do not paste one into an issue.

Five of the vendor's twenty-four documented paths are deliberately not wrapped:
`locations/all-doc/`, `notifications/`, `llm/submit/`, `llm/results/{id}/` and
`llm/balance/`. Listing them is the point - an omission nobody wrote down reads
the same as an oversight.

A list endpoint returns a `Page`, which iterates **one page** and not the
collection. `iterate()` gets the rest:

```python
page = client.countries()               # one page, 1000 rows by default
for country in client.iterate(page):    # all of them
    ...
```

**`page.count` is `None` everywhere, and that is the API's shape rather than a
gap here.** No schema in the vendor's specification declares a `count` or a
`next` at all - `PaginatedCountryList` is `{"results": [...]}` and nothing else -
and a page of 50 drawn from a catalogue of nearly 200 countries came back with
all three fields empty. A full page is therefore indistinguishable from a
complete collection by looking at it, so `iterate()` asks for the next cursor
and reads the answer.

**It stops on an empty page, not on a short one.** That rule changed on
2026-09-09 and the one before it was unsafe against this server in particular:
it stopped at the first page shorter than the size it had asked for, which is
wrong wherever the server caps the size below the request. `cities(limit=10000)`
is answered with 1000 rows out of 1965, and "shorter than asked" reads those
1000 as the end. The measurement that says so is four paragraphs up in this same
file and was already there - a measurement sitting in a document is not a
measurement anyone applied. Stopping on empty costs one spare request per walk
and cannot truncate.

`limit` and `offset` are sent on your behalf and are overridable:

```python
client.countries(limit=50)              # four requests instead of one
```

They are sent rather than omitted because `isps()` **refuses** a request without
them, while the others answer one with a silently partial list. `offset` is
honoured: `offset=50` returns rows disjoint from `offset=0`, and an offset past
the end answers `200` with zero rows.

`sub_users()` and `whitelist_ips()` are numbered by page instead, and **both
start at page 1**, measured 2026-09-09 - see
[the reference](#client-and-page). They mark the end of a collection
differently, so `iterate()` cannot use one rule for both: past the last page
`sub-users/` answers `200` with an empty payload and `whitelist/ips` answers
`404`. A `404` therefore ends the walk on the whitelist and nowhere else.

`iterate()` raises rather than looping in four cases: a next-page url it has
already returned, more than `max_pages` pages, a page identical to the
one before it - which means the server took the cursor and ignored it - and a
next-page url on another host. None is a tuning knob; each is the difference
between a bug you can see and one that surfaces as a rate limit or a short
answer.

### The ISP catalogue answers a different shape

`isps()` returns a `Page` like the others and most callers can stop here. The
rest of this section is why it took two runs to get there.

Its `200` is an object keyed `city`, `country`, `isps` and `region`, with no
`results` anywhere. The rows are the list under `isps` - 358 of them for
`country__code="us"`; the other three fields are strings and are not rows.
`isps()` reads that key and the other four list methods read `results`. That is
per-endpoint knowledge in the client rather than a page builder that goes
looking for whichever value happens to be a list, which is a rule decided by key
order the day a second list appears.

For a day this method returned a `Page` of exactly one row - the envelope itself
- whatever the account held. Nothing was released in that state; it was written
up as broken rather than fixed, because the run that found it printed the key
*names* and not the values, and a key unwrapped because its name reads right is
how a parameter the gateway ignores once got into this package and a field the
server does not send got into this README. The fix waited for one command, and
was the same edit either way.

### The whitelist needs a field the spec marks optional

`upsert_whitelist_ip()` always sends `protocol`, defaulting to `"HTTP"`. The
vendor's OpenAPI document marks `ip` and `ports_count` required and gives
`protocol` a `default: "HTTP"`; the server does not apply that default. Measured
2026-09-09 at 16:18, one field at a time:

| body | answer |
|---|---|
| `ip`, `ports_count`, `name` | `400 "Please enter a valid protocol(HTTP or SOCKS5)."` |
| the same plus `protocol: "HTTP"` | `201`, `{"ip_id", "message"}`, and a read of `whitelist/ips` found the address |

So a client written from the specification sends the one body that fails. The
default here is a compensation for that, not a convenience, which is why
`protocol` is a keyword with a value rather than another `None`.

Two things that run did not settle: `name` was present in every rung, so whether
it is also required is untested, and no rung tried `ip`, `ports_count` and
`protocol` alone, so that trio is not known to be a complete body.

An earlier version of this section said only that the required pair was refused
and that which field was short was the server's word. That was accurate and it
was one call away from being a measurement.

### Checking a Proxy against the catalogue

The gateway answers a country it does not have with `407`, which reads as a
credentials problem, and does not say which parameter was wrong. The catalogue
knows, so it can be asked:

```python
problems = client.validate(proxy)
if problems:
    raise SystemExit("\n".join(problems))
```

This is a method on `Client` and not a check inside `Proxy`, for one reason: a
refusal that ships in a release can be wrong forever, and the catalogue moves.
Asking the live catalogue cannot go stale - and it costs a network call, so it
has to be your decision rather than a hidden one.

Two things are checked. `country` is matched against the catalogue, and **a
`city` sent without a `region` is refused before the request goes out** - that
one needs no network. The gateway answers a city with no region with `500`,
which reads as a fault on their side and is not one; the same city with its own
region answers `200`. The values of `region`, `city` and
`isp` are not matched against the catalogue, because city codes repeat across
regions - `aberdeen`, `albany` and `alexandria` each appear twice in a single
page - so matching a bare code would report success and mean nothing.

### No dependencies, and your own client if you want one

The transport is `urllib.request` from the standard library, so this adds nothing
to your dependency tree. If you would rather it went through the client you
already have, that is one function:

```python
def transport(method, url, headers, body):
    r = requests.request(method, url, headers=headers, data=body)
    return r.status_code, r.content

client = Client(transport=transport)
```

Return the status rather than raising on it; mapping statuses to exceptions is
this library's job, and doing it in both places is how a `NotFoundError` becomes
somebody else's exception halfway up a stack.

## What this library does not do

**It does not retry.** That is deliberate, and it is the one design decision
here taken against a measurement rather than a preference.

Retrying a refused request is the thing that most reliably makes the next one
worse: each retry confirms automation to the target and burns the exit range for
everyone else sharing the pool. Measured over 1464 attempts, the chance that the
next attempt succeeds, by how many failures came immediately before it:

| failures before | P(next attempt succeeds) |
|---|---|
| 0 | 75% |
| 1 | 21% |
| 3 | 5.9% |
| 5 | 5.8% |
| 6 | 1.6% |
| 7-9 | 0.5% |

294 attempts were spent past six consecutive failures and returned 3 pages - 98
attempts per delivered page, against 1.7 in a healthy session. A library that
shipped automatic retry as a default would be spending that on your behalf
without telling you.

Those 1464 attempts, and the cells they came from, are in
[nodemaven/proxy-benchmark](https://github.com/nodemaven/proxy-benchmark) - the
harness that measured them, open source, so the table above can be re-run rather
than believed.

It also does not own an HTTP client, a connection pool or a browser. Those are
yours, and they are better than anything a vendor SDK would bundle.

## Other gateways

**No account here? Any proxy you already have works.** Parameters are data, not
hardcoded keywords. A gateway is its prefix, separators, session parameter and
the set of parameter names it actually recognises - and a definition written by
you goes through the same builder and the same validation as the one shipped
here.

Build it in place:

```python
from nodemaven import Provider, Proxy

mine = Provider(id="mine", label="My proxy", known_params=frozenset())
proxy = Proxy(provider=mine, login="u", password="p",
              host="proxy.example.com", port=8000)
```

Describe the parameters it does take and it validates those too. Or keep the
definition in a TOML file:

```toml
# my-gateway.toml
label = "My proxy"
known_params = ["country", "session"]
session_param = "session"
host = "proxy.example.com"
port = 8000
```

```python
from nodemaven import Proxy, load_file

mine = load_file("my-gateway.toml")
proxy = Proxy(provider=mine, login="u", password="p", country="us")
proxy.session("order4417")     # u-country-us-session-order4417
```

`known_params` is the whole point of the file: name a parameter that is not in
it and the call raises instead of connecting. Leave the list empty and every
parameter is refused, which is the correct thing to say about a gateway whose
dialect nobody has established.

Credentials fall back to the environment under the definition's id in upper case,
so this one reads `MY_GATEWAY_LOGIN` and `MY_GATEWAY_PASSWORD` and never
`NODEMAVEN_*`. One process can hold several gateways without their credentials
reaching each other.

**The id comes from the filename, not from the variable you assign it to.**
`load_file("my-gateway.toml")` is `my-gateway` however it is named in your code,
and `-` becomes `_` in the variable names. Pass `provider_id=` to say it
outright. The error raised when a credential is missing prints the exact pair it
looked for, so this is one guess you never have to make.

Every definition carries a `status`. `measured` means traffic has gone through
that gateway and the dialect was read off the wire. `documented` means it was
transcribed from documentation and never exercised. Only `nodemaven` is shipped
here, and it is `measured`.

## Requirements

Python 3.9 or newer. No dependencies on 3.11 and newer; `tomli` on older ones.

## Changes

[CHANGELOG.md](https://github.com/nodemaven/nodemaven-python/blob/main/CHANGELOG.md).
Entries carry the probe and the date behind any change to what the gateway is
believed to accept.

## License

<!-- Absolute and `blob/main`, for the same reason the logo src is absolute: on
     the PyPI page a relative `](LICENSE)` resolves against pypi.org and 404s. -->

[MIT](https://github.com/nodemaven/nodemaven-python/blob/main/LICENSE).
