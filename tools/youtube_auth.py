#!/usr/bin/env python3
"""One-time YouTube OAuth consent — mints the refresh token the uploader needs.

RUN THIS ON YOUR OWN COMPUTER (it needs a browser), NOT in the cloud sandbox.

Setup first (~5 min, once):
  1. https://console.cloud.google.com/  ->  create a project.
  2. "APIs & Services" -> Library -> enable "YouTube Data API v3".
  3. "APIs & Services" -> OAuth consent screen -> External -> add YOUR google
     account under "Test users" (so you can consent while the app is unverified).
  4. "Credentials" -> Create credentials -> OAuth client ID -> type "Desktop app".
     Copy the Client ID and Client secret.

Then run:
    pip install httpx
    python youtube_auth.py --client-id XXXX --client-secret YYYY

A browser opens; approve access to your channel. The script prints the three env
vars to set wherever you run the pipeline (the sandbox's environment settings):

    YOUTUBE_CLIENT_ID=...
    YOUTUBE_CLIENT_SECRET=...
    YOUTUBE_REFRESH_TOKEN=...

Only needs to be done once; the refresh token is long-lived.
"""
from __future__ import annotations

import argparse
import http.server
import socket
import urllib.parse
import webbrowser

import httpx

# youtube.upload covers both videos.insert and thumbnails.set.
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    args = ap.parse_args()

    port = _free_port()
    redirect_uri = f"http://localhost:{port}/"
    params = {
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # ask for a refresh token
        "prompt": "consent",          # force it to be returned every time
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    code_holder: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.urlparse(self.path).query
            code_holder.update(urllib.parse.parse_qs(q))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Authorized. You can close this tab and return "
                             b"to the terminal.</h2>")

        def log_message(self, *a):  # silence
            pass

    print("\nOpening your browser to approve access...")
    print("If it doesn't open, paste this URL manually:\n" + url + "\n")
    webbrowser.open(url)
    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    server.handle_request()          # serve exactly one request (the redirect)

    if "code" not in code_holder:
        raise SystemExit(f"No authorization code received: {code_holder}")
    code = code_holder["code"][0]

    r = httpx.post(TOKEN_URL, data={
        "code": code,
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=60)
    r.raise_for_status()
    tok = r.json()
    refresh = tok.get("refresh_token")
    if not refresh:
        raise SystemExit("No refresh_token returned. Revoke the app's access at "
                         "https://myaccount.google.com/permissions and re-run "
                         "(prompt=consent should force it).")

    print("\n" + "=" * 64)
    print("SUCCESS — set these three env vars where the pipeline runs:\n")
    print(f"YOUTUBE_CLIENT_ID={args.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={args.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh}")
    print("=" * 64)


if __name__ == "__main__":
    main()
