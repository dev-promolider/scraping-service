"""Pluralsight course catalog through its documented, credentialed GraphQL API.

Official reference:
https://developer.pluralsight.com/docs/getting-started/using-graphql
https://developer.pluralsight.com/docs/getting-started/first-request
https://developer.pluralsight.com/docs/getting-started/faqs

The API requires a Professional or Enterprise plan API key. Its course catalog
does not expose an individual purchase price, so no price is inferred.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from os import environ
from threading import Lock
from time import monotonic
from urllib.parse import urlparse

import requests

from scrapegraph_api.providers.errors import SourceBlockedError


_ENDPOINT = "https://paas-api.pluralsight.com/graphql"
_QUERY = """
query CourseCatalog($first: Int!, $after: String) {
  courseCatalog(first: $first, after: $after) {
    nodes { title url }
    pageInfo { hasNextPage endCursor }
  }
}
"""
_PAGE_SIZE = 1000
_MAX_PAGES = 25
_CACHE_SECONDS = 3600
_LOAD_BUDGET_SECONDS = 35
_LOCK = Lock()
_CACHE: tuple[str, float, tuple[dict[str, str], ...]] | None = None
_STOP_WORDS = {"a", "and", "curso", "cursos", "de", "del", "el", "en", "for", "la", "las", "los", "of", "para", "por", "the", "un", "una", "y"}


class PluralsightBlocked(SourceBlockedError):
    """Pluralsight denied access or rate-limited the authorized API client."""


def _fold(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def _matches(topic: str, title: str) -> bool:
    words = [word for word in re.findall(r"[\w+#]+", _fold(topic)) if word not in _STOP_WORDS]
    if not words:
        return False
    content = _fold(title)
    return all(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", content) for word in words)


def _valid_course_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    parsed = urlparse(value)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not (host == "pluralsight.com" or host.endswith(".pluralsight.com")):
        return ""
    return value


def _load_catalog(api_key: str) -> tuple[dict[str, str], ...]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None and _CACHE[0] == api_key and monotonic() < _CACHE[1]:
            return _CACHE[2]

        courses: list[dict[str, str]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        deadline = monotonic() + _LOAD_BUDGET_SECONDS
        for _ in range(_MAX_PAGES):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Pluralsight no completó el catálogo dentro del tiempo disponible")
            response = requests.post(
                _ENDPOINT,
                json={"query": _QUERY, "variables": {"first": _PAGE_SIZE, "after": cursor}},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=(min(5, remaining), min(12, remaining)),
            )
            if response.status_code in (401, 403, 429):
                raise PluralsightBlocked(f"Pluralsight respondió HTTP {response.status_code}")
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("errors"):
                raise ValueError("Pluralsight rechazó la consulta GraphQL del catálogo")
            data = body.get("data")
            catalog = data.get("courseCatalog") if isinstance(data, dict) else None
            if not isinstance(catalog, dict) or not isinstance(catalog.get("nodes"), list):
                raise ValueError("Pluralsight cambió el formato del catálogo")

            for node in catalog["nodes"]:
                if not isinstance(node, dict):
                    continue
                title = node.get("title")
                url = _valid_course_url(node.get("url"))
                if isinstance(title, str) and title.strip() and url:
                    courses.append({"title": " ".join(title.split()), "url": url})

            page_info = catalog.get("pageInfo")
            if not isinstance(page_info, dict) or not isinstance(page_info.get("hasNextPage"), bool):
                raise ValueError("Pluralsight no informó la paginación del catálogo")
            if not page_info["hasNextPage"]:
                result = tuple(courses)
                _CACHE = (api_key, monotonic() + _CACHE_SECONDS, result)
                return result
            next_cursor = page_info.get("endCursor")
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                raise ValueError("Pluralsight devolvió un cursor de paginación inválido")
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        raise ValueError("El catálogo de Pluralsight excedió el límite de páginas configurado")


def pluralsight(topic: str, max_items: int) -> list[dict[str, str]]:
    """Search the authorized catalog, returning only observed course metadata."""
    if max_items <= 0 or not topic.strip():
        return []
    api_key = environ.get("PLURALSIGHT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Pluralsight requiere PLURALSIGHT_API_KEY de un plan autorizado")
    matches: list[dict[str, str]] = []
    for course in _load_catalog(api_key):
        if _matches(topic, course["title"]):
            matches.append(
                {
                    "title": course["title"],
                    "description": "",
                    "price": "No disponible",
                    "url": course["url"],
                }
            )
            if len(matches) >= max_items:
                break
    return matches


ADAPTERS: dict[str, Callable[[str, int], list[dict[str, str]]]] = {
    "pluralsight": pluralsight,
}
