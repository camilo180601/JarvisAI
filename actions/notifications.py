"""
notifications.py — Tool para que JARVIS controle el motor de notificaciones por voz.

Acciones:
  status         — qué fuentes están activas, qué reglas hay, estado DND
  add_alert      — "avisame si me escribe Juan" (contact, keyword, source)
  remove_alert   — quitar una regla por id
  list_alerts    — listar reglas activas
  dnd_on         — "silenciá X por Y" (scope, duration)
  dnd_off        — quitar el silencio
  dnd_status     — ver si hay DND activo y cuándo expira
"""
from __future__ import annotations
import re
from datetime import datetime

from core.notification_engine import get_engine
from core.registry import tool

# Conversión de duración natural → segundos
def _parse_duration(raw: str) -> int:
    """Acepta '1h', '30m', '90s', '2h30m', '1h30m' o numero (= segundos)."""
    raw = (raw or "").strip().lower()
    if not raw:
        return 3600
    if raw.isdigit():
        return int(raw)
    total = 0
    for amount, unit in re.findall(r"(\d+)\s*([smh])", raw):
        n = int(amount)
        if unit == "s": total += n
        elif unit == "m": total += n * 60
        elif unit == "h": total += n * 3600
    return total or 3600


@tool(
    name='notifications',
    description="Controla notificaciones proactivas y modo No Molestar. USAR cuando el usuario dice: 'avisame si me escribe X', 'avisame de TODOS los WhatsApp' (add_alert source=whatsapp SIN contact = catch-all), 'silenciá WhatsApp/iMessage/email por N hora(s)', 'dejame en paz por N minutos', '¿quién me escribió?', 'quitá el silencio', 'modo concentración'. Los remitentes de WhatsApp se muestran con el nombre de la agenda de Apple (ej 'Mamá'). Acciones: status | add_alert | remove_alert | list_alerts | dnd_on | dnd_off | dnd_status.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'status | add_alert | remove_alert | list_alerts | '
                                              'dnd_on | dnd_off | dnd_status'},
                    'name': {'type': 'STRING',
                             'description': 'Para add_alert: nombre descriptivo de la regla'},
                    'contact': {'type': 'STRING',
                                'description': 'Para add_alert: nombre del contacto a vigilar'},
                    'keyword': {'type': 'STRING',
                                'description': 'Para add_alert: palabra clave en el mensaje'},
                    'source': {'type': 'STRING',
                               'description': 'imessage | whatsapp | gmail | * (default *)'},
                    'id': {'type': 'STRING', 'description': 'Para remove_alert: id de la regla'},
                    'scope': {'type': 'STRING',
                              'description': 'Para dnd_on: all | imessage | whatsapp | gmail | '
                                             'contact:NOMBRE'},
                    'duration': {'type': 'STRING',
                                 'description': "Para dnd_on: duración natural '1h', '30m', '2h30m' o "
                                                'segundos'},
                    'whitelist_keywords': {'type': 'ARRAY',
                                           'items': {'type': 'STRING'},
                                           'description': 'Palabras que SÍ alertan aunque haya DND '
                                                          "(ej: 'urgente')"},
                    'whitelist_contacts': {'type': 'ARRAY',
                                           'items': {'type': 'STRING'},
                                           'description': 'Contactos que SÍ alertan aunque haya DND'}},
     'required': ['action']},
)
def run(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "status").lower()
    engine = get_engine()

    if action == "status":
        rules = engine.list_rules()
        dnd = engine.get_dnd()
        sources = [s.name for s in engine.sources]
        lines = [
            f"📬 Notification Engine",
            f"  Sources activas: {', '.join(sources) if sources else '(ninguna)'}",
            f"  Reglas: {len(rules)}",
        ]
        if dnd.active():
            lines.append(f"  🔇 DND activo: scope='{dnd.scope}', expira {dnd.expires_at}")
        else:
            lines.append(f"  🔔 DND inactivo")
        return "\n".join(lines)

    if action == "add_alert":
        name = (parameters.get("name") or "").strip()
        contact = (parameters.get("contact") or "").strip()
        keyword = (parameters.get("keyword") or "").strip()
        source = (parameters.get("source") or "*").strip().lower()
        # "todos/all/*" como contacto = avisar de TODOS los mensajes de esa fuente.
        if contact.lower() in ("*", "todos", "todas", "all", "cualquiera", "cualquier"):
            contact = ""
        # Catch-all permitido SOLO si se acota a una fuente concreta (ej whatsapp).
        if not (contact or keyword):
            if source in ("whatsapp", "imessage", "gmail"):
                name = name or f"Todos los {source}"
            else:
                return ("Error: especificá 'contact', 'keyword', o una 'source' concreta "
                        "(ej source=whatsapp para avisar de TODOS los WhatsApp).")
        if not name:
            name = f"Alerta de {contact or keyword}"
        r = engine.add_rule(name=name, contact=contact, keyword=keyword, source=source)
        return f"✓ Regla '{name}' creada [{r.id}]. JARVIS te avisará cuando matchee."

    if action == "remove_alert":
        rule_id = (parameters.get("id") or "").strip()
        if not rule_id:
            return "Error: falta 'id' de la regla."
        ok = engine.remove_rule(rule_id)
        return "✓ Regla eliminada." if ok else f"No encontré regla con id '{rule_id}'."

    if action == "list_alerts":
        rules = engine.list_rules()
        if not rules:
            return "Sin reglas. Usá add_alert con contact y/o keyword."
        lines = [f"Reglas activas ({len(rules)}):"]
        for r in rules:
            flag = "✓" if r.enabled else "✗"
            conds = []
            if r.contact: conds.append(f"contact={r.contact}")
            if r.keyword: conds.append(f"keyword={r.keyword}")
            if r.source != "*": conds.append(f"source={r.source}")
            lines.append(f"  [{r.id}] {flag} {r.name} ({', '.join(conds)})")
        return "\n".join(lines)

    if action == "dnd_on":
        scope = (parameters.get("scope") or "all").strip().lower()
        duration = parameters.get("duration") or "1h"
        secs = _parse_duration(duration) if isinstance(duration, str) else int(duration)
        # whitelist opcional
        wl_kw = parameters.get("whitelist_keywords") or []
        wl_ct = parameters.get("whitelist_contacts") or []
        if isinstance(wl_kw, str): wl_kw = [wl_kw]
        if isinstance(wl_ct, str): wl_ct = [wl_ct]
        dnd = engine.set_dnd(scope=scope, duration_seconds=secs,
                             whitelist_keywords=wl_kw, whitelist_contacts=wl_ct)
        hrs = secs / 3600
        suffix = " (con whitelist)" if (wl_kw or wl_ct) else ""
        return f"🔇 DND activado: '{scope}' por {hrs:.1f}h{suffix}. Expira: {dnd.expires_at}"

    if action == "dnd_off":
        engine.clear_dnd()
        return "🔔 DND quitado. Notificaciones normales."

    if action == "dnd_status":
        dnd = engine.get_dnd()
        if not dnd.active():
            return "🔔 Sin DND activo."
        return (
            f"🔇 DND activo: scope='{dnd.scope}', expira {dnd.expires_at}\n"
            f"  Whitelist keywords: {dnd.whitelist_keywords}\n"
            f"  Whitelist contacts: {dnd.whitelist_contacts}"
        )

    return f"Acción '{action}' no soportada. Usá: status | add_alert | remove_alert | list_alerts | dnd_on | dnd_off | dnd_status"
