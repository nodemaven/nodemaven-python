# API reference

What every public name takes, returns and raises.

<!-- The rule this file is held to: nothing here explains a decision. Every
     "why" belongs in observed-behavior.md, in validation.md, or in the
     docstring. If a sentence here would survive the decision being reversed, it
     does not belong here.

     This was the second half of the README until 2026-09-10. It moved because
     the README had grown to 984 lines and a reader arriving from PyPI met the
     reference before the second example. Nothing was deleted in the move;
     `tests/test_readme.py` checks this file against the code exactly as it
     checked the section. -->

Nothing here needs [observed-behavior.md](observed-behavior.md) or
[validation.md](validation.md); those carry the measurements the refusals were
built on.

- [`Proxy`](#proxy)
- [`Check`](#check)
- [`Client` and `Page`](#client-and-page)
- [`Provider` and the module functions](#provider-and-the-module-functions)
- [Your own transport](#your-own-transport)

## `Proxy`

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
of your own reads its own pair.

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

## `Check`

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

`.exit_ip` is `None` more often than the definition suggests - see
[the exit address is not promised](observed-behavior.md#the-exit-address-is-not-promised).

## `Client` and `Page`

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
| `.isps()` `.isp_regions()` `.isp_cities()` | a `Page` - `isps()` has an [envelope that is not the usual one](observed-behavior.md#the-isp-catalogue-answers-a-different-shape) |
| `.statistics_data(proxy_username, **filters)` / `.statistics_requests(...)` | a `dict` |
| `.domain_statistics(proxy_username, **filters)` | a `Page` that does not page - the whole answer is one object |
| `.sub_users()` `.whitelist_ips()` | a `Page`, numbered by page rather than by offset |
| `.whitelist_ip(id)` | a `dict` |
| `.create_sub_user(username, password, *, traffic_limit=None, is_traffic_limited=None, **extra)` | a `dict` |
| `.update_sub_user(id, **changes)` / `.delete_sub_user(id)` | a `dict` |
| `.reset_sub_user_usage(ids)` | a `dict`. Takes a list, not one id |
| `.upsert_whitelist_ip(ip, ports_count, *, name=None, protocol="HTTP", sticky=None, ttl=None, **extra)` | a `dict`. Creates **or replaces**. [`protocol` is always sent](observed-behavior.md#the-whitelist-needs-a-field-the-spec-marks-optional) |
| `.delete_whitelist_ip(id)` | a `dict` |
| `.iterate(page, *, max_pages=100)` | an iterator over the rest of the collection, page by page |
| `.validate(proxy)` | a list of problem strings, empty when the catalogue agrees |

Every list call takes `**filters`, passed through as query parameters in the
server's own spelling - `country__code="us"`.

**Those filters are not validated, and this server ignores a query parameter it
does not know.** A misspelt filter is therefore accepted by Python, sent, and
dropped, with nothing anywhere saying so. The filter names the statistics
endpoints have are `proxy_username`, `timezone`, `start`, `end`, `period`,
`request_source` and `limit`.

### Paging

**It differs by endpoint and the difference is not cosmetic.** The nine location
endpoints take `limit` and `offset`, both **always sent**: `limit` defaults to
`DEFAULT_PAGE_SIZE`, 1000, and `offset` to 0. `sub_users()` takes `page` and
`per_page`; `whitelist_ips()` takes `page` and `page_size`, whose documented
default is 5 and maximum 100. An unknown query parameter is ignored rather than
refused, so one hard-coded pair would silently do nothing on two thirds of this
surface.

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

**Both page-numbered endpoints start at page 1**, and they do not mark the end
of a collection the same way - see
[paging is three conventions](observed-behavior.md#paging-is-three-conventions-not-one).

## `Provider` and the module functions

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

## Your own transport

The transport is `urllib.request` from the standard library, so the account API
adds nothing to your dependency tree. If you would rather it went through the
client you already have, that is one function. The example below is `requests`,
which this package does not install:

```
pip install nodemaven[requests]
```

```python
import requests

def transport(method, url, headers, body):
    r = requests.request(method, url, headers=headers, data=body)
    return r.status_code, r.content

client = Client(transport=transport)
```

Return the status rather than raising on it; mapping statuses to exceptions is
this library's job, and doing it in both places is how a `NotFoundError` becomes
somebody else's exception halfway up a stack.
