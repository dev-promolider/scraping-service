"""
CLI de ejemplo para el endpoint POST /recursos: dado un topic, busca en
Hotmart y extrae titulo, descripcion y precio (convertido a USD) de los
cursos encontrados.

Reutiliza scrapegraph_api.scraping.fetch_course_titles, la misma funcion
generica que usa la API, para no duplicar la logica de scraping/conversion.
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from scrapegraph_api.config import PROVIDER_ENV_KEYS
from scrapegraph_api.scraping import fetch_course_titles


def main() -> None:
    load_dotenv()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Extrae cursos (titulo, descripcion, precio) de Hotmart por topic"
    )
    parser.add_argument(
        "topic",
        nargs="?",
        default="Python",
        help="Tema a buscar en Hotmart, ej: 'Excel', 'Ingles' (default: Python)",
    )
    args = parser.parse_args()

    provider = os.getenv("LLM_PROVIDER", "openai")
    key_env, _, _ = PROVIDER_ENV_KEYS.get(provider, PROVIDER_ENV_KEYS["openai"])
    api_key = os.getenv(key_env)
    if not api_key:
        sys.exit(f"{key_env} no esta configurada en el .env")

    course_titles = fetch_course_titles(topic=args.topic, api_key=api_key)

    print(f"\nTotal de cursos extraidos: {len(course_titles)}\n")
    print(json.dumps(course_titles, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()
