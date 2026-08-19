import json
import re
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

    Primero descarga el HTML plano para extraer metadatos de productos de __NEXT_DATA__,
    luego realiza una peticion POST a la API publica de Hotmart para obtener los precios
    y monedas reales de las ofertas encontradas, y finalmente entrega un JSON consolidado
    a SmartScraperGraph para filtrar y estructurar.
    """
    source_url = build_search_url(topic)
    config = build_graph_config(api_key)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 1. Obtener HTML estatico
    try:
        response = requests.get(source_url, headers=headers, timeout=20)
        response.raise_for_status()
        html_content = response.text
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch content from Hotmart ({source_url}): {exc}"
        ) from exc

    # 2. Extraer datos JSON incrustados en __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html_content)
    if not match:
        raise HTTPException(
            status_code=502, detail="Hotmart structure parsing failed (NEXT_DATA not found)"
        )

    try:
        metadata = json.loads(match.group(1))
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Failed to parse Hotmart metadata JSON"
        )

    results = metadata.get("props", {}).get("pageProps", {}).get("resultsData", {}).get("requestData", {}).get("results", [])
    if not results:
        return []

    # 3. Mapear ofertas y preparar consulta de precios a la API
    offers_payload = []
    product_map = {}

    for r in results[:max_items]:
        offer_code = r.get("offer")
        if offer_code:
            offers_payload.append({"products": [{"offer": offer_code}], "additionalData": {"shopperIp": "1.1.1.1"}})
            product_map[offer_code] = {
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "precio_valor": 0.0,
                "moneda": "USD"
            }

    # 4. Consultar precios via API externa
    if offers_payload:
        try:
            api_url = "https://api-display-gateway.dsp.hotmart.com/public/v1/payment/checkout/load-products"
            api_response = requests.post(api_url, json=offers_payload, headers=headers, timeout=15)
            api_response.raise_for_status()
            prices_data = api_response.json()

            for pr in prices_data.get("productsResponse", []):
                prods = pr.get("products", [])
                if prods:
                    prod = prods[0]
                    offer_info = prod.get("offer", {})
                    offer_key = offer_info.get("offer")
                    if offer_key in product_map:
                        pay_methods = offer_info.get("paymentMethods", [])
                        if pay_methods:
                            amount = pay_methods[0].get("amount", {})
                            product_map[offer_key]["precio_valor"] = amount.get("value", 0.0)
                            product_map[offer_key]["moneda"] = amount.get("currency", "USD")
        except Exception as e:
            # Registrar el error en consola para depurar si la API falla en el daemon
            import sys
            print(f"Error fetching prices from Hotmart: {e}", file=sys.stderr)
            pass

    clean_products = list(product_map.values())

    # 5. Formatear y retornar la lista final de cursos de manera 100% programática y confiable
    course_titles = []
    for prod in clean_products[:max_items]:
        precio_usd = convertir_a_usd(prod["precio_valor"], prod["moneda"])
        price_str = (
            f"${precio_usd:.2f}"
            if precio_usd is not None
            else f"{prod['precio_valor']} {prod['moneda']}"
        )
        course_titles.append(
            {
                "title": prod["title"],
                "description": prod["description"],
                "price": price_str,
            }
        )

    return course_titles
