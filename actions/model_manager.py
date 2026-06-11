"""
model_manager.py — Pensar/consultar con el cerebro configurable + gestionarlo.

consult_model : delega razonamiento pesado al modelo configurado (o a un override).
model_config  : elegir proveedor/modelo, listar disponibles, ver estado.

La VOZ sigue siendo Gemini 2.5 Flash; esto solo cambia QUIÉN piensa.
"""
from __future__ import annotations

from core.llm_router import consult, list_models_human, get_reasoning_config, MODELS
from core.registry import tool


@tool(
    name='consult_model',
    description="Delega razonamiento pesado a un modelo de texto (el 'cerebro' configurado: Gemini por default, o GPT/Claude). USAR cuando el usuario pide pensar a fondo, analizar, escribir código/ensayos largos, o dice 'consultale a GPT/Claude', 'pensá con X'. JARVIS sigue HABLANDO con su voz (Gemini 2.5 Flash); esto solo trae el contenido pensado. Acepta override de provider/model por llamada.",
    parameters={'type': 'OBJECT',
     'properties': {'prompt': {'type': 'STRING',
                               'description': 'La consulta / lo que hay que pensar o resolver'},
                    'system': {'type': 'STRING',
                               'description': 'Instrucción de sistema opcional (rol/estilo)'},
                    'provider': {'type': 'STRING',
                                 'description': 'Override opcional: gemini | openai | claude'},
                    'model': {'type': 'STRING',
                              'description': 'Override opcional: id de modelo (ej gpt-5.5, '
                                             'claude-opus-4-8, gemini-2.5-pro)'},
                    'max_tokens': {'type': 'INTEGER',
                                   'description': 'Máximo de tokens de salida (default 2000)'}},
     'required': ['prompt']},
)
def consult_model(parameters: dict, player=None) -> str:
    prompt = (parameters.get("prompt") or parameters.get("query") or parameters.get("question") or "").strip()
    if not prompt:
        return "Error: falta 'prompt' (qué consultar/pensar)."
    system = parameters.get("system")
    provider = parameters.get("provider")          # override opcional
    model = parameters.get("model")                # override opcional
    max_tokens = int(parameters.get("max_tokens") or 2000)
    # Si se pide explícitamente un cerebro sin key → abrir la ventana y avisar
    if provider:
        try:
            from core.credentials import require_key
            ok, msg = require_key(provider)
            if not ok:
                return msg + " Cuando la guardes, repetí el pedido."
        except Exception:
            pass
    if player:
        p, m = (provider, model) if provider else get_reasoning_config()
        player.write_log(f"🧠 Pensando con {p}:{m or '(default)'}...")
    text, used = consult(prompt, system=system, provider=provider, model=model, max_tokens=max_tokens)
    return text


@tool(
    name='model_config',
    description="Configura o muestra el 'cerebro de pensamiento' (modelo que usa consult_model) Y la prioridad del cerebro para PROGRAMAR. USAR cuando el usuario dice: 'usá GPT para pensar', 'cambiá a Claude', 'poné gemini 2.5 pro', 'qué modelos hay', 'qué cerebro estás usando' (→ status/set); o 'para programar priorizá X', 'preguntame siempre cuál usar para programar', 'usá automáticamente mi prioridad' (→ action=code_brain). action=status lista modelos; action=set cambia proveedor/modelo de pensamiento; action=code_brain muestra/cambia la prioridad de programación (mode=ask|auto). La voz NO cambia (siempre Gemini 2.5 Flash).",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'status (lista y muestra el actual) | set | code_brain '
                                              '(prioridad para programar)'},
                    'provider': {'type': 'STRING',
                                 'description': 'set (cerebro de PENSAMIENTO): gemini | openai | '
                                                'claude | minimax | claude_cli | antigravity (CLIs sin '
                                                'API key)'},
                    'model': {'type': 'STRING',
                              'description': 'set: id del modelo de pensamiento (opcional; si se omite '
                                             'usa el default del proveedor)'},
                    'voice': {'type': 'STRING',
                              'description': 'set: cambiar el modelo de VOZ (independiente del '
                                             'cerebro). Default gemini-2.5-flash audio nativo. Solo si '
                                             'el usuario pide cambiar la voz.'},
                    'mode': {'type': 'STRING',
                             'description': 'action=code_brain: ask (preguntar cuál usar cuando hay '
                                            'varias) | auto (usar la 1ra de mi prioridad). Sin mode = '
                                            'solo muestra el estado.'}},
     'required': []},
)
def model_config(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "status").lower().strip()

    if action in ("status", "list", "list_models"):
        from memory.config_manager import cfg as _c
        vm = _c("voice_model", "") or "gemini-2.5-flash (audio nativo, default)"
        return list_models_human() + f"\n\n🎙️ VOZ (independiente del cerebro): {vm}"

    if action in ("set", "use", "switch"):
        # Cambiar el modelo de VOZ (Live API) — independiente del cerebro de pensamiento
        voice = (parameters.get("voice") or "").strip()
        if voice:
            vm = {"gemini-2.5-flash": "models/gemini-2.5-flash-native-audio-preview-12-2025",
                  "2.5-flash": "models/gemini-2.5-flash-native-audio-preview-12-2025"}.get(voice.lower(), voice)
            from memory.config_manager import load_api_keys, save_api_keys
            c = load_api_keys()
            for s in ("gemini_api_key", "openai_api_key", "anthropic_api_key", "minimax_api_key",
                      "spotify_client_id", "spotify_client_secret", "spotify_redirect_uri",
                      "tuya_api_key", "tuya_api_secret", "tuya_region", "figma_token"):
                c.pop(s, None)
            c["voice_model"] = vm
            save_api_keys(c)
            return f"✓ Modelo de VOZ cambiado a {vm}. Aplica al reconectar/reiniciar JARVIS."

        provider = (parameters.get("provider") or "").lower().strip()
        model = (parameters.get("model") or "").strip()
        if provider and provider not in MODELS:
            return f"Proveedor '{provider}' no válido. Opciones: {', '.join(MODELS)}."
        from memory.config_manager import load_api_keys, save_api_keys
        cfg = load_api_keys()
        # quitar secretos para no escribirlos al JSON
        for s in ("gemini_api_key", "openai_api_key", "anthropic_api_key", "minimax_api_key",
                  "spotify_client_id", "spotify_client_secret", "spotify_redirect_uri",
                  "tuya_api_key", "tuya_api_secret", "tuya_region", "figma_token"):
            cfg.pop(s, None)
        if provider:
            saved_p = provider
            saved_m = model or MODELS[provider][0][0]
        elif model:
            saved_p, _ = get_reasoning_config()
            saved_m = model
        else:
            return "Decime 'provider' (gemini/openai/claude/minimax/claude_cli) y/o 'model'."
        cfg["reasoning_provider"] = saved_p
        cfg["reasoning_model"] = saved_m
        save_api_keys(cfg)
        # ¿tiene con qué funcionar? (claude_cli=CLI, el resto=API key)
        from core.llm_router import _has_key
        if _has_key(saved_p):
            return f"✓ Cerebro de pensamiento: {saved_p} / {saved_m}."
        # falta la key → abrir la ventana y avisar que mientras tanto cae a Gemini Flash
        try:
            from core.credentials import require_key
            require_key(saved_p)
        except Exception:
            pass
        return (f"✓ Guardé {saved_p} / {saved_m}, pero falta su API key — te abrí la ventana para cargarla. "
                "Mientras tanto pienso con Gemini Flash. Cuando la cargues, ya uso ese cerebro.")

    if action in ("code_brain", "code_priority", "cerebro_codigo", "prioridad_codigo"):
        from core import code_brain as cb
        sub = (parameters.get("mode") or parameters.get("set") or "").lower().strip()
        if sub in ("ask", "preguntar"):
            cb.set_mode("ask")
            return "✓ Para programar, te voy a preguntar siempre cuál usar cuando haya varias opciones."
        if sub in ("auto", "automatico", "automático", "prioridad"):
            cb.set_mode("auto")
            return "✓ Para programar, voy a usar automáticamente el primero disponible de tu prioridad.\n\n" + cb.status_human()
        return cb.status_human()

    return ("Acciones: status (lista modelos y el actual) | set (provider/model) | "
            "code_brain (prioridad para programar; mode=ask|auto).")
