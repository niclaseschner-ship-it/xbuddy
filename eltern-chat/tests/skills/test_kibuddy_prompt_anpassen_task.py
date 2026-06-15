"""Tests für KibuddyPromptAnpassenTask und Catalog-Registrierung
(KPA-8, Refs #883).

Abgedeckte ACs:
  AC1  — Skill ist via build_catalog inline registriert (KPA-8, TASK-7);
          Listung zeigt 'kibuddy_prompt_anpassen'.
  AC2  — propose() ohne neuer_prompt → sokratischer Dialog-Start (KPA-4),
          kein GET- oder PUT-Aufruf.
  AC2  — propose() mit neuer_prompt → Diff-Vorschau (KPA-6) + Bestätigungs-
          Frage; GET für alten Prompt wird aufgerufen.
  AC3  — execute() mit neuer_prompt → PUT mit korrektem Text → Erfolgs-Quittung.
  AC3  — execute() bei Backend-400 → Quittung „zu lang" (KPA-7).
  AC3  — execute() bei Backend-500 → Quittung „Schreibfehler" mit .bak-Hinweis.
  AC4  — AND-Guard: ohne kibuddy_origin_url → nicht im Katalog.
  AC4  — AND-Guard: ohne family_group_chat_id_getter → nicht im Katalog.
  KPA-6 — Diff-Vorschau enthält `- ` und `+ ` Zeilen bei echten Änderungen.
  KPA-7 — execute() ohne neuer_prompt → Fehler-Quittung ohne PUT-Aufruf.
  KPA-3 — execute() von Nicht-Mitglied → Berechtigung-Quittung, kein PUT.

Tests laufen ohne Netz (EC-17): KibuddyPromptClient wird durch
FakeKibuddyPromptClient ersetzt (CLIENT-1 Transport-Stub-Naht).
"""

from skills.kibuddy_prompt_anpassen_client import KibuddyPromptClientError
from skills.kibuddy_prompt_anpassen_task import (
    KibuddyPromptAnpassenTask,
    _build_diff,
)
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Doppelungen
# ============================================================

class FakeKibuddyPromptClient:
    """Kontrollierter Doppelter des KibuddyPromptClient (CLIENT-1)."""

    def __init__(self, get_response=None, put_error=None):
        self._get_response = get_response or {
            "prompt": "Ich bin ein KIBuddy.",
            "byte-laenge": 21,
            "geaendert-am": "2026-06-15T10:00:00",
        }
        self._put_error = put_error
        self.get_calls = []
        self.put_calls = []

    def get_prompt(self):
        self.get_calls.append(True)
        return self._get_response

    def put_prompt(self, prompt_text):
        self.put_calls.append(prompt_text)
        if self._put_error is not None:
            raise self._put_error
        return {"ok": True, "byte-laenge": len(prompt_text.encode()),
                "bisherige-laenge": 21}


def _family_getter(fgcid=200):
    return lambda: fgcid


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_task(client=None, family_group_chat_id_getter=None,
               is_member_fn=None):
    if client is None:
        client = FakeKibuddyPromptClient()
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    if is_member_fn is None:
        is_member_fn = _immer_mitglied
    return KibuddyPromptAnpassenTask(
        kibuddy_prompt_client=client,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=is_member_fn)


def _turn_context(user_id=42, chat_id=100):
    tc = TurnContext.__new__(TurnContext)
    tc.from_user_id = user_id
    tc.chat_id = chat_id
    return tc


# ============================================================
#  Grundlegende Task-Eigenschaften
# ============================================================

def test_KPA8_ist_write_task():
    """KPA-8: KibuddyPromptAnpassenTask erbt von WriteTask."""
    assert issubclass(KibuddyPromptAnpassenTask, WriteTask)


def test_KPA8_name():
    """KPA-8: Task-Name ist 'kibuddy_prompt_anpassen'."""
    task = _make_task()
    assert task.name == "kibuddy_prompt_anpassen"


def test_KPA8_ist_sync():
    """KPA-8: is_async=False (synchrone Aufgabe, kein Worker-Thread)."""
    task = _make_task()
    assert task.is_async is False


def test_KPA8_keine_post_execute_hooks():
    """KPA-8: post_execute_hooks ist leer."""
    task = _make_task()
    assert task.post_execute_hooks == ()


# ============================================================
#  AC2 — propose() ohne neuer_prompt → Dialog-Start
# ============================================================

def test_AC2_propose_ohne_prompt_liefert_proposal():
    """AC2: propose() ohne neuer_prompt → Proposal-Objekt."""
    task = _make_task()
    result = task.propose({}, _turn_context())
    assert isinstance(result, Proposal)


def test_AC2_propose_ohne_prompt_startet_dialog():
    """AC2 + KPA-4: propose() ohne neuer_prompt enthält sokratischen Dialog-Start."""
    task = _make_task()
    result = task.propose({}, _turn_context())
    text = result.summary
    # Dialog-Start nennt das Thema und fragt nach dem Wunsch
    assert "KIBuddy" in text or "ändern" in text.lower() or "anpassen" in text.lower()


def test_AC2_propose_ohne_prompt_kein_get():
    """AC2 / TASK-10: propose() ohne neuer_prompt ruft GET NICHT auf."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)
    task.propose({}, _turn_context())
    assert client.get_calls == []


def test_AC2_propose_ohne_prompt_kein_put():
    """TASK-10: propose() ohne neuer_prompt ruft PUT NICHT auf."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)
    task.propose({}, _turn_context())
    assert client.put_calls == []


# ============================================================
#  AC2 — propose() mit neuer_prompt → Diff-Vorschau
# ============================================================

def test_AC2_propose_mit_prompt_liefert_proposal():
    """AC2: propose() mit neuer_prompt → Proposal-Objekt."""
    task = _make_task()
    result = task.propose({"neuer_prompt": "Neuer Text"}, _turn_context())
    assert isinstance(result, Proposal)


def test_AC2_propose_mit_prompt_ruft_get_auf():
    """AC2 + KPA-6: propose() mit neuer_prompt ruft GET für alten Prompt auf."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)
    task.propose({"neuer_prompt": "Neuer Text"}, _turn_context())
    assert len(client.get_calls) == 1


def test_AC2_propose_mit_prompt_enthaelt_bestaetigungsfrage():
    """AC2 + KPA-6: Diff-Vorschau enthält Bestätigungs-Frage."""
    task = _make_task()
    result = task.propose({"neuer_prompt": "Neuer Text"}, _turn_context())
    text = result.summary
    assert "Bestätig" in text or "ja" in text.lower() or "nein" in text.lower()


def test_AC2_propose_kein_put():
    """TASK-10: propose() mit neuer_prompt ruft PUT NICHT auf."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)
    task.propose({"neuer_prompt": "Neuer Text"}, _turn_context())
    assert client.put_calls == []


# ============================================================
#  KPA-6 — Diff-Vorschau enthält Diff-Zeilen
# ============================================================

def test_KPA6_diff_enthaelt_minus_und_plus_zeilen():
    """KPA-6: Diff zwischen altem und neuem Text enthält '- ' und '+ ' Zeilen."""
    alter = "Zeile 1\nZeile 2 alt\nZeile 3"
    neuer = "Zeile 1\nZeile 2 neu\nZeile 3"
    diff = _build_diff(alter, neuer)
    assert "- " in diff
    assert "+ " in diff


def test_KPA6_diff_identischer_text():
    """KPA-6: Diff bei identischem Text meldet 'kein Unterschied'."""
    text = "Gleicher Text"
    diff = _build_diff(text, text)
    assert "identisch" in diff.lower() or "kein" in diff.lower()


def test_KPA6_propose_diff_in_proposal_summary():
    """KPA-6: propose() mit geändertem Prompt enthält Diff-Indikatoren."""
    client = FakeKibuddyPromptClient(get_response={
        "prompt": "Zeile 1\nZeile 2 alt\nZeile 3",
        "byte-laenge": 30,
        "geaendert-am": "2026-06-15T10:00:00",
    })
    task = _make_task(client=client)
    result = task.propose(
        {"neuer_prompt": "Zeile 1\nZeile 2 neu\nZeile 3"},
        _turn_context())
    text = result.summary
    # Diff-Vorschau muss Minus- oder Plus-Zeilen enthalten
    assert "- " in text or "+ " in text


# ============================================================
#  AC3 — execute() mit neuer_prompt → PUT + Quittung
# ============================================================

def test_AC3_execute_liefert_erfolgs_quittung():
    """AC3: execute() mit neuer_prompt → Erfolgs-Quittung."""
    task = _make_task()
    result = task.execute({"neuer_prompt": "Mein neuer Prompt"}, _turn_context())
    assert isinstance(result, str)
    assert "aktiv" in result.lower() or "KIBuddy" in result


def test_AC3_execute_put_aufgerufen():
    """AC3: execute() ruft PUT mit korrektem Text auf."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)
    task.execute({"neuer_prompt": "Mein neuer Prompt"}, _turn_context())
    assert client.put_calls == ["Mein neuer Prompt"]


def test_AC3_execute_400_zu_lang_quittung():
    """AC3 + KPA-7: execute() bei Backend-400 → Quittung 'zu lang'."""
    err = KibuddyPromptClientError("Prompt zu lang", status=400)
    client = FakeKibuddyPromptClient(put_error=err)
    task = _make_task(client=client)

    result = task.execute({"neuer_prompt": "x" * 60000}, _turn_context())

    assert isinstance(result, str)
    assert "lang" in result.lower() or "400" in result


def test_AC3_execute_500_schreibfehler_quittung():
    """AC3 + KPA-7: execute() bei Backend-500 → Quittung 'Schreibfehler' + .bak-Hinweis."""
    err = KibuddyPromptClientError("Disk voll", status=500)
    client = FakeKibuddyPromptClient(put_error=err)
    task = _make_task(client=client)

    result = task.execute({"neuer_prompt": "Mein neuer Prompt"}, _turn_context())

    assert isinstance(result, str)
    assert "500" in result or "Schreibfehler" in result or ".bak" in result


def test_AC3_execute_500_enthaelt_bak_hinweis():
    """KPA-7 / KIBUDDY-15: Fehler-Quittung bei 500 enthält Hinweis auf .bak."""
    err = KibuddyPromptClientError("Schreibfehler", status=500)
    client = FakeKibuddyPromptClient(put_error=err)
    task = _make_task(client=client)

    result = task.execute({"neuer_prompt": "Mein neuer Prompt"}, _turn_context())

    assert ".bak" in result or "Backup" in result


# ============================================================
#  KPA-7 — execute() ohne neuer_prompt
# ============================================================

def test_execute_ohne_prompt_kein_put():
    """KPA-7: execute() ohne neuer_prompt → kein PUT-Aufruf."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)

    result = task.execute({}, _turn_context())

    assert client.put_calls == []
    assert isinstance(result, str)


# ============================================================
#  KPA-3 — Berechtigungs-Prüfung
# ============================================================

def test_KPA3_nicht_mitglied_kein_put():
    """KPA-3: execute() von Nicht-Mitglied → kein PUT, Berechtigung-Quittung."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client, is_member_fn=_kein_mitglied)

    result = task.execute({"neuer_prompt": "Mein neuer Prompt"}, _turn_context())

    assert client.put_calls == []
    assert isinstance(result, str)
    assert "Mitglied" in result or "Gruppe" in result


# ============================================================
#  Nicht-erreichbar (Connection-Fehler)
# ============================================================

def test_execute_nicht_erreichbar_quittung():
    """KPA-7: Connection-Fehler → 'nicht erreichbar'-Quittung."""
    err = KibuddyPromptClientError("Connection refused", status=None)
    client = FakeKibuddyPromptClient(put_error=err)
    task = _make_task(client=client)

    result = task.execute({"neuer_prompt": "Mein neuer Prompt"}, _turn_context())

    assert "erreichbar" in result.lower()


# ============================================================
#  AC4 + AC1 — Catalog-Registrierung via build_catalog (KPA-8, TASK-7)
# ============================================================

class _FakeTelegram:
    """Minimaler Telegram-Stub für build_catalog-Tests."""
    def get_chat_member(self, chat_id, user_id):
        return {"status": "member"}


def _make_catalog_via_build_catalog(kibuddy_url="http://127.0.0.1:5054",
                                     fgcid_getter=None):
    """Baut einen Catalog via build_catalog mit KPA-Parametern (KPA-8, TASK-7)."""
    if fgcid_getter is None:
        fgcid_getter = _family_getter()
    return build_catalog(
        _FakeTelegram(), "/instanz/rootCA.pem",
        kibuddy_origin_url=kibuddy_url,
        family_group_chat_id_getter=fgcid_getter)


def test_AC1_skill_ist_registriert():
    """AC1: build_catalog mit kibuddy_origin_url registriert den Skill im Katalog (KPA-8)."""
    catalog = _make_catalog_via_build_catalog()
    task = catalog.get("kibuddy_prompt_anpassen")
    assert task is not None


def test_AC4_ohne_kibuddy_url_nicht_registriert():
    """AC4 AND-Guard: ohne kibuddy_origin_url → KPA-Skill NICHT im Katalog."""
    catalog = build_catalog(
        _FakeTelegram(), "/instanz/rootCA.pem",
        family_group_chat_id_getter=_family_getter())
    task = catalog.get("kibuddy_prompt_anpassen")
    assert task is None


def test_AC4_ohne_family_getter_nicht_registriert():
    """AC4 AND-Guard: ohne family_group_chat_id_getter → KPA-Skill NICHT im Katalog."""
    catalog = build_catalog(
        _FakeTelegram(), "/instanz/rootCA.pem",
        kibuddy_origin_url="http://127.0.0.1:5054",
    )
    task = catalog.get("kibuddy_prompt_anpassen")
    assert task is None


def test_AC1_skill_name_in_katalog():
    """AC1: Registrierter Task trägt Namen 'kibuddy_prompt_anpassen'."""
    catalog = _make_catalog_via_build_catalog()
    task = catalog.get("kibuddy_prompt_anpassen")
    assert task.name == "kibuddy_prompt_anpassen"


def test_AC1_kaqs_und_kpa_beide_registriert():
    """AC1: build_catalog mit kibuddy_origin_url registriert BEIDE Skills (KAQS + KPA)."""
    catalog = _make_catalog_via_build_catalog()
    assert catalog.get("kibuddy_aufnahme_quelle_setzen") is not None
    assert catalog.get("kibuddy_prompt_anpassen") is not None
