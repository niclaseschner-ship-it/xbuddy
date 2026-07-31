#!/usr/bin/env python3
"""Seiten-Registry — HTTP-Schnittstelle + Entrypoint (SREG-3).

Siehe specs/platform/seiten-registry.md (Refs #347, ratifiziert RAT-13,
RAT-31 E3 Umbau #1496). Diese Datei ist die echte Komponente um
`seiten/aggregator.py` herum: Flask-App + systemd-Service-Entrypoint.
Konsumenten (der Eltern-Chat-Skill `seiten_finden`, SREG-5) reden über HTTP
(DCOMP-1), nicht über `import seiten`.

Endpunkte:
  GET /api/v1/seiten   — das aggregierte Inventar (SREG-3), IMMER aus
                          `inventar.json`, KEIN Upstream-Call im Request-Pfad,
                          Laufzeit < 50 ms.
  GET /healthz         — Health-Check (SVC-1)

Service-Topologie (Lego-Prinzip): die Registry läuft als schlanker
eigenständiger Flask-Prozess auf Loopback-Port 5042 (PORT-2). nginx-Origin
matcht `= /api/v1/seiten` exakt auf diesen Prozess (URL-14, `xbuddy_seiten`).

Aktualität (TTL, SREG-3): `inventar.json` wird neu gebaut, sobald es älter als
der TTL ist (Default 30 s). Der Rebuild läuft on-demand beim nächsten Request —
er liest die committeten Manifeste von der Platte (SREG-2). Kein HTTP zu
anderen Services nötig (RAT-31 E3: Panel-/Geräte-Registry-Snapshots entfernt).
"""

import argparse
import contextlib
import json
import logging
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1),
# `tools.logsetup` (LOG-4) und `seiten.aggregator` auch beim Direktstart
# `python3 seiten/main.py` gefunden werden — analog panel/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import aggregator, pwa_mantel, render  # noqa: E402
from tools import configloader, instanzen, logsetup  # noqa: E402
from tools import familie_client as _familie_client_mod  # noqa: E402
from tools.familie_client import DEFAULT_ORIGIN as _FAMILIE_DEFAULT_ORIGIN  # noqa: E402

# EZG-6 / ESSEN-31 / T1015: Init-Data-Validierung aus tools.initdata
# (vorher per sys.path-Hack aus eltern-chat/init_data.py — Cluster-A-Option-B
# 2026-06-18-1720 heilt MOD-4 / MOD-6).
from tools.initdata import auth_gate as _auth_gate  # noqa: E402
from tools.initdata import init_data as _init_data_mod  # noqa: E402
from tools.initdata import session_cookie as _session_cookie  # noqa: E402
from tools.service_diagnostics import register_version  # noqa: E402

# DCOMP-4: Dateirechte auf den Eigentümer beschränkt — analog PREG-4 / GER-4.
FILE_MODE = 0o600



# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Der Aufbau-Kontext: Repo-Wurzel (Manifest-Discovery), Inventar-Pfad,
# Upstream-Origins, TTL. Der Entrypoint befüllt das Dict; Tests setzen es über
# `configure()`. `inventar` hält das zuletzt gebaute Inventar in-memory als
# Last-Known-Good-Basis (SREG-3) — die Wahrheit auf der Platte ist `inventar.json`.
runtime = {
    "root":              _REPO_ROOT,
    "inventar_path":     None,
    # SREG-17 / RAT-31 E6b (#1564): Origin des panel-Service, an den seiten
    # config.json/tiles.json/bearbeiten* der App-Panel-Instanzen proxyt
    # (DCOMP-1 — kein Direkt-Read der panels.json). Default http://127.0.0.1:5041
    # (PORT-2, panel-Loopback). Serving von /controller/app-panel/ ist seit
    # #1564 seiten-owned (vorher Router, ROU-24/ROU-27 — Code stirbt #1568).
    "panel_service_url": "http://127.0.0.1:5041",
    # ROU-26 / RAT-31 E6f-B (#1586): konfigurierbare icon-root.
    # Leer = Default aus DEFAULT_ICON_ROOT (/home/buddy/apps/icons/).
    "icon_root":         "",
    "ttl":               30,
    "inventar":          None,
    "gebaut_um":         0.0,
    # SREG-7: zwei Display-URL-Origins (Heim + Funnel, Funnel-only seit #1458).
    # Heim ist Pflicht fuer SREG-5-Link und SREG-12-Seite.
    # Tailscale-Origin aufgegeben (Nic-Setzung 2026-07-25, #1458): self-signed
    # IP-Verbindungen werden nicht mehr angeboten; Slot bleibt als Leer-String
    # damit configure()-Aufrufe mit tailscale_origin=... nicht brechen.
    # Funnel ist fuer Familien-User-Geraete ueber den Tailscale-Funnel (AUTH-7b,
    # RAT-27 RATIFIZIERT 2026-07-07). Fehlt, ist der externe User-Geraete-Zugang
    # schlicht nicht angeboten (kein Auto-Fallback — falsche Origin = Cookie im
    # falschen Jar + nicht-erreichbarer Link, SREG-7).
    "heim_origin":       "",
    "tailscale_origin":  "",   # immer leer seit #1458 (Funnel-only)
    "funnel_origin":     "",
    # MAD-7 / EZG-6 / ESSEN-31: Init-Data-Auth fuer Mini-App-Routen.
    # bot_token: aus ENV ELTERNCHAT_BOT_TOKEN (systemd EnvironmentFile, APP-7).
    # init_data_config: dict aus init_data.load_config() — cached nach erstem Lauf.
    "bot_token":         None,
    "init_data_config":  None,
    # T1015 / Cluster-A-Option-B: FAM-Lookup via tools.familie_client gegen
    # Familie-Service-API (FAM-7 / DCOMP-1) statt familie.json direkt zu lesen.
    # familie_client darf eine FamilieClient-Instanz oder ein Test-Doppel sein.
    "familie_client":    None,
}


def configure(root=None, inventar_path=None, ttl=None,
              heim_origin=None, tailscale_origin=None,
              funnel_origin=None,
              bot_token=None, init_data_config=None,
              familie_client=None,
              panel_service_url=None, icon_root=None,
              router_url=None):  # RAT-31 E6f-C (#1588): SHELL-2-Slot entfernt, Param bleibt als no-op fuer aeltere Test-Aufrufe.
    """Setzt Aufbau-Wurzel, Inventar-Pfad, TTL und Display-URL-Origins
    (SREG-3, SREG-7).

    RAT-31 E3: `panel_url`/`geraete_url` entfernt — keine Snapshot-Sorten
    mehr; das Inventar kommt ausschließlich aus committeten Manifesten (#1496).

    Wird `inventar_path` gesetzt, persistiert jeder Rebuild atomar dorthin und
    der Request liest von dort. Ohne `inventar_path` (Test-Modus) bleibt das
    in-memory-`inventar` die Quelle, ohne Disk-Schreiben.

    `heim_origin`, `tailscale_origin` und `funnel_origin` werden fuer die
    SREG-12-Seite benoetigt (render.baue_layout). Leer = Wert bleibt
    unpetraendert (None ueberschreibt auf leeren String — explizit loeschbar).
    `funnel_origin` ist die Funnel-FQDN fuer Familien-User-Geraete (AUTH-7b,
    SREG-7 dritte Origin, RAT-27 RATIFIZIERT 2026-07-07).

    `bot_token` und `init_data_config` werden fuer die MAD-7-Mini-App-Auth
    benoetigt. Im Test-Modus werden sie direkt gesetzt;
    im Produktiv-Betrieb kommen sie aus ENV / init_data.load_config().

    `familie_client` (T1015 / Cluster-A-Option-B): Test-Doppel mit
    ``get_telegram_ids()``-Methode oder eine ``tools.familie_client.FamilieClient``-
    Instanz. None → Produktiv-Pfad via ENV ``SEITEN_FAMILIE_ORIGIN``.
    Ersetzt den frueheren ``familie_json_path``-Direkt-Read (DCOMP-1 / FAM-7).

    `icon_root` (ROU-26 / RAT-31 E6f-B, #1586): Pfad zur icon-root fuer
    /display/_shared/icons/ + /api/v1/icons/suche. Leer = DEFAULT_ICON_ROOT.
    """
    if root is not None:
        runtime["root"] = root
    runtime["inventar_path"] = inventar_path
    if ttl is not None:
        runtime["ttl"] = ttl
    if heim_origin is not None:
        runtime["heim_origin"] = heim_origin
    if tailscale_origin is not None:
        runtime["tailscale_origin"] = tailscale_origin
    if funnel_origin is not None:
        runtime["funnel_origin"] = funnel_origin
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    if familie_client is not None:
        runtime["familie_client"] = familie_client
    if panel_service_url is not None:
        runtime["panel_service_url"] = panel_service_url
    if icon_root is not None:
        runtime["icon_root"] = icon_root
    runtime["inventar"] = None
    runtime["gebaut_um"] = 0.0


# Rebuild-Serialisierung (SREG-3): parallele Flask-Threads sollen nicht
# gleichzeitig holen + schreiben. Das Lock klammert nur den Rebuild — die
# schnelle GET-Antwort liest lock-frei aus `inventar.json` (DCOMP-2).
_rebuild_lock = threading.Lock()


# RAT-31 E3 (#1496): SnapshotUnreachable, _hole_json_liste, hole_panels und
# hole_geraete entfernt — das Inventar kommt ausschließlich aus committeten
# Manifesten (SREG-2). Kein HTTP zu panel/geraete-Registries mehr nötig.


# ============================================================
#  Inventar-Persistenz (DCOMP-4, atomar 0600)
# ============================================================

def save_inventar(inventar, path):
    """Schreibt das Inventar atomar mit 0600-Rechten (DCOMP-4).

    Pattern wie panel.save / geraete.save: erst eine Temp-Datei im
    Zielverzeichnis, mit 0600 geöffnet, dann `os.replace` (in-Filesystem
    atomares Rename). Bei Fehlschlag wird die Temp-Datei aufgeräumt; die alte
    Datei bleibt unverändert.
    """
    import tempfile

    target_dir = os.path.dirname(os.path.abspath(path))
    if target_dir and not os.path.isdir(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".inventar.", suffix=".json.tmp", dir=target_dir)
    os.close(tmp_fd)
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(inventar, f, indent=2, ensure_ascii=False, sort_keys=False)
            f.write("\n")
        os.chmod(tmp_path, FILE_MODE)
        os.replace(tmp_path, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise
    os.chmod(path, FILE_MODE)


def load_inventar(path):
    """Liest das persistierte Inventar (SREG-3). Fehlt es oder ist es kaputt,
    liefert es None — der Aufrufer baut dann frisch (Kaltstart)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ============================================================
#  Rebuild + Lese-Zugriff (SREG-3)
# ============================================================

def rebuild():
    """Baut das Inventar neu (SREG-3): liest committete Manifeste von der Platte.

    RAT-31 E3 (#1496): kein HTTP zu panel/geraete-Registries mehr — rein
    manifest-basiert (SREG-2). Persistiert atomar, wenn `inventar_path` gesetzt.
    Aktualisiert den in-memory-Cache und den Bauzeitstempel.
    """
    inventar = aggregator.baue_inventar(runtime["root"])

    path = runtime.get("inventar_path")
    if path is not None:
        try:
            save_inventar(inventar, path)
        except OSError as e:
            # Schreibfehler ist nicht-fatal: das in-memory-Inventar bleibt als
            # Antwort gültig, nur die Persistenz fehlte (Warnung).
            logging.warning("inventar.json nicht geschrieben: %s — in-memory gültig", e)

    runtime["inventar"] = inventar
    runtime["gebaut_um"] = time.monotonic()
    return inventar


def _aktuelles_inventar():
    """Liefert das Inventar für genau diesen Request (SREG-3).

    Immer aus `inventar.json` bzw. dem in-memory-Cache — KEIN Upstream-Call im
    Request-Pfad. Ist das Inventar abgelaufen (älter als TTL) oder noch nie
    gebaut (Kaltstart), löst genau dieser Request EINEN Rebuild aus (on-demand,
    hinter `_rebuild_lock`); die schnelle Antwort kommt danach aus dem frisch
    geschriebenen Inventar. Die Manifest-Sorten kommen frisch von der Platte —
    nie eine leere Antwort.
    """
    path = runtime.get("inventar_path")
    inventar = runtime.get("inventar")
    if inventar is None and path is not None:
        inventar = load_inventar(path)
        runtime["inventar"] = inventar

    abgelaufen = (time.monotonic() - runtime["gebaut_um"]) >= runtime["ttl"]
    if inventar is None or abgelaufen:
        with _rebuild_lock:
            # Doppelcheck unter Lock: ein paralleler Request kann gerade gebaut
            # haben — dann nicht erneut bauen.
            inventar = runtime.get("inventar")
            abgelaufen = (time.monotonic() - runtime["gebaut_um"]) >= runtime["ttl"]
            if inventar is None or abgelaufen:
                inventar = rebuild()
    return inventar


# ============================================================
#  FAM-7/8 — Familien-Mitglieds-Prüfung
# ============================================================

# T1015 / Cluster-A-Option-B: Familie-Service-Origin per Komponenten-ENV.
# Default kommt aus tools.familie_client.DEFAULT_ORIGIN (zentral, CLIENT-1).
_ENV_FAMILIE_ORIGIN = "SEITEN_FAMILIE_ORIGIN"


def _get_familie_client():
    """Liefert einen FamilieClient (Test-Naht oder frisch aus ENV, T1015).

    Replaced den frueheren familie.json-Direkt-Read (DCOMP-1 / FAM-7-Heilung).
    """
    cached = runtime.get("familie_client")
    if cached is not None:
        return cached
    origin = os.environ.get(_ENV_FAMILIE_ORIGIN, _FAMILIE_DEFAULT_ORIGIN)
    return _familie_client_mod.FamilieClient(origin_url=origin)


def _check_familie_mitglied(user_id):
    """Prüft ob user_id in der Familien-Registry registriert ist (FAM-7/8 / AC4).

    Gibt None zurück wenn OK (user_id ist Mitglied oder Familie-Service unerreichbar).
    Gibt (json-Response, 403) zurück wenn user_id NICHT in der Registry.

    T1015: HTTP-Pfad über ``tools.familie_client``; fail-open bei Service-
    Nichterreichbarkeit (Plan-Buddy-Geist, analog zum frueheren Datei-Fallback).
    """
    familie_ids = _get_familie_client().get_telegram_ids()
    if familie_ids is None:
        # Familie-Service nicht erreichbar oder kein Lookup möglich → fail-open
        logging.debug("FAM-7: Familie-Service nicht erreichbar — FAM-Check uebersprungen")
        return None
    if user_id not in familie_ids:
        logging.warning("FAM-7: user_id %s ist kein Familien-Mitglied → 403", user_id)
        return jsonify({"error": "Nicht autorisiert — kein Familienmitglied"}), 403
    return None


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__, template_folder="templates",
            static_folder="static",
            static_url_path="/api/v1/seiten/static")


# ── Version-Endpoint (SVC-6) — geteilte Naht in tools/service_diagnostics ──
register_version(app)


@app.route("/api/v1/seiten", methods=["GET"])
def get_seiten():
    """SREG-3: das aggregierte Inventar aller aufrufbaren Views.

    Serviert IMMER aus `inventar.json` (kein Upstream-Call im Request-Pfad,
    < 50 ms). Die Antwort ist nie leer (die Manifest-Sorten tragen sie auch beim
    Kaltstart). RAT-31 E3: keine Snapshot-Sorten mehr, kein stale/pending.
    """
    inventar = _aktuelles_inventar()
    return jsonify(inventar)


@app.route("/api/v1/seiten/uebersicht", methods=["GET"])
def get_seiten_uebersicht():
    """SREG-12: gerenderte Eltern-Uebersichts-Seite (HTML).

    Baut die V2-Layout-Datenstruktur via render.baue_layout und liefert das
    gerendertes HTML (Jinja2, Template uebersicht.html). Origins kommen aus dem
    runtime-Dict (SREG-7): ENV-Overrides SEITEN_HEIM_ORIGIN /
    SEITEN_FUNNEL_ORIGIN oder CLI-Flags --seiten-heim-origin /
    --seiten-funnel-origin, gesetzt beim Start (resolved_config).

    SEITEN_TAILSCALE_ORIGIN wird seit #1458 nicht mehr gelesen (Funnel-only).
    """
    inventar = _aktuelles_inventar()
    layout = render.baue_layout(
        inventar,
        heim_origin=runtime["heim_origin"],
        tailscale_origin=runtime["tailscale_origin"],
        funnel_origin=runtime["funnel_origin"],
    )
    return render_template("uebersicht.html", **layout)


@app.route("/api/v1/seiten/layout", methods=["GET"])
def get_seiten_layout():
    """#1210 (Daten-SSoT): der EINE angereicherte Layout-Kontrakt als JSON.

    Liefert exakt `render.baue_layout(...)` — dieselbe Ableitung, die der
    Jinja-Pfad `/uebersicht` rendert. So konsumieren ALLE familienseitigen
    Uebersichts-/Registry-Oberflaechen (Grossbild + Mini-App) EINE Quelle;
    keine Oberflaeche re-derived Gruppierung/Anreicherung lokal (SREG-15).

    Das ist ein DATEN-Endpunkt (kein View) — Geschwister zu `GET /api/v1/seiten`
    (SREG-3). Er listet sich darum NICHT in views.json (siehe die Ausnahme in
    test_views_manifest_eigentest.py, analog zum Inventar-Endpunkt selbst).

    Auth (MAD-11-Muster): wie /uebersicht public — die HTML-Skeletons laden
    ohne Header, die JS-Seite prueft via /api/v1/init-data/validate. Der
    Kontrakt traegt keine Geheimnisse (nur Labels/Pfade/URLs aus dem Inventar).
    """
    inventar = _aktuelles_inventar()
    layout = render.baue_layout(
        inventar,
        heim_origin=runtime["heim_origin"],
        tailscale_origin=runtime["tailscale_origin"],
        funnel_origin=runtime["funnel_origin"],
    )
    return jsonify(layout)


def _get_bot_token():
    """Liest den Bot-Token aus runtime-Dict oder ENV (MAD-7 / APP-7).

    Reihenfolge: runtime-Dict (Test-Naht) → ELTERNCHAT_BOT_TOKEN
    (CONFIG-5-Schema aus eltern-chat/.env via systemd EnvironmentFile-Sharing,
    #684) → TELEGRAM_BOT_TOKEN (Fallback-Name).
    """
    return (
        runtime.get("bot_token")
        or os.environ.get("ELTERNCHAT_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
    )


# ============================================================
#  AUTH-7b — Dual-Gate-Decorator (Cookie ODER Operator-IP)
# ============================================================
#
# Spec-Anker: specs/platform/auth.md AUTH-7 (Dual-Gate, 495-504) +
# AUTH-3.a (Observe→Hard-Leiter, 237-281) + AUTH-8 (401-Anweisungsseite).
# Die pure Prüf-Mechanik (CIDR-Mitgliedschaft, Cookie-Verifikation) lebt
# Flask-frei in tools/initdata/auth_gate.py (RAT-16); dieser Decorator ist der
# Flask-Glue. Er wird — wie require_init_data (essen/photo/kibuddy/plan) —
# PRO SERVICE dupliziert (auth.md AUTH-5:347: Loopback/Decorator je Buddy
# kopiert bis n=3). Der Zwilling steht in router/main.py.

# AUTH-8: 401 rendert die Re-Pair-Anweisungsseite statt eines rohen Codes.
# Die 401-Antwort IST die Re-Pair-Anweisung (7b-Public-Ausnahme, auth.md
# AUTH-7:510) — keine separate Re-Pair-Route. 7b-Renderer-Routen tragen keine
# API-display_id im Auth-Kontext → neutraler Geräte-Hinweis (auth.md AUTH-8).
_DUAL_GATE_401_HTML = (
    "<!doctype html>\n"
    "<html lang=\"de\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>Gerät neu verbinden</title></head>"
    "<body style=\"font-family:system-ui,sans-serif;max-width:32rem;"
    "margin:3rem auto;padding:0 1rem;line-height:1.5\">"
    "<h1>Dieses Gerät muss neu verbunden werden.</h1>"
    "<p>Frag den Familien-Chatbot einfach nach einem neuen Cookie für dein "
    "Gerät — dann geht es wieder. Oder pair im Chat ein neues Gerät.</p>"
    "</body></html>"
)


def _client_ip():
    """Client-IP für die Operator-IP-Prüfung (AUTH-7 7a).

    `X-Real-IP` vom Origin-nginx ist die vertrauenswürdige Quelle (ESC-2:
    seiten bindet Loopback, nginx überschreibt den Header — ein externer
    Client kann die Operator-CIDR nicht spoofen). Fallback: erstes Token aus
    `X-Forwarded-For`; zuletzt `request.remote_addr`.
    """
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr


# SREG-17 / RAT-32: Auth-Modus fuer die vom Router uebernommenen App-Panel-
# Routen (#1564). 'observe' = verhaltensneutraler Deploy, `XBUDDY_AUTH_MODE=hard`
# flippt sie hart — identisch zum Router-Schalter (router/main.py:262), damit die
# Serving-Verlagerung das Auth-Verhalten nicht ungewollt aendert.
_AUTH_MODE = os.environ.get("XBUDDY_AUTH_MODE", "observe")


def _dual_auth_401():
    """AUTH-8-Re-Pair-Renderer für den Dual-Gate (D1, buddy-variant).

    Liefert die 401-Antwort mit dem AUTH-8-Re-Pair-HTML byte-gleich zum
    bisherigen Inline-401 (make_response(_DUAL_GATE_401_HTML, 401) +
    Content-Type text/html; charset=utf-8). Der injizierte Renderer ist der
    einzige Ort, an dem der 401-Text lebt — die #1625-Factory inlined ihn NIE.
    """
    resp = make_response(_DUAL_GATE_401_HTML, 401)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


# AUTH-7b-Dual-Gate über die #1625-Factory (auth.md „AUTH-Decorator-Lib", #1383,
# RAT-32). Ersetzt den bislang hand-kopierten require_dual_gate byte-gleich:
# Cookie gültig → 200 + Rolling-Refresh (AUTH-2:78); keine Quelle + mode="hard"
# → _dual_auth_401(); keine Quelle + mode="observe" → 200 + Observe-Log. Der
# Name `require_dual_gate` BLEIBT (Copetrage-AST MODULE_MAP_7B trägt per Namen);
# die Factory ist parametrisierbar (`require_dual_gate(mode="hard")` /
# `mode=_AUTH_MODE`), default_mode="observe" wie zuvor. ist_operator_ip
# (get_client_ip) speist nur noch das Observe-Log (RAT-32, kein Gate).
require_dual_gate = _auth_gate.make_require_dual_gate(
    get_bot_token=_get_bot_token,
    get_client_ip=_client_ip,
    auth_401=_dual_auth_401,
    default_mode="observe",
)


def _validate_mini_app_request():
    """Validiert den Authorization-Header für Mini-App-Requests (MAD-7).

    Liest 'Authorization: tma <initData>' aus dem Request-Header,
    validiert via HMAC-SHA256 (init_data.validate_header).

    Gibt InitData zurück bei Erfolg.
    Gibt (json-Response, 401) zurück bei Auth-Fehler.
    Gibt (json-Response, 500) zurück bei fehlendem Bot-Token.
    """
    bot_token = _get_bot_token()
    if not bot_token:
        logging.error("MAD-7: ELTERNCHAT_BOT_TOKEN nicht gesetzt — Mini-App-Route nicht nutzbar.")
        return None, (jsonify({"error": "Serverkonfiguration unvollständig (Bot-Token fehlt)"}), 500)

    # Konfig laden (gecacht im runtime-Dict)
    cfg = runtime.get("init_data_config")
    if cfg is None:
        cfg = _init_data_mod.load_config()
        runtime["init_data_config"] = cfg

    auth_header = request.headers.get("Authorization")
    try:
        init_data = _init_data_mod.validate_header(
            auth_header,
            bot_token,
            cfg["max_age_seconds"],
        )
    except _init_data_mod.InitDataError as exc:
        logging.warning("MAD-7 Auth fehlgeschlagen: %s", exc)
        return None, (jsonify({"error": "initData ungültig, abgelaufen oder fehlt"}), 401)

    return init_data, None


@app.route("/api/v1/init-data/validate", methods=["POST"])
def init_data_validate():
    """MAD-11: JS-Side-Auth-Endpoint für Mini-App-Mount-Validation.

    Mini-App-JS macht beim Mount POST mit Authorization: tma <initData>-Header.
    Endpoint validiert via HMAC + FAM-Lookup. Returnt 200 + {user_id, family_member}
    bei Erfolg, 401 (ungültig/abgelaufen) oder 403 (kein Familien-Mitglied).

    Antwort-Format (200):
      {"user_id": 12345, "user_first_name": "Nic", "family_member": true}

    Pendant zu MAD-7: HTML-Render-Route ist public (Telegram-WebView sendet
    beim Initial-Load keinen Header); JS-Mount-Call macht die Auth-Probe.
    """
    init_data, err = _validate_mini_app_request()
    if err is not None:
        return err

    fam_err = _check_familie_mitglied(init_data.user_id)
    if fam_err is not None:
        return fam_err

    return jsonify({
        "user_id": init_data.user_id,
        "user_first_name": getattr(init_data, "user_first_name", None),
        "family_member": True,
    }), 200


# ============================================================
#  AUTH-2.a — Pairing-Endpoint /auth/pair (T948, OD2 auf seiten)
# ============================================================
#
# Spec-Anker: specs/platform/auth.md AUTH-2.a. Der Pairing-Token (15min, HMAC
# mit Bot-Token, kodiert das Session-Subjekt, stateless — OD4) wird verifiziert;
# bei Erfolg setzt der Endpoint nur den xbuddy_session-Cookie (AUTH-2) und
# redirected neutral auf die Übersicht (SREG-12). RAT-31 E6c (Nic-Setzung
# 2026-07-29): KEINE geraete-Registry mehr — kein paired_at-Write, keine
# verwendungs-abhängige Ziel-Ableitung. Die Rolle (Kinder-Display vs.
# Elterngerät) wählt das Elternteil beim PWA-Installieren, nicht der Server.

# AUTH-2.a: 400-Anweisung bei ungültigem/abgelaufenem Token (statt rohem Code).
_PAIR_400_HTML = (
    "<!doctype html>\n"
    "<html lang=\"de\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>Pairing-Link ungültig</title></head>"
    "<body style=\"font-family:system-ui,sans-serif;max-width:32rem;"
    "margin:3rem auto;padding:0 1rem;line-height:1.5\">"
    "<h1>Dieser Pairing-Link ist ungültig oder abgelaufen.</h1>"
    "<p>Fordere im Familien-Bot einen neuen Pairing-Link an und öffne ihn "
    "innerhalb von 15 Minuten auf diesem Gerät.</p>"
    "</body></html>"
)


@app.route("/auth/pair", methods=["GET"])
def auth_pair():
    """AUTH-2.a: `GET /auth/pair?token=<X>` — Pairing-Token → Cookie → redirect.

    Verifiziert den stateless 15-Minuten-Pairing-Token (OD4). Bei Erfolg:
    setzt den xbuddy_session-Cookie (AUTH-2, HttpOnly/Secure/SameSite=Lax) und
    redirected neutral auf die Übersichtsseite (SREG-12). Bei
    ungültigem/abgelaufenem Token: 400 mit Anweisungsseite (AUTH-2.a).

    RAT-31 E6c: kein geraete.json-Read/Write, kein paired_at, keine
    verwendungs-abhängige Ziel-Ableitung mehr — alle Geräte landen auf der
    Übersicht; die Rolle wählt das Elternteil beim PWA-Install.
    """
    bot_token = _get_bot_token()
    if not bot_token:
        logging.error("AUTH-2.a: ELTERNCHAT_BOT_TOKEN nicht gesetzt — "
                      "/auth/pair nicht nutzbar.")
        return ("Serverkonfiguration unvollständig (Bot-Token fehlt)", 500)

    token = request.args.get("token", "")
    subjekt = _session_cookie.verify_pairing(token, bot_token)
    if subjekt is None:
        resp = make_response(_PAIR_400_HTML, 400)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    # RAT-31 E6c: neutraler Redirect auf die Übersicht für alle (SREG-12).
    resp = redirect("/api/v1/seiten/uebersicht")
    resp.set_cookie(
        _session_cookie.COOKIE_NAME,
        _session_cookie.sign_session(subjekt, bot_token),
        **_session_cookie.session_cookie_kwargs(),
    )
    return resp


@app.route("/seiten/essen/einkauf/", methods=["GET"])
def essen_einkauf_view_trailing_slash():
    """ESSEN-34 Trailing-Slash-Alias: GET /seiten/essen/einkauf/ → HTML.

    manifest.json traegt start_url: "/seiten/essen/einkauf/" — der PWA-Open
    nach Install laedt diese URL. Ohne diese Route landet der Nutzer in 404.
    Form: Option C (dedizierter Handler, kein strict_slashes, kein Reihenfolge-
    Risiko gegenueber einkauf_asset_view bei /seiten/essen/einkauf/<asset>).
    """
    return essen_einkauf_view()


@app.route("/seiten/essen/einkauf", methods=["GET"])
def essen_einkauf_view():
    """EZG-6 / ESSEN-31 / ESSEN-33: Eltern-Mini-App-View fuer die Einkaufsliste.

    HTML-Render-Route lädt Skeleton OHNE Auth (MAD-7-konform: Telegram-WebView
    sendet beim HTML-Initial-Load KEINEN Authorization-Header — initData kommt
    nur via window.Telegram.WebApp.initData in der JS-App). JS macht beim Mount
    platform.ensureAuth() → ruft /api/v1/init-data/validate mit Header → bei
    401/403 sperrt UI. Daten-Schutz auf API-Routen (essen/main.py) bleibt scharf.

    Cache-Buster: build_id aus mtime der JS-Datei (Telegram-WebView cached
    Mini-App-Assets sonst aggressiv — Pattern analog routine/MAU/hoerspiel).

    ESSEN-33: HTML bindet manifest.json + sw.js ein (PWA-Mantel). Asset-Routen
    leben unter /seiten/essen/einkauf/<asset> — siehe einkauf_asset_view.
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    build_id = pwa_mantel.build_id_for("einkauf", static_dir)
    # T1324: sw_scope aus REGISTRY — Template nutzt {{ sw_scope }} statt hartkodiertem Literal.
    sw_scope = pwa_mantel.REGISTRY["einkauf"].sw_scope
    resp = make_response(render_template("essen-einkauf.html", build_id=build_id, sw_scope=sw_scope))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ============================================================
#  ESSEN-33..35 — PWA-Asset-Auslieferung (Mantel, Service-Worker, Icons)
# ============================================================
#
# Spec-Anker: specs/buddies/essen.md ESSEN-34 (Asset-Auslieferung am
# Mini-App-Pfad, NICHT am generischen /seiten/static/-Pfad). Vorbild:
# router/main.py _send_controller_asset (ROU-23) — Defense in Depth via
# werkzeug safe_join (via send_from_directory) + expliziter realpath-Check.

# Content-Types fuer die PWA-Mantel-Assets (ESSEN-34-Acceptance-Tabelle).
_EINKAUF_MIME = {
    ".json": "application/manifest+json",   # Manifest braucht diesen Typ,
                                            # sonst lehnt Chrome WebAPK-Install ab.
    ".js":   "application/javascript",
    ".png":  "image/png",
}


def _einkauf_asset_root():
    """Wurzelverzeichnis fuer PWA-Mantel-Assets (ESSEN-34).

    Liegt unter seiten/static/einkauf/ (Lego-Trennung: PWA-Verzeichnis ist
    Geschwister zu den anderen Mini-App-Assets, aber URL-mapped auf den
    Mini-App-Pfad). Test-Naht: ueberschreibbar via runtime["einkauf_asset_dir"].
    """
    override = runtime.get("einkauf_asset_dir") if isinstance(runtime, dict) else None
    if override:
        return override
    return os.path.join(os.path.dirname(__file__), "static", "einkauf")


def _current_build_id():
    """build_id fuer den einkauf-SW aus dem Source-Set [essen-einkauf.js,
    platform.js] (PWAM-4/5, pwa_mantel.REGISTRY['einkauf']).

    +platform.js gegenueber frueher (nur essen-einkauf.js): ein platform.js-Bump
    invalidiert jetzt AUCH den SW-Cache, nicht nur die HTML-Route
    (T1266 AC3-Kill-Kriterium, conventions/pwa-mantel.md PWAM-4).
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return pwa_mantel.build_id_for("einkauf", static_dir)


@app.route("/seiten/essen/einkauf/<path:asset>", methods=["GET"])
def einkauf_asset_view(asset):
    """ESSEN-34: PWA-Mantel-Asset-Auslieferung (analog ROU-23).

    Antwortet auf /seiten/essen/einkauf/manifest.json, /sw.js, /icon-*.png.
    Path-Traversal-Schutz via realpath-Check. Andere Pfade → 404.

    Sonderfall sw.js: BUILD_ID-Platzhalter wird beim Ausliefern durch den
    aktuellen build_id-Wert ersetzt (ESSEN-35-Cache-Versionierung).
    """
    from flask import abort, send_from_directory

    root = os.path.realpath(_einkauf_asset_root())
    # werkzeug safe_join (via send_from_directory) wuerde bei .. selbst
    # ablehnen; zusaetzlich realpath-Check, damit Symlinks nicht
    # ausbrechen koennen.
    target = os.path.realpath(os.path.join(root, asset))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    # Privat-Datei (_make_icons.py) nicht ausliefern.
    if os.path.basename(target).startswith("_"):
        abort(404)

    ext = os.path.splitext(target)[1].lower()
    mimetype = _EINKAUF_MIME.get(ext, "application/octet-stream")

    # Sonderfall sw.js: build_id-Platzhalter ersetzen + Cache-Control-Header
    # damit der Browser den Worker bei jedem Update neu holt.
    if os.path.basename(target) == "sw.js":
        build_id = _current_build_id()
        body = pwa_mantel.read_sw_with_build_id(target, build_id)
        resp = make_response(body, 200)
        resp.headers["Content-Type"] = mimetype + "; charset=utf-8"
        # Browser muss sw.js fresh holen, sonst kein Update-Trigger.
        # https://web.dev/articles/service-worker-lifecycle#updates
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        # Service-Worker-Allowed nicht noetig — Scope passt zur Default-Wurzel.
        return resp

    # Andere Assets: send_from_directory mit explizitem Content-Type.
    return send_from_directory(root, asset, mimetype=mimetype)


# ============================================================
#  PLAN-35 — Plan-Einstellungs-PWA (Mantel, Service-Worker, Icons)
# ============================================================
#
# Spec-Anker: specs/buddies/plan.md PLAN-35 (P2: Eltern-Einstellungs-Seite,
# PWA-Mantel). Surface: /seiten/plan/einstellungen. PUBLIC / Netz-Trust
# (auth.md AUTH-6, /api/v1/plan/*). Vorbild: ESSEN-34 (einkauf_asset_view).

_PLAN_EINST_MIME = {
    ".json": "application/manifest+json",
    ".js":   "application/javascript",
    ".png":  "image/png",
}


def _plan_einst_asset_root():
    """Wurzelverzeichnis fuer Plan-Einstellungs-PWA-Mantel-Assets (PLAN-35).

    Liegt unter seiten/static/plan/ (Lego-Trennung: PWA-Verzeichnis ist
    Geschwister zu den anderen Mini-App-Assets). Test-Naht: ueberschreibbar
    via runtime["plan_einst_asset_dir"].
    """
    override = runtime.get("plan_einst_asset_dir") if isinstance(runtime, dict) else None
    if override:
        return override
    return os.path.join(os.path.dirname(__file__), "static", "plan")


def _plan_einst_build_id():
    """build_id fuer den plan-SW aus [plan-einstellungen.js, platform.js]
    (PWAM-4/5, pwa_mantel.REGISTRY['plan']).

    +platform.js gegenueber frueher: platform.js-Bump invalidiert jetzt AUCH den
    SW-Cache (T1266 AC3-Fix, analog einkauf).
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return pwa_mantel.build_id_for("plan", static_dir)


@app.route("/seiten/plan/einstellungen/", methods=["GET"])
def plan_einstellungen_view_trailing_slash():
    """PLAN-35 Trailing-Slash-Alias: GET /seiten/plan/einstellungen/ → HTML.

    manifest.json traegt start_url: "/seiten/plan/einstellungen/" — der PWA-Open
    nach Install laedt diese URL. Ohne diese Route landet der Nutzer in 404.
    Form: Option C (dedizierter Handler, analog essen_einkauf_view_trailing_slash).
    """
    return plan_einstellungen_view()


@app.route("/seiten/plan/einstellungen", methods=["GET"])
def plan_einstellungen_view():
    """PLAN-35: Plan-Einstellungs-PWA — HTML-Render-Route.

    PUBLIC / Netz-Trust (auth.md AUTH-6): kein Auth-Header, kein initData.
    Cache-Buster: build_id aus mtime der plan-einstellungen.js (platform.js einbezogen, T1229).
    PWA-Mantel: manifest.json + sw.js unter /seiten/plan/einstellungen/<asset>.
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    build_id = pwa_mantel.build_id_for("plan", static_dir)
    # T1324: sw_scope aus REGISTRY — Template nutzt {{ sw_scope }} statt hartkodiertem Literal.
    sw_scope = pwa_mantel.REGISTRY["plan"].sw_scope
    resp = make_response(render_template("plan-einstellungen.html", build_id=build_id, sw_scope=sw_scope))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/seiten/plan/einstellungen/<path:asset>", methods=["GET"])
def plan_einstellungen_asset_view(asset):
    """PLAN-35: PWA-Mantel-Asset-Auslieferung (analog ESSEN-34 / ROU-23).

    Antwortet auf /seiten/plan/einstellungen/manifest.json, /sw.js, /icon-*.png.
    Path-Traversal-Schutz via realpath-Check. Private Dateien (_*) → 404.

    Sonderfall sw.js: __BUILD_ID__-Platzhalter wird beim Ausliefern ersetzt
    (PLAN-35 Cache-Versionierung, analog ESSEN-35).
    """
    from flask import abort, send_from_directory

    root = os.path.realpath(_plan_einst_asset_root())
    target = os.path.realpath(os.path.join(root, asset))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    if os.path.basename(target).startswith("_"):
        abort(404)

    ext = os.path.splitext(target)[1].lower()
    mimetype = _PLAN_EINST_MIME.get(ext, "application/octet-stream")

    # Sonderfall sw.js: build_id-Platzhalter ersetzen.
    if os.path.basename(target) == "sw.js":
        build_id = _plan_einst_build_id()
        body = pwa_mantel.read_sw_with_build_id(target, build_id)
        resp = make_response(body, 200)
        resp.headers["Content-Type"] = mimetype + "; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    return send_from_directory(root, asset, mimetype=mimetype)


# ============================================================
#  CONN-8 — Connector-Übersicht-PWA (KI-Anbieter-Landschaft)
# ============================================================
#
# Spec-Anker: specs/platform/connector.md (CONN-1..CONN-8). Surface:
# /api/v1/seiten/connector/ (faellt unter den bestehenden nginx-^~ /api/v1/seiten/-
# Block — KEINE nginx-Aenderung; ein /seiten/connector/-Block existiert nicht).
# PUBLIC / Netz-Trust (auth.md AUTH-6, wie plan-einstellungen; haertet mit #948).
#
# EINE dynamische Route: die HTML-Shell. Sie SERVER-RENDERt das Aggregat
# (connector.py → tools.llm.telemetry_read, Track A) + ZD-Inventar (CONN-7, nur
# Status) als JSON-Blob in die Seite — KEIN separater /uebersicht-Sub-Endpunkt.
# Grund: der Manifest⇔Route-Eigentest (test_views_manifest_eigentest.py) verlangt,
# dass JEDE /api/v1/seiten/<sub>-Rule ein gelisteter View ist; ein Daten-Endpunkt
# waere ein Nicht-View und wuerde die Eltern-Uebersicht verschmutzen. Darum:
#   - HTML-Shell  → /api/v1/seiten/connector/  (gelisteter PWA-View, SREG-15)
#   - PWA-Assets  → /api/v1/seiten/static/connector/<datei>  (Flask-static,
#                   vom Eigentest via "/static/" ausgenommen — keine Extra-Rule)
# (PWA-First/fetch-Variante mit eigenem Endpunkt: V2, wenn der Eigentest einen
# Daten-Sub-Pfad zulaesst — Handoff-Flag fuer Nic.)


def _connector_asset_root():
    """Wurzelverzeichnis fuer Connector-Assets (seiten/static/connector/).

    Test-Naht: runtime["connector_asset_dir"].
    """
    override = runtime.get("connector_asset_dir") if isinstance(runtime, dict) else None
    if override:
        return override
    return os.path.join(os.path.dirname(__file__), "static", "connector")


def _connector_build_id():
    """build_id aus [index.html] (PWAM-4/5, pwa_mantel.REGISTRY['connector']).

    Override-aware: base_dir = _connector_asset_root() (runtime-Override bleibt
    erhalten). Verhalten unpetraendert gegenueber frueher (mtime(index.html)) —
    connector wird in #1266 nur mechanisch ueber die Lib geroutet, KEINE
    Verhaltensaenderung (Set-Vorbehalt: style.css erst im Angleich-Folgetrack).
    """
    return pwa_mantel.build_id_for("connector", _connector_asset_root())


def _connector_jsonl_source():
    """Telemetrie-Quelle fuer das Aggregat.

    Test-Naht: runtime["connector_jsonl_source"] (Pfad-String ODER Iterable von
    JSONL-Zeilen). Default leerer String → telemetry_read loest den ENV-Pfad auf.
    """
    src = runtime.get("connector_jsonl_source") if isinstance(runtime, dict) else None
    return src if src is not None else ""


@app.route("/api/v1/seiten/connector/", methods=["GET"])
def connector_view():
    """CONN-8: Connector-PWA — server-gerenderte HTML-Shell. PUBLIC (AUTH-6).

    Read-only. Baut das Aggregat (Track A) + ZD-Inventar (CONN-7, nur Status)
    via seiten/connector.py und bettet es als JSON-Blob (__CONNECTOR_DATA__) in
    die Shell — das JS rendert beide Tabellen + 7-Tage-Charts daraus. Kein
    PUT/POST/DELETE (V1 read-only).
    """
    import json as _json

    from seiten import connector as connector_modul

    # Test-Nahte: deterministisches Heute + injizierbares ZD-Slot-Inventar,
    # damit Tests den realen Store/heute nicht anfassen (Default None → selbst
    # aufgeloest).
    today = runtime.get("connector_today") if isinstance(runtime, dict) else None
    slot_names = runtime.get("connector_slot_names") if isinstance(runtime, dict) else None
    context = connector_modul.baue_context(
        _connector_jsonl_source(), today=today, slot_names=slot_names)

    root = _connector_asset_root()
    with open(os.path.join(root, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    # CONN-7: json.dumps der bereits geheimnis-freien Struktur. </script>-Guard,
    # damit ein etwaiger String den Inline-<script>-Block nicht schliesst.
    blob = _json.dumps(context, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("__CONNECTOR_DATA__", blob)
    html = html.replace("__BUILD_ID__", _connector_build_id())
    # PWAM-3 / CONN-8: SW-Scope aus REGISTRY — kein hartkodierter String.
    html = html.replace("__SW_SCOPE__", pwa_mantel.REGISTRY["connector"].sw_scope)

    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/api/v1/seiten/static/connector/sw.js", methods=["GET"])
def connector_sw_view():
    """CONN-8 / PWAM-3: Service-Worker mit build_id-Substitution + Scope-Header.

    Steht VOR dem Flask-static-Catch-all fuer /api/v1/seiten/static/ — Werkzeug
    gibt der vollstaendig-statischen Rule hoehere Prioritaet als dem
    <path:filename>-Muster (mehr Fixed-Parts gewinnt).

    Service-Worker-Allowed: REGISTRY['connector'].sw_scope — erlaubt dem Browser,
    den SW fuer /api/v1/seiten/connector/ zu registrieren, obwohl die SW-Datei
    selbst unter /api/v1/seiten/static/connector/ liegt (PWAM-3-Scope-Fix,
    T1365).

    Liegt unter /api/v1/seiten/static/... → vom views.json-Eigentest via
    '/static/'-Pruefregel ausgenommen (keine Extra-Rule in views.json noetig).
    """
    sw_path = os.path.join(_connector_asset_root(), "sw.js")
    if not os.path.isfile(sw_path):
        from flask import abort
        abort(404)
    build_id = _connector_build_id()
    body = pwa_mantel.read_sw_with_build_id(sw_path, build_id)
    scope = pwa_mantel.REGISTRY["connector"].sw_scope
    resp = make_response(body, 200)
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    resp.headers["Service-Worker-Allowed"] = scope
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/api/v1/seiten/mini-app-uebersicht", methods=["GET"])
def mini_app_uebersicht_view():
    """MAU-1: Telegram-Mini-App-Uebersichts-View — HTML fuer den Familien-Bot.

    Auth (MAD-7 / MAU-3): Authorization: tma <initData>-Header Pflicht.
    Fehlender oder ungueliger Header → 401. Nicht-Familienmitglied → 403.

    JS laedt das Inventar bei Boot via:
      GET /api/v1/seiten  (SREG-3, aggregiertes Inventar)
    und rendert zwei Accordion-Sektionen (MAU-4, RAT-31 E3 #1496 — Geraete-Paare entfernt):
      1. Mini Telegram Apps (typ: mini-app)
      2. Buddy-Seiten (typ: eltern)

    Cache-Buster (Mini-App-Cache-Buster-Pattern): build_id aus mtime der JS-Datei
    haengt am CSS+JS als ?v=... — Telegram cached Mini-App-Assets sonst aggressiv.
    Response-Header no-store zusaetzlich, damit jeder Open das HTML neu holt.
    """
    # MAD-7-konform: HTML-Render-Route lädt Skeleton OHNE Auth (Telegram-WebView
    # sendet beim Initial-Load keinen Header). JS macht platform.ensureAuth().
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    build_id = pwa_mantel.build_id_for("mini-app-uebersicht", static_dir)
    resp = make_response(render_template("mini-app-uebersicht.html", build_id=build_id))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/seiten/routine/anpassen/", methods=["GET"])
def routine_anpassen_view_trailing_slash():
    """ROUTINE-23 Trailing-Slash-Alias: GET /seiten/routine/anpassen/ → HTML (T1665).

    manifest.json traegt start_url: "/seiten/routine/anpassen/" — der PWA-Open
    nach Install laedt diese URL. Ohne diese Route landet der Nutzer in 404.
    """
    return routine_anpassen_view()


@app.route("/seiten/routine/anpassen", methods=["GET"])
def routine_anpassen_view():
    """ROUTINE-20 / ROUTINE-23: Eltern-Anpassen-Mini-App-View (T1665: PWA-Mantel).

    Auth (MAD-7 / T708-C): Authorization: tma <initData>-Header Pflicht.
    Fehlender oder ungültiger Header → 401. Nicht-Familienmitglied → 403.

    JS laedt Items und Config beim Boot via:
      GET /api/v1/routine/items  (ROUTINE-14, items-Liste)
      GET /api/v1/routine/config (ROUTINE-14, Zeit-Schluessel)
    nginx routet /api/v1/routine/... zum routine-Buddy (Port 5050).

    Cache-Buster (T728 Live-Iter): build_id aus mtime der JS-Datei haengt
    am CSS+JS als ?v=... — Telegram cached Mini-App-Assets sonst aggressiv
    und Iterationen werden im Phone nicht sichtbar (Befund Nic 2026-06-12).
    response-Header no-store zusaetzlich, damit jeder Open das HTML neu
    holt.

    PWA-Mantel (T1665 / ROUTINE-23): manifest.json + sw.js werden DYNAMISCH
    aus der Lib erzeugt (pwa_mantel.build_manifest / render_sw) — kein
    statisches manifest.json/sw.js auf Platte.
    """
    # MAD-7-konform: HTML-Render-Route lädt Skeleton OHNE Auth. JS macht ensureAuth().
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    build_id = pwa_mantel.build_id_for("routine", static_dir)
    # T1665: sw_scope aus REGISTRY — Template nutzt {{ sw_scope }} (analog plan).
    sw_scope = pwa_mantel.REGISTRY["routine"].sw_scope
    resp = make_response(render_template("routine-anpassen.html", build_id=build_id, sw_scope=sw_scope))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ============================================================
#  ROUTINE-23 (T1665) — PWA-Mantel-Asset-Auslieferung
# ============================================================
#
# Spec-Anker: specs/buddies/routine.md ROUTINE-20/23 (T1665 reduzierter Sweep).
# Surface:
#   GET /seiten/routine/anpassen/manifest.json — build_manifest() aus Lib.
#   GET /seiten/routine/anpassen/sw.js         — render_sw() aus Lib.
#   GET /seiten/routine/anpassen/icon-*.png    — statisch aus seiten/static/routine/.
#
# Auth: Route selbst ist public (HTML-Skeleton ohne Auth, MAD-7). SW + manifest
# sind technisch-public (Browser-Fetch credential-los wie bei plan).
# Icon-Assets: public (analog plan / einkauf).
#
# Manifest + sw.js kommen aus der Lib (pwa_mantel.REGISTRY['routine']) —
# KEIN manifest.json/sw.js auf Platte. Icons in seiten/static/routine/
# (V1-Platzhalter aus plan-Icons, eigenes Motiv als Mini-Folge-Ticket).

_ROUTINE_ANPASSEN_MIME = {
    ".json": "application/manifest+json",
    ".js":   "application/javascript",
    ".png":  "image/png",
}


def _routine_anpassen_asset_root():
    """Wurzelverzeichnis fuer Routine-Anpassen-PWA-Mantel-Icons (T1665).

    Liegt unter seiten/static/routine/ (nur Icons — manifest.json/sw.js sind
    Lib-generiert). Test-Naht: ueberschreibbar via runtime['routine_anpassen_asset_dir'].
    """
    override = runtime.get("routine_anpassen_asset_dir") if isinstance(runtime, dict) else None
    if override:
        return override
    return os.path.join(os.path.dirname(__file__), "static", "routine")


def _routine_anpassen_build_id():
    """build_id fuer den routine-SW aus [routine-anpassen.js, platform.js]
    (PWAM-4/5, pwa_mantel.REGISTRY['routine']).
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return pwa_mantel.build_id_for("routine", static_dir)


@app.route("/seiten/routine/anpassen/<path:asset>", methods=["GET"])
def routine_anpassen_asset_view(asset):
    """ROUTINE-23 / T1665: PWA-Mantel-Asset-Auslieferung ueber die Lib (PWML-1/2).

    - manifest.json → pwa_mantel.build_manifest(REGISTRY['routine']) (PWML-1).
    - sw.js         → pwa_mantel.render_sw('routine', build_id) (PWML-2), no-store.
    - icon-*.png    → statisch aus seiten/static/routine/ mit realpath-Traversal-Guard.
    """
    from flask import abort, send_from_directory

    cfg = pwa_mantel.REGISTRY["routine"]

    if asset == "manifest.json":
        resp = make_response(json.dumps(pwa_mantel.build_manifest(cfg)), 200)
        resp.headers["Content-Type"] = "application/manifest+json; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    if asset == "sw.js":
        build_id = _routine_anpassen_build_id()
        body = pwa_mantel.render_sw("routine", build_id=build_id)
        resp = make_response(body, 200)
        resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
        # Service-Worker-Allowed: sw_scope aus REGISTRY ueberdeckt die start_url.
        resp.headers["Service-Worker-Allowed"] = cfg.sw_scope
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    # Statische Icons aus seiten/static/routine/ mit Traversal-Guard.
    root = os.path.realpath(_routine_anpassen_asset_root())
    target = os.path.realpath(os.path.join(root, asset))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    if os.path.basename(target).startswith("_"):
        abort(404)

    ext = os.path.splitext(target)[1].lower()
    mimetype = _ROUTINE_ANPASSEN_MIME.get(ext, "application/octet-stream")
    return send_from_directory(root, asset, mimetype=mimetype)


# ============================================================
#  HSP-33 / T1681 — Hörspiel-Eltern-PWA (ESB-1..4 / PWAM-5)
# ============================================================
#
# Spec-Anker: specs/buddies/hoerspiel.md HSP-33 + conventions/eltern-seite.md ESB-1..4.
# Surface:
#   GET /seiten/hoerspiel/<kind_id>/eltern          — HTML-Shell (Template hoerspiel/)
#   GET /seiten/hoerspiel/<kind_id>/eltern/manifest.json — build_manifest() aus Lib
#   GET /seiten/hoerspiel/<kind_id>/eltern/sw.js         — render_sw() aus Lib
#   GET /seiten/hoerspiel/<kind_id>/eltern/icon-*.png    — aus hoerspiel/static/
#
# ESB-1 (PWAM-5): pwa_mantel.REGISTRY['hoerspiel-eltern'] — scope: /seiten/hoerspiel/.
# ESB-2: Datenrouten (config/alben/resume/themen) sind AUTH-3-hart (@require_init_data).
# ESB-3: hoerspiel/views.json traegt Eintrag mit zielgruppe: eltern (T1681).
# ESB-4: eltern.css traegt kein body-overflow:hidden (scrollbar, nicht Kiosk-Sorte).
#
# scope-Entscheidung (T1681): /seiten/hoerspiel/ deckt ALLE kind_id-Instanzen;
# start_url ist /seiten/hoerspiel/mia/eltern (repraesentativer kanonischer Pfad).
# eltern.js laedt kind_id aus location.pathname — kein Mantel-Fork pro Kind.
# Auth: HTML-Shell public (MAD-7: ensureAuth() im JS). SW/manifest: credential-los.
#
# Icons: hoerspiel/static/ (192/512/maskable, geteilt mit hoerspiel-player).
# Manifest + sw.js lib-generiert — KEIN manifest.json/sw.js auf Platte.

_HOERSPIEL_ELTERN_COMPONENT = "hoerspiel-eltern"

_HOERSPIEL_ELTERN_MIME = {
    ".json": "application/manifest+json",
    ".js":   "application/javascript",
    ".png":  "image/png",
}


def _hoerspiel_eltern_asset_root():
    """Asset-Wurzel fuer hoerspiel-eltern-Mantel-Icons (hoerspiel/static/).

    Geteilt mit hoerspiel-player (gleiche Icons). Test-Naht:
    runtime['hoerspiel_eltern_asset_dir'].
    """
    override = (runtime.get("hoerspiel_eltern_asset_dir")
                if isinstance(runtime, dict) else None)
    if override:
        return override
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "hoerspiel", "static")


def _hoerspiel_eltern_build_id():
    """build_id fuer den hoerspiel-eltern-SW aus [eltern.js, eltern.css]
    (PWAM-4/5, pwa_mantel.REGISTRY['hoerspiel-eltern']).
    """
    return pwa_mantel.build_id_for(_HOERSPIEL_ELTERN_COMPONENT, _hoerspiel_eltern_asset_root())


@app.route("/seiten/hoerspiel/<kind_id>/eltern", methods=["GET"])
def hoerspiel_eltern_view(kind_id: str):
    """HSP-33 / T1681: Hörspiel-Eltern-PWA-Shell (kind_id-tragend, ESB-1, PWAM-5).

    Auth (MAD-7): HTML-Skeleton ohne Auth, JS macht ensureAuth().
    Datenrouten sind AUTH-3-hart (@require_init_data, ESB-2).

    Template liegt in hoerspiel/templates/eltern.html (HSP-33: Wohnort im
    hoerspiel/-Modul). Rendered via absoluten Pfad analog anderen Mini-Apps.

    JS laedt beim Boot via:
      GET /api/v1/hoerspiel/<kind_id>/config  (HSP-34: Einstellungen)
      GET /api/v1/hoerspiel/<kind_id>/alben   (HSP-35: Folgen-Liste)
    nginx routet /api/v1/hoerspiel/... zum hoerspiel-Buddy (Port 5053).
    kind_id kommt aus location.pathname (eltern.js, T970).

    Cache-Buster: build_id aus pwa_mantel (eltern.js + eltern.css, PWAM-4/5).
    """
    # MAD-7-konform: HTML-Render-Route laed Skeleton OHNE Auth. JS macht ensureAuth().
    build_id = _hoerspiel_eltern_build_id()
    sw_scope = pwa_mantel.REGISTRY[_HOERSPIEL_ELTERN_COMPONENT].sw_scope

    # INST-1 (#1670): Instanz-Liste server-injiziert (analog hoerspiel_player_view).
    # </script>-Guard analog CONN-7.
    from markupsafe import Markup
    _instanzen_blob = json.dumps(
        _hsp_instanzen(), ensure_ascii=False
    ).replace("</", "<\\/")
    instanzen_json = Markup(_instanzen_blob)

    # Template aus hoerspiel/templates/ via absolutem Pfad.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hoerspiel_templates = os.path.join(repo_root, "hoerspiel", "templates")
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(hoerspiel_templates), autoescape=True)
    tmpl = env.get_template("eltern.html")
    html = tmpl.render(build_id=build_id, instanzen_json=instanzen_json, sw_scope=sw_scope,
                       kind_id=kind_id)

    resp = make_response(html, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/seiten/hoerspiel/<kind_id>/eltern/<path:asset>", methods=["GET"])
def hoerspiel_eltern_asset_view(kind_id: str, asset: str):
    """T1681 / ESB-1: PWA-Mantel-Asset-Auslieferung fuer hoerspiel-eltern (PWML-1/2).

    - manifest.json → pwa_mantel.build_manifest(REGISTRY['hoerspiel-eltern']) (PWML-1).
    - sw.js         → pwa_mantel.render_sw('hoerspiel-eltern', build_id) (PWML-2), no-store.
    - icon-*.png    → statisch aus hoerspiel/static/ mit realpath-Traversal-Guard.

    Auth: public (HTML-Shell public, MAD-7). SW/manifest: credential-los (Browser-Fetch).
    """
    from flask import abort, send_from_directory

    cfg = pwa_mantel.REGISTRY[_HOERSPIEL_ELTERN_COMPONENT]

    if asset == "manifest.json":
        resp = make_response(json.dumps(pwa_mantel.build_manifest(cfg)), 200)
        resp.headers["Content-Type"] = "application/manifest+json; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    if asset == "sw.js":
        build_id = _hoerspiel_eltern_build_id()
        body = pwa_mantel.render_sw(_HOERSPIEL_ELTERN_COMPONENT, build_id=build_id)
        resp = make_response(body, 200)
        resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
        # Service-Worker-Allowed: sw_scope (/seiten/hoerspiel/) deckt alle kind_id-Pfade.
        resp.headers["Service-Worker-Allowed"] = cfg.sw_scope
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    # Statische Icons aus hoerspiel/static/ mit Traversal-Guard.
    root = os.path.realpath(_hoerspiel_eltern_asset_root())
    target = os.path.realpath(os.path.join(root, asset))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    if os.path.basename(target).startswith("_"):
        abort(404)

    ext = os.path.splitext(target)[1].lower()
    mimetype = _HOERSPIEL_ELTERN_MIME.get(ext, "application/octet-stream")
    return send_from_directory(root, asset, mimetype=mimetype)


# ============================================================
#  HSP-47 — Hörspiel-Player-PWA (erster Voll-Konsument der PWA-Mantel-Lib)
# ============================================================
#
# Spec-Anker: specs/buddies/hoerspiel.md HSP-47 + specs/platform/pwa-mantel-lib.md
# (PWML-1..5). Surface:
#   GET /seiten/hoerspiel/player            — HTML-Shell (Template aus hoerspiel/)
#   GET /seiten/hoerspiel/player/<asset>    — manifest.json (build_manifest),
#       sw.js (render_sw + build_id), player.{css,js}/icon-*.png aus hoerspiel/static/.
# AUTH-2 Cookie-only (HSP-47, #1292 gebaut 2026-07-07). Kein tma-Fallback
# (PWA, kein Mini-App). Kein Loopback-Bypass (browser-only Route, kein
# interner Server-Caller — grep bestätigt keine internen Aufrufer).
# nginx: /seiten/hoerspiel/ → seiten:5042 deckt den Pfad (KEINE nginx-Änderung).
#
# Manifest + sw.js kommen aus der Lib (pwa_mantel.REGISTRY['hoerspiel-player']),
# NICHT von der Platte — deshalb kein manifest.json/sw.js in hoerspiel/static/.
# player.html/player.{css,js}/Icons liefert der hoerspiel-Buddy (Track B).

_HOERSPIEL_PLAYER_MIME = {
    ".json": "application/manifest+json",
    ".js":   "application/javascript",
    ".css":  "text/css",
    ".png":  "image/png",
}

_HOERSPIEL_PLAYER_COMPONENT = "hoerspiel-player"

# INST-1 (conventions/instanzen-config.md, #1656): die Instanz-Liste ist
# KEINE Code-Konstante mehr — sie kommt aus der Repo-Root-`instanzen.json`
# (tools.instanzen). Fehlt/kaputt die Datei, greift der eingebettete
# Loader-Default (INST-6). Feld-Mapping für den Player-Blob (HSP-49,
# window.__HSP_INSTANZEN__): kind_id = slug, name = display_name.
# foto_url bleibt None — tools.familie_client bietet keinen Foto-Zugang
# (FAM-8, stop_rule kein_familie_client) und foto_url steht nicht in
# instanzen.json (INST-2, genau vier Felder).
def _hsp_instanzen():
    """Player-Blob-Liste (kind_id/name/foto_url) aus instanzen.json (INST-1).

    Liest via tools.instanzen und mappt auf die vom player.js erwarteten
    Feldnamen. Reine Anzeige-Ableitung — kein Port/Route wird generiert (INST-3).
    """
    return [
        {"kind_id": e["slug"], "name": e["display_name"], "foto_url": None}
        for e in instanzen.lade_instanzen("hoerspiel")
    ]


def _hoerspiel_static_dir():
    """Asset-Wurzel des hoerspiel-Buddys (player.{css,js} + Icons, Track B).

    hoerspiel/static/ — der seiten-Service liest (nicht schreibt) daraus.
    Test-Naht: runtime['hoerspiel_player_asset_dir'].
    """
    override = (runtime.get("hoerspiel_player_asset_dir")
               if isinstance(runtime, dict) else None)
    if override:
        return override
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "hoerspiel", "static")


def _hoerspiel_player_template_dir():
    """Template-Wurzel des Hörspiel-Players (player.html, Track B).

    Test-Naht: runtime['hoerspiel_player_template_dir'].
    """
    override = (runtime.get("hoerspiel_player_template_dir")
               if isinstance(runtime, dict) else None)
    if override:
        return override
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "hoerspiel", "templates")


def _hoerspiel_player_build_id():
    """build_id aus dem Player-Source-Set [player.js, player.css] in
    hoerspiel/static/ (PWML-3, pwa_mantel.REGISTRY['hoerspiel-player'])."""
    return pwa_mantel.build_id_for(_HOERSPIEL_PLAYER_COMPONENT, _hoerspiel_static_dir())


@app.route("/seiten/hoerspiel/player", methods=["GET"])
def hoerspiel_player_view():
    """HSP-47/HSP-49: Hörspiel-Player-PWA — HTML-Render-Route.

    AUTH-2 Cookie-only (auth.md AUTH-2, #1292). Template liegt in
    hoerspiel/templates/player.html (Track B) und wird via absolutem Pfad
    gerendert — analog hoerspiel_eltern_view, aber OHNE dessen tma-Auth.

    Cache-Buster: build_id aus dem Player-Source-Set (PWML-3).

    Instanz-Liste (HSP-49 / HSP-43): window.__HSP_INSTANZEN__ wird als
    server-serialisierter JSON-Blob in den Template-Kontext eingebettet.
    Template: {{ instanzen_json }} — Markup-Objekt, kein HTML-Escape noetig.
    """
    # AUTH-2: Cookie-Gate (HSP-47, #1292). PWA ist browser-only — kein
    # tma-Fallback, kein Loopback-Bypass (keine internen Caller dieser Route).
    _bot_token = _get_bot_token()
    _cookie_val = request.cookies.get(_session_cookie.COOKIE_NAME)
    if not _bot_token:
        return ("", 401)
    _subject = _session_cookie.verify_session(_cookie_val, _bot_token)
    if _subject is None:
        return ("", 401)

    build_id = _hoerspiel_player_build_id()

    # HSP-49 / INST-1: Instanz-Blob — Quelle ist jetzt instanzen.json via
    # _hsp_instanzen() (eine Wahrheit, #1656). </script>-Guard analog CONN-7.
    from markupsafe import Markup
    _instanzen_blob = json.dumps(
        _hsp_instanzen(), ensure_ascii=False
    ).replace("</", "<\\/")
    instanzen_json = Markup(_instanzen_blob)

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(_hoerspiel_player_template_dir()), autoescape=True)
    tmpl = env.get_template("player.html")
    html = tmpl.render(build_id=build_id, instanzen_json=instanzen_json)

    resp = make_response(html, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    # Rolling-Refresh (auth.md AUTH-2, Nic-Option-B #1292): Cookie mit frischem
    # 90-Tage-exp neu setzen — jeder App-Start rollt vor, ITP-Drop abgefangen.
    resp.set_cookie(
        _session_cookie.COOKIE_NAME,
        _session_cookie.sign_session(_subject, _bot_token),
        **_session_cookie.session_cookie_kwargs(),
    )
    return resp


@app.route("/seiten/hoerspiel/player/<path:asset>", methods=["GET"])
def hoerspiel_player_asset_view(asset):
    """HSP-47: PWA-Mantel-Asset-Auslieferung über die Lib (PWML-1/2).

    AUTH-2 Cookie-only (auth.md AUTH-2, #1292). Alle Player-Assets benötigen
    einen gültigen xbuddy_session-Cookie — kein öffentliches Asset.

    - manifest.json → pwa_mantel.build_manifest(REGISTRY['hoerspiel-player'])
      (PWML-1: display:standalone, PNG-Icons 192/512/maskable).
    - sw.js        → pwa_mantel.render_sw(...) mit substituiertem build_id
      (PWML-2: zwei Knöpfe + __BUILD_ID__), no-store-Header.
    - player.{css,js}/icon-*.png → statisch aus hoerspiel/static/ mit
      realpath-Traversal-Guard (analog ESSEN-34); sonst 404.
    """
    # AUTH-2: Cookie-Gate (HSP-47, #1292). PWA ist browser-only — kein
    # tma-Fallback, kein Loopback-Bypass (keine internen Caller dieser Route).
    _bot_token = _get_bot_token()
    _cookie_val = request.cookies.get(_session_cookie.COOKIE_NAME)
    if (not _bot_token
            or _session_cookie.verify_session(_cookie_val, _bot_token) is None):
        return ("", 401)

    from flask import abort, send_from_directory

    cfg = pwa_mantel.REGISTRY[_HOERSPIEL_PLAYER_COMPONENT]

    if asset == "manifest.json":
        resp = make_response(json.dumps(pwa_mantel.build_manifest(cfg)), 200)
        resp.headers["Content-Type"] = "application/manifest+json; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    if asset == "sw.js":
        build_id = _hoerspiel_player_build_id()
        body = pwa_mantel.render_sw(_HOERSPIEL_PLAYER_COMPONENT, build_id=build_id)
        resp = make_response(body, 200)
        resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
        # Service-Worker-Allowed: REGISTRY['hoerspiel-player'].sw_scope — SW-Scope
        # darf ueber das Skript-Verzeichnis /seiten/hoerspiel/player/ hinaus das
        # Shell-Dokument /seiten/hoerspiel/player (OHNE Slash) decken. Ohne diesen
        # Header kontrolliert der SW die Seite nie -> offline alles tot (GAP-1).
        # (T1324: SSoT aus REGISTRY statt hartkodiertem String, analog CONN-8.)
        resp.headers["Service-Worker-Allowed"] = pwa_mantel.REGISTRY["hoerspiel-player"].sw_scope
        # sw.js fresh holen, sonst kein Update-Trigger.
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

    # Statische Player-Assets aus hoerspiel/static/ (Track B) mit Traversal-Guard.
    root = os.path.realpath(_hoerspiel_static_dir())
    target = os.path.realpath(os.path.join(root, asset))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    if os.path.basename(target).startswith("_"):
        abort(404)

    ext = os.path.splitext(target)[1].lower()
    mimetype = _HOERSPIEL_PLAYER_MIME.get(ext, "application/octet-stream")
    return send_from_directory(root, asset, mimetype=mimetype)


# ============================================================
#  SHELL-1..11 / SHELL-PWA — Heim-Shell PWA (Split-Layout, Pilot Mia, #1182)
# ============================================================
#
# Spec-Anker: specs/platform/heim-shell.md (SHELL-1..11 + SHELL-PWA, RAT-25).
# Surface: GET /shell/<panel_id> (HTML) + GET /shell/<panel_id>/<asset>
#   (manifest.json dynamisch; sw.js + icon-*.png aus seiten/static/shell/).
# LAN-only, KEIN AUTH-7/Phase-4-Rollout (SHELL-6, #948 bleibt Plan B).
# nginx routet /shell/ zum seiten-Service (PORT-2, Loopback 5042) — Deploy-Schritt.
#
# SHELL-3: Split-Layout — linke Rail 280px Iframe → /controller/app-panel/<panel_id>/,
#   rechts Buddy-Pane ohne statischen src (src per SSE-Swap, SHELL-4 RAT-31 E2).
#   Panel bleibt unpetraendert (PANEL-12 berechnet Grid-Geometrie adaptiv).
# SHELL-4: Same-device Live-Refresh — seiten-seitiger SSE-Stream + Ingest (RAT-31 E2).
#   KEIN Router-Fanout, KEIN display_id-Lookup mehr (SHELL-2 obsolet durch RAT-31).
# SHELL-5: rechtes Pane swappt nur iframe.src, keine displib-Kopie.
# SHELL-9: IDs aus Daten (URL), kein Hardcode im Code.
# SHELL-PWA: PWA-Mantel analog ESSEN-33..35 — Manifest (Icons+display:fullscreen+
#   scope /shell/), eigener SW (Scope /shell/, Service-Worker-Allowed-Header),
#   Asset-Route analog einkauf_asset_view. Kachel-Scaling shell-seitig via CSS.


def _lookup_display_id(panel_id):  # pragma: no cover
    """SHELL-2 TOMBSTONE — RAT-31 E6f-C (#1588): entfernt.

    Funktion ist tot (kein Produktions-Aufrufer). Bleibt als Stub damit
    monkeypatch.setattr(seiten_main, '_lookup_display_id', ...) in aelteren
    Tests (seiten/tests/test_build_id_registry.py) nicht AttributeError wirft.
    Loeschen sobald alle externen Test-Aufrufer bereinigt sind.
    """
    return None


_HARD_RESET_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Frisch laden</title></head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem;line-height:1.5">
<h1>App wird frisch geladen</h1>
<p id="s">Service-Worker und Zwischenspeicher werden geleert &mdash; dein Login (Cookie) bleibt erhalten.</p>
<script>
(function(){
  var s=document.getElementById('s');
  var TO="__TO__";
  (async function(){
    try{
      if('serviceWorker' in navigator){
        var regs=await navigator.serviceWorker.getRegistrations();
        await Promise.all(regs.map(function(r){return r.unregister();}));
      }
      if(window.caches){
        var keys=await caches.keys();
        await Promise.all(keys.map(function(k){return caches.delete(k);}));
      }
      s.textContent='Fertig \\u2014 lade frisch\\u2026';
    }catch(e){ s.textContent='Konnte nicht ganz leeren ('+e+') \\u2014 lade trotzdem neu\\u2026'; }
    setTimeout(function(){ location.replace(TO); }, 700);
  })();
})();
</script>
</body></html>"""


@app.route("/api/v1/seiten/reset", methods=["GET"])
# PUBLIC (AUTH-4): reiner Client-Reset (deregistriert ALLE Service-Worker +
# loescht ALLE Cache-Storage-Eintraege dieses Origins), keine Datenexposition.
# Muss auch bei klebendem/kaputtem SW laden -> liegt ausserhalb aller SW-Scopes
# + no-store. Der xbuddy_session-Cookie bleibt unberuehrt (separater Speicher).
# (#1461 — "wirklich echtes, hartes Neu-Laden von allem")
def hard_reset_purge():
    to = request.args.get("to", "/shell/mias-panel-01")
    # Open-Redirect-Schutz: nur eigene relative Pfade, Zeichen-Allowlist.
    to = "".join(c for c in to if c.isalnum() or c in "/_-")
    if not to.startswith("/") or to.startswith("//"):
        to = "/shell/mias-panel-01"
    resp = make_response(_HARD_RESET_HTML.replace("__TO__", to))
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ============================================================
#  SHELL-4 (RAT-31 E2) — Same-device Live-Refresh in seiten/
# ============================================================
#
# Verpflanzt aus router/main.py (ROU-22 SSE + POST /events tile_selected-Ingest),
# BEVOR der Router-Fanout stirbt (heim-shell.md E0-Banner, decisions/RAT-31).
# Kernunterschied zum Router: EIN Gerät = EIN Ziel — es gibt KEINEN
# routing.json-Lookup und KEINEN display_id-Key. Ein prozess-weiter Zustand +
# EINE Subscriber-Menge. Mehrere offene Shell-Tabs teilen sich per Ein-Gerät-
# Setzung denselben Stream (RAT-31 „ein Gerät für immer"). Reine Intra-Prozess-
# Verdrahtung (queue.Queue, threading.Lock) — kein Broker, keine Topics
# (E-DC-1 grenzt SSE vom verschobenen MQTT-Transport ab).

# RAT-35 (#1576/#1546): Shell-Zustand wird per ephemerer, geräte-anonymer `sid`
# gekeyed (client crypto.randomUUID() pro Shell-Dokument) — NICHT per panel_id
# (das bräuchte eine Registry und bräche RAT-31 „registry-frei"). So laufen Pi
# und Tablet mit derselben panel_id unabhängig: jedes Shell-Dokument hat seine
# eigene sid → eigene State-Session → eigener SSE-Fanout. Kein display_id-Lookup,
# kein routing.json — die sid IST der Kanal-Key, rein Intra-Prozess (queue.Queue).
#
# Struktur: sid → {'state': <shell_state|None>, 'subscribers': set[queue.Queue]}.
# Sessions entstehen lazy pro sid und werden GC'd, sobald ihr letzter Subscriber
# geht (kein Registry-Leak: anonyme sids akkumulieren sonst prozess-weit).
_shell_sessions: dict[str, dict] = {}
_shell_sessions_lock = threading.Lock()

# Fallback-sid für gecachte alte Shell-Dokumente OHNE ?sid= (vor #1546). Weicher,
# additiver Fallback: alle sid-losen Requests teilen sich diese eine Session —
# funktionsfähig, aber ohne Geräte-Isolation. KEIN Registry-Key (RAT-31).
_SHELL_LEGACY_SID = "legacy"

# Heartbeat: hält die Verbindung über nginx offen und lässt den Generator
# abgebrochene Clients erkennen (sonst bliebe die Queue für immer blockiert).
SHELL_SSE_HEARTBEAT_SECONDS = 15


def _shell_now_iso():
    """UTC-Zeitstempel im ROU-10-Format (sekundengenau, Z-Suffix)."""
    import datetime as _dt
    return (_dt.datetime.now(_dt.UTC)
            .replace(microsecond=0).isoformat().replace("+00:00", "Z"))


def _shell_session_for(sid):
    """Holt (oder legt lazy an) die State-Session einer sid. Muss unter
    _shell_sessions_lock aufgerufen werden."""
    sess = _shell_sessions.get(sid)
    if sess is None:
        sess = {"state": None, "subscribers": set()}
        _shell_sessions[sid] = sess
    return sess


def _shell_subscribe(sid):
    """Registriert eine neue Queue für die sid-Session (lazy angelegt)."""
    q = queue.Queue()
    with _shell_sessions_lock:
        _shell_session_for(sid)["subscribers"].add(q)
    return q


def _shell_unsubscribe(sid, q):
    """Entfernt die Queue aus der sid-Session; GC der Session, sobald ihr
    letzter Subscriber geht (sonst leaken anonyme sids prozess-weit)."""
    with _shell_sessions_lock:
        sess = _shell_sessions.get(sid)
        if sess is None:
            return
        sess["subscribers"].discard(q)
        if not sess["subscribers"]:
            del _shell_sessions[sid]


def _shell_publish(sid, shell_state):
    """Legt den neuen Zustand NUR in die Queues DIESER sid (kein Cross-Device-
    Broadcast — das ist der RAT-35-Kern: Pi und Tablet bleiben getrennt)."""
    with _shell_sessions_lock:
        sess = _shell_sessions.get(sid)
        subs = list(sess["subscribers"]) if sess is not None else []
    for q in subs:
        q.put(shell_state)


def _shell_sse_pack(shell_state):
    """Formatiert einen Shell-State als SSE-Nachricht (Analog ROU-22 sse_pack)."""
    return "data: " + json.dumps(shell_state, ensure_ascii=False) + "\n\n"


def _shell_event_stream(sid):
    """Generator für den Shell-SSE-Stream EINER sid (Analog ROU-22
    display_event_stream): liefert den aktuellen Zustand dieser sid beim
    Verbinden (falls gesetzt), danach jede Änderung. Heartbeats sind data-Events
    `{"type":"heartbeat"}` statt SSE-Comments, damit Mobile-Browser-EventSource
    sie als Lebenszeichen sieht (R6 Track-E 2026-06-18). Der Empfänger im Template
    ignoriert heartbeat-Typ.

    Race-Schluss (#1542 last-state-on-subscribe): Snapshot NACH _shell_subscribe(),
    damit ein POST, der vor dem Connect ins Leere broadcastet hat, beim Connect
    nachgeliefert wird. Snapshot vor der while-Schleife, nicht beim Generator-
    Aufbau — sonst liest man den Zustand vor der Queue-Registrierung (neue Race)."""
    q = _shell_subscribe(sid)
    try:
        # Snapshot NACH Subscribe lesen (load-bearing Reihenfolge):
        # Ein POST vor dem Connect setzt den sid-State, findet aber keine Queue
        # (empty set → Broadcast verpufft). Hier lesen wir den bereits gesetzten
        # Zustand nach → Pane lädt beim ersten Tap. Ist der Zustand None (Ruhe),
        # senden wir kein Geister-Event; die Heartbeat-Schleife hält die Leitung.
        with _shell_sessions_lock:
            sess = _shell_sessions.get(sid)
            _snapshot = sess["state"] if sess is not None else None
        if _snapshot is not None:
            yield _shell_sse_pack(_snapshot)
        while True:
            try:
                s = q.get(timeout=SHELL_SSE_HEARTBEAT_SECONDS)
            except queue.Empty:
                yield 'data: {"type":"heartbeat"}\n\n'
                continue
            yield _shell_sse_pack(s)
    finally:
        _shell_unsubscribe(sid, q)


def _adapt_shell_event(event):
    """SHELL-4: Validiert ein Shell-Ingest-Event (Analog router adapt_app_panel).

    Zwei Event-Typen (PANEL-6): `tile_selected` mit Pflichtfeldern `app`,
    `view` (Strings/Zahlen) und optional flachem `query`; `panel_cleared`
    (Ruhe-Zustand, kein Descriptor). Liefert (kind, descriptor) oder
    (None, fehler-string). Nur flache query-Werte (PANEL-7) — verschachtelte
    Objekte/Listen werden abgewiesen.
    """
    t = event.get("type")
    if t == "panel_cleared":
        return ("end", None), None
    if t == "tile_selected":
        if "app" not in event:
            return None, "app fehlt"
        if "view" not in event:
            return None, "view fehlt"
        app_val = event["app"]
        view_val = event["view"]
        if not isinstance(app_val, (str, int, float)) or isinstance(app_val, bool):
            return None, "app muss String oder Zahl sein"
        if not isinstance(view_val, (str, int, float)) or isinstance(view_val, bool):
            return None, "view muss String oder Zahl sein"
        query = event.get("query")
        if query is not None:
            if not isinstance(query, dict):
                return None, "query muss ein flaches Objekt sein"
            for k, v in query.items():
                if isinstance(v, bool) or not isinstance(v, (str, int, float)):
                    return None, ("query.%s muss String oder Zahl sein "
                                  "(keine verschachtelten Objekte/Listen)" % k)
        descriptor = {"app": app_val, "view": view_val}
        if query:
            descriptor["query"] = dict(query)
        return ("trigger", descriptor), None
    return None, 'unbekannter type "%s"' % t


def _apply_shell_trigger(sid, descriptor):
    """SHELL-4/RAT-35: setzt den Shell-Zustand DIESER sid aus dem Descriptor und
    publiziert ihn an deren SSE-Stream. payload.url per Konvention
    (render.build_panel_url, byte-gleich zum Router). KEIN routing.json/display_id-
    Lookup — die sid ist der Kanal (Analog router apply_panel_trigger, ohne den
    panels-Hop)."""
    url = render.build_panel_url(
        descriptor["app"], descriptor["view"], descriptor.get("query"))
    shell_state = {
        "descriptor": descriptor,
        "payload": {"url": url},
        "since": _shell_now_iso(),
    }
    with _shell_sessions_lock:
        _shell_session_for(sid)["state"] = shell_state
    _shell_publish(sid, shell_state)


def _apply_shell_end(sid):
    """SHELL-4/RAT-35: Ruhe-Zustand (panel_cleared) für DIESE sid — Zustand auf
    None, publizieren."""
    with _shell_sessions_lock:
        _shell_session_for(sid)["state"] = None
    _shell_publish(sid, None)


@app.route("/shell/<panel_id>/events", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-7b: Shell-Flotte gepairt (Nic/Mia-LAN) — hard enforced, wie /shell/<panel_id>.
def shell_events(panel_id):
    """SHELL-4 (RAT-31 E2 / RAT-35): SSE-Zustands-Stream des Shell-Panes, gekeyed
    per ephemerer `sid` (Query-Param `?sid=`, client crypto.randomUUID()).

    Analog ROU-22, aber OHNE routing.json/display_id-Match — die sid ist der
    Kanal (RAT-35): Pi und Tablet mit derselben `panel_id` bekommen dank
    unterschiedlicher sids getrennte Streams. `panel_id` bleibt load-bearing für
    Auth/URL-Symmetrie zu /shell/<panel_id>, ist aber NICHT der State-Key.
    Fehlt `sid` (gecachtes altes Shell-Dokument vor #1546), greift der weiche
    Fallback auf die "legacy"-sid — funktionsfähig, ohne Geräte-Isolation.
    same-origin unter der seiten-Origin (kein router-Hop).
    """
    sid = request.args.get("sid") or _SHELL_LEGACY_SID
    resp = app.response_class(_shell_event_stream(sid),
                              mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"  # T1542: nginx-Pufferung abschalten (Gürtel)
    return resp


@app.route("/shell/<panel_id>/events", methods=["POST"])
@require_dual_gate(mode="hard")  # AUTH-7b: Shell-Flotte gepairt — hard enforced (Ingest same-origin).
def shell_ingest(panel_id):
    """SHELL-4 (RAT-31 E2 / RAT-35): tile_selected-Ingest same-origin, publiziert
    an den Shell-SSE-Stream DIESER sid — OHNE router-Hop (Analog router POST
    /api/v1/events, aber ohne routing.json). Die linke Panel-Nav postet an die
    ingest_url, die das Shell-Template ihr mitgibt (inkl. `?sid=`) → die Nav
    braucht KEINE Änderung, sie folgt nur der URL.

    RAT-35: kein source_id/display_id-Match — die `sid` (Query-Param, gleicher
    weicher "legacy"-Fallback wie GET) bestimmt, welche Shell-Session getroffen
    wird; jedes valide tile_selected trifft genau ihren Zustand.
    """
    sid = request.args.get("sid") or _SHELL_LEGACY_SID
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON-Body fehlt oder ungültig"}), 400
    if "type" not in body:
        return jsonify({"error": "type ist Pflicht"}), 400
    adapted, err = _adapt_shell_event(body)
    if err:
        return jsonify({"error": err}), 400
    kind, descriptor = adapted
    if kind == "end":
        _apply_shell_end(sid)
        return "", 204
    _apply_shell_trigger(sid, descriptor)
    return "", 204


@app.route("/shell/<panel_id>", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-7b: Shell-Flotte gepairt (Nic/Mia-LAN) — hard enforced (T1448).
def heim_shell(panel_id):
    """SHELL-1: Heim-Shell Split-Layout — GET /shell/<panel_id> liefert HTML.

    LAN-only (SHELL-6). Live-Refresh same-origin ueber seiten/-SSE-Stream
    (SHELL-4, RAT-31 E2); kein Router-Fanout, kein display_id-Lookup mehr.
    IDs aus Daten, kein Hardcode (SHELL-9). Cache-Control no-store (Mini-App-
    Cache-Buster-Pattern).
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    build_id = pwa_mantel.build_id_for("shell", static_dir)  # PWAM-5-Registry (T1284-AC1)
    # T1324: sw_scope aus REGISTRY — Template nutzt {{ sw_scope }} statt hartkodiertem Literal.
    sw_scope = pwa_mantel.REGISTRY["shell"].sw_scope
    resp = make_response(render_template(
        "heim-shell.html",
        panel_id=panel_id,
        build_id=build_id,
        sw_scope=sw_scope,
    ))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/shell/<panel_id>/manifest.json", methods=["GET"])
# manifest.json bleibt public — Browser holt PWA-Manifeste credential-los (Fetch-Spec).
# Gegated 401 über den Funnel würde PWA-Install brechen (#1437). sw.js/Icons unberührt.
def heim_shell_manifest(panel_id):
    """SHELL-10 / SHELL-PWA: PWA-Manifest je panel_id (analog PWA-1 / ESSEN-33).

    start_url = /shell/<panel_id> — damit der PWA-Open nach Install die Shell
    fuer genau dieses Panel oeffnet. display=fullscreen (SHELL-PWA, AC1).
    scope=/shell/ — deckt alle Shell-Instanzen (SW-Scope passt).
    Icons unter /shell/<panel_id>/icon-*.png (shell_asset_view, SHELL-PWA AC1).
    panel_id kommt aus der URL, kein Hardcode (SHELL-9).
    """
    base = "/shell/" + panel_id
    manifest = {
        "name": "Heim-Shell · " + panel_id,
        "short_name": "Heim-Shell",
        "description": "Heim-Shell Panel-Navigator — " + panel_id,
        "start_url": base,
        "scope": "/shell/",
        "display": "fullscreen",
        "orientation": "landscape",
        "background_color": "#F5F1E8",
        "theme_color": "#47503C",
        "lang": "de",
        "icons": [
            {
                "src": base + "/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": base + "/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": base + "/icon-maskable-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }
    resp = make_response(json.dumps(manifest, ensure_ascii=False))
    resp.headers["Content-Type"] = "application/manifest+json"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── SHELL-PWA: Asset-Auslieferung (sw.js gated, icons/manifest public) ───────
#
# Spec-Anker: SHELL-PWA (specs/platform/heim-shell.md). Analog ESSEN-34/PLAN-35.
# Auth-Klassifikation (AUTH-4 / AUTH-7b, T1448-S3-fix):
#   manifest.json — heim_shell_manifest (public, AUTH-4): Browser-Fetch spec.
#   sw.js         — shell_sw_view (gated, AUTH-7b hard): eigene Literal-Route,
#                   Literal-Segment trumpft Variable → Flask bevorzugt diese Route.
#   icon-*.png    — shell_asset_view (public, AUTH-4): WebAPK-Installer credential-los.
#
# Flask-Routing-Prioritaet: Literal > String-Variable > Path-Variable.
# /shell/<panel_id>/sw.js (Literal "sw.js") wird IMMER vor
# /shell/<panel_id>/<path:asset> ausgewaehlt, wenn der Request auf sw.js endet.

_SHELL_MIME = {
    ".js":  "application/javascript",
    ".png": "image/png",
}


def _shell_asset_root():
    """Wurzelverzeichnis fuer Shell-PWA-Mantel-Assets (SHELL-PWA).

    Liegt unter seiten/static/shell/ (Lego-Trennung, analog einkauf/).
    Test-Naht: ueberschreibbar via runtime['shell_asset_dir'].
    """
    override = runtime.get("shell_asset_dir") if isinstance(runtime, dict) else None
    if override:
        return override
    return os.path.join(os.path.dirname(__file__), "static", "shell")


def _shell_build_id():
    """build_id aus [heim-shell.css] (PWAM-4/5, pwa_mantel.REGISTRY['shell']).

    Verhalten unpetraendert gegenueber frueher (mtime(heim-shell.css)).
    """
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return pwa_mantel.build_id_for("shell", static_dir)


def _is_shell_icon(asset):
    """Prueft, ob `asset` ein Shell-PWA-Icon ist (icon-*.png, AUTH-4-Public).

    WebAPK-Installer holt Manifest-Icons credential-los (Fetch-Spec) — diese
    Assets sind inhaltlich oeffentlich (AUTH-4-Kategorie analog manifest.json).
    sw.js und alle anderen Assets bleiben gated (hard, AUTH-7b).
    """
    import re as _re
    return bool(_re.match(r"^icon-[a-z0-9_-]+\.png$", asset))


@app.route("/shell/<panel_id>/sw.js", methods=["GET"])
@require_dual_gate(mode="hard")  # AUTH-7b hard (T1448-S3-fix): sw.js bleibt gated.
def shell_sw_view(panel_id):
    """SHELL-PWA: Service-Worker-Auslieferung (gated, AUTH-7b hard).

    Eigene Literal-Route fuer sw.js — Flask-Prioritaet: Literal-Segment ("sw.js")
    trumpft Path-Variable (<path:asset>), deshalb landen sw.js-Requests IMMER hier
    und NICHT in shell_asset_view. Das macht den require_dual_gate-Decorator per
    AST sichtbar (AUTH-9-Membran, T1448-S3-fix).

    Sonderfall sw.js:
      - __BUILD_ID__-Platzhalter wird ersetzt (SHELL-PWA Cache-Versionierung, PWAM-4/5).
      - Service-Worker-Allowed: /shell/ — erlaubt Scope jenseits der SW-Datei-URL.
      - Cache-Control no-store, damit der Browser den Worker bei Updates neu holt.
    """
    from flask import abort

    root = os.path.realpath(_shell_asset_root())
    target = os.path.realpath(os.path.join(root, "sw.js"))
    if not target.startswith(root + os.sep) and target != root:
        abort(404)
    if not os.path.isfile(target):
        abort(404)

    build_id = _shell_build_id()
    body = pwa_mantel.read_sw_with_build_id(target, build_id)
    resp = make_response(body, 200)
    resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
    # Service-Worker-Allowed: REGISTRY['shell'].sw_scope — SW-Scope darf
    # /shell/<panel_id>/ ueberschreiten. Ohne diesen Header erlaubt der Browser
    # nur Scope <= /shell/<panel_id>/. (T1324: SSoT aus REGISTRY, analog CONN-8.)
    resp.headers["Service-Worker-Allowed"] = pwa_mantel.REGISTRY["shell"].sw_scope
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app.route("/shell/<panel_id>/<path:asset>", methods=["GET"])
# PUBLIC (AUTH-4): icon-*.png — WebAPK-Installer holt Icons credential-los (Fetch-Spec,
# auth.md AUTH-4). Gegated 401 ueber den Funnel bricht PWA-Install (#1437, T1448-S2).
# sw.js wird von shell_sw_view (Literal-Route, gated) bedient — nicht hier.
# manifest.json wird von heim_shell_manifest bedient — nicht hier.
# AST-Membran: shell_sw_view traegt require_dual_gate (sichtbar per AUTH-9-Test);
#   shell_asset_view ist als AUTH-4-Public-Route explizit ausgenommen (test_auth_decorator_copetrage.py).
def shell_asset_view(panel_id, asset):
    """SHELL-PWA: PWA-Icon-Auslieferung (public, AUTH-4, analog ESSEN-34 / PLAN-35).

    Bedient /shell/<panel_id>/icon-*.png (und weitere statische Shell-Assets, falls
    kuenftig ergaenzt). sw.js wird per Literal-Route shell_sw_view gated ausgeliefert
    (Flask-Prioritaet: Literal > Path-Variable). manifest.json geht an heim_shell_manifest.

    Path-Traversal-Schutz via realpath-Check (analog einkauf_asset_view).
    Kein Gate-Decorator: AUTH-4-Public-Kategorie (WebAPK credential-los).
    """
    from flask import abort, send_from_directory

    # Manifest wird von heim_shell_manifest bedient — diese Route dient es nicht.
    if asset == "manifest.json":
        abort(404)
    # sw.js wird von shell_sw_view (Literal-Route, gated) bedient.
    # Flask routet sw.js-Requests dorthin; dieser Guard ist defensiv.
    if asset == "sw.js":
        abort(404)

    root = os.path.realpath(_shell_asset_root())
    target = os.path.realpath(os.path.join(root, asset))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    if os.path.basename(target).startswith("_"):
        abort(404)

    ext = os.path.splitext(target)[1].lower()
    mimetype = _SHELL_MIME.get(ext, "application/octet-stream")
    return make_response(send_from_directory(root, asset, mimetype=mimetype))


# ============================================================
#  App-Panel-Serving (SREG-17 / RAT-31 E6b, #1564)
# ============================================================
#
# Spec-Anker: specs/platform/seiten-registry.md (SREG-17) + specs/platform/app-panel.md.
# Verlagert von router/main.py (ROU-24/ROU-27/PBE-1/PBE-2 — dortiger Code stirbt
# #1568) nach seiten, damit /shell/<id> und /controller/app-panel/<id>/ same-origin
# aus EINEM Service kommen (SHELL-3 Rail-Iframe, kein Cross-Origin-Cookie-Jar).
#
# Serving-Vertrag (1:1 vom Router uebernommen):
#   GET /controller/app-panel/<panel_id>/            → index.html (Token-Subst PANEL-2/IDENT-5)
#   GET /controller/app-panel/<panel_id>            → 301 auf /<id>/ (Trailing-Slash, relative Assets)
#   GET /controller/app-panel/<panel_id>/config.json → PROXY panel(5041) /api/v1/panels/<id>/config.json
#                                                       + LKG-Cache + Code-Default-Fallback (DCOMP-3/PANEL-8)
#   GET .../tiles.json                               → PROXY dito (LKG)
#   GET .../bearbeiten[.js|.css]                     → PROXY panel(5041) /controller/app-panel/<id>/<sicht>
#                                                       (KEIN LKG, 404/502 durchgereicht, PBE-1/PBE-2)
#   GET .../sw.js                                    → Statik + __BUILD_ID__-Subst + no-cache
#   GET .../<asset>                                  → Statik aus controller/app-panel/ (realpath-Traversal-Schutz)
#
# DCOMP-1: seiten liest NIE panels.json direkt — config/tiles kommen ueber HTTP
# vom panel-Service. `from panel import …` ist verboten.

# controller/app-panel/-Statik liegt im Repo, Schwester von seiten/ unter der
# Repo-Wurzel (_REPO_ROOT). Analog Router DEFAULT_APP_PANEL_DIR.
_DEFAULT_APP_PANEL_DIR = os.path.normpath(
    os.path.join(_REPO_ROOT, "controller", "app-panel"))
_DEFAULT_CONTROLLER_SHARED_DIR = os.path.normpath(
    os.path.join(_REPO_ROOT, "controller", "_shared"))
_DEFAULT_DISPLAY_SHARED_DESIGN_DIR = os.path.normpath(
    os.path.join(_REPO_ROOT, "display", "_shared", "design"))

# Sichten, die an den panel-Service geproxt + Last-Known-Good-gecacht werden
# (SREG-17 / ROU-27, 1:1 vom Router).
_PANEL_PROXY_VIEWS = frozenset({"config.json", "tiles.json"})

# Editor-Seite + Assets — Proxy ohne LKG, 404 wird durchgereicht (PBE-1/PBE-2).
_PANEL_BEARBEITEN_VIEWS = frozenset({"bearbeiten", "bearbeiten.js", "bearbeiten.css"})

_PANEL_BEARBEITEN_CONTENT_TYPES = {
    "bearbeiten":     "text/html; charset=utf-8",
    "bearbeiten.js":  "application/javascript; charset=utf-8",
    "bearbeiten.css": "text/css; charset=utf-8",
}

# Code-Default-Fallback, wenn der panel-Service nie erreichbar war und kein
# LKG-Snapshot vorliegt (PANEL-8, stiller Fallback — kein Crash).
_PANEL_CODE_DEFAULTS = {
    "config.json": b"{}",
    "tiles.json":  b"[]",
}

_PANEL_PROXY_TIMEOUT = 5

# Content-Type-Mapping fuer Statik-Assets (analog Router _CONTROLLER_MIME).
_APP_PANEL_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js":   "application/javascript",
    ".json": "application/manifest+json",
    ".png":  "image/png",
    ".css":  "text/css",
    ".svg":  "image/svg+xml",
    ".mp3":  "audio/mpeg",
}

# LKG-Cache fuer die Proxy-Sichten (config/tiles). Zugriff aus Flask-Threads → Lock.
_panel_lkg_cache: dict = {}
_panel_lkg_lock = threading.Lock()


def _app_panel_dir():
    """Wurzelverzeichnis der App-Panel-Statik (controller/app-panel/).

    Test-Naht: ueberschreibbar via runtime['app_panel_dir'] (analog
    _shell_asset_root, main.py). Default: Repo-Schwester controller/app-panel/.
    """
    override = runtime.get("app_panel_dir") if isinstance(runtime, dict) else None
    return override or _DEFAULT_APP_PANEL_DIR


def _panel_service_base():
    """Origin-Basis des panel-Service (SREG-17). Runtime-Wert (panel_service_url),
    Default http://127.0.0.1:5041 (PORT-2)."""
    return runtime.get("panel_service_url") or "http://127.0.0.1:5041"


def _app_panel_build_id():
    """PANEL-14: build_id aus max(mtime) des cache-relevanten Runtime-Asset-Satzes
    (app.js, style.css, sw.js, manifest.json, silent.mp3, controller/_shared/config.js,
    display/_shared/design/tokens.css). 1:1 vom Router uebernommen — der Service-Worker
    precacht config.js + tokens.css, deshalb muessen sie in die build_id einfliessen,
    sonst bleibt ein geaendertes Token-Asset unsichtbar. OSError-Fallback: '0'."""
    panel_dir = _app_panel_dir()
    asset_paths = [
        os.path.join(panel_dir, "app.js"),
        os.path.join(panel_dir, "style.css"),
        os.path.join(panel_dir, "sw.js"),
        os.path.join(panel_dir, "manifest.json"),
        os.path.join(panel_dir, "silent.mp3"),
        os.path.join(_DEFAULT_CONTROLLER_SHARED_DIR, "config.js"),
        os.path.join(_DEFAULT_DISPLAY_SHARED_DESIGN_DIR, "tokens.css"),
    ]
    try:
        return str(int(max(os.path.getmtime(p) for p in asset_paths)))
    except OSError:
        return "0"


def _proxy_panel_view(panel_id, sicht):
    """SREG-17 / ROU-27: holt config.json oder tiles.json vom panel-Service und
    liefert (body_bytes, content_type). Erfolg frischt den LKG-Cache; Ausfall
    (Timeout/5xx/Connection) greift auf den LKG-Snapshot zurueck, fehlt auch der,
    kommt der Code-Default (PANEL-8, kein Crash). Monkeypatch-bare Test-Naht
    Monkeypatch-bare Test-Naht mit LKG. `sicht` ∈ _PANEL_PROXY_VIEWS."""
    url = "%s/api/v1/panels/%s/%s" % (_panel_service_base(), panel_id, sicht)
    cache_key = (panel_id, sicht)
    content_type = "application/json"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=_PANEL_PROXY_TIMEOUT) as resp:
            if resp.status >= 400:
                raise urllib.error.HTTPError(
                    url, resp.status, "panel-Service Fehler", {}, None)
            body = resp.read()
        with _panel_lkg_lock:
            _panel_lkg_cache[cache_key] = (body, content_type)
        return body, content_type
    except Exception as exc:
        logging.warning(
            "SREG-17: panel-Service nicht erreichbar (%s/%s): %s — LKG/Fallback",
            panel_id, sicht, exc)
    with _panel_lkg_lock:
        cached = _panel_lkg_cache.get(cache_key)
    if cached is not None:
        return cached
    return _PANEL_CODE_DEFAULTS[sicht], content_type


def _proxy_panel_bearbeiten(panel_id, sicht):
    """PBE-1/PBE-2: holt bearbeiten / bearbeiten.js / bearbeiten.css vom
    panel-Service und liefert (body_bytes, content_type, status_code).

    KEIN LKG, kein Code-Default: ein 404 vom panel-Service wird als (body, ct, 404)
    durchgereicht (Browser bekommt das korrekte HTTP-Signal). Netz-Fehler / 5xx
    liefern 502. Die Editor-Seite haengt am /controller/app-panel/-Pfad des
    panel-Service (nicht /api/v1/panels/) — Produktions-Bug-Lehre aus T459."""
    url = "%s/controller/app-panel/%s/%s" % (_panel_service_base(), panel_id, sicht)
    content_type = _PANEL_BEARBEITEN_CONTENT_TYPES.get(sicht, "application/octet-stream")
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=_PANEL_PROXY_TIMEOUT) as resp:
            body = resp.read()
        return body, content_type, 200
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            body = exc.read() if hasattr(exc, "read") else b""
            return body, "application/json", 404
        logging.warning(
            "PBE proxy: panel-Service antwortet mit %s fuer %s/%s",
            exc.code, panel_id, sicht)
        return b"", "application/json", 502
    except Exception as exc:
        logging.warning(
            "PBE proxy: panel-Service nicht erreichbar (%s/%s): %s",
            panel_id, sicht, exc)
        return b"", "application/json", 502


def _render_app_panel_index(panel_id):
    """PANEL-2 / IDENT-5: liefert index.html mit der Panel-Identitaet als
    __PANEL_ID__-Token (Server-side-Identitaet, kein Roundtrip) und der aktuellen
    build_id fuer alle __BUILD_ID__-Asset-URLs (PANEL-14). 1:1 vom Router.

    INST-1 (#1656): __HSP_INSTANZEN_JSON__ wird durch die HSP-Slug-Liste aus
    instanzen.json ersetzt (window.__HSP_INSTANZEN__), damit app.js die Liste
    liest statt sie hartzukodieren (Drift-Fix: emil erscheint). Nur slugs —
    keine Ports/Origins (INST-3)."""
    index_path = os.path.join(_app_panel_dir(), "index.html")
    with open(index_path, encoding="utf-8") as fh:
        html = fh.read()
    build_id = _app_panel_build_id()
    # HSP-Slug-Liste als JSON-Array. </script>-Guard analog CONN-7.
    _hsp_slugs = [e["slug"] for e in instanzen.lade_instanzen("hoerspiel")]
    _hsp_blob = json.dumps(_hsp_slugs, ensure_ascii=False).replace("</", "<\\/")
    return (html
            .replace("__PANEL_ID__", panel_id, 1)
            .replace("__HSP_INSTANZEN_JSON__", _hsp_blob)
            .replace("__BUILD_ID__", build_id))


def _send_app_panel_asset(rel_path):
    """Statik-Auslieferung aus controller/app-panel/ mit realpath-Traversal-Schutz
    (Defense in Depth, analog shell_asset_view / Router _send_app_panel_asset)."""
    from flask import abort, send_from_directory

    root = os.path.realpath(_app_panel_dir())
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _APP_PANEL_MIME.get(ext, "application/octet-stream")
    return send_from_directory(root, rel_path, mimetype=mime)


@app.route("/controller/app-panel/<panel_id>", methods=["GET"])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (App-Panel-Index-no-slash)
def app_panel_index_no_slash(panel_id):
    # Relative Asset-Pfade in index.html (./app.js …) brauchen den Trailing-Slash,
    # sonst resolvt der Browser ./ auf den Parent (301 → /<id>/, HTTP-Standard).
    return redirect("/controller/app-panel/" + panel_id + "/", code=301)


@app.route("/controller/app-panel/<panel_id>/", methods=["GET"])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (App-Panel-Index)
def app_panel_index_slash(panel_id):
    """PANEL-2: index.html mit Panel-Identitaet + build_id (SREG-17, #1564)."""
    return _render_app_panel_index(panel_id), 200, {
        "Content-Type": "text/html; charset=utf-8"}


@app.route("/controller/app-panel/<panel_id>/<path:asset>", methods=["GET"])
@require_dual_gate(mode=_AUTH_MODE)  # AUTH-7b: Cookie-only-hart (RAT-32), ENV-getoggelt (App-Panel-Assets)
def app_panel_asset(panel_id, asset):
    """SREG-17 (#1564): App-Panel-Asset-Auslieferung.

    config.json/tiles.json → Proxy an panel-Service + LKG (ROU-27/PANEL-8).
    bearbeiten* → Proxy ohne LKG, 404/502 durchgereicht (PBE-1/PBE-2).
    sw.js → Statik + __BUILD_ID__-Subst + no-cache (PANEL-14).
    sonst → Statik aus controller/app-panel/ (realpath-Traversal-Schutz).
    """
    from flask import Response, abort

    if asset in _PANEL_PROXY_VIEWS:
        body, content_type = _proxy_panel_view(panel_id, asset)
        return Response(body, status=200, mimetype=content_type)
    if asset in _PANEL_BEARBEITEN_VIEWS:
        body, content_type, status = _proxy_panel_bearbeiten(panel_id, asset)
        return Response(body, status=status, mimetype=content_type)
    if asset == "sw.js":
        # __BUILD_ID__-Subst + no-cache, damit der Browser den neuen Worker holt.
        # Defense-in-Depth-Traversal-Schutz analog _send_app_panel_asset.
        root = os.path.realpath(_app_panel_dir())
        target = os.path.realpath(os.path.join(root, "sw.js"))
        if not (target == root or target.startswith(root + os.sep)):
            abort(404)
        if not os.path.isfile(target):
            abort(404)
        with open(target, encoding="utf-8") as fh:
            body = fh.read().replace("__BUILD_ID__", _app_panel_build_id())
        resp = Response(body, status=200)
        resp.headers["Content-Type"] = "application/javascript; charset=utf-8"
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp
    return _send_app_panel_asset(asset)


# ============================================================
#  controller/_shared — PWA-übergreifende Helper (ROU-23, RAT-31 E6f-A, #1582)
# ============================================================

def _send_controller_shared_asset(rel_path):
    """Statik-Auslieferung aus controller/_shared/ mit realpath-Traversal-Schutz
    (Defense in Depth, analog _send_app_panel_asset / Router _send_shared_asset).
    ROU-23: PWA-übergreifender Helper-Pfad, z.B. config.js."""
    from flask import abort, send_from_directory

    root = os.path.realpath(_DEFAULT_CONTROLLER_SHARED_DIR)
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _APP_PANEL_MIME.get(ext, "application/octet-stream")
    return send_from_directory(root, rel_path, mimetype=mime)


@app.route("/controller/_shared/<path:asset>", methods=["GET"])
# ROU-23: /controller/_shared/<asset> — ungegated statischer Asset-Pfad,
# analog zum Router (router/main.py:1181 — kein require_dual_gate).
# config.js wird vom Service-Worker precacht und von allen Panels geladen,
# bevor ein Auth-Cookie gesetzt ist; ein Gate würde den SW-Precache brechen.
def controller_shared_asset(asset):
    """ROU-23 / RAT-31 E6f-A (#1582): /controller/_shared/<asset> aus controller/_shared/.
    PWA-übergreifende Helper (config.js). 1:1 vom Router nach seiten verlagert."""
    return _send_controller_shared_asset(asset)


# ============================================================
#  display/_shared/design — geteilte Design-Tokens (ROU-30, RAT-31 E6f-A, #1582)
# ============================================================

def _send_display_shared_design_asset(rel_path):
    """Statik-Auslieferung aus display/_shared/design/ mit realpath-Traversal-Schutz
    (Defense in Depth, analog _send_controller_shared_asset / Router _send_design_asset).
    ROU-30 / DTOK-1 / DTOK-2: geteilter Design-Token-Strang (tokens.css)."""
    from flask import abort, send_from_directory

    root = os.path.realpath(_DEFAULT_DISPLAY_SHARED_DESIGN_DIR)
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _APP_PANEL_MIME.get(ext, "application/octet-stream")
    return send_from_directory(root, rel_path, mimetype=mime)


@app.route("/display/_shared/design/<path:asset>", methods=["GET"])
# ROU-30: /display/_shared/design/<asset> — ungegated statischer Asset-Pfad,
# analog zum Router (router/main.py:1220 — kein require_dual_gate).
# tokens.css wird vom Service-Worker precacht und von JEDEM Buddy-View geladen;
# ein Gate würde den SW-Precache und nicht-authentifizierte Display-Views brechen.
def display_shared_design_asset(asset):
    """ROU-30 / DTOK-1 / DTOK-2 / RAT-31 E6f-A (#1582): /display/_shared/design/<asset>
    aus display/_shared/design/. Geteilter Design-Token-Strang (tokens.css).
    1:1 vom Router nach seiten verlagert."""
    return _send_display_shared_design_asset(asset)


# ============================================================
#  display/_shared/icons — Icon-Bibliothek (ROU-26, RAT-31 E6f-B, #1586)
# ============================================================
#
# Spec-Anker: specs/platform/router.md ROU-26, specs/platform/icons.md ICONS-5.
# Verlagert vom Router (router/main.py:1188-1236) nach seiten, damit der seiten-
# Service die Icon-Bibliothek + die Stichwort-Suche (ROU-31) unter demselben
# Origin serviert. Der Router-seitige Code lebt bis #1568 als toter Zwilling.
#
# Die icon-root ist ein Per-Instanz-Wert (ICONS-2, Default /home/buddy/apps/icons/);
# seiten laeuft als User buddy und liest die icon-root problemlos — analog Router.
# Kein nginx-alias (scheiterte an 0700-Home-Permission, #135).
#
# ROU-31 / ICONS-7: Lazy-Cache fuer pictogram_cache.json (Wort→ID).
# Wird beim ersten Zugriff oder bei Wechsel der icon-root befuellt.
# Zugriff aus Flask-Threads → Lock (analog Router).

# ROU-26 / ICONS-2: Default-icon-root (Per-Instanz, ausserhalb des Repos).
DEFAULT_ICON_ROOT = "/home/buddy/apps/icons/"

_pictogram_cache: dict = {}
_pictogram_cache_root: str = ""
_pictogram_cache_lock = threading.Lock()

_ICONS_SUCHE_MAX_CAP = 50  # obere Klemme fuer den max-Parameter (ICONS-7)

# Content-Type-Mapping fuer icon-Assets (PNG + Fallback).
_ICON_MIME = {
    ".png": "image/png",
    ".json": "application/json",
}


def _icon_root():
    """ROU-26 / RAT-31 E6f-B: konfigurierbare icon-root (ICONS-2).

    Leer = DEFAULT_ICON_ROOT. Wert kommt aus runtime['icon_root'] (via configure()
    oder Test-Naht). 1:1 analog icon_root() in router/main.py:1140-1142.
    """
    return runtime.get("icon_root") or DEFAULT_ICON_ROOT


def _send_icon_asset(rel_path):
    """ROU-26: Statik-Auslieferung aus der icon-root mit realpath-Traversal-Schutz.

    Defense in Depth: werkzeug safe_join (via send_from_directory) +
    expliziter realpath-Check gegen Path-Traversal. 1:1 vom Router
    (router/main.py:1188-1200).
    """
    from flask import abort, send_from_directory

    root = os.path.realpath(_icon_root())
    target = os.path.realpath(os.path.join(root, rel_path))
    if target != root and not target.startswith(root + os.sep):
        abort(404)
    if not os.path.isfile(target):
        abort(404)
    ext = os.path.splitext(target)[1].lower()
    mime = _ICON_MIME.get(ext, "application/octet-stream")
    return send_from_directory(root, rel_path, mimetype=mime)


@app.route("/display/_shared/icons/<path:asset>", methods=["GET"])
# ROU-26 / ICONS-5: ungegated statischer Asset-Pfad, analog zum Router
# (router/main.py:1230-1236 — kein require_dual_gate). Icons werden von
# Display-Views credential-los geladen; ein Gate wuerde Kinder-Displays brechen.
def display_shared_icon(asset):
    """ROU-26 / URL-16 / ICONS-5 / RAT-31 E6f-B (#1586):
    /display/_shared/icons/<asset> aus der icon-root.

    1:1 vom Router nach seiten verlagert. Die icon-root ist konfigurierbar
    via runtime['icon_root'] / ENV ICON_ROOT / CLI --icon-root."""
    return _send_icon_asset(asset)


def _load_pictogram_cache():
    """ROU-31 / ICONS-7: Liefert den Wort→ID-Cache aus pictogram_cache.json.

    Lazy: wird beim ersten Aufruf oder bei geaenderter icon-root geladen.
    Gibt ein leeres Dict zurueck, wenn die Datei fehlt (Icon-root noch nicht
    geseedet — kein Fehler, Suche liefert dann []). Thread-sicher via Lock.
    1:1 vom Router (router/main.py:1239-1259).
    """
    global _pictogram_cache, _pictogram_cache_root
    current_root = _icon_root()
    with _pictogram_cache_lock:
        if _pictogram_cache_root == current_root and _pictogram_cache:
            return _pictogram_cache
        cache_path = os.path.join(current_root, "pictogram_cache.json")
        try:
            with open(cache_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        _pictogram_cache = data
        _pictogram_cache_root = current_root
        return _pictogram_cache


def _score_match(needle: str, word: str) -> float:
    """Match-Score: exact > prefix > word-boundary > substring.

    1:1 vom Router (router/main.py:1262-1282).
    """
    needle = needle.lower()
    w = word.lower()
    if needle not in w:
        return 0.0
    if w == needle:
        return 1000.0
    if w.startswith(needle):
        return 400.0 + 100.0 / max(len(w), 1)
    if (" " + needle) in w or ("-" + needle) in w:
        return 100.0 + 50.0 / max(len(w), 1)
    return 1.0 + 1.0 / max(len(w), 1)


@app.route("/api/v1/icons/suche", methods=["GET"])
def icons_suche():
    """ROU-31 / ICONS-7 / URL-4 / RAT-31 E6f-B (#1586):
    Stichwort-Suche ueber den lokalen Icon-Cache.

    GET /api/v1/icons/suche?q=<stichwort>&max=<n>
    → 200, JSON [{id: int, url: str}], nur IDs mit lokalem PNG.
    400 ohne q. Leere Treffer → 200 [].

    1:1 vom Router (router/main.py:1285-1370) nach seiten verlagert.
    Ungated: Suche wird von Display-Views (keine Cookie-Auth) genutzt.
    """
    q = request.args.get("q")
    if q is None:
        abort(400)

    try:
        max_results = int(request.args.get("max", 3))
    except (ValueError, TypeError):
        max_results = 3
    max_results = max(1, min(max_results, _ICONS_SUCHE_MAX_CAP))

    try:
        min_score = float(request.args.get("min_score", 100))
    except (ValueError, TypeError):
        min_score = 100.0

    tokens = q.split()
    if not tokens:
        return jsonify([])

    cache = _load_pictogram_cache()

    score: dict = {}
    token_hits: dict = {}
    first_seen: dict = {}
    for _ti, token in enumerate(tokens):
        matched_this_token: set = set()
        for idx, (word, icon_id) in enumerate(cache.items()):
            if icon_id in matched_this_token:
                continue
            match_score = _score_match(token, word)
            if match_score > 0:
                matched_this_token.add(icon_id)
                if icon_id not in first_seen:
                    first_seen[icon_id] = idx
                score[icon_id] = score.get(icon_id, 0.0) + match_score
                token_hits[icon_id] = token_hits.get(icon_id, 0) + 1

    qualified_ids = [i for i in score if score[i] >= min_score]

    sorted_ids = sorted(
        qualified_ids,
        key=lambda i: (-token_hits[i], -score[i], first_seen[i]),
    )

    root = os.path.realpath(_icon_root())
    results = []
    for icon_id in sorted_ids:
        if len(results) >= max_results:
            break
        rel = os.path.join("arasaac", f"{icon_id}.png")
        target = os.path.realpath(os.path.join(root, rel))
        if not (target == root or target.startswith(root + os.sep)):
            continue
        if os.path.isfile(target):
            results.append({
                "id": icon_id,
                "url": f"/display/_shared/icons/arasaac/{icon_id}.png",
            })

    return jsonify(results)


# ============================================================
#  Entrypoint
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1): nur die Werte, die der Service-Start braucht.
# Familienspezifische Daten gibt es hier keine — das Inventar wird aggregiert,
# nicht handgepflegt; `inventar.json` ist abgeleiteter Cache, kein Per-Instanz-
# Stammdatum.


# ── Health-Check (SVC-1) ─────────────────────────────────────────────────

@app.route("/healthz", methods=["GET"])
def healthz():
    """SVC-1: Health-Endpoint — liefert immer 200 + OK."""
    return jsonify({"ok": True}), 200


RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5042,
    "log_level":   "INFO",
    "ttl":         30,
}


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Seiten-Registry V1")
    p.add_argument("--root", help="Repo-Wurzel für die Manifest-Discovery (SREG-2)")
    p.add_argument("--inventar", default="inventar.json",
                   help="Pfad zum gecachten Inventar (SREG-3)")
    p.add_argument("--ttl", type=int, help="Inventar-TTL in Sekunden (SREG-3)")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level",
                   help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key",  help="TLS-Key (optional, für HTTPS-Modus)")
    # SREG-7: Display-URL-Origins für die SREG-12-Übersichts-Seite.
    # Können auch via ENV gesetzt werden (SEITEN_HEIM_ORIGIN /
    # SEITEN_TAILSCALE_ORIGIN) — CLI-Flag schlägt ENV schlägt Default.
    p.add_argument("--seiten-heim-origin", dest="seiten_heim_origin",
                   help="Heimnetz-Origin für SREG-12-Seite (SREG-7, z.B. https://xbuddy-hub.local:8443)")
    p.add_argument("--seiten-tailscale-origin", dest="seiten_tailscale_origin",
                   help="Tailscale-Origin für SREG-12-Seite (SREG-7, leer = Banner)")
    p.add_argument("--seiten-funnel-origin", dest="seiten_funnel_origin",
                   help="Funnel-FQDN-Origin für Familien-User-Geräte (SREG-7 dritte Origin,"
                        " AUTH-7b, RAT-27; z.B. https://buddyboard.demo-tailnet.ts.net)")
    # SREG-17 / RAT-31 E6b (#1564): Origin des panel-Service, an den seiten
    # config.json/tiles.json/bearbeiten* der App-Panel-Instanzen proxyt (DCOMP-1).
    # ENV PANEL_SERVICE_URL ueberschreibt Default; CLI-Flag schlaegt ENV.
    p.add_argument("--panel-service-url", dest="panel_service_url",
                   help="Origin des panel-Service fuer das App-Panel-Serving-Proxy "
                        "(SREG-17, Default http://127.0.0.1:5041)")
    # ROU-26 / RAT-31 E6f-B (#1586): icon-root fuer /display/_shared/icons/ +
    # /api/v1/icons/suche. ENV ICON_ROOT ueberschreibt Default; CLI-Flag schlaegt ENV.
    p.add_argument("--icon-root", dest="icon_root",
                   help="Pfad zur Icon-Bibliothek (ROU-26, ICONS-2, "
                        "Default /home/buddy/apps/icons/)")
    return p.parse_args(argv)


def resolved_config(args):
    """Auflösung der RUNTIME-Konfiguration: Datei < ENV < CLI (CONFIG-1).

    Host/Port/Log-Level/TTL kommen vom gemeinsamen `tools.configloader`. `root`
    (Manifest-Wurzel) und `inventar` (Cache-Pfad, SREG-3) bleiben außerhalb des
    Loader-Schemas. ENV-Overrides: `SEITEN_INVENTAR`, `SEITEN_ROOT`.
    RAT-31 E3: PANEL_URL/GERAETE_URL entfernt (#1496).
    """
    cfg = configloader.load(component="seiten", schema=RUNTIME_SCHEMA)
    cfg["root"] = args.root or os.environ.get("SEITEN_ROOT", _REPO_ROOT)
    cfg["inventar"] = os.environ.get("SEITEN_INVENTAR", args.inventar)
    if args.ttl is not None:
        cfg["ttl"] = args.ttl
    if args.host:
        cfg["listen_host"] = args.host
    if args.port:
        cfg["listen_port"] = args.port
    if args.log_level:
        cfg["log_level"] = args.log_level
    # SREG-7: Display-URL-Origins für die SREG-12-Seite.
    # CLI-Flag schlägt ENV schlägt Default (leer).
    cfg["heim_origin"] = (
        args.seiten_heim_origin
        or os.environ.get("SEITEN_HEIM_ORIGIN", ""))
    # SREG-7 / #1458 Funnel-only: SEITEN_TAILSCALE_ORIGIN wird nicht mehr gelesen.
    # Self-signed-Tailnet-IP-Origins wurden aufgegeben (Nic-Setzung 2026-07-25).
    # Der Slot bleibt im runtime-Dict als leerer String (Nullwert), damit
    # configure()-Aufrufe und render.baue_layout nicht brechen — die tailscale_
    # Spalte rendert bei leerem Wert ohnehin nicht (urls.tailscale == None).
    cfg["tailscale_origin"] = ""
    # SREG-7 dritte Origin: Funnel-FQDN fuer Familien-User-Geraete (AUTH-7b,
    # RAT-27 RATIFIZIERT 2026-07-07). CLI schlaegt ENV schlaegt Default (leer).
    # Leer = externer User-Geraete-Zugang nicht angeboten (kein Auto-Fallback).
    cfg["funnel_origin"] = (
        args.seiten_funnel_origin
        or os.environ.get("SEITEN_FUNNEL_ORIGIN", ""))
    # SREG-17 (#1564): Origin des panel-Service fuer das App-Panel-Serving-Proxy.
    # CLI schlaegt ENV schlaegt Default (127.0.0.1:5041, PORT-2).
    cfg["panel_service_url"] = (
        args.panel_service_url
        or os.environ.get("PANEL_SERVICE_URL", "http://127.0.0.1:5041"))
    # ROU-26 / RAT-31 E6f-B (#1586): icon-root fuer Icons + Suche.
    # CLI schlaegt ENV schlaegt Default (leer = DEFAULT_ICON_ROOT).
    cfg["icon_root"] = (
        args.icon_root
        or os.environ.get("ICON_ROOT", ""))
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logsetup.setup(cfg["log_level"])

    configure(root=cfg["root"], inventar_path=cfg["inventar"],
              ttl=cfg["ttl"],
              heim_origin=cfg["heim_origin"],
              tailscale_origin=cfg["tailscale_origin"],
              funnel_origin=cfg["funnel_origin"],
              panel_service_url=cfg["panel_service_url"],
              icon_root=cfg["icon_root"])
    # SREG-7 / #1458: SEITEN_TAILSCALE_ORIGIN ist aufgegeben — kein Warning mehr.
    if not cfg["funnel_origin"]:
        # SREG-7 dritte Origin: Funnel leer → externer User-Geraete-Zugang (AUTH-7b)
        # nicht angeboten. Warnung damit Deploy-Tracking erkennt, ob die
        # Per-Instanz-Datei SEITEN_FUNNEL_ORIGIN noch benoetigt.
        logging.warning(
            "SEITEN_FUNNEL_ORIGIN leer — Familien-User-Geraete erhalten keinen"
            " Funnel-Origin-Link (SREG-7, AUTH-7b).")

    # Kaltstart-Aufbau (SREG-3): das Inventar sofort einmal bauen, damit der
    # erste Request schon eine vollständige Manifest-Sorte aus der Platte sieht.
    rebuild()

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info(
        "Seiten-Registry hört auf %s://%s:%s (inventar=%s, ttl=%ss, RAT-31-E3-manifest-only)",
        scheme, cfg["listen_host"], cfg["listen_port"],
        cfg["inventar"], cfg["ttl"])
    logging.info("Icon-Bibliothek (ROU-26 / RAT-31 E6f-B): %s", _icon_root())
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
