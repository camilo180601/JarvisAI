"""
file_controller.py — Operaciones de archivos cross-platform.

Soporta: list, create_file, create_folder, delete (papelera), move, copy, rename,
read, write, edit, find, largest, disk_usage, info.
"""
from __future__ import annotations
import os
import shutil
import hashlib
from pathlib import Path
from core.registry import tool

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


def _resolve_shortcut(path: str) -> Path:
    """Resuelve atajos comunes: desktop, downloads, documents, home, pictures."""
    if not path:
        return Path.home()
    p = path.strip().lower()
    home = Path.home()
    shortcuts = {
        "desktop": home / "Desktop",
        "escritorio": home / "Desktop",
        "downloads": home / "Downloads",
        "descargas": home / "Downloads",
        "documents": home / "Documents",
        "documentos": home / "Documents",
        "pictures": home / "Pictures",
        "imagenes": home / "Pictures",
        "imágenes": home / "Pictures",
        "music": home / "Music",
        "música": home / "Music",
        "videos": home / "Movies" if (home / "Movies").exists() else home / "Videos",
        "home": home,
    }
    if p in shortcuts:
        return shortcuts[p]
    return Path(path).expanduser().resolve()


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


@tool(
    name='file_controller',
    description='Archivos/carpetas: list, create_file, create_folder, delete (papelera), move, copy, rename, read, write, edit, find, largest, disk_usage, info.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'list | create_file | create_folder | delete (mueve a '
                                              'papelera) | move | copy | rename | read | write | edit '
                                              '| find | largest | disk_usage | organize_desktop | '
                                              'info'},
                    'path': {'type': 'STRING',
                             'description': 'File/folder path or shortcut: desktop, downloads, '
                                            'documents, home'},
                    'destination': {'type': 'STRING', 'description': 'Destination path for move/copy'},
                    'new_name': {'type': 'STRING', 'description': 'New name for rename'},
                    'content': {'type': 'STRING', 'description': 'Content for create_file/write'},
                    'name': {'type': 'STRING', 'description': 'File name to search for'},
                    'extension': {'type': 'STRING',
                                  'description': 'File extension to search (e.g. .pdf)'},
                    'count': {'type': 'INTEGER', 'description': 'Number of results for largest'},
                    'old_text': {'type': 'STRING', 'description': 'Texto a reemplazar (para edit)'},
                    'new_text': {'type': 'STRING',
                                 'description': 'Nuevo texto o contenido (para edit)'},
                    'mode': {'type': 'STRING',
                             'description': 'replace | append | prepend | overwrite (para edit)'},
                    'confirm': {'type': 'BOOLEAN', 'description': 'true para confirmar eliminaciones'}},
     'required': ['action']},
)
def file_controller(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "").lower()
    path_str = parameters.get("path", "")
    target = _resolve_shortcut(path_str) if path_str else Path.home()

    try:
        if action == "list":
            if not target.exists():
                return f"La ruta '{target}' no existe."
            if not target.is_dir():
                return f"'{target}' no es un directorio."
            items = sorted(target.iterdir())
            lines = []
            for item in items[:50]:
                kind = "📁" if item.is_dir() else "📄"
                size = "" if item.is_dir() else f" ({_human_size(item.stat().st_size)})"
                lines.append(f"{kind} {item.name}{size}")
            extra = f"\n...y {len(items)-50} más." if len(items) > 50 else ""
            return f"Contenido de {target}:\n" + "\n".join(lines) + extra

        if action == "create_file":
            content = parameters.get("content", "")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Archivo creado: {target}"

        if action == "create_folder":
            target.mkdir(parents=True, exist_ok=True)
            return f"Carpeta creada: {target}"

        if action == "delete":
            if not target.exists():
                return f"No existe: {target}"
            if send2trash:
                send2trash(str(target))
                return f"Enviado a la papelera: {target.name}"
            else:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                return f"Eliminado permanentemente: {target.name} (send2trash no instalado)"

        if action == "move":
            dest = _resolve_shortcut(parameters.get("destination", ""))
            if dest.is_dir():
                dest = dest / target.name
            shutil.move(str(target), str(dest))
            return f"Movido a: {dest}"

        if action == "copy":
            dest = _resolve_shortcut(parameters.get("destination", ""))
            if dest.is_dir():
                dest = dest / target.name
            if target.is_dir():
                shutil.copytree(str(target), str(dest))
            else:
                shutil.copy2(str(target), str(dest))
            return f"Copiado a: {dest}"

        if action == "rename":
            new_name = parameters.get("new_name", "")
            if not new_name:
                return "Error: falta 'new_name' para rename."
            new_path = target.parent / new_name
            target.rename(new_path)
            return f"Renombrado a: {new_path.name}"

        if action == "read":
            if not target.is_file():
                return f"No es archivo o no existe: {target}"
            try:
                content = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return f"Archivo binario (no se puede leer como texto): {target.name}"
            if len(content) > 4000:
                content = content[:4000] + "\n...[contenido truncado]"
            return f"Contenido de {target.name}:\n{content}"

        if action == "write":
            content = parameters.get("content", "")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Escrito {len(content)} caracteres en {target.name}"

        if action == "edit":
            if not target.is_file():
                return f"Archivo no existe: {target}"
            mode = (parameters.get("mode") or "replace").lower()
            current = target.read_text(encoding="utf-8")
            if mode == "replace":
                old = parameters.get("old_text", "")
                new = parameters.get("new_text", "")
                if old not in current:
                    return f"No se encontró '{old[:50]}' en el archivo."
                target.write_text(current.replace(old, new), encoding="utf-8")
                return f"Reemplazado en {target.name}"
            elif mode == "append":
                target.write_text(current + parameters.get("new_text", ""), encoding="utf-8")
                return f"Agregado al final de {target.name}"
            elif mode == "prepend":
                target.write_text(parameters.get("new_text", "") + current, encoding="utf-8")
                return f"Prepuesto a {target.name}"
            elif mode == "overwrite":
                target.write_text(parameters.get("new_text", ""), encoding="utf-8")
                return f"Sobrescrito {target.name}"
            return f"Modo de edición desconocido: {mode}"

        if action == "find":
            name = (parameters.get("name") or "").lower()
            ext = (parameters.get("extension") or "").lower().lstrip(".")
            if not name and not ext:
                return "Error: especifica 'name' o 'extension' para find."
            search_root = target if target.is_dir() else Path.home() / "Desktop"
            matches = []
            for p in search_root.rglob("*"):
                if len(matches) >= 30:
                    break
                if not p.is_file():
                    continue
                if name and name not in p.name.lower():
                    continue
                if ext and not p.suffix.lower().lstrip(".") == ext:
                    continue
                matches.append(str(p))
            if not matches:
                return f"No se encontraron archivos en {search_root}."
            return f"Encontrados {len(matches)}:\n" + "\n".join(matches[:20])

        if action == "largest":
            count = int(parameters.get("count", 10))
            search_root = target if target.is_dir() else Path.home()
            files = []
            for p in search_root.rglob("*"):
                if p.is_file():
                    try:
                        files.append((p.stat().st_size, p))
                    except Exception:
                        pass
            files.sort(reverse=True)
            top = files[:count]
            return "Archivos más grandes:\n" + "\n".join(
                f"{_human_size(sz)}  {p}" for sz, p in top
            )

        if action == "disk_usage":
            usage = shutil.disk_usage(str(target if target.exists() else Path.home()))
            return (
                f"Disco en {target}:\n"
                f"  Total: {_human_size(usage.total)}\n"
                f"  Usado: {_human_size(usage.used)} ({usage.used*100/usage.total:.1f}%)\n"
                f"  Libre: {_human_size(usage.free)}"
            )

        if action == "info":
            if not target.exists():
                return f"No existe: {target}"
            st = target.stat()
            kind = "Carpeta" if target.is_dir() else "Archivo"
            size = _human_size(st.st_size) if target.is_file() else "—"
            return (
                f"{kind}: {target}\n"
                f"  Tamaño: {size}\n"
                f"  Modificado: {st.st_mtime}\n"
                f"  Permisos: {oct(st.st_mode)[-3:]}"
            )

        return f"Acción '{action}' no soportada. Usa: list, create_file, create_folder, delete, move, copy, rename, read, write, edit, find, largest, disk_usage, info."

    except PermissionError as e:
        return f"Sin permisos: {e}"
    except FileNotFoundError as e:
        return f"No encontrado: {e}"
    except Exception as e:
        return f"Error en file_controller: {e}"
