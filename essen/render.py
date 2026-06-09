"""Essens-Buddy — Render-Logik der View `wunsch` (ESSEN-2/3/8/9/11).

Baut aus dem Katalog und der Wunsch-Liste das View-Modell für
`templates/wunsch.html` (Tabbed Single-Canvas, Gate-B-Wahl 2026-06-09,
E-ESSEN-7).

Drei Verantwortungen:
  1. ARASAAC-Piktogramme über die geteilte Icon-Plattform referenzieren
     (ICONS-5, ESSEN-11) — nicht buddy-eigener ARASAAC-Bezug.
  2. Vier Kategorien-Tabs in fester Reihenfolge (ESSEN-9).
  3. Wunsch-Liste nach Kategorie in fester Reihenfolge gruppieren (ESSEN-8,
     gleiche Reihenfolge wie WZE-5: gericht → obst_gemuese → brotbelag → sonstiges).
"""

import logging

logger = logging.getLogger(__name__)

# ICONS-5: geteilte Icon-Plattform-URL — kein buddy-eigener ARASAAC-Bezug (ESSEN-11).
ICON_BASIS = "/display/_shared/icons/arasaac/"

# ESSEN-9: feste Tab-Reihenfolge + Kategorie-Metadaten.
# bild_ref: ARASAAC-IDs aus dem Mockup (variante-A-tabbed.html):
#   gericht=6456, obst_gemuese=28339, brotbelag=2494, sonstiges=2445
TABS = [
    {"slug": "gericht",       "label": "Gerichte",       "bild_ref": "6456"},
    {"slug": "obst_gemuese",  "label": "Obst & Gemüse",  "bild_ref": "28339"},
    {"slug": "brotbelag",     "label": "Brotbelag",       "bild_ref": "2494"},
    {"slug": "sonstiges",     "label": "Sonstiges",       "bild_ref": "2445"},
]

# ESSEN-9: Default-aktiver Tab ist obst_gemuese.
DEFAULT_TAB = "obst_gemuese"

# ESSEN-8: Reihenfolge für die Wunsch-Listen-Gruppen (wie WZE-5).
GRUPPEN_REIHENFOLGE = ("gericht", "obst_gemuese", "brotbelag", "sonstiges")

GRUPPEN_LABEL = {
    "gericht":      "Gerichte",
    "obst_gemuese": "Obst & Gemüse",
    "brotbelag":    "Brotbelag",
    "sonstiges":    "Sonstiges",
}


def icon_url(bild_ref):
    """URL eines ARASAAC-Piktogramms über die geteilte Plattform (ICONS-5, ESSEN-11)."""
    if bild_ref in (None, ""):
        return None
    return ICON_BASIS + str(bild_ref) + ".png"


def baue_tabs(aktiv_slug):
    """Baut das Tab-View-Modell mit vier Tabs (ESSEN-9).

    Jeder Tab trägt: slug, label, icon_url, aktiv (bool).
    """
    return [
        {
            "slug":     t["slug"],
            "label":    t["label"],
            "icon_url": icon_url(t["bild_ref"]),
            "aktiv":    t["slug"] == aktiv_slug,
        }
        for t in TABS
    ]


def baue_item_grid(katalog_kategorien, aktiv_slug):
    """Baut das Item-Grid für die aktive Kategorie (ESSEN-8/9/12/14).

    Für die Gerichte-Kategorie kommt `katalog_kategorien["gericht"]`
    (leere Liste wenn noch keine Gerichte, ESSEN-9).
    Gibt dict { titel, kacheln: [{id, label, icon_url, bild_ref, kategorie}], leer }.
    """
    items_roh = katalog_kategorien.get(aktiv_slug, [])
    tab_meta = next((t for t in TABS if t["slug"] == aktiv_slug), None)
    titel = tab_meta["label"] if tab_meta else aktiv_slug

    items = [
        {
            "id":        item["id"],
            "label":     item.get("label", ""),
            "icon_url":  icon_url(item.get("bild_ref", "")),
            "bild_ref":  item.get("bild_ref", ""),
            "kategorie": aktiv_slug,
        }
        for item in items_roh
    ]
    return {
        "titel":   titel,
        "kacheln": items,
        "leer":    len(items) == 0,
    }


def baue_wunsch_liste(wuensche):
    """Baut den kategorie-gruppierten Wunsch-Listen-Block (ESSEN-8/15, WZE-5).

    Gibt list of { kat_slug, kat_label, eintraege: [{id, label, icon_url,
    bild_ref, kategorie, quelle, erstellt_am}] } — nur nicht-leere Gruppen.
    """
    gruppen = {k: [] for k in GRUPPEN_REIHENFOLGE}
    for w in wuensche:
        kat = w.get("kategorie")
        if kat in gruppen:
            gruppen[kat].append({
                "id":          w.get("id", ""),
                "label":       w.get("label", ""),
                "icon_url":    icon_url(w.get("bild_ref", "")),
                "bild_ref":    w.get("bild_ref", ""),
                "kategorie":   kat,
                "quelle":      w.get("quelle", ""),
                "erstellt_am": w.get("erstellt_am", ""),
            })
    # Reihenfolge: gericht → obst_gemuese → brotbelag → sonstiges; nur nicht-leer.
    return [
        {
            "kat_slug":    k,
            "kat_label":   GRUPPEN_LABEL.get(k, k),
            "eintraege":   gruppen[k],
        }
        for k in GRUPPEN_REIHENFOLGE
        if gruppen[k]
    ]


def baue_view(katalog_kategorien, wuensche, aktiv_tab=DEFAULT_TAB):
    """Baut das vollständige View-Modell der View `wunsch` (ESSEN-2/8).

    katalog_kategorien  dict mit Schlüsseln gericht, obst_gemuese, brotbelag, sonstiges
    wuensche            Liste der Wunsch-Dicts
    aktiv_tab           slug des aktiven Tabs (Default: obst_gemuese, ESSEN-9)

    Liefert ein dict für `templates/wunsch.html`.
    """
    if aktiv_tab not in {t["slug"] for t in TABS}:
        logger.info("Unbekannter Tab-Slug %r — Default %r", aktiv_tab, DEFAULT_TAB)
        aktiv_tab = DEFAULT_TAB

    return {
        "tabs":        baue_tabs(aktiv_tab),
        "aktiv_tab":   aktiv_tab,
        "item_grid":   baue_item_grid(katalog_kategorien, aktiv_tab),
        "wunsch_liste": baue_wunsch_liste(wuensche),
    }
