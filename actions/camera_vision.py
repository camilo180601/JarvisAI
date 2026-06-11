"""
camera_vision.py — JARVIS mira por la webcam, BAJO DEMANDA, y describe lo que ve.

La cámara se abre solo al pedirlo y aparece un preview en la interfaz (señal de que
está mirando). Acciones:
  on / look   abre la cámara y muestra el preview (opcional: query para analizar ya)
  analyze     captura un frame y lo describe con Gemini (default)
  photo       guarda una foto en ~/Pictures/JARVIS
  off         apaga la cámara y oculta el preview
"""
from __future__ import annotations
import time
from pathlib import Path
from datetime import datetime
from core.registry import tool


def _cfg(key, default=""):
    try:
        from memory.config_manager import cfg
        return cfg(key, default)
    except Exception:
        return default


# Memoria corta del "hilo visual" (en RAM): lo que JARVIS fue viendo en esta charla,
# para poder comparar opciones ("antes me mostraste X, ahora Y → te conviene...").
_VISUAL_THREAD: list[str] = []
_THREAD_MAX = 6


def _thread_context() -> str:
    if not _VISUAL_THREAD:
        return ""
    items = "\n".join(f"- {t}" for t in _VISUAL_THREAD[-_THREAD_MAX:])
    return ("\n\nContexto: esto es lo que ya viste antes en esta misma conversación "
            f"(de lo más viejo a lo más nuevo), úsalo para COMPARAR y dar una recomendación:\n{items}")


def reset_visual_thread() -> None:
    _VISUAL_THREAD.clear()


def _analyze(query: str) -> str:
    from core.camera import CAMERA
    # El sensor (auto-exposición) tarda 2-3s en ajustar: los primeros cuadros salen
    # NEGROS aunque sean válidos. Esperamos un cuadro CON LUZ, no solo uno no-nulo.
    best, best_bright, waited = None, -1.0, 0.0
    while waited < 4.0 and CAMERA.is_on():
        fr = CAMERA.get_frame()
        if fr is not None:
            try:
                bright = float(fr.mean())
            except Exception:
                bright = 0.0
            if bright > best_bright:
                best_bright, best = bright, fr
            if bright >= 18:   # cuadro con luz suficiente → listo
                break
        time.sleep(0.2)
        waited += 0.2
    fr = best
    if fr is None:
        return "La cámara todavía no tiene imagen — esperá un segundo y reintento."
    if best_bright < 8:
        return ("La cámara está entregando imagen totalmente negra. Suele ser una de tres: "
                "el lente está tapado, otra app la está usando (cerrá Zoom/Meet/FaceTime/Cámara de Continuidad), "
                "o es la cámara equivocada. Si tenés varias, cambiá 'camera_index' (0, 1 o 2) en la config. "
                "Destapá/liberá la cámara y volvé a decirme 'qué ves'.")
    try:
        import cv2
        ok, buf = cv2.imencode(".jpg", fr)
        if not ok:
            return "No pude capturar el cuadro de la cámara."
        img_bytes = buf.tobytes()
    except Exception as e:
        return f"Error capturando: {e}"
    api_key = _cfg("gemini_api_key")
    if not api_key:
        return "Falta gemini_api_key para analizar la imagen."
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        prompt = (f"Esto es lo que veo en vivo por mi cámara. {query}{_thread_context()}\n\n"
                  "Respondé en español, breve y al grano, como si estuvieras mirando junto al usuario. "
                  "Si te pide opinión o elegir entre opciones, DECIDÍ y justificá en una frase.")
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(parts=[
                types.Part(text=prompt),
                types.Part(inline_data=types.Blob(data=img_bytes, mime_type="image/jpeg")),
            ])],
        )
        out = (resp.text or "").strip() or "No pude analizar la imagen."
        # guardar en el hilo visual para comparar más adelante
        _VISUAL_THREAD.append(f"[{query[:60]}] {out[:160]}")
        return out
    except Exception as e:
        return f"Error analizando con Gemini: {str(e)[:140]}"


@tool(
    name='camera_vision',
    description="Mira por la cámara web SOLO cuando el usuario lo pide (privacidad) y muestra un preview en la interfaz. USAR cuando diga: 'mirá por la cámara', 'qué ves', 'activá la cámara', 'sacá una foto', 'apagá la cámara'. Acciones: on (abre la cámara + preview), analyze (describe lo que ve con Gemini, default), photo (guarda una foto), off (apaga y oculta). La cámara queda encendida (y el preview visible) hasta que se diga 'off'.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'on | analyze | photo | off'},
                    'query': {'type': 'STRING',
                              'description': "Qué querés saber de lo que ve (ej '¿qué objeto tengo en "
                                             "la mano?', '¿cuántas personas hay?')"}},
     'required': []},
)
def camera_vision(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "analyze").lower().strip()
    from core.camera import CAMERA, request_show, request_hide
    idx = int(_cfg("camera_index", 0) or 0)

    if action in ("off", "close", "apagar", "stop", "cerrar"):
        CAMERA.stop()
        request_hide()
        reset_visual_thread()
        return "📷 Cámara apagada."

    def _ensure_on() -> str | None:
        if not CAMERA.is_on():
            if not CAMERA.start(idx):
                return ("No pude abrir la cámara. Verificá el permiso de Cámara "
                        "(Ajustes → Privacidad → Cámara) y que el índice sea correcto.")
            request_show()
            time.sleep(0.7)  # warm-up del sensor
        else:
            request_show()
        return None

    if action in ("on", "ver", "mirar", "look", "abrir", "show", "activar"):
        err = _ensure_on()
        if err:
            return err
        q = (parameters.get("query") or "").strip()
        if q:
            return _analyze(q)
        return ("📷 Cámara activada — la ves en la interfaz. Decime 'qué ves' para que "
                "lo analice, o 'apagá la cámara' cuando quieras.")

    if action in ("photo", "foto", "snapshot", "capture", "capturar"):
        err = _ensure_on()
        if err:
            return err
        fr = CAMERA.get_frame()
        if fr is None:
            return "No hay imagen aún, reintentá."
        try:
            import cv2
            out = Path.home() / "Pictures" / "JARVIS" / f"cam_{datetime.now():%Y%m%d_%H%M%S}.jpg"
            out.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out), fr)
            return f"📸 Foto guardada en {out}"
        except Exception as e:
            return f"Error guardando la foto: {e}"

    # default: analyze
    err = _ensure_on()
    if err:
        return err
    return _analyze(parameters.get("query") or "¿Qué ves? Describilo en español, breve.")
