"""Plan-Buddy — Aktivitäts-Katalog (PLAN-12, PLAN-13, E-PLAN-8, PLAN-34).

EINE Quelle für die familienspezifische Liste der Kind-Aktivitäten. Sowohl
die Lese-Seite (Titel → Art, `render.py`) als auch die Schreib-Seite (Art →
Titel-Label, `main.py`) beziehen sich auf diesen Katalog.

Seit #308 speist dieser Katalog zusätzlich PLAN-13: `icon_fuer_art()` liefert
den Termin-Icon-Key für eine Art, `termin_icon_keywords_aus_katalog()` erzeugt
die zugehörigen (keyword, icon)-Paare für `render.py`. Damit sind
Aktivitäts-Erkennung (PLAN-12) und Termin-Icon-Zuordnung (PLAN-13) konsistent.

Seit #445/#578 (PLAN-28/PLAN-34) ist der Katalog dateigetrieben: die Quelle
ist die `aktivitaeten`-Section in `plan.json` (via `Config.aktivitaeten`).
Fehlt die Section, greift AKTIVITAETEN_V1 als CONFIG-4-Fallback (E-PLAN-8).

Alle Funktionen nehmen einen optionalen `config`-Parameter (plan.config.Config).
Ist er None oder hat er kein `aktivitaeten`-Feld (== None), greift
AKTIVITAETEN_V1. So bleibt render.py — das termin_icon_keywords_aus_katalog()
ohne Config beim Modul-Import aufruft — unverändert lauffähig.
"""

# PLAN-12/PLAN-28: V1-Default-Katalog — CONFIG-4-Fallback, wenn plan.json keine
# `aktivitaeten`-Section hat (E-PLAN-8 V1.2). Format je Eintrag:
# { "art": <schlüssel>, "label": <text>, "keywords": [<str>, …],
#   "piktogramm": <arasaac-id-string> }
#
# `piktogramm` hier als leerer String — ARASAAC-Ids werden in V1 per
# Direkt-Edit oder PAS-Skill gesetzt (PLAN-28). Der Fallback rendert das
# generische Symbol (ICONS-7-Garantie greift nur bei IDs aus der Suche).
#
# Reihenfolge zählt: bei der Lese-Heuristik gewinnt der erste Treffer in
# der flachen keyword-Liste. Die hiesige Reihenfolge bewahrt das alte
# Verhalten aus `render.AKTIVITAETS_KEYWORDS` 1:1 (Refs #101).
AKTIVITAETEN_V1 = [
    {"art": "klettern",    "label": "Klettern",    "keywords": ["klettern"],
     "piktogramm": ""},
    {"art": "kreativ",     "label": "Kreativ",     "keywords": ["kreativ"],
     "piktogramm": ""},
    {"art": "schwimmen",   "label": "Schwimmen",   "keywords": ["schwimm"],
     "piktogramm": ""},
    {"art": "spielplatz",  "label": "Spielplatz",  "keywords": ["spielplatz"],
     "piktogramm": ""},
    {"art": "musik",       "label": "Musik",
     "keywords": ["musik", "klavier", "geige", "gitarre"],
     "piktogramm": ""},
    {"art": "ausflug",     "label": "Ausflug",     "keywords": ["ausflug"],
     "piktogramm": ""},
    {"art": "geburtstag",  "label": "Geburtstag",
     "keywords": ["geburtstag", "geburts"],
     "piktogramm": ""},
    {"art": "petrabredung", "label": "Petrabredung", "keywords": ["petrabredung"],
     "piktogramm": ""},
    {"art": "waldgang",    "label": "Waldgang",    "keywords": ["wald"],
     "piktogramm": ""},
]

# PLAN-13: Art → Termin-Icon-Key (V1-Default; spiegelt _ART_ZU_ICON aus #308).
# Bleibt als Konstante, da render.py keinen Config-Zugriff hat.
_ICON_V1 = {
    "klettern":    "climb",
    "kreativ":     "brush",
    "schwimmen":   "wave",
    "spielplatz":  "play",
    "musik":       "music",
    "ausflug":     "pin",
    "geburtstag":  "cake",
    "petrabredung": "friends",
    "waldgang":    "trees",
}


def _katalog(config=None):
    """Liefert die aktive Aktivitäts-Liste als dicts (PLAN-12, CONFIG-4).

    Reihenfolge: Config.aktivitaeten (als to_dict()-Dicts) → AKTIVITAETEN_V1.
    """
    if config is not None and getattr(config, "aktivitaeten", None) is not None:
        return [a.to_dict() for a in config.aktivitaeten]
    return AKTIVITAETEN_V1


def keyword_paare(config=None):
    """Flache Liste `(keyword, art)` in Reihenfolge der Heuristik (PLAN-12).

    Lese-Seite: der erste Treffer im Titel gewinnt. Optional `config` für
    den dateigetriebenen Katalog; ohne → AKTIVITAETEN_V1 (CONFIG-4-Fallback).
    """
    return [
        (kw, entry["art"])
        for entry in _katalog(config)
        for kw in entry["keywords"]
    ]


def art_aus_titel(titel, config=None):
    """Aktivitäts-Art aus einem Titel-Schlüsselwort (PLAN-12). None, wenn keins passt."""
    s = (titel or "").lower()
    for needle, art in keyword_paare(config):
        if needle in s:
            return art
    return None


def label_fuer_art(art, config=None):
    """Anzeige-Label einer Aktivitäts-Art für den Event-Titel (PLAN-11)."""
    for entry in _katalog(config):
        if entry["art"] == art:
            return entry["label"]
    # Unbekannte Art: capitalize als Fallback (altes Verhalten).
    return art.capitalize() if art else art


def icon_fuer_art(art, config=None):
    """Termin-Icon-Key für eine Aktivitäts-Art (PLAN-13).

    Liest aus dem aktiven Katalog; unbekannte Art → None. Fällt für
    Icon-Keys, die nicht im Katalog stehen, auf _ICON_V1 zurück (render.py
    erwartet immer einen Key für die bekannten V1-Arten). Wird von
    `render.py` über `termin_icon_keywords_aus_katalog()` genutzt (#308).
    """
    # Zuerst V1-Map — render.py kennt nur diese Icon-Keys.
    v1_icon = _ICON_V1.get(art)
    if v1_icon is not None:
        return v1_icon
    # Falls eine neue Art via PLAN-34-POST hinzugekommen ist und einen
    # "piktogramm"-Wert hat, ist kein Icon-Key im V1-Schema vorhanden —
    # render.py fällt auf den generischen Fallback zurück. None ist korrekt.
    return None


def termin_icon_keywords_aus_katalog(config=None):
    """Flache Liste `(keyword, icon_key)` aus dem Aktivitäts-Katalog (PLAN-13).

    Liefert für jedes Keyword jeder Aktivitäts-Art den zugehörigen Icon-Key.
    Arten ohne Icon-Eintrag in _ICON_V1 werden übersprungen (render.py kennt
    nur die V1-Icon-Keys). Wird von `render.py` als Teil von
    TERMIN_ICON_KEYWORDS verwendet (#308).

    `render.py` ruft diese Funktion beim Modul-Import ohne Config auf —
    dann greift CONFIG-4-Fallback AKTIVITAETEN_V1 + _ICON_V1.
    """
    pairs = []
    for entry in _katalog(config):
        icon = _ICON_V1.get(entry["art"])
        if icon is None:
            continue
        for kw in entry["keywords"]:
            pairs.append((kw, icon))
    return pairs
