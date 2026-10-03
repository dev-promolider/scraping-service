"""Reseñas públicas con marcado explícito; no infiere opiniones del texto comercial."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scrapegraph_api.models import CourseReviews, PublicReview, ReviewCourseRequest
from scrapegraph_api.multisource import OFFICIAL_DOMAINS, _valid_official_url


def _review_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _review_nodes(item)
    elif isinstance(value, dict):
        kind = value.get("@type", [])
        kinds = kind if isinstance(kind, list) else [kind]
        if "Review" in kinds:
            yield value
        for key, item in value.items():
            if key != "reviewBody":
                yield from _review_nodes(item)


def parse_public_reviews(html: str, source: str, url: str) -> list[PublicReview]:
    soup = BeautifulSoup(html, "html.parser")
    nodes = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            nodes.extend(_review_nodes(json.loads(script.string or script.get_text())))
        except (json.JSONDecodeError, TypeError, RecursionError):
            continue
    for node in soup.select('[itemprop="review"]'):
        body = node.select_one('[itemprop="reviewBody"]')
        if body:
            nodes.append({"reviewBody": body.get_text(" ", strip=True)})

    reviews = []
    seen = set()
    for node in nodes:
        text = node.get("reviewBody")
        if not isinstance(text, str):
            continue
        text = " ".join(BeautifulSoup(text, "html.parser").get_text(" ", strip=True).split())
        if len(text) < 15:
            continue
        digest = hashlib.sha256(text.casefold().encode()).hexdigest()[:24]
        if digest in seen:
            continue
        seen.add(digest)
        rating = node.get("reviewRating")
        try:
            score = float(rating.get("ratingValue")) if isinstance(rating, dict) else None
            if score is not None and not 0 <= score <= 100:
                score = None
        except (TypeError, ValueError):
            score = None
        date = node.get("datePublished")
        reviews.append(PublicReview(
            id=digest, text=text[:2000], url=url, source=source,
            date=date[:40] if isinstance(date, str) else None, rating=score,
        ))
        if len(reviews) >= 5:
            break
    return reviews


def fetch_course_reviews(course: ReviewCourseRequest) -> CourseReviews:
    source, url = course.source, course.url
    result = CourseReviews(source=source, url=url, status="not_exposed")
    if source not in OFFICIAL_DOMAINS or not _valid_official_url(source, url):
        raise ValueError("La URL de reseñas debe pertenecer a una plataforma oficial")
    parsed_url = urlparse(url)
    if parsed_url.username or parsed_url.password or parsed_url.port not in (None, 443):
        raise ValueError("La URL de reseñas no admite credenciales ni puertos alternativos")
    path = parsed_url.path.casefold()
    if any(part in path for part in ("/search", "/buscar", "/catalog")):
        return result
    try:
        response = requests.get(
            url, timeout=(2, 4), allow_redirects=False,
            headers={"User-Agent": "PickleBotCourseCatalog/1.0 (+public course reviews)"},
        )
        if response.status_code in (401, 403, 429):
            result.status = "blocked"
            return result
        if 300 <= response.status_code < 400:
            return result
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            result.status = "error"
            return result
        result.reviews = parse_public_reviews(response.text, source, url)
        result.status = "available" if result.reviews else "not_exposed"
    except requests.RequestException:
        result.status = "error"
    return result


def fetch_reviews(courses: list[ReviewCourseRequest]) -> list[CourseReviews]:
    unique = {(course.source, course.url.rstrip("/")): course for course in courses}
    # Validación antes de lanzar tareas para no ocultar URLs inválidas como fallos parciales.
    for course in unique.values():
        if course.source not in OFFICIAL_DOMAINS or not _valid_official_url(course.source, course.url):
            raise ValueError("Plataforma o URL de reseñas no válida")
    with ThreadPoolExecutor(max_workers=min(4, len(unique))) as pool:
        return list(pool.map(fetch_course_reviews, unique.values()))
