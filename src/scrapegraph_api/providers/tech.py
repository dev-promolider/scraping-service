"""Public course catalogs with no login or protected-content access.

The adapters return observed offer data only. A missing course price is never
interpreted as zero or as the price of a platform subscription.
"""

import re
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scrapegraph_api.providers.errors import SourceBlockedError


class CatalogError(RuntimeError):
    """A catalog cannot be read reliably right now."""


class CatalogBlocked(CatalogError, SourceBlockedError):
    """The site denied automated access or requested a challenge."""


class CatalogStructureChanged(CatalogError):
    """The public page no longer contains recognizable course records."""


_HEADERS = {"User-Agent": "PickleBot course-catalog research/1.0"}
_STOP_WORDS = {"a", "de", "del", "el", "en", "la", "las", "los", "para", "por", "the", "y", "and", "curso", "cursos", "course", "courses"}
_PRICE = re.compile(r"(?<!\w)\$\s*\d+(?:[.,]\d{2})?(?!\w)")
_OFFICIAL_DOMAINS = ("dataquest.io", "linuxfoundation.org")


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
    final_host = (urlparse(response.url).hostname or "").casefold()
    if not any(
        final_host == domain or final_host.endswith("." + domain)
        for domain in _OFFICIAL_DOMAINS
    ):
        raise CatalogBlocked(f"La consulta salió del catálogo oficial: {url}")
    page_text = response.text.casefold()
    if any(marker in page_text for marker in ('cf-challenge', 'id="captcha"', 'class="g-recaptcha"')):
        raise CatalogBlocked(f"El sitio solicitó una verificación en {url}")
    return BeautifulSoup(response.content, "html.parser")


def _text(value: str) -> str:
    return " ".join(value.split())


def _matches(topic: str, text: str) -> bool:
    words = [word for word in re.findall(r"[\w+#]+", topic.casefold()) if word not in _STOP_WORDS]
    if not words:
        return False
    haystack = text.casefold()
    return all(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", haystack) for word in words)


def _course_url(base: str, href: str, prefix: str) -> str | None:
    url = urljoin(base, href)
    parsed = urlparse(url)
    expected = urlparse(base)
    if parsed.scheme != "https" or parsed.hostname != expected.hostname:
        return None
    if not re.fullmatch(rf"{re.escape(prefix)}[^/]+/?", parsed.path):
        return None
    return url


def _observed_card_price(card_text: str) -> str:
    """Return a single displayed amount without inferring its currency code."""
    observed = _PRICE.findall(card_text)
    return observed[0].replace(" ", "") if len(observed) == 1 else "No disponible"


def _details(url: str) -> tuple[str, str]:
    soup = _fetch(url)
    heading = soup.find("h1")
    title = _text(heading.get_text(" ", strip=True)) if heading else ""
    description_tag = soup.find("meta", attrs={"name": "description"})
    description = _text(str(description_tag.get("content", ""))) if description_tag else ""
    if not description:
        main = soup.find("main") or soup
        paragraph = main.find("p")
        description = _text(paragraph.get_text(" ", strip=True)) if paragraph else ""
    if not title:
        raise CatalogStructureChanged(f"No se encontró el título del curso: {url}")
    return title, description


def dataquest(topic: str, max_items: int) -> list[dict[str, str]]:
    """Read the official public sitemap, then selected public course pages."""
    if max_items <= 0 or not topic.strip():
        return []
    base = "https://www.dataquest.io/sitemap/"
    soup = _fetch(base)
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for link in soup.select("a[href]"):
        url = _course_url(base, str(link.get("href", "")), "/course/")
        title = _text(link.get_text(" ", strip=True))
        if url and url not in seen and title and _matches(topic, title):
            seen.add(url)
            candidates.append((url, title))
    if not any(_course_url(base, str(a.get("href", "")), "/course/") for a in soup.select("a[href]")):
        raise CatalogStructureChanged("El índice público de Dataquest ya no enumera cursos")
    result: list[dict[str, str]] = []
    for url, indexed_title in candidates[: min(max_items, 3)]:
        title, description = _details(url)
        if _matches(topic, f"{title} {description}"):
            result.append({"title": title or indexed_title, "description": description, "price": "No disponible", "url": url})
    return result


def linux_foundation(topic: str, max_items: int) -> list[dict[str, str]]:
    """Read course offers from the official Linux Foundation training catalog."""
    if max_items <= 0 or not topic.strip():
        return []
    base = "https://training.linuxfoundation.org/full-catalog/?_sft_product_type=training"
    soup = _fetch(base)
    cards: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for link in soup.select("a[href]"):
        url = _course_url(base, str(link.get("href", "")), "/training/")
        if not url or url in seen:
            continue
        seen.add(url)
        card_text = _text(link.get_text(" ", strip=True))
        if _matches(topic, card_text):
            price = _observed_card_price(card_text)
            cards.append((url, card_text, price))
    if not any(_course_url(base, str(a.get("href", "")), "/training/") for a in soup.select("a[href]")):
        raise CatalogStructureChanged("El catálogo de Linux Foundation ya no enumera cursos")
    result: list[dict[str, str]] = []
    for url, card_text, price in cards[: min(max_items, 3)]:
        title, description = _details(url)
        if _matches(topic, f"{title} {description} {card_text}"):
            result.append({"title": title, "description": description, "price": price, "url": url})
    return result


ADAPTERS: dict[str, Callable[[str, int], list[dict[str, str]]]] = {
    "dataquest": dataquest,
    "linux_foundation": linux_foundation,
}
