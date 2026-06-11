# JARVIS-IA

Asistente personal **por voz** para escritorio, en Python. La voz es **Gemini 2.5 Flash**
(audio nativo, Live API); el "pensar" se delega a un cerebro multi-proveedor configurable.
Interfaz *glassmorphic* en PyQt6 con un orbe reactivo, y un set grande de capacidades:
control del sistema, automatización de apps Adobe, navegador, archivos, casa inteligente,
mensajería, y un motor de skills extensible.

> Desarrollado y probado en **macOS** (Apple Silicon). El código es cross-platform donde
> tiene sentido (hay dependencias marcadas solo-Windows), pero el camino principal es macOS.

---

## ✨ Capacidades (resumen)

- **Voz en tiempo real** — Gemini Live (audio nativo). Reconocimiento local con Vosk para el modo suspensión. Saludo según la hora (buenos días/tardes/noches) en tu zona horaria.
- **Cerebro de pensamiento configurable** — Gemini (default), GPT, Claude (API, incluido **Fable 5** el más potente), MiniMax, o CLIs sin API key: **Claude Code CLI** y **Antigravity CLI**. Catálogo de modelos al día (GPT-5.5, Gemini 3.5/3.1 Pro, MiniMax M3) en `core/llm_router.py`; cambiá por voz ("usá Fable", "qué modelos hay"). Selector de prioridad para programar.
- **Adobe (Illustrator / InDesign / Photoshop)** — ~110 operaciones curadas vía ExtendScript: formas, color, tipografía, capas, máscaras, filtros, maquetación, y detección de caras de troqueles/dielines.
- **Idiomas (trío de modos persistentes)** —
  - 🌐 **Traductor en vivo**: *"convertite en traductor de español a inglés"* — JARVIS deja de conversar y se vuelve intérprete: vos hablás en un idioma y él dice SOLO la traducción en el otro, turno a turno. Cambiá el par (*"de francés a portugués"*), invertilo (*"al revés"*) o salí (*"pará el modo traductor"*). 12 idiomas.
  - 👨‍🏫 **Profesor de conversación por niveles**: *"practiquemos inglés, soy B1"* — conversa con vos EN ese idioma adaptado a tu nivel MCER (A1–C2): vocabulario, gramática y velocidad acordes, te corrige con tacto y siempre devuelve una pregunta para que sigas hablando. *"subí/bajá el nivel"*, cambiá de idioma o de tema cuando quieras.
  - 📝 **Examen de nivel**: *"evaluá mi nivel de alemán"* — te hace preguntas adaptativas (sube/baja la dificultad según respondés) y al final te da tu nivel MCER estimado con justificación y consejo.
- **Skills extensibles** — carpetas `skills/<nombre>/` con `SKILL.md` + `skill.py` (recargables sin reiniciar). Además de los modos de idioma: búsqueda web, git, saludo por hora. JARVIS puede **aprender skills nuevas** por voz (*"aprendete a..."*).
- **WhatsApp** — enviar/leer por el bridge local (whatsmeow), resolviendo el destinatario contra tu **agenda de Apple** ("mandá a Mamá"). Notificaciones proactivas ("te escribió X") y *"leelo"* para que te lea el mensaje. Vinculación con **QR en ventana** (no terminal) y chip de estado conectado/desconectado en la UI. Arranca solo con JARVIS.
- **Llamadas FaceTime** (Mac) — *"llamá a Mamá"* resuelve el contacto en tu agenda y abre la llamada (audio o video); confirmás con un click.
- **Bot de trading (paper)** — invierte con dinero FICTICIO sobre precios reales: DCA o estrategia *smart* (SMA+RSI) que vigila una **watchlist** de tickers, con **stop-loss automático**, reporte de rendimiento por período y panel gráfico. Opcionalmente conectable a un broker real (Alpaca). **No garantiza ganancias.**
- **Cámara con visión** — bajo demanda; opina y compara lo que le mostrás para ayudarte a decidir.
- **Servidores MCP** — memoria, GitHub, Telegram, WhatsApp, **Figma** (lee diseños/estilos y baja assets), **Vercel** (proyectos, deploys, logs, docs — MCP oficial con OAuth), **Chrome DevTools** (control profundo del navegador: clicks/formularios/consola/red, oficial de Google) y, en Windows, **Windows-MCP** (control avanzado element-aware vía UIAutomation). Los servers pueden atarse a un SO (`"platform"`) y se omiten solos donde no corresponde. Ver [MCP_SETUP.md](MCP_SETUP.md).
- **AppleScript a la carta** (Mac) — `mac_control` action=`run_script`: para cualquier cosa de macOS que las acciones estructuradas no cubran.
- **Control del entorno** — apps, volumen, ventanas, archivos, **recordatorios persistentes** (sobreviven reinicios, con fecha/hora real en tu zona horaria), scheduler, casa inteligente (Tuya/Hue), Spotify (con "qué suena" en vivo en el dashboard), Google (Calendar/Drive/Gmail), YouTube (reproduce directo el primer resultado), clima con pronóstico (Open-Meteo), rutas con distancia/tiempo hablados.
- **Notificaciones proactivas + No Molestar** — *"avisame si me escribe X"* / *"avisame de todos los WhatsApp"*; DND por fuente o global con whitelist (*"silenciá todo 1h pero avisame si dicen urgente"*).

---

## 🛠️ Requisitos

- **Python 3.11**
- **macOS** (para la integración Adobe vía `osascript`, permisos de Cámara/Micrófono/Accesibilidad)
- Una **API key de Gemini** (obligatoria — voz + cerebro por defecto). El resto de las keys son opcionales.

---

## 🚀 Instalación

**Camino rápido** (clonás y corrés — `dev.sh` arma venv, deps y modelo Vosk):

```bash
git clone <tu-repo> JARVIS-IA && cd JARVIS-IA
./dev.sh
```

**Manual**, si preferís controlar cada paso:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_vosk.py            # modelo Vosk (modo suspensión) → config/vosk_model/
playwright install chromium        # (opcional) navegador para automatización web
```

---

## ⚙️ Configuración

Hay **dos lugares** de configuración, y se complementan:

### 1. Secretos / API keys → `.env`
Copiá la plantilla y completá solo lo que vayas a usar:

```bash
cp .env.example .env
```

`GEMINI_API_KEY` es lo único **obligatorio**. Lo demás (OpenAI, Anthropic, MiniMax,
TMDB, Figma, Spotify, Tuya, GitHub, Telegram, Brave, Notion, Composio, **Alpaca** para
el bot de trading real) es opcional y habilita su integración. El `.env` tiene prioridad
sobre el JSON y **nunca se sube a git**.

### Configurar TODO desde la app (recomendado)

No hace falta tocar archivos: la **ventana de configuración** carga cualquier clave y la
guarda en el `.env` automáticamente (los JSON de config nunca almacenan secretos).

**Cómo abrirla** (3 formas): se abre sola al arrancar si falta Gemini · botón ⚙️ de la
cabecera · por voz: *"abrí la configuración de API keys"*.

**Campos por categoría y dónde sacar cada clave:**

| Categoría | Campos | Dónde sacarla |
|---|---|---|
| Cerebros de IA | Gemini (obligatoria), OpenAI, Anthropic, OpenRouter, MiniMax | [aistudio.google.com](https://aistudio.google.com/apikey) · [platform.openai.com](https://platform.openai.com/api-keys) · [console.anthropic.com](https://console.anthropic.com) · openrouter.ai · platform.minimax.io |
| Trading (broker real) | Alpaca Key + Secret | [alpaca.markets](https://alpaca.markets) → API Keys (empezá con las *Paper*) |
| Diseño | Figma token personal | figma.com → Settings → Personal access tokens |
| Spotify | Client ID + Secret + Redirect | [developer.spotify.com](https://developer.spotify.com/dashboard) → app nueva; después usá el botón **Enlazar cuenta** de la misma ventana |
| Casa (Tuya) | Access ID + Secret + región | [iot.tuya.com](https://iot.tuya.com) → Cloud Project |
| Integraciones MCP | GitHub token · Telegram bot · Brave · Notion · Composio | github.com/settings/tokens · @BotFather · brave.com/search/api · notion.so/my-integrations · app.composio.dev (detalle en [TOKENS.md](TOKENS.md)) |
| Contenido | TMDB | themoviedb.org → Settings → API |

**Secciones extra de la misma ventana:**
- **Google (Calendar/Gmail/Drive)** — botón *"Elegir google_credentials.json…"*: descargás el
  JSON del cliente OAuth (Desktop) desde Google Cloud Console → APIs → Credentials, lo elegís
  y listo (semáforo 🔴/🟡/🟢 indica el estado; la autorización del navegador salta al primer uso).
- **Zona horaria** — select con 23 zonas (afecta saludo, recordatorios y scheduler).
- **Audio** — elegir micrófono y altavoz.
- **Prioridad para programar** — qué cerebro usa JARVIS para codear (o "preguntarme siempre").
- **Enlazar Spotify** — OAuth con un click una vez cargados ID/Secret.

**Integraciones sin clave** (se configuran solas o con un gesto):
- **WhatsApp** — decí *"conectá WhatsApp"*: escaneás un QR **en ventana** una sola vez.
- **Vercel** — al primer uso se abre el navegador para el login OAuth y queda.
- **Claude Code / Antigravity CLI** — basta tenerlos logueados en una terminal (`claude` / `agy`).

### 2. Ajustes de la app → `config/api_keys.json`
Tema, modelo de voz, cerebro de pensamiento, prioridades, zona horaria (`timezone`),
dispositivos de audio, etc. (no secretos). La app lo gestiona sola; rara vez hay que tocarlo a mano.

### 3. Servidores MCP → `config/mcp_servers.json`
Qué servers MCP levantar y con qué tokens. Partí de la plantilla:

```bash
cp config/mcp_servers.example.json config/mcp_servers.json
```

Detalles en [MCP_SETUP.md](MCP_SETUP.md) y [TOKENS.md](TOKENS.md).

### Qué necesita cada integración

| Integración | Requisito | SO |
|---|---|---|
| Voz + cerebro default | `GEMINI_API_KEY` (la única obligatoria) | Todos |
| Cerebros extra (GPT/Claude/MiniMax) | Su API key, opcional | Todos |
| Claude Code CLI / Antigravity CLI | CLI instalado y logueado (sin API key) | Todos |
| WhatsApp | Escanear QR **una vez** (ventana en la UI); el bridge arranca solo. Necesita `go` y `uv` (`brew install go uv`) | Todos |
| FaceTime / iMessage / Notas / agenda | Nada (apps nativas) + permisos de macOS | Solo Mac |
| Adobe (Illustrator/InDesign/Photoshop) | Apps instaladas + permiso de Automatización | Mac (osascript) / Win (COM) |
| Figma (MCP lectura + REST) | `FIGMA_TOKEN` (token personal gratis de figma.com) | Todos |
| Figma Dev Mode MCP (oficial) | App Figma Desktop + toggle *Enable Dev Mode MCP Server* (asiento Dev/Full pago) | Todos |
| Vercel (MCP oficial) | Login OAuth la 1ª vez (se abre el navegador; token queda en `~/.mcp-auth`) | Todos |
| Windows-MCP (control avanzado) | Python 3.13+ y `uv` en la máquina Windows | Solo Windows |
| Trading real (Alpaca) | `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` (cuenta gratis; paper primero) | Todos |
| Spotify | Client ID/Secret + enlazar desde la ventana de keys | Todos |
| Casa inteligente (Tuya) / Telegram / GitHub / Notion | Su token (ver [TOKENS.md](TOKENS.md)) | Todos |
| Clima, rutas, YouTube, búsqueda web, traductor/profesor de idiomas, recordatorios, bot de trading paper | **Nada** — funcionan de fábrica | Todos |

### Permisos de macOS
La primera vez, otorgá en **Ajustes → Privacidad y seguridad**:
- **Micrófono** (voz) y **Cámara** (visión, solo si la usás)
- **Accesibilidad** (control de apps/ventanas)
- **Automatización** → Illustrator/InDesign/Photoshop (si usás Adobe)

---

## ▶️ Ejecutar (desarrollo)

```bash
./dev.sh
```

`dev.sh` crea el venv si falta, instala dependencias, baja el modelo Vosk la primera
vez y arranca `main.py` (es idempotente). Equivale a:

```bash
source .venv/bin/activate && python main.py
```

Arranca la ventana con el orbe y conecta la voz. JARVIS corre **en segundo plano**:
cerrar la ventana con la X lo manda a la bandeja (tray), no lo apaga. Decile
**"reiniciate"** para reiniciarlo (aplica cambios) o **"apagá JARVIS"** para cerrarlo de verdad.

---

## 📦 Compilar (instaladores)

```bash
./build.sh
```

Congela JARVIS con PyInstaller y arma el instalador **del sistema operativo donde lo corras**:

| SO | Salida |
|----|--------|
| macOS | `release/JARVIS.dmg` |
| Linux | `release/JARVIS-linux.tar.gz` |
| Windows | `pyinstaller build.spec` → `dist\JARVIS\JARVIS.exe` |

> PyInstaller **no cross-compila**: cada instalador se arma en su propio SO. Para obtener
> los **3 a la vez** sin tener las 3 máquinas, está el CI `.github/workflows/build.yml`
> (compila en macOS + Windows + Linux y sube los artefactos). Disparalo desde la pestaña
> *Actions* o pusheando un tag `v*`.
>
> Empaquetar PyQt6 + QtWebEngine + Vosk es delicado: la receta (`build.spec`) es un punto
> de partida sólido pero puede necesitar un ajuste en la primera corrida.

---

## 🧩 Arquitectura (dónde vive todo)

| Ruta | Qué es |
|------|--------|
| `main.py` | Orquestador. La voz usa Gemini Live; `STANDARD_TOOL_HANDLERS` registra los handlers y rutea las tool calls. |
| `actions/` | Una tool por archivo. El **schema vive junto al handler** vía el decorador `@tool`. |
| `core/registry.py` | `@tool` (declaración autodescriptiva) + `ToolRegistry` + auto-descubrimiento de tools. |
| `core/tool_declarations.py` | Solo las tools "especiales" UI-coupled (shutdown/restart/save_memory…). El resto migró a `@tool`. |
| `core/runtime/` | Motores desacoplados: `audio.py`, `voice.py`, `prompt.py`, `dispatcher.py` (ejecución de tools, testeado), `context.py` (`ToolContext`), `tool_imports.py`. |
| `core/theme.py` | Motor de tema (paletas + tokens de color). Referenciar por atributo: `theme.C_PRI`. |
| `core/llm_router.py` + `core/code_brain.py` | Cerebro de pensamiento multi-proveedor + selector de prioridad para programar. |
| `core/adobe/` (illustrator/photoshop/indesign/common) | Operaciones ExtendScript por app. `core/adobe_ops.py` es la fachada que reexporta. |
| `core/credentials.py` | Ventana de API keys (keys + zona horaria + audio + prioridad + Spotify). |
| `core/mcp_client.py` · `core/platform_utils.py` | Cliente MCP · utilidades cross-OS. |
| `ui.py` + `ui_widgets.py` + `ui_helpers.py` + `assets/sphere.html` | Shell (`MainWindow`/`JarvisUI`) + widgets del dashboard + helpers + el orbe. |
| `memory/SOUL.md` · `memory/config_manager.py` | Personalidad/reglas (al system prompt) · config (`.env` + `api_keys.json`). |
| `skills/<nombre>/` | Skills dinámicas (`SKILL.md` + `skill.py`). |

---

## 🧱 Agregar una tool nueva

1. Creá `actions/<nombre>.py` con el handler **decorado** (schema co-locado):
   ```python
   from core.registry import tool
   @tool(name="<nombre>", description="…", parameters={"type": "OBJECT", "properties": {…}, "required": […]})
   def <nombre>(parameters, player=None) -> str:   # devolvé un string para la voz
       ...
   ```
2. Importala y registrala en `STANDARD_TOOL_HANDLERS` en `main.py` (para el dispatch).
3. **No** toques `core/tool_declarations.py` — el schema ya está en el `@tool`.
4. Si cambia el comportamiento del asistente, sumá una regla en `memory/SOUL.md`.
5. Secretos → `.env`. Cross-platform → `core/platform_utils.py`.

Para una **skill** (auto-contenida, recargable): creá `skills/<nombre>/SKILL.md` (frontmatter
con `name`/`description`/`parameters`) + `skill.py` con `def run(parameters, player=None, speak=None) -> str`.

Convenciones completas para el agente de código en [CLAUDE.md](CLAUDE.md).

---

## ✅ Pruebas

```bash
pip install -r requirements-dev.txt   # una vez (pytest)
pytest                                # suite de regresión (~1s, unit + contrato + golden)
python smoke_test.py                  # chequeo rápido del sistema (14/14)
```

La suite (`tests/`) fija `JARVIS_SKIP_MCP=1` y no arranca los servers MCP. Corré ambos
**antes y después** de cada cambio. CI en `.github/workflows/tests.yml`. Plan completo en [TESTING.md](TESTING.md).

---

## 📚 Documentación adicional

- [MCP_SETUP.md](MCP_SETUP.md) — conectar servidores MCP
- [TOKENS.md](TOKENS.md) — guía de tokens/credenciales
- [TESTING.md](TESTING.md) — plan de pruebas
- [CLAUDE.md](CLAUDE.md) — guía para trabajar el código del repo

---

## 🛡️ Seguridad

Secretos en `.env` y `config/api_keys.json` / `config/mcp_servers.json` están en `.gitignore`
y **no se suben**. Si exponés una key por error, revocala y generá una nueva.
