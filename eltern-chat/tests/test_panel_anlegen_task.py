"""Tests für »Panel anlegen« (PAA-1…PAA-8, Refs #183/#138/#141/#389).

Mindest-Abdeckung nach `specs/platform/panel-anlegen.md` PAA-8 — reproduzierbar
und ohne Netz: Telegram, Panel-Registry, Geräte-Registry und Seiten-Registry
werden durch kontrollierte Doppelungen ersetzt (Pattern wie GAA-8 / TES-10).

#389-Anpassung: `seiten_client` wird jetzt als Test-Naht übergeben.
Vollabdeckung des neuen Registry-Pfads ist in test_panel_anlegen.py.

Drei Schichten:
- **Skill-Verhalten** (PAA-1..4, PAA-7): `panel_anlegen(...)` direkt getrieben
  über einen `stream()`-Eingabe-Strom + Fake-Clients.
- **Aufgabe** (PAA-5): `PanelAnlegenTask` (WriteTask, async) + Katalog-Guard.
- **Routing** (PAA-6, TASK-7): ein Privatchat-Update wird durch `handle_update`
  über die geteilte `paa_sessions`-Map an den PAA-Worker geroutet — analog
  `test_handle_update_routes_to_tes_session`. Routing-Test-ID:
  `test_PAA6_handle_update_routes_to_paa_session`.
"""

import os
import tempfile
import time

from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from history import History
from main import Context, handle_update
from skills.panel_anlegen import (
    CANCELLED,
    GERAETE_FEHLER,
    KEINE_DISPLAYS,
    NOT_AUTHORIZED,
    PaaInput,
    normalisiere_slug,
    panel_anlegen,
)
from skills.panel_anlegen_task import PaaSession, PanelAnlegenTask, make_paa_input
from skills.panel_client import GeraeteReadError, PanelClientError
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Test-Doppelungen
# ============================================================

class FakePanelClient:
    """In-Memory-Doppelung des PanelClient — ohne HTTP, ohne panel/-Import.

    Der Server vergibt die `panel_id`; die Doppelung baut sie aus dem `slug`
    (analog `registry.neue_id`, aber lokal) und spiegelt PAA-4: sie leitet die
    `config`-Identität selbst ab, damit der Test die Server-Autorität abbildet.
    """

    def __init__(self, anlage_error=None, anlage_responses=None):
        self._anlage_error = anlage_error
        self._anlage_responses = list(anlage_responses or [])
        self.calls = []
        self._sequence = {}

    def panel_anlegen(self, slug, display_id, tiles, config=None):
        self.calls.append({
            "slug": slug, "display_id": display_id, "tiles": tiles,
            "config": config,
        })
        if self._anlage_error is not None:
            raise self._anlage_error
        if self._anlage_responses:
            return self._anlage_responses.pop(0)
        nr = self._sequence.get(slug, 0) + 1
        self._sequence[slug] = nr
        panel_id = "%s-%02d" % (slug, nr)
        return {
            "panel_id": panel_id,
            "display_id": display_id,
            "source_id": "app-panel:%s" % panel_id,
            "config": {"source_id": "app-panel:%s" % panel_id,
                       "display_id": display_id, "router_url": ""},
            "tiles": tiles,
        }


class FakeGeraeteDisplayClient:
    """In-Memory-Doppelung des GeraeteDisplayClient — liefert die Display-Liste
    (GER-13, bereits auf `verwendung: display` gefiltert) oder wirft."""

    def __init__(self, displays=None, error=None):
        self._displays = list(displays or [])
        self._error = error
        self.calls = 0

    def displays(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._displays)


class FakeSeitenClient:
    """In-Memory-Doppelung des SeitenClient für PAA-3.3-Tests (#389).

    get_kandidaten() gibt eine Liste von Registry-Kandidaten-Dicts zurück
    (AC1: kein APP_KANDIDATEN mehr). Test-Naht analog FakeGeraeteDisplayClient.
    """

    def __init__(self, kandidaten=None, error=None):
        self._kandidaten = list(kandidaten or _kandidaten_standard())
        self._error = error
        self.calls = 0

    def get_kandidaten(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return list(self._kandidaten)


def _kandidaten_standard():
    """Zwei Kandidaten analog der früheren APP_KANDIDATEN-Einträge."""
    return [
        {"app": "wetter", "view": "heute", "label": "Wetter heute",
         "name": "Wetter heute", "icons": ["arasaac/24721.png"]},
        {"app": "plan", "view": "woche", "label": "Wochenplan",
         "name": "Wochenplan", "icons": ["arasaac/32488.png"]},
        {"app": "plan", "view": "woche", "label": "Wochenplan für Kleinkinder",
         "name": "Wochenplan für Kleinkinder",
         "icons": ["arasaac/32488.png", "arasaac/2484.png"],
         "query": {"ansicht": "klein"}},
    ]


def _displays_zwei():
    return [
        {"id": "pi-display-flur-01", "name": "Pi-Display Flur",
         "verwendung": "display"},
        {"id": "monitor-kueche-01", "name": "Monitor Küche",
         "verwendung": "display"},
    ]


def stream(*items):
    """Baut eine `next_message`-Funktion aus einer Folge von PaaInput/Strings.
    Strings sind Kurzform für `PaaInput(text=string)`; ist die Folge erschöpft,
    liefert `next_message()` `None` (Abbruch-Vertrag)."""
    box = list(items)

    def next_message():
        if not box:
            return None
        item = box.pop(0)
        return PaaInput(text=item) if isinstance(item, str) else item
    return next_message


def _member_tg(user_id=7):
    return FakeTelegram(members={user_id: {"status": "member"}})


def _vollanlage():
    """Vollständige Antwort-Folge PAA-3.1..3.4 — Display 1, Slug »Küche«,
    App 1 (Wetter), Bestätigung."""
    return ["1", "Küche", "1", "ok"]


# ============================================================
#  PAA-1 — Aufruf-Schnittstelle
# ============================================================

def test_PAA1_erfolg_liefert_panel_id_und_controller_url():
    """PAA-1: ein Durchlauf liefert das Ergebnis-Signal mit der vergebenen
    `panel_id` und der Controller-URL `/controller/app-panel/<panel_id>`."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    tg = _member_tg()
    result = panel_anlegen(tg, chat_id=7, user_id=7, family_group_chat_id=200,
                           panel_client=panel, geraete_client=geraete,
                           next_message=stream(*_vollanlage()),
                           seiten_client=FakeSeitenClient())
    assert result.authorized is True
    assert result.panel_id == "kueche-01"
    assert result.controller_url == "/controller/app-panel/kueche-01"
    assert len(panel.calls) == 1


def test_PAA1_controller_url_mit_origin():
    """PAA-3.5: mit Origin hängt die Funktion ihn an die Controller-URL."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    result = panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                           stream(*_vollanlage()),
                           seiten_client=FakeSeitenClient(),
                           controller_url_origin="https://hub.local")
    assert result.controller_url == "https://hub.local/controller/app-panel/kueche-01"


def test_PAA1_abbruch_bei_bestaetigung_schreibt_nichts():
    """PAA-1/PAA-3.4: Abbruch in der Bestätigung → kein POST, panel_id None."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    tg = _member_tg()
    result = panel_anlegen(tg, 7, 7, 200, panel, geraete,
                           stream("1", "Küche", "1", "nein"),
                           seiten_client=FakeSeitenClient())
    assert result.panel_id is None
    assert panel.calls == []
    assert any(s["text"] == CANCELLED for s in tg.sent)


# ============================================================
#  PAA-2 — Berechtigung live geprüft
# ============================================================

def test_PAA2_nicht_mitglied_wird_abgewiesen():
    """PAA-2: ein Nicht-Familien-Mitglied wird abgelehnt; kein POST."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    tg = FakeTelegram(members={})   # niemand ist Mitglied
    result = panel_anlegen(tg, 7, 7, 200, panel, geraete,
                           stream(*_vollanlage()),
                           seiten_client=FakeSeitenClient())
    assert result.authorized is False
    assert result.panel_id is None
    assert panel.calls == []
    assert geraete.calls == 0   # gar nicht erst zur Display-Liste gekommen
    assert any(s["text"] == NOT_AUTHORIZED for s in tg.sent)


# ============================================================
#  PAA-3 — Datenerfassung in fester Reihenfolge
# ============================================================

def test_PAA3_display_auswahl_per_id_moeglich():
    """PAA-3.1: die display_id selbst (statt der Nummer) wird akzeptiert."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    result = panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                           stream("monitor-kueche-01", "Küche", "1", "ok"),
                           seiten_client=FakeSeitenClient())
    assert panel.calls[0]["display_id"] == "monitor-kueche-01"
    assert result.panel_id == "kueche-01"


def test_PAA3_invalide_display_wiederholt_frage():
    """PAA-3.1/PAA-7: eine Antwort außerhalb der Liste wird abgewiesen, die
    Frage wiederholt — dann eine gültige Nummer."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    tg = _member_tg()
    result = panel_anlegen(tg, 7, 7, 200, panel, geraete,
                           stream("99", "1", "Küche", "1", "ok"),
                           seiten_client=FakeSeitenClient())
    assert result.panel_id == "kueche-01"
    # Die Display-Frage erschien zweimal (Erst-Frage + Wiederholung).
    from skills.panel_anlegen import DISPLAY_LISTE_KOPF
    display_prompts = [s for s in tg.sent if DISPLAY_LISTE_KOPF in s["text"]]
    assert len(display_prompts) == 2


def test_PAA3_invalider_slug_wiederholt_frage():
    """PAA-3.2/PAA-7: eine nach Normalisierung leere Eingabe wird abgewiesen."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    result = panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                           stream("1", "!!!", "Küche", "1", "ok"),
                           seiten_client=FakeSeitenClient())
    assert result.panel_id == "kueche-01"
    assert panel.calls[0]["slug"] == "kueche"


def test_PAA3_apps_mehrfachauswahl_in_reihenfolge():
    """PAA-3.3: »1,2« wählt beide Apps aus dem Registry-Inventar; die Reihenfolge
    ist die Anzeige-Reihenfolge (PANEL-3); tiles tragen die PANEL-3-Pflichtfelder.
    AC1: icons[] aus Registry (_kandidaten_standard)."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                  stream("1", "Küche", "1,2", "ok"),
                  seiten_client=FakeSeitenClient())
    tiles = panel.calls[0]["tiles"]["tiles"]
    assert [t["app"] for t in tiles] == ["wetter", "plan"]
    for t in tiles:
        for feld in ("key", "app", "view", "label", "icons", "sichtbar"):
            assert feld in t, "PANEL-3-Pflichtfeld %s fehlt" % feld
        assert isinstance(t["icons"], list) and t["icons"]
        assert t["sichtbar"] is True


def test_PAA33_kleinkind_plan_kachel_traegt_query_ansicht_klein():
    """PAA-3.3 / PLAN-3 / AC2: die Kleinkind-Plan-Kachel (Kandidat 3 in
    _kandidaten_standard) trägt query={ansicht: klein} aus dem Registry-Eintrag
    — keine zweite Wahrheit im Skill mehr (APP_KANDIDATEN entfernt, #389)."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                  stream("1", "Küche", "3", "ok"),
                  seiten_client=FakeSeitenClient())
    tiles = panel.calls[0]["tiles"]["tiles"]
    assert len(tiles) == 1
    assert tiles[0]["app"] == "plan" and tiles[0]["view"] == "woche"
    # query kommt aus dem Registry-Kandidaten (AC2)
    assert tiles[0]["query"] == {"ansicht": "klein"}
    # Kandidat 2 (Wochenplan ohne query) hat kein query-Feld
    panel2 = FakePanelClient()
    panel_anlegen(_member_tg(), 7, 7, 200, panel2, geraete,
                  stream("1", "Küche", "2", "ok"),
                  seiten_client=FakeSeitenClient())
    tiles2 = panel2.calls[0]["tiles"]["tiles"]
    assert "query" not in tiles2[0]


def test_PAA3_invalide_app_auswahl_wiederholt_frage():
    """PAA-3.3/PAA-7: eine Eingabe ohne gültige Nummer wiederholt die Frage."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    result = panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                           stream("1", "Küche", "abc", "1", "ok"),
                           seiten_client=FakeSeitenClient())
    assert result.panel_id == "kueche-01"


def test_PAA3_skill_liefert_keine_panel_id_uebernimmt_server_id():
    """PAA-3/PAA-4: der Skill sendet KEINE panel_id; er übernimmt die
    server-vergebene aus der PREG-15-Antwort."""
    panel = FakePanelClient(anlage_responses=[{"panel_id": "server-vergeben-07"}])
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    result = panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                           stream(*_vollanlage()),
                           seiten_client=FakeSeitenClient())
    # Der POST-Body trägt keine panel_id.
    assert "panel_id" not in panel.calls[0]
    assert result.panel_id == "server-vergeben-07"
    assert result.controller_url == "/controller/app-panel/server-vergeben-07"


# ============================================================
#  PAA-4 — Server leitet config-Identität ab; Skill sendet keine
# ============================================================

def test_PAA4_skill_sendet_keine_config_identitaet():
    """PAA-4: der an PREG-15 gesendete Body enthält {slug, display_id, tiles}
    und KEINE config-Identität (source_id/display_id/router_url)."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    panel_anlegen(_member_tg(), 7, 7, 200, panel, geraete,
                  stream(*_vollanlage()),
                  seiten_client=FakeSeitenClient())
    call = panel.calls[0]
    assert set(("slug", "display_id", "tiles")).issubset(call.keys())
    # Der Skill gibt config=None weiter (keine Identität, kein Tuning).
    assert call["config"] is None


# ============================================================
#  PAA-7 — Fehlerfälle
# ============================================================

def test_PAA7_geraete_registry_nicht_erreichbar():
    """PAA-7: GER-13-Lesefehler beendet ohne Wirkung; kein POST."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(error=GeraeteReadError("kaputt"))
    tg = _member_tg()
    result = panel_anlegen(tg, 7, 7, 200, panel, geraete, stream("1"),
                           seiten_client=FakeSeitenClient())
    assert result.panel_id is None
    assert panel.calls == []
    assert any(s["text"] == GERAETE_FEHLER for s in tg.sent)


def test_PAA7_kein_display_geraet():
    """PAA-7/PAA-3.1: keine `verwendung: display`-Geräte → Voraussetzung nennen
    und beenden (E-PAA-3), kein POST."""
    panel = FakePanelClient()
    geraete = FakeGeraeteDisplayClient(displays=[])
    tg = _member_tg()
    result = panel_anlegen(tg, 7, 7, 200, panel, geraete, stream("1"),
                           seiten_client=FakeSeitenClient())
    assert result.panel_id is None
    assert panel.calls == []
    assert any(s["text"] == KEINE_DISPLAYS for s in tg.sent)


def test_PAA7_preg15_lehnt_ab():
    """PAA-7: PREG-15 lehnt ab (PanelClientError) → Misserfolg, nichts
    geschrieben (Fake hebt den Fehler im POST)."""
    panel = FakePanelClient(anlage_error=PanelClientError("HTTP 400"))
    geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    tg = _member_tg()
    result = panel_anlegen(tg, 7, 7, 200, panel, geraete,
                           stream(*_vollanlage()),
                           seiten_client=FakeSeitenClient())
    assert result.panel_id is None
    from skills.panel_anlegen import WRITE_FAILED
    assert any(s["text"] == WRITE_FAILED for s in tg.sent)


def test_normalisiere_slug():
    """PAA-3.2: Slug-Normalisierung (Umlaute, Sonderzeichen, leere Eingabe)."""
    assert normalisiere_slug("Küche") == "kueche"
    assert normalisiere_slug("Flur-Tablet!") == "flur-tablet"
    assert normalisiere_slug("  Mama iPhone  ") == "mama-iphone"
    assert normalisiere_slug("!!!") == ""
    assert normalisiere_slug("") == ""


# ============================================================
#  PAA-5 — Aufgabe (WriteTask, async) + propose/execute
# ============================================================

def _make_task(sessions=None, panel_client=None, geraete_client=None,
               seiten_client=None, tg=None):
    if sessions is None:
        sessions = {}
    if panel_client is None:
        panel_client = FakePanelClient()
    if geraete_client is None:
        geraete_client = FakeGeraeteDisplayClient(displays=_displays_zwei())
    if seiten_client is None:
        seiten_client = FakeSeitenClient()
    if tg is None:
        tg = _member_tg(42)
    return PanelAnlegenTask(
        tg, "http://test-panel", "http://test-geraete", sessions,
        family_group_chat_id_getter=lambda: 200,
        panel_client=panel_client, geraete_client=geraete_client,
        seiten_client=seiten_client)


def test_PAA5_ist_write_task_und_async():
    task = _make_task()
    assert isinstance(task, WriteTask)
    assert task.name == "panel_anlegen"
    assert task.is_async is True


def test_PAA5_propose_kontextabhaengig():
    task = _make_task()
    aus_gruppe = task.propose({}, TurnContext(chat_id=200, from_user_id=42,
                                              private_chat_id=42))
    im_privat = task.propose({}, TurnContext(chat_id=42, from_user_id=42,
                                             private_chat_id=42))
    assert isinstance(aus_gruppe, Proposal) and "Privatchat" in aus_gruppe.summary
    assert isinstance(im_privat, Proposal) and "Privatchat" not in im_privat.summary


def test_PAA5_execute_startet_session():
    sessions = {}
    task = _make_task(sessions=sessions)
    quittung = task.execute({}, TurnContext(chat_id=200, from_user_id=42,
                                            private_chat_id=42))
    assert quittung and isinstance(quittung, str)
    assert 42 in sessions
    # Worker abklingen lassen (er blockiert in next_message → bricht ab).
    time.sleep(0.05)
    sessions.pop(42, None)


def test_PAA5_execute_kein_privatchat():
    task = _make_task()
    quittung = task.execute({}, TurnContext(chat_id=200, from_user_id=None,
                                            private_chat_id=None))
    assert "Privatchat" in quittung or "privat" in quittung.lower()


def test_PAA5_execute_session_laeuft_schon():
    sessions = {42: object()}
    task = _make_task(sessions=sessions)
    quittung = task.execute({}, TurnContext(chat_id=200, from_user_id=42,
                                            private_chat_id=42))
    assert quittung
    assert isinstance(sessions[42], object)


def test_make_paa_input():
    from telegram import IncomingMessage
    msg = IncomingMessage(
        update_id=1, chat_id=42, chat_type="private", message_id=10,
        from_user_id=7, from_user_name="test", text="1",
        images=[], reply_to_message_id=None, reply_to_from_bot=False,
        mentions_bot=False)
    assert make_paa_input(msg).text == "1"


def test_PaaSession_prefix():
    assert PaaSession.THREAD_NAME_PREFIX == "paa"
    assert PaaSession.LOG_PREFIX == "PAA"


# ============================================================
#  Befund-2-Integrations-Test — Entry-Path handle_update → SeitenClient
# ============================================================

def test_ENTRY_PATH_execute_durchreicht_seiten_client_bis_panel_anlegen():
    """Entry-Path-Integration: PanelAnlegenTask.execute() → PaaSession →
    panel_anlegen → SeitenClient.get_kandidaten() (Befund 2, #389).

    Prüft, dass der seiten_client vom Worker korrekt durchgereicht wird:
    - FakeSeitenClient.calls == 1 nach einem vollständigen Durchlauf.
    - FakePanelClient.calls[0].tiles enthält App/View aus den Stub-Kandidaten
      der Registry (AC1: nicht aus einem lokalen APP_KANDIDATEN).

    Ablauf: Display 1, Slug „Küche", App 1 (Wetter, aus _kandidaten_standard),
    Bestätigungswort → panel_anlegen schreibt eine Panel-Instanz.
    """
    fake_seiten = FakeSeitenClient()
    fake_panel = FakePanelClient()
    fake_geraete = FakeGeraeteDisplayClient(displays=_displays_zwei())
    sessions = {}
    tg = _member_tg(42)

    task = PanelAnlegenTask(
        tg, "http://test-panel", "http://test-geraete", sessions,
        family_group_chat_id_getter=lambda: 200,
        panel_client=fake_panel,
        geraete_client=fake_geraete,
        seiten_client=fake_seiten)

    # execute() startet den Worker-Thread und gibt sofort eine Quittung zurück.
    quittung = task.execute({}, TurnContext(chat_id=200, from_user_id=42,
                                            private_chat_id=42))
    assert quittung and isinstance(quittung, str)

    # Worker ist jetzt gestartet; Session wartet in next_message() auf Eingaben.
    deadline = time.monotonic() + 1.0
    while 42 not in sessions and time.monotonic() < deadline:
        time.sleep(0.005)
    assert 42 in sessions, "PaaSession wurde nicht in sessions eingetragen"
    session = sessions[42]

    # Antwort-Folge aus _vollanlage() als PaaInput delivern.
    for antwort in _vollanlage():
        # Warten bis Worker auf next_message() blockiert, dann liefern.
        time.sleep(0.02)
        session.deliver(PaaInput(text=antwort))

    # Warten bis Worker fertig ist (Session beendet sich nach panel_anlegen).
    fertig_deadline = time.monotonic() + 3.0
    while not session.is_finished() and time.monotonic() < fertig_deadline:
        time.sleep(0.01)

    assert session.is_finished(), "PaaSession wurde nicht beendet — Worker hängt?"

    # Kern-Assertion: SeitenClient wurde genau einmal aufgerufen (Durchreichung).
    assert fake_seiten.calls == 1, (
        "SeitenClient.get_kandidaten() hätte genau einmal aufgerufen werden "
        "müssen — tatsächlich: %d" % fake_seiten.calls)

    # PanelClient wurde aufgerufen — tiles kommen aus den Registry-Kandidaten.
    assert len(fake_panel.calls) == 1, "PanelClient wurde nicht aufgerufen"
    tiles = fake_panel.calls[0]["tiles"]["tiles"]
    assert len(tiles) == 1
    assert tiles[0]["app"] == "wetter", (
        "Erster Kandidat aus _kandidaten_standard ist Wetter — tiles[0].app: %s"
        % tiles[0]["app"])
    assert tiles[0]["view"] == "heute"


# ============================================================
#  PAA-5 — Katalog-Registrierung (AND-Guard)
# ============================================================

def _with_ca_pem(fn):
    """Hilft den Katalog-Tests: CaVerteilungTask liest die CA-PEM-Datei beim
    Bau — wir legen eine temporäre an."""
    ca_pem = tempfile.mktemp(suffix=".pem")
    try:
        with open(ca_pem, "w") as f:
            f.write("fake-pem")
        return fn(ca_pem)
    finally:
        try:
            os.unlink(ca_pem)
        except OSError:
            pass


def test_PAA5_registriert_wenn_alle_abhaengigkeiten():
    """PAA-5: PanelAnlegenTask erscheint im Katalog, wenn panel_origin_url,
    geraete_origin_url, seiten_origin_url, paa_sessions UND
    family_group_chat_id_getter da sind."""
    def _check(ca_pem):
        catalog = build_catalog(
            FakeTelegram(), ca_pem,
            geraete_origin_url="http://127.0.0.1:5040",
            panel_origin_url="http://127.0.0.1:5041",
            seiten_origin_url="http://127.0.0.1:5042",
            paa_sessions={},
            family_group_chat_id_getter=lambda: 200)
        task = catalog.get("panel_anlegen")
        assert task is not None and isinstance(task, WriteTask)
    _with_ca_pem(_check)


def test_PAA5_nicht_registriert_ohne_seiten_origin_url():
    """PAA-5 / Watchdog-Befund 1: PanelAnlegenTask ist NICHT im Katalog, wenn
    seiten_origin_url fehlt — Dialog-Falle vermeiden (leere Kandidaten-Liste
    würde erst im Dialog scheitern, nicht beim Guard). Symmetrisch zur SUE-Form."""
    def _check(ca_pem):
        catalog = build_catalog(
            FakeTelegram(), ca_pem,
            geraete_origin_url="http://127.0.0.1:5040",
            panel_origin_url="http://127.0.0.1:5041",
            paa_sessions={},
            family_group_chat_id_getter=lambda: 200)
        assert catalog.get("panel_anlegen") is None
    _with_ca_pem(_check)


def test_PAA5_nicht_registriert_ohne_panel_origin():
    def _check(ca_pem):
        catalog = build_catalog(
            FakeTelegram(), ca_pem,
            geraete_origin_url="http://127.0.0.1:5040",
            paa_sessions={},
            family_group_chat_id_getter=lambda: 200)
        assert catalog.get("panel_anlegen") is None
    _with_ca_pem(_check)


def test_PAA5_nicht_registriert_ohne_paa_sessions():
    def _check(ca_pem):
        catalog = build_catalog(
            FakeTelegram(), ca_pem,
            geraete_origin_url="http://127.0.0.1:5040",
            panel_origin_url="http://127.0.0.1:5041",
            family_group_chat_id_getter=lambda: 200)
        assert catalog.get("panel_anlegen") is None
    _with_ca_pem(_check)


def test_PAA5_nicht_registriert_ohne_fgcid():
    def _check(ca_pem):
        catalog = build_catalog(
            FakeTelegram(), ca_pem,
            geraete_origin_url="http://127.0.0.1:5040",
            panel_origin_url="http://127.0.0.1:5041",
            paa_sessions={})
        assert catalog.get("panel_anlegen") is None
    _with_ca_pem(_check)


# ============================================================
#  PAA-6 / TASK-7 — Routing-Test durch handle_update
# ============================================================

def _ctx_with_paa_session(tmp_path, tg, paa_sessions, family_group_chat_id="-100"):
    """Minimaler Context für den handle_update-Routing-Test (PAA-6).

    Analog `_ctx_with_tes_session` in `test_termin_eintragen_task.py`: Context
    trägt eine `paa_sessions`-Map, damit handle_update eingehende
    Privatchat-Updates an die laufende Session leitet — DIESELBE Map, mit der
    der Katalog die Aufgabe verkabelt (PAA-6, die stille Lego-Falle ohne sie)."""
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        geraete_origin_url="http://test-geraete",
        panel_origin_url="http://test-panel",
        seiten_origin_url="http://test-seiten",
        paa_sessions=paa_sessions,
        family_group_chat_id_getter=lambda: family_group_chat_id)
    return Context(
        tg=tg,
        bot_username="mybot",
        family_group_chat_id=family_group_chat_id,
        context_depth=20,
        provider=FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "paa_routing.db")),
        pending=PendingStore(),
        paa_sessions=paa_sessions)


def test_PAA6_handle_update_routes_to_paa_session(tmp_path):
    """PAA-6 / TASK-7: läuft eine PAA-Session in einem Privatchat, gehen
    eingehende Privatchat-Updates über die geteilte `paa_sessions`-Map an den
    PAA-Worker (statt zum Agenten) — analog test_handle_update_routes_to_tes.

    Prüft, dass handle_update `session.deliver()` aufruft, wenn eine aktive
    PAA-Session für den eingehenden chat_id existiert. Die Nachricht landet
    NICHT beim Agenten (FakeProvider bleibt ohne Aufruf)."""
    user_id = 42
    tg = FakeTelegram(members={user_id: {"status": "member"}})
    paa_sessions = {}
    ctx = _ctx_with_paa_session(tmp_path, tg, paa_sessions)

    # Session manuell starten: eine PaaSession in die Map eintragen.
    session = PaaSession(chat_id=user_id)
    paa_sessions[user_id] = session

    delivered = []

    def _run():
        msg = session.next_message()
        if msg is not None:
            delivered.append(msg)

    session.start(_run, ())
    # Warten, bis der Worker-Thread auf next_message() blockiert.
    time.sleep(0.05)

    # handle_update aufrufen — Privatchat-Nachricht von user_id.
    msg = make_message("Küche", chat_id=user_id, from_user_id=user_id,
                       chat_type="private", message_id=200)
    handle_update(msg, ctx)

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not delivered:
        time.sleep(0.01)

    assert delivered, (
        "handle_update hätte die Privatchat-Nachricht an paa_sessions[%s].deliver() "
        "leiten müssen — stattdessen wurde sie nicht zugestellt" % user_id)
    assert delivered[0].text == "Küche"
    assert not tg.sent, (
        "Der Agent hätte bei laufender PAA-Session nicht antworten dürfen")
