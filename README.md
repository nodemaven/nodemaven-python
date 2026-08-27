<div align="center">

<!-- Absolute, and pointing at `nodemaven/.github` rather than at this repository,
     for two separate reasons.
     Absolute: this file is the PyPI long description, and PyPI resolves nothing
     relative - a relative src is a broken image on the package page.
     `.github`: it is the org's only public repository as of 2026-08-25, so its raw
     URL answers 200 to a logged-out visitor. This repository is internal and its
     own raw URL answers 404, measured the same day. Point the src here and the
     package page shows a broken image to everyone who is not signed in.
     Verified with readme_renderer (the renderer PyPI itself runs): `div align`,
     `img src`, `height` and the badges all survive its sanitiser.
     Switch the src to a relative path only after this repository is public. -->
<a href="https://go.nodemaven.com/ghpython"><img src="https://raw.githubusercontent.com/nodemaven/.github/main/profile/assets/nodemaven-mark.svg" alt="NodeMaven" height="56"></a>

# nodemaven

**Builds the proxy username a gateway expects, and refuses the input it would silently drop.**

<!-- All three read live off PyPI, so none of them can drift from the release.
     Checked 2026-08-25: v0.1.1, "3.9 | 3.10 | 3.11 | 3.12 | 3.13", MIT.
     No CI badge here: shields.io cannot see a workflow in an internal repository
     and would render "inaccessible" on a public package page. -->

[![pypi](https://img.shields.io/pypi/v/nodemaven?style=flat-square)](https://pypi.org/project/nodemaven/)
[![python](https://img.shields.io/pypi/pyversions/nodemaven?style=flat-square)](https://pypi.org/project/nodemaven/)
<!-- Absolute, not `](LICENSE)`. A relative href resolves against
     pypi.org/project/nodemaven/ on the package page and 404s there; it was the one
     dead link readme_renderer showed in this file. The repository's own LICENSE is
     not linkable either while the repository is internal. -->
[![license](https://img.shields.io/pypi/l/nodemaven?style=flat-square)](https://opensource.org/licenses/MIT)

[Quickstart](#quickstart) · [Sticky sessions](#sticky-sessions) · [Why the validation is the point](#why-the-validation-is-the-point) · [What it does not do](#what-this-library-does-not-do) · [Docs](https://docs.nodemaven.com?utm_source=github&utm_medium=sdk_python&utm_campaign=readme)

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

Everything below except this first snippet builds strings offline and runs without an
account.

```python
import requests
from nodemaven import Proxy

proxy = Proxy(login="your-login", password="your-password",
              country="us", filter="medium")

r = requests.get("https://api.ipify.org", proxies=proxy.requests())
print(r.text)
```

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

It also does not own an HTTP client, a connection pool or a browser. Those are
yours, and they are better than anything a vendor SDK would bundle.

## Other gateways

Parameters are data, not hardcoded keywords. A gateway is one TOML file - its
prefix, separators, session parameter and the set of parameter names it actually
recognises - and a definition read from disk goes through the same builder and
the same validation as the one shipped here:

```python
from nodemaven import Proxy, load_file

mine = load_file("my-gateway.toml")
proxy = Proxy(provider=mine, login="u", password="p", country="us")
```

Every definition carries a `status`. `measured` means traffic has gone through
that gateway and the dialect was read off the wire. `documented` means it was
transcribed from documentation and never exercised. Only `nodemaven` is shipped
here, and it is `measured`.

## Requirements

Python 3.9 or newer. No dependencies on 3.11 and newer; `tomli` on older ones.

## License

MIT.
