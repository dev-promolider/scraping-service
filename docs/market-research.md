# Consolidación de mercado: fuentes y capacidades

La investigación ocurre antes de proponer títulos. El usuario revisa cursos,
señales externas y opiniones, decide el enfoque y confirma el alcance.

## Cursos y comentarios

- Los conectores habilitados aportan título, descripción, precio y URL cuando
  están disponibles. No todos ofrecen temarios completos ni métricas de ventas.
- Platzi puede aportar rutas asociadas, valoración y metadatos públicos;
  las rutas no se interpretan como un temario completo.
- `/recursos/comentarios` obtiene reseñas con marcado público explícito.
  Fuentes sin ese marcado se identifican como `not_exposed`.
- No se garantiza que todas las plataformas expongan opiniones o estadísticas.
- Una valoración, cantidad de reseñas o visualizaciones no acredita ventas.

## Señales externas

`POST /recursos/tendencias`, protegido con `SCRAPING_API_KEY`, recibe
`{"topic":"Python","region":"PE"}` y devuelve señales, comentarios públicos,
estado por fuente, fecha, periodo y región de consulta.

| Fuente | Acceso | Interpretación |
|---|---|---|
| Google News RSS | Público, sin clave adicional | Publicaciones recientes; no demanda ni crecimiento medido |
| Google Trends mediante SerpAPI | `SERPAPI_API_KEY` opcional en el scraper | Consultas relacionadas en tres meses y región elegida |
| YouTube Data API | `YOUTUBE_API_KEY` opcional en el scraper | Videos recientes, estadísticas observadas y comentarios públicos |

No se activan ni se contratan proveedores pagos automáticamente. Sin las claves
opcionales se conservan los estados `not_configured`; las publicaciones recientes
no se presentan como tendencias verificadas. La API alpha oficial de Google Trends
requiere acceso previo y no está configurada en esta implementación.

Nest configura la región con `MARKET_TREND_REGION` (predeterminado `PE`) y muestra
ese ámbito al usuario. La clave de Gemini no habilita por sí sola YouTube Data API.
Los errores de fuentes opcionales permiten continuar con cobertura parcial.
Los comentarios de espectadores se diferencian de reseñas de alumnos.

## Referencias técnicas

- https://developers.google.com/search/apis/trends
- https://serpapi.com/google-trends-api
- https://developers.google.com/youtube/v3/docs/search/list
- https://developers.google.com/youtube/v3/docs/videos/list
- https://developers.google.com/youtube/v3/docs/commentThreads/list

MCP no es necesario para estas consultas directas. Se puede incorporar después
un servidor que exponga las mismas capacidades y conserve la trazabilidad.
