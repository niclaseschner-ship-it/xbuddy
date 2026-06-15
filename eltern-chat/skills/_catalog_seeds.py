"""Catalog-Seeds für KIBuddy-Skills (TASK-7-Registrierung).

Dieses Modul enthält Seed-Funktionen für die Registrierung von KIBuddy-
Skills in den Eltern-Chat-Katalog. Die Seed-Funktionen werden von
`build_catalog` in `tasks.py` aufgerufen (KAQS-6, TASK-7).

Heutiger Konsument: `kibuddy_aufnahme_quelle_setzen` (KAQS) — erster
KIBuddy-Skill im Eltern-Chat-Katalog (KIBUDDY-23).
"""

from skills.kibuddy_aufnahme_quelle_setzen_client import KibuddyConfigClient
from skills.kibuddy_aufnahme_quelle_setzen_task import (
    KibuddyAufnahmeQuelleSetzenTask,
)


def seed_kibuddy_aufnahme_quelle_setzen(
        catalog,
        kibuddy_origin_url,
        family_group_chat_id_getter,
        is_member_fn=None):
    """Registriert `kibuddy_aufnahme_quelle_setzen` im Katalog (KAQS-6, TASK-7).

    AND-Guard: `kibuddy_origin_url` UND `family_group_chat_id_getter` müssen
    gesetzt sein — fehlt eine, wird die Aufgabe NICHT registriert (analog der
    RZS-/TES-Linie in `build_catalog`).

    `catalog` ist ein `Catalog`-Objekt aus `tasks.py`.
    `kibuddy_origin_url` ist die Basis-Origin des KIBuddys (KIBUDDY-24).
    `family_group_chat_id_getter` ist eine Callable () -> int (EC-2).
    `is_member_fn` ist optional; wenn None, wird eine Immer-true-Funktion
    eingesetzt (auth.py hat die Prüfung bereits gemacht).
    """
    if not kibuddy_origin_url or family_group_chat_id_getter is None:
        return
    client = KibuddyConfigClient(origin_url=kibuddy_origin_url)
    task = KibuddyAufnahmeQuelleSetzenTask(
        kibuddy_config_client=client,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=is_member_fn)
    catalog.register(task)
