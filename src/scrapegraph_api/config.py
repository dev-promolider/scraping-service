import os

from fastapi import HTTPException


def require_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured on the server",
        )
    return api_key


def build_graph_config(api_key: str) -> dict:
    return {
        "llm": {
            "api_key": api_key,
            "model": os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini"),
        },
        "headless": True,
        # Espera a que la pagina termine de hidratarse via JS (networkidle) en vez
        # de domcontentloaded, para capturar contenido cargado de forma asincrona
        # (ej. tarjetas de producto/precio en SPAs como Hotmart, Udemy, Coursera).
        "loader_kwargs": {"load_state": "networkidle", "timeout": 30},
    }
