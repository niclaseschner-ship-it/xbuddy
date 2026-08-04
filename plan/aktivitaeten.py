"""Plan-Buddy — Aktivitäts-Katalog (PLAN-12, PLAN-13, E-PLAN-8, PLAN-34).

EINE Quelle für die familienspezifische Liste der Kind-Aktivitäten. Sowohl
die Lese-Seite (Titel → Art, `render.py`) als auch die Schreib-Seite (Art →
Titel-Label, `main.py`) beziehen sich auf diesen Katalog.

Seit #308 speist dieser Katalog zusätzlich PLAN-13: `icon_fuer_art()` liefert
die ARASAAC-Piktogramm-ID für eine Art, `termin_icon_keywords_aus_katalog()`
erzeugt die zugehörigen (keyword, piktogramm_id)-Paare für `render.py`. Damit
sind Aktivitäts-Erkennung (PLAN-12) und Termin-Icon-Zuordnung (PLAN-13)
konsistent — eine Quelle, eine Icon-Form (E-PLAN-5 V1.2, ICONS-4).

Seit #445/#578 (PLAN-28/PLAN-34) ist der Katalog dateigetrieben: die Quelle
ist die `aktivitaeten`-Section in `plan.json` (via `Config.aktivitaeten`).
Fehlt die Section, greift AKTIVITAETEN_V1 als CONFIG-4-Fallback (E-PLAN-8).

Alle Funktionen nehmen einen optionalen `config`-Parameter (plan.config.Config).
Ist er None oder hat er kein `aktivitaeten`-Feld (== None), greift
AKTIVITAETEN_V1. So bleibt render.py — das termin_icon_keywords_aus_katalog()
ohne Config beim Modul-Import aufruft — unverändert lauffähig.

ARASAAC-Icon-Pfad (E-PLAN-5 V1.2): /display/_shared/icons/arasaac/<id>.png.
Fallback-Piktogramm: 3071 (Kalender-Icon), wenn kein Keyword trifft (PLAN-13).
"""

# PLAN-13: Generisches Termin-Fallback-Piktogramm (ARASAAC id, E-PLAN-5 V1.2).
# Trifft kein Keyword im Termin-Titel, rendert die Pille dieses Kalender-Icon.
FALLBACK_PIKTOGRAMM = "3071"

# PLAN-12/PLAN-28: V1-Default-Katalog — CONFIG-4-Fallback, wenn plan.json keine
# `aktivitaeten`-Section hat (E-PLAN-8 V1.2). Format je Eintrag:
# { "art": <schlüssel>, "label": <text>, "keywords": [<str>, …],
#   "piktogramm": <arasaac-id-string> }
#
# ARASAAC-IDs: Werft #578/E-PLAN-5 V1.2 — ICONS-4-Konsum über den geteilten
# Icon-Pfad /display/_shared/icons/arasaac/<id>.png (analog ROUTINE-10).
#
# Reihenfolge zählt: bei der Lese-Heuristik gewinnt der erste Treffer in
# der flachen keyword-Liste. Die hiesige Reihenfolge bewahrt das alte
# Verhalten aus `render.AKTIVITAETS_KEYWORDS` 1:1 (Refs #101).
#
# Termin-spezifische Einträge (PLAN-13 V1.2): zahn, ferien, treff, garten,
# schule wandern hierher aus `render._TERMIN_ICON_EXTRAS` (#471). Ferien und
# Urlaub teilen denselben art-Schlüssel und dieselbe ARASAAC-ID. Die
# Präfix-Varianten "klett" und "kreat" sind als zusätzliche Keywords in den
# bestehenden klettern/kreativ-Einträgen untergebracht (PLAN-13 #308-fix).
AKTIVITAETEN_V1 = [
    # ── Familien-Aktivitäten (9 Einträge) ────────────────────────
    {"art": "klettern",    "label": "Klettern",    "keywords": ["klettern", "klett"],
     "piktogramm": "8226"},
    {"art": "kreativ",     "label": "Kreativ",     "keywords": ["kreativ", "kreat"],
     "piktogramm": "11690"},
    {"art": "schwimmen",   "label": "Schwimmen",   "keywords": ["schwimm"],
     "piktogramm": "6568"},
    {"art": "spielplatz",  "label": "Spielplatz",  "keywords": ["spielplatz"],
     "piktogramm": "2859"},
    {"art": "musik",       "label": "Musik",
     "keywords": ["musik", "klavier", "geige", "gitarre"],
     "piktogramm": "2746"},
    {"art": "ausflug",     "label": "Ausflug",     "keywords": ["ausflug"],
     "piktogramm": "4670"},
    {"art": "geburtstag",  "label": "Geburtstag",
     "keywords": ["geburtstag", "geburts"],
     "piktogramm": "3087"},
    {"art": "verabredung", "label": "Verabredung", "keywords": ["verabredung"],
     "piktogramm": "2255"},
    {"art": "waldgang",    "label": "Waldgang",    "keywords": ["wald"],
     "piktogramm": "2666"},
    # ── Termin-spezifische Einträge (PLAN-13 V1.2, #471) ─────────
    # Wandern aus render._TERMIN_ICON_EXTRAS hierher — eine Quelle (CLAUDE.md §6).
    # Keine Kind-Aktivität (tauchen in Termin-Leiste auf, nicht im Aktivitäts-Slot).
    {"art": "zahn",    "label": "Zahnarzt",  "keywords": ["zahn"],
     "piktogramm": "11229"},
    {"art": "ferien",  "label": "Ferien",    "keywords": ["ferien", "urlaub"],
     "piktogramm": "3166"},
    {"art": "treff",   "label": "Treffen",   "keywords": ["treff"],
     "piktogramm": "6487"},
    {"art": "garten",  "label": "Garten",    "keywords": ["garten"],
     "piktogramm": "2434"},
    {"art": "schule",  "label": "Schule",    "keywords": ["schule"],
     "piktogramm": "3082"},
]


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
    """ARASAAC-Piktogramm-ID für eine Aktivitäts-Art (PLAN-12, E-PLAN-5 V1.2).

    Liest das `piktogramm`-Feld direkt aus dem aktiven Katalog-Eintrag —
    eine Icon-Quelle (CLAUDE.md §6). Gibt die ID als String zurück (z. B.
    '8226') oder None, wenn die Art unbekannt ist oder kein piktogramm trägt.

    Verworfen: _ICON_V1-Map (bisherige String-Keys wie 'climb', 'brush') —
    die Icon-Quelle wechselt in V1.2 vollständig auf ARASAAC (E-PLAN-5 V1.2).
    """
    for entry in _katalog(config):
        if entry["art"] == art:
            piktogramm = entry.get("piktogramm") or ""
            return piktogramm if piktogramm else None
    return None


def termin_icon_keywords_aus_katalog(config=None):
    """Flache Liste `(keyword, piktogramm_id)` aus dem Aktivitäts-Katalog (PLAN-13).

    Liefert für jedes Keyword jeder Aktivitäts-Art die zugehörige ARASAAC-ID.
    Einträge ohne piktogramm werden übersprungen. Wird von `render.py` als
    Teil von TERMIN_ICON_KEYWORDS verwendet (#308, #471).

    `render.py` ruft diese Funktion beim Modul-Import ohne Config auf —
    dann greift CONFIG-4-Fallback AKTIVITAETEN_V1.
    """
    pairs = []
    for entry in _katalog(config):
        piktogramm = entry.get("piktogramm") or ""
        if not piktogramm:
            continue
        for kw in entry["keywords"]:
            pairs.append((kw, piktogramm))
    return pairs
