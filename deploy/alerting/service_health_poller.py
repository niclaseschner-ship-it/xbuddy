#!/usr/bin/env python3
"""service_health_poller.py — Fern-Alerting-Poller für XBuddy-Services (#1646).

Schmerz, der dieses Skript hervorgebracht hat (#1623): ein unbeaufsichtigter
Pi-Hub kann tote oder hängende Services stundenlang unbemerkt laufen lassen —
kein Mensch ist im Raum, der `journalctl` liest. Nic soll als Owner privat
alarmiert werden, sobald ein Service nicht antwortet.

Was dieses Skript tut:
  - Probt alle HTTP-Services (SVC-6 /healthz) auf localhost mit connect- UND
    read-Timeout (tot = kein TCP; hängend = TCP-accept aber kein 200 in N s).
  - Liest die Heartbeat-Datei von Bot-Services ohne HTTP-Stack (SVC-8,
    eltern-chat): Timestamp älter als Schwellwert N → tot/hängend.
  - Bei rot → private Telegram-Nachricht an den Owner-Kanal (Alert-Ziel b,
    ratifiziert 2026-07-30, Kanal-Wahl Nic).

Was dieses Skript NICHT tut: Services neu starten, Befehle auf dem Pi
ausführen, die Familien-Gruppe benachrichtigen.

Architektur (Runner-Health-Gerüst, #1113-Vorbild):
  Die Entscheidung ist eine reine Funktion `decide(service_states)` —
  Zustand rein, Verdikt raus, kein I/O. Reale HTTP-Probes, Heartbeat-Lesungen
  und der Telegram-Alert sind eine dünne I/O-Schale (`probe_http`,
  `probe_heartbeat`, `send_alert`, `main`). Nur die reine Funktion ist testbar
  (deploy/alerting/tests/), die I/O-Schale wird dry-run gefahren / gemockt.

Auth-Kette:
  - Bot-Token:   ENV `ALERTING_BOT_TOKEN` (Pflicht) oder EnvironmentFile
                 `__XBUDDY_DATA__/alerting/.env` — nie im Repo.
  - Owner-ID:    ZD-Slot `alerting-owner-chat-id` aus dem Per-Instanz-
                 Zugangsdaten-Store (SVC-5, ZD-1); via `--zugangsdaten-file`
                 oder ENV `ZUGANGSDATEN_STORE_FILE` / ZD-Default.
  - Beide Werte fehlen → Start schlägt laut fehl (SVC-7-Geist).

Aufruf:
    python3 deploy/alerting/service_health_poller.py           # normal
    python3 deploy/alerting/service_health_poller.py --dry-run # kein Alert

Service-Liste und Schwellwerte:
  HTTP-Services (SVC-6 /healthz):
    127.0.0.1:5010  xbuddy-familie
    127.0.0.1:5030  xbuddy-wetter
    127.0.0.1:5041  xbuddy-panel
    127.0.0.1:5042  xbuddy-seiten
    127.0.0.1:5050  xbuddy-routine
    127.0.0.1:5052  xbuddy-essen
    127.0.0.1:5053  xbuddy-hoerspiel
    127.0.0.1:5054  xbuddy-kibuddy
    127.0.0.1:5055  xbuddy-hoerspiel-finn
    127.0.0.1:5056  xbuddy-hoerspiel-emil

  Heartbeat-Services (SVC-8, Bot ohne HTTP):
    eltern-chat → <XBUDDY_DATA_DIR>/eltern-chat/heartbeat

  Schwellwerte:
    connect-Timeout: 5 s (tot = kein TCP-accept in 5 s)
    read-Timeout: 10 s (hängend = TCP-accept, aber kein 200 in 10 s)
    heartbeat-Schwellwert: 300 s (5 min — analoger Takt zum Timer-Intervall)

Kein Secret im Repo. Alert-Kanal: privater Owner/Master-Kanal (b),
NICHT die Familien-Gruppe.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Konstanten (per-Instanz via Flag/ENV überschreibbar, nichts hartkodiert)
# ---------------------------------------------------------------------------

# Timeouts für HTTP-Probes (CLIENT-2-Geist: explizit, kein silent-block).
# connect-Timeout = „tot": kein TCP-Handshake in 5 s.
# read-Timeout = „hängend": TCP-accept, aber kein HTTP-200 in 10 s.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_READ_TIMEOUT_SECONDS = 10

# Heartbeat-Schwellwert: eltern-chat soll alle ~30 s pollen (Telegram long-poll
# default). 5 Minuten = 10× der erwarteten Frequenz — viel Puffer für Pausen,
# aber klar genug, dass ein hängender Bot erkannt wird.
DEFAULT_HEARTBEAT_THRESHOLD_SECONDS = 300

# Loopback-Adresse (PORT-3: Services binden nur an 127.0.0.1).
_LOOPBACK = "127.0.0.1"

# ZD-Slot-Name für die Owner-Chat-ID (Alert-Ziel b, privater Betriebskanal).
_ZD_SLOT_OWNER_CHAT_ID = "alerting-owner-chat-id"

# ENV-Variable für den Bot-Token (nie im Repo).
ENV_ALERTING_BOT_TOKEN = "ALERTING_BOT_TOKEN"

def _hoerspiel_instanz_services() -> list[tuple[int, str]]:
    """Sekundäre Hörspiel-Instanz-Services aus der zentralen instanzen.json-Registry
    (Option C #1732): instanzen[1:] → (port, f"xbuddy-hoerspiel-{slug}"). instanzen[0]
    ist der Primär-Service `xbuddy-hoerspiel` (kein Suffix, in der Basis-Liste). So
    tragen die Service-Namen die echten Live-Slugs, kein Hardcode."""
    try:
        from tools import instanzen as _inst
        insts = _inst.lade_instanzen("hoerspiel")
    except Exception:  # Registry fehlt/kaputt → nur Basis-Services
        return []
    out: list[tuple[int, str]] = []
    for e in insts[1:]:
        port = e.get("port") or 0
        slug = (e.get("slug") or "").strip()
        if port and slug:
            out.append((int(port), f"xbuddy-hoerspiel-{slug}"))
    return out


# HTTP-Services (port → service-name), SVC-6 /healthz.
# Quelle: conventions/ports.md PORT-2 (Basis) + instanzen.json-Registry (Hörspiel-
# Instanzen, Option C #1732).
_HTTP_SERVICES: list[tuple[int, str]] = [
    (5010, "xbuddy-familie"),
    (5030, "xbuddy-wetter"),
    (5041, "xbuddy-panel"),
    (5042, "xbuddy-seiten"),
    (5050, "xbuddy-routine"),
    (5052, "xbuddy-essen"),
    (5053, "xbuddy-hoerspiel"),
    (5054, "xbuddy-kibuddy"),
    *_hoerspiel_instanz_services(),
]

# Heartbeat-Services (service-name → relativer Pfad unter XBUDDY_DATA_DIR).
# SVC-8: Bot-Services ohne HTTP-Stack schreiben Heartbeat statt /healthz.
_HEARTBEAT_SERVICES: list[tuple[str, str]] = [
    ("xbuddy-eltern-chat", "eltern-chat/heartbeat"),
]


# ---------------------------------------------------------------------------
# Reiner Kern: Zustand → Entscheidung (testbar, kein I/O)
# ---------------------------------------------------------------------------


class ServiceStatus(Enum):
    """Beobachteter Zustand eines einzelnen Services."""
    OK = "ok"             # HTTP 200 / heartbeat frisch
    DEAD = "dead"         # kein TCP-connect (HTTP) / heartbeat-Datei fehlt
    HANGING = "hanging"   # TCP-accept, aber kein 200 / heartbeat zu alt


@dataclass(frozen=True)
class ServiceState:
    """Beobachteter Zustand eines einzelnen Services — alles, was `decide` braucht."""
    name: str
    status: ServiceStatus
    detail: str = ""   # Diagnose-Text fürs Log / Alert (Timeout-Grund, Alter etc.)


@dataclass(frozen=True)
class Decision:
    """Verdikt für den gesamten Poller-Lauf."""
    action: str                     # "alert" | "no_action"
    red_services: tuple[ServiceState, ...] = field(default_factory=tuple)


def decide(service_states: list[ServiceState]) -> Decision:
    """Reine Entscheidungsfunktion: Liste von ServiceStates → Verdikt.

    Regeln:
      - Jeder Service mit Status != OK ist rot.
      - Mindestens ein roter Service → action "alert".
      - Alle grün → action "no_action".
    """
    red = tuple(s for s in service_states if s.status != ServiceStatus.OK)
    if red:
        return Decision(action="alert", red_services=red)
    return Decision(action="no_action", red_services=())


def format_alert_text(red_services: tuple[ServiceState, ...]) -> str:
    """Formatiert den Alert-Text für die Telegram-Nachricht.

    Kompakt, lesbar im Handy-Chat. Kein HTML/Markdown — plaintext.
    """
    lines = ["⚠️ XBuddy-Alerting: Service(s) rot\n"]
    for svc in red_services:
        symbol = "💀" if svc.status == ServiceStatus.DEAD else "⏳"
        label = "tot" if svc.status == ServiceStatus.DEAD else "hängend"
        detail = f" ({svc.detail})" if svc.detail else ""
        lines.append(f"{symbol} {svc.name} — {label}{detail}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# I/O-Schale: Proben, Alert-Versand, kein echter Test-Gegenstand
# ---------------------------------------------------------------------------


def probe_http(
    port: int,
    service_name: str,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    read_timeout: float = DEFAULT_READ_TIMEOUT_SECONDS,
) -> ServiceState:
    """Probt einen HTTP-Service auf /healthz mit getrennten Timeouts.

    Getrennter Connect- und Read-Timeout via Sockets (urllib kennt nur einen
    kombinierten Timeout). Muster nach eltern-chat/telegram.py `_build_ipv4_opener`
    (EC-26 / E-EC-12), hier vereinfacht für den einmaligen Oneshot-Aufruf.

    - Kein TCP-accept in connect_timeout Sekunden → DEAD.
    - TCP-accept, aber kein HTTP 200 in read_timeout Sekunden → HANGING.
    - HTTP 200 → OK.
    """
    url = f"http://{_LOOPBACK}:{port}/healthz"

    # --- Connect-Phase (DEAD-Erkennung) ---
    try:
        sock = socket.create_connection((_LOOPBACK, port), timeout=connect_timeout)
    except (ConnectionRefusedError, OSError, TimeoutError) as e:
        return ServiceState(
            name=service_name,
            status=ServiceStatus.DEAD,
            detail=f"connect fehlgeschlagen: {e}",
        )

    # --- Read-Phase (HANGING-Erkennung): Socket offen, HTTP-Request absenden ---
    sock.close()  # urllib öffnet seine eigene Verbindung; wir haben nur den Port-Check gemacht
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=read_timeout) as resp:
            if resp.status == 200:
                return ServiceState(
                    name=service_name,
                    status=ServiceStatus.OK,
                    detail="",
                )
            return ServiceState(
                name=service_name,
                status=ServiceStatus.HANGING,
                detail=f"HTTP {resp.status} (erwartet 200)",
            )
    except urllib.error.URLError as e:
        # Kann ConnectionRefused (nach Socket-Close) oder Timeout sein.
        reason = str(e.reason) if hasattr(e, "reason") else str(e)
        if "timed out" in reason.lower() or "timeout" in reason.lower():
            return ServiceState(
                name=service_name,
                status=ServiceStatus.HANGING,
                detail=f"read-Timeout ({read_timeout}s): {reason}",
            )
        return ServiceState(
            name=service_name,
            status=ServiceStatus.DEAD,
            detail=f"urllib-Fehler: {reason}",
        )
    except OSError as e:
        return ServiceState(
            name=service_name,
            status=ServiceStatus.DEAD,
            detail=f"OS-Fehler: {e}",
        )


def probe_heartbeat(
    service_name: str,
    heartbeat_path: str,
    threshold_seconds: int = DEFAULT_HEARTBEAT_THRESHOLD_SECONDS,
    now: float | None = None,
) -> ServiceState:
    """Liest die Heartbeat-Datei eines Bot-Services (SVC-8).

    Datei fehlt → DEAD.
    Timestamp älter als threshold_seconds → HANGING.
    Timestamp frisch → OK.
    """
    now = now if now is not None else time.time()
    try:
        with open(heartbeat_path, encoding="utf-8") as f:
            raw = f.read().strip()
        ts = float(raw)
    except FileNotFoundError:
        return ServiceState(
            name=service_name,
            status=ServiceStatus.DEAD,
            detail=f"Heartbeat-Datei fehlt: {heartbeat_path}",
        )
    except (OSError, ValueError) as e:
        return ServiceState(
            name=service_name,
            status=ServiceStatus.DEAD,
            detail=f"Heartbeat-Lesefehler ({heartbeat_path}): {e}",
        )

    age_seconds = int(now - ts)
    if age_seconds > threshold_seconds:
        return ServiceState(
            name=service_name,
            status=ServiceStatus.HANGING,
            detail=f"Heartbeat {age_seconds}s alt (Schwellwert {threshold_seconds}s)",
        )
    return ServiceState(
        name=service_name,
        status=ServiceStatus.OK,
        detail="",
    )


def send_telegram_alert(bot_token: str, owner_chat_id: str, text: str) -> None:
    """Sendet eine Telegram-Nachricht an den Owner-Kanal (Alert-Ziel b).

    Nutzt TelegramClient aus eltern-chat/telegram.py (wiederverwendeter Baustein,
    ratifizierte Runde 2026-07-30). Import erfolgt relativ aus dem Repo-Root.
    """
    # Für den Import: der Poller wird aus dem Repo-Root aufgerufen (WorkingDirectory).
    # eltern-chat/telegram.py ist paketlos (wegen Bindestrich im Verzeichnisnamen);
    # wir importieren über importlib, analog deploy/runner/tests/test_runner_health.py.
    import importlib.util
    from pathlib import Path

    telegram_module_path = Path(__file__).resolve().parents[2] / "eltern-chat" / "telegram.py"
    spec = importlib.util.spec_from_file_location("eltern_chat_telegram", telegram_module_path)
    tg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tg)

    client = tg.TelegramClient(bot_token)
    client.send_message(int(owner_chat_id), text)


def _load_owner_chat_id(zd_file: str | None) -> str:
    """Liest die Owner-Chat-ID aus dem ZD-Store (ZD-1, Slot `alerting-owner-chat-id`).

    zd_file: Pfad zur Zugangsdaten-JSON (SVC-5: außerhalb des Checkouts).
    Fehlt der Slot oder die Datei → RuntimeError (SVC-7-Geist: laut scheitern).
    """
    from tools.zugangsdaten import Zugangsdaten, resolve_store_path

    store_path = zd_file or resolve_store_path()
    zd = Zugangsdaten(store_path)
    value = zd.get(_ZD_SLOT_OWNER_CHAT_ID)
    if not value:
        raise RuntimeError(
            f"ZD-Slot '{_ZD_SLOT_OWNER_CHAT_ID}' fehlt oder leer "
            f"(Store: {store_path}). Bitte Slot setzen: "
            f"python3 -m tools.zugangsdaten set {_ZD_SLOT_OWNER_CHAT_ID} <chat-id>"
        )
    return value


def _log(payload: dict) -> None:
    """Eine JSON-Zeile nach stdout — journald ist die Quelle der Wahrheit (SVC-4-Idiom)."""
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def gather_http_states(
    http_services: list[tuple[int, str]] | None = None,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    read_timeout: float = DEFAULT_READ_TIMEOUT_SECONDS,
) -> list[ServiceState]:
    """Probt alle HTTP-Services und liefert ihre States. I/O-Schale um probe_http."""
    targets = http_services if http_services is not None else _HTTP_SERVICES
    return [probe_http(port, name, connect_timeout, read_timeout) for port, name in targets]


def gather_heartbeat_states(
    data_dir: str,
    heartbeat_services: list[tuple[str, str]] | None = None,
    threshold_seconds: int = DEFAULT_HEARTBEAT_THRESHOLD_SECONDS,
    now: float | None = None,
) -> list[ServiceState]:
    """Liest alle Heartbeat-Files und liefert ihre States. I/O-Schale um probe_heartbeat."""
    targets = heartbeat_services if heartbeat_services is not None else _HEARTBEAT_SERVICES
    return [
        probe_heartbeat(
            name,
            os.path.join(data_dir, rel_path),
            threshold_seconds=threshold_seconds,
            now=now,
        )
        for name, rel_path in targets
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fern-Alerting-Poller: probt XBuddy-Services + Heartbeats (#1646)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Entscheiden + loggen, aber keinen Telegram-Alert senden.",
    )
    parser.add_argument(
        "--zugangsdaten-file",
        default=None,
        help="Pfad zur Zugangsdaten-JSON (Default: ZD-Store-Pfad per SVC-5).",
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        help=f"TCP-Connect-Timeout in Sekunden (Default: {DEFAULT_CONNECT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=DEFAULT_READ_TIMEOUT_SECONDS,
        help=f"HTTP-Read-Timeout in Sekunden (Default: {DEFAULT_READ_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--heartbeat-threshold",
        type=int,
        default=DEFAULT_HEARTBEAT_THRESHOLD_SECONDS,
        help=f"Heartbeat-Schwellwert in Sekunden (Default: {DEFAULT_HEARTBEAT_THRESHOLD_SECONDS}).",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="XBUDDY_DATA_DIR-Override (Default: ENV XBUDDY_DATA_DIR oder /home/buddy/xbuddy-data).",
    )
    args = parser.parse_args(argv)

    data_dir = args.data_dir or os.environ.get("XBUDDY_DATA_DIR", "/home/buddy/xbuddy-data")

    # I/O: alle Services proben
    all_states: list[ServiceState] = []
    all_states += gather_http_states(
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
    )
    all_states += gather_heartbeat_states(
        data_dir=data_dir,
        threshold_seconds=args.heartbeat_threshold,
    )

    # Reine Funktion: Entscheidung
    decision = decide(all_states)

    logged: dict = {
        "poller": "service_health_poller",
        "services_checked": len(all_states),
        "action": decision.action,
        "dry_run": args.dry_run,
        "red": [
            {"name": s.name, "status": s.status.value, "detail": s.detail}
            for s in decision.red_services
        ],
        "green": [
            s.name
            for s in all_states
            if s.status == ServiceStatus.OK
        ],
    }

    if decision.action == "alert" and not args.dry_run:
        # Bot-Token aus ENV (SVC-7: fehlt er, lauter Fehler statt stillem Skip)
        bot_token = os.environ.get(ENV_ALERTING_BOT_TOKEN, "").strip()
        if not bot_token:
            _log({**logged, "error": f"ENV {ENV_ALERTING_BOT_TOKEN} fehlt — Alert NICHT gesendet."})
            return 1

        try:
            owner_chat_id = _load_owner_chat_id(args.zugangsdaten_file)
        except (RuntimeError, Exception) as e:
            _log({**logged, "error": f"Owner-Chat-ID nicht ladbar: {e}"})
            return 1

        alert_text = format_alert_text(decision.red_services)
        try:
            send_telegram_alert(bot_token, owner_chat_id, alert_text)
            logged["alert_sent"] = True
        except Exception as e:
            logged["alert_sent"] = False
            logged["alert_error"] = str(e)
            _log(logged)
            return 1

    _log(logged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
