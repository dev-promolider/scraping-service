"""CLI de ejemplo para la busqueda historica de Hotmart."""

import argparse
import json
import sys

from dotenv import load_dotenv

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

    course_titles = fetch_course_titles(topic=args.topic)

    print(f"\nTotal de cursos extraidos: {len(course_titles)}\n")
    print(json.dumps(course_titles, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()
