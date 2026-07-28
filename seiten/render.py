"""Seiten-Registry — Renderer-Datenaufbereitung fuer SREG-12 V2-Layout (#467).

Reine, testbare Daten-Vorbereitung: aus dem `inventar`-Dict (SREG-3-Output des
Aggregators) wird die V2-Layout-Struktur gebaut, die das Jinja2-Template
`uebersicht.html` braucht. Hier wohnt NICHTS, was Flask oder HTTP braucht — der
Render-Aufruf in `seiten/main.py` ruft `baue_layout(inventar, heim_origin,
tailscale_origin)` und reicht das Ergebnis an `render_template` durch.

Begruendung der Trennung (Spec-konform, SREG-12 V2):
- Die Hero-Sektion „Geraete-Paare" gruppiert Eintraege ueber DREI Sorten
  (Display-Client e + Panel-Instanz d + Editor b), gebunden ueber die SREG-4-
  Verknuepfungs-Felder. Diese Gruppierung ist genuine Daten-Logik, nicht
  Praesentation — sie gehoert in den Renderer, nicht ins Template (wo sie nur
  noch ausgegeben wird).
- Die sekundaere Sektion gruppiert nach `app` (Buddy/Service-Slug). Auch das
  ist Daten-Logik (Sortierung nach Karten-Anzahl absteigend, dann
  alphabetisch — SREG-12).
- Die zwei Origin-URLs (Heim/Tailscale) je Eintrag werden hier vorgerechnet,
  damit das Template nur noch eine Liste von URL-Paaren rendert.

Das Template bleibt damit eine reine Praesentations-Schicht ohne If-Else-
Logik gegen die Sorten — das macht es wartbar und macht den Renderer
testbar OHNE Flask/Jinja2.

SREG-12-Anker:
- V2-Layout (Hero + Buddy-Gruppen): SREG-12 Abschnitt „Layout (V1, von oben
  nach unten — nach Gate B Wahl 2026-06-08 ‚gemeinsame Box pro Geraete-Paar')".
- Hero-Paar-Box (Display + Panels + Editor-Anhang): SREG-12 Punkt 2.
- Buddy-Gruppen-Reihenfolge (Anzahl Karten absteigend, dann alphabetisch):
  SREG-12 Punkt 3 Schlusssatz.
- Icon-Fallback (Sorten b/c/d/e ohne icons[]): SREG-12 Abschnitt
  „Icon-Fallback" — Default-Piktogramm aus `seiten/static/icons/<typ>.png`.
"""

import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


# ============================================================
#  SHELL-4 (RAT-31 E2) — Panel-URL-Konvention same-origin in seiten/
# ============================================================
#
# Verpflanzt aus router/main.py::build_panel_url (ROU-24). Reine Funktion
# (Test-Naht), byte-gleiche Query-Reihenfolge zum Router — sonst Render-Drift
# zwischen dem alten Router-Pfad und dem neuen seiten/-Ingest. Hardcode-frei:
# funktioniert fuer jedes app/view-Tupel ohne Code-Aenderung.

def build_panel_url(app_val, view_val, query):
    """SHELL-4: /display/<app>/<view>[?<urlencoded query>].

    Identische Ableitung wie router/main.py::build_panel_url (ROU-24): der
    Descriptor (app/view [+ flaches query]) wird per Konvention in die
    Inhalts-URL uebersetzt, die das rechte Pane als iframe.src laedt. Die
    Query-Schluessel werden stabil (sortiert) serialisiert — deterministisch
    und testbar, byte-gleich zum Router (kein Render-Drift beim Verpflanzen).
    """
    base = "/display/%s/%s" % (app_val, view_val)
    if query:
        items = [(k, query[k]) for k in sorted(query.keys())]
        return base + "?" + urlencode(items)
    return base

# SREG-4 Sorten-typen (Spiegel zu seiten.aggregator) — der Renderer haengt
# nicht am Aggregator-Modul, damit Render-Tests den Aggregator nicht importieren
# muessen; die Werte sind durch SREG-4 fixiert.
TYP_DISPLAY = "display"
TYP_ELTERN = "eltern"
TYP_CONTROLLER = "controller"
TYP_PANEL = "panel"
TYP_DISPLAY_CLIENT = "display-client"
# SREG-14: Mini-App-Sorte (Spiegel zu seiten.aggregator.TYP_MINI_APP).
TYP_MINI_APP = "mini-app"

# #1210 / SREG-15-Erweiterung: audience-Flag am Eintrag. Die EINE Ableitung
# (baue_layout) markiert je Karte, welche familienseitige Uebersichts-/Registry-
# Oberflaeche sie rendert. Abweichende Sichten FILTERN deklarativ ueber dieses
# Feld — sie forken NICHT die Ableitung (kein zweiter Gruppierungs-Code je View).
AUDIENCE_UEBERSICHT = "uebersicht"          # server-gerenderte Grossbild-Uebersicht
AUDIENCE_MINI_APP = "mini-app-uebersicht"   # Telegram-Mini-App-Uebersicht
_ALLE_AUDIENCES = (AUDIENCE_UEBERSICHT, AUDIENCE_MINI_APP)

# SREG-12 Icon-Fallback je Sorte. Pfade unter /api/v1/seiten/static/icons/
# (Flask static_url_path, SREG-12 #467) — passt zum nginx-Sub-Pfad-Block
# `location ^~ /api/v1/seiten/` und braucht keine eigene nginx-Route.
# NICHT zu verwechseln mit /display/_shared/icons/ (Router-Origin, Display-View-
# Bibliothek; Sorte a tragt icons[] und nutzt diesen Pfad).
_FALLBACK_ICON = {
    TYP_DISPLAY: "/api/v1/seiten/static/icons/eltern.png",        # Sorte a Default (haben aber icons[])
    TYP_ELTERN: "/api/v1/seiten/static/icons/eltern.png",         # Sorte b
    TYP_CONTROLLER: "/api/v1/seiten/static/icons/controller.png", # Sorte c
    TYP_PANEL: "/api/v1/seiten/static/icons/panel.png",           # Sorte d
    TYP_DISPLAY_CLIENT: "/api/v1/seiten/static/icons/display-client.png",  # Sorte e
}


def _urls(eintrag, heim_origin, tailscale_origin, funnel_origin=""):
    """Bildet die drei Origin-URLs (Heim/Tailscale/Funnel) je Eintrag (SREG-7).

    Pfad-Anhaengung an die Origin — Origins ohne trailing Slash, Pfade mit
    fuehrendem Slash. Tailscale-URL ist None, wenn `tailscale_origin` leer
    (SREG-7 V1-Soll: dann Banner-Hinweis statt zwei Spalten). Funnel-URL ist
    None, wenn `funnel_origin` leer (SREG-7 dritte Origin, RAT-27 — User-Geraete
    externer Zugang; fehlt der Wert, wird die Spalte nicht angeboten).
    """
    pfad = eintrag.get("pfad", "")
    heim = (heim_origin.rstrip("/") + pfad) if heim_origin else None
    tail = (tailscale_origin.rstrip("/") + pfad) if tailscale_origin else None
    funnel = (funnel_origin.rstrip("/") + pfad) if funnel_origin else None
    return {"heim": heim, "tailscale": tail, "funnel": funnel}


def _karte_basis(eintrag, heim_origin, tailscale_origin, funnel_origin=""):
    """Baut eine Karten-Datenstruktur fuer das Template (SREG-12 Inhalt je Karte).

    Pflichtfelder am Template-Modell: `label`, `zeigt`, `pfad`, `typ`, `icon`,
    `urls.heim`, `urls.tailscale`, `urls.funnel`, plus `synonyme[]` (fuer die
    clientseitige Volltextsuche in SREG-12). `key` und `instanz` sind als
    data-attribute nuetzlich (Suche, Hero-Anker), wandern als `key`/`instanz` mit.
    """
    typ = eintrag.get("typ", "")
    icons = eintrag.get("icons") or []
    # SREG-12 Icon-Fallback: nur Sorte a traegt icons[], Sorten b/c/d/e
    # bekommen ein Default-Piktogramm aus /static/icons/<typ>.png.
    icon = (
        "/display/_shared/icons/" + icons[0] if icons
        else _FALLBACK_ICON.get(typ, _FALLBACK_ICON[TYP_ELTERN])
    )
    # #1210: Mini-App-Karten erscheinen in der Mini-App-Uebersicht in der
    # dedizierten Sektion `mini_apps` (mit Telegram-Deep-Link), NICHT in den
    # Buddy-Gruppen. Darum tragen sie IN den Buddy-Gruppen nur die Grossbild-
    # audience. Das ist ein deklaratives Feld (wie `icon`), KEIN Fork-Zweig.
    audience = ([AUDIENCE_UEBERSICHT] if typ == TYP_MINI_APP
                else list(_ALLE_AUDIENCES))
    return {
        "key": eintrag.get("key", ""),
        "label": eintrag.get("label", ""),
        "zeigt": eintrag.get("zeigt", ""),
        "pfad": eintrag.get("pfad", ""),
        "typ": typ,
        "icon": icon,
        "icons": list(icons),  # fuer Varianten-Karten, bewahrt SREG-10 1:1
        "synonyme": list(eintrag.get("synonyme") or []),
        "instanz": eintrag.get("instanz", ""),
        "app": eintrag.get("app", ""),
        "stale": bool(eintrag.get("stale", False)),
        "urls": _urls(eintrag, heim_origin, tailscale_origin, funnel_origin),
        # SREG-14: Mini-App-Deep-Links (leer bei Nicht-Mini-Apps). Der Aggregator
        # komponiert sie; der Renderer reicht sie nur durch (URL-12-Disziplin).
        "web_app_url": eintrag.get("web_app_url", ""),
        "funnel_url": eintrag.get("funnel_url", ""),
        "audience": audience,
    }


def _varianten_karten(eintrag, heim_origin, tailscale_origin, funnel_origin=""):
    """SREG-12 Varianten: je Variante eine eigene Karte mit voller query-Anhaengung.

    Pfad-Bildung: `<eintrag.pfad>?<k>=<v>&…` (flaches Query-Objekt, BUD-4).
    Icon-Vorrang: Varianten-`icons[]` wenn vorhanden, sonst Eintrags-`icons[]`.
    Variant-Marker: `variante=True` am Render-Modell, damit das Template das
    Variant-Markup (gestrichelter Rand + „Variante"-Tag) anwenden kann.
    """
    karten = []
    for v in eintrag.get("varianten") or []:
        # Flat Query-Objekt -> Query-String, sortiert fuer Deterministik.
        query = v.get("query") or {}
        qs = "&".join("%s=%s" % (k, query[k]) for k in sorted(query))
        pfad = eintrag.get("pfad", "")
        v_pfad = pfad + "?" + qs if qs else pfad
        v_icons = v.get("icons") or eintrag.get("icons") or []
        karte = {
            "key": "%s/%s" % (eintrag.get("key", ""), v.get("slug", "")),
            "label": v.get("label", eintrag.get("label", "")),
            "zeigt": eintrag.get("zeigt", ""),
            "pfad": v_pfad,
            "typ": eintrag.get("typ", ""),
            "icon": ("/display/_shared/icons/" + v_icons[0]) if v_icons
                    else _FALLBACK_ICON.get(eintrag.get("typ"), _FALLBACK_ICON[TYP_ELTERN]),
            "icons": list(v_icons),
            "synonyme": list(eintrag.get("synonyme") or []),
            "instanz": "",
            "app": eintrag.get("app", ""),
            "stale": bool(eintrag.get("stale", False)),
            "urls": {
                "heim": (heim_origin.rstrip("/") + v_pfad) if heim_origin else None,
                "tailscale": (tailscale_origin.rstrip("/") + v_pfad) if tailscale_origin else None,
                # SREG-7 dritte Origin (RAT-27): Funnel-URL fuer User-Geraete.
                "funnel": (funnel_origin.rstrip("/") + v_pfad) if funnel_origin else None,
            },
            # Varianten sind nie Mini-Apps: keine Deep-Links, beide Audiences.
            "web_app_url": "",
            "funnel_url": "",
            "audience": list(_ALLE_AUDIENCES),
            "variante": True,
        }
        karten.append(karte)
    return karten


# ============================================================
#  Hero-Sektion „Geraete-Paare" (SREG-12 Punkt 2)
# ============================================================

def _hero_paare(eintraege, heim_origin, tailscale_origin, funnel_origin=""):
    """Baut die Hero-Paar-Boxen (Display + Panels + Editor-Anhang).

    Ein Paar entsteht, sobald ein Display-Client `verknuepft_mit_panels` traegt
    (≥1 Panel). Reihenfolge: Displays alphabetisch nach `instanz` (display_id).
    Innerhalb eines Paars: Panels in der Reihenfolge von `verknuepft_mit_panels`,
    je Panel der Editor angedockt (verknuepft_mit_panel = panel_id Lookup).

    *Wenn* kein Display ein gekoppeltes Panel hat → leere Liste; das Template
    rendert dann den „Noch keine Geraete-Paare angelegt"-Hinweis.
    """
    by_panel_id = {e["instanz"]: e for e in eintraege
                   if e.get("typ") == TYP_PANEL and e.get("instanz")}
    editor_by_panel_id = {e.get("verknuepft_mit_panel"): e for e in eintraege
                          if e.get("typ") == TYP_ELTERN
                          and e.get("verknuepft_mit_panel")}
    paare = []
    displays = [e for e in eintraege
                if e.get("typ") == TYP_DISPLAY_CLIENT
                and e.get("verknuepft_mit_panels")]
    for display in sorted(displays, key=lambda e: e.get("instanz") or ""):
        panel_karten = []
        for pid in display["verknuepft_mit_panels"]:
            panel = by_panel_id.get(pid)
            if panel is None:
                # Defensiv: PREG-Inkonsistenz, Display sagt Panel da, Panel-Sorte
                # fehlt im Inventar. SREG-3-Last-Known-Good kann sowas erzeugen.
                logger.warning(
                    "Hero-Paar: Panel %r am Display %r nicht im Inventar — uebersprungen",
                    pid, display.get("instanz"))
                continue
            editor = editor_by_panel_id.get(pid)
            # SHELL-10: Shell-URL je panel_id in SREG-12-Form (Heim + Tailscale +
            # SREG-7 Funnel). URL aus panel_id abgeleitet — kein GER-Co-Location.
            panel_karten.append({
                "panel": _karte_basis(panel, heim_origin, tailscale_origin, funnel_origin),
                "editor": (_karte_basis(editor, heim_origin, tailscale_origin, funnel_origin)
                           if editor else None),
                "shell_urls": {
                    "heim": (heim_origin.rstrip("/") + "/shell/" + pid) if heim_origin else None,
                    "tailscale": (tailscale_origin.rstrip("/") + "/shell/" + pid) if tailscale_origin else None,
                    # SREG-7 dritte Origin (RAT-27): Funnel-Shell-URL fuer User-Geraete.
                    "funnel": (funnel_origin.rstrip("/") + "/shell/" + pid) if funnel_origin else None,
                },
            })
        paare.append({
            "display": _karte_basis(display, heim_origin, tailscale_origin, funnel_origin),
            "panel_anzahl": len(panel_karten),
            "panels": panel_karten,
        })
    return paare


# ============================================================
#  Sekundaere Sektion „Andere Seiten" (SREG-12 Punkt 3)
# ============================================================

def _ist_im_hero(eintrag, hero_paare):
    """True, wenn dieser Eintrag in einer Hero-Paar-Box steckt (Display, Panel
    oder Editor). Sorten a/c sind nie im Hero."""
    typ = eintrag.get("typ")
    if typ not in (TYP_DISPLAY_CLIENT, TYP_PANEL, TYP_ELTERN):
        return False
    key = eintrag.get("key")
    for paar in hero_paare:
        if paar["display"]["key"] == key:
            return True
        for pk in paar["panels"]:
            if pk["panel"]["key"] == key:
                return True
            if pk["editor"] and pk["editor"]["key"] == key:
                return True
    return False


def _buddy_gruppen(eintraege, hero_paare, heim_origin, tailscale_origin, funnel_origin=""):
    """Gruppiert die uebrigen Eintraege nach `app` (Buddy/Service-Slug).

    Eintraege in Hero-Paar-Boxen werden ausgeschlossen (sie haengen dort). Sorten
    d/e ohne `app` fallen in eine Sammel-Gruppe `instanz` (SREG-12 Punkt 3).

    Reihenfolge SREG-12: Anzahl Karten absteigend, dann alphabetisch.
    Variant-Karten haengen als eigene Geschwister-Karten in derselben Gruppe
    (SREG-12 Punkt 3).
    """
    gruppen = {}  # app_slug -> [karten]
    for e in eintraege:
        if _ist_im_hero(e, hero_paare):
            continue
        app = e.get("app")
        if not app:
            # Sorten d/e ohne app — Sammelgruppe „instanz"
            app = "instanz"
        gruppe = gruppen.setdefault(app, [])
        gruppe.append(_karte_basis(e, heim_origin, tailscale_origin, funnel_origin))
        gruppe.extend(_varianten_karten(e, heim_origin, tailscale_origin, funnel_origin))
    # SREG-12 Reihenfolge: Anzahl absteigend, dann alphabetisch
    return [
        {"app": app, "karten": karten, "anzahl": len(karten)}
        for app, karten in sorted(
            gruppen.items(), key=lambda it: (-len(it[1]), it[0]))
    ]


# ============================================================
#  Mini-App-Sektion (SREG-14) — dedizierte Telegram-App-Liste
# ============================================================

def _mini_apps(eintraege, heim_origin, tailscale_origin, funnel_origin=""):
    """Baut die dedizierte Mini-Telegram-App-Sektion (SREG-14, MAU-4 Punkt 1).

    Dieselbe Ableitung wie fuer die Buddy-Gruppen (`_karte_basis`), nur als
    eigene Liste — damit eine Oberflaeche die Mini-Apps mit ihrem Telegram-
    Deep-Link (`web_app_url`) in einer eigenen Sektion zeigen kann. Die
    Grossbild-Uebersicht rendert Mini-Apps stattdessen als gewoehnliche
    Buddy-Karte (pfad-URL); das ist die einzige ratifiziert-legitime Sicht-
    Asymmetrie (#1210, Berater-Constraint 4). Dieselben Karten-Objekte tauchen
    darum bewusst in beiden Ableitungs-Zweigen auf (Buddy-Gruppe: audience
    nur `uebersicht`; hier: volle Mini-App-Sektion).

    Reihenfolge: alphabetisch nach `label` (deterministisch fuer den Guard).
    """
    apps = [_karte_basis(e, heim_origin, tailscale_origin, funnel_origin)
            for e in eintraege if e.get("typ") == TYP_MINI_APP]
    return sorted(apps, key=lambda k: (k.get("label") or "").lower())


# ============================================================
#  Layout-Aufbau (V2)
# ============================================================

def baue_layout(inventar, heim_origin, tailscale_origin, funnel_origin=""):
    """Bereitet die V2-Layout-Datenstruktur fuer das Template auf (SREG-12).

    Args:
        inventar: das Aggregator-Ergebnis ({"eintraege": […], "snapshot_pending": […]}).
        heim_origin: `display_url_origin_heim` (Pflicht, SREG-7).
        tailscale_origin: `display_url_origin_tailscale` (V1-Soll, SREG-7) — leer
            string oder None loest den Tailscale-Banner aus.
        funnel_origin: `display_url_origin_funnel` (SREG-7, RAT-27) — leer string
            oder None unterdrueckt die Funnel-Spalte in der Uebersicht (kein Auto-
            Fallback auf heim/tailscale — falsche Origin waere Cookie im falschen Jar).

    Returns:
        Dict mit `hero_paare`, `buddy_gruppen`, `mini_apps`, `tailscale_banner`
        (bool), `snapshot_pending` (Liste), `heim_origin`, `tailscale_origin`,
        `funnel_origin`. Direkt an `render_template("uebersicht.html", **layout)`
        reichbar UND als JSON-Kontrakt fuer `GET /api/v1/seiten/layout` (#1210
        Daten-SSoT). Jede Karte traegt `urls.funnel` (None wenn leer).

    #1210 (Daten-SSoT): Dieses Dict ist die EINE angereicherte Ableitung, die
    ALLE familienseitigen Uebersichts-/Registry-Oberflaechen konsumieren
    (Jinja `/uebersicht` UND die Mini-App). Keine Oberflaeche re-derived
    Gruppierung/Anreicherung lokal; abweichende Sichten filtern deklarativ
    ueber das `audience`-Feld je Karte (SREG-15-Erweiterung).
    """
    eintraege = (inventar or {}).get("eintraege", []) or []
    hero = _hero_paare(eintraege, heim_origin, tailscale_origin, funnel_origin)
    buddies = _buddy_gruppen(eintraege, hero, heim_origin, tailscale_origin, funnel_origin)
    return {
        "hero_paare": hero,
        "buddy_gruppen": buddies,
        # SREG-14 / #1210: dedizierte Mini-App-Sektion (additiv — Jinja liest sie
        # nicht; die Mini-App-Uebersicht rendert sie mit Telegram-Deep-Link).
        "mini_apps": _mini_apps(eintraege, heim_origin, tailscale_origin, funnel_origin),
        "tailscale_banner": not bool(tailscale_origin),
        "snapshot_pending": list((inventar or {}).get("snapshot_pending", []) or []),
        "heim_origin": heim_origin or "",
        "tailscale_origin": tailscale_origin or "",
        # SREG-7 dritte Origin (RAT-27): Funnel-FQDN fuer User-Geraete.
        # Leer wenn nicht konfiguriert — kein Auto-Fallback (Cookie-Jar-Integritat).
        "funnel_origin": funnel_origin or "",
    }
