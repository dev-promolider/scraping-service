# Servicio de catalogos de cursos

API FastAPI para consultar ofertas publicas de cursos. El endpoint historico
de Hotmart conserva el formato consumido por Pickle; la consulta multifuente
se ofrece por separado y requiere una clave propia del servicio.

## Comentarios públicos

`POST /recursos/comentarios` requiere `X-API-Key` con `SCRAPING_API_KEY`.
Recibe `{"courses":[{"source":"hotmart","url":"https://hotmart.com/..."}]}`,
con hasta 12 cursos de los dominios oficiales registrados. Extrae hasta cinco
reseñas por curso mediante JSON-LD `Review` o microdatos explícitos.
Cada resultado incluye `source`, `url`, `status` y `reviews`; cada reseña guarda
identificador, texto, origen y fecha/calificación cuando están publicados.
No guarda autores ni convierte descripciones comerciales en opiniones.
No sigue redirecciones ni elude restricciones. `blocked`, `error` o `not_exposed`
son resultados por curso: una fuente fallida no elimina las otras.

## Instalacion

El proyecto acepta Python 3.12 o superior y fija Python 3.14 en
`.python-version`. Con `uv` instalado:

```bash
uv sync
uv run python -m uvicorn scrapegraph_api.api:app --reload
```

No hace falta una clave de OpenAI para los extractores actuales. El codigo
consulta HTML publico y, cuando corresponda, APIs oficiales con credenciales.
Para usar `/recursos/multifuente`, crea `.env` en la raiz del repositorio con
una clave local:

```dotenv
SCRAPING_API_KEY=elige-una-clave-local
# Opcional: IP de referencia para mostrar precios regionales de Hotmart
HOTMART_SHOPPER_IP=1.1.1.1
```

Luego abre `http://127.0.0.1:8000/` para verificar el servicio y
`http://127.0.0.1:8000/docs` para probar los endpoints. `/recursos` mantiene
el contrato historico y no usa esa clave; `/recursos/multifuente` la requiere
en el header `X-API-Key`.

`/recursos` sigue sin autenticacion ni limite de solicitudes para conservar la
integracion actual con Pickle. Antes de exponerlo publicamente, debe protegerse
en el proxy o coordinarse la autenticacion con el cliente existente.

## Endpoints

`GET /` confirma que la API esta iniciada. `GET /plataformas` lista los
conectores registrados e indica si necesitan credenciales y si estan
configuradas. La documentacion interactiva esta en `/docs`.

Conectores habilitados actualmente: `hotmart`, `dataquest`,
`linux_foundation`, `educacionit`, `ebac`, `digitalhouse`, `le_wagon`,
`four_geeks`, `linkedin_learning`, `pluralsight` y `oreilly`. Los primeros
ocho consultan metadatos publicos. Los tres ultimos requieren acceso API
autorizado y credenciales. Que `configured` sea verdadero solo confirma que
las variables necesarias existen en el entorno; no garantiza que la cuenta,
red o plataforma respondan correctamente. El registro tampoco implica que
cada fuente haya sido probada en vivo desde esta maquina.

`POST /recursos` conserva el contrato de Pickle y consulta Hotmart:

```json
{"topic":"Python","max_items":3}
```

Su respuesta mantiene `topic` y `courseTitles`, con `title`, `description`
y `price` en cada curso. Un precio que no se pudo comprobar se representa
como `No disponible`; el precio cero se reserva para ofertas realmente gratis.
Las monedas distintas de USD se conservan con su codigo original.
Hotmart calcula el precio segun la IP enviada a su servicio. La variable
`HOTMART_SHOPPER_IP` permite fijar la ubicacion de referencia; sin ella se
conserva `1.1.1.1`, el valor que ya usaba el repositorio. Un precio local
puede variar por pais, promocion o momento de consulta.

`POST /recursos/multifuente` consulta solo las plataformas indicadas:

```bash
curl -X POST http://127.0.0.1:8000/recursos/multifuente \
  -H "Content-Type: application/json" \
  -H "X-API-Key: tu-clave" \
  -d '{"topic":"Python","platforms":["hotmart","educacionit"],"max_items":3}'
```

Configura `SCRAPING_API_KEY` en el entorno antes de usar este endpoint.
La respuesta incluye `courses` con fuente y URL, y `sources` con estado
`ok`, `empty`, `error` o `blocked`. Una fuente fallida no elimina los
resultados de las demas. Cada solicitud acepta hasta doce plataformas y
devuelve hasta cinco cursos por plataforma. Una
fuente que responda con bloqueo queda en pausa durante 15 minutos en ese
proceso de la API.
Algunos catalogos limitan cuantas fichas revisan para mantener acotado el
tiempo de respuesta; por eso `empty` significa que no se encontro coincidencia
en las fichas revisadas, no que la plataforma carezca de cursos sobre el tema.

El conector `platzi` está deshabilitado por defecto. Para habilitarlo en una
instalación local, configura `PLATZI_METADATA_ENABLED=true` solo después de
confirmar que el uso automatizado de sus páginas públicas y la reutilización
de esos datos son aceptables para tu caso. Solo consulta búsqueda y fichas
públicas; no accede a cuentas ni contenido de clases. Si la página expone los
campos, añade nivel, número de clases, horas, valoración, instructores y rutas
de aprendizaje a `metadata`; no infiere el plan de suscripción aplicable.
La respuesta histórica `/recursos` no cambia.

LinkedIn Learning usa su API oficial y requiere
`LINKEDIN_LEARNING_CLIENT_ID` y `LINKEDIN_LEARNING_CLIENT_SECRET` de una
organizacion autorizada. Sin esas credenciales, su consulta informa un error.
Pluralsight y O'Reilly usan sus APIs oficiales y requieren, respectivamente,
`PLURALSIGHT_API_KEY` y `OREILLY_MCP_TOKEN` de cuentas autorizadas.

## Verificacion

```bash
uv run python -m unittest discover -s tests -v
```

Los sitios pueden cambiar HTML, ofertas y condiciones de acceso. Cada
conector limita sus consultas, comprueba enlaces oficiales y falla de forma
visible cuando no reconoce la estructura o el sitio bloquea el acceso.
Las fuentes con una restriccion automatizada explicita no figuran en
`GET /plataformas`. Antes de uso en produccion, valida las condiciones de uso
y las reglas publicadas por cada sitio; pueden cambiar.
