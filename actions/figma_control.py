"""
figma_control.py — Integración con Figma vía REST API (token personal).

  me        verifica el token (datos de tu cuenta)
  info      resumen de un archivo (páginas y frames principales)
  export    renderiza nodos a PNG/SVG/PDF y los descarga
  comments  lista comentarios de un archivo
  comment   publica un comentario
  projects  lista los archivos de un proyecto (project_id)

El token se saca de figma.com → Settings → Security → Personal access tokens.
"""
from __future__ import annotations
import re
from pathlib import Path

import requests
from core.registry import tool

API = "https://api.figma.com/v1"
SAVE_DIR = Path.home() / "Downloads" / "JARVIS" / "figma"


def _token() -> str:
    try:
        from memory.config_manager import cfg
        return cfg("figma_token", "")
    except Exception:
        return ""


def _headers() -> dict:
    return {"X-Figma-Token": _token()}


def _file_key(s: str) -> str:
    """Extrae la file key de una URL de Figma o devuelve s si ya es la key."""
    m = re.search(r"figma\.com/(?:file|design|proto)/([A-Za-z0-9]+)", s or "")
    return m.group(1) if m else (s or "").strip()


def _node_id(s: str) -> str | None:
    m = re.search(r"node-id=([0-9A-Za-z%:-]+)", s or "")
    if m:
        return m.group(1).replace("%3A", ":").replace("-", ":", 1) if "%3A" in m.group(1) else m.group(1).replace("-", ":")
    return None


@tool(
    name='figma_control',
    description="Integración con Figma (REST API). USAR cuando el usuario menciona Figma o pasa una URL de figma.com: 'leé este archivo de Figma', 'exportá este frame a PNG', 'qué comentarios tiene', 'comentá X', 'mostrame los frames'. Acciones: me (probar token), info (estructura del archivo), export (renderizar nodos a PNG/SVG/PDF y descargar), comments (listar), comment (publicar), projects (archivos de un proyecto).",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'me | info | export | comments | comment | projects'},
                    'url': {'type': 'STRING',
                            'description': 'URL del archivo de Figma (o la file key)'},
                    'node_id': {'type': 'STRING',
                                'description': 'export: id del nodo/frame a exportar (o usar una URL '
                                               'con ?node-id=)'},
                    'format': {'type': 'STRING',
                               'description': 'export: png | svg | pdf | jpg (default png)'},
                    'scale': {'type': 'NUMBER',
                              'description': 'export: escala para png/jpg (default 2)'},
                    'message': {'type': 'STRING', 'description': 'comment: texto del comentario'},
                    'project_id': {'type': 'STRING', 'description': 'projects: id del proyecto'}},
     'required': ['action']},
)
def figma_control(parameters: dict, player=None) -> str:
    # Chequeo de credenciales (abre la ventana si falta)
    try:
        from core.credentials import require_key
        ok, msg = require_key("figma")
        if not ok:
            return msg + " (token en figma.com → Settings → Personal access tokens)"
    except Exception:
        if not _token():
            return "Falta el token de Figma (figma_token en el .env)."

    action = (parameters.get("action") or "info").lower().strip()

    try:
        if action in ("me", "whoami", "test"):
            r = requests.get(f"{API}/me", headers=_headers(), timeout=20)
            if r.status_code == 200:
                d = r.json()
                return f"✓ Figma conectado: {d.get('email','?')} ({d.get('handle','')})"
            return f"✗ Token inválido (HTTP {r.status_code}). Revisalo con manage_keys."

        url = parameters.get("url") or parameters.get("file") or ""
        key = _file_key(url)
        if not key and action not in ("projects",):
            return "Pasame la URL (o file key) del archivo de Figma."

        if action == "info":
            r = requests.get(f"{API}/files/{key}", headers=_headers(),
                             params={"depth": 2}, timeout=30)
            if r.status_code != 200:
                return f"✗ No pude leer el archivo (HTTP {r.status_code})."
            doc = r.json()
            if "document" not in doc:
                return (f"📐 '{doc.get('name','archivo')}' — el token conecta pero NO tiene permiso "
                        "para leer el contenido. Regenerá el token en figma.com → Settings → "
                        "Personal access tokens habilitando el scope 'File content' (Read-only) "
                        "(y 'Comments' si querés comentarios). Después actualizalo en el .env.")
            out = [f"📐 {doc.get('name','(archivo)')}"]
            for page in doc.get("document", {}).get("children", [])[:10]:
                out.append(f"  Página: {page.get('name')}")
                for fr in page.get("children", [])[:12]:
                    out.append(f"    • {fr.get('name')} [{fr.get('id')}] ({fr.get('type')})")
            return "\n".join(out)

        if action == "export":
            ids = parameters.get("node_id") or _node_id(url) or parameters.get("ids")
            if not ids:
                return "Decime qué nodo exportar (node_id o una URL con ?node-id=)."
            if isinstance(ids, list):
                ids = ",".join(ids)
            fmt = (parameters.get("format") or "png").lower()
            scale = parameters.get("scale") or 2
            r = requests.get(f"{API}/images/{key}", headers=_headers(),
                             params={"ids": ids, "format": fmt, "scale": scale}, timeout=60)
            data = r.json()
            images = data.get("images", {})
            if not images:
                return f"✗ Figma no devolvió imágenes ({data.get('err') or r.status_code})."
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            saved = []
            for nid, img_url in images.items():
                if not img_url:
                    continue
                content = requests.get(img_url, timeout=60).content
                fn = SAVE_DIR / f"{nid.replace(':','-')}.{fmt}"
                fn.write_bytes(content)
                saved.append(str(fn))
            return f"✓ Exportado: {len(saved)} archivo(s) en {SAVE_DIR}" if saved else "Sin imágenes."

        if action == "comments":
            r = requests.get(f"{API}/files/{key}/comments", headers=_headers(), timeout=20)
            cms = r.json().get("comments", [])
            if not cms:
                return "Sin comentarios."
            return "💬 Comentarios:\n" + "\n".join(
                f"  • {c.get('user',{}).get('handle','?')}: {c.get('message','')[:120]}" for c in cms[:15])

        if action == "comment":
            msg = parameters.get("message") or parameters.get("text")
            if not msg:
                return "Decime el 'message' a publicar."
            r = requests.post(f"{API}/files/{key}/comments", headers=_headers(),
                              json={"message": msg}, timeout=20)
            return "✓ Comentario publicado." if r.status_code in (200, 201) else f"✗ HTTP {r.status_code}"

        if action == "projects":
            pid = parameters.get("project_id")
            if not pid:
                return "Decime el project_id (lo ves en la URL del proyecto en Figma)."
            r = requests.get(f"{API}/projects/{pid}/files", headers=_headers(), timeout=20)
            files = r.json().get("files", [])
            return "📁 Archivos:\n" + "\n".join(f"  • {f.get('name')} (key {f.get('key')})" for f in files[:30]) \
                if files else "Sin archivos."

        return "Acciones: me, info, export, comments, comment, projects."
    except Exception as e:
        return f"Error con Figma: {str(e)[:150]}"
