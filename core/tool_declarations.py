"""
tool_declarations.py — Definiciones de funciones que JARVIS expone a Gemini.

Cada tool tiene: name, description (1 línea), parameters (schema).
Al final se cargan herramientas dinámicas desde actions/custom_tools.json
(creadas por tool_creator/auto_programmer en runtime).
"""
from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent.parent

TOOL_DECLARATIONS = [
    {'name': 'jarvis_ui_control',
     'description': 'Controla la ventana JARVIS y widgets del dashboard (weather, spotify, system, '
                    'notes, todo, maps, image, camera).',
     'parameters': {'type': 'OBJECT',
                    'properties': {'action': {'type': 'STRING',
                                              'description': 'minimize (minimizar ventana) | restore '
                                                             '(restaurar ventana) | show (mostrar '
                                                             'widget) | hide (ocultar widget) | '
                                                             'hide_all (ocultar todos los widgets) | '
                                                             'toggle (alternar widget)'},
                                   'widget': {'type': 'STRING',
                                              'description': 'Nombre del widget (solo para '
                                                             'show/hide/toggle): weather | spotify | '
                                                             'system | notes | todo | maps | image | '
                                                             'camera'}},
                    'required': ['action']}},
    {'name': 'sleep_mode',
     'description': "Modo suspensión: micrófono off hasta que el usuario diga 'JARVIS'.",
     'parameters': {'type': 'OBJECT', 'properties': {}}},
    {'name': 'agent_task',
     'description': 'Tareas multi-paso con varias tools encadenadas. NO usar para un solo comando.',
     'parameters': {'type': 'OBJECT',
                    'properties': {'goal': {'type': 'STRING',
                                            'description': 'Complete description of what to '
                                                           'accomplish'},
                                   'priority': {'type': 'STRING',
                                                'description': 'low | normal | high (default: '
                                                               'normal)'}},
                    'required': ['goal']}},
    {'name': 'shutdown_jarvis',
     'description': 'Cierra JARVIS. Llamar cuando el usuario se despide o pide terminar.',
     'parameters': {'type': 'OBJECT', 'properties': {}}},
    {'name': 'restart_jarvis',
     'description': 'Reinicia JARVIS: lanza una instancia nueva y cierra la actual (vuelve solo en '
                    "unos segundos). USAR cuando el usuario diga 'reiniciate', 'reiniciá JARVIS', "
                    "'reiniciate vos mismo', 'reseteate', o cuando haga falta aplicar cambios de "
                    'código/voz/UI que requieren reinicio. No es lo mismo que apagar '
                    '(shutdown_jarvis): esto vuelve solo.',
     'parameters': {'type': 'OBJECT', 'properties': {}}},
    {'name': 'save_memory',
     'description': 'Guardar hecho personal en memoria de largo plazo. Llamar en silencio. NO para '
                    'clima/recordatorios/comandos puntuales. Values en inglés.',
     'parameters': {'type': 'OBJECT',
                    'properties': {'category': {'type': 'STRING',
                                                'description': 'identity — name, age, birthday, city, '
                                                               'job, language, nationality | '
                                                               'preferences — favorite '
                                                               'food/color/music/film/game/sport, '
                                                               'hobbies | projects — active projects, '
                                                               'goals, things being built | '
                                                               'relationships — friends, family, '
                                                               'partner, colleagues | wishes — future '
                                                               'plans, things to buy, travel dreams | '
                                                               'notes — habits, schedule, anything '
                                                               'else worth remembering'},
                                   'key': {'type': 'STRING',
                                           'description': 'Short snake_case key (e.g. name, '
                                                          'favorite_food, sister_name)'},
                                   'value': {'type': 'STRING',
                                             'description': 'Concise value in English (e.g. Fatih, '
                                                            'pizza, older sister)'}},
                    'required': ['category', 'key', 'value']}},
]

# Cargar herramientas dinámicas creadas por tool_creator
try:
    _custom_tools_path = BASE_DIR / "actions" / "custom_tools.json"
    if _custom_tools_path.exists():
        _custom_tools = json.loads(_custom_tools_path.read_text(encoding="utf-8"))
        if isinstance(_custom_tools, list):
            for _t in _custom_tools:
                if _t.get("name") not in [td["name"] for td in TOOL_DECLARATIONS]:
                    TOOL_DECLARATIONS.append(_t)
except Exception as _e:
    pass
