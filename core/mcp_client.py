"""
mcp_client.py — Cliente MCP (Model Context Protocol) para JARVIS.

Permite que JARVIS use cualquier servidor MCP (filesystem, WhatsApp, Spotify, etc.)
como si fueran tools nativas. Cada server corre en subprocess separado y se
comunica vía JSON-RPC 2.0 sobre stdio.

Flow:
  1. Lee config/mcp_servers.json
  2. Por cada server: spawn subprocess + initialize + tools/list
  3. Traduce las tools MCP al formato Gemini con prefijo mcp__<server>__<tool>
  4. Al invocar, rutea por JSON-RPC al server correcto

Las tools quedan disponibles en TOOL_DECLARATIONS automáticamente.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "mcp_servers.json"
MCP_PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT = 30


# ── JSON Schema → Gemini schema translator ───────────────────────────────────

_TYPE_MAP = {
    "object": "OBJECT",
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "null": "STRING",  # Gemini no soporta null directo, lo tratamos como string opcional
}


def _translate_schema(schema: dict | None) -> dict:
    """Convierte JSON Schema (MCP) a schema de Gemini function declaration."""
    if not isinstance(schema, dict):
        return {"type": "OBJECT", "properties": {}, "required": []}

    out: dict = {}
    t = schema.get("type")
    if isinstance(t, list):
        # union types — escoger el primero no-null
        t = next((x for x in t if x != "null"), "string")
    out["type"] = _TYPE_MAP.get(t, "STRING")

    if "description" in schema:
        out["description"] = schema["description"]

    if out["type"] == "OBJECT":
        props_in = schema.get("properties", {}) or {}
        props_out = {}
        for pname, pdef in props_in.items():
            props_out[pname] = _translate_schema(pdef)
        out["properties"] = props_out
        if "required" in schema and isinstance(schema["required"], list):
            out["required"] = schema["required"]
        else:
            out["required"] = []

    if out["type"] == "ARRAY":
        items = schema.get("items", {})
        out["items"] = _translate_schema(items) if items else {"type": "STRING"}

    if "enum" in schema:
        out["enum"] = schema["enum"]

    return out


def _mcp_tool_to_gemini_decl(server_name: str, mcp_tool: dict) -> dict:
    """Convierte una tool MCP al formato de TOOL_DECLARATIONS de Gemini."""
    tool_name = mcp_tool.get("name", "")
    qualified_name = f"mcp__{server_name}__{tool_name}"
    desc_parts = [mcp_tool.get("description", "")]
    desc_parts.append(f"(via MCP server '{server_name}')")
    return {
        "name": qualified_name,
        "description": " ".join(desc_parts).strip(),
        "parameters": _translate_schema(mcp_tool.get("inputSchema") or {"type": "object", "properties": {}}),
    }


# ── Command resolver — encuentra npx/node/uvx aunque GUI no herede PATH ──────

def _resolve_command(command: str) -> str:
    """Resuelve un comando a ruta absoluta. Apps lanzadas por GUI en Mac no
    heredan el PATH del shell, así que buscamos en ubicaciones comunes."""
    import shutil
    # 1. Si ya es ruta absoluta y existe, usarla
    if os.path.isabs(command) and os.path.exists(command):
        return command
    # 2. shutil.which (respeta PATH actual)
    found = shutil.which(command)
    if found:
        return found
    # 3. Ubicaciones comunes (nvm, homebrew, sistema)
    home = Path.home()
    search = []
    if command in ("npx", "node", "npm"):
        # nvm: tomar la versión más nueva instalada
        nvm_dir = home / ".nvm" / "versions" / "node"
        if nvm_dir.exists():
            for ver in sorted(nvm_dir.iterdir(), reverse=True):
                search.append(ver / "bin" / command)
        search += [
            Path("/opt/homebrew/bin") / command,
            Path("/usr/local/bin") / command,
            Path("/usr/bin") / command,
        ]
    elif command in ("uv", "uvx"):
        search += [
            home / ".local" / "bin" / command,
            home / ".cargo" / "bin" / command,
            Path("/opt/homebrew/bin") / command,
            Path("/usr/local/bin") / command,
        ]
    for p in search:
        if p.exists():
            return str(p)
    # 4. Devolver tal cual (fallará con FileNotFoundError descriptivo)
    return command


# ── Server wrapper ───────────────────────────────────────────────────────────

class MCPServer:
    """Wrapper alrededor de un subprocess MCP. JSON-RPC sequential, thread-safe."""

    def __init__(self, name: str, command: str, args: list, env: dict | None = None, cwd: str | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env_extra = env or {}
        self.cwd = cwd
        self.proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._next_id = 1
        self.tools: list[dict] = []   # raw MCP tools
        self.initialized = False
        self._stderr_thread: threading.Thread | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Lanza el subprocess y hace handshake MCP. Retorna True si OK."""
        env = os.environ.copy()
        env.update(self.env_extra)
        resolved_cmd = _resolve_command(self.command)
        # Inyectar el dir del comando al PATH para que sus subprocesos (ej: npx → node)
        # se encuentren aunque la app se haya lanzado por GUI sin PATH de shell.
        cmd_dir = os.path.dirname(resolved_cmd)
        if cmd_dir and cmd_dir not in env.get("PATH", "").split(os.pathsep):
            env["PATH"] = cmd_dir + os.pathsep + env.get("PATH", "")
        try:
            self.proc = subprocess.Popen(
                [resolved_cmd] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=self.cwd,
                bufsize=1,   # line-buffered
                text=True,
                encoding="utf-8",
            )
        except FileNotFoundError:
            print(f"[MCP/{self.name}] ❌ Comando no encontrado: {self.command}")
            return False
        except Exception as e:
            print(f"[MCP/{self.name}] ❌ Error spawn: {e}")
            return False

        # Drain stderr en thread para que no bloquee el pipe
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

        # Handshake MCP
        try:
            self._send_request("initialize", {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "jarvis-ia", "version": "1.0"},
            }, timeout=15)
            # Notification: initialized
            self._send_notification("notifications/initialized", {})
            # Listar tools
            result = self._send_request("tools/list", {}, timeout=15)
            self.tools = result.get("tools", []) if isinstance(result, dict) else []
            self.initialized = True
            print(f"[MCP/{self.name}] ✓ {len(self.tools)} tools cargadas")
            return True
        except Exception as e:
            print(f"[MCP/{self.name}] ❌ Handshake falló: {e}")
            self.stop()
            return False

    def stop(self) -> None:
        if not self.proc:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.initialized = False

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _drain_stderr(self) -> None:
        if not self.proc or not self.proc.stderr:
            return
        try:
            for line in self.proc.stderr:
                line = line.rstrip()
                if line:
                    # No spamear consola — solo si tiene "error"/"warn" lo mostramos
                    low = line.lower()
                    if "error" in low or "warn" in low or "fatal" in low:
                        print(f"[MCP/{self.name}/stderr] {line[:200]}")
        except Exception:
            pass

    # ── JSON-RPC ──────────────────────────────────────────────────────────

    def _send_notification(self, method: str, params: dict) -> None:
        """Notification = mensaje sin id, no espera respuesta."""
        if not self.proc or not self.proc.stdin:
            return
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            with self._lock:
                self.proc.stdin.write(json.dumps(msg) + "\n")
                self.proc.stdin.flush()
        except Exception as e:
            print(f"[MCP/{self.name}] notify failed: {e}")

    def _send_request(self, method: str, params: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
        """Request síncrono — envía y bloquea hasta recibir respuesta con ese id."""
        if not self.proc or not self.proc.stdin or not self.proc.stdout:
            raise RuntimeError(f"{self.name}: proceso no iniciado")

        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            try:
                self.proc.stdin.write(json.dumps(msg) + "\n")
                self.proc.stdin.flush()
            except BrokenPipeError:
                raise RuntimeError(f"{self.name}: stdin cerrado (server murió)")

            deadline = time.time() + timeout
            while time.time() < deadline:
                if not self.is_alive():
                    raise RuntimeError(f"{self.name}: proceso terminó (exit={self.proc.returncode if self.proc else '?'})")

                line = self.proc.stdout.readline()
                if not line:
                    time.sleep(0.05)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    # Algunos servers loggean en stdout — ignorar líneas no-JSON
                    continue
                # ¿es respuesta a NUESTRO request?
                if resp.get("id") == req_id:
                    if "error" in resp:
                        err = resp["error"]
                        raise RuntimeError(f"{err.get('code')}: {err.get('message', err)}")
                    return resp.get("result", {})
                # else: notification o respuesta de otro id → ignorar

            raise TimeoutError(f"{self.name}.{method}: timeout {timeout}s")

    # ── Public API ────────────────────────────────────────────────────────

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Invoca una tool del server. Retorna texto."""
        if not self.initialized:
            return f"Server {self.name} no inicializado."
        try:
            result = self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            })
        except Exception as e:
            return f"Error MCP {self.name}.{tool_name}: {e}"

        # Resultado MCP: {content: [{type:"text", text:"..."}, ...], isError: bool}
        if isinstance(result, dict):
            if result.get("isError"):
                content = result.get("content", [])
                if content and isinstance(content[0], dict):
                    return f"Error: {content[0].get('text', '?')}"
                return "Error desconocido."
            content = result.get("content", [])
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
            return "\n".join(texts) if texts else json.dumps(result)[:500]

        return str(result)[:500]


# ── Manager ──────────────────────────────────────────────────────────────────

class MCPClientManager:
    """Carga config y gestiona múltiples servers MCP."""

    def __init__(self):
        self.servers: dict[str, MCPServer] = {}
        self._lock = threading.Lock()

    def load_from_config(self) -> int:
        """Lee config/mcp_servers.json y arranca cada server. Retorna #servers OK."""
        if not CONFIG_PATH.exists():
            print(f"[MCP] No hay config en {CONFIG_PATH} — saltando.")
            return 0
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[MCP] Error parseando config: {e}")
            return 0

        servers_cfg = cfg.get("servers", {})
        if cfg.get("enabled") is False:
            print("[MCP] Disabled en config (enabled=false).")
            return 0

        ok = 0
        for name, sc in servers_cfg.items():
            if sc.get("disabled"):
                print(f"[MCP] '{name}' deshabilitado en config.")
                continue
            # Servers atados a un SO (ej. windows-mcp): "platform": "win32"|"darwin"|"linux"
            want = (sc.get("platform") or "").lower().strip()
            if want and not sys.platform.startswith(want.replace("windows", "win")):
                print(f"[MCP] '{name}' es solo para {want} — omitido en este SO.")
                continue
            srv = MCPServer(
                name=name,
                command=sc.get("command", ""),
                args=sc.get("args") or [],
                env=sc.get("env") or {},
                cwd=sc.get("cwd"),
            )
            if srv.start():
                with self._lock:
                    self.servers[name] = srv
                ok += 1
        return ok

    def start_one(self, name: str) -> tuple[bool, list[dict]]:
        """Arranca UN server de la config en caliente (sin reiniciar JARVIS).
        Devuelve (ok, decls_de_ese_server). Si ya está corriendo, lo reinicia."""
        if not CONFIG_PATH.exists():
            return False, []
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return False, []
        sc = (cfg.get("servers") or {}).get(name)
        if not sc:
            return False, []
        # Si ya estaba, pararlo primero
        with self._lock:
            if name in self.servers:
                self.servers[name].stop()
                del self.servers[name]
        srv = MCPServer(
            name=name,
            command=sc.get("command", ""),
            args=sc.get("args") or [],
            env=sc.get("env") or {},
            cwd=sc.get("cwd"),
        )
        if not srv.start():
            return False, []
        with self._lock:
            self.servers[name] = srv
        decls = [_mcp_tool_to_gemini_decl(name, t) for t in srv.tools]
        return True, decls

    def get_tool_declarations(self) -> list[dict]:
        """Lista todas las tools MCP en formato Gemini."""
        decls = []
        for name, srv in self.servers.items():
            for tool in srv.tools:
                try:
                    decls.append(_mcp_tool_to_gemini_decl(name, tool))
                except Exception as e:
                    print(f"[MCP/{name}] tool '{tool.get('name')}' falló traducción: {e}")
        return decls

    def call(self, qualified_name: str, arguments: dict) -> str:
        """Invoca mcp__<server>__<tool> con args."""
        if not qualified_name.startswith("mcp__"):
            return f"Nombre no MCP: {qualified_name}"
        parts = qualified_name.split("__", 2)
        if len(parts) != 3:
            return f"Nombre MCP mal formado: {qualified_name}"
        _, server_name, tool_name = parts
        srv = self.servers.get(server_name)
        if not srv:
            return f"Server MCP '{server_name}' no cargado."
        return srv.call_tool(tool_name, arguments)

    def list_servers(self) -> str:
        if not self.servers:
            return "Sin servers MCP cargados."
        lines = []
        for name, srv in self.servers.items():
            status = "✓ alive" if srv.is_alive() else "✗ dead"
            lines.append(f"  {name}: {status}, {len(srv.tools)} tools")
        return "Servers MCP:\n" + "\n".join(lines)

    def shutdown(self) -> None:
        for srv in self.servers.values():
            srv.stop()
        self.servers.clear()


# ── Singleton para usar desde main.py ─────────────────────────────────────

_MANAGER: MCPClientManager | None = None


def get_manager() -> MCPClientManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = MCPClientManager()
    return _MANAGER
