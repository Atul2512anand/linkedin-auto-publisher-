import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone

import requests

from common import TOKENS_FILE, load_env

TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"
UPLOADS_URL = "https://api.linkedin.com/rest/uploads?action=registerUpload"
DOCUMENTS_INIT_URL = "https://api.linkedin.com/rest/documents?action=initializeUpload"


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


def get_author_urn(tokens):
    author_type = os.environ.get(
        "LINKEDIN_AUTHOR_TYPE", tokens.get("author_type", "person")
    ).strip().lower()
    if author_type == "organization":
        org_id = os.environ.get("LINKEDIN_ORGANIZATION_ID", "").strip()
        if not org_id:
            print("ERROR: LINKEDIN_AUTHOR_TYPE=organization but LINKEDIN_ORGANIZATION_ID "
                  "is not set in .env")
            sys.exit(1)
        return f"urn:li:organization:{org_id}"
    return f"urn:li:person:{get_person_id(tokens)}"


def _api_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": datetime.now().strftime("%Y%m"),
        "Content-Type": "application/json",
    }


def upload_image(path, author_urn, token):
    body = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": author_urn,
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ],
        }
    }
    resp = requests.post(UPLOADS_URL, json=body, headers=_api_headers(token), timeout=30)
    resp.raise_for_status()
    value = resp.json()["value"]
    asset, upload_url = value["asset"], value["uploadUrl"]
    with open(path, "rb") as f:
        data = f.read()
    put = requests.put(
        upload_url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "image/png"},
        timeout=180,
    )
    put.raise_for_status()
    return asset


def upload_document(path, author_urn, token):
    body = {"initializeUploadRequest": {"owner": author_urn}}
    resp = requests.post(DOCUMENTS_INIT_URL, json=body, headers=_api_headers(token), timeout=30)
    resp.raise_for_status()
    value = resp.json()["value"]
    doc_urn, upload_url = value["document"], value["uploadUrl"]
    with open(path, "rb") as f:
        data = f.read()
    put = requests.put(
        upload_url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/pdf"},
        timeout=300,
    )
    put.raise_for_status()
    status_url = f"https://api.linkedin.com/rest/documents/{urllib.parse.quote(doc_urn, safe='')}"
    deadline = time.time() + 300
    last_status = "unknown"
    time.sleep(3)
    while time.time() < deadline:
        check = requests.get(status_url, headers=_api_headers(token), timeout=30)
        if check.ok:
            last_status = check.json().get("status", "unknown")
            if last_status in ("DOCUMENT_PROCESSED", "SUCCEEDED", "AVAILABLE"):
                return doc_urn
            if last_status == "FAILED":
                raise RuntimeError(f"document processing failed: {check.text[:200]}")
            print(f"  document status: {last_status}...")
        else:
            last_status = f"HTTP {check.status_code}"
        time.sleep(5)
    raise RuntimeError(f"document processing timed out (last status: {last_status})")


def create_post(text, media_path=None):
    access_token, tokens = get_access_token()
    author_urn = get_author_urn(tokens)
    version = datetime.now().strftime("%Y%m")

    media_id, media_kind = None, None
    if media_path:
        try:
            if media_path.lower().endswith(".pdf"):
                media_id = upload_document(media_path, author_urn, access_token)
                media_kind = "document"
                print(f"Carousel uploaded: {media_id}")
            else:
                media_id = upload_image(media_path, author_urn, access_token)
                media_kind = "image"
                print(f"Image uploaded: {media_id}")
        except Exception as exc:
            print(f"WARNING: media upload failed ({exc}). Falling back to text-only post.")

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
    if media_kind == "document":
        doc_title = os.path.splitext(os.path.basename(media_path))[0].replace("_", " ")
        payload["content"] = {"media": {"id": media_id, "title": doc_title}}
    elif media_kind == "image":
        payload["content"] = {"media": [{"id": media_id}]}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": version,
    }
    resp = requests.post(POSTS_URL, json=payload, headers=headers, timeout=30)
    if resp.ok:
        post_id = resp.headers.get("x-restli-id", "")
        label = f"posted with {media_kind}" if media_kind else "posted"
        return True, f"{label} via /rest/posts id={post_id}"

    if media_kind:
        legacy_media = [{
            "status": "READY",
            "title": {"text": os.path.basename(media_path)},
            "originalUrl": media_id,
        }]
        category = "DOCUMENT" if media_kind == "document" else "IMAGE"
        legacy_payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": category,
                    "media": legacy_media,
                }
            },
            "visibility": {"com.linkedin.ugcs.MemberNetworkVisibility": "PUBLIC"},
        }
    else:
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
        label = f"posted with {media_kind}" if media_kind else "posted"
        return True, f"{label} via /v2/ugcPosts id={post_id}"
    return False, f"posts API {resp.status_code}: {resp.text[:300]} | ugcPosts {resp2.status_code}: {resp2.text[:300]}"
