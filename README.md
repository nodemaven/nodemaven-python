<div align="center">

<!-- Absolute, and pointing at `nodemaven/.github`.
     Absolute, permanently: this file is the PyPI long description, and PyPI
     resolves nothing relative, so a relative src is a broken image on the package
     page no matter what this repository's visibility is. An earlier version of
     this comment ended with "switch the src to a relative path only after this
     repository is public", which contradicted the sentence above it and was
     removed on 2026-09-04 rather than acted on. Publishing changes which absolute
     URLs resolve; it does not give PyPI a base to resolve a relative one against.
     `.github`: it is public, so its raw URL answers 200 to a logged-out visitor.
     That was the whole requirement. This comment used to justify the choice with
     ".github is the org's only public repository as of 2026-08-25", which stopped
     being true - `proxy-benchmark` and `connection-checker` are public too as of
     2026-09-01 - without the choice itself becoming wrong. Moving the asset here
     is now possible and buys nothing.
     Verified with readme_renderer (the renderer PyPI itself runs): `div align`,
     `img src`, `height` and the badges all survive its sanitiser. -->
<a href="https://go.nodemaven.com/ghpython"><img src="https://raw.githubusercontent.com/nodemaven/.github/main/profile/assets/nodemaven-mark.svg" alt="NodeMaven" height="56"></a>

# nodemaven

**Builds the proxy username a gateway expects, and refuses the input it would silently drop.**

<!-- The first three read live off PyPI, so none of them can drift from the
     release. Checked 2026-08-25: v0.1.1, "3.9 | 3.10 | 3.11 | 3.12 | 3.13", MIT.
     The CI badge was absent until 2026-09-04 for a reason that has expired:
     shields.io could not see a workflow in an internal repository and rendered
     "inaccessible" on a public package page. It reads `.github/workflows/ci.yml`
     on `main`, which is where the runs are - last five green, 2026-08-25 to
     2026-08-27, and `ci.yml` confirmed as the workflow's real path.
     **The reason has not expired yet at the time of writing, and this is the
     ordering constraint for the whole commit.** Fetched 2026-09-04 while the
     repository was still internal, the badge SVG's title reads
     "tests: repo or workflow not found". This line, the LICENSE link at the
     bottom and the Source/Issues entries in pyproject.toml are all only correct
     once nodemaven/nodemaven-python is public: land them before the flip and the
     PyPI page carries a broken badge and a dead link, which is the exact thing
     the flip is supposed to fix.
     Unlike the other three badges this one CAN break by itself later: it goes red
     when the suite goes red, which is the point of having it. -->

[![pypi](https://img.shields.io/pypi/v/nodemaven?style=flat-square)](https://pypi.org/project/nodemaven/)
[![python](https://img.shields.io/pypi/pyversions/nodemaven?style=flat-square)](https://pypi.org/project/nodemaven/)
[![ci](https://img.shields.io/github/actions/workflow/status/nodemaven/nodemaven-python/ci.yml?branch=main&style=flat-square&label=tests)](https://github.com/nodemaven/nodemaven-python/actions/workflows/ci.yml)
<!-- Absolute, not `](LICENSE)`. A relative href resolves against
     pypi.org/project/nodemaven/ on the package page and 404s there; it was the one
     dead link readme_renderer showed in this file. The badge keeps pointing at
     opensource.org because it is a claim about the licence rather than about this
     repository; the file itself is linked from the License section at the bottom,
     which it could not be while the repository was internal. -->
[![license](https://img.shields.io/pypi/l/nodemaven?style=flat-square)](https://opensource.org/licenses/MIT)

[Quickstart](#quickstart) · [Sticky sessions](#sticky-sessions) · [Why the validation is the point](#why-the-validation-is-the-point) · [What it does not do](#what-this-library-does-not-do) · [Other gateways](#other-gateways) · [Docs](https://docs.nodemaven.com?utm_source=github&utm_medium=sdk_python&utm_campaign=readme)

</div>

Build and validate proxy connection strings.

This library opens no socket. It builds the username a proxy gateway expects,
refuses the input that gateway would mishandle, and hands the result to whatever
HTTP client you already use.

```
pip install nodemaven
```

## Quickstart

<!-- This paragraph exists because the snippet below is the first thing an outside
     developer runs, it opens a real socket, and `your-login` is not something they
     can guess. Without it the first result of the quickstart is a bare 407 and no
     indication of what to do about it. Both links checked 200 on 2026-08-25. -->

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

<!-- This block is here because the paragraph above used to be followed by
     "everything below except this first snippet runs without an account", which
     was true and left the wrong impression: it reads as "the live path needs us".
     It does not. A gateway is data here, so any proxy drives the same builder,
     and that is worth saying at the top rather than in the last section.
     Checked 2026-09-04 against the published 0.1.2 wheel in a clean venv, with
     NODEMAVEN_* cleared from the environment so nothing could pass by picking up
     this machine's credentials: 7 of 7, including the one-liner below, an
     encoded password, and the refusal of a parameter the definition does not
     declare. `drafts/byo_proxy_check.py`. -->

**No account? Any proxy you already have works.** A gateway is a data
description, not a code path, so one that ships no definition here goes through
the same builder and the same validation:

```python
import requests
from nodemaven import Proxy, Provider

# An empty known_params is not a stub. It says nobody has established what this
# gateway recognises, so every parameter is refused rather than sent to be
# silently dropped - see "Why the validation is the point" below.
mine = Provider(id="mine", label="My proxy", known_params=frozenset())

proxy = Proxy(provider=mine, login="your-login", password="your-password",
              host="proxy.example.com", port=8000)

r = requests.get("https://api.ipify.org", proxies=proxy.requests())
print(r.text)
```

Describe the parameters it does take and it validates those too - see
[Other gateways](#other-gateways). Everything from here to the end of that
section builds strings offline and opens no socket at all.

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

## Parameters

<!-- Added 2026-09-04. Until then the README showed `country` and `filter` in
     examples and never said what else existed, so `city`, `isp`, `ttl` and the
     rest were reachable only by reading the shipped TOML. Kept to a table on
     purpose: the reference documentation goes on the docs site, this is the
     minimum a developer needs to not have to guess.
     The right-hand column is values *measured to work*, with the date, and it is
     deliberately not called "allowed" - see the note under the table. -->

What the shipped NodeMaven definition accepts. Every name here was confirmed
against the gateway rather than transcribed:

| parameter | what it selects | values measured to work |
|---|---|---|
| `country` | country code, or `any` | `us`, `de`, ... |
| `region` | area inside the country | a name |
| `city` | city inside the country | a name |
| `isp` | the exit's ISP | a name |
| `sid` | the sticky session - see below | any string with no `-` |
| `ttl` | how long that session is held | `10m`, `1m` |
| `filter` | IP quality | `low`, `medium`, `high` (2026-08-13) |
| `speed` | connection speed class | `fast`, `slow` (2026-08-12) |
| `ipv4` | force IPv4 | `True` / `False` |

**Names are validated, values are not.** Passing a name that is not in this table
raises before anything is sent, because the gateway answers an unknown name with
200 and drops the setting. Values are passed through, because what is known is
which ones have been observed to work - and that is not the same as the set the
gateway accepts. Refusing on a guessed list would block a setting that would have
worked, which is the worse mistake of the two.

Credentials come from `NODEMAVEN_LOGIN` and `NODEMAVEN_PASSWORD` when not passed
in, and the gateway address from `NODEMAVEN_HOST` and `NODEMAVEN_PORT`.

## Errors

All four inherit from `NodeMavenError`, so one `except` catches everything this
library raises.

| exception | raised when |
|---|---|
| `ParamError` | a parameter name is unknown, a value is empty, or a value contains the gateway's separator |
| `CredentialsError` | no login, no password, or no gateway address, from arguments or environment |
| `ProviderError` | a gateway definition is missing, unreadable, or internally inconsistent |
| `NodeMavenError` | the base, never raised on its own |

Nothing here is raised from a response, because nothing here sends one. Every
failure this library reports is a failure it found before a socket existed.

## Sticky sessions

One `Proxy` is one identity. Pin it to a sticky session:

```python
held = proxy.session("order4417")
```

**A session id cannot contain the character the gateway separates parameters
with**, which for this one is `-`, and passing one raises rather than connecting.
That is measured and not a precaution: on 2026-08-20 a probe opened tunnels with
`sid-order8e3bf9-4417` and with `sid-order8e3bf9`, four rounds each, interleaved,
and both landed on **one exit address** while a third arm spelled
`sid-order8e3bf94417` held a different one throughout. The gateway cuts the value
at the separator and reads the rest as something else, so every order id
beginning `order` would quietly share one session and one exit.

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

## Why the validation is the point

A gateway is bad at telling you that you got the username wrong. Measured
against this one on 2026-08-10, seven kinds of bad input produce seven
different reactions and not one of them names the cause:

| you sent | the gateway answers |
|---|---|
| bad country | `406 Not Acceptable` |
| bad region | `406 Not Acceptable` |
| bad city | `500 Internal Server Error` |
| bad `filter` value | `407 Proxy Authentication Required` |
| bad `ttl` value | `407 Proxy Authentication Required` |
| empty value | nothing, the connection hangs about 20 s |
| **unknown parameter name** | **`200`, and the parameter is ignored** |

The two `407` replies send you to check credentials that are correct. The last
row is worse than any of them: the request succeeds, your code carries on, and
the setting you asked for was never applied. Nothing that comes back over the
wire can tell you.

So this library checks before anything is sent:

```python
>>> Proxy(login="u", password="p", contry="us")
ParamError: NodeMaven does not know the parameter 'contry': it is answered with
200 and dropped, so the connection would succeed and your setting would NOT be
applied. Known: ['city', 'country', 'filter', 'ipv4', 'isp', 'region', 'sid',
'speed', 'ttl']
```

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

<!-- Added 2026-09-04. The harness went public at some point before 2026-09-01 and
     nothing here linked it, which left the table above as a number you have to
     take on trust when it is one you can re-derive. Checked the same day:
     `gh api repos/nodemaven/proxy-benchmark --jq .visibility` says public, and its
     README carries the same 1464 - so this link resolves anonymously and lands on
     the figure, rather than on a repository that merely sounds related. -->

Those 1464 attempts, and the cells they came from, are in
[nodemaven/proxy-benchmark](https://github.com/nodemaven/proxy-benchmark) - the
harness that measured them, open source, so the table above can be re-run rather
than believed.

It also does not own an HTTP client, a connection pool or a browser. Those are
yours, and they are better than anything a vendor SDK would bundle.

## Other gateways

Parameters are data, not hardcoded keywords. A gateway is its prefix,
separators, session parameter and the set of parameter names it actually
recognises - and a definition written by you goes through the same builder and
the same validation as the one shipped here. Either build it in place, as in the
[quickstart](#quickstart), or keep it in a TOML file:

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

<!-- Absolute and `blob/main`, for the same reason the logo src is absolute: on the
     PyPI page a relative `](LICENSE)` resolves against pypi.org and 404s. This
     link could not be here at all while the repository was internal, when it 404'd
     for every anonymous visitor - added 2026-09-04 with the visibility flip. -->

[MIT](https://github.com/nodemaven/nodemaven-python/blob/main/LICENSE).
