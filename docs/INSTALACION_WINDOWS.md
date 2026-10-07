# Instalación en Windows

Esta guía instala `busqueda-web-mcp` en Windows y lo conecta con LM Studio. El servidor usa stdio: LM Studio inicia Python y se comunica con él directamente. No necesitas abrir puertos ni obtener API keys.

## 1. Requisitos

- **Python 3.11 o superior**, con pip y venv. Descárgalo desde [Python para Windows](https://www.python.org/downloads/windows/).
- **Git para Windows**, disponible en [git-scm.com](https://git-scm.com/downloads/win). Si prefieres descargar el proyecto como ZIP, Git es opcional.
- **LM Studio con soporte MCP**, disponible desde la versión 0.3.17. Descárgalo desde [lmstudio.ai](https://lmstudio.ai/).
- Internet para instalar las dependencias y realizar búsquedas o lecturas de páginas públicas.

Abre **PowerShell** desde el menú Inicio y comprueba:

```powershell
python --version
python -m pip --version
git --version
```

Si `python` no funciona pero `py --version` sí, usa `py` en los comandos iniciales de Python. Confirma que la versión elegida sea al menos 3.11. Después de instalar Python o Git, vuelve a abrir PowerShell para que reconozca sus comandos.

## 2. Descargar el proyecto

Ejecuta en PowerShell, sin permisos de administrador:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\dev" | Out-Null
Set-Location "$env:USERPROFILE\dev"
git clone https://github.com/konatox/busqueda-web-mcp.git
Set-Location .\busqueda-web-mcp
```

La carpeta habitual será `C:\Users\TU_USUARIO\dev\busqueda-web-mcp`. Puedes elegir otra ubicación; conserva su ruta para configurar LM Studio.

**Alternativa sin Git:** abre el [repositorio](https://github.com/konatox/busqueda-web-mcp), selecciona **Code > Download ZIP** y extrae todo su contenido. Entra en la carpeta que contiene `pyproject.toml` (normalmente `busqueda-web-mcp-main`) usando `Set-Location "C:\ruta\busqueda-web-mcp-main"`. Los pasos restantes son iguales; para actualizar una copia ZIP, descarga y extrae la nueva versión y vuelve a instalarla.

## 3. Crear el entorno e instalar

Desde la carpeta que contiene `pyproject.toml`:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .
& .\.venv\Scripts\python.exe -m pip check
```

Si utilizas `py`, el primer comando será `py -m venv .venv`. Los siguientes siguen usando el ejecutable de `.venv`.

`pip install -e .` instala el proyecto y sus dependencias declaradas en `pyproject.toml`. Si `pip check` termina con `No broken requirements found.`, las dependencias instaladas son coherentes.

Estos comandos invocan Python directamente: no necesitas activar el entorno ni cambiar la política de ejecución de PowerShell. Esta forma de usar venv está contemplada en la [documentación oficial de Python](https://docs.python.org/3/library/venv.html).

### Si usas CMD en lugar de PowerShell

Usa estos comandos en **Símbolo del sistema**, desde la descarga hasta la instalación:

```bat
if not exist "%USERPROFILE%\dev" mkdir "%USERPROFILE%\dev"
cd /d "%USERPROFILE%\dev"
git clone https://github.com/konatox/busqueda-web-mcp.git
cd busqueda-web-mcp
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m pip check
```

Si ya descargaste el proyecto, entra en su carpeta y comienza en `python -m venv .venv`. En CMD no se usa el operador `&` delante del ejecutable.

## 4. Configurar LM Studio

1. Abre LM Studio y un chat con un modelo que soporte llamadas a herramientas.
2. En la barra lateral derecha, abre **Program > Install > Edit mcp.json**, según la [guía oficial de LM Studio](https://lmstudio.ai/docs/app/mcp).
3. Agrega la entrada `busqueda-web` al objeto `mcpServers`. Si ya tienes otros servidores, conserva sus entradas.

Para una instalación sin otros servidores, el contenido completo es:

```json
{
  "mcpServers": {
    "busqueda-web": {
      "command": "C:/Users/TU_USUARIO/dev/busqueda-web-mcp/.venv/Scripts/python.exe",
      "args": ["-m", "busqueda_web_mcp.server"]
    }
  }
}
```

También puedes partir de [examples/mcp.windows.json](../examples/mcp.windows.json).

Reemplaza `TU_USUARIO` y cualquier carpeta diferente por tu ruta real. `command` debe apuntar al archivo **python.exe** del entorno virtual, incluso si instalaste el proyecto desde un ZIP. Las barras `/` permiten escribir la ruta en JSON sin escapes; si usas barras invertidas, escribe cada una como `\\`. No uses `%USERPROFILE%`, `$env:USERPROFILE` ni `~` en `command`: coloca la ruta absoluta.

Para obtener un JSON con tu ruta exacta, ejecuta desde la carpeta del proyecto en PowerShell:

```powershell
$mcpConfig = @{
    mcpServers = @{
        'busqueda-web' = @{
            command = (Resolve-Path .\.venv\Scripts\python.exe).Path
            args = @('-m', 'busqueda_web_mcp.server')
        }
    }
}
$mcpConfig | ConvertTo-Json -Depth 4
```

Este comando solo muestra la configuración; cópiala al editor de LM Studio. No sustituye automáticamente tus servidores existentes.

Guarda el archivo, habilita el servidor en el chat y comprueba que aparezcan **web_search** y **fetch_url**. Si el servidor no se recarga, reinícialo desde LM Studio o vuelve a abrir la aplicación. LM Studio inicia el proceso: no hace falta mantener una terminal abierta ni activar `.venv` antes de abrir la aplicación.

## 5. Comprobar la instalación

Desde la carpeta del proyecto, ejecuta en PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe scripts\check_stdio.py
```

La suite debe terminar con `OK`. La comprobación del protocolo debe imprimir `MCP stdio OK: initialize, list_tools, blocked fetch_url, parameter validation`. Ambas pruebas funcionan sin Internet; algunos tests imprimen errores simulados de forma intencional.

Para comprobar una búsqueda y una lectura reales:

```powershell
& .\.venv\Scripts\python.exe scripts\manual_search.py "Python asyncio documentation" --read
& .\.venv\Scripts\python.exe scripts\manual_fetch.py "https://example.com"
```

Estas pruebas necesitan Internet. DuckDuckGo puede limitar peticiones o devolver resultados vacíos. En LM Studio puedes probar: **«Busca documentación oficial de Python asyncio, lee el resultado más relevante y cita su URL»**.

Para iniciar el servidor manualmente como diagnóstico:

```powershell
& .\.venv\Scripts\python.exe -m busqueda_web_mcp.server
```

Es normal que espere sin mostrar texto: está esperando mensajes MCP. Pulsa **Ctrl+C** para cerrarlo.

## 6. Actualizar

Si instalaste mediante Git, detén el servidor en LM Studio y ejecuta desde su carpeta:

```powershell
git pull --ff-only
& .\.venv\Scripts\python.exe -m pip install -e .
& .\.venv\Scripts\python.exe -m pip check
```

Después reinicia el servidor en LM Studio. Si cambias de carpeta, recrea el entorno virtual y actualiza la ruta de `command`; los entornos venv no deben copiarse entre ubicaciones o sistemas operativos.

## Solución de problemas

| Problema | Qué revisar |
| --- | --- |
| `python` no se reconoce o abre Microsoft Store | Comprueba `py --version`. Si tampoco funciona, instala Python y vuelve a abrir la terminal. Usa el ejecutable de Python instalado o revisa sus alias de ejecución en Windows. |
| `git` no se reconoce | Instala Git para Windows y vuelve a abrir la terminal, o usa la descarga ZIP. |
| No existe `.venv\Scripts\python.exe` | Entra en la carpeta que contiene `pyproject.toml` y ejecuta de nuevo `python -m venv .venv`. |
| PowerShell bloquea `Activate.ps1` | Sigue los comandos de esta guía con `.venv\Scripts\python.exe`; no requieren activación. |
| `ModuleNotFoundError: busqueda_web_mcp` | Ejecuta `& .\.venv\Scripts\python.exe -m pip install -e .` desde la carpeta del proyecto y usa ese mismo Python en LM Studio. |
| JSON inválido | Usa comillas dobles, elimina comas finales y escribe las rutas con `/` o `\\`. |
| LM Studio no inicia el servidor | Revisa la ruta absoluta en `command` y los logs MCP; verifica primero `scripts\check_stdio.py`. |
| Las herramientas aparecen pero el modelo no las usa | Habilita el servidor en el chat y usa un modelo con soporte de llamadas a herramientas. |
| Error de conexión, DNS, certificado o límite de DuckDuckGo | Comprueba Internet y prueba `scripts\manual_fetch.py`. El lector necesita salida directa a Internet y no usa los proxies del entorno. |

La guía se revisó desde Linux; no se ejecutó una instalación real en Windows. Los comandos y la estructura de venv siguen la [documentación de Python para Windows](https://docs.python.org/3/using/windows.html) y la configuración sigue la guía MCP de LM Studio. Consulta [README.md](../README.md) para los límites del servidor y [VALIDATION.md](../VALIDATION.md) para el historial de pruebas.
