"""Wetter-Buddy — Render-Logik der View `heute` (WETTER-2 … WETTER-13, WETTER-18/19).

Siehe specs/buddies/wetter.md §1-4, §6. Dieses Modul baut aus den zwei
Tageszeit-Wettern (meteo.py) und den Garderoben-Outfits (clothing.py) das
View-Modell, das `templates/wetter_heute.html` rendert — ein Diptychon aus
Wetter-Karte (links) und Anziehen-Karte (rechts), Stufe `toddler` (WETTER-2/4).

Drei Verkabelungs-Aufgaben löst dieses Modul:
  1. ARASAAC-Piktogramme über die geteilte Icon-Plattform-URL referenzieren
     (ICONS-5, WETTER-18) — nicht über den ARASAAC-CDN des Mockups.
  2. UV NIE in die Ausgabe (WETTER-11, E-WETTER-2) — nur der `sunscreen`-Boolean
     steuert die Sonnencreme-Karte. Das View-Modell trägt `uv`/`uvLabel` nicht.
  3. Das Temperatur-Spektrum (WETTER-9) als Prozent-Positionen rechnen, damit
     der Gradient-Balken die heute erwartete Spanne (low–high) hervorhebt.

WETTER-7 (E-WETTER-11): Der Wetter-Zustands-Hero ist die app-eigene Wetter-Szene
(Haus + Himmel, Inline-SVG im Template) — kein ARASAAC-Hero-Piktogramm.
Die `kind`-Kategorie wählt die Szenen-Variante direkt im Template. Die
ARASAAC/ICONS-5-Anbindung gilt für Outfit-Piktogramme (WETTER-13/18), nicht
für den Zustands-Hero.
"""

import logging

from . import meteo as meteo_mod

logger = logging.getLogger(__name__)

# WETTER-18/ICONS-5: die geteilte Icon-Plattform-URL. Piktogramme werden NICHT
# buddy-eigen vom ARASAAC-CDN bezogen (wie im Mockup-Prototyp), sondern über
# diese read-only-URL, die der Router aus der icon-root serviert (ROU-26).
ICON_BASIS = "/display/_shared/icons/arasaac/"

# WETTER-9: das gesamte mögliche Temperatur-Spektrum des Balkens (Grad). Der
# Mockup-Balken läuft von −5° bis 35°. Diese Grenzen rahmen die Prozent-
# Rechnung der heute erwarteten Spanne.
SPEKTRUM_MIN = -5.0
SPEKTRUM_MAX = 35.0


def icon_url(pikto_id):
    """Geteilte Icon-Plattform-URL einer ARASAAC-ID (ICONS-5, WETTER-18).

    Wird für Inhalts-Piktogramme genutzt (Kleidung/Outfit, WETTER-13/18).
    Der Wetter-Zustands-Hero ist die app-eigene Haus-SVG-Szene (WETTER-7,
    E-WETTER-11) — kein ARASAAC-Piktogramm.
    Liefert None für eine leere ID — die View zeigt dann keinen Piktogramm-Slot.
    """
    if pikto_id in (None, ""):
        return None
    return ICON_BASIS + str(pikto_id) + ".png"


def _gefuehlt_label(feels):
    """Kurztext zur gefühlten Temperatur (WETTER-8). Kindgerecht, knapp."""
    if feels is None:
        return ""
    if feels < 4:
        return "gefühlt kalt"
    if feels < 12:
        return "gefühlt kühl"
    if feels < 22:
        return "gefühlt mild"
    if feels < 28:
        return "gefühlt warm"
    return "gefühlt heiß"


def _prozent(wert):
    """Position eines Temperatur-Werts auf dem Spektrum-Balken in Prozent (WETTER-9).

    Geklemmt auf [0, 100], damit ein Ausreißer den Balken nicht verlässt.
    """
    if wert is None:
        return None
    p = (wert - SPEKTRUM_MIN) / (SPEKTRUM_MAX - SPEKTRUM_MIN) * 100.0
    return max(0.0, min(100.0, p))


def _runde(wert):
    """Ganzzahlige Temperatur für die Anzeige (WETTER-8). None bleibt None."""
    if wert is None:
        return None
    return int(round(wert))


def _wetter_view(wetter):
    """View-Modell einer Tageszeit-Wetter-Karte (WETTER-7..11).

    `kind` wird direkt übergeben — das Template wählt daraus die Haus-Wetter-
    Szene (WETTER-7, E-WETTER-11). Kein hero_pikto: der Wetter-Zustands-Hero
    ist die app-eigene Inline-SVG, kein ARASAAC-Piktogramm.

    Wichtig (WETTER-11, E-WETTER-2): `uv`/`uvLabel` werden NICHT übernommen —
    nur `sunscreen` als Boolean. Das ist die Stelle, an der der UV-Wert vor dem
    Kind verschwindet.
    """
    return {
        "desc": wetter.desc,
        "kind": wetter.kind,
        "temp": _runde(wetter.temp),
        "feels": _runde(wetter.feelsLike),
        "feels_label": _gefuehlt_label(wetter.feelsLike),
        "low": _runde(wetter.low),
        "high": _runde(wetter.high),
        "wind": wetter.wind,
        "rain_prob": wetter.rainProb,
        "rain_amount": wetter.rainAmount,
        "sunscreen": bool(wetter.sunscreen),
        "neutral": wetter.kind == meteo_mod.KIND_NEUTRAL,
        # WETTER-9: Spektrum-Positionen der heute erwarteten Spanne.
        "low_pct": _prozent(wetter.low),
        "high_pct": _prozent(wetter.high),
    }


def _eimer_stufen(rain_amount, rain_prob):
    """Regen-Eimer-Füllstufe 0..4 als Bild-Skala (WETTER-10).

    Aus der Menge (`rainAmount` in mm) abgeleitet; fehlt die Menge, dient die
    Wahrscheinlichkeit als grobe Ersatz-Skala. Kein nackter Zahlenwert — die
    View malt die Stufe als gefüllte/leere Punkte (WETTER-10).
    """
    if rain_amount is not None:
        if rain_amount <= 0.0:
            return 0
        if rain_amount < 1.0:
            return 1
        if rain_amount < 3.0:
            return 2
        if rain_amount < 6.0:
            return 3
        return 4
    if rain_prob is not None:
        return min(4, int(rain_prob // 25))
    return 0


def _wind_stufen(wind):
    """Wind-Gauge-Stufe 0..5 als Bild-Skala (WETTER-10).

    Aus der Windgeschwindigkeit (km/h) abgeleitet. Kein nackter Zahlenwert —
    die View malt aktive/inaktive Balken (WETTER-10).
    """
    if wind is None:
        return 0
    schwellen = (5, 12, 20, 30, 45)  # km/h
    stufe = 0
    for s in schwellen:
        if wind >= s:
            stufe += 1
    return stufe


def _metrik_view(wetter):
    """View-Modell der drei Metrik-Karten als Bild-Skalen (WETTER-10)."""
    return {
        "eimer": _eimer_stufen(wetter.rainAmount, wetter.rainProb),
        "wind": _wind_stufen(wetter.wind),
        # WETTER-11: nur der Boolean — keine UV-Zahl, kein UV-Label.
        "sunscreen": bool(wetter.sunscreen),
    }


def _outfit_view(outfit):
    """View-Modell eines Outfit-Blocks mit Icon-URLs (WETTER-13, WETTER-18)."""
    def _teil(k):
        return {"name": k.name, "pikto": icon_url(k.pikto)}
    return {
        "pflicht": [_teil(k) for k in outfit.pflicht],
        "optional": [_teil(k) for k in outfit.optional],
        "hinweis": outfit.hinweis,
    }


def baue_view(cfg, morgens, mittags, fuer_morgen=False):
    """Baut das vollständige View-Modell der View `heute` (WETTER-2 … WETTER-13).

    cfg          wetter.config.Config — für die Garderoben-Regeln (WETTER-14)
    morgens      meteo.Tageswetter der Morgens-Tageszeit (WETTER-5)
    mittags      meteo.Tageswetter der Mittags-Tageszeit (WETTER-5)
    fuer_morgen  True, wenn der Abend-Rollover greift (WETTER-6) — die View
                 zeigt dann „morgen" statt „heute" im Tages-Label.

    Beide Tageszeiten werden eigenständig gerechnet (WETTER-12, E-WETTER-10):
    je Tageszeit ein eigenes Wetter-Modell und ein eigenständig aus der
    gefühlten Temperatur abgeleitetes Outfit (WETTER-14). Liefert ein dict für
    `templates/wetter_heute.html`.
    """
    outfit_morgens = cfg.garderobe.outfit_fuer(morgens)
    outfit_mittags = cfg.garderobe.outfit_fuer(mittags)

    return {
        "fuer_morgen": fuer_morgen,
        "tages_label": "Morgen" if fuer_morgen else "Heute",
        # Die Wetter-Karte (links) zeigt das Hero/Spektrum/Metriken des Tages.
        # Hero + Spektrum stützen sich auf die Mittags-Tageszeit (der Tag „in
        # voller Fahrt"); low/high sind ohnehin die gemeinsame Tagesspanne.
        "wetter": _wetter_view(mittags),
        "metrik": _metrik_view(mittags),
        # Die Anziehen-Karte (rechts) zeigt beide Tageszeit-Blöcke (WETTER-12).
        "bloecke": [
            {
                "tageszeit": "Morgens",
                "wetter": _wetter_view(morgens),
                "outfit": _outfit_view(outfit_morgens),
            },
            {
                "tageszeit": "Mittags",
                "wetter": _wetter_view(mittags),
                "outfit": _outfit_view(outfit_mittags),
            },
        ],
    }
