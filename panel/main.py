#!/usr/bin/env python3
"""Panel-Registry — HTTP-Schnittstelle + Entrypoint.

Siehe specs/platform/panel-registry.md (Refs #58, #329). Diese Datei ist die
echte Komponente um `panel/registry.py` herum: Flask-App + systemd-Service-
Entrypoint. Konsumenten reden über HTTP (DCOMP-1), nicht über `import panel`.

Endpunkte:
  GET  /api/v1/panels/                       — alle Panels (PREG-13)
  GET  /api/v1/panels/<id>                    — ein Panel je `panel_id` (PREG-14)
  GET  /api/v1/panels/<id>/config.json        — config-Sicht (PREG-14)
  GET  /api/v1/panels/<id>/tiles.json         — tiles-Sicht (PREG-14)
  PUT  /api/v1/panels/<id>/tiles              — tiles schreiben, atomar (PBE-4, #330)
  POST /api/v1/panels/                        — Panel anlegen, atomar (PREG-15)

Service-Topologie (Lego-Prinzip): die Registry läuft als schlanker
eigenständiger Flask-Prozess auf Loopback-Port 5041 (PORT-2), Schwester der
Geräte-Registry (GER/5040). nginx-Origin matcht `/api/v1/panels/` auf diesen
Prozess (URL-14, `xbuddy_panel`).

Cross-Component-HTTP-Aufrufe (DCOMP-1 — kein Python-Import):
  - Display-Validierung beim POST: GER-14, PREG-7 (Geräte-Registry)
  - Router-Forward/Repair: ROU-29, PREG-16/PREG-17 (Router)
"""

import argparse
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request

from flask import Flask, Response, jsonify, request

# Repo-Wurzel auf den Importpfad, damit `tools.configloader` (CONFIG-1) und
# `tools.logsetup` (LOG-4) auch beim Direktstart `python3 panel/main.py`
# gefunden werden — analog geraete/main.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from panel import registry as registry_mod  # noqa: E402
from tools import configloader, logsetup  # noqa: E402

# ============================================================
#  Laufzeit-Zustand
# ============================================================

# Die geladene Registry, der Registry-Pfad, die Geräte-Registry-URL und die
# Router-Origin. Der Entrypoint befüllt das Dict; Tests setzen es über
# `configure()`.
runtime = {
    "registry":      registry_mod.Registry(),
    "registry_path": None,
    "geraete_url":   "http://127.0.0.1:5040",
    "router_url":    "http://127.0.0.1:5000",
}


def configure(reg, registry_path=None, geraete_url=None, router_url=None):
    """Setzt die laufende Registry, den Registry-Pfad, die Geräte-Registry-URL
    und die Router-Origin (PREG-11).

    Wird `registry_path` nicht übergeben, bleibt das übergebene Registry-Objekt
    die Quelle (Test-Modus, ohne Disk-Schreiben). Mit `registry_path` liest
    jeder Request frisch von Disk (DCOMP-2), und POST schreibt persistent
    (DCOMP-4 über `panel.save`).
    """
    runtime["registry"] = reg
    runtime["registry_path"] = registry_path
    if geraete_url is not None:
        runtime["geraete_url"] = geraete_url
    if router_url is not None:
        runtime["router_url"] = router_url


# Schreib-Serialisierung (PREG-15): Read-Modify-Write der Registry-Datei aus
# parallelen Flask-Threads würde ohne Lock verlorengehende Updates produzieren.
# Das Lock klammert nur den Schreib-Pfad — Lesen bleibt lock-frei (DCOMP-2).
_write_lock = threading.Lock()

# PREG-11: Default-Backoff-Folge für die Heal-on-Boot-Erreichbarkeits-Probe
# (PREG-18). Summe ≈ 50 s Cap. Werte exakt aus Spec.
_DEFAULT_HEAL_BOOT_BACKOFFS = [0.2, 1, 2, 5, 5, 5, 5, 5, 5, 5, 5, 5]


# ============================================================
#  Geräte-Validierung (PREG-7, GER-14) — der eine Cross-Component-Teil
# ============================================================

class _GeraeteUnreachable(Exception):
    """Die Geräte-Registry ist nicht erreichbar — PREG-7 → 503."""


def display_existiert(display_id):
    """Prüft per HTTP gegen die Geräte-Registry, ob `display_id` existiert.

    GER-14 / PREG-7: `GET <geraete_url>/api/v1/geraete/<display_id>`.
    200 → existiert (True), 404 → unbekannt (False). Jeder Transport- oder
    sonstige Fehler ist `_GeraeteUnreachable` (PREG-7 → 503): ein Panel auf ein
    nicht validierbares Display anzulegen ist keine sichere Default-Annahme.

    Bewusst über HTTP, KEIN Python-Import der Geräte-Komponente (DCOMP-1). Als
    Funktion auf Modulebene, damit Tests sie stubben können (PREG-12: ohne Netz).
    """
    base = runtime["geraete_url"].rstrip("/")
    url = "%s/api/v1/geraete/%s" % (base, display_id)
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        # Andere HTTP-Fehler (5xx der Geräte-Registry) sind kein „unbekannt",
        # sondern ein nicht-validierbarer Zustand → unreachable (503).
        raise _GeraeteUnreachable(
            "Geräte-Registry antwortet mit %s" % e.code) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise _GeraeteUnreachable(str(e)) from e


# ============================================================
#  Router-Forward / Repair (PREG-16/PREG-17, ROU-29)
# ============================================================

class _RouterUnreachable(Exception):
    """Der Router ist nicht erreichbar oder antwortet mit 5xx — PREG-16."""


def router_reachable():
    """Erreichbarkeits-Probe: antwortet der Router auf HTTP? (PREG-18)

    Gibt True zurück, wenn der Router irgendeine HTTP-Antwort liefert — auch
    4xx/5xx zählen als „Router ist oben". Gibt False zurück bei Verbindungs-
    fehlern (Connection refused, Timeout, kein Route-to-Host), die bedeuten,
    dass der Router noch nicht gestartet ist (transient).

    Bewusst über HTTP, KEIN Python-Import des Routers (DCOMP-1). Als Funktion
    auf Modulebene, damit Tests sie stubben können (PREG-12: ohne Netz).
    """
    base = runtime["router_url"].rstrip("/")
    url = "%s/" % base
    try:
        with urllib.request.urlopen(url, timeout=5):
            return True
    except urllib.error.HTTPError:
        # Jede HTTP-Fehlerantwort (4xx/5xx) bedeutet: Router ist oben.
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def router_tiles_changed(display_id):
    """Signalisiert dem Router, dass Tiles für display_id geändert wurden (PBE-10).

    POST <router_url>/api/v1/router/admin/panels/<display_id>/tiles-changed
    Leerer Body. 204 → Router hat publish() aufgerufen, SSE-Event unterwegs.
    5xx / Netz-Fehler → _RouterUnreachable (graceful: DCOMP-2 trägt als Fallback).

    Bewusst über HTTP, KEIN Python-Import des Routers (DCOMP-1). Als Funktion
    auf Modulebene, damit Tests sie stubben können (PREG-12: ohne Netz).
    Latenz lokaler Round-Trip << 5 s (PBE-10-Schranke erfüllt).
    """
    base = runtime["router_url"].rstrip("/")
    url = "%s/api/v1/router/admin/panels/%s/tiles-changed" % (base, display_id)
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 204
    except urllib.error.HTTPError as e:
        raise _RouterUnreachable(
            "Router antwortet mit %s auf PBE-10 tiles-changed für display_id=%r"
            % (e.code, display_id)) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise _RouterUnreachable(str(e)) from e


def router_panels_upsert(source_id, display_id):
    """Schreibt einen `panels`-Eintrag in die Router-routing.json via ROU-29.

    POST <router_url>/api/v1/router/admin/panels/  Body: {source_id, display_id}
    200 → Eintrag geschrieben (True).
    400 → Schema-Fehler (nicht wiederhol-bar; wirft _RouterUnreachable mit Kontext).
    5xx / Netz-Fehler → _RouterUnreachable (temporär, Repair kann es erneut probieren).

    Bewusst über HTTP, KEIN Python-Import des Routers (DCOMP-1). Als Funktion
    auf Modulebene, damit Tests sie stubben können (PREG-12: ohne Netz).
    """
    import json as _json
    base = runtime["router_url"].rstrip("/")
    url = "%s/api/v1/router/admin/panels/" % base
    body = _json.dumps({"source_id": source_id, "display_id": display_id}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        # 4xx sind Konfigurations-Fehler (kein panel), nicht temporär.
        raise _RouterUnreachable(
            "Router antwortet mit %s auf ROU-29 für source_id=%r"
            % (e.code, source_id)) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise _RouterUnreachable(str(e)) from e


def _do_repair_loop(panels):
    """Innerer Repair-Lauf (PREG-17): blind idempotenter Upsert für alle Panels.

    Jede Panel-Instanz in `panels` wird unbedingt via ROU-29 an den Router
    geschrieben — kein Zurücklesen des Ist-Stands, kein Lese-Endpunkt (Nic-
    Entscheid 2026-06-04). Schlägt ein einzelner ROU-29-Aufruf fehl, bleibt
    diese Instanz reconcile-pending (Warnung im Log) und der Lauf macht mit
    den übrigen WEITER — kein Abbruch beim ersten Fehler (PREG-17 Robustheit).
    Repair ist nicht-fatal: Fehler blockieren den Service-Start nicht.

    Separiert von repair_heal_on_boot(), damit der Probe/Retry-Wrapper (PREG-18)
    und die Upsert-Schleife (PREG-17) unabhängig testbar sind.
    """
    ok = 0
    pending = 0
    for p in panels:
        try:
            router_panels_upsert(p.source_id, p.display_id)
            ok += 1
        except _RouterUnreachable as e:
            logging.warning(
                "Heal-on-Boot: reconcile-pending für panel_id=%r source_id=%r: %s"
                " — Panel in panels.json gültig, Router-Eintrag fehlt noch (PREG-17)",
                p.panel_id, p.source_id, e)
            pending += 1
    logging.info(
        "Heal-on-Boot abgeschlossen: %d geheilt, %d reconcile-pending (PREG-17)",
        ok, pending)


def repair_heal_on_boot(panels, backoffs=None, _sleep=None, _probe=None):
    """Repair-Lauf (PREG-17) mit Boot-Robustheit gegen nicht-erreichbaren Router (PREG-18).

    Ist der Router beim Start nicht erreichbar, pollt diese Funktion die
    Erreichbarkeit mit den konfigurierten Backoff-Intervallen (PREG-11) und
    führt den Repair aus, sobald der Router antwortet. Läuft der Cap ab ohne
    Antwort, werden alle Panels als reconcile-pending geloggt und der Service
    fährt nicht-fatal fort — der Start wird nie blockiert (PREG-18).

    Leere Backoff-Folge (`backoffs=[]`) = genau ein Versuch ohne Probe/Retry
    (Verhalten wie vor PREG-18, PREG-11: leere Folge = genau ein Versuch).

    `_sleep` und `_probe` sind injizierbar, damit Tests keinen Wall-Clock-sleep
    brauchen (PREG-12 / PREG-18: injizierbarer Sleep/Clock, keine echte Wartezeit
    im Test).

    Die Unterscheidung transient (Router noch nicht oben → Backoff/Retry des
    GANZEN Laufs) vs einzelner ROU-29-Upsert-Fehler (Instanz reconcile-pending,
    Lauf macht weiter) ist in _do_repair_loop() abgebildet — PREG-17 unverändert.
    """
    if backoffs is None:
        backoffs = _DEFAULT_HEAL_BOOT_BACKOFFS
    if _sleep is None:
        _sleep = time.sleep
    if _probe is None:
        _probe = router_reachable

    # Leere Folge = genau ein Versuch, kein Probe/Retry (PREG-11).
    if not backoffs:
        _do_repair_loop(panels)
        return

    # Erreichbarkeits-Probe mit beschränktem Backoff (PREG-18).
    # Probe, bei Fehlschlag: sleep(backoffs[i]) + nächste Probe; nach Cap → nicht-fatal.
    remaining = list(backoffs)
    while True:
        if _probe():
            # Router erreichbar → Repair-Lauf ausführen (PREG-17).
            _do_repair_loop(panels)
            return
        if not remaining:
            # Backoff-Cap abgelaufen → nicht-fatal fortfahren (PREG-18).
            logging.warning(
                "Heal-on-Boot: Router nicht erreichbar nach Backoff-Cap — "
                "%d Panel(s) reconcile-pending, Service fährt nicht-fatal fort (PREG-18)",
                len(panels))
            for p in panels:
                logging.warning(
                    "Heal-on-Boot: reconcile-pending für panel_id=%r source_id=%r"
                    " — Router nicht erreichbar, Panel in panels.json gültig (PREG-17)",
                    p.panel_id, p.source_id)
            logging.info(
                "Heal-on-Boot abgeschlossen: 0 geheilt, %d reconcile-pending (PREG-17)",
                len(panels))
            return
        wait = remaining.pop(0)
        logging.info(
            "Heal-on-Boot: Router noch nicht erreichbar — warte %.1fs "
            "(%d weitere Versuche, PREG-18)",
            wait, len(remaining))
        _sleep(wait)


# ============================================================
#  Flask-App
# ============================================================

app = Flask(__name__)


def _aktuelle_registry():
    """Liefert die aktuelle Panel-Registry für genau diesen Request (DCOMP-2).

    Ist ein `registry_path` gesetzt, wird pro Request frisch von Disk geladen —
    sonst sähe der Service Cross-Service-Schreibvorgänge erst nach Restart. Im
    Test-Modus (`configure()` ohne `registry_path`) bleibt das in-memory-Objekt
    die Quelle.
    """
    path = runtime.get("registry_path")
    if path is None:
        return runtime["registry"]
    return registry_mod.load(path)


@app.route("/api/v1/panels/", methods=["GET"])
def get_panels():
    """PREG-13: alle Panel-Instanzen der Familie als JSON-Array."""
    return jsonify([p.to_dict() for p in _aktuelle_registry().list_all()])


@app.route("/api/v1/panels/<panel_id>", methods=["GET"])
def get_panel(panel_id):
    """PREG-14: ein Panel je `panel_id`. Unbekannte id: 404 mit JSON-Fehler."""
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.to_dict())


@app.route("/api/v1/panels/<panel_id>/config.json", methods=["GET"])
def get_panel_config(panel_id):
    """PREG-14: das `config`-Feld als eigenständiges JSON-Dokument (PANEL-8).

    Genau die Form, die die Panel-Seite per `fetch('./config.json')` erwartet —
    der Router proxyt diese Sicht (PREG-9).
    """
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.config)


@app.route("/api/v1/panels/<panel_id>/tiles.json", methods=["GET"])
def get_panel_tiles(panel_id):
    """PREG-14: das `tiles`-Feld als eigenständiges JSON-Dokument (PANEL-3).

    Genau die Form, die die Panel-Seite per `fetch('./tiles.json')` erwartet —
    der Router proxyt diese Sicht (PREG-9).
    """
    p = _aktuelle_registry().get(panel_id)
    if p is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    return jsonify(p.tiles)


def _unprocessable(msg):
    """PBE-11: 422 mit JSON-Fehler für ungültige tiles-Liste."""
    return jsonify({"error": msg}), 422


@app.route("/api/v1/panels/<panel_id>/tiles", methods=["PUT"])
def put_panel_tiles(panel_id):
    """PBE-4: vollständige neue tiles-Liste schreiben.

    Body: ein tiles-Objekt {"tiles": [...]} — die vollständige neue Liste
    (nicht ein Patch). Last-Write-Wins (Nic 2026-06-07).

    - PBE-11 Validierung VOR dem Schreiben → 422 + JSON-Fehler, Datei unverändert.
    - Unbekannte panel_id → 404.
    - Schreibfehler am Dateisystem → 500 + JSON-Fehler (GER-6/DCOMP-4-Geist).
    - PREG-5: config-Feld der Instanz wird NICHT berührt.
    - DCOMP-4: atomares Schreiben (Temp + os.replace) über registry_mod.save().
    - PBE-10: nach erfolgreichem Schreiben wird router_tiles_changed(display_id)
      aufgerufen (SSE-Publish). Bei Router-Unreachable graceful (kein Crash, kein
      5xx) — DCOMP-2 reload-on-read bleibt Fallback (V1-Ausfall-Toleranz).
    """
    path = runtime.get("registry_path")
    if path is None:
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    body = request.get_json(silent=True)
    if body is None:
        return _unprocessable("kein gültiges JSON im Request-Body (PBE-11)")

    # PBE-11: Validierung vor dem Schreiben — via registry_mod (konsolidiert).
    try:
        registry_mod.validate_tiles_payload(body)
    except registry_mod.RegistryError as e:
        return _unprocessable(str(e))

    display_id = None
    with _write_lock:
        # DCOMP-2: frisch von Disk lesen — nie einen veralteten Stand überschreiben.
        reg = registry_mod.load(path)
        panel = reg.get(panel_id)
        if panel is None:
            return jsonify({"error": "unbekannte panel_id (PBE-4)"}), 404

        display_id = panel.display_id

        # PREG-5: nur tiles ersetzen, config unberührt.
        geaendertes_panel = registry_mod.Panel(
            panel_id=panel.panel_id,
            display_id=panel.display_id,
            config=panel.config,
            tiles=body,
            router_url=panel.router_url,
            source_id=panel.source_id,
        )
        # Registry mit geändertem Panel aufbauen — alle anderen Panels erhalten.
        neue_panels = []
        for p in reg.list_all():
            if p.panel_id == panel_id:
                neue_panels.append(geaendertes_panel)
            else:
                neue_panels.append(p)
        neue_reg = registry_mod.Registry(neue_panels)

        try:
            registry_mod.save(neue_reg, path)
        except registry_mod.RegistryError as e:
            logging.warning("put_panel_tiles: Schreiben fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 500

    # PBE-10: SSE-Publish-Signal an den Router (AC1). Graceful bei Ausfall —
    # DCOMP-2 reload-on-read bleibt Fallback, kein Crash, kein 5xx.
    try:
        router_tiles_changed(display_id)
    except _RouterUnreachable as e:
        logging.warning(
            "put_panel_tiles: router_tiles_changed fehlgeschlagen für display_id=%r: %s"
            " — DCOMP-2 reload-on-read trägt als Fallback (PBE-10)",
            display_id, e)

    return jsonify({"ok": True, "panel_id": panel_id}), 200


def _bad_request(msg):
    """PREG-15: 4xx mit JSON-Fehler, keine Stack-Traces (analog GER-15)."""
    return jsonify({"error": msg}), 400


# ============================================================
#  PBE-1/PBE-2 — Editor-Seite je Panel-Instanz (Frontend-Auslieferung)
# ============================================================
#
# Der panel-Service liefert je Panel-Instanz die Editor-Seite (PBE-1) unter
# der deterministisch aus der `panel_id` abgeleiteten URL
# `/controller/app-panel/<panel_id>/bearbeiten` (PBE-2) aus. Der Daten-Eigentümer
# (panel-Service) liefert seine eigene Editor-Seite, die zeigt UND editiert —
# Muster RAT-2 / #328 (Garderoben-Editor). Auth = Heimnetz/Tailscale-Grenze
# (PBE-3 / RAT-2); keine Rolle in V1.
#
# Die Statik liegt in `controller/app-panel/bearbeiten.{html,js,css}` neben der
# bestehenden Display-Seite. Wir lesen die HTML-Datei einmalig pro Request und
# substituieren die Panel-Identität in den <body>-Tag (analog zu router/main.py
# render_app_panel_index, PANEL-2-Muster), damit die JS-Schicht ohne weiteren
# Roundtrip ihre Panel-ID kennt.

# controller/app-panel/ liegt parallel zum panel-Service-Verzeichnis im Repo.
_BEARBEITEN_STATIC_DIR = os.path.normpath(os.path.join(
    _HERE, "..", "controller", "app-panel"))


def _editor_static_dir():
    """Erlaubt Tests, das Auslieferungs-Verzeichnis zu überschreiben."""
    return runtime.get("editor_static_dir") or _BEARBEITEN_STATIC_DIR


def _read_editor_html(filename):
    """Liest die Editor-HTML-Datei aus dem Auslieferungs-Verzeichnis (PBE-1)."""
    path = os.path.join(_editor_static_dir(), filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


# PBE-1 Token-Substitution: das echte <body>-Tag in bearbeiten.html trägt
# `data-panel-id="__PANEL_ID__"`. Wir ersetzen genau dieses Token — kein
# Substring-Match auf `<body>` (das stünde sonst auch im HTML-Kommentar und
# würde dort fälschlich substituiert, sodass das echte Tag leer bliebe).
# IDENT-5 — Server-side-Identitäts-Token in HTML-Templates.
_PANEL_ID_TOKEN = "__PANEL_ID__"


def _send_editor_static(panel_id, filename, mimetype):
    """Liefert eine statische Editor-Datei aus (PBE-1, Konsolidierung).

    Gemeinsame Helferfunktion für HTML/JS/CSS-Routen — kein dreifach kopierter
    Read+404+OSError-Block. Die 404-Probe auf `panel_id` läuft hier zentral:
    eine unbekannte Identität darf weder HTML noch JS/CSS für diese Instanz
    bekommen (PBE-1: Seite ist an die `panel_id` gebunden).
    """
    if _aktuelle_registry().get(panel_id) is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    try:
        body = _read_editor_html(filename)
    except OSError as e:
        logging.warning("Editor-Statik %r konnte nicht gelesen werden: %s",
                        filename, e)
        return jsonify({"error": "%s nicht verfügbar" % filename}), 500
    return Response(body, status=200, mimetype=mimetype)


@app.route("/controller/app-panel/<panel_id>/bearbeiten", methods=["GET"])
def get_panel_editor(panel_id):
    """PBE-1/PBE-2: Editor-Seite je Panel-Instanz.

    Liefert `bearbeiten.html` mit der Panel-Identität als `data-panel-id` am
    <body> (analog PANEL-2-Muster im Router). 404 bei unbekannter `panel_id`
    (PBE-1: die Seite ist an die `panel_id` gebunden — sie editiert nie eine
    andere Instanz; eine unbekannte Identität darf keine Editor-Seite bekommen).

    PBE-3: keine zusätzliche Auth-Schicht; das Heimnetz/Tailscale-Gate (RAT-2)
    trägt den Zugriff.

    PBE-1: Panel-Identität wird per Token-Substitution `__PANEL_ID__` im echten
    `<body>`-Tag durch die `panel_id` ersetzt — die Editor-JS-Schicht liest sie
    per `document.body.dataset.panelId` und braucht keinen Roundtrip. Token
    statt Substring-Match auf `<body>`, damit HTML-Kommentare nicht
    versehentlich gematcht werden.
    """
    if _aktuelle_registry().get(panel_id) is None:
        return jsonify({"error": "unbekannte panel_id"}), 404
    try:
        html = _read_editor_html("bearbeiten.html")
    except OSError as e:
        logging.warning("Editor-HTML konnte nicht gelesen werden: %s", e)
        return jsonify({"error": "Editor-Seite nicht verfügbar"}), 500
    html = html.replace(_PANEL_ID_TOKEN, panel_id)
    return Response(html, status=200,
                    mimetype="text/html; charset=utf-8")


@app.route("/controller/app-panel/<panel_id>/bearbeiten.js", methods=["GET"])
def get_panel_editor_js(panel_id):
    """PBE-1: Editor-JS-Bundle (statisch). 404 bei unbekannter panel_id."""
    return _send_editor_static(panel_id, "bearbeiten.js", "application/javascript")


@app.route("/controller/app-panel/<panel_id>/bearbeiten.css", methods=["GET"])
def get_panel_editor_css(panel_id):
    """PBE-1: Editor-CSS (statisch). 404 bei unbekannter panel_id."""
    return _send_editor_static(panel_id, "bearbeiten.css", "text/css; charset=utf-8")


@app.route("/api/v1/panels/", methods=["POST"])
def post_panel():
    """PREG-15: Panel-Instanz anlegen.

    JSON-Body `{slug, display_id, router_url?, config?, tiles?}`:

    - `slug` (Pflicht) — Basis der `panel_id` (PREG-6); der Server vergibt die
      `panel_id` kollisionsfrei, der Client liefert sie NICHT.
    - `display_id` (Pflicht) — gegen die Geräte-Registry validiert (PREG-7).
    - `router_url` (optional, Default leer = same-origin, PREG-8).
    - `config` (optional) — Tuning-Felder (z. B. `backoffs`); die
      Identitätsfelder (`source_id`, `display_id`, `router_url`) werden vom
      Server gesetzt und überschreiben alle gleichnamigen Aufrufer-Werte
      (PREG-15 server-autoritativer `config`-Aufbau, Nic-Entscheid 2026-06-03).
    - `tiles` (optional) — PANEL-3; fehlt es, leere Kachel-Liste.

    Antwort 200 mit dem Panel-JSON inkl. vergebener `panel_id` und abgeleitetem
    `source_id`. Unbekanntes `display_id` → 400; Geräte-Registry nicht
    erreichbar → 503; Schreibfehler → 503 (panels.json bleibt unverändert).
    Read-Modify-Write läuft hinter `_write_lock` (parallele POSTs erhalten
    verschiedene `panel_id`s, beide Einträge landen, DCOMP-4 atomar).
    """
    path = runtime.get("registry_path")
    if path is None:
        return jsonify({"error": "kein Registry-Pfad konfiguriert"}), 503

    body = request.get_json(silent=True) or {}
    slug = (body.get("slug") or "").strip()
    display_id = (body.get("display_id") or "").strip()
    router_url = (body.get("router_url") or "").strip()
    caller_config = body.get("config")
    tiles = body.get("tiles")

    if not slug:
        return _bad_request("slug fehlt")
    if not display_id:
        return _bad_request("display_id fehlt")
    if caller_config is None:
        caller_config = {}
    if tiles is None:
        tiles = {}
    if not isinstance(caller_config, dict):
        return _bad_request("config muss ein Objekt sein (PANEL-8)")
    if not isinstance(tiles, dict):
        return _bad_request("tiles muss ein Objekt sein (PANEL-3)")

    # PREG-7: display_id gegen die Geräte-Registry validieren (GER-14, HTTP).
    try:
        if not display_existiert(display_id):
            return _bad_request(
                "display_id %r in der Geräte-Registry unbekannt (PREG-7)"
                % display_id)
    except _GeraeteUnreachable as e:
        return jsonify({"error": "Geräte-Registry nicht erreichbar: %s" % e}), 503

    with _write_lock:
        # DCOMP-2: frisch von Disk lesen — sonst überschreiben parallele Writes.
        reg = registry_mod.load(path)
        try:
            panel_id = registry_mod.neue_id(reg, slug)
        except (registry_mod.RegistryError, ValueError) as e:
            return _bad_request(str(e))

        # PREG-15 server-autoritativer config-Aufbau (Nic-Entscheid 2026-06-03):
        # Merge-Regel: Aufrufer-Tuning zuerst, dann server-Identität überschreibt.
        # So bleibt Tuning (backoffs, …) erhalten, Identitätsfelder sind immer
        # server-gesetzt — auch wenn der Aufrufer sie weggelassen oder falsch
        # gesetzt hätte (PANEL-8: source_id/display_id/router_url sind Pflicht).
        config = dict(caller_config)
        config["source_id"] = registry_mod.source_id_for(panel_id)
        config["display_id"] = display_id
        config["router_url"] = router_url

        try:
            panel = registry_mod.Panel(
                panel_id=panel_id, display_id=display_id,
                config=config, tiles=tiles, router_url=router_url)
            reg.add(panel)
        except registry_mod.RegistryError as e:
            return _bad_request(str(e))
        try:
            registry_mod.save(reg, path)
        except registry_mod.RegistryError as e:
            logging.warning("post_panel: Schreiben fehlgeschlagen: %s", e)
            return jsonify({"error": str(e)}), 503

    # PREG-16 Forward-on-Create: panels.json-Eintrag geschrieben → Router-Eintrag
    # nachziehen (ROU-29). Scheitert Step 2, bleibt panels.json-Eintrag gültig,
    # aber die Instanz ist reconcile-pending (Warnung + Signal an Aufrufer).
    try:
        router_panels_upsert(panel.source_id, panel.display_id)
        return jsonify(panel.to_dict()), 200
    except _RouterUnreachable as e:
        logging.warning(
            "post_panel: reconcile-pending für panel_id=%r source_id=%r: %s"
            " — panels.json-Eintrag gültig, Router-Eintrag fehlt (PREG-16)",
            panel.panel_id, panel.source_id, e)
        result = panel.to_dict()
        result["reconcile_pending"] = True
        return jsonify(result), 202


# ============================================================
#  Entrypoint (PREG-11)
# ============================================================

# Runtime-Konfig-Schema (CONFIG-1): nur die Werte, die der Service-Start
# braucht — Bind, Log-Level. Datei + ENV laufen über `tools.configloader`,
# CLI-Flags überschreiben den Loader-Output danach. Familienspezifische Werte
# (Panels selbst) liegen in `panels.json` (PREG-4).
RUNTIME_SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5041,
    "log_level":   "INFO",
}


def _parse_heal_boot_backoffs(raw):
    """Parst die HEAL_BOOT_BACKOFFS-Konfiguration (PREG-11/PREG-18).

    Erwartet eine kommagetrennte Folge von Sekunden-Zahlen (z. B. „0.2,1,2,5").
    Leerer String → leere Liste (genau ein Versuch, kein Retry — PREG-11).
    Parsefehler → Warnung + Default-Werte statt Absturz (defensiv).
    """
    stripped = raw.strip()
    if not stripped:
        return []
    try:
        return [float(s.strip()) for s in stripped.split(",") if s.strip()]
    except ValueError:
        logging.warning(
            "HEAL_BOOT_BACKOFFS=%r nicht parsebar — Default-Werte werden verwendet",
            raw)
        return list(_DEFAULT_HEAL_BOOT_BACKOFFS)


def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Panel-Registry V1")
    # PREG-11: Pfad zur Registry-Datei kann nicht in der Datei selbst stehen.
    p.add_argument("--panels", default="panels.json",
                   help="Pfad zur Registry-Datei (PREG-4/11)")
    p.add_argument("--geraete-url", dest="geraete_url",
                   help="Origin der Geräte-Registry (PREG-7/11)")
    p.add_argument("--router-url", dest="router_url",
                   help="Origin des Routers für Forward/Repair via ROU-29 (PREG-11/16/17)")
    p.add_argument("--heal-boot-backoffs", dest="heal_boot_backoffs",
                   help="Kommagetrennte Backoff-Intervalle (Sekunden) für die "
                        "Heal-on-Boot-Erreichbarkeits-Probe (PREG-11/18). "
                        "Leer = genau ein Versuch, kein Retry.")
    p.add_argument("--host", help="Bind-Host")
    p.add_argument("--port", type=int, help="Bind-Port")
    p.add_argument("--log-level", dest="log_level",
                   help="DEBUG | INFO | WARNING | ERROR")
    p.add_argument("--cert", help="TLS-Cert (optional, für HTTPS-Modus)")
    p.add_argument("--key",  help="TLS-Key (optional, für HTTPS-Modus)")
    return p.parse_args(argv)


def resolved_config(args):
    """Auflösung der RUNTIME-Konfiguration: Datei < ENV < CLI (CONFIG-1).

    Host/Port/Log-Level kommen vom gemeinsamen `tools.configloader`. `panels`
    (Registry-Pfad, PREG-11), `geraete_url` (Geräte-Registry-Origin, PREG-7/11)
    und `router_url` (Router-Origin, PREG-11/16/17) bleiben außerhalb des
    Loader-Schemas — analog geraete/main.py. ENV-Overrides decken den Dev-Override
    ab (`PANELS_REGISTRY`, `GERAETE_URL`, `ROUTER_URL`, `HEAL_BOOT_BACKOFFS`).
    """
    cfg = configloader.load(component="panel", schema=RUNTIME_SCHEMA)
    cfg["panels"] = os.environ.get("PANELS_REGISTRY", args.panels)
    cfg["geraete_url"] = (
        args.geraete_url
        or os.environ.get("GERAETE_URL", "http://127.0.0.1:5040"))
    cfg["router_url"] = (
        args.router_url
        or os.environ.get("ROUTER_URL", "http://127.0.0.1:5000"))
    # PREG-11/PREG-18: Backoff-Folge (CLI > ENV > Default).
    # Nur wenn CLI-Arg oder ENV explizit gesetzt → parsen; sonst Default.
    _heal_raw = args.heal_boot_backoffs
    if _heal_raw is None:
        _heal_env = os.environ.get("HEAL_BOOT_BACKOFFS")
        if _heal_env is not None:
            cfg["heal_boot_backoffs"] = _parse_heal_boot_backoffs(_heal_env)
        else:
            cfg["heal_boot_backoffs"] = list(_DEFAULT_HEAL_BOOT_BACKOFFS)
    else:
        cfg["heal_boot_backoffs"] = _parse_heal_boot_backoffs(_heal_raw)
    if args.host:      cfg["listen_host"] = args.host
    if args.port:      cfg["listen_port"] = args.port
    if args.log_level: cfg["log_level"]   = args.log_level
    return cfg


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    cfg = resolved_config(args)
    logsetup.setup(cfg["log_level"])

    reg = registry_mod.load(cfg["panels"])
    configure(reg, registry_path=cfg["panels"],
              geraete_url=cfg["geraete_url"], router_url=cfg["router_url"])

    # PREG-17/PREG-18 Heal-on-Boot: einmaliger Repair-Lauf VOR dem Annehmen
    # von Anfragen. PREG-18 macht den Lauf robust gegen noch-nicht-gestarteten
    # Router: pollt mit Backoff bis Router antwortet, bei Cap-Ablauf nicht-fatal.
    # Schreibt jeden panels.json-Eintrag blind via ROU-29 (idempotenter Upsert —
    # kein Zurücklesen des Router-Stands, kein Lese-Endpunkt, Nic-Entscheid 2026-
    # 06-04). Einzelne Upsert-Fehler sind nicht-fatal (PREG-17 Robustheit).
    panels_beim_start = reg.list_all()
    if panels_beim_start:
        repair_heal_on_boot(panels_beim_start,
                            backoffs=cfg["heal_boot_backoffs"])
    else:
        logging.info("Heal-on-Boot: keine Panels in panels.json — kein Repair nötig")

    ssl_context = None
    scheme = "http"
    if args.cert and args.key:
        ssl_context = (args.cert, args.key)
        scheme = "https"
    logging.info(
        "Panel-Registry hört auf %s://%s:%s (panels=%s, geraete=%s, router=%s)",
        scheme, cfg["listen_host"], cfg["listen_port"],
        cfg["panels"], cfg["geraete_url"], cfg["router_url"])
    app.run(host=cfg["listen_host"], port=cfg["listen_port"],
            debug=False, threaded=True, ssl_context=ssl_context)


if __name__ == "__main__":
    main()
