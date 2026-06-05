"""Berechtigung — siehe specs/platform/eltern-chat.md EC-2/EC-3, E-EC-3/E-EC-4
(Refs #27).

Sicherheits-Gate: Berechtigt ist, wer im Moment der Nachricht Mitglied der
Familien-Gruppe ist. Geprüft wird je eingehender Nachricht live (E-EC-3) —
keine zweite Wahrheitsquelle neben der Gruppe.

Dieses Modul liegt bewusst AUSSERHALB des Agent-Loops (E-EC-4): der LLM ruft es
nie auf. agent.py importiert authz nicht.
"""

import logging

from telegram import ChatMigratedError

# Telegram-Mitglieds-Status, die als „in der Gruppe" gelten.
_MEMBER_STATUSES = frozenset({"creator", "administrator", "member"})


def is_authorized(tg, family_group_chat_id, user_id):
    """True, wenn `user_id` aktuell Mitglied der Familien-Gruppe ist (EC-2).

    `tg` ist ein Objekt mit `get_chat_member(chat_id, user_id)` (TelegramClient).
    Bei einem API-Fehler gilt: nicht berechtigt — ein Fehler darf keine
    Berechtigung erteilen.
    """
    try:
        member = tg.get_chat_member(family_group_chat_id, user_id)
    except ChatMigratedError:
        # EC-18: Eine Supergruppen-Migration ist keine Berechtigungsfrage — der
        # Aufrufer zieht die Gruppen-Bindung nach. Nicht als „nicht berechtigt"
        # verschlucken.
        raise
    except Exception as e:
        logging.warning("Mitgliedschaftsprüfung fehlgeschlagen für %s: %s", user_id, e)
        return False
    if not isinstance(member, dict):
        return False
    status = member.get("status")
    if status in _MEMBER_STATUSES:
        return True
    # 'restricted' zählt nur, solange der Nutzer die Gruppe nicht verlassen hat.
    if status == "restricted":
        return bool(member.get("is_member"))
    # 'left', 'kicked', alles andere: nicht berechtigt.
    return False
