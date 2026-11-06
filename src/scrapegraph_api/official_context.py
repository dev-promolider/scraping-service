"""Contexto técnico comprobado en páginas oficiales; no mide demanda."""
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Son fuentes de evidencia, no reglas que obliguen a recomendar un enfoque.
DOCUMENTS = {
    "java": ("https://dev.java/learn/",),
    "spring": ("https://spring.io/projects/spring-boot/",),
    "spring ai": ("https://spring.io/projects/spring-ai/",),
    "python": ("https://docs.python.org/3/tutorial/",),
    "fastapi": ("https://fastapi.tiangolo.com/",),
    "pydantic ai": ("https://ai.pydantic.dev/",),
    "react": ("https://react.dev/learn",),
    "angular": ("https://angular.dev/overview",),
    "typescript": ("https://www.typescriptlang.org/docs/",),
    "php": ("https://www.php.net/manual/es/intro-whatis.php",),
    "javascript": ("https://developer.mozilla.org/es/docs/Web/JavaScript/Guide",),
}


def official_context(topic):
    text = topic.casefold()
    urls = [url for term, pages in DOCUMENTS.items()
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)
            for url in pages]
    if re.search(r"\bjava\b", text) and re.search(r"\b(?:ia|ai)\b|inteligencia artificial", text):
        urls += DOCUMENTS["spring ai"]
    def retrieve(url):
        try:
            response = requests.get(url, timeout=(3, 6), allow_redirects=False)
            response.raise_for_status()
            if response.status_code != 200 or len(response.content) > 2_000_000:
                return None
            soup = BeautifulSoup(response.content, "html.parser")
            for tag in soup.select("script, style, nav, footer, header"):
                tag.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else urlparse(url).hostname
            body = " ".join((soup.select_one("main") or soup).get_text(" ", strip=True).split())
            if len(body) < 80:
                return None
            return {"id": hashlib.sha256(url.encode()).hexdigest()[:24],
                    "source": "official_documentation", "title": title[:250],
                    "url": url, "kind": "documentation", "context": body[:1600]}
        except requests.RequestException:
            return None
    with ThreadPoolExecutor(max_workers=3) as pool:
        return [row for row in pool.map(retrieve, list(dict.fromkeys(urls))[:4]) if row]
