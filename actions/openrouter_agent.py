"""
openrouter_agent.py — Agente delegado para razonamiento pesado.

Nombre histórico: se llamaba "openrouter_agent" cuando usaba OpenRouter.
Ahora usa Gemini 2.5 Flash directamente (tier gratis de Google AI Studio).
La función mantiene el mismo nombre y firma para no romper main.py.
"""
import json
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("gemini_api_key", "")
    except Exception:
        return ""

@tool(
    name='openrouter_agent',
    description='Delega tareas de pensamiento pesado (código largo, ensayos, razonamiento profundo) a un Gemini de texto.',
    parameters={'type': 'OBJECT',
     'properties': {'query': {'type': 'STRING',
                              'description': 'El prompt o instrucción completa para el agente '
                                             'especialista'},
                    'model': {'type': 'STRING',
                              'description': 'Opcional. Modelo Gemini a usar, por defecto '
                                             'gemini-2.5-flash'}},
     'required': ['query']},
)
def openrouter_agent(query: str, model: str = "gemini-2.5-flash") -> str:
    """
    Delega una tarea de texto compleja a Gemini 2.5 Flash.
    Mantiene el nombre 'openrouter_agent' por compatibilidad con main.py.
    """
    api_key = _get_api_key()
    if not api_key:
        return (
            "No se encontró una clave de Gemini en la configuración. "
            "Por favor, añade 'gemini_api_key' en config/api_keys.json."
        )

    # Normalizar nombre de modelo: aceptar variantes "google/..." por compatibilidad
    if model.startswith("google/"):
        model = model.replace("google/", "", 1)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "Error: el paquete 'google-genai' no está instalado. Ejecuta: pip install google-genai"

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=[
                types.Content(parts=[
                    types.Part(text=(
                        "Eres un Agente Especialista delegado por JARVIS. "
                        "Responde de forma clara, directa y en español.\n\n"
                        f"Tarea del usuario:\n{query}"
                    ))
                ])
            ],
            config=types.GenerateContentConfig(
                max_output_tokens=1500,
            ),
        )
        text = (resp.text or "").strip()
        return text or "El agente especialista no devolvió texto."
    except Exception as e:
        return f"Error al consultar a Gemini: {str(e)}"
