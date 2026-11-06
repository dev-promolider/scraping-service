"""Orquesta consultas independientes a catalogos publicos habilitados."""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import BoundedSemaphore, Lock
from time import monotonic
from urllib.parse import urlparse

import requests
from fastapi import HTTPException

from scrapegraph_api.models import CourseOffer, MultiSourceResponse, SourceStatus
from scrapegraph_api.providers.errors import SourceBlockedError


OFFICIAL_DOMAINS = {
    "hotmart": "hotmart.com",
    "dataquest": "dataquest.io",
    "frontend_masters": "frontendmasters.com",
    "treehouse": "teamtreehouse.com",
    "linux_foundation": "linuxfoundation.org",
    "scrimba": "scrimba.com",
    "platzi": "platzi.com",
    "crehana": "crehana.com",
    "coderhouse": "coderhouse.com",
    "digitalhouse": "digitalhouse.com",
    "henry": "soyhenry.com",
    "desafio_latam": "desafiolatam.com",
    "educacionit": "educacionit.com",
    "ebac": "ebac.mx",
    "senpai": "senpaiacademy.com",
    "le_wagon": "lewagon.com",
    "four_geeks": "4geeks.com",
    "linkedin_learning": "linkedin.com",
    "pluralsight": "pluralsight.com",
    "oreilly": "oreilly.com",
}
_PAUSED_UNTIL: dict[str, float] = {}
_PAUSE_LOCK = Lock()
_BLOCK_PAUSE_SECONDS = 15 * 60
_MAX_ACTIVE_SOURCE_TASKS = 12
_SOURCE_EXECUTOR = ThreadPoolExecutor(
    max_workers=_MAX_ACTIVE_SOURCE_TASKS,
    thread_name_prefix="course-source",
)
_SOURCE_CAPACITY = BoundedSemaphore(_MAX_ACTIVE_SOURCE_TASKS)
_SOURCE_ADMISSION_LOCK = Lock()


def available_adapters():
    # La importacion diferida deja disponible la API anterior aunque un conector
    # opcional necesite una dependencia que aun no este instalada.
    from scrapegraph_api.providers.cohort import ADAPTERS as cohort_adapters
    from scrapegraph_api.providers.extra_api import ADAPTERS as extra_api_adapters
    from scrapegraph_api.providers.general import ADAPTERS as general_adapters
    from scrapegraph_api.providers.hotmart import ADAPTERS as hotmart_adapters
    from scrapegraph_api.providers.latam import ADAPTERS as latam_adapters, platzi
    from scrapegraph_api.providers.official_api import ADAPTERS as api_adapters
    from scrapegraph_api.providers.tech import ADAPTERS as tech_adapters

    adapters = {
        **hotmart_adapters,
        **tech_adapters,
        **latam_adapters,
        **cohort_adapters,
        **api_adapters,
        **extra_api_adapters,
        **general_adapters,
    }
    if os.getenv("PLATZI_METADATA_ENABLED", "").strip().casefold() == "true":
        adapters["platzi"] = platzi
    return {key: value for key, value in adapters.items() if key in OFFICIAL_DOMAINS}


def _valid_official_url(source: str, url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    domain = OFFICIAL_DOMAINS[source]
    return parsed.scheme == "https" and (host == domain or host.endswith("." + domain))


def _query_source(source: str, adapter, topic: str, max_items: int):
    rows = adapter(topic, max_items)
    if not isinstance(rows, list):
        raise ValueError("El conector no devolvio una lista")

    courses = []
    seen = set()
    for row in rows[:max_items]:
        if not isinstance(row, dict):
            raise ValueError("El conector devolvio un curso invalido")
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        if not title or not _valid_official_url(source, url):
            raise ValueError("El conector devolvio un titulo o enlace invalido")
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("El conector devolvio metadatos invalidos")
        key = (url.rstrip("/").casefold(), title.casefold())
        if key in seen:
            continue
        seen.add(key)
        courses.append(
            CourseOffer(
                source=source,
                title=title,
                description=str(row.get("description") or "").strip(),
                price=str(row.get("price") or "No disponible").strip(),
                url=url,
                metadata=metadata,
            )
        )
    return courses


def _paused(source: str) -> bool:
    with _PAUSE_LOCK:
        return _PAUSED_UNTIL.get(source, 0) > monotonic()


def _pause(source: str) -> None:
    with _PAUSE_LOCK:
        _PAUSED_UNTIL[source] = monotonic() + _BLOCK_PAUSE_SECONDS


def search_catalogs(topic: str, platforms: list[str], max_items: int) -> MultiSourceResponse:
    adapters = available_adapters()
    requested = list(dict.fromkeys(platforms))
    unknown = sorted(set(requested) - set(adapters))
    if unknown:
        raise ValueError("Plataformas no disponibles: " + ", ".join(unknown))

    outcomes = {
        source: (
            [],
            SourceStatus(source=source, status="blocked", count=0, detail="Fuente en pausa"),
        )
        for source in requested
        if _paused(source)
    }
    runnable = [source for source in requested if source not in outcomes]
    if not runnable:
        return MultiSourceResponse(
            topic=topic, courses=[], sources=[outcomes[source][1] for source in requested]
        )
    # Fallar rápido evita que búsquedas antiguas se acumulen en la cola interna.
    reserved = 0
    with _SOURCE_ADMISSION_LOCK:
        if len(runnable) <= _MAX_ACTIVE_SOURCE_TASKS:
            for _ in runnable:
                if not _SOURCE_CAPACITY.acquire(blocking=False):
                    break
                reserved += 1
        if reserved != len(runnable):
            for _ in range(reserved):
                _SOURCE_CAPACITY.release()
            reserved = 0

    if reserved != len(runnable):
        for source in runnable:
            outcomes[source] = (
                [],
                SourceStatus(
                    source=source,
                    status="error",
                    count=0,
                    detail="Scraper ocupado; no se encoló. Intenta de nuevo en unos segundos.",
                ),
            )
        return MultiSourceResponse(
            topic=topic, courses=[], sources=[outcomes[source][1] for source in requested]
        )

    pending = {}
    try:
        for source in runnable:
            future = _SOURCE_EXECUTOR.submit(
                _query_source, source, adapters[source], topic, max_items
            )
            future.add_done_callback(lambda _: _SOURCE_CAPACITY.release())
            pending[future] = source
    except Exception:
        for _ in range(reserved - len(pending)):
            _SOURCE_CAPACITY.release()
        for future in pending:
            future.cancel()
        raise

    for future in as_completed(pending):
        source = pending[future]
        try:
            courses = future.result()
            outcomes[source] = (
                courses,
                SourceStatus(
                    source=source,
                    status="ok" if courses else "empty",
                    count=len(courses),
                ),
            )
        except HTTPException as exc:
            blocked = exc.status_code in (401, 403, 429)
            if blocked:
                _pause(source)
            outcomes[source] = (
                [],
                SourceStatus(
                    source=source,
                    status="blocked" if blocked else "error",
                    count=0,
                    detail=f"HTTP {exc.status_code}",
                ),
            )
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else None
            blocked = code in (401, 403, 429)
            if blocked:
                _pause(source)
            outcomes[source] = (
                [],
                SourceStatus(
                    source=source,
                    status="blocked" if blocked else "error",
                    count=0,
                    detail=f"HTTP {code}" if code else "Error HTTP",
                ),
            )
        except Exception as exc:
            blocked = isinstance(exc, SourceBlockedError)
            if blocked:
                _pause(source)
            outcomes[source] = (
                [],
                SourceStatus(
                    source=source,
                    status="blocked" if blocked else "error",
                    count=0,
                    detail=type(exc).__name__,
                ),
            )

    return MultiSourceResponse(
        topic=topic,
        courses=[course for source in requested for course in outcomes[source][0]],
        sources=[outcomes[source][1] for source in requested],
    )
