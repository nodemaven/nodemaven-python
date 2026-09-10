# Why the validation is the point

<!-- Everything below is a measurement, and none of it carries a date. The dates
     and the probes are in CHANGELOG.md, which is linked from the next paragraph
     and is where a reader asking "is this still true" should be sent. Putting a
     date on every claim here was tried and read as noise.

     This was a README section until 2026-09-10. It moved so that the README
     could be read in one sitting; it did not shrink in the move, because the
     argument only works at full length - the point is that five different
     status codes name no parameter, and a summary of that is just an opinion. -->

Every gateway behaviour below was measured against the live gateway rather than
transcribed from documentation, and each one carries its date and the probe
behind it in [CHANGELOG.md](../CHANGELOG.md).

- [What a wrong value looks like](#what-a-wrong-value-looks-like)
- [Case and spacing](#case-and-spacing)
- [Why a separator in a value is refused](#why-a-separator-in-a-value-is-refused)
- [Why session ids are hexadecimal](#why-session-ids-are-hexadecimal)

## What a wrong value looks like

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
over six CONNECTs holding the login, the password, the target, the gateway host
and port and the parameter order fixed. `country=us`, `region=louisiana`,
`city=abbeville` answers `200`, and so does a second city in a second region.
The same city with the region left out answers `500`, and an invented name sent
with a real region answers `406` - so the gateway does look the name up, and the
`500` is a request it could not resolve rather than a fault on their side.
`Client.validate()` refuses that combination before it goes out.

The last row is worse than any of them: the request succeeds, your code carries
on, and the setting you asked for was never applied. Nothing that comes back
over the wire can tell you.

So this library checks before anything is sent:

```python
>>> Proxy(login="u", password="p", contry="us")
ParamError: NodeMaven does not know the parameter 'contry': it is answered with
200 and dropped, so the connection would succeed and your setting would NOT be
applied. Known: ['city', 'country', 'filter', 'ipv4', 'isp', 'region', 'sid',
'speed', 'ttl', 'type']
```

**Names are validated. Values, on this gateway, are not.** Passing a name that is
not in the parameter table raises before anything is sent, because the gateway
answers an unknown name with 200 and drops the setting. Values are passed
through, because what is known is which ones have been observed to work - and
that is not the same as the set the gateway accepts. Refusing on a guessed list
would block a setting that would have worked, which is the worse mistake of the
two. The schema does carry a per-parameter list of legal values and refuses
anything outside it; the shipped definition leaves that list empty for every
parameter, deliberately, and a definition you write yourself gets the check as
soon as you fill it in.

## Case and spacing

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
`ttl-10m` opens the tunnel and `ttl-10M` is answered `407`, which reads as a
credentials problem and is not one. `filter` and `speed` were not refused in
either case, and this library still does not fold them - what the gateway
accepts today and what it will accept next month are different claims, and the
fold list is data in the gateway definition rather than a decision in this
package.

`ttl` counts in minutes and hours - `1m`, `10m`, `10h` and `24h` connect, while
`10s`, `10d` and a bare `10` are answered `407`. Parameter *names* are
case-insensitive at the gateway; values are not, and `ttl` is the one where it
has been measured to matter.

Which parameters fold is declared in the gateway definition, as data, so a
gateway you describe yourself folds what you say it folds and nothing else.

**Every other value is refused if it contains whitespace.** There is no spelling
of a space that works here - `username` would emit it raw, `url()` would
percent-encode it to `%20`, and `playwright()` would hand over a third thing -
so between the fold and the refusal, no value with whitespace in it can reach
the wire by any path.

## Why a separator in a value is refused

**A session id cannot contain the character the gateway separates parameters
with**, which for this one is `-`, and passing one raises rather than
connecting. That is measured and not a precaution: a probe opened tunnels with
`sid-order8e3bf9-4417` and with `sid-order8e3bf9`, four rounds each,
interleaved, and both landed on **one exit address** while a third arm spelled
`sid-order8e3bf94417` held a different one throughout. The gateway cuts the
value at the separator and reads the rest as something else, so every order id
beginning `order` would quietly share one session and one exit.

**The same cut applies to every parameter, not just `sid`,** which is why a
separator in any value is refused. `isp-verizon` opens the tunnel, a junk `isp`
is answered `406`, and `isp-verizon-zzqqx-zzqqx` is answered `200` - so the
gateway took `verizon` as the ISP and read the tail as a parameter name it does
not know, which it drops silently.

**The session key is the whole parameter set, not the session id.**
`country=us, sid=A` and `country=us, sid=A, filter=medium` are two different
sessions on the gateway, so adding or removing any parameter moves you to a
different exit address. That is why parameters change through a method that
returns a new object rather than by assignment - the move is a different
identity, and the code should say so.

**The set, not the order.** Measured over 20 rounds a side: the canonical
parameter order and a shuffled one drew the same exit 20 times each, while a
control differing by one parameter *value* drew a different exit 20 times. So
the order this library emits parameters in cannot change which exit you get.

## Why session ids are hexadecimal

`sessions()` draws from `secrets` in hex, and not from the alphabets people
reach for first, because the gateway cuts a value at its separator and every id
sharing a prefix then collapses onto one exit - silently, since the connection
still succeeds. `secrets.token_urlsafe` emits `-` and `_`, `uuid4()` emits `-`
four times, base64 emits `+` and `/`, and each of those is a separator on some
gateway.

From `secrets` and not `random` because `random` is seeded from the clock: two
workers starting in the same millisecond would draw the same ids.

Asking for the whole space or more raises `ParamError` - `sessions(256, length=1)`
wants every one of the 256 ids an eight-bit space holds, and drawing them
without repeating is a loop that either never finishes or leaves nothing for the
next caller.
