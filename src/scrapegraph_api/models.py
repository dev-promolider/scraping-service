from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Schema interno usado para forzar salida estructurada del LLM ---
# (ver scraping.py: se pasa como `schema` a SmartScraperGraph)


class CursoDetectado(BaseModel):
    title: str = Field(description="Titulo exacto del curso")
    description: str = Field(
        description="Resumen breve (1-2 oraciones) de que trata el curso"
    )
    precio_valor: float = Field(
        description="Precio numerico del curso tal como aparece en la pagina, sin simbolo de moneda"
    )
    moneda: str = Field(
        description="Codigo de moneda en el que se muestra el precio (ej. USD, PEN, EUR, BRL)"
    )


class ListaCursosDetectados(BaseModel):
    cursos: list[CursoDetectado] = Field(description="Lista de cursos encontrados")


# --- Schema publico de la API (contrato fijo, no cambia por sitio/prompt) ---


class CourseTitle(BaseModel):
    title: str
    description: str
    price: str


class RecursosRequest(BaseModel):
    topic: str = Field(
        ..., min_length=1, description="Tema a buscar (ej. 'python para principiantes')"
    )
    max_items: int = Field(
        40, ge=1, le=100, description="Maximo de cursos a extraer de la pagina"
    )


class RecursosResponse(BaseModel):
    topic: str
    courseTitles: list[CourseTitle]


class MultiSourceRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    platforms: list[str] = Field(..., min_length=1, max_length=40)
    max_items: int = Field(5, ge=1, le=5, description="Limite por plataforma")


class CourseOffer(BaseModel):
    source: str
    title: str
    description: str
    price: str
    url: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceStatus(BaseModel):
    source: str
    status: Literal["ok", "empty", "error", "blocked"]
    count: int
    detail: str | None = None


class MultiSourceResponse(BaseModel):
    topic: str
    courses: list[CourseOffer]
    sources: list[SourceStatus]


class ReviewCourseRequest(BaseModel):
    source: str = Field(min_length=1, max_length=50)
    url: str = Field(min_length=1, max_length=2000)


class ReviewsRequest(BaseModel):
    courses: list[ReviewCourseRequest] = Field(min_length=1, max_length=12)


class PublicReview(BaseModel):
    id: str
    text: str
    url: str
    source: str
    date: str | None = None
    rating: float | None = None


class CourseReviews(BaseModel):
    source: str
    url: str
    status: Literal["available", "empty", "not_exposed", "error", "blocked"]
    reviews: list[PublicReview] = Field(default_factory=list)


class ReviewsResponse(BaseModel):
    courses: list[CourseReviews]


class MarketSignalsRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    region: str = Field("PE", pattern=r"^[A-Z]{2}$")
    focus: str | None = Field(None, max_length=120)
