"""
screen_vision.py — Captura la pantalla y la analiza con Gemini 2.5 Flash (multimodal).

Antes usaba OpenRouter (pago). Migrado a Gemini directo (tier gratis).
"""
import json
import io
from pathlib import Path
from mss import mss
from PIL import Image
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("gemini_api_key", "")
    except Exception:
        return ""

def _capture_screen_jpeg_bytes() -> bytes:
    """Captura la pantalla principal, la redimensiona y la devuelve como JPEG en bytes."""
    with mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        img.thumbnail((1280, 720), Image.Resampling.BILINEAR)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=65)
        return buffer.getvalue()


@tool(
    name='screen_process',
    description='Captura y analiza pantalla o webcam. Sin esto no podés ver. Tras llamarlo, callate — el módulo habla solo.',
    parameters={'type': 'OBJECT',
     'properties': {'angle': {'type': 'STRING',
                              'description': "'screen' to capture display, 'camera' for webcam. "
                                             "Default: 'screen'"},
                    'text': {'type': 'STRING',
                             'description': 'The question or instruction about the captured image'}},
     'required': ['text']},
)
@tool(
    name='screen_vision',
    description='VER la pantalla con IA: describe, question (con question), help, read (texto visible).',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'describe=describir qué hay en pantalla | '
                                              'question=responder pregunta sobre la pantalla | '
                                              'help=dar ayuda contextual | read=leer todo el texto '
                                              'visible'},
                    'question': {'type': 'STRING',
                                 'description': 'Pregunta o tarea específica sobre lo que se ve en '
                                                'pantalla (para action=question/help)'},
                    'monitor': {'type': 'INTEGER',
                                'description': '0=toda la pantalla (default), 1=monitor principal, '
                                               '2=segundo monitor'}},
     'required': ['action']},
)
def screen_vision(parameters: dict, player=None) -> str:
    """
    Toma una captura de pantalla y la analiza usando Gemini 2.5 Flash.
    """
    api_key = _get_api_key()
    if not api_key:
        return (
            "Error: No se encontró gemini_api_key en config/api_keys.json. "
            "Conseguila gratis en https://aistudio.google.com/apikey."
        )

    query = (
        parameters.get("query")
        or parameters.get("text")
        or parameters.get("question")
        or "¿Qué ves en mi pantalla?"
    )

    if player:
        player.write_log("👁️ Capturando pantalla para Gemini Vision...")

    try:
        img_bytes = _capture_screen_jpeg_bytes()
    except Exception as e:
        return f"Error al capturar la pantalla: {e}"

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "Error: el paquete 'google-genai' no está instalado."

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(parts=[
                    types.Part(text=f"Esta es una captura de mi pantalla. {query}"),
                    types.Part(inline_data=types.Blob(data=img_bytes, mime_type="image/jpeg")),
                ])
            ],
            config=types.GenerateContentConfig(max_output_tokens=1500),
        )
        text = (resp.text or "").strip()
        return text or "Gemini no devolvió análisis de la imagen."
    except Exception as e:
        return f"Error al analizar la pantalla con Gemini: {str(e)}"
