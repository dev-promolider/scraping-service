"""Adaptador del extractor historico de Hotmart para la consulta multifuente."""

from scrapegraph_api.scraping import build_search_url, fetch_course_titles


def hotmart(topic: str, max_items: int) -> list[dict[str, str]]:
    search_url = build_search_url(topic)
    return [
        {**course, "url": course.get("url") or search_url}
        for course in fetch_course_titles(topic=topic, max_items=max_items)
    ]


ADAPTERS = {"hotmart": hotmart}
