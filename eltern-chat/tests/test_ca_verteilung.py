"""Tests für die CA-Verteilung — CAV-1 … CAV-7, EC-29 (Refs #39, #63, #95, #551).

Geprüft wird das Code-Verhalten der CA-Verteilung: die aufrufbare Funktion
selbst (ca_verteilung) und ihr Trigger als EC-8-Aufgabe (`ca_task`,
CAV-6). Telegram ist durch die kontrollierte Doppelung `FakeTelegram` ersetzt
— die Tests laufen reproduzierbar und ohne Netz (CAV-7, analog EC-17/ONB-9).

EC-29 / TASK-10 (CAV-4): Datei-Anhang-Sonderfall.
- tg.send_document: bleibt (Datei sendet der Skill — technische Notwendigkeit).
- tg.send_message / tg.sent: leer in allen Pfaden — Text-Teil ist Tool-Result.
- verteile_ca() returnt CaVerteilungResult.tool_result_text mit OS-Anleitung.
- CaVerteilungTask.run() gibt tool_result_text direkt zurück (kein _QUITTUNG).
"""

import inspect

import pytest
from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message, task_call_response, text_response
from history import History
from main import Context, handle_update
from model import READ
from skills import ca_verteilung
from skills.ca_task import CaVerteilungTask
from skills.ca_verteilung import SUPPORTED_GERAETE, CaVerteilungError, CaVerteilungResult, verteile_ca
from tasks import TurnContext, build_catalog
from telegram import TelegramError

# Ein realistisches öffentliches Root-CA-Zertifikat (Inhalt belanglos — nur die
# PEM-Hülle zählt für die Auslieferung). KEIN Privatschlüssel.
_PUBLIC_CA_PEM = (b"-----BEGIN CERTIFICATE-----\n"
                  b"MIIBkTCB+wIJANxbuddyTESTca0wDQYJKoZIhvcNAQEL\n"
                  b"-----END CERTIFICATE-----\n")

# Eine Datei MIT Privatschlüssel — die CA-Verteilung darf so etwas nie senden.
_PRIVATE_KEY_PEM = (b"-----BEGIN PRIVATE KEY-----\n"
                    b"MIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n"
                    b"-----END PRIVATE KEY-----\n")


def _write_ca(tmp_path, content=_PUBLIC_CA_PEM, name="rootCA.pem"):
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _ctx(tmp_path, tg, ca_pem_path, provider=None):
    """Context für die Orchestrierungs-Tests des Aufgaben-Wegs (CAV-6).

    Der Katalog enthält die CA-Verteilungs-Aufgabe — wie zur Laufzeit von
    `build_catalog` verdrahtet (#63)."""
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20,
        provider=provider if provider is not None else FakeProvider([]),
        catalog=build_catalog(tg, ca_pem_path),
        history=History(str(tmp_path / "ca.db")), pending=PendingStore())


# ============================================================
#  CAV-1 — CA-Verteilung ist eine aufrufbare, trigger-agnostische Funktion
# ============================================================

def test_CAV_1_is_a_callable_function_returning_a_result(tmp_path):
    """verteile_ca ist eine aufrufbare Funktion und liefert ein Ergebnis.

    EC-29: result.tool_result_text enthält den Text-Teil (OS-Anleitung);
    guide_message_id existiert nicht mehr — der Text geht nicht via send_message.
    """
    tg = FakeTelegram()
    result = verteile_ca(tg, chat_id=42,
                         ca_pem_path=_write_ca(tmp_path), geraet="android")
    assert isinstance(result, CaVerteilungResult)
    assert result.chat_id == 42
    assert result.document_message_id is not None
    # EC-29: Text-Teil ist Tool-Result, nicht message_id
    assert isinstance(result.tool_result_text, str)
    assert len(result.tool_result_text) > 0


def test_CAV_1_function_does_not_know_its_caller(tmp_path):
    """E-CAV-1: der Aufrufer ist nicht Teil des Funktions-Vertrags. Die
    Signatur nimmt nur Kanal, Zielchat, Zertifikatspfad und Zielgerät —
    keinen Trigger, keinen Onboarding-Flow, keinen Befehls-Kontext."""
    params = list(inspect.signature(verteile_ca).parameters)
    assert params == ["tg", "chat_id", "ca_pem_path", "geraet"]


# ============================================================
#  CAV-2 — Zweck: Geräte-Vertrauen (das öffentliche CA-Zertifikat wird geliefert)
# ============================================================

def test_CAV_2_delivers_the_public_root_ca_certificate(tmp_path):
    """Die Funktion stellt dem Gerät genau das öffentliche Root-CA-Zertifikat
    bereit — den Trust-Anker, ohne den XBuddy-HTTPS-Seiten warnen."""
    tg = FakeTelegram()
    verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path), geraet="android")
    assert len(tg.documents) == 1
    doc = tg.documents[0]
    assert doc["file_bytes"] == _PUBLIC_CA_PEM
    assert b"BEGIN CERTIFICATE" in doc["file_bytes"]


# ============================================================
#  CAV-3 — Nur das öffentliche Zertifikat, nie ein Privatschlüssel
# ============================================================

def test_CAV_3_refuses_to_send_a_private_key(tmp_path):
    """Zeigt ca_pem_path versehentlich auf eine Schlüsseldatei, bricht die
    Funktion ab — ein Privatschlüssel wird nie ausgeliefert."""
    tg = FakeTelegram()
    key_path = _write_ca(tmp_path, content=_PRIVATE_KEY_PEM)
    try:
        verteile_ca(tg, chat_id=42, ca_pem_path=key_path, geraet="android")
        assert False, "verteile_ca hätte abbrechen müssen"
    except CaVerteilungError:
        pass
    assert tg.documents == []          # nichts gesendet
    assert tg.sent == []


def test_CAV_3_missing_certificate_file_aborts_cleanly(tmp_path):
    """Fehlt die Zertifikatsdatei, bricht die Funktion sauber ab — kein
    Teil-Versand, keine stumme Auslieferung."""
    tg = FakeTelegram()
    try:
        verteile_ca(tg, chat_id=42, ca_pem_path=str(tmp_path / "fehlt.pem"),
                    geraet="android")
        assert False, "verteile_ca hätte abbrechen müssen"
    except CaVerteilungError:
        pass
    assert tg.documents == []


def test_CAV_3_ca_pem_path_is_a_per_instance_config_value():
    """CAV-3: der Pfad zur CA-Datei ist ein Per-Instanz-Konfigurationswert mit
    Default UND Override-Pfad — keine reine Code-Konstante. Der Override-Pfad
    folgt seit #179 der Loader-Konvention `ELTERNCHAT_<KEY>` und wird durch
    das Schema (`DEFAULTS`) sichergestellt."""
    import config as config_mod
    assert "ca_pem_path" in config_mod.DEFAULTS
    assert config_mod.DEFAULTS["ca_pem_path"]                 # sinnvoller Default


def test_CAV_3_config_resolves_ca_pem_path(tmp_path, monkeypatch):
    """Die eltern-chat-Konfiguration löst ca_pem_path auf (Env > Datei > Default)."""
    import config as config_mod
    monkeypatch.setenv(config_mod.ENV_BOT_TOKEN, "t")
    monkeypatch.setenv("ELTERNCHAT_CA_PEM_PATH", "/instanz/rootCA.pem")
    cfg = config_mod.resolve(str(tmp_path / "config.json"))
    assert cfg.ca_pem_path == "/instanz/rootCA.pem"
    # Ohne Override greift der Default.
    monkeypatch.delenv("ELTERNCHAT_CA_PEM_PATH")
    cfg_default = config_mod.resolve(str(tmp_path / "config.json"))
    assert cfg_default.ca_pem_path == config_mod.DEFAULTS["ca_pem_path"]


# ============================================================
#  CAV-4 — Auslieferung über den Eltern-Chat-Bot
# ============================================================

def test_CAV_4_certificate_is_delivered_as_telegram_document(tmp_path):
    """Das Zertifikat geht als Datei (Telegram-Dokument) über den Bot-Kanal —
    an den übergebenen Zielchat, mit dem Dateinamen xbuddy-rootCA.crt (#75:
    `.pem` ist auf Windows keinem Cert-Handler zugeordnet, `.crt` ist der
    OS-übergreifende Standard; Inhalt bleibt PEM)."""
    tg = FakeTelegram()
    verteile_ca(tg, chat_id=777, ca_pem_path=_write_ca(tmp_path),
                geraet="android")
    assert len(tg.documents) == 1
    assert tg.documents[0]["chat_id"] == 777
    assert tg.documents[0]["file_name"] == "xbuddy-rootCA.crt"


def test_CAV_4_send_failure_is_reported_as_error(tmp_path):
    """Scheitert der Bot-Versand, meldet die Funktion das als CaVerteilungError —
    keine stille Nicht-Auslieferung."""
    tg = FakeTelegram(send_document_error=TelegramError("Kanal weg"))
    try:
        verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path),
                    geraet="android")
        assert False, "verteile_ca hätte den Sendefehler melden müssen"
    except CaVerteilungError:
        pass


def test_CAV_4_task_is_behind_the_group_membership_gate(tmp_path):
    """Der Aufgaben-Weg (CAV-6) liegt hinter der Live-Berechtigung (CAV-4,
    analog EC-2): von einem Nicht-Mitglied erreicht die Anfrage den Agenten
    gar nicht — kein Zertifikat, kein Anbieter-Aufruf."""
    tg = FakeTelegram(members={})           # niemand ist Mitglied
    provider = FakeProvider([])             # darf nicht aufgerufen werden
    ctx = _ctx(tmp_path, tg, _write_ca(tmp_path), provider=provider)
    handle_update(make_message("schick mir das Zertifikat", from_user_id=7), ctx)
    assert tg.documents == []
    assert tg.sent == []
    assert provider.requests == []


# ============================================================
#  CAV-5 — OS-spezifische Installations-Anleitung, hart-codiert,
#          Auslieferung gerätespezifisch (#95)
# ============================================================

def test_CAV_5_install_guide_covers_all_target_platforms_in_code(tmp_path):
    """Die Spec normiert das Soll: alle vier Plattformen sind im Code
    gleichgewichtig abgedeckt — die *Auslieferung* ist pro Aufruf
    gerätespezifisch (#95)."""
    # Jeder OS-Block existiert im Code und benennt die zugehörige Plattform.
    assert "Windows" in ca_verteilung._GUIDE_WINDOWS
    assert "Android" in ca_verteilung._GUIDE_ANDROID
    assert "iOS" in ca_verteilung._GUIDE_IOS and "iPadOS" in ca_verteilung._GUIDE_IOS
    assert "macOS" in ca_verteilung._GUIDE_MACOS


def test_CAV_5_install_guide_addresses_known_stumbling_blocks(tmp_path):
    """#77: pro OS müssen die im Real-Test 2026-05-22 belegten Stolpersteine
    benannt sein — sonst regrediert die Anleitung wieder zur dünnen Fassung.

    Marker je OS:
    - Windows: zweite Speicher-Frage „Vertrauenswürdige Stammzertifizierungsstellen"
      explizit auswählen + eigener Firefox-Speicher.
    - Android: PIN/Sperre-Voraussetzung und App-vs-Browser-Trust-Hinweis.
    - iOS/iPadOS: BEIDE Schritte (Profil-Installation UND Vertrauen aktivieren
      unter „Zertifikatsvertrauenseinstellungen").
    - macOS: Schlüsselbund „System" (nicht „Anmeldung") und „Immer vertrauen".
    """
    # Windows
    assert "Vertrauenswürdige Stammzertifizierungsstellen" in ca_verteilung._GUIDE_WINDOWS
    assert "Firefox" in ca_verteilung._GUIDE_WINDOWS
    # Android
    assert "CA-Zertifikat" in ca_verteilung._GUIDE_ANDROID
    # iOS / iPadOS
    assert "Zertifikatsvertrauenseinstellungen" in ca_verteilung._GUIDE_IOS
    # macOS
    assert "System" in ca_verteilung._GUIDE_MACOS
    assert "Immer vertrauen" in ca_verteilung._GUIDE_MACOS


def test_CAV_5_install_guide_needs_no_ai_provider(tmp_path):
    """Die Anleitung ist hart-codiert: derselbe Aufruf liefert deterministisch
    denselben Text — kein KI-Anbieter im Spiel.

    EC-29: Der Text ist jetzt im Tool-Result (result.tool_result_text), nicht
    in tg.sent — kein send_message-Aufruf.
    """
    tg1, tg2 = FakeTelegram(), FakeTelegram()
    r1 = verteile_ca(tg1, chat_id=1, ca_pem_path=_write_ca(tmp_path), geraet="ios")
    r2 = verteile_ca(tg2, chat_id=2, ca_pem_path=_write_ca(tmp_path), geraet="ios")
    # EC-29: kein send_message
    assert tg1.sent == []
    assert tg2.sent == []
    # Deterministisch und providerfrei
    assert r1.tool_result_text == r2.tool_result_text
    # Die Anleitung ist eine feste Modul-Konstante, kein generierter Text.
    assert r1.tool_result_text == ca_verteilung._GUIDE_IOS


# ------------------------------------------------------------
#  CAV-5 (#95) — `geraet` ist Pflicht-Eingabe, Auslieferung gerätespezifisch
# ------------------------------------------------------------

def test_CAV_5_geraet_is_required(tmp_path):
    """#95: ohne `geraet` ist der Aufruf ungültig. Nichts wird ausgeliefert —
    keine stille Default-Wahl, keine Vier-OS-Sammlung."""
    tg = FakeTelegram()
    with pytest.raises(ValueError):
        verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path),
                    geraet=None)
    assert tg.documents == []
    assert tg.sent == []


def test_CAV_5_unknown_geraet_is_rejected(tmp_path):
    """#95: ein OS-Wert außerhalb der Enum (z. B. das von der GAA
    unterstützte `linux`, das CAV in V1 nicht abdeckt) wird abgelehnt."""
    tg = FakeTelegram()
    with pytest.raises(ValueError):
        verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path),
                    geraet="linux")
    assert tg.documents == []
    assert tg.sent == []


@pytest.mark.parametrize("geraet,foreign_markers,own_marker", [
    ("windows",
     ("iPadOS", "Schlüsselbundverwaltung", "Android (12 / 13 / 14)"),
     "Vertrauenswürdige Stammzertifizierungsstellen"),
    ("android",
     ("Schlüsselbundverwaltung", "Zertifikatsvertrauenseinstellungen",
      "Vertrauenswürdige Stammzertifizierungsstellen"),
     "Android (12 / 13 / 14)"),
    ("ios",
     ("Schlüsselbundverwaltung", "Android (12 / 13 / 14)",
      "Vertrauenswürdige Stammzertifizierungsstellen"),
     "Zertifikatsvertrauenseinstellungen"),
    ("macos",
     ("iPadOS", "Android (12 / 13 / 14)",
      "Vertrauenswürdige Stammzertifizierungsstellen"),
     "Schlüsselbundverwaltung"),
])
def test_CAV_5_only_the_matching_block_is_delivered(
        tmp_path, geraet, foreign_markers, own_marker):
    """#95: pro Aufruf bekommt die Familie nur den passenden OS-Block,
    nicht alle vier auf einmal.

    EC-29: Die Anleitung ist im Tool-Result (result.tool_result_text),
    kein send_message — tg.sent bleibt leer.
    """
    tg = FakeTelegram()
    result = verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path), geraet=geraet)
    # EC-29: kein send_message
    assert tg.sent == [], "CAV-5: verteile_ca sendet keine Nachricht (EC-29)"
    # Anleitungstext ist im Tool-Result
    guide = result.tool_result_text
    assert own_marker in guide, (
        "%s-Anleitung enthält den eigenen Marker nicht" % geraet)
    for foreign in foreign_markers:
        assert foreign not in guide, (
            "%s-Anleitung enthält fremden Marker %r" % (geraet, foreign))


def test_CAV_5_enum_matches_supported_geraete():
    """#95: die als Modul-API exportierte SUPPORTED_GERAETE-Tupel deckt sich
    mit der Enum, die die Task-Definition (ca_task.parameters) ans Modell
    reicht. Eine Stelle, nicht doppelt."""
    assert set(SUPPORTED_GERAETE) == {"windows", "android", "ios", "macos"}


# ============================================================
#  CAV-6 — Trigger: die CA-Verteilung als EC-8-Aufgabe (#63)
# ============================================================

def test_CAV_6_is_a_read_task_without_a_confirmation_gate(tmp_path):
    """F4: die CA-Verteilungs-Aufgabe ist lesend (EC-9) — verteile_ca verändert
    keine Familien-Daten, also kein Bestätigungs-Gate."""
    task = CaVerteilungTask(FakeTelegram(), _write_ca(tmp_path))
    assert task.kind == READ
    assert task.name == "ca_verteilen"


def test_CAV_6_task_requires_geraet_as_parameter():
    """#95: Die Task-Definition deklariert `geraet` als Pflicht-Parameter mit
    Enum der vier OS-Werte — damit fragt das Modell von selbst nach (EC-22),
    statt alle Varianten gleichzeitig zu liefern."""
    task = CaVerteilungTask(FakeTelegram(), "/tmp/dummy.pem")
    params = task.parameters
    assert params["type"] == "object"
    assert "geraet" in params["properties"]
    assert params["properties"]["geraet"]["type"] == "string"
    assert set(params["properties"]["geraet"]["enum"]) == {
        "windows", "android", "ios", "macos"}
    assert params["required"] == ["geraet"]


def test_CAV_6_task_delivers_certificate_and_guide_itself(tmp_path):
    """F3: die Aufgabe liefert das Zertifikat als Datei und gibt die
    OS-Anleitung als Tool-Result-String zurück (EC-29).

    EC-29: kein send_message — tg.sent leer. Anleitungstext im return-Wert.
    """
    tg = FakeTelegram()
    task = CaVerteilungTask(tg, _write_ca(tmp_path))
    tool_result = task.run(arguments={"geraet": "android"},
                           turn_context=TurnContext(chat_id=42))
    assert len(tg.documents) == 1
    assert tg.documents[0]["file_name"] == "xbuddy-rootCA.crt"
    # EC-29: kein send_message
    assert tg.sent == [], "CAV-6-Task sendet keine Nachricht (EC-29)"
    # Anleitungstext ist im Tool-Result
    assert "Android" in tool_result
    assert isinstance(tool_result, str) and len(tool_result) > 0


def test_CAV_6_task_uses_chat_id_from_turn_context_not_arguments(tmp_path):
    """F3: der Zielchat kommt aus dem turn_context — nie aus den vom Modell
    gelieferten arguments. Das Modell bestimmt nicht, an wen ausgeliefert wird.

    EC-29: nur das Dokument geht via Telegram; kein send_message.
    """
    tg = FakeTelegram()
    task = CaVerteilungTask(tg, _write_ca(tmp_path))
    # Das Modell „schlägt" einen abweichenden chat_id vor — er wird ignoriert.
    task.run(arguments={"chat_id": 999, "geraet": "android"},
             turn_context=TurnContext(chat_id=42))
    assert tg.documents[0]["chat_id"] == 42
    # EC-29: kein send_message — nur das Dokument geht an Telegram
    assert tg.sent == [], "CAV-6-Task sendet keine Nachricht (EC-29)"


def test_CAV_6_task_without_geraet_raises_and_delivers_nothing(tmp_path):
    """#95: ruft der Agent die Aufgabe ohne `geraet` auf (z. B. weil der
    Anbieter die JSON-Schema-`required`-Vorgabe ignoriert), wirft die
    Aufgabe — und der Loop meldet das dem Modell, statt blind alle vier
    OS-Blöcke zu schicken."""
    tg = FakeTelegram()
    task = CaVerteilungTask(tg, _write_ca(tmp_path))
    with pytest.raises(ValueError):
        task.run(arguments={}, turn_context=TurnContext(chat_id=42))
    assert tg.documents == []
    assert tg.sent == []


def test_CAV_6_task_failure_propagates_to_the_agent_loop(tmp_path):
    """Scheitert die Auslieferung, reicht die Aufgabe den CaVerteilungError an
    den Agent-Loop weiter — der meldet ihn isoliert (EC-9)."""
    tg = FakeTelegram(send_document_error=TelegramError("Kanal weg"))
    task = CaVerteilungTask(tg, _write_ca(tmp_path))
    try:
        task.run(arguments={"geraet": "android"},
                 turn_context=TurnContext(chat_id=42))
        assert False, "die Aufgabe hätte den Fehler weiterreichen müssen"
    except CaVerteilungError:
        pass


def test_CAV_6_natural_language_request_delivers_via_the_agent(tmp_path):
    """End-to-End: eine natürlichsprachige Bitte mit angegebenem Gerät
    erreicht den Agenten, der die Katalog-Aufgabe aufruft — Auslieferung
    ohne Tippbefehl (#63), nur der iOS-Abschnitt geht raus (#95).

    EC-29: Das Dokument sendet die Aufgabe selbst; der Anleitungstext geht
    als Tool-Result ans LLM, das ihn als Bot-Nachricht postet.
    """
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([
        task_call_response("ca_verteilen", arguments={"geraet": "ios"}),
        text_response("Ich habe dir das Zertifikat geschickt."),
    ])
    ctx = _ctx(tmp_path, tg, _write_ca(tmp_path), provider=provider)
    handle_update(make_message("schick mir bitte das Zertifikat für mein iPhone",
                               from_user_id=7, chat_id=42), ctx)
    # Die Aufgabe hat das Dokument direkt ausgeliefert ...
    assert len(tg.documents) == 1
    assert tg.documents[0]["chat_id"] == 42
    # ... EC-29: keine direkte send_message-Auslieferung der Anleitung
    # (die Anleitung kommt als Tool-Result zum LLM, das sie als Antwort postet)
    guide_via_send_message = [s for s in tg.sent
                              if s.get("text") == ca_verteilung._GUIDE_IOS]
    assert len(guide_via_send_message) == 0, (
        "EC-29: Anleitung darf nicht direkt via send_message gehen")
    # ... und der Agent hat zum Schluss geantwortet.
    assert tg.sent[-1]["text"] == "Ich habe dir das Zertifikat geschickt."


# ============================================================
#  CAV-7 — automatisierte Tests je Anforderung, ohne Netz
# ============================================================

def test_CAV_7_delivery_runs_without_network(tmp_path):
    """CAV-7: die CA-Verteilung ist mit der Telegram-Doppelung vollständig
    ohne Netz prüfbar — dieser Lauf belegt es, kein Socket wird geöffnet.

    EC-29: tg.sent leer — kein send_message. Dokument + Tool-Result-Text
    sind das vollständige Ergebnis.
    """
    tg = FakeTelegram()
    result = verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path),
                         geraet="android")
    assert isinstance(result, CaVerteilungResult)
    assert len(tg.documents) == 1
    assert tg.sent == [], "CAV-7: kein send_message (EC-29)"
    assert isinstance(result.tool_result_text, str) and len(result.tool_result_text) > 0


# ============================================================
#  EC-29 / TASK-10 — Datei-Anhang-Sonderfall: Datei vom Skill, Text vom LLM
# ============================================================

def test_EC29_verteile_ca_sendet_keine_message(tmp_path):
    """EC-29 / CAV-4: verteile_ca ruft in keinem Pfad tg.send_message auf.

    Datei-Anhang-Sonderfall: tg.send_document BLEIBT (technische Notwendigkeit),
    tg.send_message ist raus. Text-Teil ist Tool-Result.
    """
    tg = FakeTelegram()
    verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path), geraet="windows")
    assert tg.sent == [], "EC-29: verteile_ca darf kein send_message aufrufen"
    assert len(tg.documents) == 1, "CAV-4: send_document muss aufgerufen werden"


@pytest.mark.parametrize("geraet", ["windows", "android", "ios", "macos"])
def test_EC29_tool_result_text_enthaelt_os_anleitung(tmp_path, geraet):
    """EC-29 / CAV-5: tool_result_text enthält den gerätespezifischen
    Anleitungstext — für jedes OS.

    CAV-5 Trust: LLM übernimmt diesen Text wortwörtlich in seine Antwort.
    """
    tg = FakeTelegram()
    result = verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path), geraet=geraet)
    assert isinstance(result.tool_result_text, str), (
        "EC-29: tool_result_text muss ein String sein")
    assert len(result.tool_result_text) > 0, (
        "EC-29: tool_result_text darf nicht leer sein")
    # CAV-5: der gerätespezifische Guide muss im Tool-Result stehen
    expected_guide = ca_verteilung._GUIDES_BY_GERAET[geraet]
    assert result.tool_result_text == expected_guide, (
        "EC-29/CAV-5: tool_result_text muss exakt der %s-Guide sein" % geraet)


def test_TASK10_baseline_run_sendet_keine_message(tmp_path):
    """TASK-10 / EC-29 Baseline-Test (Datei-Anhang-Sonderfall):
    CaVerteilungTask.run() sendet in keinem Pfad eine Telegram-Nachricht.

    Datei-Send ist erlaubt (tg.documents darf Einträge haben).
    tg.sent muss leer bleiben — das LLM postet den Text.
    Tool-Result ist nicht-leer (Anleitungstext).
    """
    tg = FakeTelegram()
    task = CaVerteilungTask(tg, _write_ca(tmp_path))
    ctx = TurnContext(chat_id=42)

    tool_result = task.run(arguments={"geraet": "ios"}, turn_context=ctx)

    # Datei-Send bleibt (CAV-4)
    assert len(tg.documents) == 1, "TASK-10: send_document muss aufgerufen werden"
    # Kein send_message (EC-29)
    assert tg.sent == [], "TASK-10: run() darf kein send_message aufrufen"
    # Tool-Result enthält OS-Anleitung (CAV-5)
    assert isinstance(tool_result, str) and len(tool_result) > 0, (
        "TASK-10: run() muss nicht-leeren Tool-Result-Text zurückgeben")
    assert "iOS" in tool_result or "iPadOS" in tool_result, (
        "TASK-10: Tool-Result muss iOS-Anleitungstext enthalten")
