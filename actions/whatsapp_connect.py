"""
whatsapp_connect.py — Orquesta el ciclo de vida del bridge de WhatsApp.

"conectar WhatsApp" por voz → abre una terminal con el QR para escanear.

Arquitectura (whatsapp-mcp de lharries):
  - Bridge Go: conexión WhatsApp + REST en localhost:8080 + escribe messages.db.
    Debe correr siempre. Necesita escaneo de QR una vez.
  - MCP server Python: lo lanza JARVIS (mcp_client) cuando se activa en config.

Acciones:
  connect — verifica prereqs, lanza el bridge en terminal visible (QR), activa MCP
  status  — ¿bridge corriendo? ¿logueado?
  stop    — mata el bridge
"""
from __future__ import annotations
import json
import socket
import subprocess
import sys
from pathlib import Path
from core.registry import tool

HOME = Path.home()
BASE_DIR = Path(__file__).resolve().parent.parent
# Vendoreado DENTRO del proyecto (integrations/); fallback a la ubicación vieja.
REPO = BASE_DIR / "integrations" / "whatsapp-mcp"
if not REPO.exists() and (HOME / "Documents" / "whatsapp-mcp").exists():
    REPO = HOME / "Documents" / "whatsapp-mcp"
BRIDGE_DIR = REPO / "whatsapp-bridge"
MESSAGES_DB = BRIDGE_DIR / "store" / "messages.db"
BRIDGE_PORT = 8080

MCP_CONFIG = BASE_DIR / "config" / "mcp_servers.json"


def _bridge_running() -> bool:
    """¿Hay algo escuchando en el puerto REST del bridge?"""
    try:
        with socket.create_connection(("localhost", BRIDGE_PORT), timeout=1):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def _check_prereqs() -> tuple[bool, str]:
    import shutil
    # go en PATH o en homebrew
    go = shutil.which("go") or ("/opt/homebrew/bin/go" if Path("/opt/homebrew/bin/go").exists() else None)
    if not go:
        return False, "Falta Go. Instalá con: brew install go"
    if not BRIDGE_DIR.exists():
        return False, f"No está clonado el repo. git clone https://github.com/lharries/whatsapp-mcp.git en {REPO.parent}"
    return True, go


def _write_launch_script(go_path: str) -> Path:
    """Escribe un script ejecutable que arranca el bridge (evita quoting hell)."""
    go_dir = str(Path(go_path).parent)
    script_path = HOME / ".jarvis" / "whatsapp_bridge_launch.command"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "#!/bin/bash\n"
        f'export PATH="{go_dir}:$PATH"\n'
        f'cd "{BRIDGE_DIR}"\n'
        'echo "📱 JARVIS — Conectando WhatsApp. Escaneá el QR de abajo:"\n'
        'echo "(WhatsApp → Ajustes → Dispositivos vinculados → Vincular dispositivo)"\n'
        'echo ""\n'
        "go run main.go\n"
    )
    script_path.write_text(content, encoding="utf-8")
    script_path.chmod(0o755)
    return script_path


def _launch_bridge_terminal(go_path: str) -> tuple[bool, str]:
    """Abre una terminal visible corriendo el bridge (muestra el QR)."""
    go_dir = str(Path(go_path).parent)

    if sys.platform == "darwin":
        # Script .command que Terminal.app abre directo — sin problemas de comillas
        script = _write_launch_script(go_path)
        try:
            subprocess.run(["open", "-a", "Terminal", str(script)],
                           check=True, capture_output=True)
            return True, "Terminal abierta con el QR."
        except Exception as e:
            return False, f"No pude abrir Terminal: {e}"

    elif sys.platform.startswith("linux"):
        bridge_cmd = f'cd "{BRIDGE_DIR}" && export PATH="{go_dir}:$PATH" && go run main.go'
        import shutil
        for term in ("gnome-terminal", "konsole", "xterm", "x-terminal-emulator"):
            if shutil.which(term):
                try:
                    if term == "gnome-terminal":
                        subprocess.Popen([term, "--", "bash", "-c", f"{bridge_cmd}; exec bash"])
                    else:
                        subprocess.Popen([term, "-e", f"bash -c '{bridge_cmd}; exec bash'"])
                    return True, f"Terminal ({term}) abierta con el QR."
                except Exception:
                    continue
        return False, "No encontré un emulador de terminal. Corré el bridge manualmente."

    elif sys.platform == "win32":
        try:
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", bridge_cmd], shell=True)
            return True, "Ventana CMD abierta con el QR."
        except Exception as e:
            return False, f"No pude abrir CMD: {e}"

    return False, f"SO no soportado: {sys.platform}"


def _enable_in_config() -> bool:
    """Flip whatsapp disabled:false en mcp_servers.json."""
    if not MCP_CONFIG.exists():
        return False
    try:
        cfg = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
        if "whatsapp" in (cfg.get("servers") or {}):
            cfg["servers"]["whatsapp"]["disabled"] = False
            MCP_CONFIG.write_text(json.dumps(cfg, indent=4, ensure_ascii=False), encoding="utf-8")
            return True
    except Exception:
        pass
    return False


@tool(
    name='whatsapp_connect',
    description="Conecta WhatsApp: abre una terminal con el QR para escanear y activa las tools de WhatsApp en vivo. USAR cuando el usuario dice 'conectá WhatsApp', 'vinculá WhatsApp', 'activá WhatsApp'. action=connect (default) abre el QR; status verifica si está conectado; stop apaga el bridge. Tras escanear el QR, el usuario dice 'recargar whatsapp' (mandar action=connect de nuevo) para activar las herramientas.",
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING', 'description': 'connect (default) | status | stop'}},
     'required': []},
)
def whatsapp_connect(parameters: dict, player=None, speak=None) -> str:
    action = (parameters.get("action") or "connect").lower()

    if action == "status":
        running = _bridge_running()
        db_exists = MESSAGES_DB.exists()
        prereq_ok, _ = _check_prereqs()
        return (
            f"WhatsApp bridge: {'🟢 corriendo' if running else '🔴 apagado'}\n"
            f"  DB de mensajes: {'existe' if db_exists else 'no creada aún'}\n"
            f"  Prerequisitos: {'OK' if prereq_ok else 'faltan'}"
        )

    if action == "stop":
        try:
            # matar procesos del bridge (go run / el binario compilado)
            subprocess.run(["pkill", "-f", "whatsapp-bridge"], capture_output=True)
            subprocess.run(["pkill", "-f", "go run main.go"], capture_output=True)
            return "Bridge de WhatsApp detenido."
        except Exception as e:
            return f"No pude detener el bridge: {e}"

    # action == "connect"
    if _bridge_running():
        # Ya está corriendo → solo activar MCP
        _enable_in_config()
        if player:
            player.write_log("✅ Bridge de WhatsApp ya estaba corriendo.")
        return ("WhatsApp ya está conectado (el bridge corre en puerto 8080). "
                "Activé las tools MCP. Si recién lo escaneaste, decime 'recargar whatsapp'.")

    ok, go_or_msg = _check_prereqs()
    if not ok:
        return f"No puedo conectar WhatsApp: {go_or_msg}"

    # Flujo nuevo: bridge en background + QR en VENTANA de la UI (no Terminal).
    try:
        from core import whatsapp_bridge as wb
        if player:
            player.write_log("📱 Conectando WhatsApp (el QR aparece en una ventana si hace falta)...")
        r = wb.connect_with_ui()
        _enable_in_config()
        if r == "ya estaba conectado":
            return "WhatsApp ya está conectado."
        return ("📱 Conectando WhatsApp. Si hay que vincular, se abre una ventana con el QR: "
                "escanealo desde WhatsApp → Ajustes → Dispositivos vinculados. "
                "Si ya estabas vinculado, conecta solo en unos segundos.")
    except Exception as e:
        # Fallback: el flujo viejo por Terminal
        if player:
            player.write_log(f"📱 UI de QR no disponible ({str(e)[:40]}); abro Terminal...")
        launched, msg = _launch_bridge_terminal(go_or_msg)
        if not launched:
            return f"Error lanzando el bridge: {msg}"
        _enable_in_config()
        return ("📱 Abrí una terminal con el QR. Escanealo: WhatsApp → Ajustes → "
                "Dispositivos vinculados → Vincular dispositivo.")
