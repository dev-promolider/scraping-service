# Scrapegraph API

API en FastAPI que expone [scrapegraphai](https://github.com/ScrapeGraphAI/Scrapegraph-ai) para extraer informacion estructurada de paginas web usando un LLM (OpenAI).

## Indice

- [Requisitos](#requisitos)
- [Instalacion](#instalacion-paso-a-paso)
- [Configuracion (.env)](#configuracion-env)
- [Levantar el servidor](#levantar-el-servidor)
- [Como probar la API](#como-probar-la-api)
  - [Swagger UI](#swagger-ui)
  - [curl](#curl)
  - [Postman](#postman)
- [Endpoints](#endpoints)
- [CLI de ejemplo](#cli-de-ejemplo)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Detalle tecnico: SPAs](#detalle-tecnico-contenido-cargado-por-js-spas-y-sus-limites)
- [Limitaciones conocidas](#limitaciones-conocidas)

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

## Configuracion (.env)

Crea un archivo `.env` en la raiz del proyecto (no se commitea, ya esta listado en `.gitignore`):

```
OPENAI_API_KEY=tu-api-key-de-openai
OPENAI_MODEL=openai/gpt-4o-mini
```

| variable         | obligatoria | descripcion                                                                          |
| ---------------- | ----------- | --------------------------------------------------------------------------------------- |
| `OPENAI_API_KEY` | si          | Sin ella la API responde `500` en cualquier request que scrapee.                       |
| `OPENAI_MODEL`   | no          | Default `openai/gpt-4o-mini`, el unico verificado como estable con `schema` forzado -- ver [detalle tecnico](#detalle-tecnico-contenido-cargado-por-js-spas-y-sus-limites). |

## Levantar el servidor

```bash
uv run uvicorn scrapegraph_api.api:app --reload
```

`--reload` reinicia el servidor automaticamente al guardar cambios en el codigo; podes omitirlo en un uso mas "productivo".

**Windows**: si da `error: Failed to spawn: 'uvicorn' ... Una directiva de Control de aplicaciones bloqueo este archivo`, es Smart App Control/Application Control de Windows bloqueando el `.exe` de `uvicorn` dentro de `.venv`. Solucion: correrlo como modulo de Python en vez de invocar el ejecutable directamente:

```bash
uv run python -m uvicorn scrapegraph_api.api:app --reload
```

Una vez levantado:

- API: http://127.0.0.1:8000
- Documentacion interactiva (Swagger): http://127.0.0.1:8000/docs

## Como probar la API

Con el servidor corriendo, confirma primero el healthcheck:

```bash
curl http://127.0.0.1:8000/
```

Deberia devolver `{"message":"Scrapegraph API is running"}`. Si da error de conexion, el servidor no esta corriendo o esta en otro puerto/host.

Para probar `/recursos` (el endpoint que scrapea de verdad, ver [detalle](#post-recursos)) tenes tres opciones. Las tres tardan varios segundos en responder (el servidor arranca un navegador Playwright y llama al LLM), asi que no es un timeout si tarda unos segundos.

### Swagger UI

La mas comoda para probar a mano, sin herramientas externas:

1. Abrir http://127.0.0.1:8000/docs
2. Desplegar `POST /recursos`
3. Click en **"Try it out"**
4. Completar el body (ver ejemplo en [Endpoints](#post-recursos))
5. Click en **"Execute"**

### curl

```bash
curl -X POST http://127.0.0.1:8000/recursos \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "python para principiantes",
    "max_items": 2
  }'
```

### Postman

1. **Method**: `POST`
2. **URL**: `http://127.0.0.1:8000/recursos`
3. **Body** → pestaña `Body` → `raw` → tipo `JSON` (Postman agrega el header `Content-Type: application/json` solo):

   ```json
   {
     "topic": "python para principiantes",
     "max_items": 5
   }
   ```

4. Click **Send**.

En cualquiera de los tres casos, la respuesta tiene siempre la misma forma fija -- ver [Endpoints](#post-recursos) para el detalle completo y los codigos de error.

## Endpoints

### `GET /`

Healthcheck.

```json
{ "message": "Scrapegraph API is running" }
```

### `POST /recursos`

Unico endpoint de scraping del proyecto. Dado un `topic`, busca en **Hotmart** (marketplace fijo, no configurable via request) y devuelve una salida con forma fija -- pensada para ser consumida por otro backend sin ambiguedad -- con **titulo**, **descripcion breve** y **precio** (convertido a USD) de cada curso encontrado.

**Request**

| campo       | tipo   | descripcion                                                     |
| ----------- | ------ | ---------------------------------------------------------------- |
| `topic`     | string | Tema a buscar (ej. `"python para principiantes"`)               |
| `max_items` | int    | Maximo de cursos a extraer de la pagina de resultados (1-100, default 40) |

```json
{
  "topic": "python para principiantes",
  "max_items": 2
}
```

**Response** (forma fija, siempre la misma estructura sin importar el topic o la cantidad de resultados)

```json
{
  "topic": "python para principiantes",
  "courseTitles": [
    {
      "title": "Python desde cero: fundamentos para principiantes",
      "description": "Curso introductorio que cubre sintaxis basica, variables y estructuras de control.",
      "price": "$40.94"
    },
    {
      "title": "Programacion en Python: de principiante a intermedio",
      "description": "Aprende los fundamentos de Python y avanza hacia conceptos de programacion orientada a objetos.",
      "price": "$60.97"
    }
  ]
}
```

Errores: `422` si `topic` es invalido, `500` si falta `OPENAI_API_KEY`, `502` si el scraping falla.

**Como funciona internamente** (`fetch_course_titles` en `src/scrapegraph_api/scraping.py`):

1. Arma la URL de busqueda en Hotmart a partir de `topic` (`build_search_url`).
2. Llama a `SmartScraperGraph` con `schema=ListaCursosDetectados` (Pydantic, definido en `models.py`) para forzar salida estructurada del LLM -- evita el bug conocido del parser JSON de texto libre en `generate_answer_node.py` de `scrapegraphai`, y garantiza que la respuesta siempre tenga la misma forma (nunca un dict libre segun lo que "decida" el LLM).
3. Usa `gpt-4o-mini` por la misma razon (modelo verificado como estable con schema).
4. Convierte cada precio a USD con tasas de cambio fijas en `TASAS_A_USD` (`currency.py`; no se le pide al LLM que "adivine" el tipo de cambio). Si la moneda detectada no esta en esa tabla, `price` se deja en su valor y moneda original sin convertir (ej. `"45.0 EUR"`).

## CLI de ejemplo

`uv run extraer-cursos [topic]` (default `"Python"`) reutiliza `fetch_course_titles` (`src/scrapegraph_api/cli.py`), la misma funcion que usa la API, e imprime el resultado por consola sin levantar el servidor.

```bash
uv run extraer-cursos "excel"
```

## Estructura del proyecto

```
src/scrapegraph_api/
├── __init__.py    # marcador del paquete
├── api.py         # app FastAPI y endpoints (capa fina, delega en los modulos de abajo)
├── models.py       # schemas Pydantic (requests/responses, contrato fijo de la API)
├── config.py        # lectura de env vars y config del graph de scrapegraphai
├── currency.py      # tasas de cambio y conversion de precios a USD
├── scraping.py       # fetch_course_titles: la logica de scraping en si (siempre contra Hotmart)
└── cli.py            # CLI de ejemplo (entry point `extraer-cursos`)
```

`api.py` no tiene logica propia de scraping ni de conversion de moneda: solo arma la `FastAPI app`, valida el request con los modelos de `models.py` y llama a las funciones de `config.py`/`scraping.py`. Esto permite reusar `fetch_course_titles` tanto desde la API como desde la CLI sin duplicar codigo.

## Detalle tecnico: contenido cargado por JS (SPAs) y sus limites

`scrapegraphai` usa Playwright para obtener el HTML de cada pagina. Por defecto solo espera a `domcontentloaded`, sin esperar a que terminen las llamadas asincronas que hidratan la pagina. En sitios tipo SPA, las tarjetas de producto/curso (con su precio) suelen cargarse en una llamada posterior a la carga inicial y no estan presentes en ese HTML, aunque si sean visibles para un usuario real en el navegador.

**Solucion aplicada**: `build_graph_config` pasa `loader_kwargs={"load_state": "networkidle", "timeout": 30}`, lo que hace que Playwright espere a que la red quede inactiva (JS ya hidratado) antes de leer el HTML, sin perder el modo stealth normal de scraping (a diferencia de la alternativa `requires_js_support: True`, que usa un codepath distinto sin stealth). Verificado contra Hotmart (`hotmart.com/es/marketplace/productos?q=...`): funciona bien, titulo y precio correctos.

## Limitaciones conocidas

- **Marketplace fijo (Hotmart)**: `/recursos` no acepta otra fuente por request; si en el futuro se necesita otro marketplace hay que extender `build_search_url` en `scraping.py`.
- **Chunking de paginas largas**: en paginas con mucho contenido, el dato buscado puede quedar en una parte que el pipeline de resumen/extraccion no prioriza.
- **Costo y latencia**: cada llamada a `/recursos` implica al menos una llamada al LLM y un render de pagina completo con Playwright, asi que el tiempo de respuesta es del orden de varios segundos.
