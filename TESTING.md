# JARVIS — Plan de Pruebas

Guía para validar todo el sistema antes de considerarlo estable. Dividido en
**automático** (corre solo) y **manual por voz** (vos hablándole a JARVIS).

---

## Nivel 0 — Smoke test automático (30 segundos)

Sin arrancar la UI. Valida que todos los módulos cargan y los subsistemas básicos andan.

```bash
python3 smoke_test.py            # resumen
python3 smoke_test.py --verbose  # con detalles
```

**Esperado**: `✅ Todos los chequeos críticos pasaron` (14 checks).
Si algo da ✗, arreglalo antes de seguir — la UI no va a andar bien.

Cubre: config, tool_declarations, skills, tool_resolver, episodic, planner,
notification engine, MCP, platform_utils.

---

## Nivel 0.5 — Suite de regresión (pytest, ~1 segundo)

Red de seguridad para refactors: la suite completa de tests unitarios y de contrato que corren
sin arrancar JARVIS ni los servers MCP (los tests fijan `JARVIS_SKIP_MCP=1`).

```bash
pip install -r requirements-dev.txt   # una vez
pytest                                 # corre todo (lee pytest.ini)
```

**Esperado**: que TODO pase. Qué cubre (`tests/`):
- `test_imports.py` — todos los módulos de `actions/`, `core/`, `memory/` importan.
- `test_tool_contract.py` — cada tool declarada tiene schema válido y es **ejecutable**
  (handler, dispatch especial, o fallback dinámico `actions/<name>.py`); ningún handler
  queda sin declarar. (Atrapa el desincronizado del registro de tools.)
- `test_registry_snapshot.py` — baseline en `tests/registry_baseline.json`: detecta si
  una tool **desaparece** sin querer durante un refactor. Re-basar a propósito = regenerar
  el JSON y revisar el diff.
- `test_mac_contacts.py` / `test_whatsapp.py` / `test_trading_bot.py` — lógica pura
  (normalización de acentos, resolución de contactos, indicadores SMA/RSI, compra/venta)
  con dependencias mockeadas (sin red, AppleScript ni SQLite).

Correr esto **antes y después** de cada cambio de arquitectura: si pasa igual, no rompiste nada.

---

## Nivel 1 — Arranque de JARVIS

```bash
# Con venv (recomendado, Python 3.11):
source .venv/bin/activate && python main.py
# o el launcher:
./dev.sh
```

**Checklist de consola al arrancar** — deberías ver:
- [ ] `[Skills] N skills cargadas desde skills/`
- [ ] `[MCP/memory] ✓ 9 tools cargadas`
- [ ] `[MCP/thinking] ✓ 1 tools cargadas`
- [ ] `[MCP] +N tools agregadas al registry de Gemini`
- [ ] `[MCP-Explorer] 🔭 Background runner iniciado`
- [ ] `[JARVIS] 📔 Episodic logger: ~/.jarvis/sessions/...jsonl`
- [ ] `[NotifEngine] 👁️ watcher iniciado con N source(s)` (tras conectar)
- [ ] `[JARVIS] 🔌 Conectando...` → la orbe aparece y reacciona
- [ ] Sin tracebacks rojos

---

## Nivel 2 — Tools core por voz

Probá una de cada categoría. Decí el comando, verificá que ejecuta (no que "dice" que ejecutó).

| Categoría | Comando de voz | Esperado |
|---|---|---|
| App | "Abrí la calculadora" | Calculator se abre |
| Volumen | "Bajá el volumen a 30" | volumen del Mac cambia |
| Terminal | "Corré `ls` en mi escritorio" | lista archivos |
| Web search | "Buscá el precio del dólar hoy" | resultados reales |
| Archivos | "Listame los archivos de Descargas" | lista real |
| Git | "¿Cómo está el git de este proyecto?" | git status |
| Maps | "Cómo llego de Bogotá a Medellín" | abre Maps |
| Knowledge | "Acordate que mi color favorito es azul" | guarda nota |
| Memoria larga | "¿Cuál es mi color favorito?" | responde azul |
| Delegación | "Escribime un ensayo corto sobre el café" | usa openrouter_agent |

**Criterio**: la acción REAL ocurre. Si JARVIS dice "listo" pero nada pasó → falla.

---

## Nivel 3 — Skills system

| Test | Comando | Esperado |
|---|---|---|
| Listar | "¿Qué skills tenés?" | enumera git_control, etc. |
| **Enseñar** | "Aprendete una skill: devolver un número random entre 1 y 100" | genera `skills/<nombre>/`, testea, activa |
| Usar la nueva | invocá la skill recién creada | ejecuta |
| Persistencia | reiniciá JARVIS, "¿qué skills tenés?" | la nueva sigue ahí |

Verificá en disco: `ls skills/` → debería aparecer la carpeta nueva con SKILL.md + skill.py.

---

## Nivel 4 — Memoria episódica

| Test | Comando | Esperado |
|---|---|---|
| Recall | (después de varios comandos) "¿Qué hicimos recién?" | lista acciones |
| Recall por tool | "¿Cuándo abrí una app por última vez?" | timestamps |
| Knowledge graph | "Acordate que Roberto es mi jefe de marketing" | mcp__memory__create_entities |
| Query graph | "¿Quién es Roberto?" | recupera del graph |

Verificá: `~/.jarvis/sessions/*.jsonl` crece, `~/.jarvis/memory_graph.json` se crea.

---

## Nivel 5 — Planner multi-step

| Comando | Esperado |
|---|---|
| "Buscá el clima de Bogotá y guardalo en mis notas" | plan de 2 pasos, ejecuta ambos |
| "Listame mis notas, después decime cuántas hay" | encadena knowledge_base |

Verificá en consola: `📋 Planificando...` → `▶️ [1/N]` por paso → resumen con ✓/✗.
Si un paso falla, debería ver `🔄 Replanificando`.

---

## Nivel 6 — Notificaciones + DND

**Setup previo**: iMessage (Full Disk Access) y/o Gmail activos.

| Test | Comando | Cómo verificar |
|---|---|---|
| Crear alerta | "Avisame si me escribe [contacto real]" | regla creada |
| **Disparar** | pedile a alguien que te mande un iMessage | JARVIS habla solo: "Te escribió X" |
| Listar | "¿Qué alertas tengo?" | enumera reglas |
| DND on | "Silenciá todo por 10 minutos" | confirma DND |
| DND respeta | llega mensaje durante DND | JARVIS NO habla |
| Whitelist | "Silenciá pero avisame si dicen urgente" + mensaje con 'urgente' | SÍ habla |
| DND off | "Quitá el silencio" | vuelve a notificar |

**Importante**: el primer arranque hace bookmark (no alerta de mensajes viejos). Probá con mensajes NUEVOS.

---

## Nivel 7 — MCP

| Test | Comando | Esperado |
|---|---|---|
| Explorer list | "¿Qué integraciones nuevas me servirían?" | top candidatos rankeados |
| Explorer details | "Contame del MCP de Obsidian" | plan de integración |
| Memory MCP | "Guardá en tu grafo que X" | create_entities |
| Activar playwright | flip `disabled:false` en config, reiniciar | `[MCP/playwright] ✓ 23 tools` |

---

## Nivel 8 — Cross-platform (si migrás a otra máquina)

| Check | Comando |
|---|---|
| OS detection | `python3 -c "from core.platform_utils import OS_NAME; print(OS_NAME)"` |
| Volumen | "Subí el volumen" (debe usar el método del SO correcto) |
| Notif sources | en Windows: imessage no aparece; en Mac sí |

---

## Nivel 9 — Resiliencia

| Escenario | Cómo probar | Esperado |
|---|---|---|
| Reconexión | matá el wifi 5s y volvé | reconecta sin perder contexto (session resumption) |
| Tool que falla | pedí algo de un MCP apagado | mensaje de error claro, no crash |
| Gemini 503 | (si pasa) | retry con backoff, cae a flash-lite |
| Skill rota | creá skill con código inválido | sandbox la rechaza, no rompe JARVIS |
| Stop | "pará" / botón DETENER mientras habla | corta audio inmediato |

---

## Criterio de "listo para empaquetar"

Antes de PyInstaller, todo esto debería pasar:
- [ ] Nivel 0 (smoke) = 14/14
- [ ] Nivel 1 (arranque limpio, sin tracebacks)
- [ ] Nivel 2 (al menos 8/10 tools core)
- [ ] Nivel 3 (enseñar + usar skill nueva)
- [ ] Nivel 6 (al menos 1 notificación real disparada)
- [ ] Nivel 9 (reconexión + stop)

Cuando esos pasen consistentemente, JARVIS está estable para bundle.
