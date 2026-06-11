"""open_app.py — Lanzador de aplicaciones cross-platform."""
from core.platform_utils import open_application
from core.registry import tool


@tool(
    name='open_app',
    description='Abre cualquier app del SO. Llamar siempre — no decir que abriste sin invocarlo.',
    parameters={'type': 'OBJECT',
     'properties': {'app_name': {'type': 'STRING',
                                 'description': "Exact name of the application (e.g. 'WhatsApp', "
                                                "'Chrome', 'Spotify')"}},
     'required': ['app_name']},
)
def open_app(parameters: dict, response=None, player=None) -> str:
    """Abre una app por nombre. Funciona en Windows, Mac y Linux."""
    app_name = parameters.get("app_name", "").strip()
    if not app_name:
        return "App name is required, sir."

    ok, msg = open_application(app_name)
    if player:
        prefix = "🚀" if ok else "⚠️"
        player.write_log(f"{prefix} {msg}")
    return msg
