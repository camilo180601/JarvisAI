"""
terminal_agent.py — Ejecuta comandos de shell cross-platform.

Windows: PowerShell o CMD según parámetro 'shell'.
Mac/Linux: bash o zsh según parámetro 'shell' (default: bash).
"""
import os
import sys
import subprocess
from core.registry import tool

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


@tool(
    name='terminal_agent',
    description='Ejecuta comandos shell (powershell/cmd en Windows, bash/zsh en Mac/Linux). Comodín universal si no hay tool específica.',
    parameters={'type': 'OBJECT',
     'properties': {'command': {'type': 'STRING', 'description': 'El comando exacto a ejecutar'},
                    'shell': {'type': 'STRING',
                              'description': 'Shell a usar: powershell (default) o cmd'},
                    'timeout': {'type': 'INTEGER',
                                'description': 'Timeout en segundos (default: 120, max: 600)'},
                    'working_directory': {'type': 'STRING',
                                          'description': 'Directorio de trabajo para el comando '
                                                         '(opcional)'}},
     'required': ['command']},
)
def terminal_agent(parameters: dict, player=None) -> str:
    """Ejecuta cualquier comando en la terminal del SO."""
    command = parameters.get("command", "")
    shell_type = parameters.get("shell", "").lower().strip()
    timeout_sec = int(parameters.get("timeout", 120))
    working_dir = parameters.get("working_directory", None)

    if not command:
        return "No se proporcionó ningún comando para ejecutar."

    timeout_sec = max(10, min(timeout_sec, 600))

    try:
        if IS_WINDOWS:
            shell_type = shell_type or "powershell"
            if shell_type == "cmd":
                cmd_args = ["cmd", "/c", command]
            else:
                cmd_args = [
                    "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-Command",
                    f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}"
                ]
            extra_kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW}
        else:
            # Mac / Linux
            shell_bin = shell_type or "bash"
            if shell_bin not in ("bash", "zsh", "sh"):
                shell_bin = "bash"
            cmd_args = [shell_bin, "-c", command]
            extra_kwargs = {}

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=working_dir,
            encoding="utf-8",
            errors="replace",
            env=env,
            **extra_kwargs,
        )

        output = (result.stdout or "").strip()
        error = (result.stderr or "").strip()

        if result.returncode == 0:
            if output:
                if len(output) > 3000:
                    output = output[:3000] + "\n...[Salida truncada]"
                return f"Comando ejecutado exitosamente:\n{output}"
            return "Comando ejecutado exitosamente (sin salida)."
        else:
            combined = ""
            if error:
                combined += f"STDERR:\n{error}\n"
            if output:
                combined += f"STDOUT:\n{output}"
            if not combined:
                combined = "(sin salida de error)"
            return f"El comando finalizó con código {result.returncode}:\n{combined}"

    except subprocess.TimeoutExpired:
        return f"Error: El comando excedió el timeout de {timeout_sec} segundos y fue terminado."
    except FileNotFoundError as e:
        return f"Error: No se encontró el ejecutable para shell '{shell_type}': {e}"
    except Exception as e:
        return f"Excepción ejecutando terminal: {str(e)}"
