"""Wetter-Buddy — View-Modell des Garderoben-Editors (WETTER-27).

Siehe specs/buddies/wetter.md §10. Dieses Modul baut aus dem geladenen
wetter.json-Stand und der kuratierten Palette das View-Modell für die
Eltern-Editor-Seite (`templates/wetter_regeln.html`) — Muster **Übersicht +
Fokus** (WETTER-27): je Regel die read-only Bedingung (menschenlesbar) plus
Pflicht-/Optional-Set und Hinweis, dazu das Fallback und die wählbare Palette.

Reine Transformation, **kein IO** (CLAUDE.md §6, eine Verantwortung): die
Garderobe wird vom Aufrufer (main.py) geladen und hereingereicht. Piktogramme
werden über die geteilte Icon-Plattform referenziert (ICONS-5, WETTER-18) —
dieselbe `render.icon_url`, die der Kiosk nutzt, kein zweiter Icon-Pfad.
"""

from . import render as render_mod

# WETTER-27: menschenlesbare Labels der read-only Bedingungs-Schwellen. Nur zur
# Orientierung der Eltern — editierbar sind sie NICHT (WETTER-28).
_SCHWELLE_LABELS = (
    ("feels_min", "gefühlt ab %s°"),
    ("feels_max", "gefühlt bis %s°"),
    ("rain_prob_min", "Regen-Wahrscheinlichkeit ab %s%%"),
    ("rain_amount_min", "Regenmenge ab %s mm"),
    ("wind_min", "Wind ab %s km/h"),
)


def _bedingung_text(bedingung):
    """Baut die read-only Bedingung als kurze, menschenlesbare Liste (WETTER-27).

    Liefert eine Liste von Textbausteinen — leer, wenn die Regel keine Schwelle
    setzt (matcht dann immer). `sunscreen` wird als Sonnen-Bedingung gezeigt.
    """
    bedingung = bedingung or {}
    teile = []
    for key, vorlage in _SCHWELLE_LABELS:
        wert = bedingung.get(key)
        if wert is not None:
            teile.append(vorlage % _zahl(wert))
    sun = bedingung.get("sunscreen")
    if sun is not None:
        teile.append("bei Sonne" if sun else "ohne Sonne")
    return teile


def _zahl(wert):
    """Stellt eine Schwelle kompakt dar — ganze Zahl ohne `.0`-Schwanz."""
    try:
        f = float(wert)
    except (TypeError, ValueError):
        return str(wert)
    return str(int(f)) if f == int(f) else str(f)


def _set_view(stuecke):
    """View eines Kleidungs-Sets: `{name, pikto, icon_url}` je Stück (WETTER-18)."""
    return [
        {"name": str(s.get("name", "")),
         "pikto": str(s.get("pikto", "")),
         "icon_url": render_mod.icon_url(s.get("pikto"))}
        for s in (stuecke or [])
    ]


def _regel_view(roh_regel, index):
    """View einer Regel (WETTER-27): read-only Bedingung + editierbare Sets."""
    return {
        "index": index,
        "bedingung_text": _bedingung_text(roh_regel.get("bedingung")),
        "hinweis": str(roh_regel.get("hinweis", "")),
        "pflicht": _set_view(roh_regel.get("pflicht")),
        "optional": _set_view(roh_regel.get("optional")),
    }


def baue_view(geladener_stand, palette):
    """Baut das vollständige Editor-View-Modell (WETTER-27).

    `geladener_stand` ist der frisch geladene wetter.json-Inhalt (dict);
    `palette` das palette-Modul. Liefert ein dict für
    `templates/wetter_regeln.html`: die geordnete Regel-Liste (erste passende
    gewinnt, WETTER-14), das Fallback und die wählbare Palette mit Icon-URLs.
    """
    wardrobe = geladener_stand.get("wardrobe") or {}
    regeln = [
        _regel_view(roh, i)
        for i, roh in enumerate(wardrobe.get("regeln") or [])
    ]
    roh_fb = wardrobe.get("fallback") or {}
    fallback = {
        "hinweis": str(roh_fb.get("hinweis", "")),
        "pflicht": _set_view(roh_fb.get("pflicht")),
        "optional": _set_view(roh_fb.get("optional")),
    }
    palette_view = [
        {"name": s["name"], "pikto": s["pikto"],
         "icon_url": render_mod.icon_url(s["pikto"])}
        for s in palette.laden()
    ]
    return {
        "regeln": regeln,
        "fallback": fallback,
        "palette": palette_view,
    }
