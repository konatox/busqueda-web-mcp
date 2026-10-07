# busqueda-web-mcp

MCP local pequeño para buscar con DuckDuckGo y leer páginas públicas desde LM Studio. Python 3.11+, transporte **stdio**, sin puertos, API keys, Docker, bases de datos ni procesos auxiliares permanentes. Pensado para modelos pequeños: dos herramientas, schemas simples y respuestas limitadas.

## Instalación en CachyOS / Arch Linux

Instala Python y pip con el gestor del sistema si faltan (`sudo pacman -S python python-pip`). No uses `sudo pip`.

Clona el repositorio e instala el proyecto en un entorno virtual:

```bash
git clone https://github.com/konatox/busqueda-web-mcp.git ~/dev/busqueda-web-mcp
cd ~/dev/busqueda-web-mcp
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

En **Fish**, cambia únicamente la activación:

```fish
source .venv/bin/activate.fish
python -m pip install -e .
```

Los tests usan `unittest`, incluido en Python. Las dependencias directas son el SDK oficial `mcp` (FastMCP incluido, rama 1.x), `httpx`, `beautifulsoup4` y `ddgs`. Se fija `backend="duckduckgo"` y se rechaza un backend no disponible para impedir el fallback automático de DDGS; no se usa Google. El lector usa `busqueda-web-mcp/1.0`; DDGS gestiona su propio User-Agent de navegador.

## Ejecución

```bash
python -m busqueda_web_mcp.server
# O el script instalado:
busqueda-web-mcp
```

Es normal que el proceso espere sin imprimir nada: habla JSON-RPC por stdin/stdout; no es una CLI de chat. Ctrl+C lo detiene. Todos los logs van a stderr.

El nombre de distribución y del comando es `busqueda-web-mcp`; el módulo Python usa guiones bajos (`busqueda_web_mcp`) para mantener imports convencionales. Instala primero el paquete: entonces funciona desde cualquier directorio, sin `PYTHONPATH`.

## LM Studio

En la configuración MCP de LM Studio, agrega este contenido a `mcp.json` (integra `mcpServers` con los servidores existentes):

```json
{
  "mcpServers": {
    "busqueda-web": {
      "command": "/home/konatox/dev/busqueda-web-mcp/.venv/bin/python",
      "args": ["-m", "busqueda_web_mcp.server"]
    }
  }
}
```

También disponible en `examples/mcp.json`. Ajusta la ruta si instalaste en otro lugar. LM Studio inicia el proceso; no necesitas iniciarlo en otra terminal. Selecciona un modelo con soporte de llamadas a herramientas y habilita este MCP en el chat. La calidad de la elección de herramientas depende del modelo y su plantilla.

Documentación de referencia: [MCP en LM Studio](https://lmstudio.ai/docs/app/mcp), [SDK oficial Python](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x), [DDGS](https://github.com/deedy5/ddgs).

## Herramientas

| Herramienta | Parámetros | Respuesta |
| --- | --- | --- |
| `web_search` | `query`, `max_results=5` (1–8) | `query`, `results`: título (`title`), URL (`url`), snippet (`snippet`) |
| `fetch_url` | `url`, `max_chars=12000` (1–30000) | URL final (`url`), `title`, `text`, `truncated` |

```json
{"query": "latest comfyui release", "max_results": 3}
```

```json
{"url": "https://example.com", "max_chars": 4000}
```

Los errores devuelven `error: true` y un `message` breve. `fetch_url` conserva además `url`, `title`, `text`, `truncated`; si la petición falla, `url` es la URL solicitada y el contenido queda vacío. Los errores de esquema MCP se devuelven como errores de herramienta del SDK, sin traceback. Los detalles técnicos se registran en stderr.

Prompts de ejemplo:

> Busca cuál es la última versión de ComfyUI.

> Busca información reciente sobre Proton y Helldivers 2 y revisa el resultado más relevante.

> Busca documentación oficial de Python asyncio. Lee solo el resultado más relevante con un máximo de 4000 caracteres y cita su URL.

## Límites y seguridad

Todos los límites están en `src/busqueda_web_mcp/config.py`: 8 resultados, timeout de 10 segundos, 30000 caracteres por página, descarga máxima de 2 MB descomprimidos, 5 redirecciones, query de 500 caracteres, URL de 4096 caracteres, títulos de 300 y snippets de 500. Los parámetros fuera de rango se rechazan. El timeout de lectura incluye DNS, redirecciones y descarga.

La caché de búsqueda usa memoria local: TTL de 5 minutos, máximo 100 entradas. Desactívala con `CACHE_ENABLED = False` y reinicia el MCP. No persiste datos en disco.

`fetch_url` solo acepta HTTP/HTTPS sin credenciales. Rechaza localhost, direcciones no globales, privadas, loopback, link-local, multicast, reservadas y metadata cloud. Valida **todas** las respuestas DNS y cada redirección. Conecta a una IP comprobada, conservando `Host` y el hostname TLS para evitar una segunda resolución DNS vulnerable a rebinding. Mantiene la verificación de certificados e ignora proxies del entorno en el lector.

Si falla el establecimiento de conexión con una IP, prueba las demás IP públicas validadas del dominio dentro del mismo timeout total. No reintenta errores HTTP ni descargas interrumpidas.

Las páginas son datos externos: pueden contener instrucciones maliciosas. El modelo debe usarlas como fuentes, sin obedecer instrucciones incrustadas. Este filtro de red no reemplaza el aislamiento del sistema operativo frente a un administrador de red malicioso.

## Tests y prueba real

```bash
python -m unittest discover -s tests -v
python scripts/check_stdio.py
python scripts/manual_search.py 'última versión ComfyUI'
```

Los tests y `check_stdio.py` funcionan sin Internet. Este último inicia el servidor como subproceso, negocia MCP, comprueba las dos herramientas y ejecuta una llamada bloqueada. `manual_search.py` usa DuckDuckGo real; devuelve un código de salida distinto de cero ante error o búsqueda sin resultados. Para probar también una lectura pública:

```bash
python scripts/manual_search.py 'Python asyncio documentation' --read
```

La prueba real requiere Internet y puede fallar por límites de DuckDuckGo. No es parte de la suite offline.

## Limitaciones y futuras mejoras

- DuckDuckGo puede devolver CAPTCHA, rate limit, resultados vacíos o cambiar sus endpoints. No hay SLA, reintentos automáticos ni fallback a otro buscador. DDGS se encarga de su mecanismo web; su timeout limita peticiones y el servicio limita cuánto espera una llamada. Un trabajo síncrono iniciado en un thread puede terminar después del timeout; no se puede cancelar forzosamente ese thread.
- No ejecuta JavaScript, no inicia sesión ni procesa PDF, imágenes, vídeo o formatos binarios. Acepta HTML/XHTML y texto plano. Una página superior a 2 MB se rechaza.
- La extracción es heurística: prioriza `main`, contenido con `role=main` o `article`, conserva encabezados/párrafos/listas y elimina navegación, formularios y duplicados. Puede omitir contenido útil en sitios atípicos; la codificación sin charset se interpreta con el fallback de httpx.
- Las URLs de búsqueda son referencias, no se descargan ni resuelven automáticamente. Se validan de nuevo al llamar `fetch_url`.
- `search_and_read` queda fuera de v1 para mantener mínimo el contexto y dejar la selección al modelo. Una futura implementación debe limitarse a `MAX_SEARCH_AND_READ_PAGES = 3` y reutilizar los servicios actuales.
- Para nuevos proveedores, implementa `SearchProvider.search` e inyéctalo en `SearchService`. No hace falta cambiar las herramientas MCP.

## Solución de problemas

- **ModuleNotFoundError**: ejecuta `python -m pip install -e .` con el mismo Python configurado en `mcp.json`; usa `busqueda_web_mcp.server` con guiones bajos.
- **El servidor no imprime nada**: es normal con stdio. Usa `python scripts/check_stdio.py` para verificar el protocolo.
- **LM Studio no muestra herramientas**: revisa la ruta absoluta, JSON válido, logs MCP, activación del servidor y soporte de herramientas del modelo. Reinicia el servidor tras instalar o modificar configuración.
- **Timeout/rate limit**: revisa la conexión; espera y prueba una consulta corta. No aumentes ilimitadamente los límites.
- **Could not connect to the page**: falló la conexión HTTP; la búsqueda usa otro cliente y puede funcionar aunque el lector falle. Para ver el traceback con la causa concreta, ejecuta `python scripts/manual_fetch.py 'https://www.mimicpc.com/learn/how-to-craft-wan22-ai-video-prompts'`. Los errores de certificado y negociación TLS tienen mensajes específicos. El lector requiere salida directa a Internet y no usa los proxies del entorno.
- **URL bloqueada**: alguna IP DNS o redirección es privada/reservada; el bloqueo es intencional. No desactives la validación para leer servicios internos.
- **Unsupported Content-Type/texto vacío**: usa otra página HTML estática o texto plano. Los sitios que requieren JavaScript o bloquean clientes HTTP no se pueden leer con este lector.

La validación realizada y las restricciones del entorno de construcción están registradas en [VALIDATION.md](VALIDATION.md).
