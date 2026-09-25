"""Buddy-Logos (#1953) — Lesezugriff auf `seiten/logos.json`.

Nic 2026-09-25: jeder Buddy hat EIN eigenes, eindeutiges Logo. Dasselbe Logo
ist das PWA-Icon aller Mäntel dieses Buddys und das Bild seiner Karten auf der
Übersicht. Wahrheit ist `seiten/logos.json` (Buddy → ARASAAC-ID); die PNGs
erzeugt `seiten/static/logos/_make_logos.py` daraus.

Rein und ohne Flask — der Renderer (`render.py`) und die Tests lesen hier.
"""

from __future__ import annotations

import functools
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
LOGOS_JSON = os.path.join(_HERE, "logos.json")
LOGO_DIR = os.path.join(_HERE, "static", "logos")

# Die drei Pflicht-Icons eines Mantels (PWAM-2).
ICON_DATEIEN = ("icon-192.png", "icon-512.png", "icon-maskable-512.png")

# Öffentlicher Pfad der Logos (Flask-static des seiten-Service, nginx
# `location ^~ /api/v1/seiten/`).
_URL_PREFIX = "/api/v1/seiten/static/logos"


def _ohne_doc(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


@functools.lru_cache(maxsize=1)
def lade():
    """Liest `logos.json` einmal (Datei ist committeter Repo-Inhalt)."""
    with open(LOGOS_JSON, encoding="utf-8") as fh:
        roh = json.load(fh)
    return {
        "buddies": _ohne_doc(roh["buddies"]),
        "einstellungen": _ohne_doc(roh["einstellungen"]),
        "zuordnung": _ohne_doc(roh["zuordnung"]),
        "maentel": _ohne_doc(roh["maentel"]),
    }


def buddy_fuer(key, app):
    """Buddy eines Inventar-Eintrags: explizite Zuordnung, sonst der App-Slug."""
    return lade()["zuordnung"].get(key or "", app or "")


def hat_logo(buddy):
    return buddy in lade()["buddies"]


def logo_url(buddy, datei="icon-192.png"):
    """URL des Logos von `buddy` — None, wenn der Buddy (noch) keins hat."""
    if not hat_logo(buddy):
        return None
    return "%s/%s/%s" % (_URL_PREFIX, buddy, datei)


def name(buddy):
    eintrag = lade()["buddies"].get(buddy)
    return eintrag["name"] if eintrag else buddy


def ist_einstellung(buddy):
    return buddy in lade()["einstellungen"]["buddies"]
