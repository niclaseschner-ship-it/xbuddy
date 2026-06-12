"""Essens-Buddy — Render-Logik der View `wunsch` (ESSEN-2/3/8/9/11/22/28).

Baut aus dem Katalog und der Wunsch-Liste das View-Modell für
`templates/wunsch.html` (Tabbed Single-Canvas, Gate-B-Wahl 2026-06-09,
E-ESSEN-7).

Vier Petrantwortungen:
  1. ARASAAC-Piktogramme über die geteilte Icon-Plattform referenzieren
     (ICONS-5, ESSEN-11) — nicht buddy-eigener ARASAAC-Bezug.
  2. Vier Kategorien-Tabs in fester Reihenfolge (ESSEN-9).
  3. Wunsch-Liste nach Kategorie in fester Reihenfolge gruppieren (ESSEN-8,
     gleiche Reihenfolge wie WZE-5: gericht → obst_gemuese → brotbelag → sonstiges).
  4. Quelle-Kacheln als gesperrt markieren, wenn ihr Item auf der aktiven
     Wunschliste steht (ESSEN-28): data-wunsch-aktiv="true" + .kachel-gesperrt.
  5. Familien-Foto-Override (ESSEN-22): Gericht mit foto_ref ODER Item mit
     Eintrag in foto_overrides.json → Foto-URL aus Photo-Buddy statt ARASAAC.
     Kreisförmig via CSS-Klasse kachel-foto.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

# ICONS-5: geteilte Icon-Plattform-URL — kein buddy-eigener ARASAAC-Bezug (ESSEN-11).
ICON_BASIS = "/display/_shared/icons/arasaac/"

# ESSEN-22: Photo-Buddy-Pfad für Familien-Fotos (relative URL, nginx-geroutet).
PHOTO_BUDDY_MEDIEN_PFAD = "/api/v1/photo/medien/"

# ESSEN-22 / SVC-5: Default-Pfad für foto_overrides.json (Per-Instanz, xbuddy-data).
DEFAULT_FOTO_OVERRIDES_PFAD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "xbuddy-data", "essen", "foto_overrides.json",
)

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


def foto_url(medien_id):
    """URL eines Familien-Fotos aus dem Photo-Buddy (ESSEN-22, PHOTO-15).

    Baut eine relative URL `/api/v1/photo/medien/<id>` — konsistent mit der
    ICON_BASIS-Konvention (relative, nginx-geroutet).
    """
    if medien_id in (None, ""):
        return None
    return PHOTO_BUDDY_MEDIEN_PFAD + str(medien_id)


def lade_foto_overrides(pfad=None):
    """Liest foto_overrides.json (ESSEN-22, SVC-5).

    Tolerant gegen FileNotFoundError — gibt leeres Dict zurück (kein Override
    aktiv). Andere Ausnahmen (z. B. JSON-Syntaxfehler) werden geloggt und
    ebenfalls als leeres Dict behandelt (Defense in Depth).

    pfad: Dateipfad zu foto_overrides.json. Default: DEFAULT_FOTO_OVERRIDES_PFAD.
    Schema: { "<item_id>": "<photo_buddy_medien_id>" }
    """
    if pfad is None:
        pfad = DEFAULT_FOTO_OVERRIDES_PFAD
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning("foto_overrides.json konnte nicht gelesen werden: %s", pfad)
        return {}


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


def baue_item_grid(katalog_kategorien, aktiv_slug, gesperrte_item_ids=None,
                   foto_overrides=None):
    """Baut das Item-Grid für die aktive Kategorie (ESSEN-8/9/12/14/28).

    Für die Gerichte-Kategorie kommt `katalog_kategorien["gericht"]`
    (leere Liste wenn noch keine Gerichte, ESSEN-9).
    Gibt dict { titel, kacheln: [{id, label, icon_url, bild_ref, kategorie,
    gesperrt, ist_foto}], leer }.

    ESSEN-28: `gesperrte_item_ids` ist ein set von Item-IDs, die bereits auf
    der aktiven Wunschliste stehen. Kacheln mit Treffer tragen gesperrt=True.
    Matching strikt über item_id — kein bild_ref-Fallback (ESSEN-28).

    ESSEN-22: `foto_overrides` ist ein dict { item_id: medien_id } aus
    foto_overrides.json. Pro Item: zuerst foto_ref am Item prüfen, dann
    foto_overrides-Eintrag, dann ARASAAC-Fallback. ist_foto=True markiert
    Foto-Kacheln (CSS-Klasse kachel-foto).
    """
    items_roh = katalog_kategorien.get(aktiv_slug, [])
    tab_meta = next((t for t in TABS if t["slug"] == aktiv_slug), None)
    titel = tab_meta["label"] if tab_meta else aktiv_slug
    gesperrt_set = gesperrte_item_ids or set()
    overrides = foto_overrides or {}

    items = []
    for item in items_roh:
        item_id = item["id"]
        bild_ref = item.get("bild_ref", "")
        # ESSEN-22 Pfad 1: Gericht trägt foto_ref.
        gericht_foto_ref = item.get("foto_ref", "")
        # ESSEN-28: Matching strikt über item_id (kein bild_ref-Fallback, ESSEN-28).
        gesperrt = item_id in gesperrt_set

        # ESSEN-22: Override-Logik — Reihenfolge: foto_ref > foto_overrides > ARASAAC.
        if gericht_foto_ref:
            url = foto_url(gericht_foto_ref)
            ist_foto = True
        elif item_id in overrides:
            url = foto_url(overrides[item_id])
            ist_foto = True
        else:
            url = icon_url(bild_ref)
            ist_foto = False

        items.append({
            "id":        item_id,
            "label":     item.get("label", ""),
            "icon_url":  url,
            "bild_ref":  bild_ref,
            "kategorie": aktiv_slug,
            "gesperrt":  gesperrt,
            "ist_foto":  ist_foto,
        })
    return {
        "titel":   titel,
        "kacheln": items,
        "leer":    len(items) == 0,
    }


def baue_wunsch_liste(wuensche, foto_overrides=None):
    """Baut den kategorie-gruppierten Wunsch-Listen-Block (ESSEN-8/15/27, WZE-5).

    Gibt list of { kat_slug, kat_label, eintraege: [{id, label, icon_url,
    bild_ref, kategorie, quelle, erstellt_am, entfernen_url, ist_foto}] } —
    nur nicht-leere Gruppen.

    ESSEN-27: jeder Eintrag trägt `entfernen_url` (ARASAAC 11751) für das
    Display-Lösch-Symbol. Das Attribut `data-wunsch-id` im Template greift
    auf `eintrag.id`.

    ESSEN-22: `foto_overrides` wird geprüft (item_id-basiert, ESSEN-28 analog).
    Wunsch-Eintrag trägt foto_ref oder item_id-Override → Foto-URL +
    ist_foto=True; sonst ARASAAC + ist_foto=False.
    """
    entfernen_url = icon_url(ENTFERNEN_ICON_REF)
    overrides = foto_overrides or {}
    gruppen = {k: [] for k in GRUPPEN_REIHENFOLGE}
    for w in wuensche:
        kat = w.get("kategorie")
        if kat in gruppen:
            item_id = w.get("item_id", "")
            bild_ref = w.get("bild_ref", "")
            # ESSEN-22 Pfad 1: Wunsch-Eintrag trägt foto_ref (Gericht).
            w_foto_ref = w.get("foto_ref", "")

            # ESSEN-22: Override-Logik — Reihenfolge: foto_ref > foto_overrides > ARASAAC.
            if w_foto_ref:
                url = foto_url(w_foto_ref)
                ist_foto = True
            elif item_id and item_id in overrides:
                url = foto_url(overrides[item_id])
                ist_foto = True
            else:
                url = icon_url(bild_ref)
                ist_foto = False

            gruppen[kat].append({
                "id":            w.get("id", ""),
                "label":         w.get("label", ""),
                "icon_url":      url,
                "bild_ref":      bild_ref,
                "kategorie":     kat,
                "quelle":        w.get("quelle", ""),
                "erstellt_am":   w.get("erstellt_am", ""),
                "entfernen_url": entfernen_url,   # ESSEN-27
                "ist_foto":      ist_foto,         # ESSEN-22
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

    ESSEN-28: Matching strikt über `item_id` (Pflichtfeld, ESSEN-16).
    Kein bild_ref-Fallback — bild_ref kann über Katalog-Grenzen kollidieren (ESSEN-28).
    `item_id` ist seit ESSEN-16-Schärfung Pflichtfeld in jedem Wunsch-Eintrag.
    """
    return {w["item_id"] for w in wuensche if w.get("item_id")}


def baue_view(katalog_kategorien, wuensche, aktiv_tab=DEFAULT_TAB,
              foto_overrides_pfad=None):
    """Baut das vollständige View-Modell der View `wunsch` (ESSEN-2/8/22/28).

    katalog_kategorien  dict mit Schlüsseln gericht, obst_gemuese, brotbelag, sonstiges
    wuensche            Liste der Wunsch-Dicts
    aktiv_tab           slug des aktiven Tabs (Default: obst_gemuese, ESSEN-9)
    foto_overrides_pfad optionaler Pfad zu foto_overrides.json (ESSEN-22/SVC-5);
                        None → DEFAULT_FOTO_OVERRIDES_PFAD

    Liefert ein dict für `templates/wunsch.html`.

    ESSEN-28: übergibt gesperrte_item_ids an baue_item_grid, damit Kacheln
    mit Items auf der aktiven Wunschliste als .kachel-gesperrt gerendert werden.

    ESSEN-22: lädt foto_overrides einmal pro Render-Cycle; tolerant gegen
    fehlende foto_overrides.json (lade_foto_overrides gibt {} zurück).
    """
    if aktiv_tab not in {t["slug"] for t in TABS}:
        logger.info("Unbekannter Tab-Slug %r — Default %r", aktiv_tab, DEFAULT_TAB)
        aktiv_tab = DEFAULT_TAB

    gesperrte_ids = baue_gesperrte_item_ids(wuensche)
    # ESSEN-22: ein Lade-Aufruf pro Render-Cycle, tolerant gegen Fehler.
    overrides = lade_foto_overrides(foto_overrides_pfad)

    return {
        "tabs":        baue_tabs(aktiv_tab),
        "aktiv_tab":   aktiv_tab,
        "item_grid":   baue_item_grid(
            katalog_kategorien, aktiv_tab, gesperrte_ids, overrides),
        "wunsch_liste": baue_wunsch_liste(wuensche, overrides),
    }
