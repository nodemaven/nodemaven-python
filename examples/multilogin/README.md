# NodeMaven proxies in Multilogin X profiles

Start a Multilogin X browser profile on a NodeMaven residential proxy, drive it
with Playwright, and check that sites see the proxy's address.

The script:

1. builds a sticky proxy session with the `nodemaven` SDK, so the profile keeps
   one exit address while it runs;
2. starts a Multilogin quick profile on that proxy (a temporary profile, deleted
   when it closes);
3. attaches Playwright to the profile over CDP and opens a page;
4. compares the address the page sees with the session's exit, then stops the
   profile.

## Run it

You need the Multilogin X app (or agent) running and signed in, and an
[automation token](https://multilogin.com/help/automation-token).

```bash
pip install nodemaven playwright "requests[socks]"
export NODEMAVEN_LOGIN=... NODEMAVEN_PASSWORD=... MLX_AUTOMATION_TOKEN=...
python nodemaven_multilogin.py --country us
```

```
proxy exit: 203.0.113.7
profile 6edad0d2-... started, CDP on port 63768
the site sees: 203.0.113.7
matches the proxy's exit
profile stopped
```

`--socks5` uses SOCKS5 on port 1080 instead of HTTP on 8080, for networks that
interfere with HTTP proxy traffic.

`NODEMAVEN_LOGIN` and `NODEMAVEN_PASSWORD` are the proxy credentials from the
[NodeMaven dashboard](https://dashboard.nodemaven.com), not the account sign-in.

## Use it in your own code

`start_quick_profile()` returns the profile id and the CDP port. Everything after
`connect_over_cdp()` is ordinary Playwright: the profile's own fingerprint,
cookies and proxy stay in place. For a saved profile instead of a quick one,
start it with the launcher's profile start endpoint and the same
`automation_type=playwright`.
