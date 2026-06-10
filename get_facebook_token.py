"""
Exchange a short-lived Facebook User Access Token for a long-lived one (~60 days).

Steps:
1. Go to https://developers.facebook.com/tools/explorer
2. Select your app from the dropdown
3. Under "Permissions", add: pages_read_engagement
4. Click "Generate Access Token" and log in when prompted
5. Copy the token shown in the Access Token field
6. Run:  uv run python get_facebook_token.py
7. Paste the token when prompted
"""

import requests
from pathlib import Path

TOKEN_FILE = Path(__file__).parent / "facebook_api_token.txt"


def main():
    current = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""

    # If file contains APP_ID|APP_SECRET, use it; otherwise ask
    if "|" in current and not current.startswith("EAA"):
        app_id, app_secret = current.split("|", 1)
        print(f"Using App ID {app_id} from {TOKEN_FILE.name}")
    else:
        app_id = input("App ID: ").strip()
        app_secret = input("App Secret: ").strip()

    short_lived = input(
        "\nPaste your short-lived User Access Token from Graph API Explorer:\n> "
    ).strip()

    resp = requests.get(
        "https://graph.facebook.com/v20.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived,
        },
        timeout=15,
    )

    if not resp.ok:
        print(f"\nError: {resp.json()}")
        return

    data = resp.json()
    long_lived = data["access_token"]
    expires_in = data.get("expires_in")

    TOKEN_FILE.write_text(long_lived)
    print(f"\nLong-lived token saved to {TOKEN_FILE.name}")
    if expires_in:
        print(f"Expires in: {int(expires_in) // 86400} days")
    print("\nRun: uv run python scan.py")


if __name__ == "__main__":
    main()
