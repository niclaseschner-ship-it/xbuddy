"""Tests für die CA-Verteilung — CAV-1 … CAV-7 (Refs #39).

Geprüft wird das Code-Verhalten der CA-Verteilung: die aufrufbare Funktion
selbst (ca_verteilung) und der direkte Aufruf-Weg über den Chat-Befehl
(main.handle_update). Telegram ist durch die kontrollierte Doppelung
`FakeTelegram` ersetzt — die Tests laufen reproduzierbar und ohne Netz (CAV-7,
analog EC-17/ONB-9).
"""

import inspect

import ca_verteilung
import main
from ca_verteilung import CaVerteilungError, CaVerteilungResult, verteile_ca
from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message, text_response
from history import History
from main import Context, handle_update
from tasks import Catalog
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


def _ctx(tmp_path, tg, ca_pem_path):
    """Context für die Orchestrierungs-Tests des Chat-Befehls (CAV-6)."""
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=FakeProvider([]), catalog=Catalog(),
        history=History(str(tmp_path / "ca.db")), pending=PendingStore(),
        ca_pem_path=ca_pem_path)


# ============================================================
#  CAV-1 — CA-Verteilung ist eine aufrufbare, trigger-agnostische Funktion
# ============================================================

def test_CAV_1_is_a_callable_function_returning_a_result(tmp_path):
    """verteile_ca ist eine aufrufbare Funktion und liefert ein Ergebnis."""
    tg = FakeTelegram()
    result = verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path))
    assert isinstance(result, CaVerteilungResult)
    assert result.chat_id == 42
    assert result.document_message_id is not None
    assert result.guide_message_id is not None


def test_CAV_1_function_does_not_know_its_caller(tmp_path):
    """E-CAV-1: der Aufrufer ist nicht Teil des Funktions-Vertrags. Die
    Signatur nimmt nur Kanal, Zielchat und Zertifikatspfad — keinen Trigger,
    keinen Onboarding-Flow, keinen Befehls-Kontext."""
    params = list(inspect.signature(verteile_ca).parameters)
    assert params == ["tg", "chat_id", "ca_pem_path"]


# ============================================================
#  CAV-2 — Zweck: Geräte-Vertrauen (das öffentliche CA-Zertifikat wird geliefert)
# ============================================================

def test_CAV_2_delivers_the_public_root_ca_certificate(tmp_path):
    """Die Funktion stellt dem Gerät genau das öffentliche Root-CA-Zertifikat
    bereit — den Trust-Anker, ohne den XBuddy-HTTPS-Seiten warnen."""
    tg = FakeTelegram()
    verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path))
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
        verteile_ca(tg, chat_id=42, ca_pem_path=key_path)
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
        verteile_ca(tg, chat_id=42, ca_pem_path=str(tmp_path / "fehlt.pem"))
        assert False, "verteile_ca hätte abbrechen müssen"
    except CaVerteilungError:
        pass
    assert tg.documents == []


def test_CAV_3_ca_pem_path_is_a_per_instance_config_value():
    """CAV-3: der Pfad zur CA-Datei ist ein Per-Instanz-Konfigurationswert mit
    Default UND Override-Pfad (Env/Datei) — keine reine Code-Konstante."""
    import config as config_mod
    assert "ca_pem_path" in config_mod.DEFAULTS
    assert config_mod.DEFAULTS["ca_pem_path"]                 # sinnvoller Default
    assert "ca_pem_path" in config_mod.ENV_OVERRIDES          # Env-Override


def test_CAV_3_config_resolves_ca_pem_path(tmp_path):
    """Die eltern-chat-Konfiguration löst ca_pem_path auf (Env > Datei > Default)."""
    import config as config_mod
    env = {config_mod.ENV_BOT_TOKEN: "t",
           "ELTERNCHAT_CA_PEM_PATH": "/instanz/rootCA.pem"}
    cfg = config_mod.resolve(str(tmp_path / "config.json"), env=env)
    assert cfg.ca_pem_path == "/instanz/rootCA.pem"
    # Ohne Override greift der Default.
    cfg_default = config_mod.resolve(str(tmp_path / "config.json"),
                                     env={config_mod.ENV_BOT_TOKEN: "t"})
    assert cfg_default.ca_pem_path == config_mod.DEFAULTS["ca_pem_path"]


# ============================================================
#  CAV-4 — Auslieferung über den Eltern-Chat-Bot
# ============================================================

def test_CAV_4_certificate_is_delivered_as_telegram_document(tmp_path):
    """Das Zertifikat geht als Datei (Telegram-Dokument) über den Bot-Kanal —
    an den übergebenen Zielchat, mit dem Dateinamen rootCA.pem."""
    tg = FakeTelegram()
    verteile_ca(tg, chat_id=777, ca_pem_path=_write_ca(tmp_path))
    assert len(tg.documents) == 1
    assert tg.documents[0]["chat_id"] == 777
    assert tg.documents[0]["file_name"] == "rootCA.pem"


def test_CAV_4_send_failure_is_reported_as_error(tmp_path):
    """Scheitert der Bot-Versand, meldet die Funktion das als CaVerteilungError —
    keine stille Nicht-Auslieferung."""
    tg = FakeTelegram(send_document_error=TelegramError("Kanal weg"))
    try:
        verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path))
        assert False, "verteile_ca hätte den Sendefehler melden müssen"
    except CaVerteilungError:
        pass


def test_CAV_4_command_is_behind_the_group_membership_gate(tmp_path):
    """Der direkte Aufruf-Weg (CAV-6) liegt hinter der Live-Berechtigung
    (CAV-4, analog EC-2): ein Nicht-Mitglied bekommt kein Zertifikat."""
    tg = FakeTelegram(members={})           # niemand ist Mitglied
    ctx = _ctx(tmp_path, tg, _write_ca(tmp_path))
    handle_update(make_message("/ca", from_user_id=7), ctx)
    assert tg.documents == []
    assert tg.sent == []


# ============================================================
#  CAV-5 — OS-spezifische Installations-Anleitung, hart-codiert
# ============================================================

def test_CAV_5_install_guide_covers_all_target_platforms(tmp_path):
    """Zur Datei liefert die Funktion eine Anleitung für Android, iOS/iPadOS,
    Windows und macOS — als eigene Nachricht über den Bot-Kanal."""
    tg = FakeTelegram()
    verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path))
    assert len(tg.sent) == 1
    guide = tg.sent[0]["text"]
    for platform in ("Android", "iOS", "iPadOS", "Windows", "macOS"):
        assert platform in guide, "Anleitung deckt %s nicht ab" % platform


def test_CAV_5_install_guide_needs_no_ai_provider(tmp_path):
    """Die Anleitung ist hart-codiert: derselbe Aufruf liefert deterministisch
    denselben Text — kein KI-Anbieter im Spiel."""
    tg1, tg2 = FakeTelegram(), FakeTelegram()
    verteile_ca(tg1, chat_id=1, ca_pem_path=_write_ca(tmp_path))
    verteile_ca(tg2, chat_id=2, ca_pem_path=_write_ca(tmp_path))
    assert tg1.sent[0]["text"] == tg2.sent[0]["text"]
    # Die Anleitung ist eine feste Modul-Konstante, kein generierter Text.
    assert tg1.sent[0]["text"] == ca_verteilung._INSTALL_GUIDE


# ============================================================
#  CAV-6 — direkter Aufruf-Weg: ein Chat-Befehl ruft dieselbe Funktion
# ============================================================

def test_CAV_6_chat_command_delivers_certificate_and_guide(tmp_path):
    """Der Chat-Befehl /ca eines berechtigten Mitglieds löst die Auslieferung
    aus — Zertifikat als Dokument plus Anleitung."""
    tg = FakeTelegram(members=_members(7))
    ctx = _ctx(tmp_path, tg, _write_ca(tmp_path))
    handle_update(make_message("/ca", from_user_id=7), ctx)
    assert len(tg.documents) == 1
    assert tg.documents[0]["file_name"] == "rootCA.pem"
    assert "Android" in tg.sent[0]["text"]


def test_CAV_6_command_handler_only_calls_the_function(tmp_path, monkeypatch):
    """Der Befehls-Handler ist ein dünner Aufrufer: er ruft genau die Funktion
    aus CAV-1 auf und gibt ihr Kanal, Zielchat und Zertifikatspfad weiter —
    keine eigene Auslieferungs-Logik. Genauso würde ein Onboarding-Flow sie
    aufrufen."""
    calls = []

    def spy(tg, chat_id, ca_pem_path):
        calls.append((tg, chat_id, ca_pem_path))
        return CaVerteilungResult(chat_id, 1, 2)

    monkeypatch.setattr(main.ca_verteilung, "verteile_ca", spy)
    tg = FakeTelegram(members=_members(7))
    ctx = _ctx(tmp_path, tg, "/pfad/rootCA.pem")
    handle_update(make_message("/ca", from_user_id=7, chat_id=42), ctx)
    assert calls == [(tg, 42, "/pfad/rootCA.pem")]


def test_CAV_6_command_accepts_botname_qualified_form(tmp_path):
    """In Gruppen darf der Befehl mit @botname qualifiziert sein: /ca@mybot."""
    tg = FakeTelegram(members=_members(7))
    ctx = _ctx(tmp_path, tg, _write_ca(tmp_path))
    handle_update(make_message("/ca@mybot", from_user_id=7,
                               chat_type="group", mentions_bot=True), ctx)
    assert len(tg.documents) == 1


def test_CAV_6_non_command_text_goes_to_the_agent_not_the_function(tmp_path):
    """Normale Anfragen lösen die CA-Verteilung nicht aus — nur der Befehl tut
    es. Der Befehl und der Agent-Pfad sind sauber getrennt."""
    tg = FakeTelegram(members=_members(7))
    ctx = _ctx(tmp_path, tg, _write_ca(tmp_path))
    ctx.provider = FakeProvider([text_response("Antwort vom Agenten.")])
    handle_update(make_message("was ist ein Zertifikat?", from_user_id=7), ctx)
    assert tg.documents == []
    assert tg.sent[0]["text"] == "Antwort vom Agenten."


def test_CAV_6_command_failure_yields_a_clear_hint(tmp_path):
    """Schlägt die Auslieferung fehl, antwortet der Befehls-Handler dem
    Mitglied mit einem klaren Hinweis, statt stumm zu bleiben."""
    tg = FakeTelegram(members=_members(7),
                      send_document_error=TelegramError("Kanal weg"))
    ctx = _ctx(tmp_path, tg, _write_ca(tmp_path))
    handle_update(make_message("/ca", from_user_id=7), ctx)
    assert tg.documents == []
    assert tg.sent[0]["text"] == main._CA_FAILED


# ============================================================
#  CAV-7 — automatisierte Tests je Anforderung, ohne Netz
# ============================================================

def test_CAV_7_delivery_runs_without_network(tmp_path):
    """CAV-7: die CA-Verteilung ist mit der Telegram-Doppelung vollständig
    ohne Netz prüfbar — dieser Lauf belegt es, kein Socket wird geöffnet."""
    tg = FakeTelegram()
    result = verteile_ca(tg, chat_id=42, ca_pem_path=_write_ca(tmp_path))
    assert isinstance(result, CaVerteilungResult)
    assert len(tg.documents) == 1 and len(tg.sent) == 1
