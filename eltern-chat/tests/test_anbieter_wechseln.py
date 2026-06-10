"""Tests für »Anbieter wechseln« — ONB-11, ONB-12, ONB-13 (Refs #639).

Geprüft werden:
  * die trigger-agnostische Funktion (`anbieter_wechseln`) — Auth,
    Anbieter-Wahl, Key-Eingabe, Validierungs-Ping, ZD-Schreiben, Bestätigung.
  * Same-Provider-Quittung (ONB-11).
  * Validierungs-Fehler → byte-gleicher Erhalt des alten Eintrags (ONB-12).
  * Schreib-Fehler → byte-gleicher Erhalt, Instanz nicht unterbrochen (ONB-12).
  * ONB-8-Schutz: kein Klartext-Key in Bestätigungen, Fehlermeldungen, Logs.

Telegram, Zugangsdaten-Speicher und Validierungs-Ping sind durch kontrollierte
Doppelungen ersetzt (kein Netz, ONB-13).
"""

import json

from fakes import FakeTelegram
from skills.anbieter_wechseln import (
    DONE_PRIVAT,
    ERGEBNIS_ABGELEHNT,
    ERGEBNIS_GEWECHSELT,
    ERGEBNIS_UNVERAENDERT,
    KEY_INVALID,
    NOT_AUTHORIZED,
    REJECT_ANBIETER,
    SAME_PROVIDER,
    WRITE_FAILED,
    ZD_NAME_PROVIDER_API_KEY,
    ZD_NAME_PROVIDER_NAME,
    AvbInput,
    anbieter_wechseln,
)

from tools.zugangsdaten import StoreError

# ============================================================
#  Test-Doppelungen
# ============================================================


class FakeZd:
    """In-Memory-Zugangsdaten-Speicher (ZD-5).

    `writes` protokolliert die Schreib-Reihenfolge (Tupel name/value).
    `fail_on_write` lässt `set()` einen StoreError werfen — für ONB-12-
    Schreib-Fehler-Tests.
    """

    def __init__(self, initial=None, fail_on_write=False):
        self._data = dict(initial or {})
        self.writes = []
        self.fail_on_write = fail_on_write

    def get(self, name, default=None):
        return self._data.get(name, default)

    def set(self, name, value):
        self.writes.append((name, value))
        if self.fail_on_write:
            raise StoreError("simulierter Schreib-Fehler")
        self._data[name] = value

    def has(self, name):
        return name in self._data

    def snapshot(self):
        """JSON-Snapshot für Byte-Vergleich (ONB-12)."""
        return json.dumps(self._data, sort_keys=True)


def _members(*user_ids):
    """Hilfsfunktion: FakeTelegram-Members-Dict."""
    return {uid: {"status": "member"} for uid in user_ids}


def _stream(*texts):
    """Liefert AvbInput-Objekte der Reihe nach, dann None (Timeout)."""
    items = [AvbInput(text=t) for t in texts] + [None]
    it = iter(items)
    return lambda: next(it)


def _validate_ok(name, key):
    """Validierungs-Doppelung: immer erfolgreich."""
    return True


def _validate_fail(name, key):
    """Validierungs-Doppelung: immer fehlgeschlagen."""
    return False


# ============================================================
#  1. Happy-Path: Claude → Mistral
# ============================================================

def test_happy_path_claude_to_mistral():
    """ONB-13 Happy-Path Claude → Mistral: Wechsel abgeschlossen, ZD gesetzt,
    Bestätigung im Privatchat und in der Familien-Gruppe."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={
        ZD_NAME_PROVIDER_API_KEY: "old-claude-key",
        ZD_NAME_PROVIDER_NAME: "claude",
    })
    fgcid = 99

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=fgcid,
        zd=zd, next_message=_stream("mistral", "new-mistral-key-xxxxxxxxxxxx"),
        current_provider_name="claude",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_GEWECHSELT
    assert result.neuer_anbieter == "mistral"

    # ZD-Speicher gesetzt (ONB-12).
    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "new-mistral-key-xxxxxxxxxxxx"
    assert zd.get(ZD_NAME_PROVIDER_NAME) == "mistral"

    # Bestätigung im Privatchat.
    privat_texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    assert any(DONE_PRIVAT in t for t in privat_texte)

    # Bestätigung in der Familien-Gruppe — kein Key im Text (ONB-8).
    gruppe_texte = [m["text"] for m in tg.sent if m["chat_id"] == fgcid]
    assert any("Mistral" in t or "mistral" in t.lower() for t in gruppe_texte)
    for t in gruppe_texte:
        assert "new-mistral-key" not in t, "ONB-8: Key im Gruppen-Output"


# ============================================================
#  2. Happy-Path: Mistral → Claude
# ============================================================

def test_happy_path_mistral_to_claude():
    """ONB-13 Happy-Path Mistral → Claude: analoger Wechsel in die andere
    Richtung."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={
        ZD_NAME_PROVIDER_API_KEY: "old-mistral-key",
        ZD_NAME_PROVIDER_NAME: "mistral",
    })

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=_stream("claude", "sk-ant-new-claude-xxxxxxxxxxxx"),
        current_provider_name="mistral",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_GEWECHSELT
    assert result.neuer_anbieter == "claude"
    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "sk-ant-new-claude-xxxxxxxxxxxx"
    assert zd.get(ZD_NAME_PROVIDER_NAME) == "claude"

    # ONB-8: Key nirgendwo im Output.
    for m in tg.sent:
        assert "sk-ant-new-claude" not in m["text"], "ONB-8: Key im Output"


# ============================================================
#  3. Same-Provider-Quittung
# ============================================================

def test_same_provider_quittung_claude():
    """ONB-13 Same-Provider-Quittung: wählt man den aktuellen Anbieter erneut,
    kommt die harte Quittung — kein Schreiben, kein Re-Key."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={ZD_NAME_PROVIDER_API_KEY: "existing-key"})
    snapshot_vorher = zd.snapshot()

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=_stream("claude"),
        current_provider_name="claude",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_UNVERAENDERT
    # Kein Schreiben in den ZD-Speicher.
    assert zd.writes == [], "Same-Provider: darf nicht schreiben"
    assert zd.snapshot() == snapshot_vorher, "ZD-Inhalt muss byte-gleich bleiben"
    # Quittung im Privatchat.
    texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    assert any(SAME_PROVIDER in t for t in texte)


def test_same_provider_quittung_mistral():
    """Same-Provider-Quittung auch für Mistral."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd()
    snapshot_vorher = zd.snapshot()

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=_stream("mistral"),
        current_provider_name="mistral",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_UNVERAENDERT
    assert zd.writes == []
    assert zd.snapshot() == snapshot_vorher


# ============================================================
#  4. Validierungs-Fehler → byte-gleicher Erhalt (ONB-12)
# ============================================================

def test_validierungsfehler_alter_eintrag_byte_gleich():
    """ONB-13 / ONB-12 Validierungs-Fehler: ungültiger Key → ZD-Speicher bleibt
    byte-gleich, alter Anbieter weiter aktiv."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={
        ZD_NAME_PROVIDER_API_KEY: "existing-claude-key",
        ZD_NAME_PROVIDER_NAME: "claude",
    })
    snapshot_vorher = zd.snapshot()

    # Liefert zuerst einen ungültigen Key, dann None (Timeout — kein Retry).
    msgs = iter([
        AvbInput(text="mistral"),
        AvbInput(text="invalid-key-xxxxxxxxxxxx"),   # Ping schlägt fehl
        None,                                         # Timeout nach einem Versuch
    ])
    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=lambda: next(msgs),
        current_provider_name="claude",
        _validate=_validate_fail)

    # ZD unverändert (ONB-12).
    assert zd.snapshot() == snapshot_vorher, "ZD muss byte-gleich bleiben"
    assert result.ergebnis == ERGEBNIS_UNVERAENDERT

    # Fehlermeldung im Privatchat — kein Key im Text (ONB-8).
    privat_texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    assert any("invalid" not in t and ("ungültig" in t or "nicht erreichbar" in t
               or KEY_INVALID % "Mistral" in t)
               for t in privat_texte), "Keine KEY_INVALID-Nachricht gefunden"
    for t in privat_texte:
        assert "invalid-key" not in t, "ONB-8: Key im Fehler-Output"


def test_validierungsfehler_retry_danach_erfolg():
    """ONB-12: nach einem fehlgeschlagenen Validierungs-Ping kann der User
    einen neuen Key eingeben und erfolgreich wechseln."""
    call_count = [0]

    def validate_second_ok(name, key):
        call_count[0] += 1
        return call_count[0] >= 2   # erster Aufruf fehlschlägt, zweiter ok

    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={ZD_NAME_PROVIDER_API_KEY: "old"})

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd,
        next_message=_stream("mistral",
                             "bad-key-xxxxxxxxxxxx",
                             "good-key-xxxxxxxxxxxx"),
        current_provider_name="claude",
        _validate=validate_second_ok)

    assert result.ergebnis == ERGEBNIS_GEWECHSELT
    assert zd.get(ZD_NAME_PROVIDER_API_KEY) == "good-key-xxxxxxxxxxxx"


# ============================================================
#  5. Schreib-Fehler → byte-gleicher Erhalt, Instanz nicht unterbrochen
#     (ONB-12)
# ============================================================

def test_schreibfehler_alter_eintrag_byte_gleich():
    """ONB-13 / ONB-12 Schreib-Fehler: simulierter os.replace-Bruch →
    ZD-Speicher byte-gleich, laufende Instanz nicht unterbrochen."""
    tg = FakeTelegram(members=_members(42))
    initial = {
        ZD_NAME_PROVIDER_API_KEY: "existing-key",
        ZD_NAME_PROVIDER_NAME: "claude",
    }
    zd = FakeZd(initial=initial, fail_on_write=True)
    snapshot_vorher = zd.snapshot()

    # Die Funktion darf keine Exception nach außen werfen.
    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd,
        next_message=_stream("mistral", "valid-new-key-xxxxxxxxxxxx"),
        current_provider_name="claude",
        _validate=_validate_ok)

    # ZD unverändert (byte-gleich).
    assert zd.snapshot() == snapshot_vorher, "ZD muss byte-gleich bleiben"
    assert result.ergebnis == ERGEBNIS_UNVERAENDERT

    # Fehlermeldung im Privatchat.
    privat_texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    assert any(WRITE_FAILED in t for t in privat_texte)

    # ONB-8: Key nicht im Fehler-Output.
    for t in privat_texte:
        assert "valid-new-key" not in t, "ONB-8: Key im Fehler-Output"


# ============================================================
#  6. ONB-8-Schutz: kein Key im Klartext in Outputs
# ============================================================

def test_onb8_kein_key_in_gruppen_bestaetigung():
    """ONB-13 / ONB-8: Familien-Gruppen-Bestätigung enthält weder alten noch
    neuen Key im Klartext."""
    tg = FakeTelegram(members=_members(42))
    new_key = "super-secret-key-xxxxxxxxxxxx"
    zd = FakeZd(initial={ZD_NAME_PROVIDER_API_KEY: "old-key"})

    anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd,
        next_message=_stream("mistral", new_key),
        current_provider_name="claude",
        _validate=_validate_ok)

    for m in tg.sent:
        assert new_key not in m["text"], "ONB-8: neuer Key im Output"
        assert "old-key" not in m["text"], "ONB-8: alter Key im Output"


def test_onb8_kein_key_in_fehlermeldung_validierung():
    """ONB-8: Key nicht in der Fehler-Nachricht nach Validierungs-Fehlschlag."""
    tg = FakeTelegram(members=_members(42))
    evil_key = "leak-this-key-xxxxxxxxxxxx"
    zd = FakeZd()
    msgs = iter([AvbInput("mistral"), AvbInput(evil_key), None])

    anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=lambda: next(msgs),
        current_provider_name="claude",
        _validate=_validate_fail)

    for m in tg.sent:
        assert evil_key not in m["text"], "ONB-8: Key im Output"


def test_onb8_kein_key_in_schreib_fehlermeldung():
    """ONB-8: Key nicht in der Fehler-Nachricht nach Schreib-Fehlschlag."""
    tg = FakeTelegram(members=_members(42))
    evil_key = "leak-this-write-xxxxxxxxxxxx"
    zd = FakeZd(fail_on_write=True)

    anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd,
        next_message=_stream("mistral", evil_key),
        current_provider_name="claude",
        _validate=_validate_ok)

    for m in tg.sent:
        assert evil_key not in m["text"], "ONB-8: Key im Output"


# ============================================================
#  7. Nicht berechtigt (EC-2)
# ============================================================

def test_not_authorized():
    """EC-2: ein User, der nicht in der Familien-Gruppe ist, wird abgewiesen."""
    tg = FakeTelegram(members=_members(99))   # User 42 NICHT in der Gruppe
    zd = FakeZd()

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=_stream("mistral"),
        current_provider_name="claude",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_ABGELEHNT
    assert zd.writes == [], "Kein Schreiben bei nicht-berechtigtem User"
    texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    assert any(NOT_AUTHORIZED in t for t in texte)


# ============================================================
#  8. Unbekannter Anbieter-Name → re-prompt
# ============================================================

def test_unbekannter_anbieter_reprompt():
    """ONB-11: ein nicht-passender Anbieter-Name löst einen re-prompt aus
    (SESS-4-Analogie)."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd()

    # Erst ungültig, dann gültig.
    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd,
        next_message=_stream("openai", "mistral", "valid-mistral-xxxxxxxxxxxx"),
        current_provider_name="claude",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_GEWECHSELT
    texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    assert any(REJECT_ANBIETER in t for t in texte)


# ============================================================
#  9. Timeout während Anbieter-Wahl
# ============================================================

def test_timeout_anbieter_wahl():
    """Gibt next_message() None zurück während der Anbieter-Wahl, ist das
    Ergebnis ERGEBNIS_UNVERAENDERT ohne Schreiben."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={ZD_NAME_PROVIDER_API_KEY: "old"})
    snapshot_vorher = zd.snapshot()

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=lambda: None,
        current_provider_name="claude",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_UNVERAENDERT
    assert zd.snapshot() == snapshot_vorher


# ============================================================
#  10. Familien-Bestätigung enthält Anbieter-Anzeigenamen
# ============================================================

def test_gruppen_bestaetigung_nennt_anbieter():
    """ONB-11 Schritt 5: die Familien-Gruppen-Bestätigung nennt den neuen
    Anbieter (z. B. »Mistral«), nicht den internen Namen."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd()

    anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd,
        next_message=_stream("mistral", "valid-mistral-xxxxxxxxxxxx"),
        current_provider_name="claude",
        _validate=_validate_ok)

    gruppe_texte = [m["text"] for m in tg.sent if m["chat_id"] == 99]
    assert gruppe_texte, "Keine Nachricht an die Familien-Gruppe"
    # Die Bestätigung nennt den Anzeige-Namen (enthält „Mistral").
    assert any("Mistral" in t for t in gruppe_texte)
