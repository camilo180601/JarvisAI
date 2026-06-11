"""
whatsapp.py — Envío de WhatsApp vía el BRIDGE local (whatsmeow), SIN navegador.

Antes abría WhatsApp Web en el navegador + pyautogui (frágil). Ahora manda por el
bridge (POST http://localhost:8080/api/send), igual que las tools mcp__whatsapp__*.
El QR de la terminal (whatsapp_connect) es el login UNA vez; después se envía directo.
"""
import json
import unicodedata
from pathlib import Path
from core.registry import tool


def _norm(s: str) -> str:
    """Minúsculas sin acentos, para comparar 'Mama' con 'Mamá'."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()

BASE_DIR = Path(__file__).resolve().parent.parent
CONTACTS_FILE = BASE_DIR / "config" / "whatsapp_contacts.json"
BRIDGE_URL = "http://localhost:8080/api/send"


def load_contacts() -> dict:
    if CONTACTS_FILE.exists():
        try:
            return json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_contacts(contacts: dict):
    try:
        CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTACTS_FILE.write_text(json.dumps(contacts, indent=4, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[WhatsApp] Error saving contacts: {e}")


def _resolve_phone(receiver: str, contacts: dict) -> tuple[str, str]:
    """Devuelve (telefono, nombre_mostrado). telefono='' si no se pudo resolver."""
    cleaned = "".join(c for c in receiver if c.isdigit() or c == "+")
    if sum(c.isdigit() for c in cleaned) >= 8:
        return cleaned.replace("+", ""), receiver
    m = contacts.get(receiver.lower())
    if m:
        return m["phone"], m["name"]
    for k, v in contacts.items():
        if receiver.lower() in k or k in receiver.lower():
            return v["phone"], v["name"]
    return "", receiver


# ── Resolución vía la base del bridge (contactos sincronizados de WhatsApp) ──
# WhatsApp usa LIDs (IDs internos) en vez del número. whatsmeow_lid_map mapea
# LID → número (pn); whatsmeow_contacts tiene los nombres. Así "mandá a Mamá"
# resuelve aunque no esté en los contactos locales de JARVIS.

def _whatsapp_db():
    import re
    cands = []
    cfg = BASE_DIR / "config" / "mcp_servers.json"
    try:
        txt = cfg.read_text(encoding="utf-8")
        for mt in re.finditer(r'"(/[^"]*whatsapp-mcp[^"]*)"', txt):
            base = Path(mt.group(1))
            while base.name and base.name != "whatsapp-mcp":
                base = base.parent
            if base.name == "whatsapp-mcp":
                cands.append(base / "whatsapp-bridge" / "store" / "whatsapp.db")
    except Exception:
        pass
    cands.append(BASE_DIR / "integrations" / "whatsapp-mcp" / "whatsapp-bridge" / "store" / "whatsapp.db")
    cands.append(Path.home() / "Documents" / "whatsapp-mcp" / "whatsapp-bridge" / "store" / "whatsapp.db")
    for c in cands:
        if c.exists():
            return c
    return None


def _bridge_matches(name: str) -> list[tuple[str, str]]:
    """Busca contactos por nombre en la base del bridge. Devuelve [(nombre, telefono)]."""
    db = _whatsapp_db()
    if not db or not name.strip():
        return []
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute(
            """
            SELECT COALESCE(NULLIF(c.full_name,''), NULLIF(c.first_name,''), c.push_name) AS nm, m.pn
            FROM whatsmeow_contacts c
            JOIN whatsmeow_lid_map m ON replace(c.their_jid,'@lid','') = m.lid
            WHERE m.pn IS NOT NULL AND m.pn != ''
              AND lower(COALESCE(c.full_name,'')||' '||COALESCE(c.first_name,'')||' '||COALESCE(c.push_name,'')) LIKE ?
            LIMIT 8
            """,
            (f"%{name.lower().strip()}%",),
        )
        rows = [(nm or "", pn) for nm, pn in cur.fetchall() if pn]
        con.close()
        # dedup por número
        seen, out = set(), []
        for nm, pn in rows:
            if pn not in seen:
                seen.add(pn); out.append((nm, pn))
        return out
    except Exception:
        return []


def _lid_to_phone(lid: str) -> str:
    """LID (123@lid o 123) → número de teléfono, vía el mapeo del bridge."""
    lid = (lid or "").replace("@lid", "").strip()
    if not lid.isdigit():
        return ""
    db = _whatsapp_db()
    if not db:
        return ""
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute("SELECT pn FROM whatsmeow_lid_map WHERE lid=?", (lid,))
        r = cur.fetchone()
        con.close()
        return r[0] if r and r[0] else ""
    except Exception:
        return ""


def sender_to_name(sender: str, chat_jid: str = "") -> str:
    """JID/LID del remitente → nombre de la agenda de Apple (o '+número real').

    Ojo: en messages.db el `sender` viene como dígitos PELADOS (sin '@lid') y el
    marcador solo está en chat_jid — por eso el LID se mapea mirando AMBOS campos,
    y como red final se intenta el mapeo LID→número siempre que el 'número' no
    resuelva a un contacto (un LID parece un teléfono pero no lo es)."""
    jid = sender or chat_jid or ""
    # el marcador @lid puede venir en cualquiera de los dos campos
    is_lid = "@lid" in (sender or "") or "@lid" in (chat_jid or "")
    digits = "".join(c for c in jid.split("@")[0].split(":")[0] if c.isdigit())
    if not digits:
        return "WhatsApp"

    def _name(ph: str) -> str:
        try:
            from core import mac_contacts as _mc
            return _mc.name_for_phone(ph)
        except Exception:
            return ""

    phone = digits
    if is_lid:
        mapped = _lid_to_phone(digits)
        if mapped:
            phone = mapped
    nm = _name(phone)
    if nm:
        return nm
    # Red final: si no resolvió, puede ser un LID sin marcador → probar el mapeo igual
    if phone == digits:
        mapped = _lid_to_phone(digits)
        if mapped:
            phone = mapped
            nm = _name(phone)
            if nm:
                return nm
    return "+" + phone


def _messages_db():
    db = _whatsapp_db()
    if db:
        m = db.parent / "messages.db"
        if m.exists():
            return m
    return None


def _read_recent(count: int = 5, who: str = "") -> str:
    """Lee los últimos mensajes ENTRANTES (para 'leelo'). Resuelve nombres."""
    db = _messages_db()
    if not db:
        return "No encuentro la base de mensajes de WhatsApp (¿el bridge está conectado?)."
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        cur = con.cursor()
        cur.execute(
            "SELECT sender, chat_jid, content, timestamp FROM messages "
            "WHERE is_from_me=0 AND content IS NOT NULL AND content!='' "
            "ORDER BY timestamp DESC LIMIT ?",
            (max(count, 1) * 6,),
        )
        rows = cur.fetchall()
        con.close()
    except Exception as e:
        return f"No pude leer los mensajes: {str(e)[:80]}"
    out = []
    for sender, chat_jid, content, _ts in rows:
        nm = sender_to_name(sender, chat_jid)
        if who and who.lower() not in nm.lower():
            continue
        out.append(f"{nm}: {content.strip()}")
        if len(out) >= count:
            break
    if not out:
        return f"No hay mensajes recientes{(' de ' + who) if who else ''}."
    out.reverse()
    return "📩 Mensajes:\n" + "\n".join(out)


@tool(
    name='whatsapp',
    description='WhatsApp: enviar texto/imagen, buscar contactos por nombre, leer, agregar/listar contactos. Resuelve el nombre del destinatario contra los contactos sincronizados de WhatsApp (no hace falta tenerlo guardado en JARVIS). Si hay varios parecidos, la tool los lista para que elijas; si no encuentra, pedir el número con código de país.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'send | send_image | search | read | unread | '
                                              'add_contact | list_contacts | delete_contact'},
                    'receiver': {'type': 'STRING',
                                 'description': 'Nombre del contacto (se busca en tus contactos de '
                                                'WhatsApp) o número con código de país (ej: '
                                                '573001234567)'},
                    'message': {'type': 'STRING', 'description': 'Texto del mensaje a enviar'},
                    'image_path': {'type': 'STRING',
                                   'description': 'Ruta de la imagen para send_image'},
                    'caption': {'type': 'STRING', 'description': 'Descripción de la imagen (opcional)'},
                    'count': {'type': 'INTEGER',
                              'description': 'Cantidad de mensajes a leer (default: 10)'},
                    'name': {'type': 'STRING',
                             'description': 'Nombre del contacto para add_contact/delete_contact'},
                    'phone': {'type': 'STRING',
                              'description': 'Número de teléfono con código de país (ej: '
                                             '5491155551234) para add_contact'}},
     'required': ['action']},
)
def whatsapp(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "").lower()
    receiver = parameters.get("receiver", "")
    message = parameters.get("message", "")
    image_path = parameters.get("image_path", "")
    caption = parameters.get("caption", "")
    name = parameters.get("name", "")
    phone_param = parameters.get("phone", "")
    contacts = load_contacts()

    if action == "send_text":
        action = "send"
    elif action in ("read_unread", "read_chat", "unread"):
        action = "read"

    # ── Contactos (DB local de JARVIS) ──
    if action == "add_contact":
        cn = name or receiver
        if not cn or not phone_param:
            return "Para agregar un contacto necesito 'name' y 'phone'."
        contacts[cn.lower()] = {"name": cn, "phone": "".join(filter(str.isdigit, phone_param))}
        save_contacts(contacts)
        return f"✓ Contacto '{cn}' guardado ({contacts[cn.lower()]['phone']})."
    if action == "delete_contact":
        cn = (name or receiver).lower()
        if cn in contacts:
            del contacts[cn]; save_contacts(contacts)
            return f"✓ Contacto eliminado."
        return "No encontré ese contacto."
    if action == "list_contacts":
        if not contacts:
            return "No tenés contactos guardados en JARVIS."
        return "Contactos:\n" + "\n".join(f"• {v['name']}: {v['phone']}" for v in contacts.values())
    if action in ("search", "buscar", "find", "search_contact", "buscar_contacto"):
        q = (receiver or name or parameters.get("query", "")).strip()
        if not q:
            return "¿Qué contacto busco?"
        matches = _bridge_matches(q)
        if not matches:
            return f"No encontré contactos de WhatsApp parecidos a '{q}'."
        return "Contactos de WhatsApp:\n" + "\n".join(
            f"• {n or 'sin nombre'}: +{p}" for n, p in matches[:10])

    # ── Enviar (por el bridge, sin navegador) ──
    if action in ("send", "send_image"):
        if not receiver:
            return "¿A quién? Falta 'receiver'."
        phone, target = _resolve_phone(receiver, contacts)
        if not phone:
            # Fallback: 1º la agenda de Apple (alias reales: "Mamá"), 2º los contactos
            # sincronizados de WhatsApp (nombre de perfil).
            try:
                from core import mac_contacts as _mc
                matches = _mc.find_by_name(receiver)
            except Exception:
                matches = []
            if not matches:
                matches = _bridge_matches(receiver)
            exact = [m for m in matches if _norm(m[0]) == _norm(receiver)]
            if len(exact) == 1:
                target, phone = exact[0][0], exact[0][1]
            elif len(matches) == 1:
                target, phone = matches[0][0] or receiver, matches[0][1]
            elif len(matches) > 1:
                opts = "; ".join(f"{n or 'sin nombre'} (+{p})" for n, p in matches[:5])
                return (f"Hay varios contactos parecidos a '{receiver}': {opts}. "
                        "Decime el nombre exacto o pasame el número.")
        if not phone:
            return (f"No tengo el número de '{target}'. Pasame el número con código de país "
                    "(ej: 573001234567) o guardalo con add_contact.")
        if not message and not image_path:
            return "¿Qué mando? Falta 'message' (o 'image_path')."
        payload = {"recipient": phone, "message": message or caption or ""}
        if action == "send_image" and image_path:
            payload["media_path"] = image_path
        if player:
            player.write_log(f"💬 Enviando WhatsApp a {target} (bridge)...")
        try:
            import requests
            r = requests.post(BRIDGE_URL, json=payload, timeout=20)
            if r.status_code == 200 and r.json().get("success"):
                return f"✓ Mensaje enviado a {target} por WhatsApp."
            return f"✗ El bridge no pudo enviar a {target}: {r.text[:150]}"
        except Exception as e:
            if "Connection" in str(e) or "refused" in str(e).lower():
                return ("WhatsApp no está conectado (el bridge no corre). Decí 'conectá WhatsApp' "
                        "y escaneá el QR de la terminal una vez; después envío directo, sin navegador.")
            return f"Error enviando WhatsApp: {str(e)[:120]}"

    # ── Leer (para "leelo") ──
    if action == "read":
        try:
            count = int(parameters.get("count") or 3)
        except Exception:
            count = 3
        who = receiver or name or ""
        return _read_recent(count=count, who=who)

    return f"Acción '{action}' no reconocida para WhatsApp."
