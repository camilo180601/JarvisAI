"""goals.py — Clean dynamic goals/tasks tracker."""
import json
from pathlib import Path
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
GOALS_PATH = BASE_DIR / "config" / "goals.json"

@tool(
    name='goals',
    description='Metas a largo plazo con steps y progreso: list, create, update_progress, complete, complete_step, add_step, delete, detail.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'list | create | update_progress | complete | '
                                              'complete_step | add_step | delete | detail'},
                    'goal_id': {'type': 'STRING',
                                'description': 'ID del objetivo para update/complete/delete/detail'},
                    'title': {'type': 'STRING', 'description': 'Título del objetivo'},
                    'description': {'type': 'STRING', 'description': 'Descripción detallada'},
                    'deadline': {'type': 'STRING', 'description': 'Fecha límite ISO (YYYY-MM-DD)'},
                    'progress': {'type': 'INTEGER', 'description': 'Progreso 0-100'},
                    'steps': {'type': 'ARRAY',
                              'items': {'type': 'STRING'},
                              'description': 'Lista de pasos del objetivo'},
                    'step': {'type': 'STRING', 'description': 'Texto del nuevo paso (add_step)'},
                    'step_index': {'type': 'INTEGER',
                                   'description': 'Índice del paso a completar (0-based)'}},
     'required': ['action']},
)
def goals(parameters: dict, player=None) -> str:
    """Read, create, or update user goals and benchmarks."""
    action = parameters.get("action", "list").lower()
    
    if action == "list":
        if not GOALS_PATH.exists():
            return "You have no active goals defined, sir."
        try:
            items = json.loads(GOALS_PATH.read_text(encoding="utf-8"))
            return "Active goals:\n" + "\n".join(f"- {g}" for g in items)
        except Exception:
            return "No active goals found."
            
    elif action == "add":
        goal_text = parameters.get("goal", "").strip()
        if not goal_text:
            return "Goal text is required, sir."
        try:
            items = []
            if GOALS_PATH.exists():
                items = json.loads(GOALS_PATH.read_text(encoding="utf-8"))
            items.append(goal_text)
            GOALS_PATH.parent.mkdir(parents=True, exist_ok=True)
            GOALS_PATH.write_text(json.dumps(items, indent=2), encoding="utf-8")
            return f"Goal '{goal_text}' added successfully."
        except Exception as e:
            return f"Failed to record goal: {e}"
            
    return f"Goal action '{action}' is not supported yet."
