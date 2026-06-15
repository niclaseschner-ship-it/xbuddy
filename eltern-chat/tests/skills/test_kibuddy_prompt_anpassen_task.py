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
    _DIALOG_START,
    KibuddyPromptAnpassenTask,
    _build_diff,
    _split_for_telegram,
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


# ============================================================
#  KPA-5 — Anzeige-Pfad (AC1-Args-Schema, AC2, AC3, AC5)
# ============================================================

def test_AC1_aktion_anzeigen_ruft_get_prompt():
    """AC1/AC2 (KPA-5): propose() mit aktion='anzeigen' ruft GET auf, kein PUT."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)
    task.propose({"aktion": "anzeigen"}, _turn_context())
    assert len(client.get_calls) == 1
    assert client.put_calls == []


def test_AC2_anzeige_summary_enthaelt_prompt():
    """AC2 (KPA-5): propose() mit aktion='anzeigen' gibt Prompt-Text zurück."""
    client = FakeKibuddyPromptClient(get_response={
        "prompt": "Ich bin ein KIBuddy für die Familie.",
        "byte-laenge": 36,
        "geaendert-am": "2026-06-15T10:00:00",
    })
    task = _make_task(client=client)
    result = task.propose({"aktion": "anzeigen"}, _turn_context())
    assert isinstance(result, Proposal)
    assert "Ich bin ein KIBuddy für die Familie." in result.summary


def test_AC3_langer_prompt_fallback_ohne_tg():
    """AC3 (KPA-5): Prompt > 3500 Zeichen + kein tg → Fallback-Summary mit Warn-Quittung."""
    langer_prompt = ("A" * 1800 + "\n\n" + "B" * 1800)
    client = FakeKibuddyPromptClient(get_response={
        "prompt": langer_prompt,
        "byte-laenge": len(langer_prompt.encode()),
        "geaendert-am": "2026-06-15T10:00:00",
    })
    # _make_task ohne tg → Fallback-Pfad (Backward-Compat)
    task = _make_task(client=client)
    result = task.propose({"aktion": "anzeigen"}, _turn_context())
    assert isinstance(result, Proposal)
    # Fallback-Warnung im summary
    assert "Multi-Part-Send" in result.summary or "nicht verfügbar" in result.summary
    # Trotzdem (Teil X/Y)-Teile im summary (gebündelt)
    assert "(Teil 1/" in result.summary
    assert "(Teil 2/" in result.summary


def test_AC4_anzeige_get_fehler_quittung():
    """AC4/AC5 (KPA-5): GET-Fehler beim Anzeigen → klare Fehler-Quittung."""
    def get_prompt_wirft():
        raise KibuddyPromptClientError("Connection refused", status=None)

    client = FakeKibuddyPromptClient()
    client.get_prompt = get_prompt_wirft
    task = _make_task(client=client)
    result = task.propose({"aktion": "anzeigen"}, _turn_context())
    assert isinstance(result, Proposal)
    assert "erreichbar" in result.summary.lower() or "nochmal" in result.summary.lower()


def test_AC5_aktion_vorschlagen_default_bleibt_kompatibel():
    """AC5: Bestehende Aufrufe ohne aktion-Argument landen weiterhin im Vorschlagen-Pfad."""
    client = FakeKibuddyPromptClient()
    task = _make_task(client=client)
    # Kein aktion-Argument — Backward-Compat Default = 'vorschlagen'
    result = task.propose({}, _turn_context())
    # Ohne neuer_prompt → Dialog-Start (KPA-4)
    assert isinstance(result, Proposal)
    assert "KIBuddy" in result.summary or "ändern" in result.summary.lower()
    # Kein GET-Aufruf beim Dialog-Start
    assert client.get_calls == []


# ============================================================
#  _split_for_telegram — Unit-Tests
# ============================================================

def test_split_kurzer_text_einelementig():
    """_split_for_telegram: kurzer Text → einelementige Liste."""
    parts = _split_for_telegram("Kurz", max_per_part=100)
    assert parts == ["Kurz"]


def test_split_langer_text_schneidet_an_doppel_newline():
    """_split_for_telegram: bevorzugt Schnitt an \\n\\n-Grenze."""
    text = "A" * 50 + "\n\n" + "B" * 50
    parts = _split_for_telegram(text, max_per_part=60)
    assert len(parts) == 2
    assert parts[0] == "A" * 50
    assert parts[1] == "B" * 50


# ============================================================
#  FIX1 — Multi-Part-Send via FakeTg (KPA-5, FIX1-FIX2)
# ============================================================


class FakeTg:
    """Minimaler Telegram-Stub für Multi-Part-Send-Tests (FIX1)."""

    def __init__(self):
        self.sent_messages = []   # Liste von (chat_id, text)-Tupeln

    def send_message(self, chat_id, text):
        self.sent_messages.append((chat_id, text))

    def get_chat_member(self, chat_id, user_id):
        return {"status": "member"}


def _make_task_mit_tg(client=None, tg=None, chat_id_getter=None,
                      family_group_chat_id_getter=None, is_member_fn=None):
    """Hilfsfunktion: Task mit tg + chat_id_getter für FIX1-Tests."""
    if client is None:
        client = FakeKibuddyPromptClient()
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    if is_member_fn is None:
        is_member_fn = _immer_mitglied
    from skills.kibuddy_prompt_anpassen_task import KibuddyPromptAnpassenTask
    return KibuddyPromptAnpassenTask(
        kibuddy_prompt_client=client,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=is_member_fn,
        tg=tg,
        chat_id_getter=chat_id_getter)


def test_FIX1_langer_prompt_sendet_teile_direkt():
    """FIX1 (KPA-5): Langer Prompt + tg → Teile via tg.send_message gesendet."""
    langer_prompt = ("A" * 1800 + "\n\n" + "B" * 1800)
    client = FakeKibuddyPromptClient(get_response={
        "prompt": langer_prompt,
        "byte-laenge": len(langer_prompt.encode()),
        "geaendert-am": "2026-06-15T10:00:00",
    })
    fake_tg = FakeTg()
    task = _make_task_mit_tg(client=client, tg=fake_tg)
    task.propose({"aktion": "anzeigen"}, _turn_context(chat_id=100))

    # tg.send_message muss für jeden Teil aufgerufen worden sein
    assert len(fake_tg.sent_messages) >= 2
    # Alle Sends gehen an die korrekte chat_id
    assert all(chat_id == 100 for chat_id, _ in fake_tg.sent_messages)
    # (Teil X/Y)-Markierung in den gesendeten Nachrichten
    gesendete_texte = [text for _, text in fake_tg.sent_messages]
    assert any("(Teil 1/" in t for t in gesendete_texte)
    assert any("(Teil 2/" in t for t in gesendete_texte)


def test_FIX1_proposal_summary_ist_kurzer_verweis():
    """FIX1 (KPA-5): Nach Multi-Part-Send ist Proposal.summary nur kurzer Verweis."""
    langer_prompt = ("A" * 1800 + "\n\n" + "B" * 1800)
    client = FakeKibuddyPromptClient(get_response={
        "prompt": langer_prompt,
        "byte-laenge": len(langer_prompt.encode()),
        "geaendert-am": "2026-06-15T10:00:00",
    })
    fake_tg = FakeTg()
    task = _make_task_mit_tg(client=client, tg=fake_tg)
    result = task.propose({"aktion": "anzeigen"}, _turn_context(chat_id=100))

    assert isinstance(result, Proposal)
    # Summary ist kurz — kein vollständiger Prompt-Text darin
    assert len(result.summary) < 200
    assert "oben" in result.summary.lower() or "Prompt" in result.summary


def test_FIX2_backward_compat_ohne_tg():
    """FIX2 (KPA-5): Ohne tg und langem Prompt → Fallback-Summary mit Warnung."""
    langer_prompt = ("A" * 1800 + "\n\n" + "B" * 1800)
    client = FakeKibuddyPromptClient(get_response={
        "prompt": langer_prompt,
        "byte-laenge": len(langer_prompt.encode()),
        "geaendert-am": "2026-06-15T10:00:00",
    })
    # Kein tg → Fallback
    task = _make_task(client=client)
    result = task.propose({"aktion": "anzeigen"}, _turn_context())
    assert isinstance(result, Proposal)
    # Warn-Quittung im summary
    assert "Multi-Part-Send" in result.summary or "nicht verfügbar" in result.summary


def test_FIX1_kurzer_prompt_kein_tg_send():
    """FIX1 (KPA-5): Kurzer Prompt → kein tg.send_message-Aufruf."""
    client = FakeKibuddyPromptClient(get_response={
        "prompt": "Kurz.",
        "byte-laenge": 5,
        "geaendert-am": "2026-06-15T10:00:00",
    })
    fake_tg = FakeTg()
    task = _make_task_mit_tg(client=client, tg=fake_tg)
    result = task.propose({"aktion": "anzeigen"}, _turn_context(chat_id=100))

    # Kurzer Prompt: kein send_message
    assert fake_tg.sent_messages == []
    # Volltext im summary
    assert isinstance(result, Proposal)
    assert "Kurz." in result.summary


# ============================================================
#  KPA-4 Mehrturn-Loop-Awareness (Live-Bug 2026-06-15)
# ============================================================
#
# Hintergrund: Nics Live-Test endete nach dem Klär-Dialog ohne erneuten
# Skill-Aufruf — LLM hatte keine explizite Anweisung, dass es nach Eltern-
# Antwort den Skill ein zweites Mal aufrufen MUSS mit `neuer_prompt`.
# Fix: _DIALOG_START im Sach-Ton (FIX3), ohne []-Markup-Marker.

def test_dialog_start_enthaelt_llm_loop_anweisung():
    """KPA-4: _DIALOG_START muss dem LLM explizit den Re-Call vorschreiben (Sach-Ton)."""
    text = _DIALOG_START
    # Loop-Hint: aktion='vorschlagen' + neuer_prompt erneut aufrufen
    assert "erneut" in text.lower() or "wieder" in text.lower() or "nochmal" in text.lower(), (
        "_DIALOG_START muss klar machen, dass der Skill nach Klärung ERNEUT aufgerufen wird"
    )
    # Zielparameter explizit nennen
    assert "neuer_prompt" in text, "_DIALOG_START muss `neuer_prompt` als Ziel-Argument nennen"
    # Kein []-Markup-Marker (FIX3: Sach-Ton ohne [ANWEISUNG]-Blöcke)
    assert "[ANWEISUNG" not in text, (
        "_DIALOG_START darf keine [ANWEISUNG AN DICH, LLM]-Marker enthalten (FIX3-Markup-Stil)"
    )
    assert "[FRAGE" not in text, (
        "_DIALOG_START darf keine [FRAGE AN ELTERN]-Marker enthalten (FIX3-Markup-Stil)"
    )


def test_dialog_start_kein_neuer_prompt_eltern_frage_bleibt():
    """KPA-4: Eltern-Frage ist trotzdem präsent (LLM darf direkten Text an Eltern leiten)."""
    text = _DIALOG_START
    # Eltern-sichtbarer Frage-Teil
    assert "?" in text, "_DIALOG_START sollte eine konkrete Frage an Eltern enthalten"
    assert "Verhalten" in text or "Tonfall" in text or "Themen" in text, (
        "_DIALOG_START sollte konkrete Anpass-Dimensionen für Eltern erwähnen"
    )


def test_description_erwaehnt_mehrturn_re_call():
    """KPA-4: Skill-Description muss dem LLM den Mehrturn-Loop erklären."""
    # Wir bauen einen Mock-Catalog und prüfen die Task-Beschreibung
    task = KibuddyPromptAnpassenTask(
        kibuddy_prompt_client=FakeKibuddyPromptClient(),
        family_group_chat_id_getter=lambda: -123,
    )
    desc = task.description
    assert "ERNEUT" in desc.upper() or "MEHRTURN" in desc.upper() or "ZWEITEN AUFRUF" in desc.upper(), (
        f"Task-Description muss Mehrturn-Re-Call explizit nennen, war: {desc[:200]}"
    )
    assert "neuer_prompt" in desc, "Description muss neuer_prompt als Pfad-C-Argument nennen"


def test_FIX2_langer_diff_sendet_teile_direkt():
    """Live-Bug 2026-06-15 (Nic): Diff-Vorschau bei realem Prompt (~4600 Bytes)
    sprengt Telegram-4096-Limit. _propose_vorschlagen muss bei langem Diff
    ebenfalls über Multi-Part-Send (tg.send_message) gehen."""
    alter_prompt = "Zeile " + "X" * 50  # kurzer alter Prompt
    neuer_prompt = "Zeile " + "Y" * 4500  # >> 3500 Zeichen
    client = FakeKibuddyPromptClient(get_response={
        "prompt": alter_prompt,
        "byte-laenge": len(alter_prompt.encode()),
        "geaendert-am": "2026-06-15T10:00:00",
    })
    fake_tg = FakeTg()
    task = _make_task_mit_tg(client=client, tg=fake_tg)
    result = task.propose(
        {"aktion": "vorschlagen", "neuer_prompt": neuer_prompt},
        _turn_context(chat_id=200))

    # Diff wird via tg multi-part gesendet
    assert len(fake_tg.sent_messages) >= 2, (
        "langer Diff muss in mehreren tg.send_message-Aufrufen landen, "
        f"war: {len(fake_tg.sent_messages)}")
    assert all(chat_id == 200 for chat_id, _ in fake_tg.sent_messages)
    gesendete = [text for _, text in fake_tg.sent_messages]
    assert any("(Teil 1/" in t for t in gesendete)
    # Proposal.summary ist kurzer Verweis + Footer
    assert isinstance(result, Proposal)
    assert "oben" in result.summary.lower() or "siehe" in result.summary.lower()
    assert len(result.summary) < 500


def test_FIX2_kurzer_diff_kein_tg_send():
    """Bei kurzem Diff (< 3500 Zeichen) bleibt das bisherige Verhalten: Diff
    landet als Volltext in Proposal.summary, kein tg.send_message-Call."""
    client = FakeKibuddyPromptClient(get_response={
        "prompt": "Alter Prompt.",
        "byte-laenge": 13,
        "geaendert-am": "2026-06-15T10:00:00",
    })
    fake_tg = FakeTg()
    task = _make_task_mit_tg(client=client, tg=fake_tg)
    result = task.propose(
        {"aktion": "vorschlagen", "neuer_prompt": "Neuer Prompt."},
        _turn_context(chat_id=200))

    # Kurzer Diff: kein Multi-Part, alles in Summary
    assert fake_tg.sent_messages == []
    assert isinstance(result, Proposal)
    assert "- " in result.summary or "+ " in result.summary  # Diff-Zeilen drin
