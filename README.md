# nodemaven

Build and validate proxy connection strings.

This library opens no socket. It builds the username a proxy gateway expects,
refuses the input that gateway would mishandle, and hands the result to whatever
HTTP client you already use.

```
pip install nodemaven
```

## Quickstart

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
held = proxy.session("order-4417")
```

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
