"""
desktop.py — Operaciones de escritorio cross-platform.

Acciones: wallpaper, organize (por tipo o fecha), clean (vacía papelera/temp),
list (qué hay en el escritorio), stats (resumen).
"""
from __future__ import annotations
import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from collections import Counter
from core.registry import tool

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


def _desktop_path() -> Path:
    """Ruta del escritorio cross-platform."""
    return Path.home() / "Desktop"


def _set_wallpaper(image_path: str) -> tuple[bool, str]:
    p = Path(image_path).expanduser().resolve()
    if not p.exists():
        return False, f"No existe: {p}"

    if sys.platform == "darwin":
        try:
            script = (
                f'tell application "System Events" to set picture of every desktop to '
                f'POSIX file "{p}"'
            )
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            return True, f"Wallpaper cambiado a {p.name}."
        except Exception as e:
            return False, f"Error wallpaper (Mac): {e}"
    elif sys.platform == "win32":
        try:
            import ctypes
            SPI_SETDESKWALLPAPER = 0x14
            ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, str(p), 3)
            return True, f"Wallpaper cambiado a {p.name}."
        except Exception as e:
            return False, f"Error wallpaper (Windows): {e}"
    else:
        # Linux con GNOME
        if shutil.which("gsettings"):
            try:
                subprocess.run(
                    ["gsettings", "set", "org.gnome.desktop.background", "picture-uri",
                     f"file://{p}"], check=True, capture_output=True,
                )
                return True, f"Wallpaper cambiado a {p.name}."
            except Exception as e:
                return False, str(e)
        return False, "Sin gsettings disponible (Linux)."


def _download_image(url: str, dest: Path) -> tuple[bool, str]:
    try:
        import urllib.request
        dest.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, dest)
        return True, str(dest)
    except Exception as e:
        return False, str(e)


def _categorize(suffix: str) -> str:
    suffix = suffix.lower().lstrip(".")
    categories = {
        "Imagenes": {"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "heic"},
        "Documentos": {"pdf", "doc", "docx", "txt", "rtf", "odt", "md"},
        "Hojas": {"xls", "xlsx", "csv", "ods"},
        "Presentaciones": {"ppt", "pptx", "odp", "key"},
        "Videos": {"mp4", "mov", "avi", "mkv", "webm", "wmv", "flv"},
        "Audio": {"mp3", "wav", "flac", "ogg", "m4a", "aac"},
        "Archivos": {"zip", "rar", "7z", "tar", "gz", "bz2"},
        "Codigo": {"py", "js", "ts", "html", "css", "java", "cpp", "c", "go", "rs", "sh"},
        "Apps": {"app", "exe", "dmg", "pkg", "deb"},
    }
    for cat, exts in categories.items():
        if suffix in exts:
            return cat
    return "Otros"


def _organize_by_type(desktop: Path) -> str:
    moved = 0
    for item in list(desktop.iterdir()):
        if item.is_dir() or item.name.startswith("."):
            continue
        cat = _categorize(item.suffix)
        target_dir = desktop / cat
        target_dir.mkdir(exist_ok=True)
        try:
            shutil.move(str(item), str(target_dir / item.name))
            moved += 1
        except Exception:
            pass
    return f"Escritorio organizado por tipo: {moved} archivos movidos."


def _organize_by_date(desktop: Path) -> str:
    moved = 0
    for item in list(desktop.iterdir()):
        if item.is_dir() or item.name.startswith("."):
            continue
        try:
            ts = item.stat().st_mtime
            folder = datetime.fromtimestamp(ts).strftime("%Y-%m")
            target_dir = desktop / folder
            target_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(target_dir / item.name))
            moved += 1
        except Exception:
            pass
    return f"Escritorio organizado por fecha: {moved} archivos movidos."


def _clean_screenshots(desktop: Path) -> str:
    """Mueve a la papelera screenshots típicos del escritorio."""
    if send2trash is None:
        return "send2trash no instalado."
    patterns_mac = ("Screen Shot", "Screenshot", "Captura")
    count = 0
    for item in desktop.iterdir():
        if item.is_file() and any(p in item.name for p in patterns_mac):
            try:
                send2trash(str(item))
                count += 1
            except Exception:
                pass
    return f"Limpieza: {count} screenshots enviados a la papelera."


def _list_desktop(desktop: Path) -> str:
    items = sorted(desktop.iterdir())
    if not items:
        return "Escritorio vacío."
    lines = []
    for i in items[:30]:
        if i.name.startswith("."):
            continue
        icon = "📁" if i.is_dir() else "📄"
        lines.append(f"{icon} {i.name}")
    extra = f"\n...y {len(items)-30} más" if len(items) > 30 else ""
    return f"Escritorio ({len(items)}):\n" + "\n".join(lines) + extra


def _stats_desktop(desktop: Path) -> str:
    total = 0
    size_total = 0
    by_cat: Counter = Counter()
    for item in desktop.rglob("*"):
        if item.is_file() and not item.name.startswith("."):
            total += 1
            try:
                size_total += item.stat().st_size
            except Exception:
                pass
            by_cat[_categorize(item.suffix)] += 1

    def human(n):
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f}{unit}"
            n /= 1024
        return f"{n:.1f}TB"

    top = "\n".join(f"  {cat}: {count}" for cat, count in by_cat.most_common(5))
    return (
        f"Escritorio: {total} archivos, {human(size_total)} en total.\n"
        f"Top categorías:\n{top}"
    )


@tool(
    name='desktop_control',
    description='Escritorio: wallpaper, organize, clean, list, stats. Usa search_name+search_path para auto-encontrar archivos.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'wallpaper | wallpaper_url | organize | clean | list | '
                                              'stats | task'},
                    'path': {'type': 'STRING', 'description': 'Image path for wallpaper'},
                    'url': {'type': 'STRING', 'description': 'Image URL for wallpaper_url'},
                    'mode': {'type': 'STRING', 'description': 'by_type or by_date for organize'},
                    'task': {'type': 'STRING', 'description': 'Natural language desktop task'},
                    'search_name': {'type': 'STRING',
                                    'description': 'Filename to search for in a directory (auto-finds '
                                                   'full path)'},
                    'search_path': {'type': 'STRING',
                                    'description': 'Directory to search: desktop, downloads, '
                                                   'documents, pictures, home (default: desktop)'}},
     'required': ['action']},
)
def desktop_control(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "list").lower()
    desktop = _desktop_path()

    if not desktop.exists():
        return f"Escritorio no encontrado en {desktop}."

    if action == "wallpaper":
        path = parameters.get("path") or parameters.get("search_name") or ""
        if parameters.get("search_name"):
            from actions.file_controller import _resolve_shortcut
            base = _resolve_shortcut(parameters.get("search_path") or "desktop")
            matches = list(base.rglob(parameters["search_name"]))
            if not matches:
                return f"No se encontró '{parameters['search_name']}' en {base}."
            path = str(matches[0])
        if not path:
            return "Error: falta 'path' o 'search_name' para wallpaper."
        ok, msg = _set_wallpaper(path)
        return msg

    if action == "wallpaper_url":
        url = parameters.get("url", "")
        if not url:
            return "Error: falta 'url'."
        dest = Path.home() / "Pictures" / "JARVIS_Wallpaper" / "downloaded.jpg"
        ok, info = _download_image(url, dest)
        if not ok:
            return f"Error descargando: {info}"
        ok, msg = _set_wallpaper(str(dest))
        return msg

    if action == "organize":
        mode = (parameters.get("mode") or "by_type").lower()
        if mode == "by_date":
            return _organize_by_date(desktop)
        return _organize_by_type(desktop)

    if action == "clean":
        return _clean_screenshots(desktop)

    if action == "list":
        return _list_desktop(desktop)

    if action == "stats":
        return _stats_desktop(desktop)

    return f"Acción '{action}' no soportada. Usa: wallpaper, wallpaper_url, organize, clean, list, stats."
