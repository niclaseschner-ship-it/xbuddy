"""Gemeinsamer Instanzen-Reader nach `conventions/instanzen-config.md` (INST-1..6).

Manche Buddy-Klassen laufen in mehreren Instanzen auf demselben Pi (der
Hörspiel-Buddy z. B. einmal je Kind). Welche Instanzen es gibt und wie sie in
der App heißen, lebt in der Repo-Root-Datei `instanzen.json` (gitignored,
live) — die **einzige Wahrheit** (INST-1). Statt die Liste an vier Stellen im
Code zu duplizieren (`eltern-chat/tasks.py`, `seiten/main.py`,
`hoerspiel/config.py`, `app.js`), werden diese Stellen zu **Lesern** dieser
Datei.

## Guard-Vertrag (INST-3, HART): nur lesen/anzeigen, nie generieren

Dieser Reader **liest und zeigt** die Instanz-Liste. Er generiert **NIE**
Ports, Routing, nginx-Origins oder systemd-Units. `port` und `origin` in der
Datei sind **Lese-Spiegel** der handverdrahteten Betriebs-Realität
(`conventions/ports.md`, nginx-Conf, systemd-Units bleiben SSoT für den
Betrieb). `origin` wird höchstens **durchgereicht**, nie konstruiert.

## Fehlt/kaputt → Default + Warnung (INST-6)

Existiert `instanzen.json` nicht oder ist sie nicht parsebar, greift der
eingebettete generische Code-Default (`kind1`/`kind2`, generische Namen — NIE
echte Namen), eine Warnung wird geloggt, und der Aufrufer startet weiter.
Eine fehlende Datei ist der normale Repo-Default-Zustand vor dem Onboarding.

## Public API

    from tools import instanzen

    liste = instanzen.lade_instanzen("hoerspiel")
    # -> [{"slug": ..., "port": ..., "origin": ..., "display_name": ...}, ...]

Pfad-Auflösung: Default ist die Repo-Root-`instanzen.json`. Für Tests kann
`INSTANZEN_CONFIG_FILE` (ENV) oder das Argument `pfad` den Pfad überschreiben
(Muster `hoerspiel/config.py` `ENV_*`).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# Repo-Root = ein Verzeichnis über tools/ (Muster tools/sync_kibuddy_env.py).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_FILE = os.path.join(_REPO_ROOT, "instanzen.json")

ENV_CONFIG_FILE = "INSTANZEN_CONFIG_FILE"

# INST-2 — genau vier Felder je Eintrag.
_FELDER = ("slug", "port", "origin", "display_name")

# INST-6 — eingebetteter generischer Fallback je Klasse. NIE echte Namen.
# Bewusst STERIL: opake Slugs `kind1`/`kind2` + `port` 0/leere `origin`, damit
# nichts aus dem Default einen echten Betriebs-Port ableitet (INST-3). Das ist
# ein anderer Zweck als die getrackte `instanzen.example.json`: die trägt die
# populierte Demo-Familie »Sonntag« (`mia`/`finn`/`emil` mit echten Beispiel-
# Ports, deckungsgleich mit `conventions/ports.md`, #1748) als Kopiervorlage.
_FALLBACK_DEFAULTS: "dict[str, list[dict]]" = {
    "hoerspiel": [
        {"slug": "kind1", "port": 0, "origin": "", "display_name": "Kind Eins"},
        {"slug": "kind2", "port": 0, "origin": "", "display_name": "Kind Zwei"},
    ],
}


def lade_instanzen(klasse="hoerspiel", pfad=None):
    """Liest die Instanz-Liste einer Buddy-Klasse aus `instanzen.json` (INST-1).

    Args:
        klasse: Buddy-Klasse (Top-Level-Key in der Datei, z. B. `"hoerspiel"`).
        pfad: Pfad zur Config-Datei. `None` = ENV `INSTANZEN_CONFIG_FILE`
            oder Default Repo-Root `instanzen.json`.

    Returns:
        Liste von Einträgen `{slug, port, origin, display_name}` (INST-2).
        Fehlt/kaputt die Datei oder die Klasse, kommt der eingebettete
        Fallback-Default + eine geloggte Warnung (INST-6) — nie eine Exception
        nach außen.
    """
    if pfad is None:
        pfad = os.environ.get(ENV_CONFIG_FILE) or DEFAULT_CONFIG_FILE

    data = _lade_datei(pfad, klasse)
    if data is None:
        return _fallback(klasse)

    roh = data.get(klasse)
    if not isinstance(roh, list):
        logger.warning(
            "instanzen: Klasse %r fehlt oder ist keine Liste in %s — "
            "eingebetteter Default gilt (INST-6)", klasse, pfad)
        return _fallback(klasse)

    # INST-2: nur die vier bekannten Felder durchreichen (kein Generieren,
    # INST-3 — `origin` wird durchgereicht, nie konstruiert).
    eintraege = [
        {feld: eintrag.get(feld) for feld in _FELDER}
        for eintrag in roh
        if isinstance(eintrag, dict)
    ]
    return eintraege


def _lade_datei(pfad, klasse):
    """Liest+parst die JSON-Datei. Fehlt/kaputt → None (INST-6 → Fallback)."""
    try:
        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning(
            "instanzen: %s nicht gefunden — eingebetteter Default fuer %r gilt "
            "(INST-6; fehlende Datei ist der normale Repo-Default vor Onboarding)",
            pfad, klasse)
        return None
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(
            "instanzen: %s nicht lesbar/parsebar (%s) — eingebetteter Default "
            "fuer %r gilt (INST-6)", pfad, e, klasse)
        return None
    if not isinstance(data, dict):
        logger.warning(
            "instanzen: %s ist kein JSON-Objekt — eingebetteter Default fuer %r "
            "gilt (INST-6)", pfad, klasse)
        return None
    return data


def _fallback(klasse):
    """Eingebetteter Default fuer eine Klasse (INST-6). Kopie, damit Aufrufer
    die interne Liste nicht mutieren."""
    return [dict(eintrag) for eintrag in _FALLBACK_DEFAULTS.get(klasse, [])]
