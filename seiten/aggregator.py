"""Seiten-Registry — Aggregator-Kern (SREG-1/SREG-2/SREG-3/SREG-4/SREG-10).

Siehe specs/platform/seiten-registry.md (Refs #347, ratifiziert RAT-13,
RAT-31 E3 Umbau #1496). Dieses Modul baut das **Inventar aller aufrufbaren
View-Einstiegspunkte** ausschließlich aus den committeten
`views.json`-Manifesten — es ist die EINE Stelle, die aus Buddy-/Platform-
Manifesten (Sorten a/b/c/mini-app/pwa) das `inventar.json`-Schema (SREG-4)
ableitet.

**RAT-31 E3 (Closes #1496):** Die instanz-spezifischen Snapshot-Sorten d
(Panel-Instanz aus PREG-HTTP) und e (Display-Client aus GER-HTTP) sind
entfernt. Das Inventar ist jetzt rein manifest-basiert (SREG-2 — Wahrheit
aus committeten Manifesten, nicht aus laufenden Prozessen). Die ehemals
PREG/GER-abhängigen Felder `verknuepft_mit_display`, `verknuepft_mit_panels`,
`verknuepft_mit_panel` (SREG-4) und der `snapshot_pending`-Mechanismus
(LKG) entfallen ersatzlos — die `panel/`- und `geraete/`-Registries sterben
per RAT-31.

Dieses Modul ist **rein und testbar ohne HTTP**: alle Manifest-Sorten kommen
aus der Platte (`tools.views_manifest.load`). Die Aggregator-Tests laufen
gegen tmp-Dir-Manifeste, ohne Netz und ohne Abhängigkeit von den echten
Buddy-Manifesten anderer Branches.

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

## Icon-Durchreichung (SREG-10)

`icons[]` und `varianten[].icons[]` aus Display-Manifesten (Sorte a) werden 1:1
durchgereicht — kein Komponieren, kein Ableiten. Sorten b/c tragen kein
`icons`-Feld (das Feld fehlt, ist nicht `null`).

Der Schalter `icons_erforderlich` (Default `False`) steuert die Durchsetzung:
- `False` (Migration): fehlendes `icons[]` → Warnung, Eintrag bleibt gelistet.
- `True` (nach Backfill): fehlendes `icons[]` → per-View-Skip, Warnung.
"""

import glob
import json
import logging
import os

from tools import views_manifest

logger = logging.getLogger(__name__)

# SREG-4: die `typ`-Wertemenge eines Eintrags. Abgeleitet, nie frei vergeben.
# RAT-31 E3: TYP_PANEL und TYP_DISPLAY_CLIENT entfernt — Sorten d/e sterben
# mit der panel/geraete-Registry-Abhängigkeit (#1496).
TYP_DISPLAY = "display"
TYP_ELTERN = "eltern"
TYP_CONTROLLER = "controller"
# SREG-14: Mini-App-Sorte — explizit aus dem Manifest-Feld `typ`, nie aus
# `zielgruppe` abgeleitet (Sonderfall in `_typ_for_view`).
TYP_MINI_APP = "mini-app"


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

def _typ_for_view(ist_controller, view):
    """Leitet `typ` aus Sorte + View-Dict ab (SREG-4 / SREG-14).

    Controller-Apps → `controller`. SREG-14-Sonderfall: `view['typ'] ==
    'mini-app'` → `TYP_MINI_APP` (explizit aus dem Manifest, NICHT aus
    `zielgruppe` abgeleitet — `zielgruppe` ist hier immer `eltern`, aber der
    Typ kommt aus dem deklarierten Feld). Sonst entscheidet `zielgruppe`:
    `eltern` → `eltern` (Sorte b), `kind` → `display` (Sorte a).
    """
    if ist_controller:
        return TYP_CONTROLLER
    if view.get("typ") == TYP_MINI_APP:
        return TYP_MINI_APP
    zielgruppe = view.get("zielgruppe")
    if zielgruppe == "eltern":
        return TYP_ELTERN
    return TYP_DISPLAY


def _eintrag_aus_manifest(app_slug, ist_controller, view, icons_erforderlich=False,
                         funnel_domain=""):
    """Baut EINEN Inventar-Eintrag aus einem Manifest-View (SREG-4/SREG-10/SREG-14).

    `key`/`typ`/`app` sind abgeleitet (deterministisch aus app+slug), der Rest
    kommt 1:1 aus dem Manifest. `varianten` und `icons[]` werden durchgereicht,
    wenn vorhanden (SREG-10 — nur Sorte a, kein Komponieren).

    SREG-14 (Mini-App-Sorte): bei `typ == 'mini-app'` werden `web_app_url` und
    `funnel_url` im Aggregator komponiert (URL-12-Disziplin: URLs entstehen
    beim Konsumenten, nicht im Manifest):
      web_app_url = https://t.me/<bot_username>/<app_short_name>
      funnel_url  = https://<funnel_domain><pfad>
    `bot_username` wird aus `os.environ[view['web_app']['bot_env_var']]` gelesen;
    fehlt die ENV-Variable, wird der Eintrag übersprungen (per-View-Skip,
    SREG-13). `funnel_domain` kommt aus der Aggregator-Konfig (SEITEN_FUNNEL_ORIGIN
    analog — wird von `manifest_eintraege`/`baue_inventar` durchgereicht).

    Bei Sorte a (Display-View): fehlendes `icons[]` erzeugt je nach Schalter
    `icons_erforderlich` eine Warnung (False) oder einen Skip-Signal (True).
    Liefert `None`, wenn der Eintrag übersprungen werden soll (SREG-10/SREG-13).
    """
    slug = view["slug"]
    typ = _typ_for_view(ist_controller, view)
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

    # SREG-14: Mini-App — web_app_url + funnel_url im Aggregator komponieren.
    # icons[] aus web_app.icons[]; kein varianten-Feld (Mini-Apps haben keine
    # Varianten in V1).
    if typ == TYP_MINI_APP:
        web_app = view.get("web_app", {})
        bot_env_var = web_app.get("bot_env_var", "")
        app_short_name = web_app.get("app_short_name", "")
        bot_username = os.environ.get(bot_env_var, "") if bot_env_var else ""
        if not bot_username:
            logger.warning(
                "Mini-App-View übersprungen (SREG-14/SREG-13 per-View-Skip):"
                " app=%s slug=%s — ENV %r nicht gesetzt",
                app_slug, slug, bot_env_var)
            return None
        eintrag["web_app_url"] = "https://t.me/%s/%s" % (bot_username, app_short_name)
        eintrag["funnel_url"] = "https://%s%s" % (funnel_domain, view["pfad"])
        icons = web_app.get("icons")
        if icons is not None:
            eintrag["icons"] = list(icons)
        return eintrag

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


def _views_mit_per_view_resilienz(pfad, app_slug):
    """Lädt die Views eines Manifests mit per-View-Skip-Granularität (SREG-3/DCOMP-3).

    Schneller Pfad: `views_manifest.load(pfad)` — wenn das ganze Manifest valide
    ist, kein Overhead. Kaputt-Pfad: schlägt `load()` mit `ManifestError` fehl
    (z. B. wegen eines einzelnen defekten View-Eintrags), wird das JSON selbst
    geparst. Datei-/Parse-/Struktur-Fehler (kein JSON, kein `views`-Schlüssel)
    führen zum Überspringen des ganzen Manifests — dort ist keine sinnvolle
    View-Teilmenge rettbar.

    Bei einer validen `views`-Liste gilt zuerst Doppel-Slug-Schutz (SREG-13):
    enthält das Manifest doppelte Slugs, ist das Manifest als Ganzes kaputt
    (Datei-Skip > View-Skip, SREG-13 Eskalations-Hierarchie) — kein View-
    Teilrettungs-Versuch. Dann wird jede View einzeln per
    `views_manifest.validate_eintrag()` in-memory geprüft (kein Tempfile):
    defekte Views werden übersprungen (Warnung), valide Views bleiben im Inventar.

    Liefert `(gültige_views, ganzes_manifest_kaputt)`. Wenn `ganzes_manifest_kaputt`
    True, ist `gültige_views` leer und der Aufrufer soll das Manifest vollständig
    überspringen (Warnung wurde hier noch NICHT geloggt — liegt beim Aufrufer).
    """
    try:
        views = views_manifest.load(pfad)
        return views, False  # Schneller Pfad: alles valide
    except views_manifest.ManifestError:
        pass  # Kaputt-Pfad: per-View-Fallback versuchen

    # Kaputt-Pfad: JSON selbst einlesen; Datei-/Struktur-Fehler → ganzes Manifest kaputt
    try:
        with open(pfad, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return [], True
    if not isinstance(data, dict):
        return [], True
    roh_views = data.get("views")
    if not isinstance(roh_views, list):
        return [], True

    # Doppel-Slug-Schutz (SREG-13 Eskalations-Hierarchie: Datei-Skip > View-Skip).
    # Zwei Views mit gleichem Slug im selben Manifest sind ein Manifest-Inhaltsfehler
    # (Autor-Fehler, kein per-View-rettbarer Einzel-Defekt) — ganzes Manifest kaputt.
    slugs = [roh.get("slug") for roh in roh_views if isinstance(roh, dict)]
    gesehene = set()
    for slug in slugs:
        if slug is not None and slug in gesehene:
            logger.warning(
                "Manifest übersprungen (%s, app=%s): doppelter slug %r —"
                " Doppel-Slug ist Manifest-Inhaltsfehler, kein per-View-Skip"
                " (SREG-13/DCOMP-3)", pfad, app_slug, slug)
            return [], True
        if slug is not None:
            gesehene.add(slug)

    # Pro View: in-memory-Validierung via views_manifest.validate_eintrag (T388-S2,
    # kein Tempfile). views_manifest ist die EINE Stelle für Manifest-Validierung
    # (CLAUDE.md §6); der Aggregator macht kein eigenes JSON-Schema.
    gueltige = []
    for roh in roh_views:
        slug_hint = roh.get("slug") if isinstance(roh, dict) else None
        try:
            eintrag = views_manifest.validate_eintrag(roh)
            gueltige.append(eintrag)
        except views_manifest.ManifestError as e:
            logger.warning(
                "View übersprungen (app=%s, slug=%r, %s): %s"
                " — übriges Manifest bleibt vollständig (SREG-3/DCOMP-3)",
                app_slug, slug_hint, pfad, e)
    return gueltige, False


def manifest_eintraege(root, icons_erforderlich=False, funnel_domain=""):
    """Sammelt die Inventar-Einträge der Manifest-Sorten a/b/c/mini-app
    (SREG-2/SREG-4/SREG-10/SREG-14).

    Liest jedes per `discover_manifests` gefundene `views.json`. Ein kaputtes
    Manifest (`ManifestError`) wird mit Warnung übersprungen (SREG-3/DCOMP-3) —
    das übrige Inventar bleibt vollständig. Innerhalb eines Manifests wird jede
    View einzeln bewertet: nur defekte Views werden übersprungen, gültige Views
    desselben Manifests bleiben im Inventar (SREG-3/DCOMP-3 — feinste
    Skip-Granularität ist die View). Liefert die Liste der Einträge in
    Discovery-Reihenfolge.

    `icons_erforderlich` steuert das SREG-10-Verhalten für fehlende `icons[]`
    bei Sorte-a-Views: False = Warnung + gelistet, True = per-View-Skip.

    `funnel_domain` (SREG-14): Funnel-Domain für `funnel_url`-Komposition
    bei Mini-App-Einträgen (URL-12 — Origin kommt vom Aggregator, nicht vom Manifest).
    """
    eintraege = []
    for app_slug, ist_controller, pfad in discover_manifests(root):
        views, ganzes_manifest_kaputt = _views_mit_per_view_resilienz(pfad, app_slug)
        if ganzes_manifest_kaputt:
            logger.warning(
                "Manifest übersprungen (%s, app=%s): JSON-/Struktur-Fehler —"
                " übriges Inventar bleibt vollständig (SREG-3/DCOMP-3)",
                pfad, app_slug)
            continue
        for view in views:
            eintrag = _eintrag_aus_manifest(
                app_slug, ist_controller, view,
                icons_erforderlich=icons_erforderlich,
                funnel_domain=funnel_domain)
            if eintrag is not None:
                eintraege.append(eintrag)
    return eintraege


# ============================================================
#  Inventar-Aufbau (SREG-3 / RAT-31 E3: rein manifest-basiert)
# ============================================================

def baue_inventar(root, icons_erforderlich=False, funnel_domain=""):
    """Baut das vollständige Inventar aus committeten Manifesten (SREG-2/SREG-3).

    RAT-31 E3 (Closes #1496): die ehemals PREG/GER-abhängigen Snapshot-Sorten
    d (Panel-Instanz) und e (Display-Client) entfallen. Das Inventar ist
    ausschließlich aus committeten `views.json`-Manifesten abgeleitet —
    kein HTTP, kein LKG, kein snapshot_pending.

    Args:
        root: Repo-Wurzel, unter der die `views.json`-Manifeste liegen (SREG-2).
        icons_erforderlich: SREG-10-Schalter (Default False = Migrationsphase;
            True = nach Backfill, per-View-Skip bei fehlendem icons[]).
        funnel_domain: Funnel-Domain für `funnel_url`-Komposition bei
            Mini-App-Einträgen (SREG-14, URL-12). Leer = `funnel_url` ohne Host
            (nur sinnvoll im Test-Modus).

    Returns:
        Ein `inventar`-Dict mit:
          - `eintraege`: alle Manifest-Sorten (immer vollständig, auch beim
            Kaltstart — committete Manifeste sind auch ohne laufende Prozesse
            lesbar, SREG-2).
          - `snapshot_pending`: immer leere Liste (keine Snapshot-Sorten mehr).
    """
    eintraege = list(manifest_eintraege(
        root, icons_erforderlich=icons_erforderlich,
        funnel_domain=funnel_domain))
    return {"eintraege": eintraege, "snapshot_pending": []}
