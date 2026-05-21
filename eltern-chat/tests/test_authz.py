"""Tests für die Berechtigung — EC-2/EC-3, E-EC-3 (Refs #27)."""

import authz


class _Telegram:
    """Doppelung, die getChatMember kontrolliert beantwortet."""

    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises
        self.calls = []

    def get_chat_member(self, chat_id, user_id):
        self.calls.append((chat_id, user_id))
        if self._raises is not None:
            raise self._raises
        return self._result


def test_EC_2_member_is_authorized():
    tg = _Telegram(result={"status": "member"})
    assert authz.is_authorized(tg, "-100", 7) is True


def test_EC_2_creator_and_admin_are_authorized():
    assert authz.is_authorized(_Telegram(result={"status": "creator"}), "-100", 7)
    assert authz.is_authorized(_Telegram(result={"status": "administrator"}), "-100", 7)


def test_EC_2_left_member_is_not_authorized():
    tg = _Telegram(result={"status": "left"})
    assert authz.is_authorized(tg, "-100", 7) is False


def test_EC_2_kicked_member_is_not_authorized():
    tg = _Telegram(result={"status": "kicked"})
    assert authz.is_authorized(tg, "-100", 7) is False


def test_EC_2_restricted_still_in_group_is_authorized():
    tg = _Telegram(result={"status": "restricted", "is_member": True})
    assert authz.is_authorized(tg, "-100", 7) is True


def test_EC_2_restricted_left_group_is_not_authorized():
    tg = _Telegram(result={"status": "restricted", "is_member": False})
    assert authz.is_authorized(tg, "-100", 7) is False


def test_EC_2_checked_live_against_family_group():
    """E-EC-3: geprüft wird je Nachricht live gegen die Familien-Gruppe."""
    tg = _Telegram(result={"status": "member"})
    authz.is_authorized(tg, "-100777", 42)
    assert tg.calls == [("-100777", 42)]


def test_EC_2_api_error_means_not_authorized():
    """Ein Fehler darf keine Berechtigung erteilen."""
    tg = _Telegram(raises=RuntimeError("API weg"))
    assert authz.is_authorized(tg, "-100", 7) is False
