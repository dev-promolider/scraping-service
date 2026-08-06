from pydantic import BaseModel, Field, HttpUrl


class ScrapeRequest(BaseModel):
    url: HttpUrl = Field(..., description="URL de la pagina a scrapear")
    prompt: str = Field(
        ..., min_length=1, description="Instruccion de que informacion extraer"
    )


class ScrapeResponse(BaseModel):
    result: dict


class RecursoDetectado(BaseModel):
    nombre: str = Field(
        description="Nombre o titulo del recurso (curso, producto, servicio, etc.)"
    )
    precio_valor: float = Field(
        description="Precio numerico del recurso tal como aparece en la pagina, sin simbolo de moneda"
    )
    moneda: str = Field(
        description="Codigo de moneda en el que se muestra el precio (ej. USD, PEN, EUR, BRL)"
    )


class ListaRecursosDetectados(BaseModel):
    recursos: list[RecursoDetectado] = Field(
        description="Lista de recursos encontrados"
    )


class RecursoItem(BaseModel):
    nombre: str
    precio: str


class RecursosRequest(BaseModel):
    url: HttpUrl = Field(
        ...,
        description=(
            "URL de una pagina de listado/busqueda de un marketplace "
            "(ej. Hotmart, Udemy, Coursera) que muestre varios recursos con precio"
        ),
    )
    max_items: int = Field(
        40, ge=1, le=100, description="Maximo de recursos a extraer de la pagina"
    )


class RecursosResponse(BaseModel):
    url: str
    recursos: list[RecursoItem]
