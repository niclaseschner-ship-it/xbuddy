"""AUTH-11 — Rueck-Verriegelung ueber die Flask-URL-Map (#1805, Abschluss-Stueck).

AUTH-9 prueft **vorwaerts**: traegt jede in der Spec *gelistete* Route ihren
Decorator? Eine Route, die in keiner Liste steht, ist fuer AUTH-9 unsichtbar.
AUTH-11 (`specs/platform/auth.md:833`) dreht die Richtung um: Ausgangspunkt ist
der **Code** — jede Regel jeder `app.url_map` muss sich erklaeren.

Genau **eine** von vier Erklaerungen muss je Regel greifen:

1. **Gegatet** — das `view_function` traegt den AUTH-11-Marker
   (`tools.initdata.auth_gate.AUTH_MARKER`, gesetzt von den drei
   Decorator-Factories und von `markiere_auth_klasse` fuer Inline-Gates).
2. **AUTH-11-Ausnahme** — die Route steht namentlich in der Tabelle
   „Zulaessige Ausnahmen — abschliessend" (`auth.md:869`).
3. **AUTH-6-Schuldstand** — die Route steht in einem der Fence-Bloecke des
   AUTH-6-Abschnitts mit einem `(Trigger: …)` (`auth.md:571`).
4. **`/healthz` bzw. `/version`** — die eine Sammelzeile der AUTH-11-Tabelle
   („je Service"); sie enumeriert bewusst nicht pro Dienst.

Alles andere ist rot.

**Warum ein Marker und keine `__wrapped__`-Heuristik.** Der frueher benutzte
Nachweis „das `view_function` hat ein `__wrapped__`" schlaegt bei JEDEM
`functools.wraps`-Decorator an — auch bei einem Caching- oder Logging-Wrapper.
Eine ungegatete Route mit irgendeinem anderen Decorator waere damit stumm
gruen. Der explizite Marker (`auth_gate.AUTH_MARKER`) ist der Unterschied
zwischen Heuristik und Verriegelung. Zum Zeitpunkt des Umbaus deckten sich
beide Messungen bis auf die zwei Inline-Gate-Routen des Hoerspiel-Players
(44 → 42 ungegatete `seiten`-Regeln) — die Heuristik hatte hier kein
Falsch-Positiv, aber auch keine Garantie.

**Die Listen werden GEPARST, nicht abgeschrieben** (AUTH-11:926: „Die Liste
erweitert man nur per Spec-Aenderung, nie im Test-Code"). Es gibt in dieser
Datei keine handgepflegte Ausnahmeliste. Zwei Fallstricke, die der Parser
kennen muss und die `test_parser_*` unten festnageln:

  - Eine Tabellenzeile fuehrt **zwei** Routen komma-getrennt
    (`/healthz` + `/version`; `/display/_shared/design/…` + `…/icons/…`).
  - Eine Zeile ist als `**[UEBERHOLT …]**` markiert und ist **keine** Ausnahme
    mehr, obwohl sie syntaktisch in der Tabelle steht
    (`/shell/<panel_id>/sw.js` — inzwischen hart gegatet).

**Sammel-Eintraege zaehlen nicht** (AUTH-11:844). Deshalb vergleicht der Test
Regel-Strings **literal**; ein Eintrag mit `*` (`/api/v1/panels/*`) deckt
keine konkrete Regel. Solche Eintraege filtert der AUTH-6-Parser sichtbar aus.

Lauf: python3 -m pytest tests/test_auth11_url_map_coverage.py -q
"""

from __future__ import annotations

import importlib
import os
import pathlib
import re
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.initdata import auth_gate  # noqa: E402  # isort:skip

REPO_ROOT = pathlib.Path(_REPO_ROOT)
AUTH_MD = REPO_ROOT / "specs" / "platform" / "auth.md"

# Die zehn Flask-Apps des Repos (Modulpfad je Service). Kein Service darf hier
# fehlen — `test_registry_deckt_jede_flask_app_des_repos` haelt die Liste
# gegen den Repo-Zustand, statt sie auf Zuruf zu pflegen.
SERVICE_MODULE = {
    "essen": "essen.main",
    "familie": "familie.main",
    "hoerspiel": "hoerspiel.main",
    "kibuddy": "kibuddy.main",
    "panel": "panel.main",
    "photo": "photo.main",
    "plan": "plan.main",
    "routine": "routine.main",
    "seiten": "seiten.main",
    "wetter": "wetter.main",
}


def _app(service: str):
    """Das ECHTE Flask-App-Objekt des Service — keine Nachbildung.

    Bewusst LAZY (Zugriff erst im Test, nicht beim Import dieser Datei):
    mehrere Suiten des Repos machen `importlib.reload` auf ihr `main`-Modul
    (ENV-Naht-Tests, z. B. `routine/tests/test_auth11_routine.py`). Eine beim
    Sammeln festgehaltene App-Referenz waere danach die alte Instanz.
    """
    return importlib.import_module(SERVICE_MODULE[service]).app


# ---------------------------------------------------------------------------
# Parser: die zwei Spec-Strukturen aus specs/platform/auth.md (AC2)
# ---------------------------------------------------------------------------

# Backtick-Route in einer Tabellenzelle: `/pfad/<param>`.
_BACKTICK_ROUTE = re.compile(r"`(/[^`]*)`")

# AUTH-6-Fence-Zeile: "<pfad>   (Trigger: …)". Ohne Trigger kein Schuldstand
# (auth.md:577 „Ohne Trigger gehoert der Eintrag nicht in AUTH-6").
_AUTH6_FENCE_LINE = re.compile(r"^(/\S+)\s+\(Trigger:")


def _abschnitt(ueberschrift: str) -> str:
    """Schneidet den Abschnitt ab `ueberschrift` bis zur naechsten Ueberschrift."""
    text = AUTH_MD.read_text(encoding="utf-8")
    start = text.index(ueberschrift)
    rest = text[start + len(ueberschrift):]
    treffer = re.search(r"\n#{2,3} ", rest)
    return rest[: treffer.start()] if treffer else rest


def auth11_ausnahmen() -> set[str]:
    """Die Routen der AUTH-11-Tabelle „Zulaessige Ausnahmen — abschliessend".

    Gelesen wird die Markdown-Tabelle im `### AUTH-11`-Abschnitt: Spalte 1
    liefert die Routen (mehrere je Zeile moeglich, komma-getrennt in
    Backticks), Spalte 2 den Grund. Eine Zeile, deren Grund mit `[UEBERHOLT`
    markiert ist, ist **keine** Ausnahme mehr und wird verworfen — sonst
    erklaerte die Tabelle eine Route, die die Spec ausdruecklich zurueckgezogen
    hat.

    Nur Spalte 1 zaehlt: die Grund-Spalte nennt haeufig weitere Pfade als
    Beleg oder Abgrenzung (`/shell/<panel_id>/sw.js`, `seiten/main.py:…`).
    """
    ausnahmen: set[str] = set()
    for route, _grund in _auth11_tabellen_zeilen(nur_gueltige=True):
        ausnahmen.add(route)
    return ausnahmen


def auth11_ueberholte_zeilen() -> set[str]:
    """Die zurueckgezogenen (`[UEBERHOLT …]`) Routen der AUTH-11-Tabelle.

    Kein Verbraucher in der Verriegelung — der Parser-Test braucht sie, um zu
    belegen, dass der UEBERHOLT-Zweig ueberhaupt greift (und nicht bloss
    zufaellig nichts findet).
    """
    return {route for route, _ in _auth11_tabellen_zeilen(nur_gueltige=False)}


def _auth11_tabellen_zeilen(*, nur_gueltige: bool):
    """(route, grund) je Tabellenzeile; `nur_gueltige` filtert den UEBERHOLT-Zweig."""
    for line in _abschnitt("### AUTH-11").splitlines():
        strip = line.strip()
        if not strip.startswith("|"):
            continue
        zellen = [z.strip() for z in strip.strip("|").split("|")]
        if len(zellen) < 2:
            continue
        route_zelle, grund = zellen[0], zellen[1]
        if set(route_zelle) <= set("- :"):   # Trenn-Zeile |---|---|
            continue
        ist_ueberholt = "ÜBERHOLT" in grund or "UEBERHOLT" in grund
        if nur_gueltige == ist_ueberholt:
            continue
        for route in _BACKTICK_ROUTE.findall(route_zelle):
            yield route, grund


def auth6_schuldstand() -> set[str]:
    """Die Routen der AUTH-6-Fence-Bloecke, die einen `(Trigger: …)` tragen.

    Alle ```-Fences des `### AUTH-6`-Abschnitts: der V1-Stand, die zehn
    Telegram-Shell-Routen (#1859) und die fuenf panel-Proxy-Routen (#1854).
    Kommentar-Zeilen (`# routine/{…}: … jetzt in AUTH-3`) tragen keinen
    Trigger und fallen raus.

    **Sammel-Eintraege werden verworfen** (AUTH-11:844): ein Eintrag mit `*`
    (`/api/v1/panels/*`, `/api/v1/geraete/*`) erklaert keine konkrete Route —
    „ein Sammel-Eintrag verdeckt genau die Routen, die niemand bedacht hat".
    Der Vergleich mit der URL-Map ist deshalb literal.
    """
    return {r for r in _auth6_alle_eintraege() if "*" not in r}


#: Der Token, mit dem die AUTH-11-Klausel ihre Inline-Beweisform einleitet.
#: Identisch mit `auth_gate.AUTH_KLASSE_INLINE_COOKIE` — Code und Spec teilen
#: den Namen, damit die Naht bei einer Umbenennung sichtbar bricht.
_INLINE_TOKEN = auth_gate.AUTH_KLASSE_INLINE_COOKIE

#: Anker der Klausel-DEFINITION: eine Zeile, die mit dem Token beginnt
#: (optional fettgesetzt), also `**AUTH-2-INLINE — vierte Beweisform …**`.
#:
#: Warum nicht „irgendeine Zeile, die den Token enthaelt": die Klausel nennt
#: ihre eigene Beweisform mehrfach als Quer-Verweis im Fliesstext
#: („… fuer Inline-Gates (AUTH-2-INLINE, unten)"). Ein Parser, der an der
#: ersten Erwaehnung ankert, startet weit VOR der Liste, laeuft in die
#: Ausnahme-Tabelle und liest deren Zeilen als Inline-Liste — gemessen: 39
#: statt 2 Eintraege, ohne die zwei echten. Das ist nicht bloss falsch,
#: sondern gefaehrlich falsch: stuende eine Route zufaellig in der
#: Ausnahme-Tabelle, waere ihr Inline-Marker still akzeptiert.
_INLINE_ANKER = re.compile(r"^\*{0,2}%s\b" % re.escape(_INLINE_TOKEN))


def auth11_inline_erlaubte() -> set[str]:
    """Die abschliessende Liste der Routen, die den Inline-Marker fuehren duerfen.

    **Warum es diese Liste braucht (Watchdog-Befund, Nic-Entscheid 2026-08-13).**
    Drei der vier AUTH-11-Erklaerungen kosten einen gereviewten Spec-PR. Der
    Inline-Marker kostete bis hierher eine Zeile Produktivcode und niemandes
    Aufmerksamkeit: `markiere_auth_klasse` setzt ein Attribut und prueft nichts
    — eine Route mit Marker und ganz OHNE Gate galt als erklaert. Das ist genau
    die Luecke, die AUTH-11 schliessen soll, an neuer Stelle. Deshalb zaehlt der
    Inline-Marker nur noch fuer Routen, die die Klausel namentlich fuehrt.

    Gelesen wird der Block im `### AUTH-11`-Abschnitt, den eine Zeile mit dem
    Token `AUTH-2-INLINE` einleitet; danach zaehlen die Backtick-Routen der
    folgenden Tabellen-/Fence-Zeilen bis zum Blockende. Beide Schreibweisen
    (Markdown-Tabelle wie die Ausnahme-Tabelle, Fence wie der AUTH-6-Schuldstand)
    werden akzeptiert, damit die Form dem Spec-Track offensteht.

    Fehlt der Block, ist die Menge **leer** — und jede Route mit Inline-Marker
    ist unerklaert. Kein Fallback, kein Grandfathering: ein „bis die Spec da ist
    zaehlt der Marker halt so" waere dieselbe selbstbediente Tuer noch einmal.
    """
    routen: set[str] = set()
    im_block = False
    im_fence = False
    # Erst wenn die eigentliche Aufzaehlung (Tabelle oder Fence) begonnen hat,
    # darf eine Prosa-Zeile den Block beenden. Sonst risse schon die zweite
    # Zeile eines mehrzeiligen Einleitungssatzes den Block ab, bevor die
    # Tabelle ueberhaupt beginnt — der Parser laese still eine leere Liste.
    struktur_begonnen = False
    for line in _abschnitt("### AUTH-11").splitlines():
        strip = line.strip()
        if not im_block:
            if _INLINE_ANKER.match(strip):
                im_block = True
                # Die einleitende Zeile darf selbst schon Routen fuehren.
                routen.update(_BACKTICK_ROUTE.findall(strip))
            continue
        if strip.startswith("```"):
            im_fence = not im_fence
            struktur_begonnen = True
            continue
        if im_fence:
            treffer = re.match(r"^(/\S+)", strip)
            if treffer:
                routen.add(treffer.group(1))
            continue
        if strip.startswith("|"):
            struktur_begonnen = True
            zellen = [z.strip() for z in strip.strip("|").split("|")]
            if zellen and not set(zellen[0]) <= set("- :"):
                routen.update(_BACKTICK_ROUTE.findall(zellen[0]))
            continue
        if not strip:
            continue
        # Prosa: vor der Aufzaehlung Einleitung (tolerieren), danach Blockende.
        routen.update(_BACKTICK_ROUTE.findall(strip))
        if struktur_begonnen:
            im_block = False
    return routen


def _auth6_alle_eintraege() -> list[str]:
    """Alle Trigger-Zeilen des AUTH-6-Abschnitts, Sammel-Eintraege eingeschlossen."""
    eintraege: list[str] = []
    im_fence = False
    for line in _abschnitt("### AUTH-6").splitlines():
        if line.strip().startswith("```"):
            im_fence = not im_fence
            continue
        if not im_fence:
            continue
        treffer = _AUTH6_FENCE_LINE.match(line.strip())
        if treffer:
            eintraege.append(treffer.group(1))
    return eintraege


# ---------------------------------------------------------------------------
# Klassifikation: welche der vier Erklaerungen greift?
# ---------------------------------------------------------------------------

# Die Sammelzeile der AUTH-11-Tabelle: „`/healthz` (je Service), `/version`".
# Sie ist die EINE Stelle, an der die Tabelle bewusst nicht pro Dienst
# enumeriert — deshalb eine eigene Erklaerungs-Sorte. Die beiden Pfade werden
# trotzdem aus der Tabelle GEPARST (unten in `erklaerung`), nicht hier
# hartkodiert: faellt die Zeile aus der Spec, faellt die Erklaerung mit.
_SAMMELZEILE = frozenset({"/healthz", "/version"})

#: Die drei Klassen, die AUSSCHLIESSLICH aus den Decorator-Factories stammen
#: duerfen. `markiere_auth_klasse` weist sie seit #1805 zurueck.
_FACTORY_KLASSEN = frozenset({
    auth_gate.AUTH_KLASSE_HART,
    auth_gate.AUTH_KLASSE_SOFT,
    auth_gate.AUTH_KLASSE_DUAL,
})


def _marker_traeger(view_func):
    """(Klasse, Traeger-Objekt) — wer in der `__wrapped__`-Kette den Marker haelt."""
    aktuell = view_func
    gesehen: set[int] = set()
    while aktuell is not None and id(aktuell) not in gesehen:
        gesehen.add(id(aktuell))
        klasse = getattr(aktuell, auth_gate.AUTH_MARKER, None)
        if klasse:
            return klasse, aktuell
        aktuell = getattr(aktuell, "__wrapped__", None)
    return None, None


def erklaerung(app, rule) -> tuple[str, str] | None:
    """Die (Sorte, Detail)-Erklaerung fuer eine URL-Map-Regel, oder `None`.

    `None` heisst: weder gegatet noch in einer der Spec-Listen — AUTH-11-rot.

    Zwei Feinheiten, beide aus dem Watchdog-Verdikt 2026-08-13:

    - **Inline-Marker nur gegen die Spec-Liste.** Ein Marker der Klasse
      `AUTH-2-INLINE` erklaert nur, wenn die Klausel die Route namentlich
      fuehrt (`auth11_inline_erlaubte`). Sonst ist die Route unerklaert — der
      Marker allein ist eine Selbstbescheinigung, kein Beweis.
    - **Listen-Drift wird benannt, nicht verschluckt.** Traegt eine Route ein
      Gate UND fuehrt die Spec sie zugleich als public (AUTH-6-Schuldstand
      oder AUTH-11-Ausnahme), ist das ein eigener Befund: die veraltete Zeile
      wuerde einen spaeteren Gate-Verlust auffangen und den Test gruen halten.
      Sicherheitsseitig gilt weiter „gegatet" (Vorrang ist richtig), aber die
      Sorte macht die Drift sichtbar (#1863).
    """
    view = app.view_functions.get(rule.endpoint)
    klasse, traeger = _marker_traeger(view)
    ausnahmen = auth11_ausnahmen()
    schuldstand = auth6_schuldstand()

    # Kohaerenz-Probe fuer die drei Factory-Klassen: sie entstehen nur an einem
    # fertigen Wrapper, und jeder dieser Wrapper traegt `functools.wraps`. Ein
    # Marker dieser Klassen auf einer NIE umhuellten Funktion kann folglich
    # nicht aus einer Factory stammen — er wurde von Hand gesetzt und behauptet
    # ein Gate, das es nicht gibt. `markiere_auth_klasse` weist diese Klassen
    # zurueck; diese Probe deckt zusaetzlich das rohe `setattr`.
    #
    # Bewusst nur VERSCHAERFEND: `__wrapped__` ist hier keine Gate-Heuristik
    # (das war der alte Fehler), sondern eine Zusatz-Bedingung. Der Marker
    # bleibt der Nachweis — er wird hier nur nicht mehr blind geglaubt.
    if klasse in _FACTORY_KLASSEN and not hasattr(traeger, "__wrapped__"):
        return None

    if klasse == auth_gate.AUTH_KLASSE_INLINE_COOKIE:
        if rule.rule not in auth11_inline_erlaubte():
            return None
        return ("gegatet-inline", "%s, namentlich in AUTH-11 gefuehrt" % klasse)
    if klasse:
        if rule.rule in schuldstand or rule.rule in ausnahmen:
            return ("gegatet-listen-drift",
                    "%s — Spec fuehrt die Route zugleich als public (#1863)" % klasse)
        return ("gegatet", klasse)

    if rule.rule in _SAMMELZEILE and rule.rule in ausnahmen:
        return ("auth11-sammelzeile", "AUTH-11-Tabelle, Zeile „je Service“")
    if rule.rule in ausnahmen:
        return ("auth11-ausnahme", "AUTH-11-Tabelle, namentliche Zeile")
    if rule.rule in schuldstand:
        return ("auth6-schuldstand", "AUTH-6-Fence mit Defer-Trigger")
    return None


def listen_drift(app) -> list[str]:
    """Routen, die ein Gate tragen und in der Spec zugleich als public stehen."""
    return sorted(
        rule.rule for rule in app.url_map.iter_rules()
        if (erklaerung(app, rule) or ("", ""))[0] == "gegatet-listen-drift"
    )


def unerklaerte_regeln(app) -> list[str]:
    """Alle Regeln einer App, fuer die keine der vier Erklaerungen greift."""
    offen = []
    for rule in app.url_map.iter_rules():
        if erklaerung(app, rule) is None:
            methoden = sorted(rule.methods - {"HEAD", "OPTIONS"})
            offen.append("%s %s [endpoint=%s]"
                         % (",".join(methoden), rule.rule, rule.endpoint))
    return sorted(offen)


# ---------------------------------------------------------------------------
# AC1 — die Verriegelung selbst, gegen die echten App-Objekte
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("service", sorted(SERVICE_MODULE))
def test_jede_url_map_regel_hat_genau_eine_erklaerung(service):
    """AUTH-11 (auth.md:839): jede Regel der echten `app.url_map` traegt
    entweder den Auth-Marker oder steht namentlich in einer der Spec-Listen.

    Messbasis ist die URL-Map, nicht der Quelltext (auth.md:929) — Flasks
    implizite `static`-Endpunkte stehen dort, ohne als `@app.route`-Dekoration
    sichtbar zu sein.

    Wird dieser Test rot, ist das ein **Fund**: entweder gehoert die Route
    gegatet, oder sie braucht einen Spec-Eintrag (AUTH-11-Ausnahme oder
    AUTH-6-Schuldstand mit Trigger). Eine Ausnahmeliste in DIESER Datei ist
    ausdruecklich nicht der Weg (auth.md:926).
    """
    app = _app(service)
    offen = unerklaerte_regeln(app)
    assert not offen, (
        "AUTH-11-Verletzung in %s — diese Routen sind weder gegatet noch in "
        "specs/platform/auth.md gefuehrt (AUTH-11-Ausnahme-Tabelle oder "
        "AUTH-6-Schuldstand mit Trigger):\n  %s"
        % (service, "\n  ".join(offen))
    )


@pytest.mark.parametrize("service", sorted(SERVICE_MODULE))
def test_keine_listen_drift_zwischen_gate_und_spec(service):
    """Watchdog-Befund 2 (#1863): eine Route, die ein Gate traegt und in der
    Spec ZUGLEICH als public gefuehrt wird, ist ein Drift-Befund.

    Warum das nicht bloss Kosmetik ist: `erklaerung()` nimmt die erste
    zutreffende Erklaerung, und Marker-vor-Spec ist fuer die Sicherheitsfrage
    die richtige Reihenfolge. Genau daraus entsteht aber ein blinder Fleck —
    verliert eine solche Route ihren Marker, faengt die veraltete
    AUTH-6-Zeile den Ausfall auf und der Coverage-Test bleibt gruen. Der
    Gate-Verlust waere unsichtbar.

    Stateless ist das nicht zu erkennen (der entfernte Marker hinterlaesst
    keine Spur). Die einzige Abhilfe ist, die veraltete Zeile zu entfernen:
    ohne stale Eintrag gibt es nichts, was den Ausfall auffangen koennte.
    Deshalb ist dieser Test rot, bis die Spec nachgezogen ist — er treibt die
    Aufloesung, statt den Zustand zu dulden.

    Bekannter Stand 2026-08-13 (#1863): drei Routen sind gegatet, waehrend
    AUTH-6 sie noch als Schuldstand fuehrt — /api/v1/hoerspiel/<kind_id>/
    audio-stream, /api/v1/seiten, /api/v1/seiten/uebersicht. Ihre Defer-Trigger
    sind faktisch gefeuert; die Zeilen gehoeren aus AUTH-6 heraus.
    """
    drift = listen_drift(_app(service))
    assert not drift, (
        "Listen-Drift in %s — diese Routen sind gegatet, die Spec fuehrt sie "
        "aber weiter als public. Die veraltete Zeile wuerde einen spaeteren "
        "Gate-Verlust maskieren (#1863). Spec nachziehen, nicht hier "
        "ausnehmen:\n  %s" % (service, "\n  ".join(drift))
    )


def test_url_map_flaeche_ist_nicht_leer_geparst():
    """Backstop gegen ein still leeres Gruen: haette `iter_rules()` nichts
    geliefert (Import-Fehler, falsches App-Objekt), waere der Test oben
    trivial gruen. Die Groessenordnung ist die Ist-Flaeche 2026-08-12."""
    gesamt = sum(len(list(_app(s).url_map.iter_rules())) for s in SERVICE_MODULE)
    assert gesamt >= 150, (
        "Nur %d URL-Map-Regeln ueber zehn Services gefunden — erwartet >=150 "
        "(Ist-Stand 2026-08-12: 175). Import- oder App-Aufloesung pruefen."
        % gesamt
    )


def test_registry_deckt_jede_flask_app_des_repos():
    """Verriegelung der Verriegelung: ein neuer Service mit eigener Flask-App
    darf nicht dadurch unsichtbar bleiben, dass ihn niemand in `SERVICE_MODULE`
    eintraegt. Gemessen am Repo-Zustand (`<dienst>/main.py` mit `app = Flask(`),
    nicht an einer zweiten Liste."""
    gefunden = {
        pfad.parent.name
        for pfad in sorted(REPO_ROOT.glob("*/main.py"))
        if re.search(r"^\s*app\s*=\s*Flask\(", pfad.read_text(encoding="utf-8"), re.M)
    }
    assert gefunden == set(SERVICE_MODULE), (
        "Flask-Apps im Repo und SERVICE_MODULE laufen auseinander — "
        "ungedeckt: %s / verwaist: %s"
        % (sorted(gefunden - set(SERVICE_MODULE)),
           sorted(set(SERVICE_MODULE) - gefunden))
    )


# ---------------------------------------------------------------------------
# AC2 — der Parser gegen die echte Spec-Datei
# ---------------------------------------------------------------------------


def test_parser_auth11_tabelle_kardinalitaet_und_stichproben():
    """Ein stiller Parse-Fehler (Tabellenformat geaendert, Regex daneben)
    wuerde die Ausnahmen leeren — und der Coverage-Test oben ginge rot statt
    stumm gruen. Trotzdem wird die Kardinalitaet hier festgenagelt, damit ein
    *teilweiser* Parse-Verlust sichtbar wird, bevor jemand ihn als „Route
    nicht erklaert" fehldeutet. Ist-Stand 2026-08-12: 36 Routen."""
    ausnahmen = auth11_ausnahmen()
    assert len(ausnahmen) >= 30, (
        "Nur %d AUTH-11-Ausnahmen geparst (erwartet >=30, Ist 2026-08-12: 36) "
        "— Tabellenformat in auth.md geaendert?" % len(ausnahmen)
    )
    # Stichproben ueber die Klassen der Tabelle.
    for route in (
        "/auth/pair",
        "/shell/<panel_id>/manifest.json",
        "/controller/_shared/<path:asset>",
        "/api/v1/init-data/validate",
        "/api/v1/seiten/static/<path:filename>",
        "/display/kibuddy/static/manifest.webmanifest",
        "/display/hoerspiel/static/manifest.webmanifest",
        "/seiten/wetter/regeln/wetter-regeln.css",
    ):
        assert route in ausnahmen, "%s fehlt in den geparsten AUTH-11-Ausnahmen" % route


def test_parser_liest_komma_getrennte_zeilen_als_zwei_routen():
    """Falle 1: eine Tabellenzeile fuehrt ZWEI Routen komma-getrennt.
    Wer nur das erste Backtick nimmt, verliert die zweite still."""
    ausnahmen = auth11_ausnahmen()
    # Zeile „`/healthz` (je Service), `/version`"
    assert {"/healthz", "/version"} <= ausnahmen
    # Zeile „`/display/_shared/design/<path:asset>`, `/display/_shared/icons/<path:asset>`"
    assert {
        "/display/_shared/design/<path:asset>",
        "/display/_shared/icons/<path:asset>",
    } <= ausnahmen


def test_parser_verwirft_ueberholte_tabellenzeile():
    """Falle 2: `/shell/<panel_id>/sw.js` steht syntaktisch in der Tabelle,
    ist aber mit `**[UEBERHOLT — Code-Gegenprobe]**` zurueckgezogen (die Route
    ist inzwischen hart gegatet, `seiten/main.py`). Ein Parser, der sie als
    Ausnahme fuehrt, wuerde ein spaeteres Entfernen des Gates decken."""
    assert "/shell/<panel_id>/sw.js" in auth11_ueberholte_zeilen(), (
        "UEBERHOLT-Zweig greift nicht mehr — Marker in auth.md umformuliert? "
        "Der Test wuerde sonst nichts pruefen."
    )
    assert "/shell/<panel_id>/sw.js" not in auth11_ausnahmen(), (
        "Zurueckgezogene Zeile wird faelschlich als AUTH-11-Ausnahme gefuehrt"
    )


def test_parser_auth6_schuldstand_kardinalitaet_und_stichproben():
    """Der AUTH-6-Parser liest alle Fence-Bloecke des Abschnitts.

    Ist-Stand 2026-08-13: 15 literale Eintraege. Zuvor 21 — #1865 hat sechs
    erledigte Posten ENTFERNT (drei tote Routen aus dem RAT-31-Router-Tod,
    drei mit am 2026-08-12 gefeuertem Trigger). Die Schwelle folgt der Spec
    nach unten: sie soll einen stillen Parse-Verlust fangen, nicht einen
    aufgeraeumten Schuldstand zurueckweisen.
    """
    schuld = auth6_schuldstand()
    assert len(schuld) >= 13, (
        "Nur %d AUTH-6-Schuldstand-Eintraege geparst (erwartet >=13, Ist: 15)"
        % len(schuld)
    )
    for route in (
        "/api/v1/seiten/mini-app-uebersicht",           # V1-Stand-Fence
        "/seiten/essen/einkauf",                        # Telegram-Shell-Fence (#1859)
        "/seiten/essen/einkauf/",                       # Trailing-Slash-Variante
        "/seiten/hoerspiel/<kind_id>/eltern",
        "/api/v1/panels/<panel_id>/config.json",        # panel-Proxy-Fence (#1854)
        "/controller/app-panel/<panel_id>/bearbeiten.css",
    ):
        assert route in schuld, "%s fehlt im geparsten AUTH-6-Schuldstand" % route


def test_parser_verwirft_sammeleintraege_des_auth6_fence():
    """AUTH-11:844 — Sammel-Eintraege zaehlen nicht. `/api/v1/panels/*` steht
    mit Trigger im V1-Stand-Fence, darf aber keine konkrete Regel erklaeren."""
    alle = _auth6_alle_eintraege()
    assert "/api/v1/panels/*" in alle, (
        "Sammel-Eintrag nicht mehr im Fence — Test prueft sonst nichts"
    )
    assert "/api/v1/panels/*" not in auth6_schuldstand()
    assert not any("*" in r for r in auth6_schuldstand())


def test_parser_ignoriert_kommentarzeilen_ohne_trigger():
    """auth.md:577 — ohne Defer-Trigger ist ein Eintrag kein AUTH-6-Eintrag.
    Die Kommentarzeile im V1-Stand-Fence („… jetzt in AUTH-3") darf nichts
    erklaeren."""
    assert not any(r.startswith("#") for r in auth6_schuldstand())
    assert "/api/v1/routine/items" not in auth6_schuldstand(), (
        "Die nach AUTH-3 gewanderte Route darf nicht mehr als Schuldstand gelten"
    )


def test_spec_listen_sind_nicht_im_testcode_dupliziert():
    """auth.md:926 — „Die Liste erweitert man nur per Spec-Aenderung, nie im
    Test-Code." Diese Datei haelt keine zweite Wahrheit: die einzigen
    literalen Routen im Quelltext sind Stichproben in `test_parser_*` und die
    Sammelzeilen-Paare — beide werden gegen die geparste Spec geprueft, nicht
    statt ihrer. Der Test verriegelt, dass die Erklaerungs-Mengen
    ausschliesslich aus `AUTH_MD` stammen."""
    quelle = pathlib.Path(__file__).read_text(encoding="utf-8")
    for name in ("auth11_ausnahmen", "auth6_schuldstand"):
        koerper = quelle.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0]
        assert "AUTH_MD" in koerper or "_abschnitt(" in koerper or "_auth" in koerper, (
            "%s liest nicht aus der Spec-Datei" % name
        )


# ---------------------------------------------------------------------------
# AC3 — Marker statt `__wrapped__`-Heuristik
# ---------------------------------------------------------------------------


def test_jede_factory_setzt_ihren_marker():
    """Jede der drei Decorator-Factories markiert ihren Wrapper mit der
    Auth-Klasse — `functools.wraps` allein (`__wrapped__`) ist KEIN Nachweis."""
    def _dummy():
        return "ok"

    hart = auth_gate.make_require_init_data(
        get_bot_token=lambda: "t", get_familie_client=lambda: None,
        get_init_data_config=lambda: {"max_age_seconds": 60},
        auth_401=lambda: ("", 401))(_dummy)
    soft = auth_gate.make_require_soft_gate(
        get_bot_token=lambda: "t", get_familie_client=lambda: None,
        get_init_data_config=lambda: {"max_age_seconds": 60},
        auth_401=lambda: ("", 401))(_dummy)
    dual = auth_gate.make_require_dual_gate(
        get_bot_token=lambda: "t", get_client_ip=lambda: None,
        auth_401=lambda: ("", 401))()(_dummy)

    assert auth_gate.auth_klasse(hart) == auth_gate.AUTH_KLASSE_HART
    assert auth_gate.auth_klasse(soft) == auth_gate.AUTH_KLASSE_SOFT
    assert auth_gate.auth_klasse(dual) == auth_gate.AUTH_KLASSE_DUAL


def test_fremder_wraps_decorator_gilt_nicht_als_gate():
    """Der Kern von AC3: ein beliebiger `functools.wraps`-Decorator setzt
    `__wrapped__` und waere unter der alten Heuristik als „gegatet"
    durchgegangen. Ohne Marker ist er kein Gate."""
    import functools

    def irgendein_decorator(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            return fn(*a, **k)
        return wrapper

    @irgendein_decorator
    def view():
        return "ok"

    assert hasattr(view, "__wrapped__"), "Voraussetzung: alte Heuristik greift"
    assert auth_gate.auth_klasse(view) is None, (
        "Ein nicht-Auth-Decorator darf keine Route als gegatet ausweisen"
    )


def test_marker_ueberlebt_einen_aeusseren_wraps_decorator():
    """Ein spaeterer aeusserer Decorator darf den Nachweis nicht verdecken:
    `functools.wraps` kopiert das `__dict__` mit, und `auth_klasse` laeuft
    zusaetzlich die `__wrapped__`-Kette ab."""
    import functools

    def aussen(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            return fn(*a, **k)
        return wrapper

    dual = auth_gate.make_require_dual_gate(
        get_bot_token=lambda: "t", get_client_ip=lambda: None,
        auth_401=lambda: ("", 401))()(lambda: "ok")
    assert auth_gate.auth_klasse(aussen(dual)) == auth_gate.AUTH_KLASSE_DUAL


def test_markiere_auth_klasse_ist_verhaltensneutral():
    """`markiere_auth_klasse` umhuellt nicht — es gibt dieselbe Funktion
    zurueck. Das ist die Bedingung, unter der die zwei Live-Player-Routen den
    Marker bekommen konnten, ohne ihren Auth-Pfad anzufassen (AC4)."""
    def view(a, b=2):
        return a + b

    markiert = auth_gate.markiere_auth_klasse(
        auth_gate.AUTH_KLASSE_INLINE_COOKIE)(view)
    assert markiert is view, "Marker darf keinen Wrapper einziehen"
    assert markiert(1) == 3
    assert auth_gate.auth_klasse(markiert) == auth_gate.AUTH_KLASSE_INLINE_COOKIE


@pytest.mark.parametrize("klasse", sorted(_FACTORY_KLASSEN))
def test_markiere_auth_klasse_verweigert_die_factory_klassen(klasse):
    """Die Tuer, die AUTH-11 zumachen soll, war nach dem Inline-Riegel nur
    verschoben: `markiere_auth_klasse` nahm jeden String an, und `erklaerung()`
    prueft die Spec-Liste NUR bei der Inline-Klasse. Ein handgesetztes
    `AUTH-7b-DUAL` auf einer gate-losen, schreibenden Route war damit gruen —
    eine Zeile, kein Spec-PR.

    AUTH-11 stuetzt seine Beweiskette ausdruecklich darauf, dass die
    Factory-Klassen nur am fertigen Wrapper entstehen (auth.md: „wer ihn
    traegt, hat zwingend auch dessen Gate-Logik"). Diese Praemisse haelt nur,
    wenn der Handsetzer sie nicht schreiben darf.
    """
    with pytest.raises(ValueError, match="AUTH-2-INLINE"):
        auth_gate.markiere_auth_klasse(klasse)


def test_markiere_auth_klasse_verweigert_auch_freie_strings():
    """Kein Ausweichen ueber einen Fantasie-Wert: nur die Inline-Klasse zaehlt."""
    with pytest.raises(ValueError, match="AUTH-2-INLINE"):
        auth_gate.markiere_auth_klasse("AUTH-9000-SUPER")


# ---------------------------------------------------------------------------
# AC4 — die zwei AUTH-2-Inline-Gates in seiten (Hoerspiel-Player)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("regel", [
    "/seiten/hoerspiel/player",
    "/seiten/hoerspiel/player/<path:asset>",
])
def test_inline_gate_routen_tragen_den_marker(regel):
    """Die Player-PWA prueft ihr AUTH-2-Cookie im Funktionskoerper statt per
    Decorator (`seiten/main.py`, „AUTH-2: Cookie-Gate (HSP-47, #1292)").
    Ohne Marker saehe AUTH-11 sie als ungegatet — mit Marker ist die Lage
    deklariert. Der Verhaltens-Beleg bleiben die 401-Tests der seiten-Suite;
    hier wird nur die Sichtbarkeit geprueft."""
    app = _app("seiten")
    treffer = [r for r in app.url_map.iter_rules() if r.rule == regel]
    assert treffer, "%s nicht in der seiten-URL-Map — Route umbenannt?" % regel
    view = app.view_functions[treffer[0].endpoint]
    assert auth_gate.auth_klasse(view) == auth_gate.AUTH_KLASSE_INLINE_COOKIE
    assert not hasattr(view, "__wrapped__"), (
        "Der Marker darf die View NICHT umhuellt haben (Live-PWA, kein Umbau)"
    )


# ---------------------------------------------------------------------------
# AC5 — Negativ-Probe: eine neue, unerklaerte Route macht rot
# ---------------------------------------------------------------------------


def _wegwerf_app(name: str):
    """Eine Wegwerf-Flask-App, die NUR die im Test deklarierten Routen fuehrt.

    `static_folder=None` ist load-bearing: `Flask(__name__)` haengt sonst
    ungefragt den impliziten `/static/<path:filename>`-Endpunkt ein, und der
    waere in einer Fantasie-App weder markiert noch in der Spec gefuehrt —
    die Probe wuerde ihn als „Fund" melden und damit ihre eigene Aussage
    verwaessern. Genau dieser implizite Endpunkt ist in den ECHTEN Diensten
    ohne eigenen `static_url_path` (`panel`, `familie`) real vorhanden und
    dort gegatet: beide tauschen ihn per
    `app.view_functions["static"] = require_dual_gate()(...)`
    (`panel/main.py:157`, `familie/main.py:264`), womit der Wrapper der
    Factory — und mit ihm der Marker — an der View haengt. Der Coverage-Test
    oben prueft das an den echten App-Objekten; hier geht es nur um die
    Klassifikations-Mechanik.
    """
    from flask import Flask

    return Flask(name, static_folder=None)


def test_negativprobe_neue_ungegatete_route_wird_rot():
    """Eine testweise hinzugefuegte Route ohne Gate und ohne Spec-Eintrag
    muss von `unerklaerte_regeln` gemeldet werden — sonst ist die
    Verriegelung eine Attrappe.

    Bewusst auf einer Wegwerf-App: die echten App-Objekte sind Modul-Singletons,
    die andere Suiten desselben pytest-Prozesses benutzen; eine dort
    eingehaengte Fantasie-Route waere ein Seiteneffekt ueber Testgrenzen hinweg.
    Geprueft wird die Klassifikations-Mechanik, und die ist dieselbe.
    """
    probe = _wegwerf_app("auth11_negativprobe")

    @probe.route("/spielwiese/neue-route", methods=["GET", "POST"])
    def neu():                                    # pragma: no cover - nie gerufen
        return "geheim"

    offen = unerklaerte_regeln(probe)
    assert offen == ["GET,POST /spielwiese/neue-route [endpoint=neu]"], (
        "Eine ungegatete, nirgends gefuehrte Route wurde NICHT (oder nicht "
        "genau sie) gemeldet: %s" % offen
    )


def test_negativprobe_nackter_inline_marker_ohne_spec_eintrag_wird_rot():
    """Watchdog-Befund 1 / Nic-Entscheid 2026-08-13: der Inline-Marker ist
    keine selbstbedienbare Tuer.

    `markiere_auth_klasse` setzt ein Attribut und prueft NICHTS — eine Route
    mit Marker und ganz ohne Gate-Code sah bis hierher erklaert aus. Drei der
    vier Erklaerungen kosten einen gereviewten Spec-PR; diese kostete eine
    Zeile Produktivcode. Jetzt zaehlt der Marker nur fuer Routen, die AUTH-11
    namentlich fuehrt — eine ungelistete Route mit nacktem Marker ist rot.
    """
    probe = _wegwerf_app("auth11_inline_negativprobe")

    @probe.route("/spielwiese/nur-marker-kein-gate")
    @auth_gate.markiere_auth_klasse(auth_gate.AUTH_KLASSE_INLINE_COOKIE)
    def nur_marker():                             # pragma: no cover - nie gerufen
        return "kein Gate, nur ein Attribut"

    assert "/spielwiese/nur-marker-kein-gate" not in auth11_inline_erlaubte(), (
        "Voraussetzung: die Fantasie-Route steht nicht in der Spec-Liste"
    )
    offen = unerklaerte_regeln(probe)
    assert offen == ["GET /spielwiese/nur-marker-kein-gate [endpoint=nur_marker]"], (
        "Ein Inline-Marker ohne namentlichen Spec-Eintrag muss unerklaert "
        "bleiben — sonst ist die Verriegelung selbstbedienbar: %s" % offen
    )


def test_inline_marker_zaehlt_sobald_die_klausel_die_route_fuehrt(tmp_path, monkeypatch):
    """Gegenstueck zur Probe oben, gegen eine FIXTURE-Spec: steht die Route in
    der Klausel, erklaert der Inline-Marker sie.

    Die Fixture belegt zugleich den Parser-Vertrag fuer den offenen Spec-Track
    (`spec/1805-inline-marker-in-auth11`): beide Schreibweisen — Tabellenzeile
    und Fence — werden gelesen, jeweils eingeleitet durch eine Zeile mit dem
    Token `AUTH-2-INLINE`.
    """
    fixture = tmp_path / "auth.md"
    # Die Fixture spiegelt die ECHTE Form: ein Quer-Verweis auf die Beweisform
    # im Fliesstext VOR der Definition (genau die Falle, die den Parser einmal
    # in die Ausnahme-Tabelle laufen liess), dann die fettgesetzte Definition
    # am Zeilenanfang, dann die Liste.
    fixture.write_text(
        "### AUTH-11 — Rueck-Verriegelung\n\n"
        "| Route | Grund |\n|---|---|\n"
        "| `/auth/pair` | Ausnahme-Tabelle, darf NICHT in die Inline-Liste. |\n\n"
        "Der Marker gilt fuer Inline-Gates (%s, unten) nur mit Liste.\n\n"
        "**%s — vierte Beweisform.** Abschliessende Liste:\n\n"
        "| Route | Grund |\n|---|---|\n"
        "| `/seiten/hoerspiel/player` | Player-PWA, Cookie-Gate im Koerper. |\n"
        "| `/seiten/hoerspiel/player/<path:asset>` | Assets derselben PWA. |\n\n"
        "## 6. Naechster Abschnitt\n" % (_INLINE_TOKEN, _INLINE_TOKEN),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "AUTH_MD", fixture)
    erlaubt = auth11_inline_erlaubte()
    assert erlaubt == {
        "/seiten/hoerspiel/player",
        "/seiten/hoerspiel/player/<path:asset>",
    }, "Tabellen-Schreibweise nicht korrekt geparst: %s" % sorted(erlaubt)

    fixture.write_text(
        "### AUTH-11 — Rueck-Verriegelung\n\n"
        "**%s — vierte Beweisform.**\n"
        "Mehrzeilige Einleitungsprosa, die den Block nicht abreissen darf.\n\n"
        "**Abschliessende Liste — heute genau zwei:**\n\n"
        "```\n/seiten/hoerspiel/player\n/seiten/hoerspiel/player/<path:asset>\n```\n\n"
        "## 6. Naechster Abschnitt\n" % _INLINE_TOKEN,
        encoding="utf-8",
    )
    erlaubt = auth11_inline_erlaubte()
    assert erlaubt == {
        "/seiten/hoerspiel/player",
        "/seiten/hoerspiel/player/<path:asset>",
    }, "Fence-Schreibweise nicht korrekt geparst: %s" % sorted(erlaubt)


def test_inline_liste_ist_klein_und_ueberschneidet_keine_andere_liste():
    """Anti-Pollution-Riegel — der Ersatz fuer die Bereitschafts-Probe.

    Vorgeschichte: der Parser ankerte an der ERSTEN Erwaehnung des Tokens.
    Die Klausel nennt ihre Beweisform aber zweimal als Quer-Verweis im
    Fliesstext, bevor sie sie definiert. Der Block startete deshalb vor der
    Ausnahme-Tabelle und las deren Zeilen als Inline-Liste: 39 Eintraege statt
    2, und ausgerechnet die zwei echten fehlten. Die Coverage ging davon rot
    — aber nur zufaellig. Stuende eine Route zugleich in der Ausnahme-Tabelle,
    waere ihr Inline-Marker still akzeptiert worden.

    Zwei strukturelle Invarianten fangen genau diese Klasse:

    - **Disjunkt.** Eine Route, deren Gate inline im Koerper liegt, ist per
      Definition nicht public — sie kann nicht zugleich AUTH-11-Ausnahme oder
      AUTH-6-Schuldstand sein. Ueberlappung heisst: ein Parser hat die
      Nachbar-Liste eingesammelt.
    - **Klein.** Die Beweisform ist die Ausnahme von der Ausnahme (n=1-Fall,
      auth.md „heute genau zwei"). Eine zweistellige Inline-Liste ist
      entweder ein Parse-Unfall oder ein Architektur-Problem — beides gehoert
      angesehen, nicht durchgewunken.
    """
    inline = auth11_inline_erlaubte()
    assert inline, "Inline-Liste leer geparst — Klausel-Form in auth.md geaendert?"

    ueberlappung_ausnahme = inline & auth11_ausnahmen()
    assert not ueberlappung_ausnahme, (
        "Inline-Liste ueberlappt die AUTH-11-Ausnahme-Tabelle — der Parser hat "
        "vermutlich die Nachbar-Tabelle eingesammelt: %s"
        % sorted(ueberlappung_ausnahme)
    )
    ueberlappung_schuld = inline & auth6_schuldstand()
    assert not ueberlappung_schuld, (
        "Inline-Liste ueberlappt den AUTH-6-Schuldstand — eine inline gegatete "
        "Route kann nicht zugleich als public gefuehrt sein: %s"
        % sorted(ueberlappung_schuld)
    )
    assert len(inline) <= 5, (
        "Inline-Liste unerwartet gross (%d Eintraege): %s — Parse-Unfall oder "
        "die Beweisform wird als Abkuerzung benutzt statt als n=1-Ausnahme."
        % (len(inline), sorted(inline))
    )


def test_negativprobe_gegatete_und_gefuehrte_routen_bleiben_gruen():
    """Gegenprobe zur Negativ-Probe: derselbe Mechanismus meldet eine
    gegatete und eine Spec-gefuehrte Route NICHT — der Test oben ist also
    nicht bloss „meldet alles".

    Die gegatete Route bekommt hier einen ECHTEN Factory-Decorator. Frueher
    stand an dieser Stelle ein handgesetztes `AUTH_KLASSE_DUAL` auf einer
    gate-losen View — damit zementierte der eigene Testkorpus genau das
    Muster, das die Verriegelung verhindern soll: wer es kopierte, tat nichts,
    was das Repo als falsch behandelt.
    """
    probe = _wegwerf_app("auth11_gegenprobe")
    echter_gate = auth_gate.make_require_dual_gate(
        get_bot_token=lambda: "t", get_client_ip=lambda: None,
        auth_401=lambda: ("", 401))()

    @probe.route("/spielwiese/gegatet")
    @echter_gate
    def gegatet():                                # pragma: no cover - nie gerufen
        return "ok"

    @probe.route("/healthz")
    def healthz():                                # pragma: no cover - nie gerufen
        return "ok"

    @probe.route("/auth/pair")
    def pair():                                   # pragma: no cover - nie gerufen
        return "ok"

    assert unerklaerte_regeln(probe) == [], (
        "Marker- bzw. Spec-gedeckte Routen duerfen nicht gemeldet werden"
    )


def test_negativprobe_handgesetzte_factory_klasse_ohne_gate_wird_rot():
    """Der vom Watchdog reproduzierte Fall, in seiner haertesten Form.

    `markiere_auth_klasse` weist die Factory-Klassen jetzt zurueck — der
    bequeme Weg ist zu. Bleibt das rohe `setattr` mit dem Attributnamen. Auch
    das darf nicht gruen sein: der Marker sitzt dann auf einer nie umhuellten
    Funktion, kann also aus keiner Factory stammen und behauptet ein Gate, das
    es nicht gibt.

    Die Route ist bewusst schreibend und fuehrt eine Kind-ID — die Klasse
    Route, die im Ausgangsbefund von #1805 unauthentifiziert erreichbar war.
    """
    probe = _wegwerf_app("auth11_gefaelschter_marker")

    @probe.route("/api/v1/kinder/<kid>/profil", methods=["GET", "POST"])
    def profil(kid):                              # pragma: no cover - nie gerufen
        return "Profil ohne jeden Gate"

    # Roh gesetzt, am Handsetzer vorbei — die einzige verbliebene Form.
    setattr(profil, auth_gate.AUTH_MARKER, auth_gate.AUTH_KLASSE_DUAL)
    assert auth_gate.auth_klasse(profil) == auth_gate.AUTH_KLASSE_DUAL, (
        "Voraussetzung: der gefaelschte Marker ist gesetzt"
    )

    offen = unerklaerte_regeln(probe)
    assert offen == ["GET,POST /api/v1/kinder/<kid>/profil [endpoint=profil]"], (
        "Eine gate-lose Route mit handgesetzter Factory-Klasse muss unerklaert "
        "bleiben — sonst genuegt eine Zeile fuer eine schreibende Route: %s" % offen
    )


def test_negativprobe_entfernter_marker_macht_echte_route_rot():
    """Zweite Richtung, diesmal am ECHTEN App-Objekt: verliert eine heute
    gegatete `seiten`-Route ihren Marker, meldet die Verriegelung sie sofort.
    `monkeypatch` stellt den Marker danach wieder her."""
    app = _app("seiten")
    kandidat = next(
        (r for r in app.url_map.iter_rules()
         if auth_gate.auth_klasse(app.view_functions[r.endpoint])
         == auth_gate.AUTH_KLASSE_DUAL
         and r.rule not in auth11_ausnahmen()
         and r.rule not in auth6_schuldstand()),
        None,
    )
    assert kandidat is not None, "keine dual-gegatete seiten-Route gefunden"

    view = app.view_functions[kandidat.endpoint]
    original = getattr(view, auth_gate.AUTH_MARKER)
    try:
        delattr(view, auth_gate.AUTH_MARKER)
        assert any(kandidat.rule in eintrag for eintrag in unerklaerte_regeln(app)), (
            "Ohne Marker muss %s als unerklaert gemeldet werden" % kandidat.rule
        )
    finally:
        setattr(view, auth_gate.AUTH_MARKER, original)
    # Nur die manipulierte Route pruefen — nicht die ganze App: andere Regeln
    # koennen aus unabhaengigen Gruenden offen sein (siehe die zwei
    # Inline-Routen, blockiert auf spec/1805-inline-marker-in-auth11). Eine
    # Wiederherstellungs-Probe, die daran haengt, misst nicht mehr sich selbst.
    assert not any(kandidat.rule in eintrag for eintrag in unerklaerte_regeln(app)), (
        "Wiederherstellung des Markers auf %s fehlgeschlagen" % kandidat.rule
    )
