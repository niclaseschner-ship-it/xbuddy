#!/usr/bin/env python3
"""Seiten-Registry — HTTP-Schnittstelle + Entrypoint (SREG-3).

Siehe specs/platform/seiten-registry.md (Refs #347, ratifiziert RAT-13). Diese
Datei ist die echte Komponente um `seiten/aggregator.py` herum: Flask-App +
systemd-Service-Entrypoint. Konsumenten (der Eltern-Chat-Skill `seiten_finden`,
SREG-5) reden über HTTP (DCOMP-1), nicht über `import seiten`.

Endpunkt:
  GET /api/v1/seiten   — das aggregierte Inventar (SREG-3), IMMER aus
                          `inventar.json`, KEIN Upstream-Call im Request-Pfad,
                          Laufzeit < 50 ms.

Service-Topologie (Lego-Prinzip): die Registry läuft als schlanker
eigenständiger Flask-Prozess auf Loopback-Port 5042 (PORT-2), Schwester der
Panel-Registry (PREG/5041) und Geräte-Registry (GER/5040). nginx-Origin matcht
`= /api/v1/seiten` exakt auf diesen Prozess (URL-14, `xbuddy_seiten`).

Aktualität (TTL, SREG-3): `inventar.json` wird neu gebaut, sobald es älter als
der TTL ist (Default 30 s). Der Rebuild läuft on-demand beim nächsten Request,
NACHDEM die schnelle Antwort schon aus der Platte serviert wurde — er holt die
Snapshot-Sorten (d/e) per HTTP von Panel-/Geräte-Registry. Scheitert ein Holer,
greift Last-Known-Good (SREG-3) — er blockiert nie den Request-Pfad.

Cross-Component-HTTP (DCOMP-1 — kein Python-Import):
  - Panel-Snapshot (Sorte d): GET <panel_url>/api/v1/panels/   (PREG-13)
  - Geräte-Snapshot (Sorte e): GET <geraete_url>/api/v1/geraete/ (GER-13)
"""

import argparse
import contextlib
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request

from flask import Flask, jsonify, make_response, render_template, request

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1),
# `tools.logsetup` (LOG-4) und `seiten.aggregator` auch beim Direktstart
# `python3 seiten/main.py` gefunden werden — analog panel/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import aggregator, render  # noqa: E402
from tools import configloader, logsetup  # noqa: E402

# EZG-6 / ESSEN-31: Init-Data-Validierung aus dem Lego-Basis-Modul.
# Vendor-neutrale HMAC-SHA256-Validierung (eltern-chat/init_data.py).
# Der Pfad liegt neben dem Repo-Root im eltern-chat/-Verzeichnis.
_ELTERN_CHAT_DIR = os.path.join(_REPO_ROOT, "eltern-chat")
if _ELTERN_CHAT_DIR not in sys.path:
    sys.path.insert(0, _ELTERN_CHAT_DIR)

import init_data as _init_data_mod  # noqa: E402

# DCOMP-4: Dateirechte auf den Eigentümer beschränkt — analog PREG-4 / GER-4.
FILE_MODE = 0o600

# CLIENT-2: Snapshot-Holer-Timeout (SREG-3). Ein langsamer/defekter Upstream
# blockiert den Rebuild nie länger als das — und der Rebuild läuft ohnehin
# außerhalb des Request-Pfads (LKG fängt das Scheitern ab).
HTTP_TIMEOUT = 2.0


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
    "panel_url":         "http://127.0.0.1:5041",
    "geraete_url":       "http://127.0.0.1:5040",
    "ttl":               30,
    "inventar":          None,
    "gebaut_um":         0.0,
    # SREG-7: zwei Display-URL-Origins (Heim + Tailscale).
    # Heim ist Pflicht fuer SREG-5-Link und SREG-12-Seite.
    # Tailscale ist V1-Soll — fehlt, zeigt SREG-12 nur Heim + Banner.
    "heim_origin":       "",
    "tailscale_origin":  "",
    # MAD-7 / EZG-6 / ESSEN-31: Init-Data-Auth fuer Mini-App-Routen.
    # bot_token: aus ENV ELTERNCHAT_BOT_TOKEN (systemd EnvironmentFile, APP-7).
    # init_data_config: dict aus init_data.load_config() — cached nach erstem Lauf.
    "bot_token":         None,
    "init_data_config":  None,
    # FAM-7/8: Familien-Registry-JSON-Pfad fuer User-ID-Lookup.
    # Aus ENV FAMILIE_JSON_PATH oder runtime-Dict (Test-Naht).
    # Fehlt der Pfad oder die Datei → kein FAM-Check (fail-open in V1).
    "familie_json_path": None,
}


def configure(root=None, inventar_path=None, panel_url=None,
              geraete_url=None, ttl=None,
              heim_origin=None, tailscale_origin=None,
              bot_token=None, init_data_config=None,
              familie_json_path=None):
    """Setzt Aufbau-Wurzel, Inventar-Pfad, Upstream-Origins, TTL und
    Display-URL-Origins (SREG-3, SREG-7).

    Wird `inventar_path` gesetzt, persistiert jeder Rebuild atomar dorthin und
    der Request liest von dort. Ohne `inventar_path` (Test-Modus) bleibt das
    in-memory-`inventar` die Quelle, ohne Disk-Schreiben.

    `heim_origin` und `tailscale_origin` werden fuer die SREG-12-Seite
    benoetigt (render.baue_layout). Leer = Wert bleibt unpetraendert (None
    ueberschreibt auf leeren String — explizit loeschbar).

    `bot_token` und `init_data_config` werden fuer die MAD-7-Mini-App-Auth
    benoetigt. Im Test-Modus werden sie direkt gesetzt;
    im Produktiv-Betrieb kommen sie aus ENV / init_data.load_config().

    `familie_json_path` (FAM-7/8): Pfad zu familie.json fuer User-ID-Lookup.
    Im Test-Modus direkt setzen; im Produktiv-Betrieb aus ENV FAMILIE_JSON_PATH.
    Fehlt der Pfad → kein FAM-Check (fail-open, Warnung im Log).
    """
    if root is not None:
        runtime["root"] = root
    runtime["inventar_path"] = inventar_path
    if panel_url is not None:
        runtime["panel_url"] = panel_url
    if geraete_url is not None:
        runtime["geraete_url"] = geraete_url
    if ttl is not None:
        runtime["ttl"] = ttl
    if heim_origin is not None:
        runtime["heim_origin"] = heim_origin
    if tailscale_origin is not None:
        runtime["tailscale_origin"] = tailscale_origin
    if bot_token is not None:
        runtime["bot_token"] = bot_token
    if init_data_config is not None:
        runtime["init_data_config"] = init_data_config
    if familie_json_path is not None:
        runtime["familie_json_path"] = familie_json_path
    runtime["inventar"] = None
    runtime["gebaut_um"] = 0.0


# Rebuild-Serialisierung (SREG-3): parallele Flask-Threads sollen nicht
# gleichzeitig holen + schreiben. Das Lock klammert nur den Rebuild — die
# schnelle GET-Antwort liest lock-frei aus `inventar.json` (DCOMP-2).
_rebuild_lock = threading.Lock()


# ============================================================
#  Snapshot-Holer (SREG-3) — die einzigen Cross-Component-Teile (DCOMP-1)
# ============================================================

class SnapshotUnreachable(Exception):
    """Ein Snapshot-Upstream (Panel-/Geräte-Registry) ist nicht erreichbar oder
    antwortet ungültig (SREG-3). Wird NICHT im Request-Pfad geworfen — der
    Holer gibt bei Fehler None zurück, der Aggregator greift dann auf
    Last-Known-Good zurück."""


def _hole_json_liste(url):
    """Holt eine JSON-Array-Antwort von `url` (CLIENT-2, Timeout 2.0s).

    Liefert die Liste bei Erfolg. Jeder Transport-/Parse-/Schema-Fehler wird als
    `SnapshotUnreachable` geworfen — der Aufrufer (`hole_panels`/`hole_geraete`)
    fängt sie ab und gibt None zurück. Bewusst über HTTP, KEIN Python-Import der
    Upstream-Komponente (DCOMP-1). Als Funktion stubbar (Tests ohne Netz).
    """
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                raise SnapshotUnreachable("%s antwortet mit %s" % (url, resp.status))
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SnapshotUnreachable(str(e)) from e
    if not isinstance(data, list):
        raise SnapshotUnreachable("%s liefert kein JSON-Array" % url)
    return data


def hole_panels():
    """Holt den Panel-Snapshot (Sorte d, PREG-13) oder None bei Ausfall (SREG-3)."""
    url = runtime["panel_url"].rstrip("/") + "/api/v1/panels/"
    try:
        return _hole_json_liste(url)
    except SnapshotUnreachable as e:
        logging.warning("Panel-Snapshot nicht geholt: %s — Last-Known-Good (SREG-3)", e)
        return None


def hole_geraete():
    """Holt den Geräte-Snapshot (Sorte e, GER-13) oder None bei Ausfall (SREG-3)."""
    url = runtime["geraete_url"].rstrip("/") + "/api/v1/geraete/"
    try:
        return _hole_json_liste(url)
    except SnapshotUnreachable as e:
        logging.warning("Geräte-Snapshot nicht geholt: %s — Last-Known-Good (SREG-3)", e)
        return None


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

def rebuild(vorheriges=None):
    """Baut das Inventar neu (SREG-3): Manifeste von der Platte + frisch geholte
    Snapshots. Persistiert atomar, wenn ein `inventar_path` gesetzt ist.

    Holt die Snapshot-Sorten (d/e) per HTTP; ein Holer-Ausfall liefert None und
    der Aggregator greift auf `vorheriges` (Last-Known-Good) zurück. Aktualisiert
    den in-memory-Cache und den Bauzeitstempel.
    """
    panels = hole_panels()
    geraete = hole_geraete()
    inventar = aggregator.baue_inventar(
        runtime["root"], panels=panels, geraete=geraete, vorheriges=vorheriges)

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
    geschriebenen Inventar. Beim Kaltstart sind die Manifest-Sorten sofort da,
    die Snapshot-Sorten kommen mit `snapshot_pending`, falls die Upstreams aus
    sind — nie eine leere Antwort.
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
            # haben — dann nicht erneut holen.
            inventar = runtime.get("inventar")
            abgelaufen = (time.monotonic() - runtime["gebaut_um"]) >= runtime["ttl"]
            if inventar is None or abgelaufen:
                inventar = rebuild(vorheriges=inventar)
    return inventar


# ============================================================
#  FAM-7/8 — Familien-Mitglieds-Prüfung
# ============================================================

def _lade_familie_telegram_ids():
    """Liest telegram_ids aller Familien-Mitglieder aus familie.json (FAM-7/8).

    Pfad: runtime['familie_json_path'] → ENV FAMILIE_JSON_PATH → None (skip).
    Fehlt die Datei oder ist sie kaputt → leere Menge (fail-open, Warnung).
    V1-Implementierung: direktes JSON-Read ohne familie-Service-Dependency
    (MOD-2: Services voneinander unabhaengig).
    """
    path = runtime.get("familie_json_path") or os.environ.get("FAMILIE_JSON_PATH")
    if not path:
        return None  # kein Pfad konfiguriert → FAM-Check überspringen

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        logging.warning("FAM-7: familie.json nicht lesbar (%s): %s — FAM-Check uebersprungen", path, exc)
        return None

    ids = set()
    for gruppe in ("erwachsene", "kinder"):
        for person in (data.get(gruppe) or []):
            tg_id = person.get("telegram_id")
            if tg_id is not None:
                ids.add(int(tg_id))
    return ids


def _check_familie_mitglied(user_id):
    """Prüft ob user_id in der Familien-Registry registriert ist (FAM-7/8 / AC4).

    Gibt None zurück wenn OK (user_id ist Mitglied oder kein Pfad konfiguriert).
    Gibt (json-Response, 403) zurück wenn user_id NICHT in der Registry.
    """
    familie_ids = _lade_familie_telegram_ids()
    if familie_ids is None:
        # Kein Pfad konfiguriert → fail-open (kein Block)
        logging.debug("FAM-7: kein familie_json_path konfiguriert — FAM-Check uebersprungen")
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


@app.route("/api/v1/seiten", methods=["GET"])
def get_seiten():
    """SREG-3: das aggregierte Inventar aller aufrufbaren Views.

    Serviert IMMER aus `inventar.json` (kein Upstream-Call im Request-Pfad,
    < 50 ms). Die Antwort ist nie leer (die Manifest-Sorten tragen sie auch beim
    Kaltstart), Snapshot-Ausfälle erscheinen als `stale`/`snapshot_pending`
    statt als gekürzte Liste.
    """
    return jsonify(_aktuelles_inventar())


@app.route("/api/v1/seiten/uebersicht", methods=["GET"])
def get_seiten_uebersicht():
    """SREG-12: gerenderte Eltern-Uebersichts-Seite (HTML).

    Baut die V2-Layout-Datenstruktur via render.baue_layout und liefert das
    gerendertes HTML (Jinja2, Template uebersicht.html). Origins kommen aus dem
    runtime-Dict (SREG-7): ENV-Overrides SEITEN_HEIM_ORIGIN /
    SEITEN_TAILSCALE_ORIGIN oder CLI-Flags --seiten-heim-origin /
    --seiten-tailscale-origin, gesetzt beim Start (resolved_config).

    Fehlende Tailscale-Origin loest einen Banner-Hinweis auf der Seite aus
    (tailscale_banner=True via render.baue_layout — keine leere Seite).
    """
    inventar = _aktuelles_inventar()
    layout = render.baue_layout(
        inventar,
        heim_origin=runtime["heim_origin"],
        tailscale_origin=runtime["tailscale_origin"],
    )
    return render_template("uebersicht.html", **layout)


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
    try:
        build_id = str(int(os.path.getmtime(os.path.join(static_dir, "essen-einkauf.js"))))
    except OSError:
        build_id = "0"
    resp = make_response(render_template("essen-einkauf.html", build_id=build_id))
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


def _read_sw_with_build_id(asset_path, build_id):
    """Liest sw.js, ersetzt __BUILD_ID__-Platzhalter und gibt String zurueck.

    ESSEN-35 Cache-Versionierung: der Service-Worker traegt den Cache-Namen
    'einkauf-pwa-<build_id>'. Beim Deploy mit neuer build_id invalidiert
    der activate-Event den alten Cache.
    """
    with open(asset_path, encoding="utf-8") as fh:
        content = fh.read()
    return content.replace("__BUILD_ID__", build_id)


def _current_build_id():
    """build_id aus mtime der essen-einkauf.js — identisch zu HTML-Route."""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    try:
        return str(int(os.path.getmtime(os.path.join(static_dir, "essen-einkauf.js"))))
    except OSError:
        return "0"


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
        body = _read_sw_with_build_id(target, build_id)
        resp = make_response(body, 200)
        resp.headers["Content-Type"] = mimetype + "; charset=utf-8"
        # Browser muss sw.js fresh holen, sonst kein Update-Trigger.
        # https://web.dev/articles/service-worker-lifecycle#updates
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        # Service-Worker-Allowed nicht noetig — Scope passt zur Default-Wurzel.
        return resp

    # Andere Assets: send_from_directory mit explizitem Content-Type.
    return send_from_directory(root, asset, mimetype=mimetype)


@app.route("/api/v1/seiten/mini-app-uebersicht", methods=["GET"])
def mini_app_uebersicht_view():
    """MAU-1: Telegram-Mini-App-Uebersichts-View — HTML fuer den Familien-Bot.

    Auth (MAD-7 / MAU-3): Authorization: tma <initData>-Header Pflicht.
    Fehlender oder ungueliger Header → 401. Nicht-Familienmitglied → 403.

    JS laedt das Inventar bei Boot via:
      GET /api/v1/seiten  (SREG-3, aggregiertes Inventar)
    und rendert drei Accordion-Sektionen (MAU-4):
      1. Mini Telegram Apps (typ: mini-app)
      2. Geraete-Paare (typ: display-client + verknuepft_mit_panels)
      3. Buddy-Seiten (typ: eltern)

    Cache-Buster (Mini-App-Cache-Buster-Pattern): build_id aus mtime der JS-Datei
    haengt am CSS+JS als ?v=... — Telegram cached Mini-App-Assets sonst aggressiv.
    Response-Header no-store zusaetzlich, damit jeder Open das HTML neu holt.
    """
    # MAD-7-konform: HTML-Render-Route lädt Skeleton OHNE Auth (Telegram-WebView
    # sendet beim Initial-Load keinen Header). JS macht platform.ensureAuth().
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    try:
        build_id = str(int(os.path.getmtime(
            os.path.join(static_dir, "mini-app-uebersicht.js"))))
    except OSError:
        build_id = "0"

    resp = make_response(render_template("mini-app-uebersicht.html", build_id=build_id))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/seiten/routine/anpassen", methods=["GET"])
def routine_anpassen_view():
    """ROUTINE-20 / ROUTINE-23: Eltern-Anpassen-Mini-App-View.

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
    """
    # MAD-7-konform: HTML-Render-Route lädt Skeleton OHNE Auth. JS macht ensureAuth().
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    try:
        build_id = str(int(os.path.getmtime(os.path.join(static_dir, "routine-anpassen.js"))))
    except OSError:
        build_id = "0"
    resp = make_response(render_template("routine-anpassen.html", build_id=build_id))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/seiten/hoerspiel/<kind_id>/eltern", methods=["GET"])
def hoerspiel_eltern_view(kind_id: str):
    """HSP-33: Hörspiel-Eltern-Mini-App-View (kind_id-tragend, HSP-26 / URL-3a).

    Auth (MAD-7 / HSP-39): Authorization: tma <initData>-Header Pflicht.
    Fehlender oder ungültiger Header → 401 + Klartext.
    Nicht-Familienmitglied → 403.

    Template liegt in hoerspiel/templates/eltern.html (HSP-33: Wohnort im
    hoerspiel/-Modul). Rendered via absoluten Pfad analog anderen Mini-Apps.

    JS laedt beim Boot via:
      GET /api/v1/hoerspiel/<kind_id>/config  (HSP-34: Einstellungen)
      GET /api/v1/hoerspiel/<kind_id>/alben   (HSP-35: Folgen-Liste)
    nginx routet /api/v1/hoerspiel/... zum hoerspiel-Buddy (Port 5053).
    kind_id kommt aus location.pathname (eltern.js, T970).

    Cache-Buster: build_id aus mtime von hoerspiel/static/eltern.js.
    response-Header no-store, damit jeder Open das HTML neu holt.
    """
    # MAD-7-konform: HTML-Render-Route lädt Skeleton OHNE Auth. JS macht ensureAuth().
    # build_id aus mtime von eltern.js in hoerspiel/static/
    _REPO_ROOT_SEITEN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hoerspiel_static = os.path.join(_REPO_ROOT_SEITEN, "hoerspiel", "static")
    try:
        build_id = str(int(os.path.getmtime(os.path.join(hoerspiel_static, "eltern.js"))))
    except OSError:
        build_id = "0"

    # Template aus hoerspiel/templates/ via absolutem Pfad.
    hoerspiel_templates = os.path.join(_REPO_ROOT_SEITEN, "hoerspiel", "templates")
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(hoerspiel_templates), autoescape=True)
    tmpl = env.get_template("eltern.html")
    html = tmpl.render(build_id=build_id)

    resp = make_response(html, 200)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


# ============================================================
#  Entrypoint
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1): nur die Werte, die der Service-Start braucht.
# Familienspezifische Daten gibt es hier keine — das Inventar wird aggregiert,
# nicht handgepflegt; `inventar.json` ist abgeleiteter Cache, kein Per-Instanz-
# Stammdatum.
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
    p.add_argument("--panel-url", dest="panel_url",
                   help="Origin der Panel-Registry für Sorte d (SREG-3)")
    p.add_argument("--geraete-url", dest="geraete_url",
                   help="Origin der Geräte-Registry für Sorte e (SREG-3)")
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
    return p.parse_args(argv)


def resolved_config(args):
    """Auflösung der RUNTIME-Konfiguration: Datei < ENV < CLI (CONFIG-1).

    Host/Port/Log-Level/TTL kommen vom gemeinsamen `tools.configloader`. `root`
    (Manifest-Wurzel), `inventar` (Cache-Pfad, SREG-3), `panel_url`/`geraete_url`
    (Snapshot-Origins) bleiben außerhalb des Loader-Schemas — analog
    panel/main.py. ENV-Overrides decken den Dev-Override ab (`SEITEN_INVENTAR`,
    `PANEL_URL`, `GERAETE_URL`, `SEITEN_ROOT`).
    """
    cfg = configloader.load(component="seiten", schema=RUNTIME_SCHEMA)
    cfg["root"] = args.root or os.environ.get("SEITEN_ROOT", _REPO_ROOT)
    cfg["inventar"] = os.environ.get("SEITEN_INVENTAR", args.inventar)
    cfg["panel_url"] = (
        args.panel_url or os.environ.get("PANEL_URL", "http://127.0.0.1:5041"))
    cfg["geraete_url"] = (
        args.geraete_url or os.environ.get("GERAETE_URL", "http://127.0.0.1:5040"))
    if args.ttl is not None:
        cfg["ttl"] = args.ttl
    if args.host:
        cfg["listen_host"] = args.host
    if args.port:
        cfg["listen_port"] = args.port
    if args.log_level:
        cfg["log_level"] = args.log_level
    # SREG-7: Display-URL-Origins für die SREG-12-Seite.
    # CLI-Flag schlägt ENV schlägt Default (leer). Leerer Tailscale-Origin
    # ist zulässig → render.baue_layout setzt tailscale_banner=True.
    cfg["heim_origin"] = (
        args.seiten_heim_origin
        or os.environ.get("SEITEN_HEIM_ORIGIN", ""))
    cfg["tailscale_origin"] = (
        args.seiten_tailscale_origin
        or os.environ.get("SEITEN_TAILSCALE_ORIGIN", ""))
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logsetup.setup(cfg["log_level"])

    configure(root=cfg["root"], inventar_path=cfg["inventar"],
              panel_url=cfg["panel_url"], geraete_url=cfg["geraete_url"],
              ttl=cfg["ttl"],
              heim_origin=cfg["heim_origin"],
              tailscale_origin=cfg["tailscale_origin"])
    if not cfg["tailscale_origin"]:
        # SREG-7 V1-Soll: Tailscale leer → SREG-12 zeigt Banner statt
        # zweiter URL-Spalte. Warnung im Log, damit Deploy-Tracking sieht,
        # ob die Per-Instanz-Datei den Wert noch ergaenzen muss.
        logging.warning(
            "SEITEN_TAILSCALE_ORIGIN leer — SREG-12 zeigt nur Heim-Spalte mit Banner.")

    # Kaltstart-Aufbau (SREG-3): das Inventar sofort einmal bauen, damit der
    # erste Request schon eine vollständige Manifest-Sorte aus der Platte sieht.
    # Snapshot-Ausfälle sind nicht-fatal (snapshot_pending / Last-Known-Good).
    rebuild()

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info(
        "Seiten-Registry hört auf %s://%s:%s (inventar=%s, panel=%s, geraete=%s, ttl=%ss)",
        scheme, cfg["listen_host"], cfg["listen_port"],
        cfg["inventar"], cfg["panel_url"], cfg["geraete_url"], cfg["ttl"])
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
