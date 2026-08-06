from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from scrapegraphai.graphs import SmartScraperGraph

from scrapegraph_api.config import build_graph_config, require_api_key
from scrapegraph_api.models import (
    RecursosRequest,
    RecursosResponse,
    ScrapeRequest,
    ScrapeResponse,
)
from scrapegraph_api.scraping import fetch_recursos_marketplace

load_dotenv()

app = FastAPI(
    title="Scrapegraph API",
    description="API para extraer informacion estructurada de paginas web usando IA.",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {"message": "Scrapegraph API is running"}


@app.post("/scrape", response_model=ScrapeResponse)
def scrape(request: ScrapeRequest):
    """Scraping libre de una unica URL segun un prompt arbitrario."""
    api_key = require_api_key()
    config = build_graph_config(api_key)
    try:
        graph = SmartScraperGraph(
            prompt=request.prompt, source=str(request.url), config=config
        )
        result = graph.run()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scraping failed: {exc}") from exc
    return ScrapeResponse(result=result)


@app.post("/recursos", response_model=RecursosResponse)
def recursos_marketplace(request: RecursosRequest):
    """Extrae nombre y precio (en USD) de los recursos listados en una pagina
    de marketplace (cursos, productos, etc.) -- funciona con Hotmart, Udemy,
    Coursera o cualquier pagina de listado/busqueda similar."""
    api_key = require_api_key()
    recursos = fetch_recursos_marketplace(str(request.url), api_key, request.max_items)
    return RecursosResponse(url=str(request.url), recursos=recursos)
