"""
google_auth.py — Helper compartido de OAuth 2.0 para Calendar/Gmail/Drive.

Setup (una vez):
1. Ir a https://console.cloud.google.com/
2. Crear un proyecto (o usar uno existente)
3. APIs & Services → Habilitar: Google Calendar API, Gmail API, Google Drive API
4. APIs & Services → Credentials → Create Credentials → OAuth client ID
   Application type: Desktop app → Create
5. Descargar el JSON y guardarlo como: config/google_credentials.json

La primera llamada abre el navegador para autorizar. El token queda en
config/google_token.json y se refresca automáticamente.
"""
from __future__ import annotations
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = BASE_DIR / "config" / "google_credentials.json"
TOKEN_PATH = BASE_DIR / "config" / "google_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
]

_setup_instructions = (
    "Necesito credenciales de Google. Setup (una sola vez):\n"
    "1. Ir a https://console.cloud.google.com/\n"
    "2. Crear/seleccionar un proyecto\n"
    "3. APIs & Services → habilitar: Google Calendar API, Gmail API, Google Drive API\n"
    "4. APIs & Services → Credentials → Create Credentials → OAuth client ID\n"
    "   Application type: Desktop app → Create\n"
    "5. Descargar el JSON y guardarlo como: config/google_credentials.json\n"
    "Después de eso, llamame de nuevo y se abrirá el navegador para autorizar."
)


def _load_creds():
    """Carga credenciales OAuth, refresca si están expiradas, abre flujo si no hay token."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError as e:
        raise RuntimeError(
            f"Falta paquete: {e}. Ejecuta: pip install google-auth google-auth-oauthlib google-api-python-client"
        )

    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(_setup_instructions)

    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            pass  # Cae al flujo interactivo

    # Flujo interactivo (abre browser)
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_service(api_name: str, version: str):
    """Devuelve un cliente autenticado para la API solicitada.

    Ejemplos:
        get_service('calendar', 'v3')
        get_service('gmail', 'v1')
        get_service('drive', 'v3')
    """
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(_setup_instructions)
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Falta el paquete 'google-api-python-client'. "
            "Ejecuta: pip install google-auth google-auth-oauthlib google-api-python-client"
        )
    creds = _load_creds()
    return build(api_name, version, credentials=creds, cache_discovery=False)


def is_configured() -> bool:
    """¿Hay credenciales y token listos para usar?"""
    return CREDENTIALS_PATH.exists()


def setup_message() -> str:
    """Mensaje legible con las instrucciones de setup."""
    return _setup_instructions
