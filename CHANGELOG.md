# Changelog

Written against the tags and the PyPI upload records rather than from memory, on
2026-09-04. Release times are UTC as PyPI recorded them.

A note on how entries here are worded, because it is the same rule the library
itself is built on: a change to what the gateway is believed to accept carries
the probe that established it and the date it was run. "The vendor's documentation
says so" is not one of those, and an entry that rests on it says so outright.

## 0.1.4 - 2026-09-10

A patch release, and it exists because **the fix does not reach anyone without
one**. The bug was reported against the README on the PyPI project page, and
both halves of the fix - the long description and the extra - travel with a
release and never with a push. Measured the same day, before this was cut:
`pypi.org/pypi/nodemaven/json` reported `provides_extras: None` and
`requires_dist: ['tomli>=1.1.0; python_version < "3.11"']` while the merged tree
had already declared the extra.

That is the same rule 0.1.3 proved in the other direction: `Source` and `Issues`
sat in `pyproject.toml` from 0.1.1, the repository went public on 2026-09-08,
and they reached the project page only when 0.1.3 shipped a day later.

**On the number.** `0.1.3.2` was considered and is valid - PEP 440 allows a
four-component release segment, `packaging.Version` accepts it, and it sorts
`0.1.3 < 0.1.3.post1 < 0.1.3.1 < 0.1.3.2 < 0.1.4`. It was rejected because the
third component already *is* the "small fix, nothing broken" signal, and no
convention exists that reads a fourth as "smaller than a patch": an unfamiliar
number does not communicate insignificance, it spends a reader's attention on
the versioning scheme. `0.1.3.post1` was rejected on the spec rather than on
taste - PEP 440 reserves post-releases for corrections that do **not** affect
the distributed software, and this one adds an installable extra.

### `pip install nodemaven[requests]`

The quickstart imported `requests` and `pip install nodemaven` did not install
it. Reported on 2026-09-10 by an outside developer reading 0.1.3 from PyPI, and
reproduced the same day in a clean venv holding only `nodemaven==0.1.3`:
`import requests` after the documented install is a `ModuleNotFoundError`, which
is the first thing that happens to anyone who copies the README.

The fix is an optional extra, declared in `[project.optional-dependencies]`, and
**`requests` is still not a dependency of this package** - `grep -rn "import
requests" src/` finds nothing, and it will go on finding nothing.
`Proxy.requests()` is a dict of strings and `check.connect()` writes its own
CONNECT by hand, for the reason under 0.1.3 below: an HTTP library throws away
the status line, the reason phrase and the headers, which on this gateway are
the diagnosis. Making `requests` a hard dependency would have cost the one
property that separates this package from the vendor's own client, to fix one
code block.

Two things worth keeping from how the fix was chosen. `pip install requirements`
was considered and does not exist - `pypi.org/pypi/requirements/json` answers
**404**, measured 2026-09-10, so that spelling breaks a step earlier with a less
legible error - and `-r requirements.txt` names a file that an installer coming
from PyPI never has. And **an undeclared extra is not an error**: pip answers
`nodemaven[nosuchthing]` with a warning and installs the package without it, so
the documented line would have gone on failing while the README looked fixed.
That is why `test_readme.py` now reads `pyproject.toml` and asserts every extra
the documentation names is declared.

`test_every_third_party_import_is_named_in_an_install_line` is the general
version: every `import` in every Python block in every document this suite
checks has to be either the standard library, `nodemaven` itself, or named in a
`pip install` line in the same file. It is what would have caught this before
the release rather than after it.

### The README was split, and nothing in it was deleted

984 lines, over half of them reference and measurement, so a reader arriving
from PyPI met the API reference before the second example. The measurements
moved rather than shrank - the argument they make only works at full length, and
summarising a measurement turns it into an opinion:

- [`docs/api-reference.md`](https://github.com/nodemaven/nodemaven-python/blob/main/docs/api-reference.md)
  - what every public name takes, returns and raises.
- [`docs/validation.md`](https://github.com/nodemaven/nodemaven-python/blob/main/docs/validation.md)
  - the five status codes a wrong value comes back as, the fold list, why a
  separator is refused, why session ids are hexadecimal.
- [`docs/observed-behavior.md`](https://github.com/nodemaven/nodemaven-python/blob/main/docs/observed-behavior.md)
  - what the account API does that its own specification does not say.

Every link out of the README is absolute and points at `blob/main`, because
**PyPI resolves nothing relative**: a `](docs/validation.md)` resolves against
`pypi.org/project/nodemaven/` and 404s there, which is a production link going
nowhere. That rule was written in three HTML comments in the README and enforced
by nobody; it is now two tests.

**The split is the moment those tests were most likely to stop testing
anything.** Every one of them scanned `README.md` by name, and content moving
out from under a by-name scan is exactly the shape a test takes when it goes
green for the wrong reason. So `test_readme.py` now names its corpus rather than
globbing it - a new file under `docs/` fails the suite until somebody decides
what checks it is owed - the per-file checks say which file they mean, and every
scan asserts it found something first. Each new test was checked by breaking
what it guards and confirming it fails: renaming the extra, removing the install
line, making a link relative, deleting a `docs/` link, and renaming a
` ```python ` fence to ` ```py `.

### `api.py`'s module docstring was wrong, and shipped that way in 0.1.3

Its "What is still not measured" block said the six write endpoints had never
been called and that the page-number base was unknown. Both had been settled on
2026-09-09, by `--phase 11` and `--phase 9`, whose findings are written into the
method docstrings **of the same file** - `Paging.first_cursor` has carried the
page base since, and `_refuse_unnumbered` was deleted with it.

Corrected in place with the note, because the failure is worth more than the
correction: a module docstring is a summary of the module and reads as the
authoritative statement of what is known, so it was believed over the code it
summarises. The check is `grep` in the source and it was not run.

## 0.1.3 - 2026-09-09 17:42

Uploaded by `publish.yml` through PyPI Trusted Publishing, from the `v0.1.3`
tag and a published GitHub Release. The publisher on the artifact reads
`nodemaven/nodemaven-python`, workflow `publish.yml`, environment `pypi`; no
token was involved. Wheel 84703 bytes, sdist 155513.

**This is the first release since the repository went public**, so `Source` and
`Issues` reach the PyPI project page for the first time. They have been in
`pyproject.toml` since 0.1.1 and were invisible for two versions, because
project metadata travels with a release and never with a visibility flip.

This heading said `not released yet` for the twenty minutes between the version
bump and the upload, with a paragraph under it explaining that PyPI still served
0.1.2 and that the two trees were different libraries. That was true when
written and false the moment the workflow finished. It is recorded rather than
quietly replaced because it is the same failure this project keeps logging: a
dated claim carried past its date. Twenty minutes is the shortest any of them
has lived, and the lifetime is not the point - the check is, and it is one
request that cannot go stale: `pypi.org/pypi/nodemaven/json` states the version
PyPI is actually serving.

### The library opens sockets now, and the README said it did not

Two calls reach the network and neither of them runs on import: `proxy.check()`
opens one CONNECT to the gateway, and `nodemaven.Client()` talks to the
dashboard API. Everything that was in 0.1.2 still opens nothing - `Proxy` builds
a string and hands it to whatever client you already have.

- **`proxy.check()`, and `Check`, `CheckError`.** One CONNECT to the gateway,
  the reply read and handed back whole: `status`, the reason phrase verbatim,
  every header, the elapsed seconds, the exit address when the gateway sends
  one, and the gateway's own explanation of that status. `ok` is `status == 200`
  and nothing more.

  **A refusal is a return value, not an exception.** A 407 is the gateway
  answering the question, so it comes back as a `Check`. `CheckError` is raised
  only when *nothing came back* - DNS, a refused connection, a timeout, or a
  first line that is not a status line.

  The CONNECT is hand-rolled rather than delegated, and the reason is what an
  HTTP library does to the diagnosis. `requests` reports a failed tunnel as
  `ProxyError('Unable to connect to proxy', OSError('Tunnel connection failed:
  407 Proxy Authentication Required'))`: the status survives as text inside a
  nested exception, and the reason phrase and every header are gone. This
  package exists to tell a caller which of seven inputs was wrong, and it cannot
  do that from a string it has to parse back out of an error message.

  Three details that are decisions rather than defaults. The response head is
  decoded **latin-1, never utf-8**, because a header value is bytes by
  specification and a gateway may put anything in a reason phrase - utf-8 would
  raise on a byte a proxy is entitled to send, turning a readable diagnosis into
  a decode error. `timeout` defaults to **15 seconds** because one of the seven
  measured reactions is *no reply for about 20 s*, and a 5 s default would
  report it as a network problem. And there is no null CONNECT, so the target is
  a parameter on every entry point rather than a constant: whatever is named
  sees a real TCP connection from the exit address. It defaults to
  `api.ipify.org:443`, port 443 because a gateway may treat plaintext
  differently.

  **`ok` does not mean your parameters were applied**, and `check()` does not
  pretend otherwise. An unrecognised parameter name is answered 200 and dropped,
  which is why this package refuses unknown names before sending; no reply can
  recover that afterwards.

- **Three uncaught exceptions in `check()` and one cross-language divergence,
  all found by porting the module to Rust.** None is reachable from a correct
  call and all four are reachable from a typo, which is the population this
  module exists for.

  `str.isdigit()` gated both the status code and the port, and it is not a test
  for "a number I can hand to C". It is True for the latin-1 superscripts
  U+00B9, U+00B2 and U+00B3, where `int()` raises `ValueError` - so
  `check(server="127.0.0.1:\xb2")` raised `ValueError` instead of the
  `CheckError` this module promises. It is also True for a digit string of any
  length, where `int()` succeeds and the socket layer raises `OverflowError` -
  which derives from `ArithmeticError` and **not** `OSError`, so it walks past
  the `except OSError` whose entire job is turning socket-layer failures into
  `CheckError`. Both gates are now a spelled-out ASCII-digit comparison, the
  port is length-bounded before `int()` sees it, and **port 0 is refused by
  name** rather than left to a platform-specific errno - Windows answers
  WinError 10049 and Linux ECONNREFUSED for the same input, and neither says
  what is wrong.

  Response header names were folded with `str.lower()`, which is Unicode-aware.
  The head is decoded latin-1 on purpose, so byte `0xC0` arrives as U+00C0;
  Python folds it to U+00E0 and Rust's `to_ascii_lowercase` does not, and the
  two SDKs would key one response two ways. RFC 9110 makes a field name a token
  and a token is ASCII, so ASCII-only is the correct fold rather than merely the
  portable one. Not reachable through this gateway, which sends ASCII header
  names; reachable through one that does not.

  Recorded as a method and not as three bugs: **writing the port is the review.**
  Four of the defects fixed in this release were found by reimplementing code
  that already had a passing test suite, because a second language does not
  share the first one's assumptions about what its own standard library means.

- **`check()` could not report a single refusal from the live gateway, because
  it required CRLF framing.** Measured 2026-09-08 against
  `gate.nodemaven.com:8080` with a raw byte dump: this gateway frames a 200 with
  CRLF and frames **every refusal - 406, 407, 500 - with a bare LF**, and each
  refusal carries `Connection: close`. A reader that ends a head only at
  `\r\n\r\n` therefore saw the peer hang up with no blank line, called it a
  truncated head, and raised - so the 407 and 406 a caller most needs to see were
  the two statuses this module could not return.

  A head now ends at any of the four spellings of a blank line - `\r\n\r\n`,
  `\n\n`, `\r\n\n`, `\n\r\n` - and lines are split on LF with one optional
  preceding CR stripped. RFC 9112 section 2.2 permits exactly this: a recipient
  may recognise a single LF as a line terminator and ignore any preceding CR. A
  CR anywhere else in a line stays in the value. The request this client *sends*
  is unchanged and still CRLF.

  **The truncation guard is unchanged**: a head that stops without its blank
  line, LF-framed or not, is still refused rather than reported as an answer.
  Both halves are pinned by tests replaying the gateway's exact bytes.

- **`connect_reactions` in the provider schema** - the gateway's own reading of
  its status codes, as data. A status code on this gateway is not a diagnosis.
  Measured 2026-09-08 by raw CONNECT: a value the gateway will not take on
  `country`, `filter`, `ttl`, `type` or `speed` is answered **407**, which sends
  the caller to check credentials that are correct, and so is a wrong password.
  `check()` prints the gateway's own sentence next to the code. The translation
  is per-gateway dialect, so it belongs in the TOML beside the separators and not
  in Python.

  Five statuses are described - 200, 406, 407, 410, 500 - and the table is
  exactly as long as the measurements. **Three of the entries report an ambiguity
  rather than a diagnosis, on purpose.** `406` answers a bad `region`, a bad
  `isp` and `charter` - a real ISP - alike, so it says neither which of the two
  parameters was refused nor whether the name is unknown or merely unavailable.
  `410` came from one value, `comcast`, and reads as a name the gateway knows
  and a pool the account cannot reach, so the entry states its sample rather
  than a rule. An entry that named a cause where none was measured would be this
  package inventing the diagnosis it exists to stop the gateway inventing. A
  regression test pins each of them so they cannot be tidied into confident
  sentences later.

  **The `city` entry went through two corrections in one day and the second one
  reversed it.** It first said `500` meant no `city` was reachable at all on the
  account, on seven values - six real US cities and a junk one. That was
  narrowed the same morning to "every `city` tried", because `locations/cities`
  answers normally on the same account, so the values existed and were not
  misspelt, and a `500` is the server reporting that *it* broke rather than that
  the input was wrong. The narrowing named the run that would settle it: a
  catalogue city sent with its own country and region.

  That run happened, and `city` **works**. `probe_gateway_city_from_catalogue.py`,
  2026-09-08, six CONNECTs holding the login, the password, the target, the
  gateway host and port and the parameter order fixed:
  `us`/`louisiana`/`abbeville` answers `200`, a second city in a second region
  answers `200`, the same city with the `region` removed answers `500`, and an
  invented name with a real region answers `406`. So `500` is `city` without
  `region`, `406` is a city the gateway does not hold, and the gateway does look
  the name up.

  What the mistake looked like from the inside: all seven earlier values were
  sent as `country` + `city`, with no `region` - one line in one probe, held
  fixed across every arm, and therefore invisible in the comparison between
  them. The arms varied the city and agreed, which reads as evidence about
  cities. **A control names what it varied and what it silently held fixed**, and
  the thing held fixed was the cause. The first wording was wrong about the
  gateway; the second was honest about its own limits and still could not see
  this, because narrowing a claim does not find a confound.

  Keys are the status as a **string**, because TOML has no integer keys and
  neither does JSON, and the golden vectors are JSON.

  This is the **third key added to the schema before the vectors freeze**, after
  `values` and `normalize`, and the arithmetic is the same one this file already
  records: one edit now, a migration in four repositories later.

- **Four places said a bad `country` gives 406. It gives 407.** Measured
  2026-09-08. Three were in `api.py` - a comment, a docstring and a live error
  message - and one was in the README's status list, so
  `Client.validate(proxy)` told a caller to expect a status the gateway does not
  send for that input - and the status it does send is the one the same page
  calls actively misleading. Corrected everywhere, and `ttl` case-sensitivity is
  now documented with it: `ttl-10m` opens the tunnel and `ttl-10M` is answered
  407, which is the one value on this gateway whose case matters.

  A dated mapping from reason phrases to causes has been **removed rather than
  annotated**, because a later raw dump did not reproduce it. The README's
  exit-address paragraph now says what is true instead: more than one
  implementation answers behind this hostname, which one you reach is decided by
  your username, and they disagree about the header name - so `Check.exit_ip`
  being `None` is normal rather than an error.

- **The session key is the parsed set, and parameter order does not reach it.**
  Measured 2026-09-08, 20 rounds a side: the canonical parameter order and a
  shuffled one each drew the same single exit 20 times, while a control
  differing by one parameter *value* drew a different exit 20 times. Until now
  the shipped note said the key is the whole parameter set, measured 2026-08-10,
  and said nothing about order - so emitting parameters in a fixed order was an
  untested assumption underneath every username this library builds. It is now
  measured, and the golden vectors may pin call order across the SDKs without
  pinning a behaviour that could change which exit a caller gets.

  **The instrument was changed before the run and that is the load-bearing
  part.** An earlier 4-round attempt read some arms from the CONNECT response's
  `X-Proxy-Exit-IP` header and others from an echo service. More than one
  implementation answers behind this hostname, which one you reach is decided by
  the username, and probe arms differ by username *by construction* - so that
  design compared two instruments and attributed the difference to the
  parameter. Every round now reads the exit from an echo service. The cost is
  named rather than hidden: the probe depends on a third-party host being up,
  and that host's own 503s and timeouts appear in the rows looking like gateway
  answers. Instrument agreement was 59 of 59 usable rounds.

- **`Proxy.sessions(n)`** - `n` proxies differing only in session id. The ids are
  hex from `secrets`, and both halves of that are load-bearing. Hex because a
  value containing the gateway's separator is cut and every id sharing a prefix
  collapses onto one exit, measured 2026-08-20 - `secrets.token_urlsafe` emits
  `-` and `_`, `uuid4()` emits `-`, base64 emits `+` and `/`, and all three
  would produce that silently. `secrets` and not `random` because `random` is
  clock-seeded, so two workers starting in the same millisecond would draw the
  same ids and share one exit while looking like two.

- **`Client`: the dashboard REST API.** `me()`, the location catalogue
  (`countries`, `regions`, `cities`, `isps`, `zip_codes`), `statistics`,
  `domain_statistics`, sub-user CRUD, and the IP whitelist. `Page` and
  `iterate()` for the paginated ones.

  **Four of the calls have now been exercised against the live API and the rest
  have not.** Every path, filter name, header form and environment variable was
  read out of the vendor's own client - `github.com/nodemavencom/proxy`,
  `python/nodemaven/client.py`, read 2026-09-07 - and on 2026-09-08 `users/me`,
  `countries`, `regions` and `cities` were sent to the live API from the user's
  own connection, this machine routing through a VPN gateway. Everything else
  here is still documented rather than measured, in exactly the sense the
  provider schema's `status` field means.

  It is not the mistake `norotate` was, and the difference is categorical rather
  than a matter of degree: a wrong **API path** is answered 404, loudly, and
  corrects itself the first time anybody runs it. A wrong **gateway parameter**
  is answered 200 and dropped, and nothing ever corrects it. Reading a vendor
  file is an acceptable source for the first and was not for the second.

  Two details worth carrying. The auth header is `Authorization: x-api-key
  <key>`, which is unusual and is what the server wants - measured 2026-09-08,
  that form answers 200 while `Authorization: Bearer <key>` and the conventional
  `X-API-Key` header are both answered 403. And `me()` returns the raw dict: a
  dataclass is a claim about field names, and the live response is why that
  restraint paid. It answers six fields - `data`, `email`, `is_traffic_frozen`,
  `proxy_password`, `proxy_username`, `subscription_status`. A dataclass written
  a day earlier from the vendor's client would have declared `traffic_left`,
  which does not exist, and typed `is_traffic_frozen` as a bool, where the server
  sends a string. The raw dict was wrong about nothing, because it claimed
  nothing.

  **The pagination shape was inference, it was marked as such in the code, and
  the live API answered something else.** `limit`/`offset` with `country__code`
  is Django REST Framework, whose `LimitOffsetPagination` answers
  `{"count", "next", "previous", "results"}`; that was a strong inference from
  the vendor's own parameter names, and `_page()` was written to accept a
  paginated object, a bare list, a single object and an empty object rather than
  to assume it. `page.count`, `.next` and `.previous` are all `None` on every
  endpoint reached so far.

  This entry said until later the same day that `countries`, `regions` and
  `cities` reply with a **bare JSON array**, and that the branch the inference
  did not predict was the one that runs. **Both halves were wrong**, measured
  2026-09-08 by `probe_catalogue_paging.py`: all three answer with the
  **envelope**, and it is the DRF-shaped branch that runs. What the mistake
  looked like from the inside: the run that produced it printed `page.count` and
  nothing else about the shape, and `count` is `None` for a bare array *and* for
  an envelope that does not fill it. One reading fitted the single number that
  was on the screen, and it was written down as a measurement in eight files.
  The instrument, not the reasoning, was the fault - the second probe prints the
  shape and the question closes in one line.

  The branch that really does run and was never predicted is the single-object
  one: `locations/isps` answers 200 with an object carrying no `results` key at
  all, so `_page()` wraps it as one row that is not a row. Its contents were not
  printed and the endpoint is still unread.

  What survives the correction, and is the reason the code kept working through
  it: `_page()` accepts four shapes because the inference was marked as an
  inference, not because anything suggested a specific alternative. That habit
  has now paid twice in opposite directions.

- **`_list` sends `limit` and `offset` on every list call, and `iterate()` walks
  by offset when there is no `next`.** Two defects, one measurement,
  2026-09-08.

  `isps()` was broken outright: `locations/isps` **refuses** a request that
  omits `limit` and `offset`. The other three location endpoints answer such a
  request with exactly 50 rows and no reported total - which is byte-for-byte
  what a complete collection looks like. That is the worse of the two failures.
  A refusal is visible on the first call; a silent truncation at 50 is a caller
  quietly building on a fraction of the catalogue with no way to detect it from
  the response. Both are fixed by always sending `DEFAULT_PAGE_SIZE` and
  `offset = 0`, which the caller can override.

  **`DEFAULT_PAGE_SIZE` is 1000**, raised from 50 later the same day once the
  server's own answer had been measured rather than guessed. 1000 is the largest
  value all five list endpoints accept: `limit=10000` is refused with 400 by
  `isps`, and on `cities` it returns exactly the same 1000 rows `limit=1000`
  does. At 1000 the whole country catalogue (192 rows) and a country's regions
  (51) arrive in one request each.

  That `cities` result was written up here, in `api.py` and in the README as a
  **ceiling** - "cut back without being reported, the original failure one order
  of magnitude further out". It was not evidence of one, and all three files
  withdrew the word: a ceiling at 1000 and a US city collection exactly 1000
  rows long make arms C and D agree for different reasons, and both arms asked
  for more than they got, so neither could see the difference.

  **Arm `limit=1000&offset=1000` was then run and the ceiling is real.** It
  returns a further 965 rows, so US cities number 1965 and 1000 is a hard server
  limit. The withdrawn sentence was true. It was still right to withdraw it: it
  had been resting on two arms that could not carry it, and it came back only
  because the third arm was run. **Being right by luck is not being justified**,
  and the version that ships now names the arm rather than the guess.

  The consequence for callers is the one the withdrawn sentence predicted.
  `cities(country__code="us")` returns 1000 of 1965 rows and nothing in the
  answer says so - raising the default from 50 moved that failure one order of
  magnitude out rather than removing it. `iterate()` is the call that returns
  the collection, and `cities()` is documented as a page.

  `iterate()` previously followed `next` and stopped when there was none, so on
  this API it yielded one page and called it the collection - the README said it
  walked pages, and it did not. It now records the call a `Page` came from, in
  `Page.request_path` and `Page.request_params`, and asks for `offset + limit`
  until a page comes back shorter than the limit.

  **That walk is an inference and it carries a guard rather than a comment.**
  The server was measured to *require* `limit` and `offset`, never to *honour*
  them across pages, and those are different claims. A server that accepts
  `offset` and ignores it would hand back the same rows a hundred times and
  `iterate()` would call it a collection - so a page identical to the one before
  it raises `ApiError` naming that cause. This is the pattern the `norotate`
  correction in 0.1.2 was about, applied before the fact: where a parameter is
  accepted with no observable effect, the code must be able to tell "honoured"
  from "swallowed", and here it is the only thing standing between an inference
  and a wrong collection. The inference has since been confirmed on `countries`,
  `regions` and `cities` - `offset=50` returns rows disjoint from `offset=0` -
  and never on `isps`, so the guard stays.

  **The first version of that walk carried a defect that a test caught, and the
  fix for it was a second defect that only a measurement caught.** A `Page.
  enveloped` flag was added on the reasoning that a `next` of `None` means two
  opposite things: inside a paging envelope the server is saying the collection
  ended, and in a bare array it is saying nothing, because there is no `next`
  field to carry a value. That reasoning is sound and the flag was wrong anyway,
  because the shape it was told apart from does not exist here - every location
  endpoint is enveloped, so gating on the flag would have stopped every
  catalogue read after one page. The exact truncation the whole entry is about,
  reintroduced by the fix for it.

  Two things made it possible and both are worth naming. The test that
  prompted the flag was written against a **hand-made** DRF envelope carrying a
  real `count`; it was pinning an inferred shape, so it could only ever confirm
  the inference. And the live envelope reports **no `count`** on a page of 50
  out of 194 - so its paging fields are not being filled, and an empty `next`
  beside an empty `count` is absence rather than an answer.

  `Page.enveloped` is gone. The rule is now shape-independent: no `next` url to
  follow means step by offset, and a page shorter than the limit asked for is
  the end. Whether the envelope even carries a `next` key has not been printed,
  and this rule is correct either way - which is the property that was missing
  from the version that had to guess right.

- **Zero required dependencies still, and no async.** The API client is
  `urllib.request` from the standard library. An SDK that pulled in an HTTP
  client would dictate one to a caller who already has one, and these calls
  happen once at start-up. `Client(transport=...)` is the seam: four arguments,
  no `timeout`, so async or your own session goes there if it is ever asked for.

  `ProxyHandler({})` in the default transport is load-bearing rather than
  decorative. Left out, `urlopen` reads `http_proxy` and `https_proxy` from the
  environment - set on precisely the machines that use proxies - and an API call
  would route through a proxy nobody asked for. Pinned by a test that reads the
  source.

- **`Client.validate(proxy)` asks the live catalogue, and the catalogue is
  deliberately not frozen into the `values` table.** The data that would fill
  that table exists in the product, which is what the note under "Values are not
  validated" was missing. It is still not shipped: a snapshot of the countries
  list is a false refusal waiting for the day a country is added, and a false
  refusal with our name on the error is worse than the gap. So the check is a
  network call, which makes it the caller's decision, which is why it is a method
  on `Client` and not something `Proxy` does behind your back.

  It also refuses a `city` sent without a `region`, which needs no network at
  all. Measured 2026-09-08, that combination is answered `500` while the same
  city with its region opens the tunnel - a shipped validation rule wearing the
  status code of a server fault. It lives here rather than in `Proxy` for the
  same reason as the rest: `Client.validate()` is the caller's call to make and
  can be wrong without shipping the wrongness into a release.

- **Five error classes, because the taxonomy crosses languages.** `CheckError`,
  `ApiError`, `AuthError`, `NotFoundError`, `RateLimitError`, all under
  `NodeMavenError`. A class exists only where a caller would plausibly write
  different code for it: 401 means fix your key, 429 means wait, a 404 from CRUD
  means the row is gone. A 400 means fix your program and there is nothing to
  branch on, so it stays on the base `ApiError`.

  Two credentials, two classes, and they are not interchangeable.
  `CredentialsError` is the **proxy** login and is raised before anything is
  sent. `AuthError` is the **dashboard API key** and has been to the server.

- **The README was wrong about the network in three places and is corrected in
  place.** It opened with "This library opens no socket", which was true of every
  version up to 0.1.2 and false the moment `check()` landed, and the Errors
  section said "Nothing here is raised from a response, because nothing here
  sends one". Both sentences are kept in HTML comments next to their
  corrections, per the house rule, and a test asserts each is gone from the prose
  *and* present in the file - the comment that records a fix is otherwise
  indistinguishable from the bug.

  New sections: `Asking the gateway`, `Account API`, and `Many sessions at once`.

- **A test per quotation, enforced.** `tests/test_readme.py` builds every output
  the README quotes and compares it, whitespace collapsed and nothing else
  forgiven. That includes the 407 block, whose text comes from the TOML - so the
  README and the shipped definition have to agree word for word, and they are two
  files of which one goes to PyPI. Both directions of the parameter table are
  pinned too: every `known_params` entry has a row, and no row names a parameter
  the package refuses, which is exactly what `norotate` was for five days.

**Two bugs in the new API client, found by reading it before wiring it up rather
than by a test.** `_urllib_transport` hardcoded `timeout=30.0`, so
`Client(timeout=...)` was accepted and silently inert, and `_interpret` took a
`timeout` argument it never used. The timeout is now bound into the default
transport with `functools.partial` at construction. Worth recording because both
are the same shape: a parameter that is threaded through the signature, looks
configured at every call site, and is dropped at the one place it would have
taken effect. Nothing failing, nothing to notice.

- **`type` is a known parameter**, and refusing it was blocking the paid mobile
  tier. Probed from the VPS on 2026-08-26, the same run that removed `norotate`
  and by the same method: a junk value discriminates where acceptance does not.
  `type=zzqqx` is answered **407**, exactly as the positive control on `filter`
  and unlike the negative control `zzqqx=1`, which is answered 200 and dropped.
  So the gateway recognises the name.

  It selects a pool rather than filtering one. Five echo requests per arm, a
  fresh `sid` and `country=us`: `type=mobile` drew AS21928 T-Mobile three times,
  AS6167 Cellco and AS7018; `type=residential` and the parameter left off drew
  Comcast, Charter, Windstream, Metronet, Fidium, Planet and AS701 wireline,
  with no mobile ASN in either arm.

- **`speed`'s comment in the shipped definition was corrected.** It said the
  name was read off the vendor's proxy generator on 2026-08-12 and never
  probed. It was probed on 2026-08-26 in the run above and is answered 407, so
  the name is confirmed. What remains unmeasured is what it *does*; the comment
  now says which half is which. No behaviour changed.

- **A place name is written the way you would say it.** `region="District of
  Columbia"` now builds `region-district_of_columbia`. Five parameters are
  folded to their wire form before anything else looks at them - `country`,
  `region`, `city`, `isp`, `type` - and the fold is three fixed steps: strip
  ASCII whitespace from both ends, lower-case ASCII `A-Z` only, replace each
  space with `_`.

  Until now a space passed straight through into the username and `country="US"`
  was sent as `country-US`. Both are settings the gateway does not apply.

  This is added on **two independent sources**, which is the bar `norotate` set
  and failed. The gateway itself emits `region-district_of_columbia` in a
  username generated on 2026-09-07, and the vendor's own client builds the same
  form in `nodemaven/utils.py::build_proxy_username`. It is also a different
  kind of claim from `norotate`: that one asserted the gateway recognises a
  *name*, which cannot be established from a generator, because an unrecognised
  name is answered 200 and dropped. This one converts an input whose behaviour
  is unknown into a form that is known to work, so there is no false refusal
  available to be wrong about.

  Which parameters fold is declared in the provider TOML under a new
  `normalize` key, as data, for the same reason `known_params` is: the public
  API must never name a gateway's parameters in its own code, and the next
  gateway will fold a different set or none at all.

  Four parameters are deliberately left out. `sid` is opaque and chosen by the
  caller, and folding it would silently move a sticky session to a different
  exit. `filter` and `ttl` are not folded by the vendor's client either, not
  even to lower case, and the generated string says nothing about them because
  its `medium` was already lowercase. `speed` does not appear in the vendor's
  builder at all.

  The fold is ASCII-only and says so in the code, because `str.lower()` is
  Unicode-aware: it maps characters like the Turkish dotted capital I in a way
  Rust and Go do not reproduce, and a golden vector that depended on it would
  fail in one SDK for reasons that have nothing to do with proxies.

- **A value containing ASCII whitespace is refused**, for every parameter
  nothing folds. A proxy username is a single token on the CONNECT line, so a
  space either malforms the line or cuts the value short, and the object would
  otherwise present three spellings of one value - raw from `username`, as
  `%20` from `url()`, and a third to a browser driver taking the fields
  separately - of which at most one can be right. The six characters treated as
  whitespace are spelled out as `ASCII_WHITESPACE` rather than delegated to
  `str.isspace`, which is Unicode-wide; a no-break space is not in the set and
  passes, which is the honest answer for input nobody has asked the gateway
  about.

- **Two ways a provider definition can now be refused at load.** Normalizing a
  parameter that is not in `known_params` is refused, because that parameter is
  rejected by name and the fold could never run. Declaring `normalize` while
  separating parameters with `_` is refused, because the fold *inserts* that
  character: `city="New York"` would become `new_york` and then be cut in half
  by the separator the fold had just produced, and the caller would be blamed
  for input that was correct.

- The unknown-parameter error message quoted in the README is now pinned by a
  test that compares the whole string. It had drifted to nine parameter names
  while the code produced ten - the Rust port carried that test from its first
  commit and this one did not.

- `Source` and `Issues` added to the package metadata, and the README gained a
  CI badge, a link to its own LICENSE and a link to the benchmark harness the
  retry table is measured on. That is five things and they were held back for
  two versions of one reason: the first four point into this repository, which
  is internal and answers 404 to anyone not signed in - the badge reads "repo or
  workflow not found" for the same reason - and the fifth points at
  `proxy-benchmark`, which was internal until 2026-09-01.
- The quickstart now shows a live first request through **any** proxy, not only
  through NodeMaven's gateway. Nothing in the library changed - the capability
  was there and the README buried it in the last section.
- A `Parameters` reference for the shipped gateway, and an `Errors` list.

- **`isps()` reads a different key, because that endpoint answers a different
  envelope.** Measured 2026-09-08 against a live account: `locations/isps`
  answers 200 with an object whose keys are `city`, `country`, `isps` and
  `region`, and there is no `results` anywhere. The rows are the list under
  `isps` - 358 of them for `country__code="us"` - and the other three fields are
  strings, whose contents have still not been printed and which this package
  therefore says nothing about and does not return.

  The fix is a `rows_key` threaded through `_list`, `_page` and `Page`, with
  `isps()` the only caller that passes anything but `results`. It is recorded on
  the `Page` so `iterate()` reads the second page the way it read the first -
  without that, the walk would parse page one as ISPs and page two as a one-row
  envelope and stop, which is a truncation wearing the shape of an ending.

  **What was rejected is the more interesting half.** The obvious alternative is
  to have `_page()` return whichever value in the object happens to be a list.
  That reads as robustness and is a guess: an envelope carrying two lists is
  resolved by key order, silently, and differently the day the server adds a
  field. Naming the key per endpoint is knowledge this package actually has.

  **This entry said until later the same day that the method did not work and
  was documented rather than fixed**, because the first probe printed the key
  *names* and not the values, so whether `body["isps"]` held a list had not been
  observed - and unwrapping a key because its name reads right is the move that
  put `norotate` in this package and `traffic_left` in its README. That was the
  right call at the time and the record is worth keeping for what it cost: one
  command. The probe was changed to print value types and lengths, it was run,
  and the answer was the obvious one. **Being obvious is not what made it safe to
  ship; being run is.**

  Nothing was released in the broken state - the whole `Client` is new in this
  version - so what the day bought was a decision procedure rather than a
  correction to a published artifact.

- **`offset` is honoured on `isps`, and the arm that shows it is not the
  obvious one.** `limit=50&offset=0` and `limit=50&offset=50` both answer 50
  rows out of 358, which is exactly what a server accepting `offset` and
  dropping it would answer, so the two arms that look like a paging test cannot
  separate the two cases. What separates them is `limit=1000&offset=1000`
  answering **zero** rows where an ignored offset would have answered all 358.

  That is the weaker of the two claims, and the code says so. On `countries`,
  `regions` and `cities` the rows at `offset=50` were read and are disjoint from
  those at `offset=0`; on `isps` page-to-page disjointness has still never been
  read. `iterate()`'s duplicate-page guard is what covers the gap, and it stays
  for that reason rather than as a leftover.

- **The `limit=1000` ceiling, withdrawn and then measured.** An earlier draft of
  this section asserted 1000 was a server ceiling on the strength of arms C
  (`limit=1000`) and D (`limit=10000`) returning the same 1000 rows. Those two
  arms cannot separate a ceiling from a collection that is exactly 1000 rows
  long, so the claim was withdrawn from `api.py`, `README.md` and from here.
  Arm H - `limit=1000, offset=1000` - was then added and returned a further 965
  rows, so `cities(country__code="us")` spans 1965 rows and one call sees the
  first 1000 of them with `count`, `next` and `previous` all `None`. The claim
  is restored naming the arm that establishes it. **Being right by luck is not
  the same as being justified**, and the withdrawal was correct when it was
  made.

- **Dates came out of the README, and out of the five `connect_reactions`
  strings.** They are here instead, and the rule is audience rather than
  subject: this file and the definition's `notes` are read to audit a claim, so
  a date is the point; the README is read to use the library and
  `connect_reactions` is printed to somebody whose tunnel just failed, where
  *when we measured it* is not part of the answer they came for. Nothing was
  softened - the README still says which behaviours were measured and which
  were transcribed, and it now names this file as where the provenance lives.
  Counted after the sweep rather than during it: `README.md` holds two dates and
  both are the arguments in `statistics(start_date=..., end_date=...)` - which
  named two filters this server does not have, corrected in the README on
  2026-09-09 and left standing here because the count was right about the dates
  and the sentence around them was quoting the example rather than the API - the
  Rust
  README holds none, all five `connect_reactions` hold none, and `notes` keeps
  its six.

  This bullet first quoted those counts as *22, 15 and 4*, written from memory
  while the edits were still open and wrong in two of three places - inside the
  entry whose whole subject is moving claims to where they get audited. It is
  worth recording because of how it happened rather than what it cost: the
  numbers were a byproduct of the work, not the finding, and that is the class
  of number nobody thinks to measure. `git diff` cannot answer it either, since
  these files carry several sessions of uncommitted work and the counts get
  attributed to whichever edit the diff algorithm pairs them with. Counting the
  finished file is the only reading that means anything.

- **A fabricated error message in the README, caught by the test written for
  exactly that.** The new quickstart contrast between a hand-written URL and a
  validated one quoted a `ParamError` reading *"'filtr' is not a parameter this
  gateway knows. Did you mean 'filter'?"*. This library has never said that -
  there is no "Did you mean" in it at all. What it says is measured and now
  quoted verbatim. The test that caught it only did so by luck: it pinned
  `quoting[0]`, the first README block quoting a `ParamError`, and the invented
  one happened to land first in the file. It now checks **every** such block,
  extracting the typo from each rather than hardcoding one, so a second
  fabricated quotation lower down would fail too.

### The account API was rewritten against the vendor's specification, 2026-09-09

The vendor publishes an OpenAPI 3.0.3 document, unauthenticated, 24 paths. It
was read on 2026-09-09 and **four of the paths this package sent did not
exist**. Nothing shipped in that state - the whole account API is unreleased,
0.1.2 carries none of it - so the corrections below cost renames and no
deprecations.

- **The paths.** `locations/zip-codes/` is `locations/zipcodes/`, solid, no
  separator. `statistics/` does not exist and was never one endpoint: it is
  `statistics/data/`, `statistics/requests/` and `statistics/domains/`, each
  requiring a `proxy_username`. `whitelist-ips/` is `whitelist/ips`, with no
  trailing slash. `sub-users/` was right and was being read under the wrong key
  - its rows are under `payload`, inside a `{success, description, errors,
  payload}` envelope that is the specification's own declared 200 schema and not
  a server defect. `update_sub_user` sent `PATCH` to a path that does not exist
  at all; it is a `PUT` to the collection with the id in the body.

- **What made this survive three weeks.** The section documenting these calls
  argued they were safe to ship untested, because *a wrong path is answered 404
  on the first call and corrects itself*. **That is false on this host**,
  measured 2026-09-09: three of the four wrong paths were answered `200`,
  `text/html`, 6415 bytes - byte-identical to a path invented on the spot as a
  negative control. The dashboard serves its front end for anything it does not
  route.

  What the mistake looked like from the inside: the claim is true of nearly
  every REST API, and it read as a property of HTTP rather than as an assumption
  about one server. It was never checked, and the check is one extra request.
  This is the same failure as `norotate` in 0.1.1 and `OptimizationHints` before
  it - **a wrong name answered with success** - which the package was built to
  defend against at the gateway and then trusted the dashboard not to do.

- **Paging is three conventions, not one.** The nine location endpoints take
  `limit`/`offset`; `sub-users/` takes `page`/`per_page`; `whitelist/ips` takes
  `page`/`page_size`. An unknown query parameter is ignored rather than refused,
  so the single hard-coded pair was silently doing nothing on two thirds of the
  surface. `Page` now carries the convention it was fetched under.

- **`iterate()` stops on an empty page, not on a short one.** The old rule
  truncated wherever the server caps the page size below the request, and this
  server does: `cities(limit=10000)` is answered with 1000 rows out of 1965, so
  "shorter than asked" read those 1000 as the end. **The measurement that says
  so was already written in this package's own docstrings** and the stop rule
  was never checked against it. A measurement sitting in a docstring is not a
  measurement anyone applied.

- **Both page-numbered endpoints number their first page 1**, measured
  2026-09-09 by `lab/probes/probe_account_api.py --phase 9` against a live
  account, asking each for pages 0, 1, 2 and 9999 at a size of one row. On
  `sub-users/` the evidence is where the rows are: page 0 came back with none
  and page 1 with the account's only sub-user, which a 0-based server cannot
  produce. On `whitelist/ips` the collection is empty, so the reading is the
  weaker one - page 1 is the only number answered `200` at all, while 0, 2 and
  9999 are answered `404`, and a 0-based server would have answered page 0.

  Written earlier the same day and retired before any release: `iterate()`
  *refused* to walk a page-numbered call whose first `page` the caller had not
  supplied, because nothing measured whether the server numbered from 0 or 1 and
  the two guesses are not symmetric - assume 1 against a 0-based server and the
  first page is dropped in silence. The refusal was the only reading that could
  not be silently wrong while the question was open, and what retired it is the
  measurement rather than a second opinion about what servers usually do.
  `Paging.first_cursor` carries the answer and the refusal is gone from the code
  rather than sitting behind a flag.

- **The two page-numbered endpoints do not mark the end of a collection the same
  way**, measured in the same run, and a single rule for both is a defect either
  way round. Past the last page `sub-users/` answers `200` with an empty payload
  and `whitelist/ips` answers `404`. `Paging.ends_with_not_found` is therefore
  set on the whitelist alone, and `iterate()` treats a `404` as the end only
  there - everywhere else a `404` stays an error, because on this host it is
  also what a wrong path looks like. Without that field, walking the whitelist
  past its last page raised `NotFoundError` instead of stopping.

  Half of it is inference and the shipped docstring says which half: the account
  holds no whitelist entries, so what is measured is `404` on pages 0, 2 and
  9999 against a `200` on page 1, and this endpoint has never been seen to end
  anywhere but at page 1. Put one address on the account and it becomes a
  measurement.

- **New methods**, all from the specification: `isp_regions`, `isp_cities`,
  `zip_code_regions`, `zip_code_cities`, `statistics_data`,
  `statistics_requests`, `whitelist_ip`, `reset_sub_user_usage`.
  `add_whitelist_ip` became `upsert_whitelist_ip` because the endpoint replaces
  an existing entry as well as creating one, and takes a required `ports_count`.

- **The specification is documentation and gets no more authority than that.**
  Two defects in it: `info.description` names host `api.nodemaven.com`, which
  404s at nginx while `dashboard.nodemaven.com` answers; and the statistics
  endpoints describe their dates as "dd-mm-yyyy" in prose while typing the same
  fields `format: date`, which is `yyyy-mm-dd`. One disagreement with a run: it
  calls the availability field `effective_availability` where the 2026-09-08
  measurement read `availability`. The run wins, and nothing depends on it.

  **The date disagreement was settled live the same day and the typed half is
  the wrong half**, `--phase 10`: `start=20-08-2026` answers `200` with 21 data
  points, `start=2026-08-20` answers `400`, and that `400`'s body is
  byte-identical to the body for `start=not-a-date`. So `format: date` is not a
  rival spelling the server declines - it is a string the server cannot parse,
  and every client generated from this document sends the one form that fails.
  The docstrings on the statistics methods now say `dd-mm-yyyy` outright.

  The same run found that all three answer **500**, not 400, when `start`, `end`
  and `period` are omitted together, though the document marks all three
  optional. There is no "give me everything" call on this surface.

  This entry read "unresolved; nothing here validates a date, so nothing here
  depends on the answer" until that run. The second clause was true, and it was
  the reason not to look - which is backwards for a defect in a document other
  people generate clients from. What this package does with a date is pass it
  through, so the cost lands on a caller who read the spec instead of this file,
  and it lands as a `400` whose body does not name which argument was refused.

- **`sub_users()` returns every sub-user's `proxy_password` in clear text**, by
  the specification's own required-field list, as does `me()`. This is now said
  in the README and in both docstrings. It is written here because a probe in
  the sibling `lab/` tree printed one to a console on 2026-09-09 and the
  password had to be rotated.

  **`create_sub_user()` does too, measured the same day rather than read off a
  schema.** The create response carries `proxy_password` alongside the id, so it
  is a credential and not a receipt.

- **All five write endpoints were called live on 2026-09-09** and four of them
  behave. Each write was followed by a *separate read* rather than trusted, which
  on this host is the only thing that distinguishes success from a `200` carrying
  the dashboard's front page: `create_sub_user` answers **`201`** where its own
  path declares only `200`; `update_sub_user`'s PUT-to-the-collection answered
  `200` and a re-read of the row showed the changed field, so the shape is
  measured and not transcribed; `reset_sub_user_usage` answers `200` with a
  `payload` **array** where every other envelope here carries an object;
  `delete_sub_user` with the id as a query parameter answers `200` with a body
  where the document declares `204`.

  **Both deletes do remove the object, and the whitelist's uniqueness check
  lags behind them.** This entry passed through two wrong versions the same day
  and both are kept, because the second was written as a correction of the
  first.

  It said "a re-read showed the row gone" for both deletes. That was withdrawn:
  the whitelist delete answered `200` at 15:13 and its immediate re-read did not
  show the address, and at 15:18 the server refused to whitelist that same
  address with `400 IP is already whitelisted.`, before any write in that run
  had succeeded. So the pair had been believed once and had been wrong once.

  It then said neither delete was confirmed to have removed anything, and named
  a soft or uncommitted delete as one of two live candidates. At 16:18 the same
  address was accepted `201`. An invisible surviving row would still have
  blocked it, so what was stale is the uniqueness check and not the storage. The
  sub-user was separately absent from a listing read at 16:15, an hour after its
  delete rather than a second after it.

  Only the bounds of the lag are measured and they are loose: still refusing at
  5 minutes, over by 62. What a caller should take from it is unchanged by the
  resolution - re-adding an address you have just deleted may be refused as a
  duplicate for some minutes.

  **`upsert_whitelist_ip()` sends `protocol` on every call**, because the
  specification marks it optional with `default: "HTTP"` and the server does not
  apply that default. Measured 2026-09-09 at 16:18, one field at a time: `ip`,
  `ports_count` and `name` is refused `400`,
  `{"error": "Please enter a valid protocol(HTTP or SOCKS5)."}`; the same body
  plus `protocol: "HTTP"` is accepted `201`, and a read of `whitelist/ips` finds
  the address. A client generated from the document therefore sends the one body
  that fails, which is why the default lives in this method rather than in the
  caller's arguments.

  An earlier run had settled the likelier-looking reading first: `not-an-ip` as
  the address draws that same message byte for byte, so `protocol` is validated
  before `ip` is examined and the reserved test address was never the problem.
  This entry then said which field was short remained the server's word rather
  than a measurement, since the accepted body varied six at once. That was right,
  and it was one call away from being settled.

  Untested and worth knowing: `name` was present in every rung of the ladder, so
  whether it is required too is unmeasured, and no rung sent `ip`, `ports_count`
  and `protocol` alone.

  **The success body is `{"ip_id", "message"}` and neither key is documented**;
  the path binds both `200` and `201` to a schema whose only property is
  `message`. The identifier is `ip_id` where the listing calls the same value
  `id`. `delete_whitelist_ip` takes it and answers `200`.

- **The API key is a JWT that lives 1800 seconds**, `exp - iat`, measured
  2026-09-09 by decoding a live one locally. No path in the vendor's 24 issues or
  refreshes a token and the document does not mention an expiry at all, so a
  `Client` held longer than half an hour begins raising `AuthError` for a reason
  no response distinguishes from a wrong key or a wrong header form. The message
  now names the clock as a third possibility. Nothing here reads `exp` or renews
  on its own - that would mean decoding a credential to take a control-flow
  decision, and one token's lifetime is not the policy.

Five of the vendor's 24 paths are deliberately not wrapped: `locations/all-doc/`,
`notifications/`, `llm/submit/`, `llm/results/{id}/` and `llm/balance/`. The
omission is listed rather than left silent.

### What a review of the above found, 2026-09-09

Ten fixes, from an automated review of the pull request carrying the section
above. Two of its twelve findings were declined and are recorded here as well,
because a declined finding is a decision and reads as an oversight if it is not
written down.

Worth stating as one thing rather than ten, because it is the pattern and not
the bugs: **in three of these the reasoning was written correctly in the comment
directly above the code, and the code beside it did something else.** The
paging comment described advancing by rows returned while the line added the
limit; the port comment said the value could come from the definition while the
message blamed the caller; the 429 message told the reader to consult a field
this client cannot fill. Prose next to code is not a test of that code, and it
is worse than no prose, because it is what a later reader checks against.

- **`iterate()` advanced the offset by the limit asked for rather than by the
  rows returned.** `cities(limit=10000)` requested offset 0 then offset 10000
  against a server that caps that collection at 1000 rows of 1965, so it walked
  off the end and returned 1000 of 1965. The cap was already measured, already
  written into this module's docstrings, and the fix had been applied to the
  stop condition - stop on an *empty* page, not a short one - and not to the
  advance, in the same sitting.

  The suite did not catch it and the reason is worth more than the fix. Three
  tests covered the case. Two asserted the wrong offsets, one of them saying so
  in its own name - `test_a_caller_who_raised_the_limit_pages_at_that_limit` -
  and the third counted rows only, which cannot fail, because the fake transport
  replays a queued list of pages whatever query string it is handed. So a test
  named after the capped page passed under the broken rule. All three now assert
  the offset sequence.

- **`RateLimitError.retry_after` is always `None` from this client, and both the
  message and the class said otherwise.** The 429 said to wait the server's own
  interval "in `retry_after`" - an instruction that could not be followed on any
  429 this package raises, because `Transport` returns `(status, bytes)` and the
  response headers are gone before anything could read `Retry-After`. The
  message now says the client cannot report the interval and that you should
  back off on your own schedule. The attribute stays: it belongs to the class
  rather than to this one transport, and a caller raising it by hand can set it.
  What was wrong was the promise, not the field. Surfacing the header means
  widening a public protocol implemented in four languages, and that is a
  version's worth of change.

- **The README's statistics examples sent ISO dates**, which this server answers
  `400`. The prose two paragraphs below them had already been corrected against
  `--phase 10` on the same day; the examples were left, so the section explained
  the right rule and demonstrated the wrong one. A test now reads the dates out
  of the fenced blocks and refuses anything that is not `dd-mm-yyyy`. It is
  scoped to the blocks deliberately - the prose quotes `start=2026-08-20` as the
  form that fails, and a whole-file scan would have to permit the exact string
  it is hunting for.

- **A provider definition's `port` is validated when the definition loads**, not
  coerced with `int()` and not left to fail later. `int()` accepted `0`, which
  means "any free port" when binding and nothing at all when connecting, and it
  raised `ValueError` rather than `ProviderError` on text. A bad port in a
  shipped TOML now fails at load with the file named.

- **A bad port from the provider definition no longer blames the caller.**
  `Proxy` falls back to the definition's port when none is passed, and the
  refusal said `port=... is not a TCP port`, naming an argument the caller did
  not supply. The two cases now raise separately: one names the definition and
  says to fix it or pass `port=` to override, the other is unchanged.

- **`normalize` and `connect_reactions` are type-checked at load.** A
  `normalize` given as a string was iterated character by character, so
  `normalize = "city"` silently produced the parameter names `c`, `i`, `t`, `y`
  and normalized nothing. Both now raise `ProviderError` naming the file.

- **A `values` list is folded when its parameter is normalized.** The fold -
  strip, ASCII lower-case, spaces to `_` - is applied to what the caller passes,
  and was not applied to the legal values it is checked against, so a definition
  listing `District of Columbia` refused the value it was written to allow. The
  fold is now one function, `_fold`, called from both places; it was two copies
  of three operations before, which is how they came apart.

- **`tests/test_check.py` caught `Exception` in four places** where it meant
  `ParamError`. `pytest.raises(Exception)` passes on a `TypeError` from a
  refactor that broke the call, which is the failure those tests exist to
  report.

- **`_headings()` in `tests/test_readme.py` read every `#` comment in every
  example as a heading.** The two tests that check in-page links point at real
  headings were therefore checking a superset: a link pointing at a code comment
  would have passed. They were green throughout and had stopped testing their
  subject.

**An eleventh fix, from a second pass of the same review, and it is a defect
the first pass introduced.** Correcting the ISO dates in the statistics examples
left the keyword names alone: they read `start_date=` and `end_date=`, and this
server's filters are `start` and `end`. The examples had been wrong about the
names since the section was written, and the edit that touched the very same two
lines did not look at them, because the finding was about the date format and
the date format is what got checked.

The consequence is worse than a wrong example. `Client` forwards `**filters` as
query parameters unaltered, and **this server ignores a query parameter it does
not know**, measured 2026-09-09. So `start_date=` is accepted by Python, sent,
and dropped; the range is then absent, and the call answers 500 with the server
complaining about a missing range rather than about the name. Nothing between
the caller and the response says the word was wrong.

That is the `norotate` failure mode one layer up, and it is worth naming as an
inconsistency in this package rather than as a typo: `Proxy` refuses an unknown
gateway parameter before sending, because the gateway answers 200 and drops it -
that refusal is most of what this library is for - and `Client` forwards an
unknown API parameter in silence for exactly the same server behaviour.
Validating `**filters` means shipping a per-endpoint list of legal names, which
is a version's worth of decision and is not made here. Three tests now pin the
examples instead: the filter names, the date format, and that no example omits
`start`, `end` and `period` together - `domain_statistics("acct-1")` did, and
all three statistics endpoints answer 500 to that.

**The test written in the first pass would not have caught it, and would have
gone quiet on being fixed.** It scanned for `(?:start|end)_date="..."`, because
it was written from the examples rather than from the API, so it pinned the date
format of two arguments that did nothing - and the moment the names were
corrected its regex would have matched nothing and it would have passed on an
empty list. It survives only because it carries an `assert dated` guard first. A
test that scans for something and then checks what it found needs to assert it
found something, or it turns into a green no-op the first time the thing it
scans for is renamed.

Two findings were declined:

- **Repeated headers in a `Check` are still collapsed to the last one.**
  Carrying them all means `Check.headers` stops being a `dict`, which is a
  breaking change to a documented attribute, and no measured gateway reaction
  depends on a repeated header. It is a design decision for a later version, not
  a fix.

- **A test that scans the source for imports** was proposed as a replacement for
  a narrower one. The replacement was not specific enough to pin anything, and a
  test that is vague about what it forbids is the shape the two above had.

## 0.1.2 - 2026-08-26 09:23

- **`values`**, a per-parameter list of legal values, added to the provider
  schema. A value outside the list is refused before anything is sent. It ships
  empty for NodeMaven on purpose: what was known was which values the vendor's
  proxy generator *emits*, which is a sample of one interface's output and not
  the set the gateway accepts. A wrong entry here blocks a setting that would
  have worked, which is worse than the gap it closes.

  The key exists before there is anything to put in it because four language
  SDKs read this schema: filling it in later is an edit to a data file, adding
  the key later is an edit to four parsers.

- The gateway's known parameters and their reactions were re-recorded in the
  shipped definition with the probes and dates behind them.

**`norotate` never shipped, and the round trip is the reason this file exists.**
It was added to the known parameter list on 2026-08-21 because it appears in the
vendor's own proxy generator, and removed on 2026-08-26 after being probed: three
ways, each with a negative control carrying a name nobody could have implemented
and a positive control on `filter`. It takes a junk value with 200 exactly as the
unknown name does; with no session id it draws 6 distinct exits of 6, exactly as
both controls; with a fixed session id and `ttl=1m` sampled at 0, 78 and 157
seconds it draws 3 distinct of 3, again exactly as both controls. The gateway
answers 200 and drops it.

Both changes sat between the 0.1.1 and 0.1.2 tags, so no release ever accepted
the parameter. What was wrong for those five days was the reasoning, not a
published artifact: an unrecognised name and a name we have not heard of produce
identical evidence on this gateway, and the vendor's file was allowed to break
the tie instead of a probe.

## 0.1.1 - 2026-08-20 20:58

No change to the library. The version exists because the README shipped an
example that did not run, and a README is the package page.

- The separator rule was restated as a measurement rather than a precaution. On
  2026-08-20 a probe opened tunnels with `sid-order8e3bf9-4417` and with
  `sid-order8e3bf9`, four rounds each, interleaved; both landed on **one** exit
  address, while a third arm spelling `sid-order8e3bf94417` held a different one
  throughout. The gateway cuts the value at the separator, so every order id
  beginning `order` would quietly share one session and one exit.

## 0.1.0 - 2026-08-20 19:42

First release.

- `Proxy`: builds the gateway username, and refuses input the gateway would
  mishandle. Credentials fall back to the environment. `url()`, `requests()`,
  `httpx()` and `playwright()` for the clients; `replace()` and `session()`
  return new objects, because on this gateway the session key is the whole
  parameter set and changing one parameter is a different exit address rather
  than an adjustment.
- `Provider`, `load()`, `load_file()`, `available()`: a gateway dialect is a
  TOML file and never a code path, so a definition you write yourself goes
  through the same builder and the same validation as the shipped one.
- `NodeMavenError` and the three exceptions under it.
- No socket, no session, no connection pool, and **no retry**. The last one is
  the only design decision here taken against a measurement rather than a
  preference: over 1464 attempts the chance the next one succeeds falls from 75%
  with no prior failure to 5.8% after five and 0.5% after seven.

This one was uploaded with an API token, before Trusted Publishing was set up.
That token was revoked and no token is stored anywhere now; every release since
is published by the `publish` workflow against an OIDC identity.
