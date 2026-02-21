#!/usr/bin/env python3
"""
Strava OAuth2 initial setup script.

Run this ONCE to obtain your access and refresh tokens.
Requires STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env.

Usage:
    uv run python scripts/setup_oauth.py
"""

import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv, set_key

load_dotenv()

CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8765/callback"
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")

authorization_code: str | None = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        global authorization_code
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            if "code" in params:
                authorization_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>&#8203;\u8a8d\u8a3c\u6210\u529f\uff01</h2>"
                    b"<p>\u3053\u306e\u30bf\u30d6\u3092\u9589\u3058\u3066\u30bf\u30fc\u30df\u30ca\u30eb\u306b\u623b\u3063\u3066\u304f\u3060\u3055\u3044\u3002</p></body></html>"
                )
            else:
                error = params.get("error", ["unknown"])[0]
                self.send_response(400)
                self.end_headers()
                self.wfile.write(f"Error: {error}".encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass  # suppress server logs


def main() -> None:
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: STRAVA_CLIENT_ID と STRAVA_CLIENT_SECRET を .env に設定してください。")
        print("\n手順:")
        print("  1. https://www.strava.com/settings/api にアクセス")
        print("  2. アプリを作成（Authorization Callback Domain: localhost）")
        print("  3. Client ID と Client Secret を .env にコピー")
        sys.exit(1)

    # Build authorization URL
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "activity:read_all",
    }
    auth_url = f"https://www.strava.com/oauth/authorize?{urlencode(auth_params)}"

    print("=" * 60)
    print("Strava OAuth2 セットアップ")
    print("=" * 60)
    print(f"\nブラウザで以下のURLを開き、アクセスを許可してください：\n\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Start local callback server
    print("コールバックを待機中... (http://localhost:8765)")
    server = HTTPServer(("localhost", 8765), OAuthCallbackHandler)
    server.timeout = 120
    server.handle_request()

    if not authorization_code:
        print("ERROR: 認証コードを取得できませんでした。")
        sys.exit(1)

    # Exchange code for tokens
    print("\nトークンを取得中...")
    response = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": authorization_code,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    response.raise_for_status()
    token_data = response.json()

    # Save to .env
    set_key(ENV_PATH, "STRAVA_ACCESS_TOKEN", token_data["access_token"])
    set_key(ENV_PATH, "STRAVA_REFRESH_TOKEN", token_data["refresh_token"])
    set_key(ENV_PATH, "STRAVA_TOKEN_EXPIRES_AT", str(token_data["expires_at"]))

    athlete = token_data.get("athlete", {})
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()

    print("\n✅ セットアップ完了！")
    print(f"   アスリート: {name}")
    print(f"   アクセストークンを .env に保存しました。")
    print("\n次のコマンドでアドバイスを取得できます：")
    print("   uv run python scripts/run_advisor.py")


if __name__ == "__main__":
    main()
