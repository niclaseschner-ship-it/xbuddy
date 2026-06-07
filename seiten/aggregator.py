"""Seiten-Registry — Aggregator-Kern (SREG-1/SREG-3/SREG-4).

Siehe specs/platform/seiten-registry.md (Refs #347, ratifiziert RAT-13). Dieses
Modul baut das **Inventar aller aufrufbaren View-Einstiegspunkte** aus den schon
existierenden Quellen zusammen — es ist die EINE Stelle, die aus den committeten
`views.json`-Manifesten (Sorten a/b/c) und den PREG/GER-Snapshots (Sorten d/e)
das `inventar.json`-Schema (SREG-4) ableitet.

Dieses Modul ist **rein und testbar ohne HTTP**: die Manifest-Sorten kommen aus
der Platte (`tools.views_manifest.load`), die Snapshot-Sorten reicht der Aufrufer
als schon-geholte Python-Strukturen herein (`panels`, `geraete` — Listen von
Dicts). Wer sie holt (urllib in `seiten/main.py`) und wie der TTL-Rebuild
getaktet ist, ist NICHT hier — hier wohnt nur die Ableitung. So testen die
Aggregator-Tests gegen tmp-Dir-Manifeste + injizierte Snapshots, ohne Netz und
ohne Abhängigkeit von den echten Buddy-Manifesten anderer Branches.

## Discovery (SREG-2)

Manifeste liegen je Komponente neben dem Code. `discover_manifests(root)`
globbt `<root>/*/views.json` (Buddys: plan/wetter/routine/photo) **und**
`<root>/controller/*/views.json` (Controller-Apps). Der Verzeichnisname ist der
App-Slug (`<root>/plan/views.json` → app `plan`,
`<root>/controller/figuren-erkennung/views.json` → app `figuren-erkennung`).

## Fehlermodell (SREG-3 / DCOMP-3)

Ein kaputtes/schema-inkompatibles Einzel-Manifest (`tools.views_manifest`
wirft `ManifestError`) wird mit Warnung **übersprungen** — das übrige Inventar
bleibt vollständig, nie crasht das ganze Inventar wegen eines Manifests.

## Snapshot-Fehlermodell (SREG-3, Last-Known-Good)

Der Aufrufer reicht je Snapshot-Sorte entweder die geholten Daten (`list`) oder
`None` (Holer scheiterte) herein. Aus dem vorigen Inventar (`vorheriges`)
übernimmt der Aggregator bei `None` den letzten erfolgreichen Teil-Snapshot
und markiert ihn `stale: true`; war die Sorte **nie** da, fehlt sie mit
`snapshot_pending: true`. Die Antwort ist dadurch **nie leer** und nie
falsch-gekürzt.
"""

import glob
import logging
import os

from tools import views_manifest

logger = logging.getLogger(__name__)

# SREG-4: die `typ`-Wertemenge eines Eintrags. Abgeleitet, nie frei vergeben.
TYP_DISPLAY = "display"
TYP_ELTERN = "eltern"
TYP_CONTROLLER = "controller"
TYP_PANEL = "panel"
TYP_DISPLAY_CLIENT = "display-client"

# SREG-1 (e)-Filter: nur diese `verwendung`-Werte zählen als Display-Seite.
_DISPLAY_VERWENDUNGEN = ("display", "beides")


# ============================================================
#  Manifest-Discovery (SREG-2)
# ============================================================

def discover_manifests(root):
    """Findet alle committeten `views.json`-Manifeste unter `root` (SREG-2).

    Globbt `<root>/*/views.json` (Buddys) und `<root>/controller/*/views.json`
    (Controller-Apps). Liefert eine Liste `(app_slug, ist_controller, pfad)`,
    sortiert nach Pfad — deterministische Inventar-Reihenfolge.

    Der App-Slug ist der Verzeichnisname des Manifests; `controller/` selbst ist
    kein App-Slug (es ist der Container der Controller-Apps), darum wird der
    `<root>/controller/views.json`-Treffer (falls je vorhanden) NICHT als
    Buddy-Manifest gewertet — der Buddy-Glob fängt nur die direkten
    Kind-Verzeichnisse.
    """
    treffer = []
    for pfad in sorted(glob.glob(os.path.join(root, "*", "views.json"))):
        app_slug = os.path.basename(os.path.dirname(pfad))
        if app_slug == "controller":
            # `<root>/controller/views.json` ist kein Buddy-Manifest — der
            # Controller-Glob unten erfasst die Apps darunter.
            continue
        treffer.append((app_slug, False, pfad))
    for pfad in sorted(glob.glob(os.path.join(root, "controller", "*", "views.json"))):
        app_slug = os.path.basename(os.path.dirname(pfad))
        treffer.append((app_slug, True, pfad))
    return sorted(treffer, key=lambda t: t[2])


# ============================================================
#  Eintrags-Ableitung (SREG-4)
# ============================================================

def _typ_for_view(ist_controller, zielgruppe):
    """Leitet `typ` aus Sorte + `zielgruppe` ab (SREG-4).

    Controller-Apps → `controller`. Sonst entscheidet `zielgruppe`:
    `eltern` → `eltern` (Sorte b, Settings/Editor-Views), `kind` → `display`
    (Sorte a, Kind-Display-Views).
    """
    if ist_controller:
        return TYP_CONTROLLER
    if zielgruppe == "eltern":
        return TYP_ELTERN
    return TYP_DISPLAY


def _eintrag_aus_manifest(app_slug, ist_controller, view):
    """Baut EINEN Inventar-Eintrag aus einem Manifest-View (SREG-4).

    `key`/`typ`/`app` sind abgeleitet (deterministisch aus app+slug), der Rest
    kommt 1:1 aus dem Manifest. `varianten` wird durchgereicht, wenn vorhanden.
    """
    slug = view["slug"]
    eintrag = {
        "key": "%s-%s" % (app_slug, slug),
        "typ": _typ_for_view(ist_controller, view["zielgruppe"]),
        "app": app_slug,
        "pfad": view["pfad"],
        "label": view["label"],
        "synonyme": list(view["synonyme"]),
        "zeigt": view["zeigt"],
        "zielgruppe": view["zielgruppe"],
    }
    if view.get("varianten"):
        eintrag["varianten"] = view["varianten"]
    return eintrag


def manifest_eintraege(root):
    """Sammelt die Inventar-Einträge der Manifest-Sorten a/b/c (SREG-2/SREG-4).

    Liest jedes per `discover_manifests` gefundene `views.json`. Ein kaputtes
    Manifest (`ManifestError`) wird mit Warnung übersprungen (SREG-3/DCOMP-3) —
    das übrige Inventar bleibt vollständig. Liefert die Liste der Einträge in
    Discovery-Reihenfolge.
    """
    eintraege = []
    for app_slug, ist_controller, pfad in discover_manifests(root):
        try:
            views = views_manifest.load(pfad)
        except views_manifest.ManifestError as e:
            logger.warning(
                "Manifest übersprungen (%s, app=%s): %s — übriges Inventar bleibt"
                " vollständig (SREG-3/DCOMP-3)", pfad, app_slug, e)
            continue
        for view in views:
            eintraege.append(_eintrag_aus_manifest(app_slug, ist_controller, view))
    return eintraege


# ============================================================
#  Snapshot-Sorten d/e (SREG-1/SREG-4)
# ============================================================

def panel_eintraege(panels):
    """Leitet die Panel-Instanz-Einträge (Sorte d) aus einem PREG-Snapshot ab.

    `panels` ist die Liste aus `GET /api/v1/panels/` (je Eintrag mit `panel_id`).
    `pfad` kommt aus der Instanz-ID (`/controller/app-panel/<panel_id>`), `label`
    wird aus ihr abgeleitet (SREG-4: PREG kennt kein Anzeige-Label).
    `synonyme`/`varianten`/`zeigt` entfallen für (d).
    """
    eintraege = []
    for p in panels:
        panel_id = p.get("panel_id")
        if not panel_id:
            continue
        eintraege.append({
            "key": "panel-%s" % panel_id,
            "typ": TYP_PANEL,
            "instanz": panel_id,
            "pfad": "/controller/app-panel/%s" % panel_id,
            "label": "Panel %s" % panel_id,
            "zielgruppe": "eltern",
        })
    return eintraege


def display_client_eintraege(geraete):
    """Leitet die Display-Client-Einträge (Sorte e) aus einem GER-Snapshot ab.

    `geraete` ist die Liste aus `GET /api/v1/geraete/`. (e)-Filter (SREG-1):
    nur Geräte mit `verwendung ∈ {display, beides}` UND `status = aktiv` —
    ein reines Controller-Gerät ist keine Display-Seite, ein stillgelegtes
    Tablet kein nutzbarer Link. `pfad`/`label` aus der Instanz-ID (`display_id`).
    """
    eintraege = []
    for g in geraete:
        display_id = g.get("id")
        if not display_id:
            continue
        if g.get("verwendung") not in _DISPLAY_VERWENDUNGEN:
            continue
        if g.get("status") != "aktiv":
            continue
        eintraege.append({
            "key": "display-%s" % display_id,
            "typ": TYP_DISPLAY_CLIENT,
            "instanz": display_id,
            "pfad": "/display/%s" % display_id,
            "label": "Display %s" % display_id,
            "zielgruppe": "kind",
        })
    return eintraege


# ============================================================
#  Inventar-Aufbau (SREG-3 LKG / nie leer)
# ============================================================

def _snapshot_sorte(neu, ableiter, vorheriges, typ):
    """Wendet das Last-Known-Good-Fehlermodell auf eine Snapshot-Sorte an (SREG-3).

    `neu` ist der frisch geholte Snapshot (`list`) oder `None` (Holer scheiterte).
    - frische Daten → abgeleitete Einträge, kein Stale-/Pending-Marker.
    - `None` + im `vorheriges`-Inventar lag schon mal ein erfolgreicher
      Teil-Snapshot dieser Sorte → diese Einträge erhalten, `stale: true`.
    - `None` + nie da gewesen → leere Liste + `pending=True`-Signal, sodass der
      Aufrufer `snapshot_pending` setzt.

    Liefert `(eintraege, pending)`.
    """
    if neu is not None:
        return ableiter(neu), False
    behalten = [dict(e) for e in (vorheriges or []) if e.get("typ") == typ]
    if behalten:
        for e in behalten:
            e["stale"] = True
        return behalten, False
    # Nie ein erfolgreicher Snapshot dieser Sorte — sie fehlt explizit.
    return [], True


def baue_inventar(root, panels=None, geraete=None, vorheriges=None):
    """Baut das vollständige Inventar (SREG-3/SREG-4) — der Kern-Aufruf.

    Args:
        root: Repo-Wurzel, unter der die `views.json`-Manifeste liegen (SREG-2).
        panels: PREG-Snapshot (`list`) oder `None`, wenn der Holer scheiterte.
        geraete: GER-Snapshot (`list`) oder `None`, wenn der Holer scheiterte.
        vorheriges: das vorige `inventar`-Dict (für Last-Known-Good), oder None.

    Returns:
        Ein `inventar`-Dict mit:
          - `eintraege`: Manifest-Sorten (immer vollständig, auch Kaltstart)
            + Snapshot-Sorten (LKG/stale/leer je Holer-Ergebnis).
          - `snapshot_pending`: Liste der Snapshot-`typ`s, die NIE da waren
            (Kaltstart ohne je erfolgreichen Snapshot) — die Antwort ist
            trotzdem gültig und nie leer (die Manifest-Sorten tragen sie).

    Die Manifest-Sorten kommen IMMER frisch von der Platte — sie sind auch beim
    Kaltstart verfügbar (SREG-3). Nur die Snapshot-Sorten tragen das
    LKG-Fehlermodell.
    """
    vorherige_eintraege = (vorheriges or {}).get("eintraege", [])

    eintraege = list(manifest_eintraege(root))

    pending = []
    panel_e, panel_pending = _snapshot_sorte(
        panels, panel_eintraege, vorherige_eintraege, TYP_PANEL)
    if panel_pending:
        pending.append(TYP_PANEL)
    eintraege.extend(panel_e)

    display_e, display_pending = _snapshot_sorte(
        geraete, display_client_eintraege, vorherige_eintraege, TYP_DISPLAY_CLIENT)
    if display_pending:
        pending.append(TYP_DISPLAY_CLIENT)
    eintraege.extend(display_e)

    return {"eintraege": eintraege, "snapshot_pending": pending}
