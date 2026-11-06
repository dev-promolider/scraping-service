"""Extractor de Hotmart usado por el contrato historico de Pickle."""

import json
import logging
import math
import os
from ipaddress import IPv4Address, AddressValueError
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException


HOTMART_SEARCH_URL = "https://hotmart.com/es/marketplace/productos?q={query}"
HOTMART_PRICE_URL = (
    "https://api-display-gateway.dsp.hotmart.com/public/v1/payment/checkout/load-products"
)
HEADERS = {"User-Agent": "PickleCourseResearch/1.0"}
logger = logging.getLogger(__name__)


def build_search_url(topic: str) -> str:
    return HOTMART_SEARCH_URL.format(query=quote(topic))


def _parse_results(html: str) -> list[dict]:
    script = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        raise HTTPException(status_code=502, detail="Hotmart cambio su pagina de resultados")
    try:
        metadata = json.loads(script.string)
        results = metadata["props"]["pageProps"]["resultsData"]["requestData"]["results"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=502, detail="Hotmart cambio su estructura de datos") from exc
    if not isinstance(results, list):
        raise HTTPException(status_code=502, detail="Hotmart devolvio resultados invalidos")
    return results


def _format_price(amount: object, currency: object) -> str:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return "No disponible"
    if not math.isfinite(amount) or amount < 0:
        return "No disponible"
    code = str(currency or "").upper()
    if len(code) != 3 or not code.isalpha():
        return "No disponible"
    return f"${amount:.2f}" if code == "USD" else f"{amount:.2f} {code}"


def fetch_course_titles(
    topic: str, api_key: str | None = None, max_items: int = 40
) -> list[dict[str, str]]:
    """Busca ofertas publicas; `api_key` se conserva para llamadas antiguas."""
    try:
        response = requests.get(build_search_url(topic), headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        if code in (403, 429):
            raise HTTPException(status_code=code, detail="Hotmart limito el acceso") from exc
        raise HTTPException(status_code=502, detail="No se pudo consultar Hotmart") from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="No se pudo consultar Hotmart") from exc

    results = _parse_results(response.text)
    products = []
    offers = {}
    for result in results[:max_items]:
        if not isinstance(result, dict):
            continue
        title = str(result.get("title") or "").strip()
        if not title:
            continue
        product = {
            "title": title,
            "description": str(result.get("description") or "").strip(),
            "price": "No disponible",
        }
        # Conserva el enlace observado; no fabrica rutas a partir del título.
        course_url = result.get("url")
        if isinstance(course_url, str) and course_url.startswith("https://"):
            product["url"] = course_url
        products.append(product)
        offer = result.get("offer")
        if isinstance(offer, str) and offer:
            offers.setdefault(offer, []).append(product)

    if offers:
        shopper_ip = os.getenv("HOTMART_SHOPPER_IP", "1.1.1.1")
        try:
            IPv4Address(shopper_ip)
        except AddressValueError as exc:
            raise HTTPException(
                status_code=500, detail="HOTMART_SHOPPER_IP debe ser una IPv4 valida"
            ) from exc
        payload = [
            {
                "products": [{"offer": code}],
                "additionalData": {"shopperIp": shopper_ip},
            }
            for code in offers
        ]
        try:
            price_response = requests.post(
                HOTMART_PRICE_URL, json=payload, headers=HEADERS, timeout=15
            )
            price_response.raise_for_status()
            prices = price_response.json()
            if not isinstance(prices, dict):
                raise ValueError("Respuesta de precios invalida")
            for item in prices.get("productsResponse", []):
                for entry in item.get("products", []):
                    offer = entry.get("offer") or {}
                    code = offer.get("key")
                    methods = offer.get("paymentMethods") or []
                    if code in offers and methods:
                        amount = methods[0].get("amount") or {}
                        price = _format_price(amount.get("value"), amount.get("currency"))
                        for product in offers[code]:
                            product["price"] = price
        except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.warning("No se obtuvieron precios de Hotmart: %s", type(exc).__name__)

    return products
