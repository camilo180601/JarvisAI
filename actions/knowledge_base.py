"""
knowledge_base.py — Base de conocimiento local en JSON.

Permite a JARVIS guardar, buscar y listar notas/hechos personales del usuario
sin depender de servicios externos.
"""
import json
from pathlib import Path
from datetime import datetime
from core.registry import tool

BASE_DIR = Path(__file__).resolve().parent.parent
KB_FILE = BASE_DIR / "config" / "knowledge_base.json"


def _load() -> list:
    if not KB_FILE.exists():
        return []
    try:
        return json.loads(KB_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(entries: list) -> None:
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    KB_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


@tool(
    name='knowledge_base',
    description='Notas personales locales: add, search, list, delete.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'add/save/store | search/find | list | get/read/view | '
                                              'update | delete | stats | export'},
                    'title': {'type': 'STRING', 'description': 'Título de la entrada'},
                    'content': {'type': 'STRING', 'description': 'Contenido o texto a guardar'},
                    'type': {'type': 'STRING',
                             'description': 'note | idea | snippet | reference | fact | task | '
                                            'question'},
                    'tags': {'type': 'STRING',
                             'description': 'Tags separados por coma (ej: python, jarvis, idea)'},
                    'query': {'type': 'STRING', 'description': 'Búsqueda en la base de conocimiento'},
                    'entry_id': {'type': 'STRING',
                                 'description': 'ID de la entrada para get/update/delete'},
                    'path': {'type': 'STRING', 'description': 'Ruta para exportar (action=export)'}},
     'required': ['action']},
)
def knowledge_base(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "list").lower()
    entries = _load()

    if action == "add" or action == "save":
        topic = (parameters.get("topic") or parameters.get("name") or "").strip()
        content = (parameters.get("content") or parameters.get("text") or "").strip()
        if not content:
            return "Error: falta 'content' para guardar."
        entry = {
            "id": len(entries) + 1,
            "topic": topic or "general",
            "content": content,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        entries.append(entry)
        _save(entries)
        return f"Guardado en knowledge_base [#{entry['id']}, tema: {entry['topic']}]"

    if action == "search":
        query = (parameters.get("query") or "").lower().strip()
        if not query:
            return "Error: falta 'query' para search."
        matches = [
            e for e in entries
            if query in e.get("content", "").lower() or query in e.get("topic", "").lower()
        ]
        if not matches:
            return f"Sin coincidencias para '{query}'."
        lines = [
            f"#{e['id']} [{e['topic']}] {e['content'][:200]}"
            for e in matches[:10]
        ]
        return f"Encontradas {len(matches)} entradas:\n" + "\n".join(lines)

    if action == "list":
        topic_filter = (parameters.get("topic") or "").lower().strip()
        items = entries
        if topic_filter:
            items = [e for e in entries if e.get("topic", "").lower() == topic_filter]
        if not items:
            return "Base de conocimiento vacía."
        lines = [f"#{e['id']} [{e['topic']}] {e['content'][:150]}" for e in items[-20:]]
        return f"Últimas {min(len(items), 20)} entradas:\n" + "\n".join(lines)

    if action == "delete":
        eid = parameters.get("id")
        if eid is None:
            return "Error: falta 'id' para delete."
        try:
            eid = int(eid)
        except ValueError:
            return "Error: 'id' debe ser un número."
        new_entries = [e for e in entries if e.get("id") != eid]
        if len(new_entries) == len(entries):
            return f"No se encontró entrada #{eid}."
        _save(new_entries)
        return f"Entrada #{eid} eliminada."

    return f"Acción '{action}' no soportada. Usa: add, search, list, delete."
