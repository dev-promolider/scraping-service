# Scrapegraph API

API en FastAPI que expone [scrapegraphai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) para extraer informacion estructurada de paginas web usando un LLM (OpenAI).

## Requisitos

- Python >= 3.14 (el repo fija la version exacta en `.python-version`; `uv` la instala solo si no la tenes)
- [uv](https://docs.astral.sh/uv/) instalado y disponible en el `PATH`
- Una API key de OpenAI con acceso al modelo configurado (por defecto `gpt-4o-mini`)

## Instalacion paso a paso

1. **Clonar el repo y ubicarte en la carpeta del proyecto.**

2. **Instalar las dependencias** (uv crea el entorno virtual `.venv` automaticamente a partir de `pyproject.toml`/`uv.lock`, no hace falta crearlo ni activarlo a mano):

   ```bash
   uv sync
   ```

3. **Instalar el navegador que usa Playwright** (scrapegraphai lo necesita para renderizar las paginas; sin este paso el scraping falla):

   ```bash
   uv run playwright install chromium
   ```

4. **Crear el archivo `.env`** en la raiz del proyecto (no se commitea, ya esta listado en `.gitignore`):

   ```
   OPENAI_API_KEY=tu-api-key-de-openai
   OPENAI_MODEL=openai/gpt-4o-mini
   ```

   - `OPENAI_API_KEY` es obligatoria; sin ella la API responde `500` en cualquier endpoint que scrapee.
   - `OPENAI_MODEL` es opcional (default `openai/gpt-4o-mini`, el unico verificado como estable con `schema` forzado -- ver seccion tecnica abajo).

## Levantar el servidor

```bash
uv run uvicorn scrapegraph_api.api:app --reload
```

`--reload` reinicia el servidor automaticamente al guardar cambios en el codigo; podes omitirlo en un uso mas "productivo".

- API: http://127.0.0.1:8000
- Documentacion interactiva (Swagger): http://127.0.0.1:8000/docs

## Probar que quedo bien levantado

Con el servidor corriendo, confirma el healthcheck:

```bash
curl http://127.0.0.1:8000/
```

Deberia devolver `{"message":"Scrapegraph API is running"}`. Si da error de conexion, el servidor no esta corriendo o esta en otro puerto/host.

Para probar los endpoints que scrapean de verdad (`/scrape` y `/recursos`, ver detalle mas abajo) tenes dos opciones:

- **Swagger UI** (mas comodo para probar a mano): abrir http://127.0.0.1:8000/docs, desplegar el endpoint, click en "Try it out", completar el body y "Execute".
- **curl** desde la terminal, como en los ejemplos de cada endpoint abajo.

Ambos endpoints tardan varios segundos en responder (arrancan un navegador Playwright y llaman al LLM), asi que no es un timeout si tarda unos segundos.

## Estructura del proyecto

```
src/scrapegraph_api/
├── __init__.py    # marcador del paquete
├── api.py         # app FastAPI y endpoints (capa fina, delega en los modulos de abajo)
├── models.py       # schemas Pydantic (requests/responses)
├── config.py        # lectura de env vars y config del graph de scrapegraphai
├── currency.py      # tasas de cambio y conversion de precios a USD
├── scraping.py       # fetch_recursos_marketplace: la logica de scraping en si
└── cli.py            # CLI de ejemplo (entry point `extraer-cursos`)
```

`api.py` no tiene logica propia de scraping ni de conversion de moneda: solo arma la `FastAPI app`, valida el request con los modelos de `models.py` y llama a las funciones de `config.py`/`scraping.py`. Esto permite reusar `fetch_recursos_marketplace` tanto desde la API como desde la CLI sin duplicar codigo.

## Endpoints

### `GET /`

Healthcheck.

```json
{ "message": "Scrapegraph API is running" }
```

### `POST /scrape`

Scraping libre de una unica URL segun un prompt arbitrario (el formato de salida lo decide el LLM, sin schema forzado).

**Request**

| campo    | tipo   | descripcion                                |
| -------- | ------ | ------------------------------------------- |
| `url`    | string | URL de la pagina a scrapear                |
| `prompt` | string | Que informacion extraer y en que formato   |

```bash
curl -X POST http://127.0.0.1:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "prompt": "Dame el titulo principal y un resumen breve de la pagina"
  }'
```

**Response**

```json
{
  "result": {
    "content": { "titulo": "Example Domain", "resumen": "..." }
  }
}
```

Errores: `422` si `url`/`prompt` son invalidos, `500` si falta `OPENAI_API_KEY`, `502` si el scraping falla (sitio caido, sin red, timeout, etc.).

### `POST /recursos`

Endpoint principal del proyecto: dado el listado/busqueda de un marketplace (cursos, productos, servicios), devuelve solo **nombre** y **precio** (convertido a USD) de cada recurso encontrado. Pensado para funcionar con cualquier sitio de este tipo -- probado con Hotmart y Udemy -- no esta acoplado a un sitio en particular.

**Request**

| campo       | tipo   | descripcion                                                                          |
| ----------- | ------ | -------------------------------------------------------------------------------------- |
| `url`       | string | URL de una pagina de listado/busqueda del marketplace                                 |
| `max_items` | int    | Maximo de recursos a extraer de la pagina (1-100, default 40)                         |

```bash
curl -X POST http://127.0.0.1:8000/recursos \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://hotmart.com/es/marketplace/productos?q=python",
    "max_items": 8
  }'
```

**Response** (verificado en pruebas reales contra Hotmart)

```json
{
  "url": "https://hotmart.com/es/marketplace/productos?q=python",
  "recursos": [
    { "nombre": "Jornada Python", "precio": "$143.45" },
    { "nombre": "Python para Data Science e Analytics", "precio": "$40.94" },
    { "nombre": "Python Bot", "precio": "$60.97" },
    { "nombre": "Curso de Python", "precio": "$20.32" }
  ]
}
```

Errores: `422` si `url` es invalida, `500` si falta `OPENAI_API_KEY`, `502` si el scraping falla.

**Como funciona internamente** (`fetch_recursos_marketplace` en `src/scrapegraph_api/scraping.py`):

1. Llama a `SmartScraperGraph` con `schema=ListaRecursosDetectados` (Pydantic, definido en `models.py`) para forzar salida estructurada del LLM -- evita el bug conocido del parser JSON de texto libre en `generate_answer_node.py` de `scrapegraphai`.
2. Usa `gpt-4o-mini` por la misma razon (modelo verificado como estable con schema).
3. Convierte cada precio a USD con tasas de cambio fijas en `TASAS_A_USD` (`currency.py`; no se le pide al LLM que "adivine" el tipo de cambio). Si la moneda detectada no esta en esa tabla, `precio` se deja en su valor y moneda original sin convertir (ej. `"45.0 EUR"`).

**CLI de ejemplo**: `uv run extraer-cursos [tema]` arma la URL de busqueda de Hotmart para `tema` (default `"Python"`) y reutiliza `fetch_recursos_marketplace` (`src/scrapegraph_api/cli.py`), la misma funcion que usa la API. Tambien acepta `--url` para apuntar a cualquier otro marketplace directamente, ej. `uv run extraer-cursos --url "https://hotmart.com/es/marketplace/productos?q=excel"`.

## Detalle tecnico: contenido cargado por JS (SPAs) y sus limites

`scrapegraphai` usa Playwright para obtener el HTML de cada pagina. Por defecto solo espera a `domcontentloaded`, sin esperar a que terminen las llamadas asincronas que hidratan la pagina. En sitios tipo SPA, las tarjetas de producto/curso (con su precio) suelen cargarse en una llamada posterior a la carga inicial y no estan presentes en ese HTML, aunque si sean visibles para un usuario real en el navegador.

**Solucion aplicada**: `_build_graph_config` pasa `loader_kwargs={"load_state": "networkidle", "timeout": 30}`, lo que hace que Playwright espere a que la red quede inactiva (JS ya hidratado) antes de leer el HTML, sin perder el modo stealth normal de scraping (a diferencia de la alternativa `requires_js_support: True`, que usa un codepath distinto sin stealth).

**Resultados verificados al probar varios marketplaces:**

| Sitio      | URL de busqueda usada                                    | Resultado                                                                                   |
| ---------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Hotmart    | `hotmart.com/es/marketplace/productos?q=...`               | Funciona bien, nombre y precio correctos.                                                    |
| Udemy      | `udemy.com/courses/search/?q=...`                           | **Falla con timeout.** El HTML inicial (`load`) no trae las tarjetas (se renderizan despues via JS), y Udemy nunca llega a `networkidle` dentro del limite de accion de Playwright (~30s, fijo internamente por `scrapegraphai`/Playwright y no configurable via `loader_kwargs`). Se probo tambien el backend `playwright_scroll` de `scrapegraphai` como alternativa, pero tiene un bug propio de la libreria (intenta `pip install playwright_scroll`, un paquete que no existe) que lo hace inutilizable tal cual. |
| Coursera   | `coursera.org/search?query=...`                             | La mayoria de resultados son cursos por suscripcion sin precio individual visible en el listado -- limitacion del modelo de negocio del sitio, no del scraper. |

En resumen: `/recursos` generaliza bien a marketplaces cuyo listado hidrata rapido (Hotmart y sitios similares), pero sitios con trafico de red constante en segundo plano (analytics/trackers que nunca dejan la red "idle", como Udemy) pueden dar `502` por timeout -- es una limitacion de la version actual de `scrapegraphai`, no algo resoluble desde la config publica de esta API.

## Limitaciones conocidas

- **Timeout en SPAs con trafico de fondo constante**: ver tabla arriba (caso confirmado: Udemy).
- **Marketplaces sin precio en el listado** (ej. Coursera, suscripciones): `/recursos` puede devolver una lista vacia o incompleta si la pagina no muestra precio por recurso.
- **Chunking de paginas largas**: en paginas con mucho contenido, el dato buscado puede quedar en una parte que el pipeline de resumen/extraccion no prioriza.
- **Costo y latencia**: cada llamada a `/recursos` o `/scrape` implica al menos una llamada al LLM y un render de pagina completo con Playwright, asi que el tiempo de respuesta es del orden de varios segundos.
