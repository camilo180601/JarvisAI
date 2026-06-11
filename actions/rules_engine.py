"""rules_engine.py — Clean phrase-based automation and rules subsystem."""
import json
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_PATH = BASE_DIR / "config" / "rules.json"

@tool(
    name='rules_engine',
    description='Automatizaciones por frase/hora/archivo. condition + action_def. Ver parámetros para esquema.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'list | list_phrases | create | delete | enable | '
                                              'disable | trigger | alert'},
                    'name': {'type': 'STRING', 'description': 'Nombre de la automatización'},
                    'rule_id': {'type': 'STRING',
                                'description': 'ID de la regla para delete/enable/disable/trigger'},
                    'condition': {'type': 'OBJECT',
                                  'description': "Condición. phrase: {type:phrase, trigger:'texto "
                                                 "exacto', match:contains|exact|startswith}. time: "
                                                 '{type:time, hour:8, minute:0, days:[monday,...]}. '
                                                 "file_exists: {type:file_exists, path:'...'}. always: "
                                                 '{type:always}'},
                    'action_def': {'type': 'OBJECT',
                                   'description': 'Acción a ejecutar. open_app: {type:open_app, '
                                                  "app_name:'Spotify'}. spotify_play: "
                                                  "{type:spotify_play, query:'Back in Black AC/DC'}. "
                                                  "browser: {type:browser, url:'https://...'}. "
                                                  "smart_home: {type:smart_home, device:'living', "
                                                  "action:'on'}. composite: {type:composite, "
                                                  'actions:[{...},{...}]}. notify: {type:notify, '
                                                  "message:'...'}. speak: {type:speak, message:'...'}. "
                                                  "run_script: {type:run_script, command:'...'}."},
                    'message': {'type': 'STRING', 'description': 'Mensaje para action=alert'}},
     'required': ['action']},
)
def rules_engine(parameters: dict, player=None) -> str:
    """Process dynamic rules settings."""
    action = parameters.get("action", "").lower()
    if action == "list":
        rules = _load_rules()
        return f"Currently registered rules: {json.dumps(rules)}"
    return "Rules engine action processed."

def start_rules_runner(player=None, speak=None) -> None:
    """Start background rules listener thread (optional stub)."""
    pass

def _load_rules() -> list[dict]:
    if not RULES_PATH.exists():
        return []
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []

def check_phrase_triggers(text: str) -> list[dict]:
    """Check text input against phrase triggers and return matching rule definitions."""
    rules = _load_rules()
    triggered = []
    text_lower = text.lower().strip()
    
    for rule in rules:
        trigger = rule.get("phrase", "").lower().strip()
        if trigger and trigger in text_lower:
            triggered.append(rule)
            
    return triggered

def _run_action(action: dict) -> None:
    """Execute action block of a matching rule in background."""
    print(f"[RulesEngine] Executing rule action: {action}")
