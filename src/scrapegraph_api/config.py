import os

from fastapi import HTTPException


PROVIDER_ENV_KEYS = {
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", "openai/gpt-4o-mini"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "deepseek/deepseek-chat"),
}


def require_api_key() -> str:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    key_env, _, _ = PROVIDER_ENV_KEYS.get(provider, PROVIDER_ENV_KEYS["openai"])
    api_key = os.getenv(key_env)
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=f"{key_env} is not configured on the server",
        )
    return api_key


def build_graph_config(api_key: str) -> dict:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    _, model_env, default_model = PROVIDER_ENV_KEYS.get(
        provider, PROVIDER_ENV_KEYS["openai"]
    )
    return {
        "llm": {
            "api_key": api_key,
            "model": os.getenv(model_env, default_model),
        },
        "headless": True,
        # Espera a que la pagina termine de hidratarse via JS (networkidle) en vez
        # de domcontentloaded, para capturar contenido cargado de forma asincrona
        # (ej. tarjetas de producto/precio en SPAs como Hotmart, Udemy, Coursera).
        "loader_kwargs": {"load_state": "networkidle", "timeout": 30},
    }
