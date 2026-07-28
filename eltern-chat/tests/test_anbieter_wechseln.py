"""Tests für »Anbieter wechseln« — ONB-11, ONB-12, ONB-13 (Refs #639, #663).

Geprüft werden:
  * die trigger-agnostische Funktion (`anbieter_wechseln`) — Auth,
    Anbieter-Wahl, Key-Eingabe, Validierungs-Ping, ZD-Schreiben, Bestätigung.
  * Same-Provider-Quittung (ONB-11).
  * Validierungs-Fehler → byte-gleicher Erhalt des alten Eintrags (ONB-12).
  * Schreib-Fehler → byte-gleicher Erhalt, Instanz nicht unterbrochen (ONB-12).
  * ONB-8-Schutz: kein Klartext-Key in Bestätigungen, Fehlermeldungen, Logs.
  * ONB-13 caplog-Schutz: keine Keys im Log (Befund 4).
  * T663 Welle A: Pfad A (vorbefüllter vendor-Slot, kein Re-Key) und Pfad B
    (neuer Vendor → set_multi mit vendor-Slot + provider-name).
  * ONB-12 V2: atomares set_multi schließt das V1-Race-Fenster.

Telegram, Zugangsdaten-Speicher und Validierungs-Ping sind durch kontrollierte
Doppelungen ersetzt (kein Netz, ONB-13).
"""

import json
import logging

from fakes import FakeTelegram
from onboarding_store import (
    ZD_NAME_PROVIDER_API_KEY,
    ZD_NAME_PROVIDER_NAME,
    zd_name_provider_api_key,
)
from skills.anbieter_wechseln import (
    DONE_PRIVAT,
    DONE_PRIVAT_PFAD_A,
    ERGEBNIS_ABGELEHNT,
    ERGEBNIS_GEWECHSELT,
    ERGEBNIS_UNVERAENDERT,
    KEY_INVALID,
    NOT_AUTHORIZED,
    REJECT_ANBIETER,
    SAME_PROVIDER,
    WRITE_FAILED,
    AvbInput,
    anbieter_wechseln,
)

from tools.zugangsdaten import StoreError

# ============================================================
#  Test-Doppelungen
# ============================================================


class FakeZd:
    """In-Memory-Zugangsdaten-Speicher (ZD-5).

    `writes` protokolliert jede Schreib-Operation als Tupel:
      * `("set", name, value)` — Single-Key-Naht.
      * `("set_multi", dict(pairs))` — Multi-Key-Naht (T663 Welle A).

    `fail_on_write` lässt jeden Schreibvorgang (`set` und `set_multi`) einen
    StoreError werfen — für ONB-12-Schreib-Fehler-Tests. Beim `set_multi`-
    Fehler bleibt der `_data`-Stand byte-gleich (atomar: alle oder keiner).
    """

    def __init__(self, initial=None, fail_on_write=False):
        self._data = dict(initial or {})
        self.writes = []
        self.fail_on_write = fail_on_write

    def get(self, name, default=None):
        return self._data.get(name, default)

    def set(self, name, value):
        self.writes.append(("set", name, value))
        if self.fail_on_write:
            raise StoreError("simulierter Schreib-Fehler")
        self._data[name] = value

    def set_multi(self, pairs):
        # Snapshot der Paare für Test-Inspektion (eigene Kopie, kein Aliasing).
        self.writes.append(("set_multi", dict(pairs)))
        if self.fail_on_write:
            # Atomar: kein Wert übernommen — `_data` bleibt byte-gleich.
            raise StoreError("simulierter Schreib-Fehler")
        self._data.update(pairs)

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
    """Validierungs-Doppelung: immer erfolgreich (kein Slot-Effekt).

    Für Tests, die den Key-Slot NICHT inspizieren. Wo die #1510-Verschmelzung
    (Probe-Schreib bleibt im litellm-Slot stehen) belegt werden soll, nutzt der
    Test `_validate_ok_writes(zd)`.
    """
    return True


def _validate_fail(name, key):
    """Validierungs-Doppelung: immer fehlgeschlagen (kein Slot-Effekt)."""
    return False


def _litellm_slot(provider):
    """Der litellm-Slot, in den der reale `_do_validate` probeweise schreibt."""
    from tools.llm import litellm_slot_for_provider
    return litellm_slot_for_provider("eltern-chat", provider)


def _validate_ok_writes(zd):
    """Validierungs-Doppelung mit realem Slot-Effekt (#1510): schreibt den Key
    probeweise in den litellm-Slot und lässt ihn stehen — spiegelt, dass der
    echte `_do_validate` den Key bei Erfolg persistiert (Schreibschritt
    verschmilzt)."""
    def _v(name, key):
        zd.set(_litellm_slot(name), key)
        return True
    return _v


def _validate_fail_deletes(zd):
    """Validierungs-Doppelung mit realem Slot-Effekt (#1510): räumt den
    litellm-Slot bei Fehler wieder ab (leerer String)."""
    def _v(name, key):
        zd.set(_litellm_slot(name), "")
        return False
    return _v


# ============================================================
#  1. Happy-Path: Claude → Mistral
# ============================================================

def test_happy_path_claude_to_mistral():
    """ONB-13 Happy-Path Claude → Mistral: Wechsel abgeschlossen, ZD gesetzt,
    Bestätigung im Privatchat und in der Familien-Gruppe.

    T663 Welle A: Mistral hat noch keinen vendor-Slot → Pfad B. Schreibt in
    den mistral-Slot (`eltern-chat-mistral-api-key`) und den provider-name —
    beide in einem `set_multi`-Aufruf.
    """
    tg = FakeTelegram(members=_members(42))
    # #1510: alter claude-litellm-Slot ist gesetzt. Mistral-litellm-Slot leer
    # → Pfad B wird durchlaufen.
    zd = FakeZd(initial={
        _litellm_slot("claude"): "old-claude-key",
        ZD_NAME_PROVIDER_NAME: "claude",
    })
    fgcid = 99

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=fgcid,
        zd=zd, next_message=_stream("mistral", "new-mistral-key-xxxxxxxxxxxx"),
        current_provider_name="claude",
        _validate=_validate_ok_writes(zd))

    assert result.ergebnis == ERGEBNIS_GEWECHSELT
    assert result.neuer_anbieter == "mistral"

    # #1510: der validierte Key liegt im litellm-Slot (Probe-Schreib
    # verschmolzen); provider-name umgeschaltet.
    assert zd.get(_litellm_slot("mistral")) == "new-mistral-key-xxxxxxxxxxxx"
    assert zd.get(ZD_NAME_PROVIDER_NAME) == "mistral"
    # Alter Anbieter-litellm-Slot bleibt erhalten (für späteren Rückwechsel — Pfad A).
    assert zd.get(_litellm_slot("claude")) == "old-claude-key"

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
    Richtung. Welle A: Claude-Slot leer → Pfad B."""
    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={
        _litellm_slot("mistral"): "old-mistral-key",
        ZD_NAME_PROVIDER_NAME: "mistral",
    })

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=_stream("claude", "sk-ant-new-claude-xxxxxxxxxxxx"),
        current_provider_name="mistral",
        _validate=_validate_ok_writes(zd))

    assert result.ergebnis == ERGEBNIS_GEWECHSELT
    assert result.neuer_anbieter == "claude"
    assert zd.get(_litellm_slot("claude")) == "sk-ant-new-claude-xxxxxxxxxxxx"
    assert zd.get(ZD_NAME_PROVIDER_NAME) == "claude"
    # Alter mistral-litellm-Slot bleibt erhalten.
    assert zd.get(_litellm_slot("mistral")) == "old-mistral-key"

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
    zd = FakeZd(initial={zd_name_provider_api_key("claude"): "existing-key"})
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
        zd_name_provider_api_key("claude"): "existing-claude-key",
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
        # #1510: spiegelt den realen _do_validate-Slot-Effekt — erster Ping
        # scheitert (Slot abräumen), zweiter gelingt (Key bleibt im Slot).
        call_count[0] += 1
        if call_count[0] >= 2:
            zd.set(_litellm_slot(name), key)
            return True
        zd.set(_litellm_slot(name), "")
        return False

    tg = FakeTelegram(members=_members(42))
    zd = FakeZd(initial={_litellm_slot("claude"): "old"})

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
    assert zd.get(_litellm_slot("mistral")) == "good-key-xxxxxxxxxxxx"


# ============================================================
#  5. Schreib-Fehler → byte-gleicher Erhalt, Instanz nicht unterbrochen
#     (ONB-12)
# ============================================================

def test_schreibfehler_alter_eintrag_byte_gleich():
    """ONB-13 / ONB-12 Schreib-Fehler: simulierter os.replace-Bruch →
    ZD-Speicher byte-gleich, laufende Instanz nicht unterbrochen."""
    tg = FakeTelegram(members=_members(42))
    initial = {
        zd_name_provider_api_key("claude"): "existing-key",
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
    zd = FakeZd(initial={zd_name_provider_api_key("claude"): "old-key"})

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
    zd = FakeZd(initial={zd_name_provider_api_key("claude"): "old"})
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


# ============================================================
#  11. Pfad A: Quittungs-Wording trennen (#1021)
# ============================================================

def test_pfad_a_quittung_unterscheidet_sich_von_pfad_b():
    """T1021: Bei Pfad A (Vendor-Slot vorgefüllt, kein Re-Key) wird KEIN neuer
    Key gespeichert — die Quittung darf nicht „der neue Key ist gespeichert"
    sagen. Pfad A sendet DONE_PRIVAT_PFAD_A, Pfad B sendet DONE_PRIVAT.
    """
    tg = FakeTelegram(members=_members(42))
    # #1510: beide litellm-Slots vorgefüllt → Wahl mistral → Pfad A (Mistral-
    # litellm-Slot truthy, kein Re-Key, kein Probe-Ping).
    zd = FakeZd(initial={
        _litellm_slot("claude"): "existing-claude-key",
        _litellm_slot("mistral"): "existing-mistral-key",
        ZD_NAME_PROVIDER_NAME: "claude",
    })

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd, next_message=_stream("mistral"),
        current_provider_name="claude",
        _validate=_validate_ok)

    assert result.ergebnis == ERGEBNIS_GEWECHSELT
    assert result.neuer_anbieter == "mistral"

    privat_texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    # Pfad-A-Quittung muss kommen, Pfad-B-Quittung NICHT.
    assert any(DONE_PRIVAT_PFAD_A in t for t in privat_texte), (
        "Pfad A muss DONE_PRIVAT_PFAD_A senden, nicht DONE_PRIVAT")
    assert not any(DONE_PRIVAT in t for t in privat_texte), (
        "Pfad A darf das Pfad-B-Wording 'Key gespeichert' nicht senden")


# ============================================================
#  12. ONB-12 V2: set_multi schließt das V1-Race-Fenster (#663)
# ============================================================

def test_set_multi_atomic_kein_partial_state():
    """ONB-12 V2 (#663 Welle A): set_multi schreibt atomar — bei Fehlschlag
    bleibt der Speicher byte-gleich (alle Paare oder keines).

    Das V1-Race-Fenster (zwei sequentielle set()-Calls, zwischen denen ein
    partieller Zustand entstehen konnte) ist durch die Multi-Key-Atomic-Naht
    in tools/zugangsdaten/store.py geschlossen — Pfad B des Wechsel-Skills
    nutzt set_multi für vendor-Slot + provider-name in einem _write-Vorgang.
    """
    tg = FakeTelegram(members=_members(42))
    initial = {
        zd_name_provider_api_key("claude"): "existing-claude-key",
        ZD_NAME_PROVIDER_NAME: "claude",
    }
    # set_multi-Aufruf scheitert komplett — atomar, kein Paar übernommen.
    zd = FakeZd(initial=initial, fail_on_write=True)
    snapshot_vorher = zd.snapshot()

    result = anbieter_wechseln(
        tg=tg, chat_id=11, user_id=42,
        family_group_chat_id=99,
        zd=zd,
        next_message=_stream("mistral", "valid-new-key-xxxxxxxxxxxx"),
        current_provider_name="claude",
        _validate=_validate_ok)

    # Skill meldet Fehler an User.
    assert result.ergebnis == ERGEBNIS_UNVERAENDERT
    privat_texte = [m["text"] for m in tg.sent if m["chat_id"] == 11]
    assert any(WRITE_FAILED in t for t in privat_texte)

    # ONB-12 V2: Speicher ist byte-gleich — kein partieller Zustand.
    assert zd.snapshot() == snapshot_vorher, (
        "ONB-12 V2 (#663): set_multi muss atomar sein — bei Fehlschlag "
        "darf kein Paar im Speicher landen. Multi-Key-Atomic-Naht in "
        "tools/zugangsdaten/store.py."
    )


# ============================================================
#  12. ONB-13 caplog-Schutz: keine Keys in Logs (Befund 4)
# ============================================================

def test_caplog_kein_key_bei_validierungsfehler(caplog):
    """ONB-13 / ONB-8: bei Validierungs-Fehlschlag landet kein Key im Log."""
    tg = FakeTelegram(members=_members(42))
    evil_key = "caplog-leak-val-key-xxxxxxxxxxxx"
    zd = FakeZd()
    msgs = iter([AvbInput("mistral"), AvbInput(evil_key), None])

    with caplog.at_level(logging.DEBUG):
        anbieter_wechseln(
            tg=tg, chat_id=11, user_id=42,
            family_group_chat_id=99,
            zd=zd, next_message=lambda: next(msgs),
            current_provider_name="claude",
            _validate=_validate_fail)

    assert evil_key not in caplog.text, (
        "ONB-8 caplog-Leck: Key in Log-Ausgabe nach Validierungs-Fehler")


def test_caplog_kein_key_bei_schreibfehler(caplog):
    """ONB-13 / ONB-8: bei Schreib-Fehlschlag landet kein Key im Log."""
    tg = FakeTelegram(members=_members(42))
    evil_key = "caplog-leak-write-key-xxxxxxxxxxxx"
    zd = FakeZd(fail_on_write=True)

    with caplog.at_level(logging.DEBUG):
        anbieter_wechseln(
            tg=tg, chat_id=11, user_id=42,
            family_group_chat_id=99,
            zd=zd,
            next_message=_stream("mistral", evil_key),
            current_provider_name="claude",
            _validate=_validate_ok)

    assert evil_key not in caplog.text, (
        "ONB-8 caplog-Leck: Key in Log-Ausgabe nach Schreib-Fehler")


def test_caplog_kein_key_bei_happy_path(caplog):
    """ONB-13 / ONB-8: auch beim erfolgreichen Wechsel landet kein Key im Log."""
    tg = FakeTelegram(members=_members(42))
    new_key = "caplog-happy-path-key-xxxxxxxxxxxx"
    old_key = "caplog-old-key-xxxxxxxxxxxx"
    zd = FakeZd(initial={
        ZD_NAME_PROVIDER_API_KEY: old_key,
        ZD_NAME_PROVIDER_NAME: "claude",
    })

    with caplog.at_level(logging.DEBUG):
        anbieter_wechseln(
            tg=tg, chat_id=11, user_id=42,
            family_group_chat_id=99,
            zd=zd,
            next_message=_stream("mistral", new_key),
            current_provider_name="claude",
            _validate=_validate_ok)

    assert new_key not in caplog.text, (
        "ONB-8 caplog-Leck: neuer Key in Log-Ausgabe beim Happy-Path")
    assert old_key not in caplog.text, (
        "ONB-8 caplog-Leck: alter Key in Log-Ausgabe beim Happy-Path")


# ============================================================
#  Hotfix-Regression: _do_validate baut GenerationRequest korrekt
# ============================================================

def test_do_validate_baut_GenerationRequest_mit_task_defs(monkeypatch):
    """Regression #639-Hotfix + #1510: _do_validate baut GenerationRequest mit
    `task_defs=` (nicht `tasks=`) — TypeError im Live-Pfad, den die Test-
    Doppelungen (`_validate=_validate_ok`) verdecken. #1510: der Ping läuft über
    den Motor-Adapter (`get_lib_agent_provider`); der probeweise geschriebene
    Slot bleibt bei Erfolg stehen (Schreibschritt verschmilzt)."""
    from skills import anbieter_wechseln as aw_mod

    captured = {}

    class _FakeProvider:
        def generate(self, request):
            captured["task_defs"] = request.task_defs
            return None

    monkeypatch.setattr(aw_mod, "get_lib_agent_provider",
                        lambda name, *a, **k: _FakeProvider())

    zd = FakeZd()
    result = aw_mod._do_validate(zd, "mistral", "dummy-key")

    assert result is True
    assert captured["task_defs"] == []
    # #1510: der probeweise geschriebene Key bleibt bei Erfolg im litellm-Slot.
    assert zd.get(_litellm_slot("mistral")) == "dummy-key"
