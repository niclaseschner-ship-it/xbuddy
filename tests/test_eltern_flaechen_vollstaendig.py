"""Guard: eine Pruefung, die AUSLASSUNG bemerkt (#1822).

Bisher fragten unsere Pruefungen nur „ist das, was jemand eingetragen hat,
richtig?". Sie fragten nie „fehlt ein Eintrag?" — und was jemand **vergisst**,
fiel niemandem auf. `seiten/tests/test_pwa_mantel.py` fror die
Mantel-Konsumenten als Literal-Set ein: das faengt **Hinzufuegen**
(Set-Gleichheit bricht), aber eine neue Eltern-Flaeche, die sich nie
registriert, laesst jeden Test gruen.

Dieser Guard laeuft den Baum der Ansichts-Verzeichnisse (`views.json`) ab,
zieht jeden Eintrag mit `zielgruppe: "eltern"` und prueft ihn gegen das
Mantel-Register (`seiten/pwa_mantel.py:REGISTRY`). Die Ableitung, die Wahl des
Laders und der Verbund-Schluessel stehen in `tests/eltern_flaechen.py` — dort
auch die **Ausnahme-Liste als Daten mit Begruendung**.

Bauform-Vorbild: `tests/test_testpaths_vollstaendig.py`.

Sichtbarkeit: `test_befunde_sind_im_lauf_sichtbar` gibt jeden dokumentierten
Befund als Warnung aus. Damit steht die Schuld-Liste in JEDEM pytest-Lauf in
der Warnungs-Zusammenfassung, statt stumm in einer Datei zu liegen.
"""

import importlib
import importlib.util
import json
import os
import sys
import warnings

import pytest


def _lade_eltern_flaechen():
    """Laedt `tests/eltern_flaechen.py` unter eindeutigem Modulnamen.

    Kein `from tests import ...`: `tools/tests/__init__.py` ist ein regulaeres
    Paket namens `tests` und gewinnt im repo-weiten Lauf gegen das
    Namensraum-Paket `tests/` in der Repo-Wurzel — der Import zoege dann das
    falsche Verzeichnis. Auch kein `sys.path`-Anhaengen von `tests/`: das
    mischte `tests/tools/` in das Namensraum-Paket `tools/`. Also Pfad-Import
    mit eigenem Namen, einmal registriert und von beiden Konsumenten geteilt
    (auch seiten/tests/test_pwa_mantel.py laedt genau so).
    """
    name = "xbuddy_eltern_flaechen"
    if name not in sys.modules:
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "eltern_flaechen.py")
        spec = importlib.util.spec_from_file_location(name, pfad)
        modul = importlib.util.module_from_spec(spec)
        sys.modules[name] = modul
        spec.loader.exec_module(modul)
    return sys.modules[name]


ef = _lade_eltern_flaechen()


def _gekuerzt(text, laenge=180):
    """Fuer die Warnungs-Zeile: lang genug, um den Sachverhalt zu tragen, kurz
    genug, dass die Zusammenfassung lesbar bleibt."""
    text = " ".join(text.split())
    return text if len(text) <= laenge else text[:laenge - 1] + "…"


# ── Fixture: der 404-Messpfad konfiguriert den seiten-Dienst ─────────────────

@pytest.fixture(autouse=True)
def _seiten_runtime_zuruecksetzen():
    """`eltern_flaechen._client_fuer()` ruft `seiten.main.configure()` — das ist
    ein Modul-Global. Snapshot vor, Wiederherstellung nach jedem Test, damit
    dieser Guard keine Nachbar-Suite vergiftet (Vorbild:
    seiten/tests/test_pwa_mantel.py::reset_runtime)."""
    from seiten import main as seiten_main

    schluessel = ("root", "inventar_path", "bot_token", "init_data_config")
    vorher = {k: seiten_main.runtime.get(k) for k in schluessel}
    yield
    for k, wert in vorher.items():
        seiten_main.runtime[k] = wert


# ── AC1 — Auslassung macht rot ───────────────────────────────────────────────

def test_jede_eltern_flaeche_hat_einen_vollen_mantel_eintrag():
    """Eine Ansicht mit `zielgruppe: "eltern"` OHNE vollen Mantel-Eintrag macht
    diesen Test rot (#1822 AC1).

    „Voll" heisst: nicht nur der Zwischenspeicher-Schluessel. Ein Eintrag, der
    allein `build_id_source_set` setzt, ist laut Baseline ausdruecklich KEIN
    Mantel — die Flaeche ist dann nicht installierbar
    (`eltern_flaechen.ist_voller_mantel`).

    Der Verbund laeuft ueber die Start-Adresse, aufgeloest auf die Flask-Regel
    — der Kurzname taugt nicht als Schluessel (`einstellungen`→`plan`,
    `regeln`→`wetter-regeln`, `anpassen`→`routine`).
    """
    luecken = ef.mantel_luecken()
    assert not luecken, (
        "Eltern-facing Ansichten ohne vollen Mantel-Eintrag (#1822):\n"
        + "\n".join("  - %s" % b.text for b in luecken)
        + "\n\nFix: Registry-Eintrag in seiten/pwa_mantel.py:REGISTRY ergaenzen. "
        "Ist die Flaeche bewusst ohne Mantel, gehoert sie mit Begruendung in "
        "tests/eltern_flaechen.py:AUSNAHMEN (Achse 'mantel') — als 'ausnahme', "
        "wenn es eine Entscheidung ist, als 'schuldstand' mit Trigger, wenn es "
        "eine offene Frage ist."
    )


def test_waechter_wird_rot_wenn_eine_neue_eltern_flaeche_sich_nicht_registriert(tmp_path):
    """Fehlerpfad-Probe (#1822 AC1): der Guard KANN rot werden.

    Ein Waechter, der nie rot wird, ist schlimmer als keiner. Hier wird der
    Fall echt ausgeloest — ein synthetischer Baum mit einer frisch angelegten
    eltern-facing Ansicht, die sich nirgends registriert hat — und der Empfang
    bestaetigt: der Guard nennt sie beim Namen.
    """
    komponente = tmp_path / "frischling"
    komponente.mkdir()
    (komponente / "views.json").write_text(json.dumps({"views": [{
        "slug": "erfunden",
        "typ": "pwa",
        "pfad": "/seiten/frischling/erfunden",
        "label": "Erfundene Eltern-Flaeche",
        "synonyme": ["erfunden"],
        "zeigt": "Eine Flaeche, die niemand im Mantel-Register eingetragen hat.",
        "zielgruppe": "eltern",
    }]}, ensure_ascii=False), encoding="utf-8")

    luecken = ef.mantel_luecken(str(tmp_path))

    assert [b.kennung for b in luecken] == ["frischling/erfunden"], (
        "Der Guard hat die nicht registrierte Eltern-Flaeche NICHT gefunden — "
        "damit koennte er die Auslassung, gegen die er gebaut ist, nicht "
        "melden. Gefunden: %r" % [b.kennung for b in luecken]
    )
    assert "seiten/pwa_mantel.py:REGISTRY" in luecken[0].text


# ── AC2 — Uebereinstimmungs-Pruefung ─────────────────────────────────────────

@pytest.mark.parametrize("anschluss", ef.ANSCHLUESSE,
                         ids=[a.komponente for a in ef.ANSCHLUESSE])
def test_uebereinstimmung_verzeichnis_gegen_routen(anschluss):
    """Ansichts-Verzeichnis ⇔ echte Flask-Routen, beide Richtungen (#1822 AC2).

    `essen` und `hoerspiel` sind damit angeschlossen — die zwei Komponenten,
    die #1822 als real offen benannt hat. `routine` laeuft hier ebenfalls
    wieder: sein Bestand-Eigentest traegt ein `@pytest.mark.skip`, dessen Grund
    seit #1689 ueberholt ist.
    """
    abweichungen = ef.uebereinstimmung_pruefen(anschluss)
    assert not abweichungen, (
        "Verzeichnis⇔Routen-Drift fuer %r:\n" % anschluss.komponente
        + "\n".join("  - %s" % a for a in abweichungen)
    )


def test_keine_komponente_ohne_anschluss_und_ohne_begruendung():
    """Jede Komponente mit Ansichts-Verzeichnis ist entweder angeschlossen oder
    traegt einen begruendeten Ausnahme-Eintrag (#1822 AC2).

    Gemeint sind ausschliesslich Verzeichnisse, welche die Betriebs-Discovery
    (`<root>/*/views.json`) ueberhaupt findet. Was ausserhalb liegt, taucht
    hier nicht auf und braucht keinen Ausnahme-Eintrag.
    """
    luecken = ef.anschluss_luecken()
    assert not luecken, (
        "Komponenten ohne Uebereinstimmungs-Pruefung und ohne Ausnahme:\n"
        + "\n".join("  - %s" % b.text for b in luecken)
        + "\n\nFix: Anschluss in tests/eltern_flaechen.py:ANSCHLUESSE eintragen "
        "oder mit Begruendung in AUSNAHMEN (Achse 'anschluss')."
    )


# ── AC3 — deklarierte Adressen existieren wirklich ───────────────────────────

def test_deklarierte_adressen_liefern_kein_404():
    """Ein Eintrag darf nicht auf eine Adresse zeigen, die es nicht gibt (#1822 AC3).

    Der bekannte Fall sitzt in den PWA-Unterfeldern der Plan-Einstellungen:
    der Hauptpfad ist in Ordnung (200), aber `plan/views.json:26` und `:28`
    zeigen auf `/seiten/static/plan/{manifest.json,sw.js}` — beide 404.
    Ausgeliefert wird unter `/seiten/plan/einstellungen/…`. Beide Befunde
    stehen als Schuldstand in `tests/eltern_flaechen.py:AUSNAHMEN` und werden
    von `test_befunde_sind_im_lauf_sichtbar` in jedem Lauf ausgegeben — der
    Test meldet den Fund, er repariert die Registry-Datei nicht.

    Gemessen wird ueber den Flask-Test-Client des ausliefernden Dienstes: kein
    Live-HTTP, also auch kein stilles Gruen, wenn kein Dienst laeuft. Gatete
    Antworten (401/403) sind KEIN Befund — die Adresse existiert dann.
    """
    offen = [b for b in ef.pfad_befunde() if b.ausnahme is None]
    assert not offen, (
        "Deklarierte Adressen, die nicht existieren (#1822 AC3):\n"
        + "\n".join("  - %s" % b.text for b in offen)
        + "\n\nFix: die Adresse im views.json korrigieren. Ist der 404 bekannt "
        "und noch offen, gehoert er als 'schuldstand' mit Trigger in "
        "tests/eltern_flaechen.py:AUSNAHMEN (Achse 'pfad')."
    )


# ── #1890 — Route→Verzeichnis: die Seite ist da, der Eintrag fehlt ──────────

def test_jede_seiten_route_hat_einen_verzeichnis_eintrag():
    """Eine Seiten-Route ohne Eintrag im Ansichts-Verzeichnis macht rot (#1890).

    Die Gegenrichtung zur Mantel-Achse — und der wahrscheinlichere reale Fall:
    jemand baut die Seite und vergisst das Verzeichnis; die umgekehrte
    Reihenfolge kommt kaum vor. Fuer den Praefix `/seiten/<komp>/<view>` hatte
    diese Richtung im ganzen Repo keine Pruefung, obwohl dort fuenf der acht
    abgeleiteten Eltern-Flaechen und saemtliche PWA-Flaechen liegen.

    Gefragt wird nach einem Eintrag ueberhaupt, nicht nach `zielgruppe:
    "eltern"` — ohne Eintrag gibt es kein Zielgruppen-Feld zu lesen.
    """
    offen = ef.route_luecken()
    assert not offen, (
        "Seiten-Routen ohne Eintrag im Ansichts-Verzeichnis (#1890):\n"
        + "\n".join("  - %s" % b.text for b in offen)
        + "\n\nFix: die Flaeche im views.json ihrer Komponente eintragen "
        "(Pfad = die ausgelieferte Adresse). Ist die Route bewusst keine "
        "gelistete Flaeche, gehoert sie mit Begruendung in "
        "tests/eltern_flaechen.py:AUSNAHMEN (Achse 'route')."
    )


def test_die_gemessene_routen_menge_ist_nicht_leer():
    """Sonst pruefte die Achse leere Menge gegen leere Menge — gruen ohne
    Gegenstand.

    Bewusst KEINE Literal-Liste der erwarteten Routen: die waere genau die
    Anti-Form, die #1890 abschafft (wer eine Seite vergisst, vergisst auch den
    Listen-Eintrag). Geprueft wird nur, dass die Formregel `ist_seiten_route`
    ueberhaupt noch Seiten durchlaesst — bricht sie, faellt es hier auf und
    nicht erst, wenn eine echte Luecke stumm durchrutscht.
    """
    routen = ef.seiten_routen()
    assert routen, (
        "Unter %r zaehlt diese Pruefung keine einzige Seiten-Route — dann ist "
        "sie gegenstandslos gruen. Entweder liefert der seiten-Dienst keine "
        "Flaechen mehr aus, oder die Formregel ist_seiten_route filtert zu "
        "hart (tests/eltern_flaechen.py)." % ef.SEITEN_PRAEFIX
    )


def test_waechter_wird_rot_wenn_eine_neue_seiten_route_kein_verzeichnis_hat():
    """Fehlerpfad-Probe (#1890): diese Achse KANN rot werden.

    Genau der Fall, den der Pruefer zur Laufzeit ausgeloest hat und den alle
    vier bisherigen Achsen leer durchlaufen liessen: eine echte Route unter
    `/seiten/…` ohne jeden `views.json`-Eintrag. Hier wird sie in einen Abzug
    der Routen-Tabelle gehaengt (die echte App bleibt unberuehrt), der Empfang
    bestaetigt — und ohne sie ist der Befund wieder weg.

    Ein Waechter, der nie rot wird, ist schlimmer als keiner: er erzeugt
    Zuversicht.
    """
    erfunden = "/seiten/frischling/eltern"

    mit_route = ef.route_befunde(app=ef.routentabelle_mit_zusatz(erfunden))
    kennungen = [b.kennung for b in mit_route]
    assert erfunden in kennungen, (
        "Die Achse 'route' hat die nicht eingetragene Seiten-Route NICHT "
        "gefunden — damit koennte sie die Auslassung, gegen die sie gebaut "
        "ist, nicht melden. Gefunden: %r" % kennungen
    )
    treffer = next(b for b in mit_route if b.kennung == erfunden)
    assert "views.json" in treffer.text

    ohne_route = [b.kennung for b in ef.route_befunde()]
    assert erfunden not in ohne_route, (
        "Ohne die erfundene Route darf sie nicht mehr auftauchen — sonst misst "
        "die Achse nicht die Routen-Tabelle, die man ihr gibt. Gefunden: %r"
        % ohne_route
    )


# ── Achse `lader` — kaputte Eintraege werden Befund, nicht blinder Fleck ─────

def test_betriebs_lader_ueberspringt_nichts_undokumentiertes():
    """Jeder Eintrag, den der Betriebs-Lader fallen laesst, ist ein Befund.

    Der strenge Lader (`views_manifest.load`) wuerde bei genau einem defekten
    Eintrag die GANZE Datei fallen lassen — bei `hoerspiel/views.json` waere
    damit auch `hoerspiel-eltern` verschwunden und dieser Guard gruen ohne
    Gegenstand. Deshalb Ueberspringen-Semantik plus Meldepflicht.
    """
    offen = [b for b in ef.lader_befunde() if b.ausnahme is None]
    assert not offen, (
        "Der Betriebs-Lader hat Eintraege uebersprungen, die nirgends "
        "dokumentiert sind (#1822):\n"
        + "\n".join("  - %s" % b.text for b in offen)
        + "\n\nEin uebersprungener Eintrag ist unsichtbar fuer JEDE Pruefung, "
        "die auf views.json aufsetzt. Fix: den Eintrag reparieren oder mit "
        "Trigger in tests/eltern_flaechen.py:AUSNAHMEN (Achse 'lader')."
    )


def test_mantel_eintraege_ohne_eltern_flaeche_sind_benannt():
    """Die Gegenrichtung wird gemessen und BENANNT — gebaut wird sie nicht.

    #1822 klammert sie ausdruecklich aus: sie zu schliessen haette eine
    Produkt-Folge (die Heim-Shell erschiene in der Seiten-Uebersicht) und ist
    damit eine Entscheidung, kein Bau-Schritt. Dieser Test erzwingt deshalb
    keine Registrierung, sondern nur eine **Benennungs-Pflicht**: wer einen
    Mantel-Schluessel anlegt, zu dem keine eltern-facing Flaeche gehoert, muss
    das mit Begruendung eintragen, statt es stumm zu lassen.

    Der Anlass: die Drehung von Set-Gleichheit auf Pflicht-Enthaltensein
    (AC5) gibt die alte Fang-Wirkung fuer HINZUGEFUEGTE Registry-Schluessel
    auf. Real betroffen sind heute `shell` und `hoerspiel-player`.
    """
    unbenannt = ef.gegenrichtung_luecken()
    assert not unbenannt, (
        "Mantel-Schluessel ohne eltern-facing Flaeche, die nirgends benannt "
        "sind (#1822):\n"
        + "\n".join("  - %s" % b.text for b in unbenannt)
        + "\n\nDieser Test verlangt KEINE Registrierung — nur einen Eintrag mit "
        "Begruendung in tests/eltern_flaechen.py:AUSNAHMEN "
        "(Achse 'gegenrichtung')."
    )


def test_kein_ansichts_verzeichnis_faellt_komplett_aus():
    """Ein komplett unlesbares `views.json` wuerde eine ganze Komponente
    unsichtbar machen — das darf nie stillschweigend passieren."""
    kaputte = ef.durchlauf().kaputte_manifeste
    assert not kaputte, (
        "Diese Ansichts-Verzeichnisse sind als Ganzes unbrauchbar (JSON-/"
        "Struktur-Fehler) — jede darauf aufsetzende Pruefung ist fuer diese "
        "Komponenten blind:\n" + "\n".join("  - %s" % p for p in kaputte)
    )


# ── AC4 — die Ausnahme-Liste ist Daten mit Begruendung, und sie ist sichtbar ─

def test_ausnahme_liste_ist_wohlgeformt():
    """Jede Ausnahme traegt eine Begruendung und eine Quelle; jeder Schuldstand
    zusaetzlich einen Aufloesungs-Trigger (#1822 AC4).

    Eine Ausnahme ohne Begruendung ist eine stille Entscheidung. Ein
    Schuldstand ohne Trigger ist ein Dauerzustand mit besserem Namen — die
    Auth-Spec fuehrt beides deshalb getrennt (AUTH-11-Ausnahme-Tabelle vs.
    AUTH-6-Schuldstand), und dieser Test erzwingt dieselbe Trennung.
    """
    maengel = []
    kennungen = set()
    for eintrag in ef.AUSNAHMEN:
        anker = "%s/%s" % (eintrag.achse, eintrag.kennung)
        if anker in kennungen:
            maengel.append("%s: doppelter Eintrag" % anker)
        kennungen.add(anker)
        if eintrag.achse not in ef.ACHSEN:
            maengel.append("%s: unbekannte Achse %r" % (anker, eintrag.achse))
        if eintrag.sorte not in (ef.SORTE_AUSNAHME, ef.SORTE_SCHULDSTAND):
            maengel.append("%s: unbekannte Sorte %r" % (anker, eintrag.sorte))
        if len(eintrag.begruendung.strip()) < 40:
            maengel.append("%s: Begruendung fehlt oder ist ein Platzhalter" % anker)
        if not eintrag.quelle.strip():
            maengel.append("%s: keine Quelle (Datei:Zeile)" % anker)
        if eintrag.sorte == ef.SORTE_SCHULDSTAND and len(eintrag.trigger.strip()) < 20:
            maengel.append(
                "%s: Schuldstand ohne Aufloesungs-Trigger — dann ist es eine "
                "Entscheidung (sorte='ausnahme') oder ein Fehler" % anker)
        if eintrag.sorte == ef.SORTE_AUSNAHME and eintrag.trigger.strip():
            maengel.append(
                "%s: Ausnahme MIT Trigger — eine Entscheidung hat kein "
                "Verfallsdatum; das ist ein Schuldstand" % anker)
    assert not maengel, "Ausnahme-Liste ist nicht wohlgeformt:\n" + "\n".join(
        "  - %s" % m for m in maengel)


def test_ausnahmen_sind_noch_real():
    """Sanitaets-Check: jeder Ausnahme-Eintrag beschreibt einen Sachverhalt, den
    es noch gibt — sonst ist die Ausnahme veraltet und gehoert entfernt.

    Ohne diesen Test verrottet die Liste: ein behobener Befund bliebe als
    Freibrief stehen und deckte kuenftig einen NEUEN Fehler derselben Kennung
    stillschweigend ab. (Vorbild:
    `test_kein_pytest_suite_eintraege_existieren_noch`.)
    """
    aggregator = importlib.import_module("seiten.aggregator")
    aggregator_komponenten = {
        k for k, _c, _p in aggregator.discover_manifests(ef.REPO_ROOT)
    }
    noch_real = {
        ef.ACHSE_MANTEL: {b.kennung for b in ef.mantel_befunde()},
        ef.ACHSE_LADER: {b.kennung for b in ef.lader_befunde()},
        ef.ACHSE_PFAD: {b.kennung for b in ef.pfad_befunde()},
        # Anschluss-Ausnahme ist real, solange die Komponente existiert und
        # NICHT angeschlossen ist.
        ef.ACHSE_ANSCHLUSS: {
            k for k in aggregator_komponenten if ef.anschluss_fuer(k) is None
        },
        ef.ACHSE_GEGENRICHTUNG: {b.kennung for b in ef.gegenrichtung_befunde()},
        ef.ACHSE_ROUTE: {b.kennung for b in ef.route_befunde()},
    }
    veraltet = [
        "%s/%s (%s)" % (e.achse, e.kennung, e.quelle)
        for e in ef.AUSNAHMEN
        if e.kennung not in noch_real[e.achse]
    ]
    assert not veraltet, (
        "Veraltete Ausnahme-Eintraege — der beschriebene Sachverhalt existiert "
        "nicht mehr. Bitte aus tests/eltern_flaechen.py:AUSNAHMEN entfernen:\n"
        + "\n".join("  - %s" % v for v in veraltet)
    )


def test_befunde_sind_im_lauf_sichtbar(capsys):
    """Die Ausnahme-Liste steht in JEDEM Testlauf sichtbar (#1822 AC4).

    Als Daten gefuehrt und als Warnung ausgegeben werden die Befunde sichtbar,
    statt stumm zu bleiben. Jeder Schuldstand erzeugt eine `UserWarning` —
    die landet in pytests Warnungs-Zusammenfassung, auch unter `-q`.
    """
    zeilen = ["", "BEFUNDE UND AUSNAHMEN — Eltern-Flaechen (#1822)", "=" * 72]
    schuldstaende = 0
    for eintrag in ef.AUSNAHMEN:
        zeilen.append("[%s/%s] %s" % (eintrag.sorte, eintrag.achse, eintrag.kennung))
        zeilen.append("    Quelle:      %s" % eintrag.quelle)
        zeilen.append("    Begruendung: %s" % eintrag.begruendung)
        if eintrag.trigger:
            zeilen.append("    Trigger:     %s" % eintrag.trigger)
        if eintrag.sorte == ef.SORTE_SCHULDSTAND:
            schuldstaende += 1
            warnings.warn(
                "#1822 offener Befund [%s] %s | Quelle: %s | %s | Trigger: %s"
                % (eintrag.achse, eintrag.kennung, eintrag.quelle,
                   _gekuerzt(eintrag.begruendung), _gekuerzt(eintrag.trigger)),
                UserWarning, stacklevel=1)
    zeilen.append("=" * 72)
    print("\n".join(zeilen))

    ausgabe = capsys.readouterr().out
    assert "plan/views.json:26" in ausgabe, (
        "Der 404-Fund bei den Plan-Einstellungen muss im Lauf benannt werden "
        "(#1822 AC3) — sonst ist er wieder unsichtbar."
    )
    assert schuldstaende >= 1, "Kein Schuldstand ausgegeben — Sichtbarkeit ungeprueft."


def test_ohne_die_ausnahme_liste_bleiben_genau_diese_befunde_offen(monkeypatch):
    """AC4-Form, behavioral geprueft: die Ausnahmen sind Daten, keine Verzweigung.

    Nimmt man die Liste weg, bleiben **genau** die dort gefuehrten Befunde
    offen — kein einziger mehr (dann waere ein Befund im Code weggezweigt) und
    kein einziger weniger (dann waere ein Eintrag Dekoration, die kuenftig
    einen NEUEN Fehler derselben Kennung stillschweigend abdeckte).

    Das ist zugleich die zweite Fehlerpfad-Probe: sie loest jeden
    dokumentierten Befund echt aus, statt seine Existenz zu behaupten. Fuenf
    der sechs Achsen machen einen offenen Befund rot; die Achse
    `gegenrichtung` verlangt nur seine Benennung (#1822 klammert ihren Bau
    aus) — offen ist er in beiden Faellen. Die Achse `route` (#1890) faehrt
    mit, obwohl sie heute keinen dokumentierten Befund traegt: sonst bliebe
    ein kuenftiger Routen-Eintrag von dieser Form-Probe ungeprueft.
    """
    erwartet = {(e.achse, e.kennung) for e in ef.AUSNAHMEN}
    monkeypatch.setattr(ef, "AUSNAHMEN", ())

    offen = set()
    for befund in (ef.mantel_luecken() + ef.anschluss_luecken()
                   + ef.gegenrichtung_luecken() + ef.route_luecken()
                   + [b for b in ef.pfad_befunde() if b.ausnahme is None]
                   + [b for b in ef.lader_befunde() if b.ausnahme is None]):
        offen.add((befund.achse, befund.kennung))

    assert offen == erwartet, (
        "Ohne Ausnahme-Liste erwartete Befunde: %s\ntatsaechlich: %s\n"
        "Differenz (nur erwartet): %s\nDifferenz (nur tatsaechlich): %s"
        % (sorted(erwartet), sorted(offen),
           sorted(erwartet - offen), sorted(offen - erwartet))
    )
