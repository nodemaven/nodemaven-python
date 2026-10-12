"""Drive a Multilogin X browser profile through a NodeMaven residential proxy.

1. Build a sticky US proxy with the `nodemaven` SDK.
2. Start a Multilogin quick profile (temporary, deleted on close) that uses it.
3. Attach Playwright to the profile over CDP and check which address a site
   sees, against the proxy's own exit.
4. Stop the profile.

Needs the Multilogin desktop app (or agent) running and signed in, and:

    NODEMAVEN_LOGIN, NODEMAVEN_PASSWORD   proxy credentials from the NodeMaven dashboard
    MLX_AUTOMATION_TOKEN                  a Multilogin automation token

    pip install nodemaven playwright "requests[socks]"
    python nodemaven_multilogin.py --country us
    python nodemaven_multilogin.py --country us --socks5   # SOCKS5 on port 1080
"""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import sys
import time

import requests
from nodemaven import Proxy
from playwright.sync_api import sync_playwright

LAUNCHER = "https://launcher.mlx.yt:45001"  # resolves to 127.0.0.1: the local agent

# Every fingerprint area masked by Multilogin; the proxy's own settings are used
# as given ("custom") so the profile does not replace them.
FLAGS = {
    "audio_masking": "mask",
    "fonts_masking": "mask",
    "geolocation_masking": "mask",
    "geolocation_popup": "prompt",
    "graphics_masking": "mask",
    "graphics_noise": "mask",
    "localization_masking": "mask",
    "media_devices_masking": "mask",
    "navigator_masking": "mask",
    "ports_masking": "mask",
    "proxy_masking": "custom",
    "screen_masking": "mask",
    "timezone_masking": "mask",
    "webrtc_masking": "mask",
}


def launcher() -> requests.Session:
    session = requests.Session()
    # The launcher is on this machine; a system or VPN proxy must not carry it.
    session.trust_env = False
    session.headers["Authorization"] = f"Bearer {os.environ['MLX_AUTOMATION_TOKEN']}"
    session.headers["Accept"] = "application/json"
    return session


def start_quick_profile(mlx: requests.Session, proxy: Proxy, kind: str) -> tuple[str, int]:
    host, port = proxy.server.rsplit(":", 1)
    body = {
        "browser_type": "mimic",
        "os_type": "windows",
        "automation": "playwright",
        "is_headless": False,
        "parameters": {
            "fingerprint": {},
            "flags": FLAGS,
            "proxy": {
                "type": kind,
                "host": host,
                "port": int(port),
                "username": proxy.username,
                "password": proxy.playwright()["password"],
            },
        },
    }
    reply = mlx.post(f"{LAUNCHER}/api/v3/profile/quick", json=body, timeout=120)
    if reply.status_code != 200:
        raise SystemExit(f"quick profile refused: {reply.status_code} {reply.text[:300]}")
    data = reply.json()["data"]
    return data["id"], int(data["port"])


def wait_for_port(port: int, timeout: float = 60.0) -> None:
    """The launcher answers before the browser listens; wait until it does."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except OSError:
            if time.monotonic() > deadline:
                raise SystemExit(f"the profile's CDP port {port} never opened")
            time.sleep(1)


def stop_profile(mlx: requests.Session, profile_id: str) -> None:
    mlx.get(f"{LAUNCHER}/api/v1/profile/stop/p/{profile_id}", timeout=60)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--country", default="us")
    ap.add_argument("--url", default="https://api.ipify.org")
    ap.add_argument("--socks5", action="store_true", help="SOCKS5 on port 1080 instead of HTTP")
    args = ap.parse_args()

    # One sticky session: the profile keeps one exit address while it runs.
    proxy = Proxy(
        login=os.environ["NODEMAVEN_LOGIN"],
        password=os.environ["NODEMAVEN_PASSWORD"],
        port=1080 if args.socks5 else 8080,
        country=args.country,
    ).session(secrets.token_hex(6))
    scheme = "socks5h" if args.socks5 else "http"
    # The address this session leaves from, asked outside the browser.
    expected = requests.get(args.url, proxies=proxy.requests(scheme), timeout=30).text.strip()
    print(f"proxy exit: {expected}")

    mlx = launcher()
    profile_id, port = start_quick_profile(mlx, proxy, "socks5" if args.socks5 else "http")
    print(f"profile {profile_id} started, CDP on port {port}")
    try:
        wait_for_port(port)
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(args.url, timeout=60_000)
            seen = page.locator("body").inner_text().strip()
            print(f"the site sees: {seen}")
            verdict = "matches" if seen == expected else "DOES NOT match"
            print(f"{verdict} the proxy's exit")
            browser.close()
    finally:
        stop_profile(mlx, profile_id)
        print("profile stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
