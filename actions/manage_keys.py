"""
manage_keys.py — Abrir la ventana de API keys y consultar estado de integraciones.

open   : abre el diálogo (opcionalmente resaltando la integración que falta).
status : muestra qué integraciones tienen su clave cargada.
"""
from __future__ import annotations
from core.registry import tool


@tool(
    name='manage_keys',
    description="Abre la ventana de configuración de API keys o muestra el estado de las integraciones. USAR cuando: una integración falla por falta de API key (abrila para que el usuario la cargue), el usuario dice 'configurá las keys', 'poné mi api key de X', 'cambiá la clave de Y', o pregunta 'qué tengo configurado'. action=open abre la ventana (integration resalta lo que falta); status lista qué integraciones tienen clave.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'open (abre la ventana) | status'},
                    'integration': {'type': 'STRING',
                                    'description': 'Integración a resaltar: gemini, openai, claude, '
                                                   'spotify, tuya, github, telegram, brave, notion, '
                                                   'composio, tmdb, openrouter'}},
     'required': []},
)
def manage_keys(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "open").lower().strip()
    from core.credentials import request_dialog, integration_status, missing_keys, _LABELS

    if action in ("status", "check", "list"):
        return integration_status()

    if action in ("open", "config", "configure", "set"):
        target = (parameters.get("integration") or parameters.get("provider") or "").lower().strip()
        opened = request_dialog(target)
        if not opened:
            return ("No pude abrir la ventana (¿estás en modo sin interfaz?). "
                    "Cargá las claves directamente en el archivo .env.")
        if target:
            miss = missing_keys(target)
            if miss:
                labels = ", ".join(_LABELS.get(k, k) for k in miss)
                return f"Abrí la ventana de API keys, resaltando lo que falta para {target} ({labels}). Guardá y reintento."
        return "Abrí la ventana de API keys. Completá lo que necesites y guardá."

    return "Acciones: open (abre la ventana) | status (qué integraciones están configuradas)."
