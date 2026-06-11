"""
visual_click.py — Localiza un elemento en la pantalla usando Gemini Vision y hace clic.

Antes usaba OpenRouter (pago). Migrado a Gemini directo (tier gratis).
"""
import json
import io
import re
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
    name='visual_click',
    description='Clic físico en un elemento ubicado por visión (descripción natural).',
    parameters={'type': 'OBJECT',
     'properties': {'element_description': {'type': 'STRING',
                                            'description': 'Descripción clara de lo que quieres '
                                                           "cliquear (ej: 'botón de enviar', 'ícono de "
                                                           "la papelera')."}},
     'required': ['element_description']},
)
def visual_click(parameters: dict, player=None) -> str:
    """
    Captura la pantalla, le pide a Gemini las coordenadas del elemento descrito,
    y usa pyautogui para hacer clic.
    """
    element_desc = parameters.get("element_description", "")
    if not element_desc:
        return "Error: No se especificó el elemento a cliquear."

    api_key = _get_api_key()
    if not api_key:
        return "Error: No se encontró gemini_api_key en config/api_keys.json."

    try:
        import mss
        import pyautogui
        from PIL import Image
    except ImportError:
        return "Error: Faltan dependencias (mss, pyautogui, Pillow)."

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return "Error: el paquete 'google-genai' no está instalado."

    if player:
        player.write_log(f"👁 Buscando coordenadas para: '{element_desc}'...")

    try:
        with mss.mss() as sct:
            mon = sct.monitors[1]
            sct_img = sct.grab(mon)
            orig_w, orig_h = sct_img.size
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            img.thumbnail((1280, 720), Image.Resampling.BILINEAR)
            new_w, new_h = img.size
            scale_x = orig_w / new_w
            scale_y = orig_h / new_h

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=75)
            img_bytes = buffer.getvalue()

        prompt = (
            f"Localiza exactamente el centro visual del elemento descrito como '{element_desc}'. "
            f"La imagen tiene un tamaño de {new_w}x{new_h} píxeles. "
            "DEBES devolver ÚNICA Y EXCLUSIVAMENTE un array JSON con las coordenadas [X, Y], "
            "sin texto adicional ni bloques markdown. "
            "Si el elemento no existe, devolvé un array vacío []. Ejemplo de salida: [450, 312]"
        )

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(parts=[
                    types.Part(text=prompt),
                    types.Part(inline_data=types.Blob(data=img_bytes, mime_type="image/jpeg")),
                ])
            ],
            config=types.GenerateContentConfig(max_output_tokens=50),
        )

        raw_text = (resp.text or "").strip()

        match = re.search(r"\[\s*\d+\s*,\s*\d+\s*\]", raw_text)
        if not match:
            if "[]" in raw_text:
                return f"No se encontró el elemento '{element_desc}' en la pantalla."
            return f"Error al parsear coordenadas de Gemini. Respuesta cruda: {raw_text}"

        coords = json.loads(match.group(0))
        ai_x, ai_y = coords[0], coords[1]
        real_x = int(ai_x * scale_x)
        real_y = int(ai_y * scale_y)

        pyautogui.moveTo(real_x, real_y, duration=0.4, tween=pyautogui.easeInOutQuad)
        pyautogui.click()

        return f"Clic visual ejecutado en '{element_desc}' (coordenadas reales: X={real_x}, Y={real_y})."

    except Exception as e:
        return f"Error en visual_click: {str(e)}"
