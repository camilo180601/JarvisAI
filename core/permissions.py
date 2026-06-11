"""
permissions.py — Onboarding de permisos de macOS (TCC) para JARVIS.

macOS NO tiene un "permitir todo" único: cada permiso es por categoría y por app,
y la mayoría solo los concede el usuario en Ajustes del Sistema. Lo que hacemos:

  • Disparar los prompts que SÍ se pueden disparar por código:
      - Micrófono            (abrimos un stream corto con sounddevice)
      - Grabación de pantalla (Quartz.CGRequestScreenCaptureAccess)
      - Automatización        (mandamos un Apple Event benigno a cada app objetivo)
  • Abrir el panel EXACTO de Ajustes para los que requieren toggle manual:
      - Accesibilidad         (pyautogui / control de teclado-mouse-ventanas)
      - Acceso Total al Disco (leer ~/Library/Messages/chat.db p/ notificaciones)

Los permisos se asignan al proceso que llama (hoy: el Python de .venv lanzado desde
tu Terminal). Si después empaquetás como .app, hay que volver a concederlos a JARVIS.app.

Uso directo:  .venv/bin/python -m core.permissions
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
FLAG = Path.home() / ".jarvis" / ".permissions_onboarded"

# anchors del esquema x-apple.systempreferences (estable desde macOS Ventura)
_PANES = {
    "screen":        "Privacy_ScreenCapture",
    "accessibility": "Privacy_Accessibility",
    "automation":    "Privacy_Automation",
    "fulldisk":      "Privacy_AllFiles",
    "microphone":    "Privacy_Microphone",
    "files":         "Privacy_FilesAndFolders",
}

# Apps a las que JARVIS les manda Apple Events. (Adobe se omite del barrido para
# no lanzar apps pesadas; piden permiso solo y de inmediato al primer uso real.)
_AUTOMATION_LIGHT = ["System Events", "Finder"]
_AUTOMATION_DEEP = ["Notes", "Reminders", "Messages", "Google Chrome", "Safari"]


def open_pane(key: str) -> None:
    anchor = _PANES.get(key)
    if anchor:
        subprocess.run(["open", f"x-apple.systempreferences:com.apple.preference.security?{anchor}"],
                       capture_output=True)


# ───────────────────────── prompts disparables ─────────────────────────

def request_microphone() -> str:
    try:
        import sounddevice as sd
        sd.rec(int(0.2 * 8000), samplerate=8000, channels=1)
        sd.wait()
        return "micrófono: prompt disparado"
    except Exception as e:
        open_pane("microphone")
        return f"micrófono: no pude disparar ({str(e)[:60]}) — abrí el panel manualmente"


def check_screen_recording() -> bool:
    try:
        import Quartz
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def request_screen_recording() -> str:
    try:
        import Quartz
        if Quartz.CGPreflightScreenCaptureAccess():
            return "grabación de pantalla: ya concedida ✓"
        Quartz.CGRequestScreenCaptureAccess()  # dispara el prompt del sistema
        open_pane("screen")
        return "grabación de pantalla: prompt disparado (activá la app en el panel)"
    except Exception:
        open_pane("screen")
        return "grabación de pantalla: abrí el panel y activá la app"


def trigger_automation(apps: list[str]) -> list[str]:
    """Manda un Apple Event benigno a cada app → macOS muestra el prompt de Automatización."""
    out = []
    for app in apps:
        try:
            r = subprocess.run(
                ["osascript", "-e", f'tell application "{app}" to get name'],
                capture_output=True, text=True, timeout=15)
            ok = r.returncode == 0
            out.append(f"  {'✓' if ok else '…'} {app}")
        except Exception:
            out.append(f"  … {app} (sin respuesta)")
    return out


def check_full_disk_access() -> bool:
    """Probamos leyendo la DB de Mensajes (requiere Acceso Total al Disco)."""
    db = Path.home() / "Library" / "Messages" / "chat.db"
    if not db.exists():
        return False
    try:
        with open(db, "rb") as f:
            f.read(16)
        return True
    except Exception:
        return False


# ───────────────────────── orquestación ─────────────────────────

def request_all(player=None, deep: bool = False) -> str:
    if not IS_MAC:
        return "Los permisos de macOS no aplican en este sistema."

    def log(m):
        if player:
            player.write_log(m)

    lines = ["🔐 Configurando permisos de macOS…", f"Proceso: {sys.executable}", ""]

    log("🔐 Micrófono…")
    lines.append("• " + request_microphone())

    log("🔐 Grabación de pantalla…")
    lines.append("• " + request_screen_recording())

    log("🔐 Automatización (apps)…")
    apps = _AUTOMATION_LIGHT + (_AUTOMATION_DEEP if deep else [])
    lines.append("• Automatización — Apple Events enviados:")
    lines.extend(trigger_automation(apps))
    if not deep:
        lines.append("  (Notas/Recordatorios/Mensajes/Chrome y Adobe piden permiso al primer uso)")

    # Manual: Accesibilidad
    open_pane("accessibility")
    lines.append("• Accesibilidad: abrí el panel y activá la app (necesario para mover el mouse/"
                 "teclado, clic visual y control de ventanas).")

    # Manual: Acceso Total al Disco
    fda = check_full_disk_access()
    if fda:
        lines.append("• Acceso Total al Disco: ya concedido ✓")
    else:
        open_pane("fulldisk")
        lines.append("• Acceso Total al Disco: activá la app en el panel (necesario para leer "
                     "iMessage/WhatsApp y las notificaciones proactivas).")

    lines.append("")
    lines.append("⚠️ Tras activar los toggles manuales, reiniciá JARVIS para que tomen efecto.")
    lines.append("⚠️ Buscá en las listas: " + Path(sys.executable).name + " (o tu Terminal).")

    try:
        FLAG.parent.mkdir(parents=True, exist_ok=True)
        FLAG.write_text("done", encoding="utf-8")
    except Exception:
        pass

    return "\n".join(lines)


def status_report() -> str:
    if not IS_MAC:
        return "No es macOS."
    return ("Permisos (lo que se puede verificar):\n"
            f"  • Grabación de pantalla: {'✓' if check_screen_recording() else '✗ / desconocido'}\n"
            f"  • Acceso Total al Disco: {'✓' if check_full_disk_access() else '✗'}\n"
            "  (Automatización/Accesibilidad/Micrófono macOS no los expone para consulta directa;\n"
            "   se confirman al usar la función correspondiente.)")


def onboard_if_first_run(player=None) -> str | None:
    """Llamado en el arranque: corre el onboarding solo la primera vez."""
    if not IS_MAC or FLAG.exists():
        return None
    return request_all(player=player, deep=False)


if __name__ == "__main__":
    deep = "--deep" in sys.argv
    print(request_all(deep=deep))
