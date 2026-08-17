"""Guard: jeder HTTP-Dienst hat eine Gesundheitsabfrage (SVC-1, #1623).

Hintergrund: `xbuddy-plan` (5020) und `xbuddy-photo` (5051) hatten keine
`/healthz`-Route. Beide antworteten mit **404** — und der Alerting-Poller kannte
sie deshalb gar nicht erst. Der Waechter meldete jahrelang „alles gruen", waehrend
zwei von zwoelf Diensten ausserhalb seines Blickfelds lagen.

Doppelt unangenehm: das Auslieferungs-Skript stuft genau dieses 404 als Warnung
statt als Fehler ein — der Falsch-gruen-Schutz griff fuer die beiden also
ebenfalls nicht.

Das ist die **Auslassungs-Klasse**: nicht „ist das Vorhandene richtig", sondern
„fehlt etwas". Ein Dienst ohne `/healthz` faellt niemandem auf, weil nichts nach
ihm fragt. Dieser Test fragt.

Er prueft die **echten** Flask-Apps ueber ihre `url_map`, keine Nachbildung — und
faengt damit auch eine Route, die zwar existiert, aber unter einem anderen Pfad
registriert wurde.
"""

import importlib

import pytest

# Dieselbe Landkarte wie die AUTH-11-Verriegelung: alle Komponenten mit
# HTTP-Stack. Bot-Dienste ohne Flask (eltern-chat) tragen stattdessen einen
# Heartbeat (SVC-8) und stehen deshalb hier nicht.
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


@pytest.mark.parametrize("service", sorted(SERVICE_MODULE))
def test_jeder_dienst_hat_healthz(service):
    """SVC-1: jede Komponente mit HTTP-Stack beantwortet `/healthz`."""
    app = importlib.import_module(SERVICE_MODULE[service]).app
    regeln = {r.rule for r in app.url_map.iter_rules()}
    assert "/healthz" in regeln, (
        "%s hat keine /healthz-Route (SVC-1). Folge: der Alerting-Poller "
        "bekommt 404 und kann den Dienst nicht ueberwachen — ein Ausfall bliebe "
        "unbemerkt.\nVorbild: wetter/main.py, Abschnitt Health-Check (SVC-1)."
        % service
    )


@pytest.mark.parametrize("service", sorted(SERVICE_MODULE))
def test_healthz_antwortet_mit_200_und_ohne_anmeldung(service):
    """`/healthz` bleibt unauthentifiziert (auth.md:227) und liefert 200.

    Die Anmeldefreiheit ist kein Versehen, sondern Vertrag: die Ueberwachung
    fragt **vor** jeder Anmeldung. Waere die Route gegatet, bekaeme der Poller
    401 statt 200 und wuerde einen gesunden Dienst als tot melden — ein
    Fehlalarm, der schlimmer ist als keiner, weil er Alarme entwertet.
    """
    app = importlib.import_module(SERVICE_MODULE[service]).app
    antwort = app.test_client().get("/healthz")
    assert antwort.status_code == 200, (
        "%s: /healthz antwortet mit %d statt 200. Bei 401/403 steht die Route "
        "faelschlich hinter dem Gate (auth.md:227 nimmt sie ausdruecklich aus)."
        % (service, antwort.status_code)
    )
