"""Ableitungs-Rueckgrat der Auslassungs-Pruefung fuer Eltern-Flaechen (#1822).

Vorbild: `tests/test_testpaths_vollstaendig.py` — den Baum ablaufen, gegen die
deklarierte Liste vergleichen, einen **dokumentierten Ausnahme-Satz** fuehren.
Diese Bauform fehlte fuer Registry-Eintraege und Eltern-Seiten.

## Wozu ueberhaupt

Unsere Pruefungen fragten bisher nur „ist das, was jemand eingetragen hat,
richtig?" — nie „fehlt ein Eintrag?". `seiten/tests/test_pwa_mantel.py` fror
die Mantel-Konsumenten als Literal-Set ein: das bricht beim **Hinzufuegen**
(Set-Gleichheit), aber eine neue Eltern-Flaeche, die sich nie registriert,
laesst jeden Test gruen. Was jemand **vergisst**, fiel niemandem auf.

## Zwei Register — nicht verwechseln

* **Ansichts-Verzeichnis** — die `views.json` je Komponente. Die Quelle der
  Wahrheit, welche Flaeche eltern-facing ist: ein Eintrag mit
  `zielgruppe: "eltern"`. Das ist mechanisch eindeutig, weil es das einzige
  Feld im Repo ist, das Zielgruppe ueberhaupt klassifiziert
  (`tools/views_manifest.py:52`).
* **Mantel-Register** — `seiten/pwa_mantel.py:REGISTRY`. Das, was geprueft
  wird: die Baseline verlangt fuer jede Eltern-Seite einen vollen Mantel,
  hier steht, wer einen hat.

Kurz: **das Ansichts-Verzeichnis liefert die Liste, das Mantel-Register wird
dagegen geprueft.**

## Welcher Lader — das ist entscheidend

Es gibt zwei, und sie verhalten sich bei einer fehlerhaften Datei
**gegensaetzlich**:

* `tools.views_manifest.load()` ist streng — ein einziger defekter Eintrag
  laesst die **ganze Datei** fallen.
* Der im Betrieb genutzte Lader
  (`seiten.aggregator.lade_views_mit_per_view_resilienz`, SREG-3/DCOMP-3)
  ueberspringt **nur den kaputten Eintrag**.

Real relevant: `hoerspiel/views.json:42` traegt `zielgruppe: "erwachsen"` —
kein erlaubter Wert. Mit dem strengen Lader verschwaenden **alle**
Hoerspiel-Ansichten aus dieser Pruefung, inklusive `hoerspiel-eltern` — genau
der Flaeche, um die es geht. Der Test waere gruen und haette sein Ziel
verfehlt. Deshalb laeuft die Ableitung ueber die Ueberspringen-Semantik des
Betriebs-Laders und meldet jeden uebersprungenen Eintrag **sichtbar**
(Achse `lader`): ein kaputter Eintrag wird zum Befund, nicht zum blinden Fleck.

Warum die per-Manifest-Naht und nicht das ebenfalls oeffentliche
`aggregator.manifest_eintraege()`: letzteres ueberspringt Mini-App-Views, wenn
die Bot-ENV nicht gesetzt ist (SREG-14/SREG-13). Das waere ein
**umgebungsabhaengiger blinder Fleck** — `seiten/mini-app-uebersicht`
verschwaende im CI aus der Liste. Die per-Manifest-Ebene traegt genau die
Skip-Semantik des Betriebs, ohne die ENV-Abhaengigkeit.
`lade_views_mit_per_view_resilienz` ist dafuer mit #1822 als oeffentliche Naht
im Aggregator angelegt worden (MOD-5) — dieses Modul zieht an keinem
Unterstrich-Namen.

## Der Verbund-Schluessel

Der Kurzname einer Ansicht ist **nicht** der Schluessel im Mantel-Register
(`einstellungen`→`plan`, `regeln`→`wetter-regeln`, `anpassen`→`routine`).
Tragfaehig ist nur die Start-Adresse — und die auch nur normalisiert:

1. Query abschneiden, abschliessenden Schraegstrich strippen
   (`/seiten/plan/einstellungen/` und `/seiten/plan/einstellungen` sind zwei
   getrennte Flask-Routen, aber dieselbe Flaeche).
2. Die normalisierte Adresse gegen die `url_map` des `seiten`-Dienstes
   aufloesen und die **Regel** als Schluessel nehmen. Das haelt auch
   instanz-parametrische Flaechen zusammen:
   `hoerspiel/views.json` deklariert `/seiten/hoerspiel/mia/eltern`, das
   Mantel-Register bildet seine `start_url` aus der Instanzen-Registry
   (`_hoerspiel_primary_slug()`) — ohne `instanzen.json` steht dort `kind1`.
   Ein reiner String-Vergleich waere hier umgebungsabhaengig falsch; beide
   loesen aber auf dieselbe Regel `/seiten/hoerspiel/<kind_id>/eltern` auf.

## Ausnahmen sind Daten, nicht Verzweigungen

`AUSNAHMEN` unten ist eine Liste mit Begruendung je Eintrag — nie ein `if` im
Testcode. Das Repo unterscheidet dabei bewusst zwei Sorten (Vorbild:
`specs/platform/auth.md`, AUTH-11-Ausnahme-Tabelle vs. AUTH-6-Schuldstand):

* `ausnahme`   — eine **Entscheidung**. Braucht eine Begruendung.
* `schuldstand` — eine **offene Frage mit Aufloesungs-Trigger**. Braucht
  zusaetzlich das Ereignis, bei dem der Eintrag verschwindet.

Eine Ausnahme ohne Begruendung ist eine stille Entscheidung — deshalb prueft
`test_eltern_flaechen_vollstaendig.py` die Form der Liste selbst, und jeder
Schuldstand wird bei JEDEM Testlauf als Warnung ausgegeben.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass, field
from urllib.parse import urlsplit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools import views_manifest  # noqa: E402  (nach sys.path-Naht)

# ── Sorten und Achsen der Ausnahme-Liste ─────────────────────────────────────

SORTE_AUSNAHME = "ausnahme"        # eine Entscheidung
SORTE_SCHULDSTAND = "schuldstand"  # eine offene Frage mit Aufloesungs-Trigger

ACHSE_MANTEL = "mantel"        # Eltern-Ansicht ohne vollen Mantel-Eintrag
ACHSE_ANSCHLUSS = "anschluss"  # Komponente ohne Uebereinstimmungs-Pruefung
ACHSE_PFAD = "pfad"            # deklarierte Adresse liefert 404
ACHSE_LADER = "lader"          # Eintrag, den der Betriebs-Lader ueberspringt
# Gegenrichtung: Mantel-Schluessel OHNE eltern-facing Ansicht. #1822 klammert
# den Bau dieser Richtung ausdruecklich aus (er haette eine Produkt-Folge: die
# Heim-Shell erschiene in der Seiten-Uebersicht). Sie wird deshalb nur GEMESSEN
# und benannt, damit die bekannte Blindheit nicht stumm bleibt.
ACHSE_GEGENRICHTUNG = "gegenrichtung"

ACHSEN = (ACHSE_MANTEL, ACHSE_ANSCHLUSS, ACHSE_PFAD, ACHSE_LADER,
          ACHSE_GEGENRICHTUNG)


@dataclass(frozen=True)
class Ausnahme:
    """Ein Eintrag der Ausnahme-Liste — Daten mit Begruendung.

    `kennung` ist der Anker, gegen den ein Befund abgeglichen wird
    (`<komponente>/<slug>` bzw. `<komponente>` auf der Anschluss-Achse).
    `quelle` traegt die Datei:Zeile, an der der Sachverhalt nachlesbar ist.
    `trigger` ist bei `sorte=schuldstand` Pflicht: das Ereignis, bei dem der
    Eintrag verschwindet. Ohne Trigger waere ein Schuldstand ein stiller
    Dauerzustand.
    """

    kennung: str
    achse: str
    sorte: str
    begruendung: str
    quelle: str
    trigger: str = ""


AUSNAHMEN: tuple[Ausnahme, ...] = (
    # ── Achse `mantel` ───────────────────────────────────────────────────────
    Ausnahme(
        kennung="seiten/mini-app-uebersicht",
        achse=ACHSE_MANTEL,
        sorte=SORTE_AUSNAHME,
        begruendung=(
            "Telegram-Mini-App (SREG-14, `typ: \"mini-app\"`): sie laeuft im "
            "Telegram-WebView und wird nie auf einen Home-Screen installiert. "
            "Ihr Registry-Eintrag traegt deshalb bewusst NUR den "
            "Zwischenspeicher-Schluessel (`build_id_source_set`) und weder "
            "Manifest- noch Service-Worker-Daten — ein halber Mantel ist hier "
            "die Entscheidung, nicht das Versehen."
        ),
        quelle="seiten/pwa_mantel.py:421 (Kommentar 'Mini-Apps ohne installierbaren Mantel')",
    ),
    Ausnahme(
        kennung="seiten/uebersicht",
        achse=ACHSE_MANTEL,
        sorte=SORTE_SCHULDSTAND,
        begruendung=(
            "Die Seiten-Uebersicht ist als eltern-facing deklariert, hat aber "
            "als einzige der drei Plattform-Ansichten KEINEN Mantel-Eintrag — "
            "nach der Baseline ein echter Verstoss, kein Ausnahmefall. Die "
            "Auth-Spec deckt sie nur auf der Auth-Achse ab (Trigger 2026-08-12 "
            "gefeuert, seither AUTH-7b DUAL gegatet, #1832/#1863); die "
            "Mantel-Achse ist dort gar nicht beruehrt. Deshalb Schuldstand "
            "statt Ausnahme: eine Ausnahme waere eine Entscheidung, dies ist "
            "eine offene Frage."
        ),
        quelle="seiten/views.json:4 (slug 'uebersicht', zielgruppe 'eltern' auf :16)",
        trigger=(
            "Eigenes Bau-Ticket entscheidet: entweder bekommt die Uebersicht "
            "einen vollen Mantel-Eintrag in seiten/pwa_mantel.py:REGISTRY, "
            "oder sie wird ausdruecklich als nicht-installierbare Flaeche "
            "ratifiziert. Beides loescht diese Zeile."
        ),
    ),
    # ── Achse `anschluss` ────────────────────────────────────────────────────
    Ausnahme(
        kennung="kibuddy",
        achse=ACHSE_ANSCHLUSS,
        sorte=SORTE_AUSNAHME,
        begruendung=(
            "#1822 nimmt kibuddy ausdruecklich aus: die Komponente fuehrt nur "
            "eine Kind-Ansicht, und diese Baseline zielt auf Eltern-Flaechen. "
            "Nachgemessen kommt hinzu, dass unter /display/kibuddy/ drei "
            "literale PWA-Asset-Routen liegen "
            "(static/manifest.webmanifest, static/icons/icon-192.png, "
            "static/icons/icon-512.png), die die Uebereinstimmungs-Pruefung "
            "als 'Route ohne Manifest-Eintrag' liest — ein Anschluss braeuchte "
            "drei Asset-Ausnahmen. Machbar, aber eine eigene Entscheidung."
        ),
        quelle="kibuddy/views.json:16 (einziger Eintrag, zielgruppe 'kind')",
    ),
    Ausnahme(
        kennung="seiten",
        achse=ACHSE_ANSCHLUSS,
        sorte=SORTE_SCHULDSTAND,
        begruendung=(
            "ACHTUNG, GROESSE DER LUECKE: dies ist NICHT 'eine Komponente passt "
            "nicht ins Schema', sondern die groesste verbleibende Blindheit "
            "dieses Guards. Der Praefix /seiten/… hat im GANZEN Repo keine "
            "Route→Manifest-Richtung: die Uebereinstimmungs-Pruefung ist auf "
            "/display/<slug>/ gebaut (conventions/buddies.md:97), und "
            "seiten/tests/test_views_manifest_eigentest.py:88 prueft 'Route "
            "ohne Eintrag' nur fuer /api/v1/seiten. Unter /seiten/… liegen aber "
            "essen/einkauf, plan/einstellungen, routine/anpassen, wetter/regeln "
            "und hoerspiel/<kind_id>/eltern — FUENF der acht abgeleiteten "
            "Eltern-Flaechen und saemtliche PWA-Flaechen. Nachgemessen: eine zur "
            "Laufzeit in seiten.main.app registrierte Eltern-Route ohne jeden "
            "views.json-Eintrag laesst ALLE Achsen dieses Guards leer. Das ist "
            "genau die Auslassungs-Klasse aus der Ticket-Praemisse ('nichts "
            "zwingt eine neue Komponente zu einem Eintrag') und der "
            "wahrscheinlichste reale Fall: jemand baut die Seite und vergisst "
            "das Manifest. Der /display/seiten/-Anschluss selbst liefe "
            "zusaetzlich leere Menge gegen leere Menge — gruen ohne "
            "Aussagewert; deshalb hier gefuehrt statt scheinbar angeschlossen."
        ),
        quelle=(
            "seiten/views.json:5 (erster Pfad, /api/v1/seiten/uebersicht); "
            "Deckungsluecke: conventions/buddies.md:97 + "
            "seiten/tests/test_views_manifest_eigentest.py:88"
        ),
        trigger=(
            "#1890 baut die Route→Manifest-Richtung fuer den Praefix /seiten/… "
            "(jede eltern-facing Route im seiten-Dienst braucht einen Eintrag "
            "oder eine begruendete Ausnahme). Mit #1890 faellt diese Zeile weg. "
            "Bewusst NICHT in #1822 gebaut: das ist eine Scope-Erweiterung ueber "
            "die Abnahme dieses Tickets hinaus."
        ),
    ),
    # ── Achse `gegenrichtung` ────────────────────────────────────────────────
    Ausnahme(
        kennung="shell",
        achse=ACHSE_GEGENRICHTUNG,
        sorte=SORTE_SCHULDSTAND,
        begruendung=(
            "Die Heim-Shell hat einen VOLLEN Mantel, aber keinen Eintrag im "
            "Ansichts-Verzeichnis — sie traegt nirgends ein zielgruppe-Feld und "
            "ist fuer die Ableitung dieses Guards strukturell unsichtbar. Bis "
            "#1822 fing die Set-Gleichheit in seiten/tests/test_pwa_mantel.py "
            "wenigstens das HINZUFUEGEN eines Registry-Schluessels; mit der "
            "Drehung auf Pflicht-Enthaltensein (AC5) ist diese Fang-Wirkung "
            "weg: ein Schluessel ohne zugehoerige Flaeche bricht nichts mehr. "
            "Das ist ein bewusster Tausch — die alte Gleichheit fing das "
            "Vergessen ueberhaupt nicht — aber es ist ein Verlust, und er steht "
            "hier, statt nur im Docstring."
        ),
        quelle="seiten/pwa_mantel.py:403 (REGISTRY['shell'], start_url /shell/<panel_id>)",
        trigger=(
            "#1822 klammert die Heim-Shell ausdruecklich aus: die Gegenrichtung "
            "zu schliessen waere technisch billig, haette aber eine "
            "Produkt-Folge — die Shell erschiene damit in der "
            "Seiten-Uebersicht. Das ist eine Entscheidung ueber die "
            "Ziel-Default-Flaeche, kein Bau-Schritt. Sobald das eigene "
            "Heim-Shell-Ticket entschieden ist, faellt diese Zeile weg."
        ),
    ),
    Ausnahme(
        kennung="hoerspiel-player",
        achse=ACHSE_GEGENRICHTUNG,
        sorte=SORTE_SCHULDSTAND,
        begruendung=(
            "Der Player traegt einen vollen Mantel und hat auch einen Eintrag "
            "im Ansichts-Verzeichnis (seiten/views.json:48) — aber mit "
            "zielgruppe 'kind'. Die Pflicht-Ableitung dieses Guards zieht nur "
            "eltern-facing Ansichten, also faellt er aus der Menge und die "
            "Gegenrichtung findet fuer seinen Registry-Schluessel keine "
            "Flaeche. Kein Fehler, aber der zweite Fall derselben Blindheit: "
            "installierbare Kind-Flaechen sind von dieser Baseline gar nicht "
            "erfasst."
        ),
        quelle="seiten/pwa_mantel.py:492 (REGISTRY['hoerspiel-player']) ⇔ seiten/views.json:48",
        trigger=(
            "Sobald entschieden ist, ob die Baseline auch installierbare "
            "Kind-Flaechen umfasst (gleiches Ticket wie der Heim-Shell-Fall), "
            "wandert der Player entweder in die Pflicht-Menge oder in eine "
            "ratifizierte Ausnahme — beides loescht diese Zeile."
        ),
    ),
    # ── Achse `lader` ────────────────────────────────────────────────────────
    Ausnahme(
        kennung="hoerspiel/alben-emil",
        achse=ACHSE_LADER,
        sorte=SORTE_SCHULDSTAND,
        begruendung=(
            "Der Eintrag traegt `zielgruppe: \"erwachsen\"`; erlaubt sind nur "
            "'kind' und 'eltern' (tools/views_manifest.py:52). Der "
            "Betriebs-Lader ueberspringt genau diesen einen Eintrag, der "
            "strenge Lader liesse die GANZE Datei fallen — und damit auch "
            "`hoerspiel-eltern`, die Flaeche, die #1822 schliesst. Der Test "
            "meldet den Fund, er repariert ihn nicht: Registry-Daten sind ein "
            "eigener Vorgang."
        ),
        quelle="hoerspiel/views.json:42",
        trigger=(
            "Sobald hoerspiel/views.json:42 auf einen erlaubten Wert korrigiert "
            "ist ODER 'erwachsen' in tools/views_manifest.py:52 "
            "(ERLAUBTE_ZIELGRUPPEN) aufgenommen wird, laedt der Eintrag sauber "
            "und diese Zeile faellt weg."
        ),
    ),
    # ── Achse `pfad` ─────────────────────────────────────────────────────────
    Ausnahme(
        kennung="plan/einstellungen:pwa.manifest",
        achse=ACHSE_PFAD,
        sorte=SORTE_SCHULDSTAND,
        begruendung=(
            "Live gemessen: der Hauptpfad /seiten/plan/einstellungen ist in "
            "Ordnung (200), aber das PWA-Unterfeld zeigt auf "
            "/seiten/static/plan/manifest.json — 404. Ausgeliefert wird das "
            "Manifest unter /seiten/plan/einstellungen/manifest.json "
            "(seiten/main.py:1013). Der Fehler sitzt im Unterfeld, nicht im "
            "Hauptpfad — genau die Sorte Auslassung, die bisher niemandem "
            "auffiel. Der Test meldet ihn; die Registry-Datei zu korrigieren "
            "ist ein eigener Vorgang."
        ),
        quelle="plan/views.json:26",
        trigger=(
            "Sobald plan/views.json:26 auf /seiten/plan/einstellungen/manifest.json "
            "zeigt, antwortet die Adresse mit 200 und diese Zeile faellt weg "
            "(test_ausnahmen_sind_noch_real erzwingt das)."
        ),
    ),
    Ausnahme(
        kennung="plan/einstellungen:pwa.service_worker",
        achse=ACHSE_PFAD,
        sorte=SORTE_SCHULDSTAND,
        begruendung=(
            "Zweites PWA-Unterfeld derselben Ansicht: /seiten/static/plan/sw.js "
            "— 404. Ausgeliefert wird der Service-Worker unter "
            "/seiten/plan/einstellungen/sw.js (seiten/main.py:985). Eigene "
            "Zeile statt Sammel-Eintrag, damit das Verschwinden des einen "
            "Befunds nicht den anderen mit abraeumt."
        ),
        quelle="plan/views.json:28",
        trigger=(
            "Sobald plan/views.json:28 auf /seiten/plan/einstellungen/sw.js "
            "zeigt, antwortet die Adresse mit 200 und diese Zeile faellt weg."
        ),
    ),
)


def ausnahme_fuer(achse: str, kennung: str) -> Ausnahme | None:
    """Der Ausnahme-Eintrag zu einem Befund, oder None (= der Befund macht rot)."""
    for eintrag in AUSNAHMEN:
        if eintrag.achse == achse and eintrag.kennung == kennung:
            return eintrag
    return None


# ── Der Baum-Lauf ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ElternAnsicht:
    """Eine Ansicht mit `zielgruppe: "eltern"` aus einem Ansichts-Verzeichnis."""

    komponente: str
    slug: str
    pfad: str
    pwa: dict = field(default_factory=dict)
    quelle: str = ""

    @property
    def kennung(self) -> str:
        return "%s/%s" % (self.komponente, self.slug)


@dataclass(frozen=True)
class Uebersprungen:
    """Ein Eintrag, den der Betriebs-Lader hat fallen lassen — ein Befund."""

    komponente: str
    slug: str
    grund: str
    quelle: str

    @property
    def kennung(self) -> str:
        return "%s/%s" % (self.komponente, self.slug)


@dataclass(frozen=True)
class Durchlauf:
    ansichten: tuple[ElternAnsicht, ...]
    uebersprungen: tuple[Uebersprungen, ...]
    kaputte_manifeste: tuple[str, ...]


def _roh_views(pfad: str) -> list:
    try:
        with open(pfad, encoding="utf-8") as fh:
            daten = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(daten, dict):
        return []
    roh = daten.get("views")
    return roh if isinstance(roh, list) else []


def _uebersprungene(pfad: str, komponente: str, views: list, quelle: str):
    """Die Roh-Eintraege, die der Betriebs-Lader NICHT durchgelassen hat.

    Abgeleitet aus der Differenz Roh-Liste ⇔ gueltige Liste; die Begruendung
    kommt aus `views_manifest.validate_eintrag()` — der EINEN Stelle fuer
    Manifest-Validierung (CLAUDE.md §6). Kein Nachbau des Schemas hier.
    """
    gueltige = {v.get("slug") for v in views}
    raus = []
    for roh in _roh_views(pfad):
        if not isinstance(roh, dict):
            raus.append(Uebersprungen(komponente, "<kein Objekt>",
                                      "Eintrag ist kein JSON-Objekt", quelle))
            continue
        if roh.get("slug") in gueltige:
            continue
        try:
            views_manifest.validate_eintrag(roh)
            grund = "vom Betriebs-Lader verworfen (kein Schema-Fehler — z. B. Doppel-Slug)"
        except views_manifest.ManifestError as fehler:
            grund = str(fehler)
        raus.append(Uebersprungen(komponente, str(roh.get("slug")), grund, quelle))
    return raus


def durchlauf(root: str = REPO_ROOT) -> Durchlauf:
    """Laeuft den Baum ab und liefert alle eltern-facing Ansichten.

    Discovery ist die des Betriebs (`aggregator.discover_manifests`) — sie
    globbt `<root>/*/views.json` und `<root>/controller/*/views.json`. Damit
    ist `tools/render-gate/views.json` gar nicht erfasst: es liegt eine Ebene
    tiefer und traegt nicht die uebliche Dateiform. Es braucht deshalb keinen
    Ausnahme-Eintrag (und wird mit RAT-37 ohnehin abgerissen, Bau #1882).
    """
    aggregator = importlib.import_module("seiten.aggregator")
    ansichten: list[ElternAnsicht] = []
    uebersprungen: list[Uebersprungen] = []
    kaputte: list[str] = []
    for komponente, _ist_controller, pfad in aggregator.discover_manifests(root):
        quelle = os.path.relpath(pfad, root)
        views, ganz_kaputt = aggregator.lade_views_mit_per_view_resilienz(pfad, komponente)
        if ganz_kaputt:
            kaputte.append(quelle)
            continue
        uebersprungen.extend(_uebersprungene(pfad, komponente, views, quelle))
        for view in views:
            if view.get("zielgruppe") != "eltern":
                continue
            ansichten.append(ElternAnsicht(
                komponente=komponente,
                slug=view["slug"],
                pfad=view["pfad"],
                pwa=dict(view.get("pwa") or {}),
                quelle=quelle,
            ))
    return Durchlauf(tuple(ansichten), tuple(uebersprungen), tuple(kaputte))


# ── Der Verbund-Schluessel ───────────────────────────────────────────────────

def _seiten_app():
    return importlib.import_module("seiten.main").app


def kanonische_regel(pfad: str, app=None) -> str | None:
    """Die Flask-Regel, die `pfad` bedient — der tragfaehige Verbund-Schluessel.

    Query weg, abschliessender Schraegstrich weg, dann gegen die `url_map`
    aufloesen. Werkzeugs Slash-Redirect wird verfolgt (Routen wie
    `/api/v1/seiten/connector/` existieren nur MIT Schraegstrich). Liefert
    None, wenn die Adresse in der App gar keine Route hat — das ist ein
    Befund, kein stiller Skip.
    """
    from werkzeug.exceptions import MethodNotAllowed, NotFound
    from werkzeug.routing.exceptions import RequestRedirect

    adapter = (app or _seiten_app()).url_map.bind("xbuddy.invalid")
    ziel = pfad.split("?")[0].rstrip("/") or "/"
    for _ in range(4):  # Slash-Redirects sind endlich; die Schranke ist Notaus.
        try:
            regel, _kwargs = adapter.match(ziel, return_rule=True)
            return regel.rule
        except RequestRedirect as umleitung:
            ziel = urlsplit(umleitung.new_url).path
        except (NotFound, MethodNotAllowed):
            return None
    return None


def ist_voller_mantel(cfg) -> bool:
    """Voller Mantel, nicht halb (PWAM-2/PWAM-3).

    Ein Eintrag, der nur den Zwischenspeicher-Schluessel (`build_id_source_set`)
    setzt, ist laut Baseline ausdruecklich KEIN Mantel: ohne Manifest-Daten
    und ohne Service-Worker-Route ist die Flaeche nicht installierbar.
    """
    return all((
        cfg.name, cfg.start_url, cfg.display, cfg.icons,
        cfg.html_cache_mode, cfg.sw_script_route, cfg.sw_scope,
    ))


def mantel_index() -> dict:
    """Verbund-Schluessel (Flask-Regel) → Mantel-Schluessel mit VOLLEM Mantel."""
    pwa_mantel = importlib.import_module("seiten.pwa_mantel")
    app = _seiten_app()
    index: dict[str, list[str]] = {}
    for name, cfg in pwa_mantel.REGISTRY.items():
        if not cfg.start_url or not ist_voller_mantel(cfg):
            continue
        regel = kanonische_regel(cfg.start_url, app) or cfg.start_url.rstrip("/")
        index.setdefault(regel, []).append(name)
    return index


# ── Achse `mantel` ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Befund:
    achse: str
    kennung: str
    text: str

    @property
    def ausnahme(self) -> Ausnahme | None:
        return ausnahme_fuer(self.achse, self.kennung)


def mantel_befunde(root: str = REPO_ROOT) -> list[Befund]:
    """Jede eltern-facing Ansicht OHNE vollen Mantel-Eintrag — dokumentiert oder nicht."""
    app = _seiten_app()
    index = mantel_index()
    befunde = []
    for ansicht in durchlauf(root).ansichten:
        regel = kanonische_regel(ansicht.pfad, app) or ansicht.pfad.rstrip("/")
        if index.get(regel):
            continue
        befunde.append(Befund(
            ACHSE_MANTEL, ansicht.kennung,
            "%s (%s) ist eltern-facing, hat aber keinen VOLLEN Mantel-Eintrag "
            "in seiten/pwa_mantel.py:REGISTRY — Verbund-Schluessel %r "
            "(deklariert in %s)"
            % (ansicht.kennung, ansicht.pfad, regel, ansicht.quelle),
        ))
    return befunde


def mantel_luecken(root: str = REPO_ROOT) -> list[Befund]:
    """Nur die UNdokumentierten Mantel-Befunde — das ist, was rot macht."""
    return [b for b in mantel_befunde(root) if b.ausnahme is None]


# ── Achse `gegenrichtung` ────────────────────────────────────────────────────

def gegenrichtung_befunde(root: str = REPO_ROOT) -> list[Befund]:
    """Mantel-Schluessel, zu denen KEINE eltern-facing Ansicht gehoert.

    Diese Richtung wird **gemessen und benannt, nicht durchgesetzt**: #1822
    klammert sie ausdruecklich aus, weil ihre Schliessung eine Produkt-Folge
    haette (die Heim-Shell erschiene in der Seiten-Uebersicht) — das ist eine
    Entscheidung ueber die Ziel-Default-Flaeche, kein Bau-Schritt.

    Sie steht trotzdem hier, weil die Drehung von Set-Gleichheit auf
    Pflicht-Enthaltensein (AC5) eine Fang-Wirkung aufgibt: vorher brach ein
    NEUER Registry-Schluessel die Gleichheit, jetzt nicht mehr. Der Verlust
    gehoert benannt, nicht in einen Docstring versteckt.

    Schluessel OHNE `start_url` bleiben hier aussen vor — sie sind auf gar
    keine Flaeche abbildbar und werden auf der Mantel-Achse gefuehrt
    (`seiten/mini-app-uebersicht`); ein zweiter Eintrag fuer denselben
    Sachverhalt waere Rauschen.
    """
    pwa_mantel = importlib.import_module("seiten.pwa_mantel")
    app = _seiten_app()
    eltern_regeln = {
        kanonische_regel(a.pfad, app) or a.pfad.rstrip("/")
        for a in durchlauf(root).ansichten
    }
    befunde = []
    for name, cfg in pwa_mantel.REGISTRY.items():
        if not cfg.start_url:
            continue
        regel = kanonische_regel(cfg.start_url, app) or cfg.start_url.rstrip("/")
        if regel in eltern_regeln:
            continue
        befunde.append(Befund(
            ACHSE_GEGENRICHTUNG, name,
            "Mantel-Schluessel %r (start_url %s, Regel %r) gehoert zu KEINER "
            "eltern-facing Ansicht — er kann angelegt oder veraendert werden, "
            "ohne dass eine Pruefung anschlaegt"
            % (name, cfg.start_url, regel),
        ))
    return befunde


def gegenrichtung_luecken(root: str = REPO_ROOT) -> list[Befund]:
    """Undokumentierte Gegenrichtungs-Befunde — die Benennungs-Pflicht."""
    return [b for b in gegenrichtung_befunde(root) if b.ausnahme is None]


# ── Achse `lader` ────────────────────────────────────────────────────────────

def lader_befunde(root: str = REPO_ROOT) -> list[Befund]:
    """Jeder Eintrag, den der Betriebs-Lader uebersprungen hat."""
    return [
        Befund(ACHSE_LADER, eintrag.kennung,
               "%s (%s): %s" % (eintrag.kennung, eintrag.quelle, eintrag.grund))
        for eintrag in durchlauf(root).uebersprungen
    ]


# ── Achse `pfad` ─────────────────────────────────────────────────────────────

# Welcher Dienst liefert welchen Adressraum aus. Daten, damit eine kuenftige
# Eltern-Flaeche ausserhalb des seiten-Dienstes hier eingetragen wird, statt
# still durchzurutschen: eine Adresse ohne passenden Praefix wird gemeldet.
DIENST_FUER_PRAEFIX: tuple[tuple[str, str], ...] = (
    ("/api/v1/seiten/", "seiten.main"),
    ("/seiten/", "seiten.main"),
)

# Welche Felder eines Eintrags eine Adresse deklarieren.
PWA_FELDER = ("manifest", "start_url", "service_worker")


def _client_fuer(modulname: str):
    modul = importlib.import_module(modulname)
    modul.configure(root=REPO_ROOT, inventar_path=None,
                    bot_token="testtoken",  # Test-Modus (MAD-7), kein echtes Geheimnis
                    init_data_config={"max_age_seconds": 86400})
    modul.app.config["TESTING"] = True
    return modul.app.test_client()


def _dienst_fuer(pfad: str) -> str | None:
    for praefix, modul in DIENST_FUER_PRAEFIX:
        if pfad.startswith(praefix):
            return modul
    return None


def pfad_befunde(root: str = REPO_ROOT) -> list[Befund]:
    """Deklarierte Adressen, die 404 liefern (oder gar keinen Dienst haben).

    Gemessen wird ueber den Flask-Test-Client des ausliefernden Dienstes —
    kein Live-HTTP, kein laufender Prozess noetig, also auch kein stilles
    Gruen, wenn im CI nichts laeuft. Auth-Antworten (401/403) zaehlen NICHT
    als Befund: die Adresse existiert dann ja, sie ist nur gegatet.
    """
    clients: dict[str, object] = {}
    befunde = []
    for ansicht in durchlauf(root).ansichten:
        adressen = [("pfad", ansicht.pfad)]
        adressen += [(feld, ansicht.pwa[feld]) for feld in PWA_FELDER
                     if ansicht.pwa.get(feld)]
        for feld, adresse in adressen:
            kennung = "%s:%s" % (ansicht.kennung,
                                 "pfad" if feld == "pfad" else "pwa.%s" % feld)
            modulname = _dienst_fuer(adresse.split("?")[0])
            if modulname is None:
                befunde.append(Befund(
                    ACHSE_PFAD, kennung,
                    "%s zeigt auf %s — kein Dienst in DIENST_FUER_PRAEFIX "
                    "zustaendig; Erreichbarkeit ungeprueft (%s)"
                    % (kennung, adresse, ansicht.quelle)))
                continue
            if modulname not in clients:
                clients[modulname] = _client_fuer(modulname)
            antwort = clients[modulname].get(adresse.split("?")[0])
            if antwort.status_code == 404:
                befunde.append(Befund(
                    ACHSE_PFAD, kennung,
                    "%s zeigt auf %s — 404 (deklariert in %s)"
                    % (kennung, adresse, ansicht.quelle)))
    return befunde


# ── Achse `anschluss` ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Anschluss:
    """Eine Komponente, die an die Uebereinstimmungs-Pruefung angeschlossen ist."""

    komponente: str
    modul: str
    ausgenommene_routen: tuple[str, ...] = ()
    begruendung: str = ""


ANSCHLUESSE: tuple[Anschluss, ...] = (
    Anschluss("essen", "essen.main", begruendung=(
        "#1822: essen war eine der zwei real offenen Komponenten. "
        "`/display/essen/wunsch?fit=viewport` traegt einen Query-Anker; der ist "
        "nach SREG-1 keine eigene Route und wird vor dem Abgleich abgeschnitten."
    )),
    Anschluss("hoerspiel", "hoerspiel.main",
              ausgenommene_routen=("/display/hoerspiel/static/manifest.webmanifest",),
              begruendung=(
                  "#1822: hoerspiel war die zweite real offene Komponente. Die "
                  "Alben-Ansichten laufen ueber die instanz-parametrische Route "
                  "/display/hoerspiel/<kind_id>/alben — deshalb loest diese "
                  "Pruefung auf die Regel auf, statt Pfad-Strings zu vergleichen. "
                  "static/manifest.webmanifest ist eine PWA-Asset-Route (#1858), "
                  "keine View, und deshalb ausgenommen. "
                  "EINSCHRAENKUNG, offengelegt: Richtung B (Route→Eintrag) ist "
                  "hier heute LEER. kanonische_display_pfade verwirft "
                  "parametrische Regeln (tools/views_manifest.py:308), und nach "
                  "Abzug der Asset-Route bleibt fuer hoerspiel keine einzige "
                  "literale /display/-Route uebrig — gemessen 0, waehrend essen, "
                  "photo, plan, routine und wetter je 1 haben. Der Anschluss "
                  "wirkt damit Richtung-A-only: er faengt einen Eintrag ohne "
                  "Route, aber keine Route ohne Eintrag. Das ist derselbe "
                  "Massstab, mit dem die seiten-Zeile oben als Schuldstand "
                  "gefuehrt wird; hier ist die Fang-Wirkung nur halb, nicht "
                  "null, und die Alben-Routen sind ueber Richtung A gedeckt. "
                  "Die fehlende Haelfte gehoert zur selben Luecke wie #1890."
              )),
    Anschluss("photo", "photo.main", begruendung="Bestand: photo/tests/test_views_photo.py:57."),
    Anschluss("plan", "plan.main", begruendung="Bestand: plan/tests/test_views_plan.py:50."),
    Anschluss("routine", "routine.main", begruendung=(
        "Bestand-Eigentest routine/tests/test_views_routine.py:61 traegt seit "
        "dem Track-A-Folgebug ein @pytest.mark.skip — er lief also NICHT. Der "
        "Skip-Grund (Mini-App-Pfad /seiten/routine/anpassen) ist seit #1689 "
        "ueberholt: assert_routes_match filtert Fremd-Praefixe selbst "
        "(tools/views_manifest.py:342). Hier laeuft der Abgleich wieder."
    )),
    Anschluss("wetter", "wetter.main", begruendung="Bestand: wetter/tests/test_views_wetter.py:71."),
)


def anschluss_fuer(komponente: str) -> Anschluss | None:
    for eintrag in ANSCHLUESSE:
        if eintrag.komponente == komponente:
            return eintrag
    return None


def anschluss_luecken(root: str = REPO_ROOT) -> list[Befund]:
    """Komponenten mit views.json, die WEDER angeschlossen sind NOCH eine Ausnahme tragen."""
    aggregator = importlib.import_module("seiten.aggregator")
    luecken = []
    for komponente, _ist_controller, pfad in aggregator.discover_manifests(root):
        if anschluss_fuer(komponente) is not None:
            continue
        befund = Befund(
            ACHSE_ANSCHLUSS, komponente,
            "%s traegt ein Ansichts-Verzeichnis (%s), ist aber weder an die "
            "Uebereinstimmungs-Pruefung angeschlossen noch mit Begruendung "
            "ausgenommen" % (komponente, os.path.relpath(pfad, root)))
        if befund.ausnahme is None:
            luecken.append(befund)
    return luecken


def uebereinstimmung_pruefen(anschluss: Anschluss, root: str = REPO_ROOT) -> list[str]:
    """Der Abgleich Ansichts-Verzeichnis ⇔ echte Flask-Routen, beide Richtungen.

    Baut auf `views_manifest.kanonische_display_pfade()` auf — demselben
    Routen-Aufzaehler, den `assert_routes_match` benutzt. Der Unterschied:
    statt Pfad-Strings gleichzusetzen, wird jede Seite auf die **Flask-Regel**
    aufgeloest. Nur so laesst sich hoerspiel ueberhaupt anschliessen, dessen
    Alben-Ansichten unter der instanz-parametrischen Route
    `/display/hoerspiel/<kind_id>/alben` liegen — Set-Gleichheit auf Strings
    kann das nicht.
    """
    aggregator = importlib.import_module("seiten.aggregator")
    app = importlib.import_module(anschluss.modul).app
    slug = anschluss.komponente
    praefix = "/display/%s/" % slug
    pfad = os.path.join(root, slug, "views.json")
    views, _ganz_kaputt = aggregator.lade_views_mit_per_view_resilienz(pfad, slug)

    abweichungen = []
    regeln_im_verzeichnis = set()
    # Richtung A: jeder deklarierte /display/<slug>/-Eintrag hat eine echte Route.
    for view in views:
        adresse = view["pfad"].split("?")[0]
        if not adresse.startswith(praefix):
            continue
        regel = kanonische_regel(adresse, app)
        if regel is None:
            abweichungen.append(
                "Eintrag ohne Route: %s (slug %r)" % (view["pfad"], view["slug"]))
        else:
            regeln_im_verzeichnis.add(regel)

    # Richtung B: jede kanonische Route hat einen Eintrag, der auf sie zeigt.
    for route in sorted(views_manifest.kanonische_display_pfade(
            app, slug, anschluss.ausgenommene_routen)):
        if kanonische_regel(route, app) not in regeln_im_verzeichnis:
            abweichungen.append("Route ohne Eintrag: %s" % route)
    return abweichungen


# ── Fuer seiten/tests/test_pwa_mantel.py (AC5) ───────────────────────────────

def fehlende_registrierungen(root: str = REPO_ROOT) -> list[str]:
    """Die Pflicht-Flaechen, die im Mantel-Register FEHLEN (abzueglich Ausnahmen).

    Das ist die Drehung von Set-Gleichheit auf Pflicht-Enthaltensein: die
    Pflicht-Menge wird aus den Ansichts-Verzeichnissen ABGELEITET, nicht als
    Literal eingefroren. Ein Literal-Set kann per Konstruktion nur
    Hinzufuegen fangen.
    """
    return [b.text for b in mantel_luecken(root)]
