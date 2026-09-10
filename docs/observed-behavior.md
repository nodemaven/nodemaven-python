# Observed behaviour

<!-- What this file is for: anything about the gateway or the dashboard API that
     was measured rather than transcribed, and that a caller only meets at
     runtime. It was spread through the README until 2026-09-10.

     The house rule it is written under: a claim carries the date and the run it
     came from, a control is named along with what it varied and what it
     silently held fixed, and a claim that did not survive replication is left
     standing next to its correction. -->

The gateway and the dashboard API both answer in ways no client can guess. Each
finding below is a run, not a reading of the vendor's documentation - where the
two disagree, which happens often, the run is what this package is built on.

- [The exit address is not promised](#the-exit-address-is-not-promised)
- [A wrong path is not answered 404](#a-wrong-path-is-not-answered-404)
- [What `me()` actually returns](#what-me-actually-returns)
- [Statistics dates are `dd-mm-yyyy`](#statistics-dates-are-dd-mm-yyyy)
- [Paging is three conventions, not one](#paging-is-three-conventions-not-one)
- [The ISP catalogue answers a different shape](#the-isp-catalogue-answers-a-different-shape)
- [The whitelist needs a field the spec marks optional](#the-whitelist-needs-a-field-the-spec-marks-optional)
- [What the catalogue can and cannot check](#what-the-catalogue-can-and-cannot-check)
- [Why there is no automatic retry](#why-there-is-no-automatic-retry)

## The exit address is not promised

The exit address arrives **on the CONNECT reply itself**, on a header the
gateway definition names, so knowing where you came out costs one handshake and
no traffic through the tunnel.

**Do not build anything on it being there.** More than one implementation
answers behind this hostname, which one you reach is decided by your username,
and they do not agree about the header: one measured `200` carried `X-Exit-IP`
where the shipped definition names `X-Proxy-Exit-IP`, and others send no address
at all. So `result.exit_ip` is `None` more often than the definition suggests,
and that is normal rather than an error. If you need the address every time,
read it through the tunnel from a service that echoes it.

**`ok` does not mean your parameters were applied.** An unrecognised parameter
name is answered `200` and dropped, which is why unknown names are refused
before anything is sent - see [validation.md](validation.md). No call can
recover that after the fact, and `check()` does not pretend to.

The timeout defaults to 15 seconds rather than something brisk, because one of
this gateway's measured reactions is no reply for about 20 seconds. A 5-second
timeout would report that as a network problem.

## A wrong path is not answered 404

Measured 2026-09-09. `locations/zip-codes/`, `statistics/` and
`whitelist-ips/` - three paths this package sent before the vendor's OpenAPI
specification was read - are answered `200`, `text/html`, 6415 bytes,
byte-identical to a path invented on the spot as a negative control. The
dashboard serves its front end for anything it does not route, so **calling a
path cannot tell you whether the path exists.** If you wrap a path of your own
against this API, compare its response against a path nobody could have
implemented rather than against a status code.

This is the same defect as the gateway answering `200` to an unknown username
parameter and dropping it, one layer up.

The real paths are `locations/zipcodes/` (solid, no separator),
`statistics/data/`, `statistics/requests/`, `statistics/domains/` and
`whitelist/ips`. `sub-users/` was real all along but was being read under
`results`, where the rows are under `payload`.

**Every path this package uses now comes from the vendor's own OpenAPI
specification**, read 2026-09-09. What has also been *sent* is more than the
paths: `users/me`, `countries`, `regions`, `cities` and `isps` were measured
2026-09-08, and all five wrapped write calls were measured 2026-09-09 against a
throwaway sub-user and an RFC 5737 address, both removed in the same run. The
rest are transcribed - from the specification now rather than from the vendor's
client at `github.com/nodemavencom/proxy`, `python/nodemaven/client.py`, where
four paths were wrong.

**The specification is documentation and gets no more authority than the
vendor's client did.** Its `info.description` names a host, `api.nodemaven.com`,
that answers 404 at nginx, and four of the five writes answered something it does
not declare: `create` answers `201` where its path declares only `200`,
`reset/usage` answers an array where every other envelope here carries an
object, `delete` answers `200` with a body where the document declares `204`,
and the whitelist upsert is refused when sent exactly the fields its own schema
marks required.

Five of the vendor's twenty-four documented paths are deliberately not wrapped:
`locations/all-doc/`, `notifications/`, `llm/submit/`, `llm/results/{id}/` and
`llm/balance/`. Listing them is the point - an omission nobody wrote down reads
the same as an oversight.

## What `me()` actually returns

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

**`me()` returns a live proxy password, and `sub_users()` returns one per row**,
by the specification's own required-field list. Do not print a row of either,
do not log one, and do not paste one into an issue. One reached a console here
on 2026-09-09 and had to be rotated.

## Statistics dates are `dd-mm-yyyy`

Measured 2026-09-09 by `--phase 10`: `start=20-08-2026` is answered **200 with
21 data points** and `start=2026-08-20` is answered **400**, with a body
byte-identical to the one `start=not-a-date` draws. The vendor's document writes
the format both ways - `dd-mm-yyyy` in the prose, `format: date` in the type -
and **the prose is the half that is right**. So ISO is not a rival spelling the
server declines, it is a string the server cannot parse, and every client
generated from that specification sends the one form that fails.

This paragraph said the opposite until 2026-09-09, and said it for the worst
possible reason: "the type is what the server parses" was an inference about
which half of a self-contradicting document to trust, written before either half
had been sent. The measurement cost one request.

All three statistics endpoints answer **500** - not 400 - when `start`, `end`
and `period` are all omitted, though the document marks all three optional. So
`domain_statistics("acct-1")` on its own is an example of a 500. `period` takes
`today` or `hours24`.

## Paging is three conventions, not one

`limit`/`offset` on the nine location endpoints, `page`/`per_page` on
`sub_users()`, `page`/`page_size` on `whitelist_ips()`. An unknown query
parameter is ignored rather than refused, so a single hard-coded pair silently
did nothing on two thirds of this surface until 2026-09-09.

`limit` and `offset` are sent on your behalf rather than omitted because
`isps()` **refuses** a request without them, while the others answer one with a
silently partial list. `offset` is honoured: `offset=50` returns rows disjoint
from `offset=0`, and an offset past the end answers `200` with zero rows.

**`iterate()` stops on an empty page, not on a short one.** That rule changed on
2026-09-09 and the one before it was unsafe against this server in particular:
it stopped at the first page shorter than the size it had asked for, which is
wrong wherever the server caps the size below the request. `cities(limit=10000)`
is answered with 1000 rows out of 1965, and "shorter than asked" reads those
1000 as the end. The measurement that says so was already written down in this
package's own documentation - a measurement sitting in a document is not a
measurement anyone applied. Stopping on empty costs one spare request per walk
and cannot truncate.

**`page.count` is `None` everywhere, and that is the API's shape rather than a
gap here.** No schema in the vendor's specification declares a `count` or a
`next` at all - `PaginatedCountryList` is `{"results": [...]}` and nothing else -
and a page of 50 drawn from a catalogue of nearly 200 countries came back with
all three fields empty. A full page is therefore indistinguishable from a
complete collection by looking at it, so `iterate()` asks for the next cursor
and reads the answer.

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

## The ISP catalogue answers a different shape

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
server does not send got into its documentation. The fix waited for one command,
and was the same edit either way.

## The whitelist needs a field the spec marks optional

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

The success body is `{"ip_id", "message"}` and **neither key is documented** -
the path binds `200` and `201` to a schema whose only property is `message` -
and the identifier is `ip_id` where the listing calls the same value `id`.

Two things that run did not settle: `name` was present in every rung, so whether
it is also required is untested, and no rung tried `ip`, `ports_count` and
`protocol` alone, so that trio is not known to be a complete body.

An earlier version of this section said only that the required pair was refused
and that which field was short was the server's word. That was accurate and it
was one call away from being a measurement.

## What the catalogue can and cannot check

`Client.validate(proxy)` checks two things. `country` is matched against the
catalogue, and **a `city` sent without a `region` is refused before the request
goes out** - that one needs no network.

The values of `region`, `city` and `isp` are **not** matched against the
catalogue, because city codes repeat across regions - `aberdeen`, `albany` and
`alexandria` each appear twice in a single page - so matching a bare code would
report success and mean nothing.

This is a method on `Client` and not a check inside `Proxy`, for one reason: a
refusal that ships in a release can be wrong forever, and the catalogue moves.
Asking the live catalogue cannot go stale - and it costs a network call, so it
has to be your decision rather than a hidden one.

## Why there is no automatic retry

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
