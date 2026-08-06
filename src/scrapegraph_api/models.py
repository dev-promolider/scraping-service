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
