"""
notification_engine.py — Motor de notificaciones proactivas para JARVIS.

Mira fuentes externas (iMessage, WhatsApp, Gmail) en background.
Cuando llega algo que matchea una regla, le dice a JARVIS que hable.

Componentes:
  - EventSource: base class para fuentes pollables
  - iMessageSource: Mac chat.db (gratis, requiere Full Disk Access)
  - WhatsAppSource: SQLite del whatsapp-mcp bridge (si está instalado)
  - GmailSource: vía google_auth (si está configurado)
  - NotificationEngine: orquestador con rules + DND

Persistencia: ~/.jarvis/notifications.json (rules + dnd + last-seen markers)
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_FILE = Path.home() / ".jarvis" / "notifications.json"

DEFAULT_POLL_INTERVAL = 8         # seconds entre polls de fuentes "rápidas"
GMAIL_POLL_INTERVAL = 90          # email no necesita 5s
MAX_BATCH_PER_POLL = 5            # nunca anunciar más de N eventos juntos


# ── Modelos ──────────────────────────────────────────────────────────────────

@dataclass
class Event:
    source: str           # "imessage" | "whatsapp" | "gmail"
    contact: str          # nombre o identifier del remitente
    text: str             # contenido (resumido si email)
    timestamp: float      # epoch
    raw_id: str = ""      # id estable para dedup


@dataclass
class Rule:
    id: str
    name: str
    contact: str = ""           # match exact/contains case-insensitive
    keyword: str = ""           # match en text
    source: str = "*"           # "imessage" | "whatsapp" | "gmail" | "*"
    enabled: bool = True
    created: str = ""

    def matches(self, evt: Event) -> bool:
        if not self.enabled:
            return False
        if self.source != "*" and self.source != evt.source:
            return False
        if self.contact and self.contact.lower() not in evt.contact.lower():
            return False
        if self.keyword and self.keyword.lower() not in evt.text.lower():
            return False
        return True


@dataclass
class DNDState:
    scope: str = ""               # "" = sin DND. "all" | "whatsapp" | "gmail" | "imessage" | "contact:Juan"
    expires_at: str = ""          # ISO timestamp
    whitelist_keywords: list = field(default_factory=list)
    whitelist_contacts: list = field(default_factory=list)

    def active(self) -> bool:
        if not self.scope:
            return False
        if not self.expires_at:
            return True
        try:
            return datetime.fromisoformat(self.expires_at) > datetime.now()
        except Exception:
            return False

    def silences(self, evt: Event) -> bool:
        """¿Este evento queda silenciado por el DND activo?"""
        if not self.active():
            return False
        # Whitelist override
        if any(w.lower() in evt.text.lower() for w in self.whitelist_keywords if w):
            return False
        if any(c.lower() in evt.contact.lower() for c in self.whitelist_contacts if c):
            return False
        # Scope check
        if self.scope == "all":
            return True
        if self.scope == evt.source:
            return True
        if self.scope.startswith("contact:"):
            target = self.scope[8:].lower()
            return target in evt.contact.lower()
        return False


# ── Sources ──────────────────────────────────────────────────────────────────

class EventSource:
    name = "base"
    poll_interval = DEFAULT_POLL_INTERVAL

    def is_available(self) -> bool:
        return False

    def poll(self, last_marker: str) -> tuple[list[Event], str]:
        """Devuelve (eventos_nuevos, nuevo_marker).
        last_marker es opaco — cada source lo interpreta."""
        return [], last_marker


# ─── iMessage ────────────────────────────────────────────────────────────────

class iMessageSource(EventSource):
    """Lee Mac chat.db. Requiere permisos de Full Disk Access en el terminal/Python."""

    name = "imessage"
    poll_interval = DEFAULT_POLL_INTERVAL

    DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"
    APPLE_EPOCH_OFFSET = 978307200  # 2001-01-01 UTC en unix epoch

    def is_available(self) -> bool:
        if os.uname().sysname != "Darwin":
            return False
        if not self.DB_PATH.exists():
            return False
        # Verificar permisos de lectura (Full Disk Access)
        try:
            conn = sqlite3.connect(f"file:{self.DB_PATH}?mode=ro", uri=True, timeout=2)
            conn.execute("SELECT 1 FROM message LIMIT 1").fetchone()
            conn.close()
            return True
        except Exception:
            return False

    def poll(self, last_marker: str) -> tuple[list[Event], str]:
        try:
            last_apple_date = int(last_marker) if last_marker else 0
        except ValueError:
            last_apple_date = 0

        try:
            conn = sqlite3.connect(f"file:{self.DB_PATH}?mode=ro", uri=True, timeout=2)
            cur = conn.cursor()
            # date está en nanoseconds since 2001
            cur.execute(
                """
                SELECT m.ROWID, m.text, m.date, h.id, c.display_name
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                WHERE m.date > ?
                  AND m.is_from_me = 0
                  AND m.text IS NOT NULL
                ORDER BY m.date ASC
                LIMIT 50
                """,
                (last_apple_date,),
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            print(f"[imessage] poll error: {e}")
            return [], last_marker

        events = []
        max_date = last_apple_date
        for rowid, text, date_ns, handle_id, chat_name in rows:
            contact = chat_name or handle_id or "(desconocido)"
            ts = (date_ns / 1e9) + self.APPLE_EPOCH_OFFSET if date_ns else time.time()
            events.append(Event(
                source=self.name,
                contact=str(contact),
                text=(text or "")[:300],
                timestamp=ts,
                raw_id=f"imsg-{rowid}",
            ))
            if date_ns > max_date:
                max_date = date_ns

        return events, str(max_date)


# ─── WhatsApp (vía bridge whatsapp-mcp) ─────────────────────────────────────

class WhatsAppSource(EventSource):
    """Lee SQLite del whatsapp-mcp bridge si está instalado. Best-effort."""

    name = "whatsapp"
    poll_interval = DEFAULT_POLL_INTERVAL

    # Rutas comunes donde el bridge guarda la DB de mensajes (la vendoreada primero)
    SEARCH_PATHS = [
        Path(__file__).resolve().parent.parent / "integrations" / "whatsapp-mcp" / "whatsapp-bridge" / "store" / "messages.db",
        Path.home() / "Documents" / "whatsapp-mcp" / "whatsapp-bridge" / "store" / "messages.db",
        Path.home() / "whatsapp-mcp" / "whatsapp-bridge" / "store" / "messages.db",
        Path.home() / "Documents" / "whatsapp-mcp" / "store" / "messages.db",
    ]

    def __init__(self):
        self._db_path: Optional[Path] = None
        for p in self.SEARCH_PATHS:
            if p.exists():
                self._db_path = p
                break

    def is_available(self) -> bool:
        return self._db_path is not None and self._db_path.exists()

    def _friendly(self, sender: str, chat_jid: str) -> str:
        """JID/LID del remitente → nombre de la agenda de Apple (o número)."""
        try:
            from actions.whatsapp import sender_to_name
            return sender_to_name(sender, chat_jid)
        except Exception:
            return (sender or chat_jid or "(WhatsApp)")

    def poll(self, last_marker: str) -> tuple[list[Event], str]:
        if not self._db_path:
            return [], last_marker
        # El bridge de lharries guarda timestamp como string "YYYY-MM-DD HH:MM:SS"
        # que ordena cronológicamente como texto. El marker es ese string.
        last_ts = last_marker or ""

        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=2)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, timestamp, sender, chat_jid, content
                FROM messages
                WHERE timestamp > ? AND is_from_me = 0 AND content IS NOT NULL AND content != ''
                ORDER BY timestamp ASC
                LIMIT 30
                """,
                (last_ts,),
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            print(f"[whatsapp] poll error (schema mismatch?): {e}")
            return [], last_marker

        events = []
        max_ts = last_ts
        for mid, ts, sender, chat_jid, content in rows:
            ts_str = str(ts) if ts is not None else ""
            contact = self._friendly(sender, chat_jid)
            events.append(Event(
                source=self.name,
                contact=str(contact),
                text=(content or "")[:300],
                timestamp=time.time(),  # epoch aprox para orden interno
                raw_id=f"wa-{mid}",
            ))
            if ts_str > max_ts:
                max_ts = ts_str

        return events, max_ts


# ─── Gmail (vía google_auth) ─────────────────────────────────────────────────

class GmailSource(EventSource):
    name = "gmail"
    poll_interval = GMAIL_POLL_INTERVAL

    def is_available(self) -> bool:
        try:
            from actions.google_auth import is_configured
            return is_configured()
        except Exception:
            return False

    def poll(self, last_marker: str) -> tuple[list[Event], str]:
        last_history_id = last_marker or ""
        try:
            from actions.google_auth import get_service
            svc = get_service("gmail", "v1")
        except Exception as e:
            print(f"[gmail] auth error: {e}")
            return [], last_marker

        try:
            if last_history_id:
                # Delta query (eficiente): listar cambios desde el último historyId
                resp = svc.users().history().list(
                    userId="me",
                    startHistoryId=last_history_id,
                    historyTypes=["messageAdded"],
                ).execute()
                histories = resp.get("history", [])
                msg_ids = []
                for h in histories:
                    for m in h.get("messagesAdded", []):
                        msg_ids.append(m["message"]["id"])
                msg_ids = msg_ids[:10]
                new_history_id = resp.get("historyId", last_history_id)
            else:
                # Primer poll: bookmark sin emitir nada (no spamear con backlog)
                profile = svc.users().getProfile(userId="me").execute()
                return [], profile.get("historyId", "")

            events = []
            for mid in msg_ids:
                try:
                    m = svc.users().messages().get(
                        userId="me", id=mid, format="metadata",
                        metadataHeaders=["From", "Subject"],
                    ).execute()
                    headers = {h["name"]: h["value"] for h in m.get("payload", {}).get("headers", [])}
                    if "UNREAD" not in (m.get("labelIds") or []):
                        continue  # ya leído desde otro device
                    snippet = m.get("snippet", "")[:200]
                    events.append(Event(
                        source=self.name,
                        contact=headers.get("From", "?"),
                        text=f"{headers.get('Subject', '(sin asunto)')} — {snippet}",
                        timestamp=time.time(),
                        raw_id=f"gm-{mid}",
                    ))
                except Exception:
                    continue

            return events, new_history_id
        except Exception as e:
            print(f"[gmail] poll error: {e}")
            return [], last_marker


# ── Engine ───────────────────────────────────────────────────────────────────

class NotificationEngine:
    def __init__(self):
        self.sources: list[EventSource] = []
        self._inject_fn: Callable[[str], None] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._state = self._load_state()
        # Reconstruir Rule/DND desde dicts
        self._rules: list[Rule] = [Rule(**r) for r in self._state.get("rules", [])]
        self._dnd = DNDState(**self._state.get("dnd", {}))
        self._last_markers: dict = self._state.get("last_markers", {})

    # ── Persistencia ──────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if not STATE_FILE.exists():
            return {"rules": [], "dnd": {}, "last_markers": {}}
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"rules": [], "dnd": {}, "last_markers": {}}

    def _save_state(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "rules": [asdict(r) for r in self._rules],
            "dnd": asdict(self._dnd),
            "last_markers": self._last_markers,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Sources ───────────────────────────────────────────────────────

    def register_default_sources(self) -> None:
        for cls in (iMessageSource, WhatsAppSource, GmailSource):
            try:
                src = cls()
                if src.is_available():
                    self.sources.append(src)
                    print(f"[NotifEngine] ✓ source '{src.name}' disponible")
                else:
                    print(f"[NotifEngine] ⏭️  source '{src.name}' no disponible")
            except Exception as e:
                print(f"[NotifEngine] error inicializando {cls.__name__}: {e}")

    # ── Public API: rules + DND ───────────────────────────────────────

    def add_rule(self, name: str, contact: str = "", keyword: str = "", source: str = "*") -> Rule:
        with self._lock:
            r = Rule(
                id=uuid.uuid4().hex[:8],
                name=name,
                contact=contact,
                keyword=keyword,
                source=source,
                enabled=True,
                created=datetime.now().isoformat(timespec="seconds"),
            )
            self._rules.append(r)
            self._save_state()
            return r

    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self._rules)
            self._rules = [r for r in self._rules if not r.id.startswith(rule_id)]
            self._save_state()
            return len(self._rules) < before

    def list_rules(self) -> list[Rule]:
        return list(self._rules)

    def set_dnd(self, scope: str, duration_seconds: int = 3600,
                whitelist_keywords: list | None = None,
                whitelist_contacts: list | None = None) -> DNDState:
        with self._lock:
            expires = (datetime.now() + timedelta(seconds=duration_seconds)).isoformat(timespec="seconds")
            self._dnd = DNDState(
                scope=scope,
                expires_at=expires,
                whitelist_keywords=whitelist_keywords or [],
                whitelist_contacts=whitelist_contacts or [],
            )
            self._save_state()
            return self._dnd

    def clear_dnd(self) -> None:
        with self._lock:
            self._dnd = DNDState()
            self._save_state()

    def get_dnd(self) -> DNDState:
        return self._dnd

    # ── Runner ────────────────────────────────────────────────────────

    def start(self, inject_fn: Callable[[str], None]) -> None:
        """Arranca el watcher en background. inject_fn(text) hace que JARVIS hable."""
        self._inject_fn = inject_fn
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return
        self.register_default_sources()
        if not self.sources:
            print("[NotifEngine] sin sources disponibles, no arranca watcher.")
            return
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="notif-engine")
        self._thread.start()
        print(f"[NotifEngine] 👁️  watcher iniciado con {len(self.sources)} source(s)")

    def stop(self) -> None:
        self._stop.set()

    def _watch_loop(self) -> None:
        next_poll: dict[str, float] = {s.name: 0.0 for s in self.sources}
        while not self._stop.is_set():
            now = time.time()
            new_events: list[Event] = []
            for src in self.sources:
                if now < next_poll[src.name]:
                    continue
                try:
                    last = self._last_markers.get(src.name, "")
                    first_poll = src.name not in self._last_markers
                    events, new_marker = src.poll(last)
                    # Primer poll = solo bookmark. No alertar del backlog histórico.
                    if events and not first_poll:
                        new_events.extend(events)
                    elif events and first_poll:
                        print(f"[NotifEngine] {src.name}: bookmark inicial ({len(events)} msgs viejos ignorados)")
                    if new_marker != last or first_poll:
                        self._last_markers[src.name] = new_marker
                        self._save_state()
                except Exception as e:
                    print(f"[NotifEngine] {src.name} poll exc: {e}")
                next_poll[src.name] = now + src.poll_interval

            if new_events:
                self._process_events(new_events)

            self._stop.wait(2)  # tick rápido para responsividad

    def _process_events(self, events: list[Event]) -> None:
        # Filtrar por reglas y DND
        alerts: list[tuple[Event, Rule | None]] = []
        for evt in events:
            if self._dnd.silences(evt):
                continue
            # Buscar regla que matchee
            matched_rule = None
            for r in self._rules:
                if r.matches(evt):
                    matched_rule = r
                    break
            if matched_rule:
                alerts.append((evt, matched_rule))
            # Sin reglas explícitas: NO alertar (default silent). El usuario
            # tiene que crear reglas explícitas para recibir alertas.

        if not alerts or not self._inject_fn:
            return

        # Batch (no spamear si llegan 5 mensajes juntos)
        alerts = alerts[:MAX_BATCH_PER_POLL]
        text = self._format_alerts(alerts)
        try:
            self._inject_fn(f"[NOTIFICACIÓN INTERNA] Avísame al usuario que: {text}")
        except Exception as e:
            print(f"[NotifEngine] inject falló: {e}")

    def _format_alerts(self, alerts: list[tuple[Event, Rule | None]]) -> str:
        lines = []
        for evt, rule in alerts:
            preview = evt.text[:120]
            if rule:
                lines.append(f"({rule.name}) {evt.contact} [{evt.source}]: {preview}")
            else:
                lines.append(f"{evt.contact} [{evt.source}]: {preview}")
        return " · ".join(lines)


# ── Singleton ────────────────────────────────────────────────────────────────

_ENGINE: NotificationEngine | None = None


def get_engine() -> NotificationEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = NotificationEngine()
    return _ENGINE
