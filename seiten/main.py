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

from flask import Flask, jsonify, render_template

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1),
# `tools.logsetup` (LOG-4) und `seiten.aggregator` auch beim Direktstart
# `python3 seiten/main.py` gefunden werden — analog panel/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import aggregator  # noqa: E402
from seiten import render  # noqa: E402
from tools import configloader, logsetup  # noqa: E402

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
}


def configure(root=None, inventar_path=None, panel_url=None,
              geraete_url=None, ttl=None,
              heim_origin=None, tailscale_origin=None):
    """Setzt Aufbau-Wurzel, Inventar-Pfad, Upstream-Origins, TTL und
    Display-URL-Origins (SREG-3, SREG-7).

    Wird `inventar_path` gesetzt, persistiert jeder Rebuild atomar dorthin und
    der Request liest von dort. Ohne `inventar_path` (Test-Modus) bleibt das
    in-memory-`inventar` die Quelle, ohne Disk-Schreiben.

    `heim_origin` und `tailscale_origin` werden fuer die SREG-12-Seite
    benoetigt (render.baue_layout). Leer = Wert bleibt unveraendert (None
    ueberschreibt auf leeren String — explizit loeschbar).
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
#  Flask-App
# ============================================================

app = Flask(__name__, template_folder="templates")


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
