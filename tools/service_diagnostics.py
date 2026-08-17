"""Geteilte Diagnose-Naht der HTTP-Services (SVC-6).

EINE Definition des `/version`-Endpunkts, den alle Buddy-Services teilen — statt
12 byte-identischer Kopien (CLAUDE.md §6: dieselbe Logik nicht zweimal). Jeder
Service registriert die Route mit EINER Zeile::

    from tools.service_diagnostics import register_version
    register_version(app)

SVC-6: `/version` liefert die Commit-SHA **des Codes, den dieser Service gerade
ausfuehrt**. Ermittelt wird sie **einmal beim Start** und im Speicher gehalten;
jeder Service hat seinen **eigenen** Wert.

**Warum beim Start und nicht bei jeder Anfrage — das ist der ganze Zweck (#1788):**

Der Wert soll den **laufenden Prozess** beschreiben, nicht die Platte. Zieht
jemand neuen Code, ohne neu zu starten, muss `/version` weiterhin den **alten**
Stand melden. Das ist die Anzeige, an der man den faelligen Neustart erkennt.

Wer stattdessen bei jeder Anfrage nachsaehe, baute einen Endpunkt, der immer
"aktuell" meldet und **genau den einen Fehler unsichtbar macht**, fuer den er da
ist. Live-Beleg vom 2026-08-13: drei Tage alter Code lief, waehrend der neue
danebenlag — und alle zwoelf Endpunkte meldeten denselben veralteten Stand.

Dass jeder Service seinen eigenen Wert hat, ergibt sich ohne Zutun: dieses Modul
wird je Prozess **einmal** importiert, und jeder Service ist ein eigener Prozess.
Ein Dienst, der seit drei Tagen laeuft, haelt den SHA von damals; ein frisch
neugestarteter den von jetzt. Genau diese Unterscheidung konnte die frueher
gemeinsame Datei nicht ausdruecken.

**Was diese Fassung abloest** (SVC-6, geaendert 2026-08-13): frueher las jeder
Aufruf eine beim Deploy geschriebene **gemeinsame** Datei, und die Ermittlung zur
Laufzeit war ausdruecklich verboten. Beides ist ueberholt — die Datei wurde
faktisch nie geschrieben (der automatische Deploy-Pfad laeuft nicht, gearbeitet
wird von Hand), und eine gemeinsame Datei zeigt selbst dann den Stand des zuletzt
gestarteten Dienstes, wenn ein einzelner auf altem Code haengt. Die alte
Begruendung fuer das Verbot ("ein paralleler Worktree wuerde einen falschen SHA
einfrieren") stammt aus der Zeit vor dem Wirbelsaeulen-Abriss und traegt nicht
mehr.
"""

import os
import subprocess

from flask import jsonify

# Wurzel des Checkouts, aus dem dieser Prozess laeuft — abgeleitet vom eigenen
# Ort, nicht aus dem Arbeitsverzeichnis (das ist bei systemd-Units nicht der
# Checkout).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ermittle_laufende_version(repo_root: str = _REPO_ROOT) -> str | None:
    """Die Commit-SHA des Checkouts, aus dem dieser Prozess laeuft.

    Bewusst als Funktion und nicht inline, damit Tests sie mit einem eigenen
    `repo_root` pruefen koennen. Im Betrieb wird sie **genau einmal** aufgerufen
    — beim Import dieses Moduls, also beim Start des Service.

    Faellt sie aus (kein git, kein Checkout, Zeitueberschreitung), liefert
    `/version` `null`. Ein fehlender Wert ist ehrlicher als ein geratener: er
    sagt "unbekannt", waehrend ein Platzhalter-SHA eine Uebereinstimmung
    behaupten wuerde, die niemand geprueft hat.
    """
    try:
        ergebnis = subprocess.run(
            ["git", "-C", repo_root, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if ergebnis.returncode != 0:
        return None
    return ergebnis.stdout.strip() or None


# EINMAL beim Import — das ist der Startzeitpunkt des Service. Spaetere
# Aenderungen am Checkout aendern diesen Wert NICHT mehr, und genau das ist
# gewollt (siehe Modul-Docstring).
LAUFENDE_VERSION: str | None = ermittle_laufende_version()


def register_version(app):
    """Registriert `GET /version` (SVC-6) auf der Flask-`app`.

    Liefert den beim Start ermittelten Wert aus dem Speicher — **kein** Lesen
    zur Anfragezeit, weder aus einer Datei noch per git.
    """

    @app.route("/version", methods=["GET"])
    def version():
        """SVC-6: die Commit-SHA des Codes, den dieser Prozess ausfuehrt."""
        return jsonify({"version": LAUFENDE_VERSION}), 200

    return version
