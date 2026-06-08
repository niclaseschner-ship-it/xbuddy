"""Tests für die Funktion routine_punkte_setzen + den Task — RPS-1 … RPS-7,
E-RPS-1, E-RPS-2 (Refs #443, hot from #354).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(RPS-7, CLAUDE.md §6). Routine-Buddy, Router-Icon-Suche und Telegram sind
durch kontrollierte Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

Pflicht-Tests (Spec RPS-7 Z. 103-117, AC2/AC3/AC4 des Contracts):
- Katalog enthält RPS genau dann, wenn alle DREI Abhängigkeiten gesetzt sind
  (routine_origin_url, icon_origin_url, family_group_chat_id_getter).
- Nicht-Mitglied → Ablehnung, kein Schreiben (RPS-2).
- Hinzufügen Happy-Path: ICONS-7-Suche → Wahl → propose → execute → POST.
- Einmalig Happy-Path: gleicher Pfad mit quelle=einmalig (RPS-3).
- Löschen: DELETE.
- Reihenfolge: PUT mit geordneter Liste.
- Icon-Suche ohne Treffer → Skill fragt nach anderem Wort, erfindet keine ID
  (RPS-4 / E-RPS-2).
- Buddy-4xx → kein Schreiben, ehrliche Grenze (RPS-5, EC-7).
- APP-3: Skill ruft die API, nicht die Datei.
"""

import contextlib
import os
import tempfile

import pytest
from fakes import FakeTelegram
from skills.icon_client import IconClientError
from skills.routine_client import RoutineClientError
from skills.routine_punkte_setzen import (
    AKTION_EINMALIG,
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
    AKTION_LOESCHEN,
    AKTION_NEU_ORDNEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_GELOESCHT,
    SIGNAL_GRENZE,
    SIGNAL_HINZUGEFUEGT,
    SIGNAL_ICON_KANDIDATEN,
    SIGNAL_KEINE_ICONS,
    SIGNAL_NEUGEORDNET,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_NICHTS_ZU_TUN,
    routine_punkte_setzen,
)
from skills.routine_punkte_setzen_task import RoutinePunkteSetzenTask
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakeRoutineClient:
    """Items-API-Doppelung des RoutineClients (CLIENT-1, RPS-6)."""

    def __init__(self, add_response=None, add_error=None,
                 delete_response=None, delete_error=None,
                 replace_response=None, replace_error=None):
        self.add_calls = []
        self.delete_calls = []
        self.replace_calls = []
        self._add_response = add_response or {"id": "neu-id"}
        self._add_error = add_error
        self._delete_response = delete_response or {"id": "geloescht-id"}
        self._delete_error = delete_error
        self._replace_response = replace_response or {"count": 0}
        self._replace_error = replace_error

    def add_item(self, quelle, label, piktogramm):
        self.add_calls.append({
            "quelle": quelle, "label": label, "piktogramm": piktogramm})
        if self._add_error is not None:
            raise self._add_error
        return dict(self._add_response)

    def delete_item(self, item_id):
        self.delete_calls.append(item_id)
        if self._delete_error is not None:
            raise self._delete_error
        return dict(self._delete_response)

    def replace_default_items(self, items):
        self.replace_calls.append(list(items))
        if self._replace_error is not None:
            raise self._replace_error
        return dict(self._replace_response)


class FakeIconClient:
    """ICONS-7-Doppelung des IconClients (CLIENT-1, RPS-4)."""

    def __init__(self, response=None, error=None):
        self.suche_calls = []
        self._response = response if response is not None else []
        self._error = error

    def suche(self, stichwort, max_treffer=3):
        self.suche_calls.append({
            "stichwort": stichwort, "max_treffer": max_treffer})
        if self._error is not None:
            raise self._error
        return list(self._response)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


# ============================================================
#  RPS-2: Berechtigung — Nicht-Mitglied → Ablehnung, kein Schreiben
# ============================================================

def test_RPS2_nicht_mitglied_kein_post():
    """RPS-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein add_item-Aufruf."""
    rc = FakeRoutineClient()
    ic = FakeIconClient(response=[{"id": 2349, "url": "/x"}])

    signal, _ = routine_punkte_setzen(
        aktion=AKTION_HINZUFUEGEN,
        routine_client=rc,
        icon_client=ic,
        is_member_fn=_kein_mitglied,
        from_user_id=99,
        label="Zähne putzen",
        piktogramm="2349",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert rc.add_calls == [], "Kein POST bei Nicht-Mitglied (RPS-2)"


def test_RPS2_kein_user_id_kein_post():
    """RPS-2: from_user_id=None → SIGNAL_ABGELEHNT, kein POST."""
    rc = FakeRoutineClient()
    ic = FakeIconClient()

    signal, _ = routine_punkte_setzen(
        aktion=AKTION_HINZUFUEGEN,
        routine_client=rc,
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=None,
        label="X", piktogramm="1",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert rc.add_calls == []


def test_RPS2_nicht_mitglied_kein_delete():
    """RPS-2: Nicht-Mitglied → kein DELETE."""
    rc = FakeRoutineClient()
    signal, _ = routine_punkte_setzen(
        aktion=AKTION_LOESCHEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_kein_mitglied,
        from_user_id=99,
        item_id="zaehne-putzen",
    )
    assert signal == SIGNAL_ABGELEHNT
    assert rc.delete_calls == []


def test_RPS2_nicht_mitglied_kein_put():
    """RPS-2: Nicht-Mitglied → kein PUT (Reihenfolge)."""
    rc = FakeRoutineClient()
    signal, _ = routine_punkte_setzen(
        aktion=AKTION_NEU_ORDNEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_kein_mitglied,
        from_user_id=99,
        items=[{"id": "a", "label": "A", "piktogramm": "1"}],
    )
    assert signal == SIGNAL_ABGELEHNT
    assert rc.replace_calls == []


# ============================================================
#  RPS-3: Hinzufügen Happy-Path (dauerhaft + einmalig)
# ============================================================

def test_RPS3_hinzufuegen_default_happy_path():
    """RPS-3: hinzufügen → POST mit quelle=default + label + piktogramm
    (Transport-Stub, CLIENT-1)."""
    rc = FakeRoutineClient(add_response={"id": "zaehne-putzen"})
    ic = FakeIconClient()

    signal, daten = routine_punkte_setzen(
        aktion=AKTION_HINZUFUEGEN,
        routine_client=rc,
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="Zähne putzen",
        piktogramm="2349",
    )

    assert signal == SIGNAL_HINZUGEFUEGT
    assert daten == {"id": "zaehne-putzen", "quelle": "default"}
    assert rc.add_calls == [{
        "quelle": "default",
        "label": "Zähne putzen",
        "piktogramm": "2349",
    }]


def test_RPS3_einmalig_happy_path():
    """RPS-3: einmalig → POST mit quelle=einmalig (ROUTINE-6)."""
    rc = FakeRoutineClient(add_response={"id": "einmalig:turnbeutel-mit"})

    signal, daten = routine_punkte_setzen(
        aktion=AKTION_EINMALIG,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="Turnbeutel mit",
        piktogramm="7777",
    )

    assert signal == SIGNAL_HINZUGEFUEGT
    assert daten["quelle"] == "einmalig"
    assert rc.add_calls[0]["quelle"] == "einmalig"


def test_RPS3_hinzufuegen_ohne_label_nichts_zu_tun():
    """RPS-3: hinzufügen ohne label → SIGNAL_NICHTS_ZU_TUN, kein POST."""
    rc = FakeRoutineClient()
    signal, daten = routine_punkte_setzen(
        aktion=AKTION_HINZUFUEGEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="", piktogramm="1",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "kein Label"
    assert rc.add_calls == []


def test_RPS3_hinzufuegen_ohne_piktogramm_nichts_zu_tun():
    """RPS-4 / E-RPS-2: hinzufügen ohne piktogramm → NICHTS_ZU_TUN, kein POST.

    Der Skill darf NIE eine ARASAAC-ID raten (E-RPS-2) — ohne gewählte ID
    geht's also nicht weiter.
    """
    rc = FakeRoutineClient()
    signal, daten = routine_punkte_setzen(
        aktion=AKTION_HINZUFUEGEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="Zähne", piktogramm="",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "kein Piktogramm"
    assert rc.add_calls == []


# ============================================================
#  RPS-3: Löschen
# ============================================================

def test_RPS3_loeschen_happy_path():
    """RPS-3: loeschen → DELETE /api/v1/routine/items/<id>."""
    rc = FakeRoutineClient(delete_response={"id": "zaehne-putzen"})

    signal, daten = routine_punkte_setzen(
        aktion=AKTION_LOESCHEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        item_id="zaehne-putzen",
    )

    assert signal == SIGNAL_GELOESCHT
    assert daten == {"id": "zaehne-putzen"}
    assert rc.delete_calls == ["zaehne-putzen"]


def test_RPS3_loeschen_ohne_id_nichts_zu_tun():
    """RPS-3: loeschen ohne item_id → SIGNAL_NICHTS_ZU_TUN, kein DELETE."""
    rc = FakeRoutineClient()
    signal, _ = routine_punkte_setzen(
        aktion=AKTION_LOESCHEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        item_id=None,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert rc.delete_calls == []


# ============================================================
#  RPS-3: Reihenfolge ändern (PUT)
# ============================================================

def test_RPS3_neu_ordnen_happy_path():
    """RPS-3: neu_ordnen → PUT /api/v1/routine/items mit geordneter Liste."""
    rc = FakeRoutineClient(replace_response={"count": 3})
    items = [
        {"id": "anziehen", "label": "Anziehen", "piktogramm": "1"},
        {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "2"},
        {"id": "zaehne", "label": "Zähne", "piktogramm": "3"},
    ]

    signal, daten = routine_punkte_setzen(
        aktion=AKTION_NEU_ORDNEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        items=items,
    )

    assert signal == SIGNAL_NEUGEORDNET
    assert daten == {"count": 3}
    assert rc.replace_calls == [items]


def test_RPS3_neu_ordnen_ohne_items_nichts_zu_tun():
    """RPS-3: neu_ordnen ohne items → SIGNAL_NICHTS_ZU_TUN, kein PUT."""
    rc = FakeRoutineClient()
    signal, _ = routine_punkte_setzen(
        aktion=AKTION_NEU_ORDNEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        items=None,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert rc.replace_calls == []


# ============================================================
#  RPS-4 + E-RPS-2: ICONS-7-Suche
# ============================================================

def test_RPS4_icon_suchen_drei_kandidaten():
    """RPS-4: icon_suchen → ICONS-7-Aufruf mit q=<wort>&max=3,
    Liefert SIGNAL_ICON_KANDIDATEN mit den Treffern."""
    ic = FakeIconClient(response=[
        {"id": 2349, "url": "/display/_shared/icons/arasaac/2349.png"},
        {"id": 8800, "url": "/display/_shared/icons/arasaac/8800.png"},
        {"id": 7777, "url": "/display/_shared/icons/arasaac/7777.png"},
    ])

    signal, daten = routine_punkte_setzen(
        aktion=AKTION_ICON_SUCHEN,
        routine_client=FakeRoutineClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Zähne",
    )

    assert signal == SIGNAL_ICON_KANDIDATEN
    assert daten["label"] == "Zähne"
    assert len(daten["kandidaten"]) == 3
    assert {k["id"] for k in daten["kandidaten"]} == {2349, 8800, 7777}
    # ICONS-7: q + max≤3
    assert ic.suche_calls == [{"stichwort": "Zähne", "max_treffer": 3}]


def test_RPS4_icon_suchen_keine_treffer_kein_erfundenes_piktogramm():
    """RPS-4 / E-RPS-2: ICONS-7 ohne Treffer → SIGNAL_KEINE_ICONS, Skill
    fragt nach anderem Wort, erfindet KEINE ID, fällt NICHT auf ARASAAC
    zurück (zweiter Icon-Pfad explizit verboten, E-RPS-2)."""
    ic = FakeIconClient(response=[])

    signal, daten = routine_punkte_setzen(
        aktion=AKTION_ICON_SUCHEN,
        routine_client=FakeRoutineClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Glubschauge",
    )

    assert signal == SIGNAL_KEINE_ICONS
    assert daten["label"] == "Glubschauge"


def test_RPS4_icon_max_wird_auf_3_gecapped():
    """RPS-4: »bis zu drei Kandidaten« — der Client cappt auf 3, auch
    wenn das Modell mehr verlangt."""
    ic = FakeIconClient(response=[{"id": 1, "url": "/a"}])

    routine_punkte_setzen(
        aktion=AKTION_ICON_SUCHEN,
        routine_client=FakeRoutineClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Hund",
        icon_max=42,
    )

    assert ic.suche_calls[0]["max_treffer"] == 3


def test_RPS4_icon_suchen_router_nicht_erreichbar():
    """RPS-5 / EC-7: ICONS-7 wirft IconClientError → SIGNAL_NICHT_ERREICHBAR."""
    ic = FakeIconClient(error=IconClientError("Router nicht erreichbar"))

    signal, _ = routine_punkte_setzen(
        aktion=AKTION_ICON_SUCHEN,
        routine_client=FakeRoutineClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Zähne",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR


# ============================================================
#  RPS-5: Buddy-4xx → ehrliche Grenze, kein Schreiben (EC-7)
# ============================================================

def test_RPS5_buddy_4xx_grenze_kein_re_try():
    """RPS-5: 4xx vom Buddy (>8 Punkte, ROUTINE-19) → SIGNAL_GRENZE mit
    Buddy-Fehlermeldung, KEIN automatisches Re-Try (ehrliche Grenze EC-7)."""
    rc = FakeRoutineClient(add_error=RoutineClientError(
        "Routine-Buddy: HTTP 400 bei POST /api/v1/routine/items — "
        "Maximal 8 Routine-Punkte erlaubt (ROUTINE-19)."))

    signal, daten = routine_punkte_setzen(
        aktion=AKTION_HINZUFUEGEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="9. Punkt",
        piktogramm="1",
    )

    assert signal == SIGNAL_GRENZE
    assert "Maximal 8" in daten["detail"]
    # 4xx wird einmal versucht, nicht wiederholt.
    assert len(rc.add_calls) == 1


def test_RPS5_buddy_5xx_nicht_erreichbar():
    """RPS-5: 5xx vom Buddy → SIGNAL_NICHT_ERREICHBAR."""
    rc = FakeRoutineClient(add_error=RoutineClientError(
        "Routine-Buddy: HTTP 503"))

    signal, _ = routine_punkte_setzen(
        aktion=AKTION_HINZUFUEGEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="X", piktogramm="1",
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR


def test_RPS5_delete_404_grenze():
    """RPS-5: DELETE 404 (ID nicht gefunden) → SIGNAL_GRENZE."""
    rc = FakeRoutineClient(delete_error=RoutineClientError(
        "Routine-Buddy: HTTP 404 bei DELETE /api/v1/routine/items/unbekannt"))

    signal, _ = routine_punkte_setzen(
        aktion=AKTION_LOESCHEN,
        routine_client=rc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        item_id="unbekannt",
    )
    assert signal == SIGNAL_GRENZE


# ============================================================
#  APP-3: Skill ruft die API, nicht die Datei
# ============================================================

def test_APP3_keine_datei_zugriffe():
    """APP-3 / RPS-6: die Funktion liest/schreibt routine.json NICHT direkt.

    Der RoutineClient ist die einzige Items-Schreib-Naht (RPS-6), der
    IconClient die einzige Icon-Lese-Naht (RPS-4). Wenn beides als Fake
    injiziert ist und gleichzeitig open() blockiert wird, müssen die Tests
    durchlaufen — ein FS-Bypass würde die `open`-Blockade auslösen.
    """
    import unittest.mock as mock

    rc = FakeRoutineClient(add_response={"id": "x"})
    ic = FakeIconClient(response=[{"id": 1, "url": "/x"}])
    with mock.patch("builtins.open",
                    side_effect=AssertionError("FS-Bypass verboten")):
        signal, _ = routine_punkte_setzen(
            aktion=AKTION_HINZUFUEGEN,
            routine_client=rc,
            icon_client=ic,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            label="Zähne", piktogramm="1",
        )
    assert signal == SIGNAL_HINZUGEFUEGT
    assert len(rc.add_calls) == 1


# ============================================================
#  WriteTask-Klassifikation + propose()
# ============================================================

def _make_task(routine_client=None, icon_client=None, is_member_fn=None):
    return RoutinePunkteSetzenTask(
        tg=FakeTelegram(),
        routine_client=routine_client or FakeRoutineClient(),
        icon_client=icon_client or FakeIconClient(),
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=is_member_fn or _immer_mitglied,
    )


def test_RPS7_ist_write_task():
    """RPS-7: RoutinePunkteSetzenTask ist ein WriteTask (EC-10)."""
    assert isinstance(_make_task(), WriteTask)


def test_RPS7_name():
    """RPS-7: Task-Name ist 'routine_punkte_setzen' (Catalog-Schlüssel)."""
    assert _make_task().name == "routine_punkte_setzen"


def test_RPS7_ist_sync():
    """RPS-7: is_async=False — V1 synchron (analog RZS-7), kein Worker."""
    assert _make_task().is_async is False


def test_RPS7_keine_post_execute_hooks():
    """RPS-7: keine Hooks (Routine-Buddy hat Reload-on-Read, ROUTINE-14)."""
    assert _make_task().post_execute_hooks == ()


def test_E_RPS1_propose_liefert_konkreten_vorschlag_mit_label_und_id():
    """E-RPS-1 / RPS-5: propose nennt Label + Piktogramm-ID (Ein-Schritt-
    Vorschlag, RPS-5 Z. 84-86)."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Zähne putzen",
        "piktogramm": "2349",
    }, ctx)
    assert isinstance(proposal, Proposal)
    assert "Zähne putzen" in proposal.summary
    assert "2349" in proposal.summary


def test_E_RPS1_propose_einmalig_nennt_heute():
    """E-RPS-1: propose für einmalig nennt »heute« / »morgen automatisch weg«."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({
        "aktion": AKTION_EINMALIG,
        "label": "Turnbeutel mit",
        "piktogramm": "7777",
    }, ctx)
    assert "heute" in proposal.summary.lower()


def test_E_RPS1_propose_loeschen_nennt_id():
    """E-RPS-1: propose für loeschen nennt die zu löschende ID."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({
        "aktion": AKTION_LOESCHEN,
        "item_id": "zaehne-putzen",
    }, ctx)
    assert "zaehne-putzen" in proposal.summary


# ============================================================
#  execute(): vollständige Kette propose → execute → POST
# ============================================================

def test_VS_propose_then_execute_ruft_post():
    """Vertikale Scheibe: propose() → execute() → POST /api/v1/routine/items
    (RPS-5 propose→confirm-Pfad, CLIENT-1-Transport-Stub).
    """
    rc = FakeRoutineClient(add_response={"id": "zaehne-putzen"})
    task = _make_task(routine_client=rc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    args = {
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Zähne putzen",
        "piktogramm": "2349",
    }

    proposal = task.propose(args, ctx)
    assert isinstance(proposal, Proposal)
    # propose darf NICHT geschrieben haben (E-RPS-1)
    assert rc.add_calls == [], "propose schreibt NICHTS (E-RPS-1)"

    quittung = task.execute(args, ctx)
    assert rc.add_calls == [{
        "quelle": "default",
        "label": "Zähne putzen",
        "piktogramm": "2349",
    }]
    # Quittung nennt die ID (D6-Muster, analog FSE-Undo-Vorlage)
    assert "zaehne-putzen" in quittung


def test_VS_einmalig_propose_then_execute_quelle_einmalig():
    """Vertikale Scheibe (einmalig): execute → POST mit quelle=einmalig."""
    rc = FakeRoutineClient(add_response={"id": "einmalig:turnbeutel-mit"})
    task = _make_task(routine_client=rc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    args = {
        "aktion": AKTION_EINMALIG,
        "label": "Turnbeutel mit",
        "piktogramm": "7777",
    }
    task.execute(args, ctx)
    assert rc.add_calls[0]["quelle"] == "einmalig"


def test_VS_loeschen_execute_ruft_delete():
    """Vertikale Scheibe (löschen): execute → DELETE."""
    rc = FakeRoutineClient(delete_response={"id": "zaehne-putzen"})
    task = _make_task(routine_client=rc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    task.execute({
        "aktion": AKTION_LOESCHEN,
        "item_id": "zaehne-putzen",
    }, ctx)
    assert rc.delete_calls == ["zaehne-putzen"]


def test_VS_neu_ordnen_execute_ruft_put():
    """Vertikale Scheibe (Reihenfolge): execute → PUT mit Liste."""
    rc = FakeRoutineClient(replace_response={"count": 2})
    task = _make_task(routine_client=rc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    items = [
        {"id": "a", "label": "A", "piktogramm": "1"},
        {"id": "b", "label": "B", "piktogramm": "2"},
    ]
    task.execute({"aktion": AKTION_NEU_ORDNEN, "items": items}, ctx)
    assert rc.replace_calls == [items]


def test_VS_icon_suchen_execute_ruft_router_und_nennt_ids():
    """RPS-4: execute(icon_suchen) → ICONS-7-Aufruf; Quittung enthält die
    Vorschlags-IDs (D6 — zweiter tool_use nutzt sie als piktogramm)."""
    ic = FakeIconClient(response=[
        {"id": 2349, "url": "/x"},
        {"id": 8800, "url": "/y"},
    ])
    task = _make_task(icon_client=ic)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    quittung = task.execute({
        "aktion": AKTION_ICON_SUCHEN,
        "icon_stichwort": "Zähne",
    }, ctx)
    assert ic.suche_calls == [{"stichwort": "Zähne", "max_treffer": 3}]
    # IDs müssen in der Quittung stehen (D6)
    assert "2349" in quittung
    assert "8800" in quittung


def test_VS_nicht_mitglied_execute_kein_schreiben():
    """RPS-2: Nicht-Mitglied → execute schreibt NICHT, Quittung nennt die
    fehlende Berechtigung."""
    rc = FakeRoutineClient()
    task = _make_task(routine_client=rc, is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    quittung = task.execute({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "X", "piktogramm": "1",
    }, ctx)
    assert rc.add_calls == []
    assert "Familien-Gruppe" in quittung


# ============================================================
#  Catalog-Registrierung (AND-Guard, RPS-7) — alle DREI Origins
# ============================================================

def _ca_pem():
    """Erzeugt eine temporäre CA-PEM-Datei für build_catalog."""
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_RPS7_guard_alle_drei_origins_gesetzt_registriert():
    """RPS-7 Spec Z. 99-105: Task erscheint im Katalog GENAU DANN, wenn
    routine_origin_url UND icon_origin_url UND family_group_chat_id_getter
    gesetzt sind."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("routine_punkte_setzen")
        assert task is not None
        assert isinstance(task, WriteTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_RPS7_guard_ohne_routine_origin_nicht_registriert():
    """RPS-7 Guard: ohne routine_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("routine_punkte_setzen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_RPS7_guard_ohne_icon_origin_nicht_registriert():
    """RPS-7 Guard: ohne icon_origin_url → keine Registrierung (E-RPS-2 —
    der Skill braucht die zentrale Icon-Suche, kein Fallback)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("routine_punkte_setzen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_RPS7_guard_ohne_fgcid_nicht_registriert():
    """RPS-7 Guard: ohne family_group_chat_id_getter → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
            icon_origin_url="http://127.0.0.1:5000",
        )
        assert catalog.get("routine_punkte_setzen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_RPS7_build_catalog_signatur_bleibt_kompatibel():
    """RPS-7 / additive Erweiterung: build_catalog(tg, ca_pem_path) bleibt
    rückwärtskompatibel — der neue icon_origin_url-Parameter ist optional
    (Default None), keine bestehende Aufrufstelle bricht."""
    ca = _ca_pem()
    try:
        # Minimal-Aufruf (wie in CAV-Tests) — darf nicht crashen.
        catalog = build_catalog(tg=FakeTelegram(), ca_pem_path=ca)
        # RPS ist NICHT registriert (alle drei Origins fehlen).
        assert catalog.get("routine_punkte_setzen") is None
        # Der CA-Task bleibt da (CAV-6, default registriert).
        assert catalog.get("ca_verteilen") is not None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Vertikale Scheibe Ende-zu-Ende: Catalog → Task → Transport-Stub
# ============================================================

def test_VS_entry_path_catalog_to_post_via_transport_stub():
    """Entry-Path-Probe (AC_ENTRY): build_catalog → Task → POST über den
    echten RoutineClient mit Transport-Stub (CLIENT-1) — die Kette aus
    Routing + Skill + Client + Transport ist hookbar (RPS-7)."""
    import json as _json

    from skills.routine_punkte_setzen_task import (
        RoutinePunkteSetzenTask as _RpsTask,
    )

    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(members={7: {"status": "member"}}),
            ca_pem_path=ca,
            routine_origin_url="http://example",
            icon_origin_url="http://example",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("routine_punkte_setzen")
        assert isinstance(task, _RpsTask)

        # Transport-Stub direkt in den Items-Client einsetzen, ohne den
        # Task neu zu bauen — wir greifen auf die Test-Naht des Clients zu.
        put_calls = []
        def transport(method, path, *, body=None, content_type=None):
            put_calls.append({"method": method, "path": path,
                              "body": body})
            return 201, _json.dumps({"id": "zaehne-putzen"}).encode("utf-8")
        task._routine_client._transport = transport

        ctx = TurnContext(chat_id=200, from_user_id=7, private_chat_id=7)
        task.execute({
            "aktion": AKTION_HINZUFUEGEN,
            "label": "Zähne putzen",
            "piktogramm": "2349",
        }, ctx)

        assert len(put_calls) == 1
        assert put_calls[0]["method"] == "POST"
        assert put_calls[0]["path"] == "/api/v1/routine/items"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Catalog-Sanity: Doppel-Registrierung wäre ein Fehler
# ============================================================

def test_RPS7_register_doppelt_ist_fehler():
    """Catalog.register() lehnt einen schon registrierten Task ab —
    Sanity-Check, dass build_catalog RPS nicht doppelt einträgt."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        # Zweite Registrierung wäre ein ValueError (doppelter Name).
        task = catalog.get("routine_punkte_setzen")
        with pytest.raises(ValueError, match="bereits registriert"):
            catalog.register(task)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Entry-Path-Test: Config-Naht (AC3 / EC-15 / #443)
# ============================================================

def test_RPS7_entry_path_via_config_naht():
    """AC3 / EC-15 / #443: routine_punkte_setzen erscheint im Katalog, wenn
    icon_origin_url über die Config-Naht kommt (cfg.icon_origin_url) statt
    explizit hardcodiert — prüft das Live-Wiring aus main.py:build_catalog.

    DEFAULTS['icon_origin_url'] = 'http://127.0.0.1:5000' (EC-15 Tabelle Z.
    465). Der Test simuliert, was main.py tut: er liest icon_origin_url aus
    einem Config-Objekt, das mit dem Default-Wert gebaut wurde, und reicht
    es an build_catalog durch — analog zum FSE-Pattern (photo_origin_url).
    """
    import config as config_mod

    # Config-Objekt mit Default-Wert für icon_origin_url — analog
    # cfg.icon_origin_url im echten main.py-Setup.
    icon_origin = config_mod.DEFAULTS["icon_origin_url"]
    routine_origin = config_mod.DEFAULTS["routine_origin_url"]

    ca = _ca_pem()
    try:
        # Kein hardcodiertes icon_origin_url="..." — der Wert kommt aus
        # config.DEFAULTS, wie er im Betrieb über cfg.icon_origin_url fließt.
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url=routine_origin,
            icon_origin_url=icon_origin,
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("routine_punkte_setzen")
        assert task is not None, (
            "routine_punkte_setzen sollte im Katalog sein, wenn "
            "icon_origin_url aus Config-DEFAULTS kommt (Live-Wiring EC-15)")
        assert isinstance(task, RoutinePunkteSetzenTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Spec-Drift-Probe (Watchdog-Linse 1): KEIN Umbenennen
# ============================================================

def test_SPEC_kein_umbenennen_in_v11():
    """Spec RPS Z. 31-32 / Z. 62: Umbenennen ist V1.1 explizit out-of-scope.

    Die Aktions-Konstanten dürfen kein 'umbenennen' enthalten (E-RPS-1 — die
    Spec ist die Wahrheit; Contract-Drift wurde bei Implementation
    ausgeräumt).
    """
    from skills import routine_punkte_setzen as rps
    aktionen = {
        rps.AKTION_HINZUFUEGEN, rps.AKTION_EINMALIG,
        rps.AKTION_LOESCHEN, rps.AKTION_NEU_ORDNEN, rps.AKTION_ICON_SUCHEN,
    }
    assert "umbenennen" not in aktionen
    assert "rename" not in aktionen
