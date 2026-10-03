"""Adaptadores para catálogos públicos de formación en Latinoamérica.

Cada función consulta únicamente páginas públicas de la plataforma indicada.
No accede a cuentas, contenidos de clase ni mecanismos de pago.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Callable
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from scrapegraph_api.providers.errors import SourceBlockedError


class ProviderError(RuntimeError):
    """La fuente rechazó la consulta o cambió su estructura pública."""


class ProviderBlocked(ProviderError, SourceBlockedError):
    """La fuente negó el acceso o solicitó una verificación."""


_HEADERS = {"User-Agent": "PickleBotCourseCatalog/1.0 (+public course metadata)"}
_STOPWORDS = {"de", "del", "la", "el", "los", "las", "y", "en", "con", "para", "curso", "cursos", "online"}
_MISSING_PRICE = "No disponible"
_MAX_DETAIL_REQUESTS = 4


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


def _relevant(topic: str, *fields: str) -> bool:
    terms = [word for word in re.findall(r"[a-z0-9]+", _normalized(topic)) if word not in _STOPWORDS]
    if not terms:
        return False
    text = _normalized(" ".join(fields))
    return all(word in text for word in terms)


def _fetch(url: str, domain: str) -> BeautifulSoup:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=(3, 8))
    except requests.Timeout as exc:
        raise ProviderError(f"Tiempo de espera agotado en {domain}: {url}") from exc
    except requests.RequestException as exc:
        raise ProviderError(f"No se pudo consultar {domain}: {exc}") from exc

    if response.status_code in (401, 403, 429):
        raise ProviderBlocked(f"{domain} rechazó la consulta con HTTP {response.status_code}")
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ProviderError(f"{domain} respondió HTTP {response.status_code}: {url}") from exc

    host = (urlparse(response.url).hostname or "").lower()
    if host != domain and not host.endswith("." + domain):
        raise ProviderError(f"{domain} redirigió la consulta fuera de su dominio: {response.url}")
    soup = BeautifulSoup(response.content, "html.parser")
    page_title = _normalized(_clean(soup.title.get_text(" ", strip=True) if soup.title else ""))
    if any(marker in page_title for marker in ("captcha", "access denied", "just a moment", "verify you are human")):
        raise ProviderBlocked(f"{domain} mostró una verificación de acceso")
    return soup


def _slug_title(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    return _clean(slug.replace("-", " ").replace("_", " ")).title()


def _card(link: Tag) -> Tag:
    """Encuentra la tarjeta más cercana sin capturar toda la página."""
    for node in [link, *list(link.parents)[:6]]:
        if not isinstance(node, Tag):
            continue
        text = _clean(node.get_text(" ", strip=True))
        if len(text) > 1400:
            break
        if node.select_one("h2, h3, h4") and (node.name == "a" or len(text) > 45):
            return node
    return link


def _card_fields(link: Tag, url: str) -> tuple[str, str, Tag]:
    card = _card(link)
    heading = link.select_one("h2, h3, h4")
    title = _clean(heading.get_text(" ", strip=True)) if heading else ""
    if not title:
        label = _clean(link.get_text(" ", strip=True))
        if label and len(label) < 110 and not re.search(r"^(ver|saber|conocer|empezar|más información)", label, re.I):
            title = label
    if not title:
        heading = card.select_one("h2, h3, h4")
        title = _clean(heading.get_text(" ", strip=True)) if heading else ""
    if not title:
        image = card.select_one("img[alt]")
        title = _clean(image.get("alt")) if image else ""
    if not title:
        title = _slug_title(url)
    title = re.sub(r"^\d+\s+(?:mes(?:es)?|semanas?)\s+", "", title, flags=re.I)
    paragraphs = [_clean(p.get_text(" ", strip=True)) for p in card.select("p")]
    description = next((part for part in paragraphs if 25 <= len(part) <= 500 and part != title), "")
    return title, description, card


def _detail_data(url: str, domain: str) -> tuple[str, str]:
    soup = _fetch(url, domain)
    headings = [_clean(tag.get_text(" ", strip=True)) for tag in soup.select("h1")]
    title = next((name for name in headings if _normalized(name) not in {"curso online", "curso online de"}), "")
    if not title and headings:
        title = headings[0]
    meta = soup.select_one('meta[name="description"], meta[property="og:description"]')
    if meta and _clean(meta.get("content")):
        return title, _clean(meta.get("content"))
    for label in soup.select("h2, h3, h4"):
        if _normalized(_clean(label.get_text(" ", strip=True))) in {"descripcion", "sobre el curso"}:
            paragraph = label.find_next("p")
            if paragraph:
                return title, _clean(paragraph.get_text(" ", strip=True))[:650]
    main = soup.select_one("main") or soup
    description = next((_clean(p.get_text(" ", strip=True))[:650] for p in main.select("p") if len(_clean(p.get_text(" ", strip=True))) >= 35), "")
    return title, description


def _detail_description(url: str, domain: str) -> str:
    return _detail_data(url, domain)[1]


def _catalog(
    topic: str,
    max_items: int,
    pages: tuple[str, ...],
    domain: str,
    allowed_link: Callable[[str], bool],
    *,
    detail: bool = True,
    detail_title: bool = False,
    free_pages: frozenset[str] = frozenset(),
) -> list[dict[str, str]]:
    if max_items <= 0 or not _clean(topic):
        return []
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    details_used = 0
    links_found = 0
    for page in pages:
        soup = _fetch(page, domain)
        for link in soup.select("a[href]"):
            url = urljoin(page, _clean(link.get("href")))
            if not allowed_link(url):
                continue
            links_found += 1
            if url in seen:
                continue
            seen.add(url)
            title, description, _ = _card_fields(link, url)
            if not _relevant(topic, title, description, _slug_title(url)):
                continue
            if detail and (not description or detail_title) and details_used < _MAX_DETAIL_REQUESTS:
                detail_name, detail_description = _detail_data(url, domain)
                if detail_title and detail_name:
                    title = detail_name
                description = detail_description or description
                details_used += 1
            if not _relevant(topic, title, description):
                continue
            results.append(
                {
                    "title": title,
                    "description": description,
                    "price": "Gratis" if page in free_pages else _MISSING_PRICE,
                    "url": url,
                }
            )
            if len(results) >= max_items:
                return results
    if links_found == 0:
        raise ProviderError(f"No se encontraron enlaces de cursos en el catálogo de {domain}; revisar su estructura")
    return results


def _path_matches(url: str, domain: str, pattern: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return (host == domain or host.endswith("." + domain)) and re.fullmatch(pattern, parsed.path.rstrip("/")) is not None


def _platzi_course_data(url: str) -> tuple[str, str, dict[str, object]]:
    soup = _fetch(url, "platzi.com")
    json_courses: list[dict] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        records = payload if isinstance(payload, list) else [payload]
        pending_records = list(records)
        while pending_records:
            record = pending_records.pop()
            if not isinstance(record, dict):
                continue
            graph = record.get("@graph", [])
            if isinstance(graph, list):
                pending_records.extend(item for item in graph if isinstance(item, dict))
            if record.get("@type") == "Course":
                json_courses.append(record)

    course = json_courses[0] if json_courses else {}
    heading = soup.select_one("h1")
    title = _clean(course.get("name")) or (
        _clean(heading.get_text(" ", strip=True)) if heading else ""
    )
    meta_description = soup.select_one('meta[name="description"], meta[property="og:description"]')
    description = _clean(course.get("description")) or (
        _clean(meta_description.get("content")) if meta_description else ""
    )
    page_text = _clean(soup.get_text(" ", strip=True))

    rating = course.get("aggregateRating") or {}
    instructors = course.get("instructor") or course.get("author") or []
    if isinstance(instructors, dict):
        instructors = [instructors]
    instructor_names = [
        _clean(person.get("name")) for person in instructors
        if isinstance(person, dict) and _clean(person.get("name"))
    ] if isinstance(instructors, list) else []

    learning_routes: list[dict[str, str]] = []
    for link in soup.select('a[href*="/ruta/"]'):
        route_url = urljoin(url, _clean(link.get("href")))
        route_title = _clean(link.get_text(" ", strip=True))
        is_route = _path_matches(route_url, "platzi.com", r"/ruta/[^/]+")
        is_new_route = all(item["url"] != route_url for item in learning_routes)
        if route_title and is_route and is_new_route:
            learning_routes.append({"title": route_title, "url": route_url})
        if len(learning_routes) == 6:
            break

    level = _clean(course.get("educationalLevel"))
    if not level:
        match = re.search(r"\b(b[aá]sico|intermedio|avanzado)\b", page_text, re.I)
        level = _clean(match.group(1)) if match else ""
    class_match = re.search(r"\b(\d{1,3})\s+clases\b", page_text, re.I)
    content_match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s+horas?\s+(?:de contenido|de video|de v[ií]deo)\b",
        page_text,
        re.I,
    )
    practice_match = re.search(
        r"\b(\d+(?:[.,]\d+)?)\s+horas?\s+de pr[aá]ctica\b",
        page_text,
        re.I,
    )

    metadata: dict[str, object] = {
        key: value for key, value in {
            "level": level or None,
            "class_count": int(class_match.group(1)) if class_match else None,
            "content_hours": content_match.group(1).replace(",", ".") if content_match else None,
            "practice_hours": practice_match.group(1).replace(",", ".") if practice_match else None,
            "rating": (
                _clean(rating.get("ratingValue"))
                if isinstance(rating, dict) and rating.get("ratingValue") is not None
                else None
            ),
            "review_count": (
                int(rating["ratingCount"])
                if isinstance(rating, dict)
                and str(rating.get("ratingCount", "")).isdigit()
                else None
            ),
            "instructors": instructor_names or None,
            "learning_routes": learning_routes or None,
        }.items() if value is not None
    }
    return title, description[:650], metadata


def platzi(topic: str, max_items: int) -> list[dict[str, object]]:
    if max_items <= 0 or not _clean(topic):
        return []
    page = f"https://platzi.com/buscar/?search={quote(topic)}"
    soup = _fetch(page, "platzi.com")
    results: list[dict[str, object]] = []
    seen: set[str] = set()
    for link in soup.select("a[href]"):
        url = urljoin(page, _clean(link.get("href")))
        if not _path_matches(url, "platzi.com", r"/cursos/[^/]+") or url in seen:
            continue
        seen.add(url)
        title, description, _ = _card_fields(link, url)
        if not _relevant(topic, title, description, _slug_title(url)):
            continue
        title, detail_description, metadata = _platzi_course_data(url)
        description = detail_description or description
        if not title or not _relevant(topic, title, description):
            continue
        results.append(
            {
                "title": title,
                "description": description,
                "price": _MISSING_PRICE,
                "url": url,
                "metadata": metadata,
            }
        )
        if len(results) >= min(max_items, _MAX_DETAIL_REQUESTS):
            break
    return results


def coderhouse(topic: str, max_items: int) -> list[dict[str, str]]:
    page = "https://www.coderhouse.com/mx/cursos"
    return _catalog(topic, max_items, (page,), "coderhouse.com", lambda url: _path_matches(url, "coderhouse.com", r"/mx/cursos/[^/]+"))


def _edu_price(card: Tag | None, currency: str) -> str:
    """Toma el precio actual visible de la tarjeta, no el precio base JSON-LD."""
    if card is None or not re.fullmatch(r"[A-Z]{3}", currency):
        return _MISSING_PRICE
    symbol = {"PEN": r"S/", "BRL": r"R\$", "USD": r"US\$", "MXN": r"\$"}.get(currency)
    if not symbol:
        return _MISSING_PRICE
    for crossed in card.select("s, del, [class*='line-through']"):
        parent = crossed.parent
        if not isinstance(parent, Tag):
            continue
        amounts = re.findall(rf"{symbol}\s*([\d.,]+)", parent.get_text(" ", strip=True))
        if len(amounts) >= 2:
            return f"{amounts[-1]} {currency}"
    return _MISSING_PRICE


def educacionit(topic: str, max_items: int) -> list[dict[str, str]]:
    if max_items <= 0 or not _clean(topic):
        return []
    index = _fetch("https://www.educacionit.com/cursos-de-programacion", "educacionit.com")
    category_urls: list[str] = []
    for link in index.select("a[href]"):
        url = urljoin("https://www.educacionit.com", _clean(link.get("href")))
        if _path_matches(url, "educacionit.com", r"/cursos-de-[^/]+") and _relevant(topic, _clean(link.get_text(" ", strip=True))):
            if url not in category_urls:
                category_urls.append(url)
    if not category_urls:
        category_urls = ["https://www.educacionit.com/cursos-de-programacion"]

    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for page in category_urls[:2]:
        soup = index if page == "https://www.educacionit.com/cursos-de-programacion" else _fetch(page, "educacionit.com")
        lists: list[dict] = []
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                payload = json.loads(script.string or script.get_text())
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("@type") == "ItemList":
                lists.append(payload)
        if not lists:
            raise ProviderError("EducaciónIT cambió los metadatos públicos de cursos")
        for listing in lists:
            for entry in listing.get("itemListElement", []):
                course = entry.get("item", {}) if isinstance(entry, dict) else {}
                if not isinstance(course, dict) or course.get("@type") != "Course":
                    continue
                title = _clean(course.get("name"))
                description = _clean(course.get("description"))
                url = _clean(course.get("url"))
                if not title or not url or url in seen or not _relevant(topic, title, description):
                    continue
                if not _path_matches(url, "educacionit.com", r"/curso-[^/]+"):
                    continue
                seen.add(url)
                card = soup.find("a", href=urlparse(url).path)
                offers = course.get("offers") or []
                offer = offers[0] if isinstance(offers, list) and offers else offers if isinstance(offers, dict) else {}
                currency = _clean(offer.get("priceCurrency")) if isinstance(offer, dict) else ""
                results.append({"title": title, "description": description, "price": _edu_price(card, currency), "url": url})
                if len(results) >= max_items:
                    return results
    return results


def ebac(topic: str, max_items: int) -> list[dict[str, str]]:
    page = "https://ebac.mx/cursos"
    excluded = {"cursos", "blog", "contacto", "nosotros", "politica", "terminos", "login", "registro"}

    def eligible(url: str) -> bool:
        path = urlparse(url).path.strip("/")
        return _path_matches(url, "ebac.mx", r"/[^/]+") and path not in excluded and not path.startswith("cursos-")

    return _catalog(topic, max_items, (page,), "ebac.mx", eligible, detail_title=True)


def senpai(topic: str, max_items: int) -> list[dict[str, str]]:
    page = "https://www.senpaiacademy.com/"
    return _catalog(topic, max_items, (page,), "senpaiacademy.com", lambda url: _path_matches(url, "senpaiacademy.com", r"/(curso|carrera)/[^/]+"))


def digitalhouse(topic: str, max_items: int) -> list[dict[str, str]]:
    if max_items <= 0 or not _clean(topic):
        return []
    page = "https://www.digitalhouse.com/explorar"
    soup = _fetch(page, "digitalhouse.com")
    cert_links = [
        (urljoin(page, link.get("href")), _clean(link.get_text(" ", strip=True))) for link in soup.select("a[href]")
        if _path_matches(urljoin(page, link.get("href")), "digitalhouse.com", r"/explorar/certificacion/[^/]+")
    ]
    if not cert_links:
        raise ProviderError("Digital House cambió los enlaces públicos de certificaciones")
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    deadline = time.monotonic() + 25
    # La página inicial muestra diez certificaciones; se leen hasta cuatro,
    # dando prioridad a las afines para mantener acotado el tiempo de consulta.
    ordered = sorted(dict(cert_links).items(), key=lambda pair: not _relevant(topic, pair[1], _slug_title(pair[0])))
    for cert_url, _ in ordered[:4]:
        if time.monotonic() >= deadline:
            break
        cert_soup = _fetch(cert_url, "digitalhouse.com")
        for link in cert_soup.select("a[href]"):
            url = urljoin(cert_url, link.get("href"))
            if not _path_matches(url, "digitalhouse.com", r"/explorar/curso/[^/]+") or url in seen:
                continue
            seen.add(url)
            title, description, _ = _card_fields(link, url)
            if not _relevant(topic, title, description, _slug_title(url)):
                continue
            if time.monotonic() >= deadline:
                return results
            title = re.sub(r"\s+\d+\s+m[oó]dulos.*$", "", title, flags=re.I)
            description = _detail_description(url, "digitalhouse.com")
            if not _relevant(topic, title, description):
                continue
            results.append({"title": title, "description": description, "price": _MISSING_PRICE, "url": url})
            if len(results) >= min(max_items, _MAX_DETAIL_REQUESTS):
                return results
    return results


def henry(topic: str, max_items: int) -> list[dict[str, str]]:
    page = "https://www.soyhenry.com/"
    return _catalog(topic, max_items, (page,), "soyhenry.com", lambda url: _path_matches(url, "soyhenry.com", r"/(curso|carrera)-[^/]+"))


def desafiolatam(topic: str, max_items: int) -> list[dict[str, str]]:
    bootcamps = "https://desafiolatam.com/bootcamps/"
    free = "https://desafiolatam.com/cursos_gratuitos/"

    def eligible(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.hostname == "cursos.desafiolatam.com":
            return parsed.path.startswith("/courses/")
        return parsed.hostname == "desafiolatam.com" and parsed.path.rstrip("/") in {
            "/automatizacion-ia", "/desarrollo-full-stack-javascript", "/desarrollo-front-end-react",
            "/data-science", "/data-analytics", "/diseno-ux-ui",
        }

    return _catalog(topic, max_items, (bootcamps, free), "desafiolatam.com", eligible, detail=False, free_pages=frozenset({free}))


# Activación auditada: Platzi, Coderhouse, Henry y Desafío Latam tienen
# restricciones de uso automatizado. Senpai requiere verificar sus términos.
# Crehana sólo entrega filtros en el HTML público, sin fichas de cursos.
# Sus funciones candidatas permanecen sin registrar ni ejecutar.
ADAPTERS: dict[str, Callable[[str, int], list[dict[str, str]]]] = {
    "educacionit": educacionit,
    "ebac": ebac,
    "digitalhouse": digitalhouse,
}
