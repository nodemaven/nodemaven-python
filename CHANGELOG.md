# Changelog

Written against the tags and the PyPI upload records rather than from memory, on
2026-09-04. Release times are UTC as PyPI recorded them.

A note on how entries here are worded, because it is the same rule the library
itself is built on: a change to what the gateway is believed to accept carries
the probe that established it and the date it was run. "The vendor's documentation
says so" is not one of those, and an entry that rests on it says so outright.

## Unreleased

- `Source` and `Issues` added to the package metadata, and the README gained a
  CI badge, a link to its own LICENSE and a link to the benchmark harness the
  retry table is measured on. All four were held back while the repository was
  internal, where they answered 404 to anyone not signed in.
- The quickstart now shows a live first request through **any** proxy, not only
  through NodeMaven's gateway. Nothing in the library changed - the capability
  was there and the README buried it in the last section.
- A `Parameters` reference for the shipped gateway, and an `Errors` list.

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
