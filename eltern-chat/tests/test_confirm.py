"""Tests für die Bestätigung — EC-10, E-EC-7 (Refs #27)."""

import confirm
from confirm import PendingProposal, PendingStore

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


# -- PendingStore: eindeutige Zuordnung Bestätigung -> Vorschlag --

def _proposal(chat="c1", msg_id=10, task="t", args=None):
    return PendingProposal(chat_id=chat, proposal_message_id=msg_id,
                           task_name=task, arguments=args or {})


def test_EC_10_take_by_reply_matches_exact_proposal():
    store = PendingStore()
    store.add(_proposal(msg_id=10, task="erste"))
    store.add(_proposal(msg_id=20, task="zweite"))
    # Bestätigung als Antwort auf die zweite Vorschlags-Nachricht.
    taken = store.take("c1", reply_to_message_id=20)
    assert taken.task_name == "zweite"
    # die erste bleibt offen
    assert store.open_count("c1") == 1


def test_EC_10_take_by_reply_unknown_id_returns_none():
    store = PendingStore()
    store.add(_proposal(msg_id=10))
    assert store.take("c1", reply_to_message_id=999) is None


def test_EC_10_take_without_reply_uses_single_open_proposal():
    store = PendingStore()
    store.add(_proposal(msg_id=10, task="einzige"))
    taken = store.take("c1", reply_to_message_id=None)
    assert taken.task_name == "einzige"


def test_EC_10_take_without_reply_is_ambiguous_with_multiple():
    """Mehrere offene Vorschläge ohne Antwortbezug → keine Bestätigung, statt zu raten."""
    store = PendingStore()
    store.add(_proposal(msg_id=10))
    store.add(_proposal(msg_id=20))
    assert store.take("c1", reply_to_message_id=None) is None
    # beide bleiben offen
    assert store.open_count("c1") == 2


def test_EC_10_no_pending_proposal_returns_none():
    assert PendingStore().take("c1", reply_to_message_id=None) is None


def test_EC_10_taken_proposal_is_consumed():
    store = PendingStore()
    store.add(_proposal(msg_id=10))
    store.take("c1", reply_to_message_id=10)
    # ein zweites Mal nicht mehr da — keine doppelte Ausführung
    assert store.take("c1", reply_to_message_id=10) is None
