"""Plan-Buddy — Aktivitäts-Katalog (PLAN-12, PLAN-13, E-PLAN-8).

EINE Quelle für die familienspezifische Liste der Kind-Aktivitäten. Sowohl
die Lese-Seite (Titel → Art, `render.py`) als auch die Schreib-Seite (Art →
Titel-Label, `main.py`) beziehen sich auf diesen Katalog — vorher lebten
beide Hälften in zwei voneinander entkoppelten Listen (Refs #101).

Seit #308 speist dieser Katalog zusätzlich PLAN-13: `icon_fuer_art()` liefert
den Termin-Icon-Key für eine Art, `termin_icon_keywords_aus_katalog()` erzeugt
die zugehörigen (keyword, icon)-Paare für `render.py`. Damit sind
Aktivitäts-Erkennung (PLAN-12) und Termin-Icon-Zuordnung (PLAN-13) konsistent —
kein Keyword kann mehr in einer Heuristik fehlen, wenn es in der anderen steht.

Per E-PLAN-8 ist V1 familienspezifisch hartcodiert: die Liste hier ist die
einzige Stelle, an der eine Familie ihren Aktivitäts-Katalog anpasst.
"""

# (art, label, keywords) — `art` ist der stabile Schlüssel, `label` der
# Anzeigetext für den Event-Titel (Schreib-Seite, PLAN-11), `keywords` sind
# die Substring-Treffer im Titel zur Erkennung (Lese-Seite, PLAN-12). Das
# erste keyword je Eintrag ist die kanonische Form; weitere Einträge sind
# Aliase (z. B. `geburts` als Kurzform von `geburtstag`).
#
# Reihenfolge zählt: bei der Lese-Heuristik gewinnt der erste Treffer in
# der flachen keyword-Liste. Die hiesige Reihenfolge bewahrt das alte
# Verhalten aus `render.AKTIVITAETS_KEYWORDS` 1:1 (Refs #101).
AKTIVITAETEN = [
    ("klettern",    "Klettern",    ["klettern"]),
    ("kreativ",     "Kreativ",     ["kreativ"]),
    ("schwimmen",   "Schwimmen",   ["schwimm"]),
    ("spielplatz",  "Spielplatz",  ["spielplatz"]),
    ("musik",       "Musik",       ["musik", "klavier", "geige", "gitarre"]),
    ("ausflug",     "Ausflug",     ["ausflug"]),
    ("geburtstag",  "Geburtstag",  ["geburtstag", "geburts"]),
    ("verabredung", "Verabredung", ["verabredung"]),
    ("waldgang",    "Waldgang",    ["wald"]),
]

# PLAN-13: Aktivitäts-Art → Termin-Icon-Key.
# Wird von `render.py` über `icon_fuer_art()` und
# `termin_icon_keywords_aus_katalog()` abgerufen, damit Termin-Icons
# konsistent mit der Aktivitäts-Erkennung bleiben (#308).
_ART_ZU_ICON = {
    "klettern":    "climb",
    "kreativ":     "brush",
    "schwimmen":   "wave",
    "spielplatz":  "play",
    "musik":       "music",
    "ausflug":     "pin",
    "geburtstag":  "cake",
    "verabredung": "friends",
    "waldgang":    "trees",
}


def keyword_paare():
    """Flache Liste `(keyword, art)` in Reihenfolge der Heuristik (PLAN-12).

    Lese-Seite: der erste Treffer im Titel gewinnt — die Reihenfolge hier
    spiegelt die alte `AKTIVITAETS_KEYWORDS`-Liste.
    """
    return [(kw, art) for art, _label, keywords in AKTIVITAETEN for kw in keywords]


def art_aus_titel(titel):
    """Aktivitäts-Art aus einem Titel-Schlüsselwort (PLAN-12). None, wenn keins passt."""
    s = (titel or "").lower()
    for needle, art in keyword_paare():
        if needle in s:
            return art
    return None


def label_fuer_art(art):
    """Anzeige-Label einer Aktivitäts-Art für den Event-Titel (PLAN-11)."""
    for a, label, _kw in AKTIVITAETEN:
        if a == art:
            return label
    # Unbekannte Art: capitalize als Fallback (altes Verhalten).
    return art.capitalize() if art else art


def icon_fuer_art(art):
    """Termin-Icon-Key für eine Aktivitäts-Art (PLAN-13).

    Liefert den Icon-Key aus `_ART_ZU_ICON`. Unbekannte Art → None.
    Wird von `render.termin_icon()` für den gemeinsamen Icon-Pfad benutzt (#308).
    """
    return _ART_ZU_ICON.get(art)


def termin_icon_keywords_aus_katalog():
    """Flache Liste `(keyword, icon_key)` aus dem Aktivitäts-Katalog (PLAN-13).

    Liefert für jedes Keyword jeder Aktivitäts-Art den zugehörigen Icon-Key.
    Keywords ohne Icon-Eintrag in `_ART_ZU_ICON` werden übersprungen.
    Wird von `render.py` als Teil von TERMIN_ICON_KEYWORDS verwendet (#308).
    """
    pairs = []
    for art, _label, keywords in AKTIVITAETEN:
        icon = _ART_ZU_ICON.get(art)
        if icon is None:
            continue
        for kw in keywords:
            pairs.append((kw, icon))
    return pairs
