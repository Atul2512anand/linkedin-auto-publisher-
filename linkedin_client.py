import json
import os
import sys
from datetime import datetime, timezone

import requests

from common import TOKENS_FILE, load_env

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"


def _load_tokens():
    if not os.path.exists(TOKENS_FILE):
        print("ERROR: tokens.json not found. Run: python auth_linkedin.py")
        sys.exit(1)
    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_tokens(tokens):
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)


def _token_expired(tokens):
    obtained_at = datetime.fromisoformat(tokens["obtained_at"])
    expires_in = tokens.get("expires_in") or 0
    age = (datetime.now(timezone.utc) - obtained_at).total_seconds()
    return age > (expires_in - 3600)


def _refresh(tokens):
    client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
    if not tokens.get("refresh_token"):
        return False
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    if not resp.ok:
        print(f"WARNING: token refresh failed ({resp.status_code}). Re-run auth_linkedin.py.")
        return False
    data = resp.json()
    tokens["access_token"] = data["access_token"]
    tokens["obtained_at"] = datetime.now(timezone.utc).isoformat()
    if data.get("refresh_token"):
        tokens["refresh_token"] = data["refresh_token"]
    _save_tokens(tokens)
    return True


def get_access_token():
    load_env()
    tokens = _load_tokens()
    if _token_expired(tokens):
        if not _refresh(tokens):
            print("ERROR: access token expired. Run: python auth_linkedin.py")
            sys.exit(1)
    return tokens["access_token"], tokens


def get_person_id(tokens):
    if tokens.get("person_id"):
        return tokens["person_id"]
    resp = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        timeout=30,
    )
    resp.raise_for_status()
    person_id = resp.json()["sub"]
    tokens["person_id"] = person_id
    _save_tokens(tokens)
    return person_id


def create_post(text):
    access_token, tokens = get_access_token()
    person_id = get_person_id(tokens)
    author_urn = f"urn:li:person:{person_id}"
    version = datetime.now().strftime("%Y%m")

    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": version,
    }
    resp = requests.post(POSTS_URL, json=payload, headers=headers, timeout=30)
    if resp.ok:
        post_id = resp.headers.get("x-restli-id", "")
        return True, f"posted via /rest/posts id={post_id}"

    legacy_payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugcs.MemberNetworkVisibility": "PUBLIC"},
    }
    legacy_headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    resp2 = requests.post(UGC_POSTS_URL, json=legacy_payload, headers=legacy_headers, timeout=30)
    if resp2.ok:
        post_id = resp2.json().get("id", "")
        return True, f"posted via /v2/ugcPosts id={post_id}"
    return False, f"posts API {resp.status_code}: {resp.text[:300]} | ugcPosts {resp2.status_code}: {resp2.text[:300]}"
