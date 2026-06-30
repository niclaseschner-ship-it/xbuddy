"""MCP-Spike #1181 — RAM- & Spawn-Messung (AC-1).

Misst mit echten Läufen (Median über N), nicht geschätzt:
  - HTTP-Dauerdienst: idle-RSS (VmRSS aus /proc) eines laufenden run_http.py.
  - stdio: Spawn-Zeit (Prozessstart → erster nutzbarer Tool-Call) und Peak-RSS
    (VmHWM aus /proc) eines pro-Aufruf gespawnten run_stdio.py.
  - Interpreter-Boden: RSS eines nackten `python -c pass` als Baseline-Delta.
  - Baseline (Direkt-Adapter): 0 Extra-Prozesse, RSS-Kosten = Import in-Prozess.

Linux-only (/proc). Auf dem Pi (Ziel-HW) der relevante Fall. Reine stdlib +
mcp-SDK aus dem Spike-venv; kein psutil.

Voraussetzung: Scratch-essen läuft (./run_scratch_essen.sh) auf 5152, sonst
liefern die Tool-Calls EssenClientError-Stubs — die RAM-/Spawn-Zahlen bleiben
trotzdem gültig (gemessen wird der MCP-Prozess, nicht die Daten).
"""

import asyncio
import os
import statistics
import subprocess
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
SPIKE_ROOT = os.path.dirname(HERE)
SERVER_DIR = os.path.join(SPIKE_ROOT, "server")
VENV_PY = os.path.join(SPIKE_ROOT, ".venv", "bin", "python")
N = int(os.environ.get("MESS_N", "7"))


def _vmrss_kb(pid):
    """VmRSS (resident, kB) eines PID aus /proc/<pid>/status."""
    return _proc_field(pid, "VmRSS")


def _vmhwm_kb(pid):
    """VmHWM (Peak resident, kB) eines PID aus /proc/<pid>/status."""
    return _proc_field(pid, "VmHWM")


def _proc_field(pid, field):
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith(field + ":"):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def _interpreter_floor_kb():
    """Peak-RSS eines nackten Spike-venv-Interpreters (Baseline-Delta-Boden)."""
    code = (
        "import os\n"
        "print(open('/proc/%d/status' % os.getpid()).read())"
    )
    out = subprocess.run(
        [VENV_PY, "-c", code], capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1])
    return None


def _find_stdio_child_pid():
    """Findet den gespawnten run_stdio.py-Kindprozess über /proc/<pid>/cmdline."""
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % entry, "rb") as f:
                cmd = f.read().decode("utf-8", "replace")
        except OSError:
            continue
        if "run_stdio.py" in cmd:
            return int(entry)
    return None


async def _one_stdio_run():
    """Ein stdio-Spawn: Start → initialize → list_tools → call_tool.

    Liefert (spawn_to_ready_ms, peak_rss_kb).
    """
    params = StdioServerParameters(
        command=VENV_PY,
        args=[os.path.join(SERVER_DIR, "run_stdio.py")],
        cwd=SERVER_DIR,
    )
    t0 = time.perf_counter()
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        await session.list_tools()
        # Erster nutzbarer Tool-Call = Prozess ist „ready".
        await session.call_tool("lese_einkauf", {})
        ready_ms = (time.perf_counter() - t0) * 1000.0
        pid = _find_stdio_child_pid()
        peak = _vmhwm_kb(pid) if pid else None
    return ready_ms, peak


def measure_stdio():
    times, peaks = [], []
    for _ in range(N):
        ready_ms, peak = asyncio.run(_one_stdio_run())
        times.append(ready_ms)
        if peak is not None:
            peaks.append(peak)
        time.sleep(0.2)
    return {
        "spawn_to_ready_ms_median": round(statistics.median(times), 1),
        "spawn_to_ready_ms_min": round(min(times), 1),
        "spawn_to_ready_ms_max": round(max(times), 1),
        "peak_rss_kb_median": int(statistics.median(peaks)) if peaks else None,
        "runs": N,
    }


def measure_http_idle():
    """Startet run_http.py, wartet bis Port lebt, misst idle-VmRSS (Median)."""
    import socket

    port = int(os.environ.get("MCP_HTTP_PORT", "5191"))
    proc = subprocess.Popen(
        [VENV_PY, os.path.join(SERVER_DIR, "run_http.py")],
        cwd=SERVER_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Auf den lauschenden Port warten (max ~10 s).
        deadline = time.time() + 10
        ready = False
        while time.time() < deadline:
            with socket.socket() as s:
                s.settimeout(0.3)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    ready = True
                    break
            time.sleep(0.2)
        if not ready:
            return {"error": "HTTP-Server nicht rechtzeitig bereit", "pid": proc.pid}
        # Idle settlen lassen, dann mehrfach VmRSS sampeln.
        time.sleep(1.0)
        samples = []
        for _ in range(N):
            rss = _vmrss_kb(proc.pid)
            if rss is not None:
                samples.append(rss)
            time.sleep(0.3)
        return {
            "idle_rss_kb_median": int(statistics.median(samples)) if samples else None,
            "samples": len(samples),
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def measure_baseline():
    """Direkt-Adapter: 0 Extra-Prozesse; RSS-Kosten = Import in-Prozess.

    Importiert _essen_http (spike-lokaler Minimal-HTTP-Client) aus SERVER_DIR —
    identische stdlib-Deps wie der vollständige EssenClient, daher gleicher
    RAM-Delta-Wert (MOD-6-konform: kein Fremdmodul-Import).
    """
    code = (
        "import os, sys\n"
        "sys.path.insert(0, %r)\n"
        "before = None\n"
        "with open('/proc/%%d/status' %% os.getpid()) as f:\n"
        "    for ln in f:\n"
        "        if ln.startswith('VmHWM:'): before = int(ln.split()[1])\n"
        "import _essen_http\n"
        "c = _essen_http.EssenHttpClient('http://127.0.0.1:5152')\n"
        "after = None\n"
        "with open('/proc/%%d/status' %% os.getpid()) as f:\n"
        "    for ln in f:\n"
        "        if ln.startswith('VmHWM:'): after = int(ln.split()[1])\n"
        "print('%%d %%d' %% (before, after))\n"
        % SERVER_DIR
    )
    out = subprocess.run(
        [VENV_PY, "-c", code], capture_output=True, text=True
    )
    before_after = out.stdout.strip().split()
    res = {"extra_prozesse": 0}
    if len(before_after) == 2:
        b, a = int(before_after[0]), int(before_after[1])
        res["import_rss_delta_kb"] = a - b
        res["interpreter_after_import_kb"] = a
    return res


def main():
    floor = _interpreter_floor_kb()
    print("=== MCP-Spike #1181 — RAM & Spawn (AC-1) ===")
    print("Interpreter-Boden (nacktes venv-Python, VmHWM): %s kB" % floor)
    print()
    print("[stdio] Spawn-Zeit + Peak-RSS (N=%d):" % N)
    s = measure_stdio()
    for k, v in s.items():
        print("  %s = %s" % (k, v))
    if floor and s.get("peak_rss_kb_median"):
        print("  delta_zum_interpreter_boden_kb = %d"
              % (s["peak_rss_kb_median"] - floor))
    print()
    print("[HTTP] idle-RSS Dauerdienst (N=%d):" % N)
    h = measure_http_idle()
    for k, v in h.items():
        print("  %s = %s" % (k, v))
    if floor and h.get("idle_rss_kb_median"):
        print("  delta_zum_interpreter_boden_kb = %d"
              % (h["idle_rss_kb_median"] - floor))
    print()
    print("[Baseline] Direkt-Adapter (RAT-3-Status quo):")
    b = measure_baseline()
    for k, v in b.items():
        print("  %s = %s" % (k, v))


if __name__ == "__main__":
    sys.exit(main())
