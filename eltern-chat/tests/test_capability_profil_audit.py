"""Audit-Tests für die drei Capability-Profil-Sonderfälle — #842, 2026-06-15.

Prüft, dass die aktuellen Implementierungen zu den Profil-Angaben in der
Capability-Karte (conventions/eltern-chat-skills.md ab Z. 29) passen:

  1. panel_anlegen  — zweistufig (WriteTask propose+execute) + Worker-Identität
                      (is_async=True, startet Privatchat-Session).
  2. termin_eintragen — gemischt-heute: WriteTask + is_async=True,
                        kein A2-Receipt (kein post_execute_hooks-Eintrag
                        der ein A2-Receipt trägt). Plan-Buddy hat kein
                        DELETE für /api/v1/plan/termine (PLAN-22-Nachweis).
  3. termine_aus_bild — Sammler-Worker: is_async=True, Mehrfach-Ressourcen
                        (Bulk-POST, nicht Single-PUT), kein DELETE-Pfad
                        im Task-Modul.

Kein Verhalten wird hier verändert — reine Profil-Konsistenz-Assertions.
"""

import inspect

from skills.panel_anlegen_task import PanelAnlegenTask
from skills.termin_eintragen_task import TermineEintragenTask
from skills.termine_aus_bild_task import TermineAusBildTask
from tasks import WriteTask

# ============================================================
#  Hilfs-Bausteine
# ============================================================

def _make_panel_task():
    """Minimale PanelAnlegenTask — keine echten Clients nötig."""
    return PanelAnlegenTask(
        tg=None,
        panel_origin_url="http://127.0.0.1:5041",
        geraete_origin_url="http://127.0.0.1:5050",
        sessions={},
        family_group_chat_id_getter=lambda: 100,
    )


def _make_tes_task():
    """Minimale TermineEintragenTask — FakePlanClient nicht nötig (kein Aufruf)."""
    class _NullClient:
        pass
    return TermineEintragenTask(
        tg=None,
        plan_client=_NullClient(),
        sessions={},
        family_group_chat_id_getter=lambda: 100,
        is_member_fn=lambda uid: True,
    )


def _make_tab_task():
    """Minimale TermineAusBildTask — keine echten Clients nötig."""
    class _NullClient:
        pass
    return TermineAusBildTask(
        tg=None,
        multimodal_provider=_NullClient(),
        plan_client=_NullClient(),
        sessions={},
        family_group_chat_id_getter=lambda: 100,
        is_member_fn=lambda uid: True,
    )


# ============================================================
#  Profil 1 — panel_anlegen
#  Capability-Karte: zweistufig + Worker-Identität (Cluster C + E)
# ============================================================

def test_PAA_is_write_task():
    """panel_anlegen ist ein WriteTask (zweistufig, EC-10 Confirm-Gate)."""
    task = _make_panel_task()
    assert isinstance(task, WriteTask)


def test_PAA_hat_propose_und_execute():
    """panel_anlegen hat propose()- und execute()-Methoden (zweistufig per Capability-Karte)."""
    task = _make_panel_task()
    assert callable(getattr(task, "propose", None)), "propose() fehlt"
    assert callable(getattr(task, "execute", None)), "execute() fehlt"


def test_PAA_is_async_worker_identitaet():
    """panel_anlegen ist is_async=True — Worker-Identität per Capability-Karte (TASK-5).

    execute() startet einen Worker-Thread statt synchron zu schreiben; das
    entspricht dem Profil-Achse-2-Eintrag 'zweistufig + Worker-Identität'.
    """
    task = _make_panel_task()
    assert task.is_async is True


# ============================================================
#  Profil 2 — termin_eintragen
#  Capability-Karte: gemischt heute — is_async=True, kein A2-Receipt,
#  Plan-Buddy DELETE-Lücke (Profil-Achse 5 = "kein")
# ============================================================

def test_TES_is_write_task():
    """termin_eintragen ist ein WriteTask (EC-10 Confirm-Gate)."""
    task = _make_tes_task()
    assert isinstance(task, WriteTask)


def test_TES_is_async_heute_zweistufig_worker():
    """termin_eintragen ist heute is_async=True (Worker-Confirm, kein A2-Receipt).

    Profil-Achse 2 = 'sofort (A2) ODER zweistufig je Anstoß' — die aktuelle
    Implementierung nutzt immer den Worker-Pfad (is_async=True), weil
    Plan-Buddy DELETE fehlt und A2-Bedingung 2 nicht erfüllt ist.
    """
    task = _make_tes_task()
    assert task.is_async is True


def test_TES_kein_a2_receipt_in_hooks():
    """termin_eintragen hat keinen A2-Receipt-Eintrag in post_execute_hooks.

    Plan-Buddy DELETE für /api/v1/plan/termine fehlt (PLAN-22, nur GET|PUT) —
    Profil-Achse 5 = 'kein'; ohne DELETE ist ein A2-Receipt-Mechanismus
    nicht implementierbar (EC-10-A2-Bedingung 2). Daher: leere Hooks.
    """
    task = _make_tes_task()
    assert task.post_execute_hooks == ()


# ============================================================
#  Profil 3 — termine_aus_bild
#  Capability-Karte: Sammler-Worker (Mehrfach-Ressourcen, N, kein DELETE)
# ============================================================

def test_TAB_is_write_task():
    """termine_aus_bild ist ein WriteTask (EC-10 Confirm-Gate, TAB-12)."""
    task = _make_tab_task()
    assert isinstance(task, WriteTask)


def test_TAB_is_async_sammler():
    """termine_aus_bild ist is_async=True — Sammler-Worker per Capability-Karte.

    Profil-Achse 3 = 'Mehrstufig (Worker)', Profil-Achse 4 = N (Mehrfach-
    Ressourcen). Der Bulk-POST-Pfad (PLAN-33) trägt N Termine auf einmal.
    """
    task = _make_tab_task()
    assert task.is_async is True


def test_TAB_kein_delete_pfad_im_modul():
    """termine_aus_bild-Modul enthält keinen DELETE-Aufruf.

    Profil-Achse 5 = 'kein' — Plan-Buddy hat keinen DELETE-Endpunkt für
    /api/v1/plan/termine (PLAN-22 nur GET|PUT). Der TAB-Worker schreibt
    additiv via Bulk-POST; ein Rückgängig-Pfad ist nicht implementiert.
    """
    import skills.termine_aus_bild_task as tab_mod
    source = inspect.getsource(tab_mod)
    # Kein DELETE-Methodenaufruf im Task-Modul (weder .delete( noch "DELETE")
    assert ".delete(" not in source.lower() or _nur_kommentar_delete(source), (
        "termine_aus_bild_task enthält einen DELETE-Aufruf — "
        "widerspricht Profil-Achse 5 = 'kein' per Capability-Karte"
    )


def _nur_kommentar_delete(source):
    """Gibt True zurück, wenn 'delete' nur in Kommentaren/Docstrings vorkommt.

    Hilfs-Funktion für test_TAB_kein_delete_pfad_im_modul: erlaubt Erwähnungen
    in Kommentaren (z. B. «kein DELETE»), aber keine Code-Aufrufe.
    """
    for line in source.splitlines():
        stripped = line.strip()
        if ".delete(" in stripped.lower() and not stripped.startswith("#"):
            return False
    return True
