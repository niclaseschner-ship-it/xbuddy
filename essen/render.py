"""Essens-Buddy — Render-Logik der View `wunsch` (ESSEN-2/3/8/9/11/28).

Baut aus dem Katalog und der Wunsch-Liste das View-Modell für
`templates/wunsch.html` (Tabbed Single-Canvas, Gate-B-Wahl 2026-06-09,
E-ESSEN-7).

Vier Verantwortungen:
  1. ARASAAC-Piktogramme über die geteilte Icon-Plattform referenzieren
     (ICONS-5, ESSEN-11) — nicht buddy-eigener ARASAAC-Bezug.
  2. Vier Kategorien-Tabs in fester Reihenfolge (ESSEN-9).
  3. Wunsch-Liste nach Kategorie in fester Reihenfolge gruppieren (ESSEN-8,
     gleiche Reihenfolge wie WZE-5: gericht → obst_gemuese → brotbelag → sonstiges).
  4. Quelle-Kacheln als gesperrt markieren, wenn ihr Item auf der aktiven
     Wunschliste steht (ESSEN-28): data-wunsch-aktiv="true" + .kachel-gesperrt.
"""

import logging

logger = logging.getLogger(__name__)

# ICONS-5: geteilte Icon-Plattform-URL — kein buddy-eigener ARASAAC-Bezug (ESSEN-11).
ICON_BASIS = "/display/_shared/icons/arasaac/"

# ESSEN-27: Entfernen-Symbol ARASAAC ID 11751 — sichtbar auf jeder liste-eintrag-Kachel.
ENTFERNEN_ICON_REF = "11751"

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


def baue_item_grid(katalog_kategorien, aktiv_slug, gesperrte_item_ids=None):
    """Baut das Item-Grid für die aktive Kategorie (ESSEN-8/9/12/14/28).

    Für die Gerichte-Kategorie kommt `katalog_kategorien["gericht"]`
    (leere Liste wenn noch keine Gerichte, ESSEN-9).
    Gibt dict { titel, kacheln: [{id, label, icon_url, bild_ref, kategorie,
    gesperrt}], leer }.

    ESSEN-28: `gesperrte_item_ids` ist ein set von Item-IDs, die bereits auf
    der aktiven Wunschliste stehen. Kacheln mit Treffer tragen gesperrt=True.
    """
    items_roh = katalog_kategorien.get(aktiv_slug, [])
    tab_meta = next((t for t in TABS if t["slug"] == aktiv_slug), None)
    titel = tab_meta["label"] if tab_meta else aktiv_slug
    gesperrt_set = gesperrte_item_ids or set()

    items = []
    for item in items_roh:
        item_id = item["id"]
        bild_ref = item.get("bild_ref", "")
        # ESSEN-28: Kachel ist gesperrt, wenn item_id direkt oder über bild_ref
        # in der Wunschliste vorkommt.
        gesperrt = (
            item_id in gesperrt_set
            or ("bild:" + str(bild_ref)) in gesperrt_set
        )
        items.append({
            "id":        item_id,
            "label":     item.get("label", ""),
            "icon_url":  icon_url(bild_ref),
            "bild_ref":  bild_ref,
            "kategorie": aktiv_slug,
            "gesperrt":  gesperrt,
        })
    return {
        "titel":   titel,
        "kacheln": items,
        "leer":    len(items) == 0,
    }


def baue_wunsch_liste(wuensche):
    """Baut den kategorie-gruppierten Wunsch-Listen-Block (ESSEN-8/15/27, WZE-5).

    Gibt list of { kat_slug, kat_label, eintraege: [{id, label, icon_url,
    bild_ref, kategorie, quelle, erstellt_am, entfernen_url}] } —
    nur nicht-leere Gruppen.

    ESSEN-27: jeder Eintrag trägt `entfernen_url` (ARASAAC 11751) für das
    Display-Lösch-Symbol. Das Attribut `data-wunsch-id` im Template greift
    auf `eintrag.id`.
    """
    entfernen_url = icon_url(ENTFERNEN_ICON_REF)
    gruppen = {k: [] for k in GRUPPEN_REIHENFOLGE}
    for w in wuensche:
        kat = w.get("kategorie")
        if kat in gruppen:
            gruppen[kat].append({
                "id":            w.get("id", ""),
                "label":         w.get("label", ""),
                "icon_url":      icon_url(w.get("bild_ref", "")),
                "bild_ref":      w.get("bild_ref", ""),
                "kategorie":     kat,
                "quelle":        w.get("quelle", ""),
                "erstellt_am":   w.get("erstellt_am", ""),
                "entfernen_url": entfernen_url,   # ESSEN-27
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


def baue_gesperrte_item_ids(wuensche):
    """Gibt ein set der Katalog-Item-IDs zurück, die auf der aktiven Wunschliste stehen.

    ESSEN-28: Quelle der Wahrheit ist die Wunschliste (ESSEN-15). Matching
    erfolgt primär über `item_id` (wenn im Wunsch gesetzt) und als Fallback
    über `bild_ref` (ARASAAC-ID ist eindeutig im V1-Katalog, ESSEN-11).

    Das set enthält sowohl item_ids als auch bild_refs (mit Präfix "bild:"),
    damit `baue_item_grid` ohne Schema-Änderung am Wunsch-Store auskommt.
    """
    ids = set()
    for w in wuensche:
        if w.get("item_id"):
            ids.add(w["item_id"])
        elif w.get("bild_ref"):
            # Fallback: bild_ref eindeutig im V1-Katalog — markiert als bild:-Referenz.
            ids.add("bild:" + str(w["bild_ref"]))
    return ids


def baue_view(katalog_kategorien, wuensche, aktiv_tab=DEFAULT_TAB):
    """Baut das vollständige View-Modell der View `wunsch` (ESSEN-2/8/28).

    katalog_kategorien  dict mit Schlüsseln gericht, obst_gemuese, brotbelag, sonstiges
    wuensche            Liste der Wunsch-Dicts
    aktiv_tab           slug des aktiven Tabs (Default: obst_gemuese, ESSEN-9)

    Liefert ein dict für `templates/wunsch.html`.

    ESSEN-28: übergibt gesperrte_item_ids an baue_item_grid, damit Kacheln
    mit Items auf der aktiven Wunschliste als .kachel-gesperrt gerendert werden.
    """
    if aktiv_tab not in {t["slug"] for t in TABS}:
        logger.info("Unbekannter Tab-Slug %r — Default %r", aktiv_tab, DEFAULT_TAB)
        aktiv_tab = DEFAULT_TAB

    gesperrte_ids = baue_gesperrte_item_ids(wuensche)

    return {
        "tabs":        baue_tabs(aktiv_tab),
        "aktiv_tab":   aktiv_tab,
        "item_grid":   baue_item_grid(katalog_kategorien, aktiv_tab, gesperrte_ids),
        "wunsch_liste": baue_wunsch_liste(wuensche),
    }
