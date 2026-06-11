# JARVIS-IA — guía para el agente de código (Claude Code)

Asistente personal por voz en **Python** (PyQt6 + Gemini Live para voz). Si trabajás en este repo,
seguí estas convenciones. Para el índice completo de capacidades, mirá el skill `jarvis-capabilities`
(en `.claude/skills/`) — NO necesitás cargarlo siempre, solo cuando sumes/toques una integración.

## Arquitectura (dónde vive todo)
- `main.py` — orquestador (la VOZ usa Gemini 2.5 Flash, audio nativo, Live API). Registra los handlers
  en `STANDARD_TOOL_HANDLERS`: `"nombre": (funcion, extras, fallback, log_prefix)`, y rutea las tool calls.
- `actions/` — una tool por archivo. El **schema vive junto al handler** vía el decorador `@tool` (Fase 1).
- `core/registry.py` — `@tool` (declaración autodescriptiva) + `ToolRegistry` + `first_party_declarations`
  (fusiona las tools `@tool` con el archivo base). `discover_action_tools()` importa todas las actions al arrancar.
- `core/tool_declarations.py` — SOLO las tools "especiales" UI-coupled (shutdown/restart/save_memory/…).
  El resto migró a `@tool` (pasó de ~1470 a ~90 líneas).
- `core/runtime/` — motores desacoplados del orquestador: `audio.py`, `voice.py`, `prompt.py`,
  `dispatcher.py` (ejecución de tools, **testeado**) y `context.py` (`ToolContext`, Fase 4).
- `core/theme.py` — motor de tema (paletas + tokens `C_*` + `apply_theme_tokens`). Referenciar por
  atributo (`theme.C_PRI`) para leer el valor vigente, nunca `from core.theme import C_PRI`.
- `core/` — más motores: `code_agent/`, `llm_router.py` (cerebro multi-proveedor), `credentials.py`,
  `mcp_client.py`, `platform_utils.py` (cross-OS).
- `ui.py` — `MainWindow` + `JarvisUI` (shell). `ui_widgets.py` — los 12 widgets del dashboard.
  `ui_helpers.py` — `RoundIconButton` + iconos nítidos + registro de iconos temáticos.
- `memory/SOUL.md` — personalidad + reglas del asistente (se inyecta al system prompt).
- `memory/config_manager.py` — config: secretos en `.env`, ajustes en `config/api_keys.json`.

## Para AGREGAR una tool nueva (patrón obligatorio)
1. Creá `actions/<nombre>.py` con el handler **decorado** (schema co-locado):
   ```python
   from core.registry import tool
   @tool(name="<nombre>", description="…", parameters={"type":"OBJECT","properties":{…},"required":[…]})
   def <nombre>(parameters, player=None) -> str:   # devolvé un string para la voz
       ...
   ```
   (Opcional, firma nueva tipada — Fase 4: `def <nombre>(ctx: ToolContext) -> str:` y usá `ctx.s/i/f/b`,
   `ctx.player`, `ctx.log/say`. El dispatcher detecta cuál firma usás.)
2. Importala y registrala en `STANDARD_TOOL_HANDLERS` en `main.py` (para el dispatch).
3. **NO** toques `core/tool_declarations.py` — el schema ya está en el `@tool`.
4. Si cambia el comportamiento del asistente, agregá una regla en `memory/SOUL.md`.
5. Secretos → `.env` (nunca al JSON). Cross-platform: usá `core/platform_utils.py`.

## Convenciones
- Respuestas de tools: string breve y claro (lo lee la voz). Errores: mensaje útil, no traceback.
- No rompas la separación voz/cerebro: la voz es Gemini Flash; el "pensar" va por `llm_router`.
- **Tests**: `pytest` (suite de regresión, ~1s, fija `JARVIS_SKIP_MCP=1`) + `python smoke_test.py` (14 chequeos)
  ANTES y DESPUÉS de cada cambio. Si refactorizás, ambos deben quedar verdes. Reportá fiel si algo falla.
- Cambios mínimos, sin gold-plating. Leé el archivo antes de editarlo.
