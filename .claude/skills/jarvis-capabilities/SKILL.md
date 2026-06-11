---
name: jarvis-capabilities
description: Índice completo de las capacidades de JARVIS-IA (tools nativas, servidores MCP y dominios de control). Cargá esto cuando trabajes en este repo y necesites saber qué tools/integraciones ya existen antes de crear algo nuevo o para no duplicar funcionalidad.
---

# Capacidades de JARVIS-IA

Antes de crear una tool nueva, revisá si ya existe acá. Cada tool nativa vive en `actions/<nombre>.py`,
se registra en `STANDARD_TOOL_HANDLERS` (main.py) y se declara en `core/tool_declarations.py`.

## Tools nativas (por dominio)

**Sistema / OS (cross-platform):** `system_control` (apps, procesos, batería, CPU/RAM, volumen, portapapeles, caffeinate), `mac_control` (Notas, Recordatorios, iMessage, Finder, screenshot, modo oscuro, WiFi, navegador, permisos), `computer_control` (teclado/mouse pyautogui), `computer_settings`, `desktop_control`, `open_app`, `screen_process`/`system_monitor`, `sleep_mode`, `shutdown_jarvis`, `set_theme` (color de la UI).

**Código / agentes:** `code_agent` (agente propio multi-cerebro, edita en rama, no despliega solo), `claude_code` (CLI de Claude Code headless, sin API key), `consult_model` + `model_config` (cerebro de pensamiento: gemini/openai/claude/minimax/claude_cli), `terminal_agent`, `auto_programmer`, `self_edit`, `tool_creator`, `git_control`.

**Web / info:** `web_search` (ddgs), `browser_agent` (Playwright: scrape/article/extract/screenshot/fill), `realtime_info` (cripto/divisas/acciones/noticias), `weather_report`, `image_fetch`, `youtube_video`, `media_download` (yt-dlp).

**Documentos / media:** `document_creator` (Word/Excel/PowerPoint/texto + resumir/traducir/OCR), `media_edit` (imagen PIL + PDF pypdf + quitar fondo), `file_controller`, `smart_file_organizer`, `knowledge_base`.

**Diseño / Adobe:** `adobe_control` — ~110 ops curadas vía ExtendScript (Mac osascript / Win COM), partidas por app en `core/adobe/{illustrator,photoshop,indesign,common}.py` (fachada `core/adobe_ops.py`): formas/color/tipografía/capas/máscaras/filtros/maquetación (Tiers 2-11), run NL→ExtendScript, detect_faces + place_in_face (troqueles/dielines), place_trace, export, data_merge, open/save/close/info. `figma_control` (REST API). Drift dispatch↔ops cubierto por tests/test_adobe_split.py.

**Casa / dispositivos:** `smart_home` (Tuya + Philips Hue: on/off/brightness/color/white/scenes/functions/set_value), `camera_vision` (webcam bajo demanda + Gemini vision).

**Google:** `google_calendar`, `gmail_control`, `google_drive`, `google_maps`.

**Comunicación:** `unified_communications` (Telegram/Discord/Gmail), `whatsapp` + `whatsapp_connect` (bridge whatsmeow), `notifications` (alertas proactivas + No Molestar), `spotify_control` (Web API real).

**Asistente / memoria:** `save_memory`, `recall`, `planner`, `morning_brief`, `reminder`, `scheduler`, `goals`, `user_profile`, `rules_engine`, `contextual_control`, `proactive_automation`, `skill_teach` (aprende skills), `skill_workshop`, `compact_sessions`, `mcp_explorer`, `manage_keys` (ventana de API keys), `jarvis_ui_control`/`native_ui`.

## Servidores MCP activos (config/mcp_servers.json)
`memory`, `thinking`, `github`, `telegram`, `whatsapp`. Sus tools aparecen como `mcp__<server>__<tool>`.
Hay más disponibles deshabilitados (playwright, filesystem, brave, spotify, notion, composio) y se pueden
sumar otros (ej. `figma` via `figma-developer-mcp`). El cliente MCP está en `core/mcp_client.py`.

## Notas clave
- La VOZ siempre es Gemini 2.5 Flash; el "pensar" es configurable (ver `core/llm_router.py`).
- Secretos en `.env` (no en el JSON). Permisos macOS se piden vía `core/permissions.py`.
- No dupliques: si pedís "agregá búsqueda web", ya existe `web_search`/`browser_agent`.
