"""
CLI de ejemplo para el endpoint POST /recursos: dado un tema, arma la URL
de busqueda de Hotmart y extrae nombre y precio (convertido a USD) de los
cursos encontrados.

Reutiliza scrapegraph_api.scraping.fetch_recursos_marketplace, la misma
funcion generica que usa la API (funciona con cualquier marketplace, no solo
Hotmart), para no duplicar la logica de scraping/conversion.
"""

import argparse
import json
import os
import sys
from urllib.parse import quote

from dotenv import load_dotenv

from scrapegraph_api.scraping import fetch_recursos_marketplace


def main() -> None:
    load_dotenv()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Extrae recursos (cursos, productos) de un marketplace"
    )
    parser.add_argument(
        "tema",
        nargs="?",
        default="Python",
        help="Tema a buscar en Hotmart, ej: 'Excel', 'Ingles' (default: Python)",
    )
    parser.add_argument(
        "--url",
        help="URL completa de listado/busqueda de cualquier marketplace (ignora 'tema' si se da)",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY no esta configurada en el .env")

    url = args.url or f"https://hotmart.com/es/marketplace/productos?q={quote(args.tema)}"

    recursos = fetch_recursos_marketplace(url, api_key)

    print(f"\nTotal de recursos extraidos: {len(recursos)}\n")
    print(json.dumps(recursos, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()
