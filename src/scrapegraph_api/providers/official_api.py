"""Course catalogs served by documented, credentialed provider APIs.

LinkedIn Learning documentation:
https://learn.microsoft.com/en-us/linkedin/learning/getting-started/authentication
https://learn.microsoft.com/en-us/linkedin/learning/reference/learningassets

The catalog API does not provide a per-course purchase price. Never infer one
from a subscription plan or mark a course free merely because no price appears.
"""

from collections.abc import Callable
from os import environ
from threading import Lock
from time import monotonic
from urllib.parse import urlparse

import requests


_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_CATALOG_URL = "https://api.linkedin.com/v2/learningAssets"
_TOKEN_LOCK = Lock()
_CACHED_TOKEN: tuple[str, str, float] | None = None


def _credentials() -> tuple[str, str]:
    client_id = environ.get("LINKEDIN_LEARNING_CLIENT_ID", "").strip()
    client_secret = environ.get("LINKEDIN_LEARNING_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "LinkedIn Learning requiere LINKEDIN_LEARNING_CLIENT_ID y "
            "LINKEDIN_LEARNING_CLIENT_SECRET de una cuenta con acceso a su API"
        )
    return client_id, client_secret


def _access_token(client_id: str, client_secret: str, *, refresh: bool = False) -> str:
    global _CACHED_TOKEN

    with _TOKEN_LOCK:
        if not refresh and _CACHED_TOKEN is not None:
            cached_id, token, deadline = _CACHED_TOKEN
            if cached_id == client_id and monotonic() < deadline:
                return token

        response = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=(3, 8),
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("access_token"), str):
            raise ValueError("LinkedIn Learning devolvió un token inválido")
        token = body["access_token"].strip()
        if not token:
            raise ValueError("LinkedIn Learning devolvió un token vacío")
        expires_in = body.get("expires_in")
        lifetime = max(0, int(expires_in) - 60) if expires_in is not None else 0
        _CACHED_TOKEN = (client_id, token, monotonic() + lifetime)
        return token


def _localized_value(value: object) -> str:
    if isinstance(value, dict):
        text = value.get("value")
        if isinstance(text, str):
            return " ".join(text.split())
    return ""


def linkedin_learning(topic: str, max_items: int) -> list[dict[str, str]]:
    """Search LinkedIn Learning courses with an authorized organization token."""
    if max_items <= 0 or not topic.strip():
        return []

    client_id, client_secret = _credentials()
    token = _access_token(client_id, client_secret)
    params = {
        "q": "criteria",
        "assetFilteringCriteria.assetTypes[0]": "COURSE",
        "assetFilteringCriteria.keyword": topic.strip(),
        "assetPresentationCriteria.sortBy": "RELEVANCE",
        "assetRetrievalCriteria.expandDepth": 1,
        "assetRetrievalCriteria.includeRetired": "false",
        "count": min(max_items, 100),
    }

    def fetch(bearer: str) -> requests.Response:
        return requests.get(
            _CATALOG_URL,
            params=params,
            headers={"Authorization": f"Bearer {bearer}"},
            timeout=(3, 8),
        )

    response = fetch(token)
    if response.status_code == 401:
        # An authorized token may have been revoked before its nominal expiry.
        response = fetch(_access_token(client_id, client_secret, refresh=True))
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or not isinstance(body.get("elements"), list):
        raise ValueError("LinkedIn Learning cambió el formato del catálogo")

    courses: list[dict[str, str]] = []
    for item in body["elements"]:
        if not isinstance(item, dict) or item.get("type") not in (None, "COURSE"):
            continue
        title = _localized_value(item.get("title"))
        details = item.get("details")
        if not isinstance(details, dict):
            continue
        urls = details.get("urls")
        if not isinstance(urls, dict):
            continue
        url = urls.get("webLaunch")
        if not isinstance(url, str):
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ("linkedin.com", "www.linkedin.com"):
            continue
        if not title:
            continue
        description = _localized_value(details.get("description")) or _localized_value(
            details.get("shortDescription")
        )
        courses.append(
            {
                "title": title,
                "description": description,
                "price": "No disponible",
                "url": url,
            }
        )
        if len(courses) >= max_items:
            break
    return courses


ADAPTERS: dict[str, Callable[[str, int], list[dict[str, str]]]] = {
    "linkedin_learning": linkedin_learning,
}
