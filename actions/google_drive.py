"""
google_drive.py — Gestión real de Google Drive vía OAuth.

Acciones: list, search, upload, download, create_folder, delete, share, info.
"""
from __future__ import annotations
from pathlib import Path

from actions.google_auth import get_service
from core.registry import tool


def _format_file(f: dict) -> str:
    icon = "📁" if f.get("mimeType") == "application/vnd.google-apps.folder" else "📄"
    size = f.get("size")
    size_str = ""
    if size:
        n = int(size)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                size_str = f" ({n:.1f}{unit})"
                break
            n /= 1024
    return f"{icon} [{f['id'][:10]}] {f.get('name', '?')}{size_str}"


@tool(
    name='google_drive',
    description='Drive: list, search, upload, download, create_folder, delete, share, info.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'list | search | upload | download | create_folder | '
                                              'delete | share | info'},
                    'folder_id': {'type': 'STRING', 'description': 'ID de la carpeta (default: root)'},
                    'file_id': {'type': 'STRING',
                                'description': 'ID del archivo para download/delete/share/info'},
                    'path': {'type': 'STRING', 'description': 'Ruta local para upload'},
                    'name': {'type': 'STRING', 'description': 'Nombre de la nueva carpeta'},
                    'query': {'type': 'STRING', 'description': 'Término de búsqueda'},
                    'destination': {'type': 'STRING',
                                    'description': 'Carpeta local de destino para download'},
                    'email': {'type': 'STRING', 'description': 'Email para compartir'},
                    'role': {'type': 'STRING', 'description': 'reader | writer | commenter'},
                    'confirm': {'type': 'BOOLEAN', 'description': 'true para confirmar eliminación'}},
     'required': ['action']},
)
def google_drive(parameters: dict, player=None) -> str:
    action = (parameters.get("action") or "list").lower()

    try:
        service = get_service("drive", "v3")
    except FileNotFoundError as e:
        return str(e)
    except RuntimeError as e:
        return str(e)
    except Exception as e:
        return f"Error de autenticación Google: {e}"

    try:
        if action == "list":
            folder_id = parameters.get("folder_id") or "root"
            res = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                pageSize=30,
                fields="files(id, name, mimeType, size, modifiedTime)",
                orderBy="folder,name",
            ).execute()
            files = res.get("files", [])
            if not files:
                return f"Carpeta vacía (id: {folder_id})."
            return f"Contenido ({len(files)}):\n" + "\n".join(_format_file(f) for f in files)

        if action == "search":
            query = parameters.get("query", "")
            if not query:
                return "Error: 'query' obligatorio."
            # Escapar comillas simples para evitar inyección de query
            q_safe = query.replace("'", "\\'")
            res = service.files().list(
                q=f"name contains '{q_safe}' and trashed=false",
                pageSize=20,
                fields="files(id, name, mimeType, size)",
            ).execute()
            files = res.get("files", [])
            if not files:
                return f"Sin coincidencias para '{query}'."
            return f"Encontrados {len(files)}:\n" + "\n".join(_format_file(f) for f in files)

        if action == "upload":
            from googleapiclient.http import MediaFileUpload
            local_path = parameters.get("path", "")
            if not local_path:
                return "Error: 'path' obligatorio (archivo local a subir)."
            p = Path(local_path).expanduser().resolve()
            if not p.exists():
                return f"No existe: {p}"
            body = {"name": p.name}
            if parameters.get("folder_id"):
                body["parents"] = [parameters["folder_id"]]
            media = MediaFileUpload(str(p))
            res = service.files().create(body=body, media_body=media, fields="id, name").execute()
            return f"Subido: {res['name']} (id: {res['id'][:10]})"

        if action == "download":
            from googleapiclient.http import MediaIoBaseDownload
            import io
            fid = parameters.get("file_id", "")
            if not fid:
                return "Error: 'file_id' obligatorio."
            meta = service.files().get(fileId=fid, fields="name, mimeType").execute()
            dest_dir = Path(parameters.get("destination") or Path.home() / "Downloads").expanduser().resolve()
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / meta["name"]
            req = service.files().get_media(fileId=fid)
            buf = io.FileIO(str(dest), "wb")
            downloader = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            buf.close()
            return f"Descargado: {dest}"

        if action == "create_folder":
            name = parameters.get("name", "")
            if not name:
                return "Error: 'name' obligatorio."
            body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
            if parameters.get("folder_id"):
                body["parents"] = [parameters["folder_id"]]
            res = service.files().create(body=body, fields="id, name").execute()
            return f"Carpeta creada: {res['name']} (id: {res['id'][:10]})"

        if action == "delete":
            fid = parameters.get("file_id", "")
            if not fid:
                return "Error: 'file_id' obligatorio."
            if not parameters.get("confirm"):
                return "Eliminación requiere confirm=true."
            service.files().delete(fileId=fid).execute()
            return f"Eliminado: {fid[:10]}"

        if action == "share":
            fid = parameters.get("file_id", "")
            email = parameters.get("email", "")
            role = parameters.get("role", "reader")
            if not fid or not email:
                return "Error: 'file_id' y 'email' obligatorios."
            if role not in ("reader", "writer", "commenter"):
                return "role debe ser: reader | writer | commenter"
            service.permissions().create(
                fileId=fid,
                body={"type": "user", "role": role, "emailAddress": email},
                sendNotificationEmail=True,
            ).execute()
            return f"Compartido con {email} como {role}."

        if action == "info":
            fid = parameters.get("file_id", "")
            if not fid:
                return "Error: 'file_id' obligatorio."
            meta = service.files().get(
                fileId=fid,
                fields="id, name, mimeType, size, createdTime, modifiedTime, owners, webViewLink",
            ).execute()
            owner = (meta.get("owners") or [{}])[0].get("emailAddress", "?")
            return (
                f"Nombre: {meta.get('name')}\n"
                f"ID: {meta.get('id')}\n"
                f"Tipo: {meta.get('mimeType')}\n"
                f"Tamaño: {meta.get('size', '—')}\n"
                f"Dueño: {owner}\n"
                f"Modificado: {meta.get('modifiedTime')}\n"
                f"Link: {meta.get('webViewLink', '—')}"
            )

        return f"Acción '{action}' no soportada."

    except Exception as e:
        return f"Error en google_drive: {e}"
