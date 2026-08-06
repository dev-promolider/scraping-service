from fastapi import HTTPException
from scrapegraphai.graphs import SmartScraperGraph

from scrapegraph_api.config import build_graph_config
from scrapegraph_api.currency import convertir_a_usd
from scrapegraph_api.models import ListaRecursosDetectados


def fetch_recursos_marketplace(
    url: str, api_key: str, max_items: int = 40
) -> list[dict]:
    """Extrae de una pagina de listado/busqueda de un marketplace (Hotmart,
    Udemy, Coursera, etc.) el nombre y precio (convertido a USD) de los
    recursos visibles, hasta `max_items`.

    Usa 'schema' para forzar salida estructurada del LLM (evita el bug del
    parser JSON en generate_answer_node.py de scrapegraphai) en vez de dejarlo
    devolver texto libre.
    """
    config = build_graph_config(api_key)

    try:
        graph = SmartScraperGraph(
            prompt=(
                f"Extrae hasta {max_items} recursos (cursos, productos o servicios) "
                "visibles en esta pagina de un marketplace, con su nombre exacto, "
                "el valor numerico de su precio, y el codigo de moneda en el que se "
                "muestra (ej. USD, PEN, EUR, BRL). Ignora los recursos sin precio visible."
            ),
            source=url,
            config=config,
            schema=ListaRecursosDetectados,
        )
        result = graph.run()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Scraping failed ({url}): {exc}"
        ) from exc

    recursos_raw = result.get("recursos", []) if isinstance(result, dict) else []

    recursos = []
    for r in recursos_raw[:max_items]:
        precio_usd = convertir_a_usd(r.get("precio_valor", 0), r.get("moneda", ""))
        precio_str = (
            f"${precio_usd:.2f}"
            if precio_usd is not None
            else f"{r.get('precio_valor')} {r.get('moneda')}"
        )
        recursos.append({"nombre": r.get("nombre", ""), "precio": precio_str})

    return recursos
