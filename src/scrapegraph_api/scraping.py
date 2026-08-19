import requests
from urllib.parse import quote

from fastapi import HTTPException
from scrapegraphai.graphs import SmartScraperGraph

from scrapegraph_api.config import build_graph_config
from scrapegraph_api.currency import convertir_a_usd
from scrapegraph_api.models import ListaCursosDetectados

HOTMART_SEARCH_URL = "https://hotmart.com/es/marketplace/productos?q={query}"


def build_search_url(topic: str) -> str:
    """URL de busqueda en Hotmart para un topic dado."""
    return HOTMART_SEARCH_URL.format(query=quote(topic))


def fetch_course_titles(topic: str, api_key: str, max_items: int = 40) -> list[dict]:
    """Busca en Hotmart cursos relacionados a `topic` y extrae de la pagina de
    resultados titulo, descripcion breve y precio (convertido a USD) de cada
    uno, hasta `max_items`.

    Usa requests para descargar el HTML plano de la pagina, evitando depender de
    Playwright (que requiere libgbm/Chromium en el servidor) y entrega el HTML
    directamente al SmartScraperGraph.
    """
    source_url = build_search_url(topic)
    config = build_graph_config(api_key)

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(source_url, headers=headers, timeout=20)
        response.raise_for_status()
        html_content = response.text
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch content from Hotmart ({source_url}): {exc}"
        ) from exc

    try:
        graph = SmartScraperGraph(
            prompt=(
                f"Extrae hasta {max_items} cursos relacionados a '{topic}' "
                "visibles en esta pagina de un marketplace, con: su titulo "
                "exacto, un resumen breve (1-2 oraciones) de que trata, el "
                "valor numerico de su precio, y el codigo de moneda en el que "
                "se muestra (ej. USD, PEN, EUR, BRL). Ignora los cursos sin "
                "precio visible."
            ),
            source=html_content,
            config=config,
            schema=ListaCursosDetectados,
        )
        result = graph.run()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Scraping analysis failed: {exc}"
        ) from exc

    cursos_raw = result.get("cursos", []) if isinstance(result, dict) else []

    course_titles = []
    for c in cursos_raw[:max_items]:
        precio_usd = convertir_a_usd(c.get("precio_valor", 0), c.get("moneda", ""))
        price_str = (
            f"${precio_usd:.2f}"
            if precio_usd is not None
            else f"{c.get('precio_valor')} {c.get('moneda')}"
        )
        course_titles.append(
            {
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                "price": price_str,
            }
        )

    return course_titles
