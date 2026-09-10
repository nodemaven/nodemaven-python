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
     the order, which is why this comment does.

     Kept as one line rather than the vertical list an outside review asked for,
     2026-09-10, and the reason is where it renders: this block is the PyPI page
     above the install command, and twelve bullets there push `pip install` off
     the first screen. A nav is the one list a reader is meant to scroll past. -->

[Quickstart](#quickstart) · [Parameters](#parameters) · [Sticky sessions](#sticky-sessions) · [Errors](#errors) · [Account API](#account-api) · [Other gateways](#other-gateways) · [Documentation](#documentation)

</div>

`Proxy` opens no socket. It builds the username a proxy gateway expects, refuses
the input that gateway would mishandle, and hands the result to whatever HTTP
client you already use.

Two calls do reach the network, both by name and neither on import:
`proxy.check()` opens one CONNECT and tells you what the gateway said about it,
and [`Client`](#account-api) talks to the dashboard API.

**Works with** requests · httpx · aiohttp · Playwright · Patchright · Puppeteer ·
curl - and anything else that takes a proxy URL, because that is all it hands
back.

## Install

```
pip install nodemaven
```

Nothing else is required. The only dependency is `tomli`, and only on Python
3.10 and older, where the standard library has no TOML parser.

<!-- The examples below are held to one rule, added 2026-09-10 after an outside
     developer installed 0.1.3 from PyPI and hit `ModuleNotFoundError: No module
     named 'requests'` on the first block of this file: **an example that imports
     something has an install line above it that installs that something.**
     `test_readme.py` checks it, over this file and over docs/. -->

## Quickstart

`login` and `password` are the **Proxy Username and Proxy Password** assigned under
Proxy Setup in the [dashboard](https://dashboard.nodemaven.com) - a separate pair from
the account you sign in with. The other option there is IP whitelisting, which needs no
credentials in the username at all; both are described in
[authentication methods](https://docs.nodemaven.com/en/articles/9979031-authentication-methods).

```python
from nodemaven import Proxy

proxy = Proxy(login="your-login", password="your-password",
              country="us", filter="medium")

print(proxy.check())
```

```
200 Connection established via gate.nodemaven.com:8080 in 0.42s, exit 203.0.113.7
```

<!-- 203.0.113.7 is RFC 5737 TEST-NET-3, reserved for documentation, so nobody
     reads it as a real exit address. The two output blocks here are compared
     against `str(Check(...))` by `test_readme.py`, word for word, after
     collapsing whitespace - so re-wrapping the prose is allowed and changing it
     is not. -->

That is one CONNECT and no traffic through the tunnel. **A refusal is a return
value, not an exception**, because the status code is the thing you came for and
raising would bury it in a traceback:

```
407 Proxy Authentication Required via gate.nodemaven.com:8080 in 0.19s
usually NOT your credentials, despite what the status says. A value the gateway
will not take on `country`, `filter`, `ttl`, `type` or `speed` answers 407, and
so does a wrong password. Check the values before the password - and check the
case of `ttl`, which is the one value that is case-sensitive: `10M` is refused
where `10m` is accepted.
```

That second paragraph is data in the gateway definition, not a string in this
library, because what a status code means is per-gateway.

`check()` tunnels to `api.ipify.org:443` by default and whatever you name will
see a TCP connection from your exit address, so the target is a parameter rather
than a constant. The timeout defaults to 15 seconds, because one of this
gateway's measured reactions is no reply for about 20 seconds.

```python
proxy.check(target="example.com:443", timeout=15.0)
```

### Sending traffic through it

The example below uses `requests`, which this package does **not** install - it
has no HTTP client of its own and does not want one. Install it alongside:

```
pip install nodemaven[requests]
```

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

Credentials can come from the environment instead, so nothing is in your source:

```python
# NODEMAVEN_LOGIN and NODEMAVEN_PASSWORD
proxy = Proxy(country="us", filter="medium")
```

### The same identity, for other clients

```python
proxy.url()          # http://user:pass@gate.nodemaven.com:8080  - httpx, aiohttp, curl
proxy.requests()     # {"http": ..., "https": ...}
proxy.httpx()        # {"http://": ..., "https://": ...}
proxy.playwright()   # {"server": ..., "username": ..., "password": ...}
proxy.username       # the username on its own
proxy.server         # host:port, no credentials
```

With Playwright, Patchright or Puppeteer:

```
pip install playwright
```

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(proxy=proxy.playwright())
```

## Why not just write the URL yourself?

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

That is the whole reason the package exists. The gateway answers a wrong *value*
five different ways and names the parameter in none of them; the table of what
it does instead, and the probes behind it, are in
[docs/validation.md](https://github.com/nodemaven/nodemaven-python/blob/main/docs/validation.md).

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
| `speed` | claims a connection speed class | `fast`, `slow` |
| `ipv4` | claims to force IPv4 | `True` |

`type` picks a different pool rather than a filter over one pool. Five requests
per arm with a fresh `sid` and `country=us`: `type=mobile` drew T-Mobile and
Verizon Wireless ASNs, while `type=residential` and leaving it unset drew
Comcast, Charter, Windstream and other wireline carriers, with no mobile ASN
among them.

**`ipv4` and `speed` are confirmed names whose effects are unmeasured**, and the
table says `claims to` for that reason.

**Names are validated. Values, on this gateway, are not.** A name outside the
table raises before anything is sent, because the gateway answers an unknown
name with 200 and drops the setting. Values are passed through, because what is
known is which ones have been *observed* to work, and that is not the same as
the set the gateway accepts - refusing on a guessed list would block a setting
that would have worked.

`country`, `region`, `city`, `isp` and `type` are folded before they are sent -
trimmed, lowered, and each remaining space turned into `_` - so `country="US"`
and `region="District of Columbia"` are not your problem:

```python
Proxy(login="u", password="p", region="District of Columbia").username
# u-region-district_of_columbia
```

`sid`, `filter`, `ttl` and `speed` keep their case, and for `ttl` that matters:
`ttl-10m` opens the tunnel and `ttl-10M` is answered `407`. Every value that is
not folded is refused if it contains whitespace.

Credentials come from `NODEMAVEN_LOGIN` and `NODEMAVEN_PASSWORD` when not passed
in, and the gateway address from `NODEMAVEN_HOST` and `NODEMAVEN_PORT`.

Which names fold, why the values are not checked against a list, and what each
wrong value is answered with, are in
[docs/validation.md](https://github.com/nodemaven/nodemaven-python/blob/main/docs/validation.md).

## Sticky sessions

One `Proxy` is one identity. Pin it to a sticky session:

```python
held = proxy.session("order4417")
```

**A session id cannot contain the character the gateway separates parameters
with**, which for this one is `-`, and passing one raises rather than
connecting. The gateway cuts the value at the separator, so without the refusal
every order id beginning `order` would quietly share one session and one exit.

**The session key is the whole parameter set, not the session id.** Adding or
removing any parameter moves you to a different exit address, which is why
parameters change through a method that returns a new object rather than by
assignment - the move is a different identity, and the code should say so:

```python
germany = proxy.replace(country="de")   # a new identity, a new exit
plain   = proxy.replace(filter=None)    # also a new identity
```

For a worker pool, one identity per worker:

```python
for identity in proxy.sessions(50):
    queue.put(identity)                 # each one a different exit
```

Each id is `2 * length` hexadecimal characters from `secrets`, `length=6` by
default, and the ids are distinct **within one call**. The measurements behind
the separator rule, and why the ids are hex rather than `uuid4()`, are in
[docs/validation.md](https://github.com/nodemaven/nodemaven-python/blob/main/docs/validation.md).

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

## Account API

Quota, usage, sub-users and the location catalogue. Separately credentialled,
because the API key and the proxy password are different secrets from different
places.

```python
from nodemaven import Client

client = Client()                       # NODEMAVEN_APIKEY from the environment
me = client.me()
print(me["data"])                       # traffic left
```

`me()` returns the server's own object with its own field names, unrenamed and
unmodelled - `data` is the traffic left and there is no `traffic_left`, and
`is_traffic_frozen` is a **string**. **It also returns your proxy password in
clear text, on every call, and so does every row of `sub_users()`.** Do not
print, log or paste either.

```python
client.countries()                      # the catalogue, paginated
client.regions(country__code="us")      # Django's field lookup, the server's spelling
client.cities(country__code="us", region__code="dc")
client.isps(country__code="us")         # a different envelope, see the docs
client.zip_codes(country__code="us")

# Which regions and cities the ISP and zip-code catalogues actually cover.
# Separate endpoints, not filters on the two above.
client.isp_regions(country__code="us")
client.isp_cities(country__code="us", region__code="dc")
client.zip_code_regions(country__code="us")
client.zip_code_cities(country__code="us", region__code="dc")

# Statistics are per proxy username, and the username is required.
# The range is `start` and `end`, not `start_date` and `end_date`, and the
# dates are `dd-mm-yyyy`. ISO is answered 400.
client.statistics_data("acct-1", start="01-09-2026", end="07-09-2026")
client.statistics_requests("acct-1", start="01-09-2026")
client.domain_statistics("acct-1", period="hours24")

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

A list endpoint returns a `Page`, which iterates **one page** and not the
collection. `iterate()` gets the rest:

```python
page = client.countries()               # one page, 1000 rows by default
for country in client.iterate(page):    # all of them
    ...
```

`page.count` is `None` everywhere, paging differs by endpoint, and one page can
be half a collection with nothing in the reply saying so. That is the API's
shape rather than a gap here, and it is measured in
[docs/observed-behavior.md](https://github.com/nodemaven/nodemaven-python/blob/main/docs/observed-behavior.md).

The gateway answers a country it does not have with `407`, which reads as a
credentials problem. The catalogue knows better, so it can be asked:

```python
problems = client.validate(proxy)
if problems:
    raise SystemExit("\n".join(problems))
```

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

Or keep the definition in a TOML file:

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
transcribed from documentation and never exercised. `available()` lists the ids
shipped here, and only `nodemaven` is one of them - it is `measured`.

## What this library does not do

**It does not retry.** Retrying a refused request is the thing that most
reliably makes the next one worse: measured over 1464 attempts, the chance the
next attempt succeeds falls from 75% with no failures behind it to 1.6% after
six, and 294 attempts spent past six failures returned three pages. A library
that shipped automatic retry as a default would be spending that on your behalf
without telling you. The table is in
[docs/observed-behavior.md](https://github.com/nodemaven/nodemaven-python/blob/main/docs/observed-behavior.md).

It also does not own an HTTP client, a connection pool or a browser. Those are
yours, and they are better than anything a vendor SDK would bundle.

## Documentation

<!-- Absolute, `blob/main`, for the same reason the logo src is absolute: on the
     PyPI page a relative `](docs/validation.md)` resolves against
     pypi.org/project/nodemaven/ and 404s there. `test_readme.py` refuses any
     relative link in this file. -->

- [API reference](https://github.com/nodemaven/nodemaven-python/blob/main/docs/api-reference.md) - every public name, what it takes and what it raises
- [Why the validation is the point](https://github.com/nodemaven/nodemaven-python/blob/main/docs/validation.md) - what the gateway answers to a wrong value, and why names are refused and values are not
- [Observed behaviour](https://github.com/nodemaven/nodemaven-python/blob/main/docs/observed-behavior.md) - the gateway and dashboard findings this package is built on, each with its run
- [CHANGELOG.md](https://github.com/nodemaven/nodemaven-python/blob/main/CHANGELOG.md) - entries carry the probe and the date behind any change to what the gateway is believed to accept
- [NodeMaven docs](https://docs.nodemaven.com?utm_source=github&utm_medium=sdk_python&utm_campaign=readme) - the product documentation

## Requirements

Python 3.9 or newer. No dependencies on 3.11 and newer; `tomli` on older ones.

## License

[MIT](https://github.com/nodemaven/nodemaven-python/blob/main/LICENSE).
