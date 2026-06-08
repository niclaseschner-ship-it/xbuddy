"""Seiten-Registry — Aggregator-Kern (SREG-1/SREG-3/SREG-4/SREG-10/SREG-11).

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

## Icon-Durchreichung (SREG-10)

`icons[]` und `varianten[].icons[]` aus Display-Manifesten (Sorte a) werden 1:1
durchgereicht — kein Komponieren, kein Ableiten. Sorten b/c/d/e tragen kein
`icons`-Feld (das Feld fehlt, ist nicht `null`).

Der Schalter `icons_erforderlich` (Default `False`) steuert die Durchsetzung:
- `False` (Migration): fehlendes `icons[]` → Warnung, Eintrag bleibt gelistet.
- `True` (nach Backfill): fehlendes `icons[]` → per-View-Skip, Warnung.

## Editor-Eintrag je Panel-Instanz (SREG-11)

Für jede Panel-Instanz (Sorte d) erzeugt `panel_eintraege` zusätzlich einen
abgeleiteten Editor-Eintrag (`typ=eltern`, `pfad=/controller/app-panel/<id>/bearbeiten`,
`key=<panel_id>-bearbeiten`). Das Ergebnis sind 2N Einträge für N Panel-Instanzen.

## Verknüpfungs-Felder (SREG-4)

Drei abgeleitete Felder verknüpfen die Snapshot-Sorten d/e und den
Editor-Eintrag (b/SREG-11), damit die Übersichtsseite (SREG-12) die
Hero-Paar-Boxen Display↔Panel↔Editor zeichnen kann:

- `verknuepft_mit_display` (Sorte d): `display_id` aus `panels.json`
  (PREG-Pflichtfeld E-PANEL-5). Trägt **nur** die Panel-Instanz.
- `verknuepft_mit_panels[]` (Sorte e): Reverse-Lookup über den
  PREG-Snapshot — Liste aller `panel_id`s, die dieses Display steuern.
  Trägt **nur** der Display-Client; mehrere Panels pro Display möglich.
- `verknuepft_mit_panel` (Sorte b, Editor-Eintrag SREG-11): die
  `panel_id` aus dem Editor-Pfad-Segment. Trägt **nur** der Editor-Eintrag.

Alle drei Felder **fehlen** bei Nicht-Trägern (analog `icons` — kein
`null`, kein leerer String; das Feld ist schlicht nicht da).
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


def _eintrag_aus_manifest(app_slug, ist_controller, view, icons_erforderlich=False):
    """Baut EINEN Inventar-Eintrag aus einem Manifest-View (SREG-4/SREG-10).

    `key`/`typ`/`app` sind abgeleitet (deterministisch aus app+slug), der Rest
    kommt 1:1 aus dem Manifest. `varianten` und `icons[]` werden durchgereicht,
    wenn vorhanden (SREG-10 — nur Sorte a, kein Komponieren).

    Bei Sorte a (Display-View): fehlendes `icons[]` erzeugt je nach Schalter
    `icons_erforderlich` eine Warnung (False) oder einen Skip-Signal (True).
    Liefert `None`, wenn der Eintrag übersprungen werden soll (SREG-10).
    """
    slug = view["slug"]
    typ = _typ_for_view(ist_controller, view["zielgruppe"])
    eintrag = {
        "key": "%s-%s" % (app_slug, slug),
        "typ": typ,
        "app": app_slug,
        "pfad": view["pfad"],
        "label": view["label"],
        "synonyme": list(view["synonyme"]),
        "zeigt": view["zeigt"],
        "zielgruppe": view["zielgruppe"],
    }

    # SREG-10: icons[] nur bei Display-Views (Sorte a, zielgruppe=kind).
    # Sorten b/c tragen kein icons-Feld (kein Feld, nicht null).
    if typ == TYP_DISPLAY:
        icons = view.get("icons")
        if icons is not None:
            eintrag["icons"] = list(icons)
        elif icons_erforderlich:
            logger.warning(
                "Sorte-a-View ohne icons[] übersprungen (icons_erforderlich=True,"
                " SREG-10): app=%s slug=%s", app_slug, slug)
            return None
        else:
            logger.warning(
                "Sorte-a-View ohne icons[] (icons_erforderlich=False, SREG-10,"
                " Warnung): app=%s slug=%s — Eintrag bleibt gelistet", app_slug, slug)

    if view.get("varianten"):
        eintrag["varianten"] = list(view["varianten"])
    return eintrag


def manifest_eintraege(root, icons_erforderlich=False):
    """Sammelt die Inventar-Einträge der Manifest-Sorten a/b/c (SREG-2/SREG-4/SREG-10).

    Liest jedes per `discover_manifests` gefundene `views.json`. Ein kaputtes
    Manifest (`ManifestError`) wird mit Warnung übersprungen (SREG-3/DCOMP-3) —
    das übrige Inventar bleibt vollständig. Liefert die Liste der Einträge in
    Discovery-Reihenfolge.

    `icons_erforderlich` steuert das SREG-10-Verhalten für fehlende `icons[]`
    bei Sorte-a-Views: False = Warnung + gelistet, True = per-View-Skip.
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
            eintrag = _eintrag_aus_manifest(
                app_slug, ist_controller, view,
                icons_erforderlich=icons_erforderlich)
            if eintrag is not None:
                eintraege.append(eintrag)
    return eintraege


# ============================================================
#  Snapshot-Sorten d/e (SREG-1/SREG-4)
# ============================================================

def panel_eintraege(panels):
    """Leitet die Panel-Instanz-Einträge (Sorte d) + Editor-Einträge aus einem PREG-Snapshot ab.

    `panels` ist die Liste aus `GET /api/v1/panels/` (je Eintrag mit `panel_id`).
    `pfad` kommt aus der Instanz-ID (`/controller/app-panel/<panel_id>`), `label`
    wird aus ihr abgeleitet (SREG-4: PREG kennt kein Anzeige-Label).
    `synonyme`/`varianten`/`zeigt` entfallen für (d).

    SREG-4-Verknüpfung: Trägt das PREG-Panel `display_id` (Pflichtfeld
    E-PANEL-5), erhält der Panel-Eintrag `verknuepft_mit_display: <display_id>`.
    Das Feld fehlt, wenn `display_id` im Snapshot leer/fehlt (defensiv —
    PREG-Pflichtfeld, sollte immer da sein).

    SREG-11: Für jede Panel-Instanz entsteht zusätzlich ein abgeleiteter
    Editor-Eintrag (`typ=eltern`, `pfad=/controller/app-panel/<panel_id>/bearbeiten`,
    `key=<panel_id>-bearbeiten`). Das Ergebnis sind 2N Einträge für N Panels.
    Der Editor-Eintrag trägt `verknuepft_mit_panel: <panel_id>` (SREG-4),
    damit die Übersichtsseite (SREG-12) ihn als Anhang an seine Panel-Karte
    rendern kann.
    """
    eintraege = []
    for p in panels:
        panel_id = p.get("panel_id")
        if not panel_id:
            continue
        # Panel-Seiten-Eintrag (Sorte d)
        panel_e = {
            "key": "panel-%s" % panel_id,
            "typ": TYP_PANEL,
            "instanz": panel_id,
            "pfad": "/controller/app-panel/%s" % panel_id,
            "label": "Panel %s" % panel_id,
            "zielgruppe": "eltern",
        }
        # SREG-4: verknuepft_mit_display — nur wenn PREG das Feld trägt
        # (E-PANEL-5 Pflichtfeld; defensiv, falls Snapshot/Migration). Das
        # Feld FEHLT bei leerem display_id — kein null/leerer String.
        display_id = p.get("display_id")
        if display_id:
            panel_e["verknuepft_mit_display"] = display_id
        eintraege.append(panel_e)
        # Editor-Eintrag (SREG-11): typ=eltern, distinkt via -bearbeiten-Key
        eintraege.append({
            "key": "%s-bearbeiten" % panel_id,
            "typ": TYP_ELTERN,
            "instanz": panel_id,
            "pfad": "/controller/app-panel/%s/bearbeiten" % panel_id,
            "label": "Panel %s bearbeiten" % panel_id,
            "zielgruppe": "eltern",
            # SREG-4: verknuepft_mit_panel — abgeleitet aus dem Pfad-Segment,
            # verbindet den Editor mit seiner Panel-Instanz (Display ↔ Panel
            # ↔ Editor-Kette in SREG-12).
            "verknuepft_mit_panel": panel_id,
        })
    return eintraege


def display_client_eintraege(geraete, panels=None):
    """Leitet die Display-Client-Einträge (Sorte e) aus einem GER-Snapshot ab.

    `geraete` ist die Liste aus `GET /api/v1/geraete/`. (e)-Filter (SREG-1):
    nur Geräte mit `verwendung ∈ {display, beides}` UND `status = aktiv` —
    ein reines Controller-Gerät ist keine Display-Seite, ein stillgelegtes
    Tablet kein nutzbarer Link. `pfad`/`label` aus der Instanz-ID (`display_id`).

    SREG-4-Verknüpfung: Ist `panels` gegeben, wird je Display ein Reverse-
    Lookup über die PREG-Panel-Liste gemacht — alle `panel_id`s, deren
    `display_id` auf dieses Display zeigt, landen als `verknuepft_mit_panels[]`
    am Eintrag. Mehrere Panels pro Display sind möglich (PREG-Beispiel
    Mama+Papa-iPhone auf Wohnzimmer-Display). Das Feld FEHLT, wenn `panels=None`
    (Snapshot-Ausfall, soll die Verknüpfung nicht mit `[]` täuschen);
    `panels=[]` liefert dagegen einen leeren Reverse-Lookup → das Feld fehlt
    bei ungepaarten Displays, ist `[panel_id, …]` bei gepaarten.
    """
    if panels is not None:
        # Reverse-Lookup einmalig vorberechnen (display_id → [panel_id, …]).
        # PREG-Pflichtfeld E-PANEL-5: jedes Panel trägt genau eine display_id.
        # Reihenfolge in der Liste folgt der Snapshot-Reihenfolge — deterministisch.
        reverse = {}
        for p in panels:
            pid = p.get("panel_id")
            did = p.get("display_id")
            if pid and did:
                reverse.setdefault(did, []).append(pid)
    else:
        reverse = None
    eintraege = []
    for g in geraete:
        display_id = g.get("id")
        if not display_id:
            continue
        if g.get("verwendung") not in _DISPLAY_VERWENDUNGEN:
            continue
        if g.get("status") != "aktiv":
            continue
        e = {
            "key": "display-%s" % display_id,
            "typ": TYP_DISPLAY_CLIENT,
            "instanz": display_id,
            "pfad": "/display/%s" % display_id,
            "label": "Display %s" % display_id,
            "zielgruppe": "kind",
        }
        # SREG-4: verknuepft_mit_panels — nur setzen, wenn PREG-Snapshot vorlag.
        # Bei panels=None (Snapshot-Ausfall) keine Verknüpfung suggerieren.
        if reverse is not None:
            verbundene = reverse.get(display_id, [])
            if verbundene:
                e["verknuepft_mit_panels"] = verbundene
        eintraege.append(e)
    return eintraege


# ============================================================
#  Inventar-Aufbau (SREG-3 LKG / nie leer)
# ============================================================

def _snapshot_sorte(neu, ableiter, vorheriges, typ):
    """Wendet das Last-Known-Good-Fehlermodell auf eine Snapshot-Sorte an (SREG-3).

    `neu` ist der frisch geholte Snapshot (`list`) oder `None` (Holer scheiterte).
    - frische Daten → abgeleitete Einträge (ableiter ist eine 0-arg-Closure
      über `neu` + ggf. weitere Snapshots), kein Stale-/Pending-Marker.
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


def baue_inventar(root, panels=None, geraete=None, vorheriges=None,
                  icons_erforderlich=False):
    """Baut das vollständige Inventar (SREG-3/SREG-4/SREG-10/SREG-11) — der Kern-Aufruf.

    Args:
        root: Repo-Wurzel, unter der die `views.json`-Manifeste liegen (SREG-2).
        panels: PREG-Snapshot (`list`) oder `None`, wenn der Holer scheiterte.
        geraete: GER-Snapshot (`list`) oder `None`, wenn der Holer scheiterte.
        vorheriges: das vorige `inventar`-Dict (für Last-Known-Good), oder None.
        icons_erforderlich: SREG-10-Schalter (Default False = Migrationsphase;
            True = nach Backfill, per-View-Skip bei fehlendem icons[]).

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

    eintraege = list(manifest_eintraege(root, icons_erforderlich=icons_erforderlich))

    pending = []
    panel_e, panel_pending = _snapshot_sorte(
        panels, panel_eintraege, vorherige_eintraege, TYP_PANEL)
    if panel_pending:
        pending.append(TYP_PANEL)
    eintraege.extend(panel_e)

    # SREG-4: Display-Client braucht den PREG-Snapshot für den
    # `verknuepft_mit_panels[]`-Reverse-Lookup. Wenn PREG ausfällt
    # (panels=None), kommt None durch — die Verknüpfung fehlt dann (keine
    # falsche `[]`-Aussage). Wenn nur GER ausfällt, läuft LKG für Sorte e und
    # `panels` ist trotzdem da — die Verknüpfung bleibt korrekt am LKG-Eintrag,
    # weil _snapshot_sorte den vorigen Eintrag inklusive `verknuepft_mit_panels`
    # 1:1 übernimmt (dict-Copy).
    display_e, display_pending = _snapshot_sorte(
        geraete, lambda g: display_client_eintraege(g, panels=panels),
        vorherige_eintraege, TYP_DISPLAY_CLIENT)
    if display_pending:
        pending.append(TYP_DISPLAY_CLIENT)
    eintraege.extend(display_e)

    return {"eintraege": eintraege, "snapshot_pending": pending}
