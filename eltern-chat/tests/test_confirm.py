"""Tests für die Bestätigung — EC-10, E-EC-7 (Refs #27).

EC-36 Korrektur-State (#844): zusätzlich der Single-Slot-Lifecycle für
`CorrectionState` (set/get/clear).
"""

import confirm
from confirm import CorrectionState, PendingProposal, PendingStore

# -- is_confirmation: deterministischer Wort-Abgleich (E-EC-7) ----

def test_E_EC_7_thumbs_up_is_confirmation():
    assert confirm.is_confirmation("👍") is True


def test_E_EC_7_confirm_words_are_recognized():
    for word in ("ok", "OK", "Ja", "  okay ", "gogogo", "passt"):
        assert confirm.is_confirmation(word) is True, word


def test_E_EC_7_non_confirm_text_is_not_confirmation():
    for text in ("ja aber lieber Dienstag", "nein", "vielleicht", "", None):
        assert confirm.is_confirmation(text) is False, text


def test_E_EC_7_partial_match_is_not_confirmation():
    """Ganzes Wort, kein Teilstring: »jacke« ist kein »ja«."""
    assert confirm.is_confirmation("jacke") is False


# -- E-EC-7-Nachschärfung (#1118): Mehrwort-Bestätigung -----------

def test_E_EC_7_mehrwort_bestaetigung_ist_confirmation():
    """#1118-Regression: »Ja mach« & Co. bestätigen (token-weise, Füller)."""
    for text in ("Ja mach", "ja bitte", "mach gerne", "ja mach bitte",
                 "ok gerne", "ja!", "ja 👍", "mach los"):
        assert confirm.is_confirmation(text) is True, text


def test_E_EC_7_mehrwort_mit_fremdwort_bleibt_keine_bestaetigung():
    """Jedes Fremdwort ⇒ False — Ablehnungs-Phrasen & Hedges bleiben abgewiesen."""
    for text in ("ja aber lieber Dienstag", "doch nicht", "lass mal",
                 "mach mal langsam", "ja aber ok", "das nicht", " nein danke",
                 "mach das"):  # »das« ist kein Füller ⇒ False
        assert confirm.is_confirmation(text) is False, text


def test_E_EC_7_nur_fueller_ohne_bestaetigungswort_ist_keine_bestaetigung():
    """»bitte gerne« ohne echtes Bestätigungswort bestätigt nicht."""
    assert confirm.is_confirmation("bitte gerne") is False


# -- E-EC-13 (#1118): kein falscher Erfolg bei offenem Vorschlag --

def test_E_EC_13_erfolgsbehauptung_wird_ersetzt():
    """»vertont/fertig«-Halluzination → ehrlicher Bestätigungs-Hinweis."""
    for text in ("Die Folge wird jetzt vertont – 1–5 Minuten.",
                 "Alles erledigt!", "Ist fertig, viel Spaß!",
                 "Der Termin ist eingetragen."):
        out = confirm.honest_no_false_success(text)
        assert out == confirm._HONEST_PENDING_REPLY, text


def test_E_EC_13_rueckfrage_bleibt_unangetastet():
    """Endet auf »?« = legitimer Re-Propose → nicht zensiert."""
    text = "Soll ich die Folge vertonen?"
    assert confirm.honest_no_false_success(text) == text


def test_E_EC_13_neutraler_text_bleibt_unangetastet():
    text = "Das Wetter wird morgen sonnig."
    assert confirm.honest_no_false_success(text) == text


# -- PendingStore: eindeutige Zuordnung Bestätigung -> Vorschlag --

def _proposal(chat="c1", msg_id=10, task="t", args=None):
    return PendingProposal(chat_id=chat, proposal_message_id=msg_id,
                           task_name=task, arguments=args or {})


def test_EC_10_take_by_reply_matches_exact_proposal():
    """EC-10 Single-Slot: take() per Reply-ID liefert den aktiven Vorschlag."""
    store = PendingStore()
    store.add(_proposal(msg_id=20, task="aktiv"))
    # Bestätigung als Antwort auf die aktive Vorschlags-Nachricht.
    taken = store.take("c1", reply_to_message_id=20)
    assert taken.task_name == "aktiv"
    assert store.open_count("c1") == 0


def test_EC_10_take_by_reply_unknown_id_returns_none():
    store = PendingStore()
    store.add(_proposal(msg_id=10))
    assert store.take("c1", reply_to_message_id=999) is None


def test_EC_10_take_without_reply_uses_single_open_proposal():
    store = PendingStore()
    store.add(_proposal(msg_id=10, task="einzige"))
    taken = store.take("c1", reply_to_message_id=None)
    assert taken.task_name == "einzige"


def test_EC_10_verdraengt_vorhandenen_pending_bei_zweitem_add():
    """EC-10 Single-Slot: zweites add() verdrängt erstes; take() liefert nur zweiten.

    Latest-wins-list ist verworfen (EC-10:664-671). open_count() ist nach
    zwei add() exakt 1 — kein Multi-Slot.
    """
    store = PendingStore()
    store.add(_proposal(msg_id=10, task="erster"))
    store.add(_proposal(msg_id=20, task="zweiter"))
    # open_count ist 1, nicht 2 — Single-Slot-Garantie
    assert store.open_count("c1") == 1
    # take() ohne Reply liefert den jüngsten (und einzigen) Vorschlag
    taken = store.take("c1", reply_to_message_id=None)
    assert taken is not None
    assert taken.task_name == "zweiter"
    assert store.open_count("c1") == 0


def test_EC_10_no_pending_proposal_returns_none():
    assert PendingStore().take("c1", reply_to_message_id=None) is None


def test_EC_10_taken_proposal_is_consumed():
    store = PendingStore()
    store.add(_proposal(msg_id=10))
    store.take("c1", reply_to_message_id=10)
    # ein zweites Mal nicht mehr da — keine doppelte Ausführung
    assert store.take("c1", reply_to_message_id=10) is None


# ============================================================
#  EC-36 Korrektur-State (#844)
# ============================================================


def _correction(skill="einkauf_hinzufuegen", args=None, quelle="a2"):
    return CorrectionState(last_skill=skill, last_args=args or {},
                           quelle=quelle)


def test_EC_36_get_correction_returns_none_initially():
    """Frischer Store hat keinen Korrektur-State."""
    assert PendingStore().get_correction("c1") is None


def test_EC_36_set_and_get_correction_roundtrip():
    """set_correction() macht den State per get_correction() sichtbar."""
    store = PendingStore()
    state = _correction(skill="foto_senden", quelle="a2")
    store.set_correction("c1", state)

    got = store.get_correction("c1")
    assert got is state
    assert got.last_skill == "foto_senden"
    assert got.quelle == "a2"


def test_EC_36_clear_correction_macht_state_unsichtbar():
    """clear_correction() löscht den State (genau-ein-Turn-Lebensdauer)."""
    store = PendingStore()
    store.set_correction("c1", _correction())
    store.clear_correction("c1")
    assert store.get_correction("c1") is None


def test_EC_36_set_correction_verdraengt_vorhandenen_state():
    """Zweites set_correction() ersetzt den ersten State atomar (Single-Slot)."""
    store = PendingStore()
    store.set_correction("c1", _correction(skill="erster"))
    store.set_correction("c1", _correction(skill="zweiter"))
    assert store.get_correction("c1").last_skill == "zweiter"


def test_EC_36_correction_state_per_chat_isoliert():
    """States verschiedener chat_ids stören sich nicht."""
    store = PendingStore()
    store.set_correction("c1", _correction(skill="skill1"))
    store.set_correction("c2", _correction(skill="skill2"))
    assert store.get_correction("c1").last_skill == "skill1"
    assert store.get_correction("c2").last_skill == "skill2"
    store.clear_correction("c1")
    # c2 bleibt erhalten
    assert store.get_correction("c1") is None
    assert store.get_correction("c2").last_skill == "skill2"
