"""
gmail_control.py — Gestión real de Gmail vía OAuth.

Acciones: inbox, read, send, reply, search, archive, delete, mark_read, labels.
"""
from __future__ import annotations
import base64
from email.mime.text import MIMEText

from actions.google_auth import get_service
from core.registry import tool


def _format_message_brief(msg: dict) -> str:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    sender = headers.get("From", "?")
    subject = headers.get("Subject", "(sin asunto)")
    snippet = (msg.get("snippet") or "")[:100]
    mid = msg.get("id", "")[:10]
    unread = "🆕 " if "UNREAD" in msg.get("labelIds", []) else ""
    return f"[{mid}] {unread}{sender}\n  📧 {subject}\n  {snippet}"


def _get_full_body(msg: dict) -> str:
    """Extrae cuerpo del mensaje (text/plain preferido)."""
    def walk(payload):
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return payload["body"]["data"]
        for part in payload.get("parts", []) or []:
            found = walk(part)
            if found:
                return found
        return None
    data = walk(msg.get("payload", {}))
    if not data:
        return msg.get("snippet", "")
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return msg.get("snippet", "")


@tool(
    name='gmail_control',
    description='Gmail: inbox, read, send, reply, search, archive, delete, mark_read, labels.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'inbox | read | send | reply | search | archive | delete '
                                              '| mark_read | labels'},
                    'count': {'type': 'INTEGER',
                              'description': 'Cantidad de correos a listar/buscar (default: 5)'},
                    'message_id': {'type': 'STRING',
                                   'description': 'ID del mensaje para '
                                                  'read/reply/archive/delete/mark_read'},
                    'to': {'type': 'STRING', 'description': 'Destinatario para send'},
                    'subject': {'type': 'STRING', 'description': 'Asunto para send'},
                    'body': {'type': 'STRING', 'description': 'Cuerpo del correo para send/reply'},
                    'query': {'type': 'STRING',
                              'description': "Búsqueda Gmail para search (ej: 'from:juan', "
                                             "'subject:factura')"},
                    'confirm': {'type': 'BOOLEAN', 'description': 'true para confirmar eliminación'}},
     'required': ['action']},
)
def gmail_control(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "inbox").lower()

    try:
        service = get_service("gmail", "v1")
    except FileNotFoundError as e:
        return str(e)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error de autenticación Google: {e}"

    try:
        if action in ("inbox", "list"):
            count = int(parameters.get("count", 5))
            res = service.users().messages().list(
                userId="me", labelIds=["INBOX"], maxResults=count,
            ).execute()
            ids = [m["id"] for m in res.get("messages", [])]
            if not ids:
                return "Bandeja vacía."
            briefs = []
            for mid in ids:
                m = service.users().messages().get(userId="me", id=mid, format="metadata",
                                                    metadataHeaders=["From", "Subject"]).execute()
                briefs.append(_format_message_brief(m))
            return f"Últimos {len(briefs)} correos:\n" + "\n\n".join(briefs)

        if action == "read":
            mid = parameters.get("message_id", "")
            if not mid:
                return "Error: 'message_id' obligatorio."
            m = service.users().messages().get(userId="me", id=mid, format="full").execute()
            headers = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
            body = _get_full_body(m)
            if len(body) > 2000:
                body = body[:2000] + "\n...[truncado]"
            return (
                f"De: {headers.get('From', '?')}\n"
                f"Asunto: {headers.get('Subject', '(sin asunto)')}\n"
                f"Fecha: {headers.get('Date', '?')}\n\n"
                f"{body}"
            )

        if action == "send":
            to = parameters.get("to", "")
            subject = parameters.get("subject", "")
            body = parameters.get("body", "")
            if not to or not body:
                return "Error: 'to' y 'body' obligatorios."
            mime = MIMEText(body, _charset="utf-8")
            mime["to"] = to
            mime["subject"] = subject
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return f"Correo enviado a {to} (id: {sent.get('id', '')[:10]})"

        if action == "reply":
            mid = parameters.get("message_id", "")
            body = parameters.get("body", "")
            if not mid or not body:
                return "Error: 'message_id' y 'body' obligatorios para reply."
            original = service.users().messages().get(userId="me", id=mid, format="metadata",
                                                       metadataHeaders=["From", "Subject", "Message-ID"]).execute()
            headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
            mime = MIMEText(body, _charset="utf-8")
            mime["to"] = headers.get("From", "")
            mime["subject"] = "Re: " + headers.get("Subject", "")
            if headers.get("Message-ID"):
                mime["In-Reply-To"] = headers["Message-ID"]
                mime["References"] = headers["Message-ID"]
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
            sent = service.users().messages().send(
                userId="me", body={"raw": raw, "threadId": original.get("threadId")},
            ).execute()
            return f"Respuesta enviada (id: {sent.get('id', '')[:10]})"

        if action == "search":
            query = parameters.get("query", "")
            count = int(parameters.get("count", 5))
            if not query:
                return "Error: 'query' obligatorio (ej: 'from:juan', 'subject:factura')."
            res = service.users().messages().list(userId="me", q=query, maxResults=count).execute()
            ids = [m["id"] for m in res.get("messages", [])]
            if not ids:
                return f"Sin resultados para '{query}'."
            briefs = []
            for mid in ids:
                m = service.users().messages().get(userId="me", id=mid, format="metadata",
                                                    metadataHeaders=["From", "Subject"]).execute()
                briefs.append(_format_message_brief(m))
            return f"Resultados de '{query}':\n" + "\n\n".join(briefs)

        if action == "archive":
            mid = parameters.get("message_id", "")
            if not mid:
                return "Error: 'message_id' obligatorio."
            service.users().messages().modify(
                userId="me", id=mid, body={"removeLabelIds": ["INBOX"]},
            ).execute()
            return f"Correo {mid[:10]} archivado."

        if action == "delete":
            mid = parameters.get("message_id", "")
            if not mid:
                return "Error: 'message_id' obligatorio."
            if not parameters.get("confirm"):
                return "Eliminación requiere confirm=true (el correo va a Trash)."
            service.users().messages().trash(userId="me", id=mid).execute()
            return f"Correo {mid[:10]} movido a Trash."

        if action == "mark_read":
            mid = parameters.get("message_id", "")
            if not mid:
                return "Error: 'message_id' obligatorio."
            service.users().messages().modify(
                userId="me", id=mid, body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            return f"Correo {mid[:10]} marcado como leído."

        if action == "labels":
            res = service.users().labels().list(userId="me").execute()
            labels = [l["name"] for l in res.get("labels", [])]
            return "Etiquetas:\n" + "\n".join(sorted(labels))

        return f"Acción '{action}' no soportada."

    except Exception as e:
        return f"Error en gmail_control: {e}"
