# JARVIS — Guía de Tokens / Credenciales

Todos los tokens van en **`config/mcp_servers.json`** (gitignored, no se sube nunca).

## Cómo se edita

Cada server tiene un bloque así. Reemplazás `PEGAR_..._AQUI` por tu token real
y cambiás `"disabled": true` → `false`:

```json
"github": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_tuTokenReal..." },
    "disabled": false
}
```

Después **reiniciás JARVIS**. En consola deberías ver `[MCP/github] ✓ N tools cargadas`.

---

## Dónde sacar cada token

### 🐙 GitHub
**Campo**: `GITHUB_PERSONAL_ACCESS_TOKEN`
1. https://github.com/settings/tokens
2. **Generate new token** → **classic**
3. Nota: "JARVIS", Expiration: 90 días (o sin vencimiento)
4. Scopes: marcá **`repo`** (y `read:org` si querés ver orgs)
5. **Generate token** → copiá el `ghp_...` (solo se ve una vez)

### 🔍 Brave Search
**Campo**: `BRAVE_API_KEY`
1. https://brave.com/search/api/
2. **Get started** → registrate
3. Elegí el plan **Free** (2.000 queries/mes, sin tarjeta)
4. Dashboard → **API Keys** → copiá la key

### 🎵 Spotify
**Campos**: `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`
1. https://developer.spotify.com/dashboard
2. Login con tu cuenta Spotify → **Create app**
3. Nombre: "JARVIS", Redirect URI: `http://127.0.0.1:8888/callback`
4. Marcá "Web API" → **Save**
5. En la app → **Settings** → copiá **Client ID** y **Client Secret**
   (ya tenés estos campos en `config/api_keys.json` también)

### 📱 Telegram
**Campo**: `TELEGRAM_BOT_TOKEN`
1. Abrí Telegram, buscá **@BotFather**
2. Mandale `/newbot`
3. Elegí nombre y username (debe terminar en `bot`)
4. Te devuelve un token tipo `123456:ABC-DEF...` → copialo
> Nota: esto crea un BOT, no tu cuenta personal. Para tu cuenta personal usá el MCP de WhatsApp.

### 📝 Notion
**Campo**: `NOTION_TOKEN`
1. https://www.notion.so/my-integrations
2. **New integration** → nombre "JARVIS" → asociala a tu workspace
3. Copiá el **Internal Integration Secret** (`secret_...` o `ntn_...`)
4. **IMPORTANTE**: en cada página/DB que quieras que JARVIS vea →
   menú `...` → **Connections** → agregá "JARVIS". Si no, no ve nada.

### 🌐 Composio (mega — 250+ apps)
**Campo**: `COMPOSIO_API_KEY`
1. https://app.composio.dev
2. Registrate → **Settings** → **API Keys** → copiá
3. Dentro de Composio conectás las apps que quieras (Gmail, Slack, Linear...)
   con sus propios OAuth — Composio maneja eso, JARVIS solo usa la API key.

### 📈 Alpaca (bot de trading — solo para dinero real)
**Campos**: `ALPACA_API_KEY` + `ALPACA_SECRET_KEY`. **No** es un server MCP; es una API
directa para el `trading_bot`. El bot arranca en simulación local (no necesita nada). Solo
si querés conectarlo a un broker real:
1. Cuenta gratis en https://alpaca.markets → sección **API Keys**.
2. Generá un par. Empezá con las de **Paper** (broker real, plata ficticia) para validar;
   las de **Live** mueven dinero REAL (requieren completar el alta/KYC).
3. Cargalas en la ventana de API keys (categoría **Trading**) o en el `.env`.

---

## Sin token (no van en este archivo)

### 📲 WhatsApp — NO usa token, usa QR
No tiene `env`. El setup es aparte (ver **MCP_SETUP.md**):
1. `brew install go uv`
2. clonar `lharries/whatsapp-mcp`
3. correr el bridge → escanear QR con el celular
4. flip `disabled:false`

### 💬 iMessage — NO usa MCP, lee chat.db directo
Ya configurado vía Full Disk Access. No toca este archivo.

### 📧 Gmail / Google — usa OAuth, no token plano
Ya configurado en `config/google_credentials.json` + `google_token.json`.
El MCP `google-workspace` (si lo querés) reusaría ese OAuth.

---

## Cero credenciales (activar ya)

Estos solo necesitan flip `disabled:false`, sin tokens:
- **playwright** — browser automation
- **filesystem** — file ops

---

## Resumen rápido

| Server | Token de dónde | Campo |
|---|---|---|
| github | github.com/settings/tokens | GITHUB_PERSONAL_ACCESS_TOKEN |
| brave-search | brave.com/search/api | BRAVE_API_KEY |
| spotify | developer.spotify.com/dashboard | SPOTIFY_CLIENT_ID + SECRET |
| telegram | @BotFather en Telegram | TELEGRAM_BOT_TOKEN |
| notion | notion.so/my-integrations | NOTION_TOKEN |
| composio | app.composio.dev | COMPOSIO_API_KEY |
| whatsapp | QR (sin token) | — |
| playwright/filesystem | nada | — |

Después de editar cualquiera: **reiniciar JARVIS** y verificar en consola.
