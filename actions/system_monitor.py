# -*- coding: utf-8 -*-
"""
system_monitor.py — Métricas de hardware (cross-platform).

Antes declaraba 11 acciones pero las ignoraba todas (siempre CPU/RAM/batería).
Ahora cada acción hace lo suyo: cpu, ram, disk, network, gpu, temperature,
battery, uptime, processes, kill, report. Temperatura en Mac vía pmset (sin sudo).
"""
import sys
import shutil
import subprocess
from datetime import datetime

import psutil

from core.registry import tool

_IS_MAC = sys.platform == "darwin"


def _gb(n: float) -> str:
    return f"{n / (1024 ** 3):.1f} GB"


def _battery() -> str:
    try:
        b = psutil.sensors_battery()
        if not b:
            return "Sin batería (equipo de escritorio)."
        state = "enchufada" if b.power_plugged else "con batería"
        left = ""
        if not b.power_plugged and b.secsleft and b.secsleft > 0:
            left = f", quedan ~{b.secsleft // 3600}h {(b.secsleft % 3600) // 60}m"
        return f"Batería: {b.percent}% ({state}{left})"
    except Exception:
        return "Batería: no disponible."


def _temperature() -> str:
    # Linux: sensores de psutil
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            flat = [t for arr in temps.values() for t in arr if t.current]
            if flat:
                mx = max(flat, key=lambda t: t.current)
                return f"Temperatura: {mx.current:.0f}°C ({mx.label or 'CPU'})"
    except Exception:
        pass
    # Mac: estado térmico vía pmset (sin sudo; no da grados pero sí presión térmica)
    if _IS_MAC:
        try:
            r = subprocess.run(["pmset", "-g", "therm"], capture_output=True, text=True, timeout=5)
            out = r.stdout
            if "CPU_Speed_Limit" in out:
                limit = [l for l in out.splitlines() if "CPU_Speed_Limit" in l][0].split("=")[-1].strip()
                if limit == "100":
                    return "Temperatura: normal (sin throttling térmico)."
                return f"Temperatura: ALTA — el CPU está limitado al {limit}% por calor."
        except Exception:
            pass
        return "Temperatura: normal (macOS no expone grados sin herramientas extra)."
    return "Temperatura: no disponible en este equipo."


def _gpu() -> str:
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
            u, mu, mt = [x.strip() for x in r.stdout.strip().split(",")]
            return f"GPU NVIDIA: {u}% de uso, {mu}/{mt} MB de VRAM."
        except Exception:
            pass
    if _IS_MAC:
        return "GPU integrada (Apple Silicon): el uso detallado no se expone sin herramientas extra; sin señales de sobrecarga si el equipo no está caliente."
    return "GPU: no disponible (instala nvidia-smi si tenés NVIDIA)."


def _processes(by: str, n: int) -> str:
    procs = []
    for p in psutil.process_iter(["name", "cpu_percent", "memory_percent"]):
        try:
            procs.append((p.info["name"] or "?", p.info["cpu_percent"] or 0.0,
                          p.info["memory_percent"] or 0.0))
        except Exception:
            pass
    key = 2 if by == "ram" else 1
    procs.sort(key=lambda t: t[key], reverse=True)
    lines = [f"  {name[:28]:28s} cpu {cpu:4.1f}%  ram {ram:4.1f}%" for name, cpu, ram in procs[:n]]
    return f"Top {n} procesos por {by}:\n" + "\n".join(lines)


def _kill(target: str) -> str:
    if not target:
        return "Decime el nombre o PID del proceso a cerrar."
    killed = 0
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if str(p.info["pid"]) == target or target.lower() in (p.info["name"] or "").lower():
                p.terminate()
                killed += 1
        except Exception:
            pass
    return f"✓ {killed} proceso(s) terminado(s)." if killed else f"No encontré procesos que coincidan con '{target}'."


@tool(
    name='system_monitor',
    description='Sistema: cpu, ram, disk, network, gpu, temperature, battery, uptime, processes, kill, report.',
    parameters={'type': 'OBJECT',
     'properties': {'action': {'type': 'STRING',
                               'description': 'cpu | ram | disk | network | gpu | temperature | '
                                              'battery | uptime | processes | kill | report'},
                    'sort_by': {'type': 'STRING', 'description': 'Para processes: cpu (default) | ram'},
                    'count': {'type': 'INTEGER',
                              'description': 'Para processes: cantidad a mostrar (default: 10)'},
                    'name': {'type': 'STRING', 'description': 'Para kill: nombre o PID del proceso'}},
     'required': ['action']},
)
def system_monitor(parameters: dict = None, player=None) -> str:
    p = parameters or {}
    action = (p.get("action") or "report").lower().strip()
    try:
        if action == "cpu":
            freq = psutil.cpu_freq()
            # En Apple Silicon psutil reporta 0 → omitir la frecuencia
            f = f" @ {freq.current / 1000:.1f} GHz" if freq and freq.current and freq.current > 100 else ""
            return f"CPU: {psutil.cpu_percent(interval=0.3)}% de uso, {psutil.cpu_count()} núcleos{f}."
        if action == "ram":
            m = psutil.virtual_memory()
            return f"RAM: {m.percent}% usada — {_gb(m.used)} de {_gb(m.total)} ({_gb(m.available)} libres)."
        if action == "disk":
            d = psutil.disk_usage("/")
            return f"Disco: {d.percent}% usado — {_gb(d.used)} de {_gb(d.total)} ({_gb(d.free)} libres)."
        if action == "network":
            io = psutil.net_io_counters()
            return f"Red desde el arranque: ↓ {_gb(io.bytes_recv)} recibidos, ↑ {_gb(io.bytes_sent)} enviados."
        if action == "battery":
            return _battery()
        if action == "temperature":
            return _temperature()
        if action == "gpu":
            return _gpu()
        if action == "uptime":
            boot = datetime.fromtimestamp(psutil.boot_time())
            up = datetime.now() - boot
            return f"Encendido hace {up.days} día(s) y {up.seconds // 3600} hora(s) (desde {boot:%Y-%m-%d %H:%M})."
        if action == "processes":
            return _processes((p.get("sort_by") or "cpu").lower(), int(p.get("count") or 10))
        if action == "kill":
            return _kill((p.get("name") or "").strip())

        # report (default): resumen completo
        cpu = psutil.cpu_percent(interval=0.3)
        m = psutil.virtual_memory()
        d = psutil.disk_usage("/")
        report = (f"CPU {cpu}% · RAM {m.percent}% ({_gb(m.used)}/{_gb(m.total)}) · "
                  f"Disco {d.percent}% · {_battery()}")
        if player:
            player.write_log(f"💻 {report[:90]}")
        return report
    except Exception as e:
        return f"No pude leer las métricas: {str(e)[:80]}"
