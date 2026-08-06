from dotenv import load_dotenv
from fastapi import FastAPI

from scrapegraph_api.config import require_api_key
from scrapegraph_api.models import RecursosRequest, RecursosResponse
from scrapegraph_api.scraping import fetch_course_titles

load_dotenv()

app = FastAPI(
    title="Scrapegraph API",
    description="API para extraer informacion estructurada de paginas web usando IA.",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {"message": "Scrapegraph API is running"}


@app.post("/recursos", response_model=RecursosResponse)
def recursos_marketplace(request: RecursosRequest):
    """Busca en Hotmart cursos relacionados a 'topic' y devuelve titulo,
    descripcion breve y precio (en USD) de cada uno. Salida siempre con la
    misma forma fija: {topic, courseTitles: [{title, description, price}]}."""
    api_key = require_api_key()
    course_titles = fetch_course_titles(
        topic=request.topic, api_key=api_key, max_items=request.max_items
    )
    return RecursosResponse(topic=request.topic, courseTitles=course_titles)
