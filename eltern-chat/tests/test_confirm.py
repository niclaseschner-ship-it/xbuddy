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
