import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from common import TOKENS_FILE, load_env

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
ORGS_URL = (
    "https://api.linkedin.com/v2/organizationAcls"
    "?q=roleAssignee&role=ADMINISTRATOR&state=APPROVED"
    "&projection=(elements*(organizationalTarget~(localizedName,vanityName)))"
)
SCOPES_PERSON = "openid profile w_member_social"
SCOPES_ORG_EXTRA = " w_organization_social r_organization_social"

result = {"code": None, "state": None}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        result["code"] = params.get("code", [None])[0]
        result["state"] = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>LinkedIn auth complete. You can close this tab.</h2>")

    def log_message(self, *args):
        pass


def main():
    load_env()
    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
    redirect_uri = os.environ.get("LINKEDIN_REDIRECT_URI", "http://localhost:8913/callback")

    if not client_id or not client_secret:
        print("ERROR: set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env first.")
        sys.exit(1)

    state = secrets.token_urlsafe(16)
    author_type = os.environ.get("LINKEDIN_AUTHOR_TYPE", "person").strip().lower()
    scopes = SCOPES_PERSON + (SCOPES_ORG_EXTRA if author_type == "organization" else "")
    if author_type == "organization":
        print("Mode: COMPANY PAGE posting (organization scopes included).")
    query = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
    })
    auth_url = f"{AUTH_URL}?{query}"

    port = urlparse(redirect_uri).port or 80
    server = HTTPServer(("localhost", port), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("Opening browser for LinkedIn login...")
    print(f"If the browser does not open, paste this URL manually:\n\n{auth_url}\n")
    webbrowser.open(auth_url)

    deadline = time.time() + 300
    while time.time() < deadline and result["code"] is None:
        time.sleep(0.5)

    if result["code"] is None:
        print("ERROR: timed out waiting for LinkedIn callback.")
        sys.exit(1)

    if result["state"] != state:
        print("ERROR: OAuth state mismatch.")
        sys.exit(1)

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    token_data = resp.json()

    userinfo = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
        timeout=30,
    )
    person_id = None
    name = None
    if userinfo.ok:
        info = userinfo.json()
        person_id = info.get("sub")
        name = info.get("name")
    else:
        print(f"WARNING: could not fetch userinfo ({userinfo.status_code}). It will be fetched later.")

    tokens = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_in": token_data.get("expires_in"),
        "obtained_at": datetime.now(timezone.utc).isoformat(),
        "person_id": person_id,
        "name": name,
        "author_type": author_type,
    }
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)

    server.shutdown()
    print(f"SUCCESS. Tokens saved to {TOKENS_FILE}")
    if name:
        print(f"Authenticated as: {name} (urn:li:person:{person_id})")

    if author_type == "organization":
        print("\nFetching company pages you admin...")
        try:
            orgs = requests.get(
                ORGS_URL,
                headers={
                    "Authorization": f"Bearer {tokens['access_token']}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )
            if orgs.ok:
                elements = orgs.json().get("elements", [])
                if not elements:
                    print("No admin pages found for this account.")
                for el in elements:
                    target = el.get("organizationalTarget", "")
                    info = el.get("organizationalTarget~", {})
                    label = info.get("localizedName") or info.get("vanityName") or "(unnamed)"
                    print(f"  - {label}: {target}")
                print("\nCopy the urn:li:organization:<ID> of your page into .env:")
                print("LINKEDIN_AUTHOR_TYPE=organization")
                print("LINKEDIN_ORGANIZATION_ID=<the numeric ID>")
            else:
                print(f"WARNING: could not list pages ({orgs.status_code}).")
                print("Set LINKEDIN_ORGANIZATION_ID manually in .env.")
        except Exception as exc:
            print(f"WARNING: could not list pages: {exc}")


if __name__ == "__main__":
    main()
