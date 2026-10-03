"""Public program catalogs for Le Wagon and 4Geeks Academy.

These adapters read only public program pages. A missing program price is
reported as unavailable; salary, scholarship, and subscription figures are
never used as tuition. Neither source was live-tested from this workspace.
"""

import json
import re
import unicodedata
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapegraph_api.providers.errors import SourceBlockedError


class CatalogError(RuntimeError):
    """A public catalog could not be read reliably."""


class CatalogBlocked(CatalogError, SourceBlockedError):
    """The source denied access or requested a challenge."""


class CatalogStructureChanged(CatalogError):
    """The page no longer exposes recognizable program links or details."""


_HEADERS = {"User-Agent": "PickleBot/1.0 (public course catalog research)"}
_STOP_WORDS = {
    "a", "and", "curso", "cursos", "de", "del", "el", "en", "for", "la",
    "las", "los", "of", "para", "por", "the", "un", "una", "y",
}
_SOURCE_CONFIG = {
    "le_wagon": ("https://www.lewagon.com/", {"lewagon.com", "www.lewagon.com"}),
    "four_geeks": ("https://4geeks.com/en/home", {"4geeks.com", "www.4geeks.com"}),
}


def _text(value: str) -> str:
    return " ".join(value.split())


def _fold(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )


def _relevant(topic: str, *fields: str) -> bool:
    words = [word for word in re.findall(r"[\w+#]+", _fold(topic)) if word not in _STOP_WORDS]
    if not words:
        return False
    content = _fold(" ".join(fields))
    return all(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", content) for word in words)


def _fetch(url: str) -> BeautifulSoup:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=(3, 8))
    except requests.RequestException as exc:
        raise CatalogError(f"No se pudo consultar {url}: {exc}") from exc
    if response.status_code in (401, 403, 429):
        raise CatalogBlocked(f"Acceso bloqueado por {url}: HTTP {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise CatalogError(f"Falló la consulta a {url}: HTTP {response.status_code}") from exc
    expected = urlparse(url).hostname
    final = urlparse(response.url).hostname
    if final != expected:
        raise CatalogBlocked(f"La consulta salió del catálogo público: {url}")
    soup = BeautifulSoup(response.content, "html.parser")
    title = _text(soup.title.get_text(" ", strip=True)).casefold() if soup.title else ""
    if "cf-challenge" in response.text.casefold() or "captcha" in title or "just a moment" in title:
        raise CatalogBlocked(f"El sitio solicitó una verificación en {url}")
    return soup


def _program_url(source: str, href: str) -> str | None:
    base, domains = _SOURCE_CONFIG[source]
    parsed = urlparse(urljoin(base, href))
    if parsed.scheme != "https" or parsed.hostname not in domains:
        return None
    path = parsed.path.rstrip("/")
    if source == "le_wagon":
        accepted = bool(re.fullmatch(r"/[a-z0-9-]+-course", path))
    else:
        accepted = bool(re.fullmatch(r"/(?:en/)?(?:career-programs|bootcamp)/[a-z0-9-]+", path))
    if not accepted:
        return None
    return parsed._replace(query="", fragment="").geturl()


def _course_offer(node: object, heading: str) -> str:
    if isinstance(node, list):
        for child in node:
            price = _course_offer(child, heading)
            if price != "No disponible":
                return price
        return "No disponible"
    if not isinstance(node, dict):
        return "No disponible"
    if "@graph" in node:
        return _course_offer(node["@graph"], heading)
    types = node.get("@type") or []
    types = [types] if isinstance(types, str) else types
    if "Course" not in types or _fold(str(node.get("name", ""))) != _fold(heading):
        return "No disponible"
    offers = node.get("offers", [])
    offers = [offers] if isinstance(offers, dict) else offers
    for offer in offers if isinstance(offers, list) else []:
        if not isinstance(offer, dict) or offer.get("@type") != "Offer":
            continue
        currency = str(offer.get("priceCurrency") or "").upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            continue
        try:
            amount = Decimal(str(offer.get("price")))
        except (InvalidOperation, TypeError):
            continue
        if amount.is_finite() and amount >= 0:
            return f"{currency} {amount:.2f}"
    return "No disponible"


def _details(url: str) -> tuple[str, str, str]:
    soup = _fetch(url)
    heading = soup.find("h1")
    title = _text(heading.get_text(" ", strip=True)) if heading else ""
    host = urlparse(url).hostname or ""
    canonical_title = ""
    if host.endswith(("lewagon.com", "4geeks.com")):
        canonical = soup.find("meta", property="og:title")
        if canonical is not None:
            canonical_title = _text(str(canonical.get("content") or ""))
            if canonical_title:
                title = canonical_title
        elif soup.title:
            title = _text(soup.title.get_text(" ", strip=True))
        title = re.sub(r"\s*[|–-]\s*Le Wagon\s*$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s*[|–-]\s*4Geeks.*$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+Career Program\s*$", "", title, flags=re.IGNORECASE)
    if host.endswith("4geeks.com") and not canonical_title:
        # Sus H1 promocionales describen la promesa comercial; el slug nombra
        # de forma estable el programa que aparece en el enlace oficial.
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        if slug:
            title = slug.replace("-", " ").title().replace("Ai ", "AI ")
    if not title or title.casefold() in {"page not found", "404"}:
        raise CatalogStructureChanged(f"No se encontró el programa en {url}")
    tag = soup.find("meta", attrs={"name": "description"})
    description = _text(str(tag.get("content") or "")) if tag else ""
    if not description:
        main = soup.find("main") or soup
        paragraph = main.find("p")
        description = _text(paragraph.get_text(" ", strip=True)) if paragraph else ""
    price = "No disponible"
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        price = _course_offer(data, title)
        if price != "No disponible":
            break
    return title, description, price


def _search(source: str, topic: str, max_items: int) -> list[dict[str, str]]:
    if max_items <= 0 or not topic.strip():
        return []
    base, _ = _SOURCE_CONFIG[source]
    soup = _fetch(base)
    links: dict[str, str] = {}
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "")
        url = _program_url(source, href)
        if url:
            links.setdefault(url, _text(anchor.get_text(" ", strip=True)))
    if not links:
        raise CatalogStructureChanged(f"No se encontraron enlaces de programas en {base}")
    offers: list[dict[str, str]] = []
    first_error: CatalogError | None = None
    successful_pages = 0
    ordered_links = sorted(
        links.items(),
        key=lambda item: not _relevant(topic, item[1], urlparse(item[0]).path),
    )
    for url, _ in ordered_links[: min(max_items * 2, 4)]:
        try:
            title, description, price = _details(url)
        except CatalogBlocked:
            raise
        except CatalogError as exc:
            first_error = first_error or exc
            continue
        successful_pages += 1
        if _relevant(topic, title, description):
            offers.append({"title": title, "description": description, "price": price, "url": url})
            if len(offers) >= max_items:
                break
    if not successful_pages and first_error:
        raise first_error
    return offers


def le_wagon(topic: str, max_items: int) -> list[dict[str, str]]:
    return _search("le_wagon", topic, max_items)


def four_geeks(topic: str, max_items: int) -> list[dict[str, str]]:
    return _search("four_geeks", topic, max_items)


ADAPTERS: dict[str, Callable[[str, int], list[dict[str, str]]]] = {
    "le_wagon": le_wagon,
    "four_geeks": four_geeks,
}
