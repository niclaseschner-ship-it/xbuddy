"""Gemeinsames `views.json`-Manifest-Rückgrat (BUD-3 / SREG-2/SREG-4).

Dieses Modul ist die EINE Stelle (CLAUDE.md §6), die das BUD-3-Manifest einer
Komponente lädt, validiert und an die echten Flask-Routen bindet. Plan, Wetter,
Routine und Photo teilen sich diesen Code — jeder Buddy liefert nur seine
`views.json` + einen Eigentest, der `assert_routes_match` gegen seine App ruft.

Es ist Bottom-Layer (`tools/`, MOD-1): es importiert KEINE Komponente
(kein `plan`/`wetter`/`seiten`-Import), nur stdlib. Die Flask-App reicht der
Aufrufer als Argument herein — der Helfer enumeriert nur `app.url_map`.

## Manifest-Form (`views.json`)

Ein JSON-Objekt mit genau einem Top-Level-Schlüssel `views` (Liste). Diese Form
ist die Vorlage für alle vier Folge-Manifeste:

    {
      "views": [
        {
          "slug": "woche",
          "pfad": "/display/plan/woche",
          "label": "Wochenplan",
          "synonyme": ["plan", "wochenplan", "kinderplan"],
          "zeigt": "Den rollierenden Wochenplan der Kinder.",
          "zielgruppe": "kind",
          "varianten": [
            {"slug": "woche-klein", "query": "ansicht=klein",
             "label": "Wochenplan für Kleinkinder"}
          ]
        }
      ]
    }

Pflichtfelder je Eintrag (SREG-4 / BUD-3): `slug`, `pfad`, `label`, `synonyme`,
`zeigt`, `zielgruppe`. Optional: `varianten[]` (je `slug`, `query`, `label`).
`key`/`typ`/`app` leitet der Aggregator AB — sie stehen NICHT im Manifest.

`zielgruppe` ist deskriptiv `kind` | `eltern` (SREG-4/SREG-6).

## Fehlermodell (DCOMP-3)

`load()` wirft bei JSON-/Pflichtfeld-Fehler eine `ManifestError`. Der Aggregator
(`xbuddy-seiten`, SREG-3) fängt sie pro Manifest ab und ÜBERSPRINGT das kaputte
Manifest mit Warnung — nie crasht das ganze Inventar (SREG-3/DCOMP-3). Dieses
Modul entscheidet NICHT über Skip; es signalisiert nur den Fehler. (Symmetrisch
zu `panel/registry.py`, das den Fehler ebenfalls als eigene Exception wirft.)
"""

import json

# Erlaubte `zielgruppe`-Werte (SREG-4/SREG-6: deskriptiv, kein Auth-Gate).
ERLAUBTE_ZIELGRUPPEN = ("kind", "eltern")

# Pflichtfelder je View-Eintrag (SREG-4 / BUD-3). `varianten` ist optional.
PFLICHTFELDER = ("slug", "pfad", "label", "synonyme", "zeigt", "zielgruppe")

# SREG-14: Mini-App-Sorte-Marker.
TYP_MINI_APP = "mini-app"

# SREG-14: Pflichtfelder im `web_app`-Block bei typ:mini-app.
WEB_APP_PFLICHTFELDER = ("bot_env_var", "app_short_name")

# SREG-14: Mini-Apps adressieren in V1 ausschließlich Eltern.
MINI_APP_ZIELGRUPPE = "eltern"

# BUD-4: icons[]-Bereich für Display-Views — mindestens ein Kachel-Icon, max 3
# (Default-Icon + bis zu zwei Markern, ICONS-5/PANEL-3). Sorten b/c tragen kein
# icons-Feld und werden hier NICHT geprüft (SREG-10: kein icons-Feld bei b/c).
ICONS_MIN = 1
ICONS_MAX = 3


class ManifestError(Exception):
    """Das `views.json`-Manifest ist inhaltlich ungültig — JSON-Fehler,
    fehlendes Pflichtfeld oder Schema-Verletzung (DCOMP-3). Der Aggregator
    fängt sie ab und überspringt das Manifest; sie crasht nie das Inventar."""


class RoutenAbweichung(AssertionError):
    """`assert_routes_match` fand eine Drift zwischen den kanonischen
    HTML-GET-Routen einer App und den Manifest-Einträgen (BUD-3-Eigentest)."""


def load(path):
    """Liest und validiert ein `views.json` (BUD-3 / SREG-4).

    Liefert die Liste der validierten View-Einträge (Dicts in Manifest-
    Reihenfolge). Bei JSON-Fehler, fehlendem Top-Level-`views`, fehlendem
    Pflichtfeld oder Schema-Verletzung wird `ManifestError` geworfen — der
    Aufrufer (Aggregator) entscheidet über Skip (DCOMP-3), dieses Modul crasht
    nicht selbst und schluckt den Fehler nicht still.

    Anders als ein gitignoretes Config-File (CONFIG-1) ist ein committetes
    Manifest KEIN „darf-fehlen": eine fehlende Datei ist hier ein echter
    `ManifestError` (FileNotFoundError → ManifestError), denn eine deklarierte
    Komponente OHNE ihr committetes Manifest ist ein Fehler, kein leerer Default.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise ManifestError("views.json fehlt: %s" % path) from e
    except json.JSONDecodeError as e:
        raise ManifestError("views.json nicht parsebar (%s): %s" % (path, e)) from e

    if not isinstance(data, dict):
        raise ManifestError(
            "views.json muss ein JSON-Objekt sein, ist %s" % type(data).__name__)
    roh_views = data.get("views")
    if not isinstance(roh_views, list):
        raise ManifestError(
            "views.json: Top-Level `views` muss eine Liste sein, ist %r"
            % type(roh_views).__name__)

    eintraege = []
    gesehene_slugs = set()
    for roh in roh_views:
        eintrag = validate_eintrag(roh)
        slug = eintrag["slug"]
        if slug in gesehene_slugs:
            raise ManifestError("views.json: doppelter slug %r" % slug)
        gesehene_slugs.add(slug)
        eintraege.append(eintrag)
    return eintraege


def _ist_display_view(roh):
    """Eine Display-View (BUD-4 / SREG-4-Sorte a) ist ein Eintrag mit
    `zielgruppe=kind` UND einem `/display/<app>/<view>`-Pfad. Nur diese Sorte
    trägt `icons[]` (Eltern-Settings-Sorte b und Controller-Sorte c nicht,
    PANEL-7 Descriptor `{app, view}` zielt nur auf Display-Views).

    Controller-Apps haben `zielgruppe=kind` möglich, aber ihren Pfad-Prefix
    `/controller/<app>/` — der Pfad-Prefix entscheidet hier, damit der
    Validator BUD-4 nicht auf Controller-Views anwendet (die `icons[]`
    nicht tragen).
    """
    pfad = roh.get("pfad") or ""
    return roh.get("zielgruppe") == "kind" and pfad.startswith("/display/")


def validate_eintrag(roh):
    """Validiert einen einzelnen View-Eintrag (SREG-4) und gibt ihn normalisiert
    zurück. Wirft `ManifestError` bei fehlendem Pflichtfeld oder Schema-Bruch.

    Public API (T388-S2): ermöglicht dem Aggregator per-View-Iteration in-memory,
    ohne für jede View ein Tempfile anzulegen. `load()` ruft diese Funktion intern
    weiterhin auf — die Validierungslogik lebt an EINER Stelle (CLAUDE.md §6).

    BUD-4-Anteil (T387-S2): für Display-Views (Sorte a) zusätzlich `icons[]`
    Pflicht (1..3 Pfade als String, relativ zur Icon-Basis
    `/display/_shared/icons/`) und `varianten[].icons[]` voll Pflicht. Sorten
    b/c bleiben unverändert — der Aggregator (SREG-10) strippt das icons-Feld
    dort nicht, das Manifest darf es dort gar nicht erst tragen.
    """
    if not isinstance(roh, dict):
        raise ManifestError("views.json: Eintrag ist kein Objekt: %r" % roh)
    for feld in PFLICHTFELDER:
        if feld not in roh or roh[feld] in (None, ""):
            raise ManifestError(
                "views.json: Eintrag ohne Pflichtfeld %r: %r" % (feld, roh))
    if not isinstance(roh["synonyme"], list):
        raise ManifestError(
            "views.json: `synonyme` muss eine Liste sein (slug %r)" % roh.get("slug"))
    if roh["zielgruppe"] not in ERLAUBTE_ZIELGRUPPEN:
        raise ManifestError(
            "views.json: `zielgruppe` muss %s sein, ist %r (slug %r)"
            % (ERLAUBTE_ZIELGRUPPEN, roh["zielgruppe"], roh.get("slug")))


    # SREG-14: Mini-App-Sorte — `typ: "mini-app"` erfordert einen validen
    # `web_app`-Block mit `bot_env_var` + `app_short_name` und
    # `zielgruppe == "eltern"` (per-View-Skip nach SREG-13 bei Fehler).
    # Der Check läuft VOR dem BUD-4-icons-Check, da Mini-Apps ihr icons-Feld
    # im `web_app`-Block tragen (nicht auf Top-Level) — kein BUD-4-Konflikt.
    if roh.get("typ") == TYP_MINI_APP:
        if roh["zielgruppe"] != MINI_APP_ZIELGRUPPE:
            raise ManifestError(
                "views.json: Mini-App (typ='mini-app') muss zielgruppe=%r haben,"
                " ist %r (slug %r) — SREG-14"
                % (MINI_APP_ZIELGRUPPE, roh["zielgruppe"], roh.get("slug")))
        web_app = roh.get("web_app")
        if not isinstance(web_app, dict):
            raise ManifestError(
                "views.json: Mini-App (typ='mini-app') ohne `web_app`-Block"
                " (slug %r) — SREG-14" % roh.get("slug"))
        for feld in WEB_APP_PFLICHTFELDER:
            if not web_app.get(feld):
                raise ManifestError(
                    "views.json: Mini-App `web_app.%s` fehlt oder leer"
                    " (slug %r) — SREG-14" % (feld, roh.get("slug")))
        # icons[] im web_app-Block ist Pflicht (SREG-14: analog Sorte a)
        web_app_icons = web_app.get("icons")
        if web_app_icons is not None:
            _validate_icons(web_app_icons, roh.get("slug"), feldname="web_app.icons")
        # Mini-Apps tragen kein Top-Level icons-Feld und keine varianten[].
        if "icons" in roh:
            raise ManifestError(
                "views.json: Mini-App darf kein Top-Level `icons[]` tragen —"
                " Icons liegen in `web_app.icons[]` (slug %r, SREG-14)"
                % roh.get("slug"))
        return roh

    ist_display = _ist_display_view(roh)
    # BUD-4: icons[] nur bei Display-Views prüfen — Sorten b/c tragen kein
    # icons-Feld; ist eines da, wäre das ein Schema-Bruch (kein Vorrat, CLAUDE.md §6).
    if "icons" in roh:
        if not ist_display:
            raise ManifestError(
                "views.json: `icons[]` nur bei Display-Views (Sorte a) erlaubt"
                " — Eintrag (slug %r, zielgruppe %r, pfad %r) darf kein"
                " icons-Feld tragen (BUD-4)"
                % (roh.get("slug"), roh.get("zielgruppe"), roh.get("pfad")))
        _validate_icons(roh["icons"], roh.get("slug"), feldname="icons")

    varianten = roh.get("varianten")
    if varianten is not None:
        _validate_varianten(varianten, roh.get("slug"), ist_display=ist_display)
    return roh


def _validate_icons(icons, slug, feldname="icons"):
    """Validiert das BUD-4-`icons[]`-Feld: Liste von 1..3 nicht-leeren Strings.

    Pfade sind relativ zur Icon-Basis `/display/_shared/icons/` (BUD-4) — der
    Validator prüft nur Schema (Liste, Länge, String-Typ, nicht-leer); der
    semantische Pfad-Check (existiert das PNG?) ist ein Deploy-/Backfill-Gate
    (Ticket #387 Backfill, nicht hier — BUD-4 Schluss-Absatz).
    """
    if not isinstance(icons, list):
        raise ManifestError(
            "views.json: `%s` muss eine Liste sein (slug %r), ist %r"
            % (feldname, slug, type(icons).__name__))
    if not ICONS_MIN <= len(icons) <= ICONS_MAX:
        raise ManifestError(
            "views.json: `%s` muss %d..%d Pfade enthalten, hat %d (slug %r) — BUD-4"
            % (feldname, ICONS_MIN, ICONS_MAX, len(icons), slug))
    for i, pfad in enumerate(icons):
        if not isinstance(pfad, str) or not pfad:
            raise ManifestError(
                "views.json: `%s`[%d] muss nicht-leerer String sein, ist %r"
                " (slug %r) — BUD-4" % (feldname, i, pfad, slug))


def _validate_varianten(varianten, slug, ist_display=False):
    """Validiert das optionale `varianten[]` (SREG-1/SREG-4 + BUD-4): Liste von
    Objekten mit je `slug`, `query`, `label`. BUD-4 (T387-S2): bei Display-View
    ist `varianten[].query` **flaches Objekt** (kein String) und
    `varianten[].icons[]` Pflicht (1..3 Pfade) — keine Erbung vom View-Icon.
    """
    if not isinstance(varianten, list):
        raise ManifestError(
            "views.json: `varianten` muss eine Liste sein (slug %r)" % slug)
    for v in varianten:
        if not isinstance(v, dict):
            raise ManifestError(
                "views.json: Variante ist kein Objekt: %r (slug %r)" % (v, slug))
        for feld in ("slug", "query", "label"):
            if feld not in v or v[feld] in (None, ""):
                raise ManifestError(
                    "views.json: Variante ohne Pflichtfeld %r: %r (slug %r)"
                    % (feld, v, slug))
        if ist_display:
            # BUD-4: query ist flaches Objekt (kein String), passt direkt ins
            # Kachel-/Descriptor-Schema (PANEL-7).
            if not isinstance(v["query"], dict):
                raise ManifestError(
                    "views.json: Variante `query` muss flaches Objekt sein"
                    " (BUD-4), ist %r (slug %r, variante %r)"
                    % (type(v["query"]).__name__, slug, v.get("slug")))
            # BUD-4: varianten[].icons[] voll Pflicht — keine Ableitung.
            if "icons" not in v:
                raise ManifestError(
                    "views.json: Display-Variante ohne `icons[]` (BUD-4, keine"
                    " Erbung vom View-Icon): %r (slug %r)" % (v, slug))
            _validate_icons(v["icons"], slug, feldname="varianten[].icons")


def kanonische_display_pfade(app, slug, ausgenommene_pfade=None):
    """Sammelt die kanonischen HTML-GET-Routen-Pfade einer Flask-App unter
    `/display/<slug>/…` (BUD-3-Eigentest, buddy-agnostisch).

    Eine Route zählt als kanonischer View-Einstiegspunkt, wenn:
    - sie GET erlaubt (`"GET" in methods`),
    - ihr Pfad echt tiefer als `/display/<slug>/` liegt (eine View darunter),
    - sie einen FESTEN Pfad hat (kein URL-Konverter `<…>`): freie/parametrische
      Routen sind keine kanonischen Einstiegspunkte (Flask-`static` mit
      `<path:filename>` fällt damit automatisch raus, ebenso `?ab=`-artige
      Anker liegen ohnehin nicht als eigene Route vor),
    - ihr Pfad nicht in `ausgenommene_pfade` steht.

    `ausgenommene_pfade` (optionales Set) trägt die buddy-spezifischen
    Ausnahmen, die NICHT aus der `url_map` ablesbar sind — Alias-/Redirect-
    Routen und HTML-rendernde Routen, die der Buddy bewusst nicht listet. So
    bleibt die Ausnahmeliste am Buddy-Eigentest sichtbar (BUD-3), statt im
    Helfer zu verschwinden. POST-/PUT-only- und `/api/`-Endpunkte sind durch
    den GET-/Prefix-Filter schon ausgenommen und gehören NICHT in dieses Set.
    """
    ausgenommene = set(ausgenommene_pfade or ())
    prefix = "/display/%s/" % slug
    pfade = set()
    for regel in app.url_map.iter_rules():
        if "GET" not in regel.methods:
            continue
        rule = regel.rule
        if not rule.startswith(prefix) or rule == prefix:
            continue
        if "<" in rule:
            # Parametrische Route (z. B. Flask-`static`) — kein kanonischer
            # View-Einstiegspunkt.
            continue
        if rule in ausgenommene:
            continue
        pfade.add(rule)
    return pfade


def assert_routes_match(app, eintraege, slug, ausgenommene_pfade=None):
    """Bindet das Manifest bidirektional an die echten Flask-Routen (BUD-3).

    Prüft, dass die Menge der kanonischen HTML-GET-Routen unter
    `/display/<slug>/…` (siehe `kanonische_display_pfade`) GENAU der Menge der
    `pfad`-Werte der Manifest-Einträge dieses Slugs entspricht:
    - jede kanonische Route hat genau einen Manifest-Eintrag, und
    - jeder Manifest-Eintrag eine kanonische Route.

    Schlägt bei Drift mit `RoutenAbweichung` fehl (verständliche Meldung, welche
    Route/welcher Eintrag fehlt). `ausgenommene_pfade` reicht der Buddy-Eigentest
    für Alias-/Redirect-Routen durch (BUD-3-Ausnahmen).

    `eintraege` ist die von `load()` gelieferte Liste; nur Einträge mit
    `pfad`-Prefix `/display/<slug>/` zählen für diese Buddy-Bindung (ein
    Manifest mit Fremd-Pfaden wäre selbst ein Fehler, aber die Bindung prüft
    den eigenen Slug).
    """
    routen_pfade = kanonische_display_pfade(app, slug, ausgenommene_pfade)
    # Nur die kanonischen /display/<slug>/-Einträge zählen für diese Buddy-Bindung
    # (siehe Docstring). Seiten-gehostete Eltern-Views (typ:pwa, Pfad /seiten/…,
    # ESB-3-Heimat im Buddy-views.json, Route aber in seiten) sind KEINE
    # /display/-Routen des Buddys und werden hier nicht gegen die Buddy-App
    # geprüft — sonst false-Drift nach #1680 (T1689).
    display_prefix = "/display/%s/" % slug
    manifest_pfade = {
        e["pfad"] for e in eintraege if e["pfad"].startswith(display_prefix)
    }

    fehlt_im_manifest = routen_pfade - manifest_pfade
    fehlt_als_route = manifest_pfade - routen_pfade
    if fehlt_im_manifest or fehlt_als_route:
        teile = []
        if fehlt_im_manifest:
            teile.append(
                "Routen ohne Manifest-Eintrag: %s" % sorted(fehlt_im_manifest))
        if fehlt_als_route:
            teile.append(
                "Manifest-Einträge ohne Route: %s" % sorted(fehlt_als_route))
        raise RoutenAbweichung(
            "Manifest⇔Route-Drift für slug %r — %s" % (slug, "; ".join(teile)))
