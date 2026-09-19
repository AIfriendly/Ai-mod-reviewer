#!/usr/bin/env python3
"""Mint the YouTube refresh token WITHOUT a browser on this machine.

`youtube_auth.py` needs the browser and the script on the same host (it catches an
OAuth redirect on localhost), which is impossible from a cloud sandbox or when you
only have a phone. Google's device flow has no redirect at all: this script prints a
short code, you type it into google.com/device on ANY device, and the token lands here.

Requires an OAuth client of type "TVs and Limited Input devices" (Google Cloud ->
Credentials -> Create credentials -> OAuth client ID). A Desktop-app client is
REJECTED by the device endpoint with "Invalid client type".

The device flow does not permit the narrow youtube.upload scope, so this asks for
`youtube` instead — videos.insert and thumbnails.set both accept it.

    python youtube_auth_device.py --client-id XXXX --client-secret YYYY
"""
from __future__ import annotations

import argparse
import time

import httpx

DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = ("https://www.googleapis.com/auth/youtube "
         "https://www.googleapis.com/auth/youtube.readonly")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    args = ap.parse_args()

    r = httpx.post(DEVICE_URL, data={"client_id": args.client_id, "scope": SCOPE},
                   timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"Device code request failed ({r.status_code}): {r.text}")
    d = r.json()

    print("\n" + "=" * 64)
    print(f"  Go to:  {d['verification_url']}")
    print(f"  Code :  {d['user_code']}")
    print("=" * 64)
    print("Sign in, pick the RIGHT channel (the account owns several), approve.")
    print(f"Code expires in {d['expires_in'] // 60} minutes. Waiting...\n", flush=True)

    interval = d.get("interval", 5)
    deadline = time.time() + d["expires_in"]
    while time.time() < deadline:
        time.sleep(interval)
        t = httpx.post(TOKEN_URL, data={
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }, timeout=60)
        if t.status_code == 200:
            refresh = t.json().get("refresh_token")
            if not refresh:
                raise SystemExit(f"No refresh_token in response: {t.text}")
            print("\n" + "=" * 64)
            print("SUCCESS — set this where the pipeline runs:\n")
            print(f"YOUTUBE_REFRESH_TOKEN={refresh}")
            print("=" * 64)
            return
        err = t.json().get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise SystemExit(f"Authorization failed: {err} — {t.text}")

    raise SystemExit("Timed out waiting for approval; re-run to get a fresh code.")


if __name__ == "__main__":
    main()
