import os
from secrets import compare_digest

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException

from scrapegraph_api.models import (
    MultiSourceRequest,
    MultiSourceResponse,
    RecursosRequest,
    RecursosResponse,
    ReviewsRequest,
    ReviewsResponse,
    MarketSignalsRequest,
)
from scrapegraph_api.multisource import available_adapters, search_catalogs
from scrapegraph_api.scraping import fetch_course_titles
from scrapegraph_api.reviews import fetch_reviews
from scrapegraph_api.market_signals import fetch_market_signals

load_dotenv()

app = FastAPI(
    title="Scrapegraph API",
    description="API de ofertas publicas de cursos por plataforma.",
    version="0.2.0",
)


@app.get("/")
def read_root():
    return {"message": "Scrapegraph API is running"}


@app.post("/recursos", response_model=RecursosResponse)
def recursos_marketplace(request: RecursosRequest):
    """Contrato historico de Pickle: busca solo en Hotmart."""
    course_titles = fetch_course_titles(
        topic=request.topic, max_items=request.max_items
    )
    return RecursosResponse(topic=request.topic, courseTitles=course_titles)


@app.get("/plataformas")
def plataformas_disponibles():
    credentials = {
        "linkedin_learning": ("LINKEDIN_LEARNING_CLIENT_ID", "LINKEDIN_LEARNING_CLIENT_SECRET"),
        "pluralsight": ("PLURALSIGHT_API_KEY",),
        "oreilly": ("OREILLY_MCP_TOKEN",),
    }
    return {
        "platforms": [
            {
                "id": source,
                "requires_credentials": source in credentials,
                "configured": all(os.getenv(name) for name in credentials.get(source, ())),
            }
            for source in sorted(available_adapters())
        ]
    }


@app.post("/recursos/multifuente", response_model=MultiSourceResponse)
def recursos_multifuente(
    request: MultiSourceRequest, x_api_key: str | None = Header(default=None)
):
    expected_key = os.getenv("SCRAPING_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=503, detail="SCRAPING_API_KEY no configurada")
    if not x_api_key or not compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="Credencial invalida")
    try:
        return search_catalogs(request.topic, request.platforms, request.max_items)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/recursos/tendencias")
def recursos_tendencias(request: MarketSignalsRequest, x_api_key: str | None = Header(default=None)):
    expected_key = os.getenv("SCRAPING_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=503, detail="SCRAPING_API_KEY no configurada")
    if not x_api_key or not compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="Credencial invalida")
    return fetch_market_signals(request.topic.strip(), request.region, request.focus)


@app.post("/recursos/comentarios", response_model=ReviewsResponse)
def recursos_comentarios(
    request: ReviewsRequest, x_api_key: str | None = Header(default=None)
):
    expected_key = os.getenv("SCRAPING_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=503, detail="SCRAPING_API_KEY no configurada")
    if not x_api_key or not compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="Credencial invalida")
    try:
        return ReviewsResponse(courses=fetch_reviews(request.courses))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
