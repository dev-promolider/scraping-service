"""Señales externas: diferencia interés medido de publicaciones y videos."""

import hashlib
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from scrapegraph_api.official_context import official_context


def _signal(source, title, url, kind, context, date=None):
    return {
        "id": hashlib.sha256((source + url + title).encode()).hexdigest()[:24],
        "source": source, "title": title[:300], "url": url,
        "kind": kind, "context": context[:700], "date": date,
    }


def _json(url, params):
    response = requests.get(url, params=params, timeout=(3, 6))
    response.raise_for_status()
    return response.json()


def _google_news(topic, region):
    normalized = unicodedata.normalize("NFKD", topic.casefold()).encode("ascii", "ignore").decode()
    technical_terms = {
        "python": ("programacion", "software", "codigo", "datos", "inteligencia artificial", "machine learning"),
        "java": ("programacion", "software", "jdk", "jvm", "spring", "codigo"),
        "react": ("javascript", "frontend", "software", "programacion", "componentes"),
        "angular": ("typescript", "frontend", "software", "programacion", "componentes"),
    }
    context = next((terms for term, terms in technical_terms.items() if re.search(r"\b" + term + r"\b", normalized)), ())
    qualifier = " (" + " OR ".join(context) + ")" if context else ""
    url = "https://news.google.com/rss/search?" + urlencode({
        "q": f'"{topic}"{qualifier} when:90d', "hl": "es-419", "gl": region, "ceid": region + ":es-419",
    })
    response = requests.get(url, timeout=(3, 6))
    response.raise_for_status()
    if len(response.content) > 1_000_000 or b"<!DOCTYPE" in response.content.upper():
        raise ValueError("Respuesta de publicaciones inválida")
    root = ET.fromstring(response.content)
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    signals = []
    for item in root.findall("./channel/item"):
        title, link = item.findtext("title", "").strip(), item.findtext("link", "").strip()
        if not title or not link.startswith("https://news.google.com/"):
            continue
        clean_title = unicodedata.normalize("NFKD", title.casefold()).encode("ascii", "ignore").decode()
        if context and not any(term in clean_title for term in context):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate", ""))
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if published < cutoff:
                continue
        except (TypeError, ValueError):
            continue
        publisher = item.findtext("source", "")
        signals.append(_signal(
            "google_news", title, link, "publication",
            f"Publicación de {publisher}. Es una señal editorial reciente, no una medición de demanda ni de crecimiento.",
            published.isoformat(),
        ))
        if len(signals) == 6:
            break
    return signals


def _google_trends(topic, region):
    key = os.getenv("SERPAPI_API_KEY")
    if not key:
        return None
    body = _json("https://serpapi.com/search.json", {
        "engine": "google_trends", "q": topic, "data_type": "RELATED_QUERIES",
        "date": "today 3-m", "geo": region, "api_key": key,
    })
    if body.get("error"):
        raise ValueError("Proveedor de Google Trends no disponible")
    signals = []
    queries = body.get("related_queries") or {}
    for group in ("rising", "top"):
        for row in queries.get(group, [])[:4]:
            title = str(row.get("query") or "").strip()
            if not title:
                continue
            url = "https://trends.google.com/trends/explore?" + urlencode({"q": title, "geo": region, "date": "today 3-m"})
            value = row.get("value", "no informado")
            context = f"Consulta relacionada ({group}) en Google Trends, últimos 3 meses, región {region}; indicador relativo: {value}. Acceso mediante SerpAPI, no ventas de cursos."
            signals.append(_signal("google_trends_serpapi", title, url, "related_query", context))
    return signals


def _youtube(topic, region):
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return None
    published_after = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = _json("https://www.googleapis.com/youtube/v3/search", {
        "part": "snippet", "q": topic + " curso", "type": "video", "maxResults": 4,
        "publishedAfter": published_after, "regionCode": region, "relevanceLanguage": "es", "key": key,
    })
    ids = [item.get("id", {}).get("videoId") for item in result.get("items", [])]
    ids = [item for item in ids if isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_-]{11}", item)]
    if not ids:
        return []
    videos = _json("https://www.googleapis.com/youtube/v3/videos", {
        "part": "snippet,statistics", "id": ",".join(ids), "key": key,
    })
    signals = []
    for video in videos.get("items", []):
        snippet, stats = video.get("snippet", {}), video.get("statistics", {})
        signals.append(_signal(
            "youtube", str(snippet.get("title", "")), "https://www.youtube.com/watch?v=" + video["id"],
            "video_interest", f"Visualizaciones observadas: {stats.get('viewCount', 'no disponibles')}. Interés en este video, no ventas ni crecimiento temporal. " + str(snippet.get("description", ""))[:350],
            snippet.get("publishedAt"),
        ))
    return signals


def fetch_market_signals(topic: str, region: str = "PE", focus: str | None = None):
    original_topic = topic
    # Las tendencias se consultan sobre el tema base, no sobre toda la promesa del curso.
    technical_topic = re.search(r"\b(python|javascript|typescript|java|react|angular|php|sql|excel)\b", topic, re.IGNORECASE)
    if technical_topic:
        base = technical_topic.group(1)
        topic = original_topic if len(original_topic.split()) <= 4 else base
    if focus:
        topic = f"{topic} {focus}"[:180]
    providers = {"official_documentation": official_context,
                 "google_news": _google_news, "google_trends_serpapi": _google_trends, "youtube": _youtube}
    def query(entry):
        name, provider = entry
        try:
            signals = provider(topic) if name == "official_documentation" else provider(topic, region)
            return signals or [], {"source": name, "status": "not_configured" if signals is None else "available" if signals else "empty"}
        except (requests.RequestException, ValueError, KeyError, TypeError, ET.ParseError):
            return [], {"source": name, "status": "error"}
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(query, providers.items()))
    signals = [signal for values, _ in results for signal in values]
    key = os.getenv("YOUTUBE_API_KEY")
    def video_comments(signal):
        if signal["source"] != "youtube" or not key:
            return []
        try:
            body = _json("https://www.googleapis.com/youtube/v3/commentThreads", {
                "part": "snippet", "videoId": signal["url"].split("v=")[-1],
                "maxResults": 5, "textFormat": "plainText", "key": key,
            })
            comments = []
            for item in body.get("items", []):
                snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = BeautifulSoup(str(snippet.get("textOriginal", "")), "html.parser").get_text(" ", strip=True)
                if len(text) >= 15:
                    comments.append({
                        "id": "yt-" + hashlib.sha256(text.casefold().encode()).hexdigest()[:24],
                        "text": text[:1500], "url": signal["url"], "source": "youtube",
                        "date": snippet.get("publishedAt"), "audience": "viewer",
                    })
            return comments
        except (requests.RequestException, ValueError, TypeError):
            return []
    with ThreadPoolExecutor(max_workers=4) as pool:
        comments = [comment for rows in pool.map(video_comments, signals) for comment in rows]
    return {
        "signals": signals, "comments": comments,
        "sources": [status for _, status in results],
        "checkedAt": datetime.now(timezone.utc).isoformat(), "region": region, "period": "últimos 90 días",
        "queryTopic": topic, "requestedTopic": original_topic,
    }
