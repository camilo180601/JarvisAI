# MCP — Cómo conectar servers externos a JARVIS

JARVIS soporta el [Model Context Protocol](https://modelcontextprotocol.io) — el mismo estándar que usa Claude Desktop. Cualquier MCP server compatible se puede agregar editando un JSON.

## Cómo funciona

1. Al arrancar, JARVIS lee `config/mcp_servers.json`
2. Por cada server: lanza un subprocess
3. Hace handshake JSON-RPC + `tools/list`
4. Las tools quedan disponibles como `mcp__<server>__<tool>` para Gemini

## Setup rápido — Filesystem MCP (1 minuto, sin riesgo)

Bueno para probar que todo anda. El filesystem MCP oficial permite a JARVIS leer/escribir archivos de una carpeta autorizada.

1. Copia el ejemplo:
   ```bash
   cp config/mcp_servers.example.json config/mcp_servers.json
   ```

2. Editar `config/mcp_servers.json`, dejar solo:
   ```json
   {
       "enabled": true,
       "servers": {
           "filesystem": {
               "command": "npx",
               "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/macbook/Documents"]
           }
       }
   }
   ```
   (Cambia la ruta por la carpeta que querés exponer)

3. Reiniciar JARVIS. En la consola:
   ```
   [MCP/filesystem] ✓ 11 tools cargadas
   [MCP] +11 tools agregadas al registry de Gemini
   ```

4. Probar por voz: "JARVIS, listame los archivos de mi carpeta de Documentos"

## Setup WhatsApp (15-30 min, mediano)

Necesita el bridge de Go + Python.

### Pre-requisitos
- Go ≥ 1.21: `brew install go`
- Python ≥ 3.11 con `uv` (recomendado) o `pip`: `brew install uv`

### Instalación

```bash
# 1. Clonar el repo
cd ~/Documents
git clone https://github.com/lharries/whatsapp-mcp.git
cd whatsapp-mcp

# 2. Arrancar el bridge Go una vez (genera el QR)
cd whatsapp-bridge
go run main.go
# → muestra QR ASCII en terminal
# → en celular: WhatsApp → Dispositivos vinculados → Vincular dispositivo → escanear
# → cuando dice "Logged in", Ctrl+C
```

El token quedó en `whatsapp-bridge/store/whatsapp.db`. Backupealo si no querés re-escanear.

### Configurar JARVIS

```bash
# Bridge corriendo en background (lo dejás abierto en otra terminal o lo lanzás con launchd)
cd <JARVIS>/integrations/whatsapp-mcp/whatsapp-bridge && go run main.go &
```

En `config/mcp_servers.json`:
```json
{
    "enabled": true,
    "servers": {
        "whatsapp": {
            "command": "uv",
            "args": [
                "--directory",
                "/Users/macbook/Documents/Proyectos/JARVIS-IA/integrations/whatsapp-mcp/whatsapp-mcp-server",
                "run",
                "main.py"
            ]
        }
    }
}
```

Reiniciar JARVIS. Deberías ver:
```
[MCP/whatsapp] ✓ 8 tools cargadas
```

### Tools que JARVIS gana

- `mcp__whatsapp__search_contacts(name)` — buscar contacto por nombre
- `mcp__whatsapp__list_chats()` — listar conversaciones recientes
- `mcp__whatsapp__list_messages(chat_jid)` — mensajes de un chat
- `mcp__whatsapp__send_message(recipient, message)` — enviar texto
- `mcp__whatsapp__download_media(message_id)` — descargar media
- etc.

### Pruebas por voz

- "JARVIS, decile a Juan que ya salí"
- "Buscame los últimos mensajes de mi mamá"
- "¿Me escribió Sofía hoy?"

## Otros MCPs útiles

| Server | Repo | Qué hace |
|---|---|---|
| Spotify | `marcelmarais/spotify-mcp-server` | Control playback + playlists |
| Playwright | `@playwright/mcp` | Automatización de browser real |
| GitHub | `@modelcontextprotocol/server-github` | PRs, issues, repos |
| Slack | `@modelcontextprotocol/server-slack` | Mensajes y canales |
| Memory | `@modelcontextprotocol/server-memory` | Memoria semántica con embeddings |
| Composio | `composio/mcp-server` | Mega-server con 250+ apps |

Para cualquiera: leer su README, agregar entry en `mcp_servers.json`, reiniciar JARVIS.

## Tips

- **Disabled flag**: en cada server podés poner `"disabled": true` para tenerlo configurado pero apagado.
- **Logs del server**: stderr del subprocess se filtra y solo se muestra si contiene "error"/"warn"/"fatal". Para debug full, lanzá el server a mano.
- **Cuando un server crashea**: JARVIS sigue funcionando — solo esas tools desaparecen hasta el próximo reinicio.
- **Naming**: si dos servers tienen tools con el mismo nombre, no hay conflicto porque el prefijo `mcp__<server>__` las separa.
- **Privacy**: cada MCP corre en tu máquina. Los mensajes/datos no van a Gemini hasta que JARVIS llame específicamente esa tool.

## windows-mcp (control avanzado de Windows)
Solo corre en Windows (`"platform": "win32"` — en Mac/Linux JARVIS lo omite solo).
15 tools vía **UIAutomation** (element-aware): Click/Type/Snapshot del árbol de UI,
App (lanzar/cambiar ventanas), PowerShell, Registry, Clipboard, Scrape, Screenshot.
Requisitos en la máquina Windows: Python 3.13+ y [uv](https://docs.astral.sh/uv/)
(`pipx install uv`). El server se levanta con `uvx windows-mcp serve` (JARVIS lo hace solo).

## figma (lectura de diseños)
`figma-developer-mcp` con tu `FIGMA_TOKEN` del `.env`: `get_figma_data` (estructura/estilos
de un archivo) y `download_figma_images` (SVG/PNG → ~/Pictures/JARVIS/figma).
`figma-devmode` (OFICIAL, get_design_context/get_screenshot) queda deshabilitado hasta que
actives en Figma Desktop: Preferences → Enable Dev Mode MCP Server (asiento Dev/Full).
