import os

from fastapi import HTTPException


def require_api_key() -> str:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="DEEPSEEK_API_KEY is not configured on the server",
            )
    else:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY is not configured on the server",
            )
    return api_key


def build_graph_config(api_key: str) -> dict:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "deepseek":
        model = os.getenv("DEEPSEEK_MODEL", "deepseek/deepseek-chat")
    else:
        model = os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini")

    return {
        "llm": {
            "api_key": api_key,
            "model": model,
        }
    }
