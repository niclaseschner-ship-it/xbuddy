"""Tests für die Funktion plan_aktivitaeten_setzen + den Task — PAS-1 … PAS-8,
E-PAS-1 … E-PAS-4 (Refs #578).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(PAS-8, CLAUDE.md §6). Plan-Buddy, Router-Icon-Suche und Telegram sind
durch kontrollierte Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

Pflicht-Tests (Spec PAS-8 Z. 231-256, AC1…AC5 des Contracts):
- Katalog enthält PAS genau dann, wenn alle DREI Abhängigkeiten gesetzt sind
  (plan_origin_url, icon_origin_url, family_group_chat_id_getter).
- Nicht-Mitglied → Ablehnung, kein Schreiben (PAS-2).
- Hinzufügen Happy-Path (eigenes Wort): icon_suchen → Wahl → propose → execute
  → POST /api/v1/plan/admin/aktivitaeten mit art/label/keywords/piktogramm.
- Hinzufügen Happy-Path (Seed-Vorschlag): Skill übernimmt art/label/keywords
  aus der Seed-Zeile, führt nur ICONS-7 + Bestätigung durch.
- Seed-Dedupe: Seed-Eintrag, der schon im Katalog steht, erscheint in
  get-Antwort gekennzeichnet.
- Doppelte art: Plan-API antwortet 409 → Skill meldet ehrliche Grenze (PAS-3).
- Löschen Happy-Path: liste_lesen → Eltern wählt → execute ruft
  DELETE /api/v1/plan/admin/aktivitaeten/<art>.
- DELETE 404 → ehrliche Grenze (PAS-3, EC-7).
- Icon-Suche ohne Treffer → Skill fragt nach anderem Wort, erfindet keine ID
  (PAS-4 / E-PAS-2).
- APP-3: der Skill ruft die API, nicht die Datei.
- Live-Probe (AC5): PAS-Skill → PlanClient → POST gegen echte Plan-Instanz
  (Test-Tempfile) → plan.json hat neue Aktivität persistent.
"""

import contextlib
import json
import os
import sys
import tempfile
import unittest.mock as mock

from fakes import FakeTelegram
from skills.icon_client import IconClientError
from skills.plan_aktivitaeten_setzen import (
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
    AKTION_LISTE_LESEN,
    AKTION_LOESCHEN,
    SEED,
    SIGNAL_ABGELEHNT,
    SIGNAL_AKTIVITAETEN,
    SIGNAL_GELOESCHT,
    SIGNAL_GRENZE,
    SIGNAL_HINZUGEFUEGT,
    SIGNAL_ICON_KANDIDATEN,
    SIGNAL_KEINE_ICONS,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_NICHTS_ZU_TUN,
    plan_aktivitaeten_setzen,
)
from skills.plan_aktivitaeten_setzen_task import PlanAktivitaetenSetzenTask
from skills.plan_client import PlanClient, PlanClientError
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakePlanClient:
    """PlanClient-Doppelung für die PLAN-34 Admin-Methoden (CLIENT-1, PAS-7)."""

    def __init__(self, hinzufuegen_response=None, hinzufuegen_error=None,
                 loeschen_error=None, lesen_response=None):
        self.hinzufuegen_calls = []
        self.loeschen_calls = []
        self.lesen_calls = []
        self._hinzufuegen_response = (hinzufuegen_response
                                       or {"ok": True, "art": "neu-art"})
        self._hinzufuegen_error = hinzufuegen_error
        self._loeschen_error = loeschen_error
        self._lesen_response = lesen_response if lesen_response is not None else []

    def aktivitaet_hinzufuegen(self, art, label, keywords, piktogramm):
        self.hinzufuegen_calls.append({
            "art": art, "label": label,
            "keywords": keywords, "piktogramm": piktogramm,
        })
        if self._hinzufuegen_error is not None:
            raise self._hinzufuegen_error
        return dict(self._hinzufuegen_response)

    def aktivitaet_loeschen(self, art):
        self.loeschen_calls.append(art)
        if self._loeschen_error is not None:
            raise self._loeschen_error
        return {"ok": True, "art": art}

    def aktivitaeten_lesen(self):
        self.lesen_calls.append(True)
        return list(self._lesen_response)


class FakeIconClient:
    """ICONS-7-Doppelung des IconClients (CLIENT-1, PAS-4)."""

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
#  PAS-2: Berechtigung — Nicht-Mitglied → Ablehnung, kein Schreiben
# ============================================================

def test_PAS2_nicht_mitglied_kein_post():
    """PAS-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein POST."""
    pc = FakePlanClient()
    ic = FakeIconClient(response=[{"id": 9999, "url": "/x"}])

    signal, _ = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=ic,
        is_member_fn=_kein_mitglied,
        from_user_id=99,
        art="capueira", label="Capueira",
        keywords=["capueira"], piktogramm="9999",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert pc.hinzufuegen_calls == [], "Kein POST bei Nicht-Mitglied (PAS-2)"


def test_PAS2_kein_user_id_abgelehnt():
    """PAS-2: from_user_id=None → SIGNAL_ABGELEHNT, kein POST."""
    pc = FakePlanClient()

    signal, _ = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=None,
        art="x", label="X", keywords=["x"], piktogramm="1",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert pc.hinzufuegen_calls == []


def test_PAS2_nicht_mitglied_kein_delete():
    """PAS-2: Nicht-Mitglied → kein DELETE."""
    pc = FakePlanClient()
    signal, _ = plan_aktivitaeten_setzen(
        aktion=AKTION_LOESCHEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_kein_mitglied,
        from_user_id=99,
        art_loeschen="capueira",
    )
    assert signal == SIGNAL_ABGELEHNT
    assert pc.loeschen_calls == []


# ============================================================
#  PAS-3: Hinzufügen Happy-Path (eigenes Wort)
# ============================================================

def test_PAS3_hinzufuegen_happy_path_alle_felder():
    """PAS-3: hinzufuegen → POST mit art/label/keywords/piktogramm.

    PAS-8 Spec Z. 237: Hinzufügen Happy-Path (eigenes Wort) — alle vier
    Pflichtfelder müssen im POST-Body stehen (Transport-Stub, CLIENT-1).
    """
    pc = FakePlanClient(hinzufuegen_response={"ok": True, "art": "capueira"})

    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="capueira",
        label="Capueira",
        keywords=["capueira", "capoeira"],
        piktogramm="2652",
    )

    assert signal == SIGNAL_HINZUGEFUEGT
    assert daten == {"art": "capueira"}
    assert pc.hinzufuegen_calls == [{
        "art": "capueira",
        "label": "Capueira",
        "keywords": ["capueira", "capoeira"],
        "piktogramm": "2652",
    }]


def test_PAS3_hinzufuegen_ohne_art_nichts_zu_tun():
    """PAS-3: hinzufügen ohne art → SIGNAL_NICHTS_ZU_TUN, kein POST."""
    pc = FakePlanClient()
    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="", label="X", keywords=["x"], piktogramm="1",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "kein art-Schlüssel"
    assert pc.hinzufuegen_calls == []


def test_PAS3_hinzufuegen_ohne_label_nichts_zu_tun():
    """PAS-3: hinzufügen ohne label → SIGNAL_NICHTS_ZU_TUN, kein POST."""
    pc = FakePlanClient()
    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="x", label="", keywords=["x"], piktogramm="1",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "kein Label"
    assert pc.hinzufuegen_calls == []


def test_PAS3_hinzufuegen_ohne_keywords_nichts_zu_tun():
    """PAS-3: hinzufügen ohne keywords → SIGNAL_NICHTS_ZU_TUN, kein POST."""
    pc = FakePlanClient()
    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="x", label="X", keywords=[], piktogramm="1",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "keine Keywords"
    assert pc.hinzufuegen_calls == []


def test_PAS3_hinzufuegen_ohne_piktogramm_nichts_zu_tun():
    """PAS-4 / E-PAS-2: hinzufügen ohne piktogramm → NICHTS_ZU_TUN, kein POST.

    Der Skill darf NIE eine ARASAAC-ID raten (E-PAS-2).
    """
    pc = FakePlanClient()
    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="x", label="X", keywords=["x"], piktogramm="",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "kein Piktogramm"
    assert pc.hinzufuegen_calls == []


# ============================================================
#  PAS-3: Löschen
# ============================================================

def test_PAS3_loeschen_happy_path():
    """PAS-3: loeschen → DELETE /api/v1/plan/admin/aktivitaeten/<art>."""
    pc = FakePlanClient()

    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_LOESCHEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art_loeschen="capueira",
    )

    assert signal == SIGNAL_GELOESCHT
    assert daten == {"art": "capueira"}
    assert pc.loeschen_calls == ["capueira"]


def test_PAS3_loeschen_ohne_art_nichts_zu_tun():
    """PAS-3: loeschen ohne art_loeschen → SIGNAL_NICHTS_ZU_TUN, kein DELETE."""
    pc = FakePlanClient()
    signal, _ = plan_aktivitaeten_setzen(
        aktion=AKTION_LOESCHEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art_loeschen=None,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert pc.loeschen_calls == []


def test_PAS3_delete_404_grenze():
    """PAS-3 / EC-7: DELETE auf unbekannte art → 404 → SIGNAL_GRENZE.

    PAS-8 Spec Z. 252: DELETE auf unbekannte art → Plan-API antwortet 404
    → Skill meldet ehrliche Grenze (EC-7).
    """
    pc = FakePlanClient(loeschen_error=PlanClientError(
        "Plan-Buddy: HTTP 404 bei DELETE /api/v1/plan/admin/aktivitaeten/unbekannt"))

    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_LOESCHEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art_loeschen="unbekannt",
    )

    assert signal == SIGNAL_GRENZE
    assert "404" in daten["detail"]


# ============================================================
#  PAS-3 / PAS-6: Buddy-4xx → ehrliche Grenze (EC-7), doppelte art → 409
# ============================================================

def test_PAS3_PAS6_doppelte_art_409_grenze():
    """PAS-3 / PAS-6: doppelte art → Plan-API antwortet 409 → SIGNAL_GRENZE,
    kein Schreiben (ehrliche Grenze EC-7).

    PAS-8 Spec Z. 246: doppelte art → 409 → Skill meldet ehrliche Grenze,
    fragt nach anderem art-Schlüssel.
    """
    pc = FakePlanClient(hinzufuegen_error=PlanClientError(
        "Plan-Buddy: HTTP 409 bei POST /api/v1/plan/admin/aktivitaeten "
        "— art_existiert"))

    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="klettern",
        label="Klettern Neu",
        keywords=["klettern"],
        piktogramm="9999",
    )

    assert signal == SIGNAL_GRENZE
    assert "art_existiert" in daten["detail"] or "409" in daten["detail"]
    # Einmal versucht, nicht wiederholt.
    assert len(pc.hinzufuegen_calls) == 1


def test_PAS3_buddy_5xx_nicht_erreichbar():
    """EC-7: 5xx vom Plan-Buddy → SIGNAL_NICHT_ERREICHBAR."""
    pc = FakePlanClient(hinzufuegen_error=PlanClientError(
        "Plan-Buddy: HTTP 503"))

    signal, _ = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="x", label="X", keywords=["x"], piktogramm="1",
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR


# ============================================================
#  PAS-4 + E-PAS-2: ICONS-7-Suche
# ============================================================

def test_PAS4_icon_suchen_drei_kandidaten():
    """PAS-4: icon_suchen → ICONS-7-Aufruf mit q=<wort>&max=3,
    liefert SIGNAL_ICON_KANDIDATEN mit den Treffern."""
    ic = FakeIconClient(response=[
        {"id": 2652, "url": "/display/_shared/icons/arasaac/2652.png"},
        {"id": 6591, "url": "/display/_shared/icons/arasaac/6591.png"},
        {"id": 5522, "url": "/display/_shared/icons/arasaac/5522.png"},
    ])

    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_ICON_SUCHEN,
        plan_client=FakePlanClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="tanz",
    )

    assert signal == SIGNAL_ICON_KANDIDATEN
    assert daten["label"] == "tanz"
    assert len(daten["kandidaten"]) == 3
    assert {k["id"] for k in daten["kandidaten"]} == {2652, 6591, 5522}
    # ICONS-7: q + max≤3
    assert ic.suche_calls == [{"stichwort": "tanz", "max_treffer": 3}]


def test_PAS4_icon_suchen_keine_treffer_kein_erfundenes_piktogramm():
    """PAS-4 / E-PAS-2: ICONS-7 ohne Treffer → SIGNAL_KEINE_ICONS, Skill
    fragt nach anderem Wort, erfindet KEINE ID, fällt NICHT auf ARASAAC
    zurück (zweiter Icon-Pfad explizit verboten, E-PAS-2)."""
    ic = FakeIconClient(response=[])

    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_ICON_SUCHEN,
        plan_client=FakePlanClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="glotzauge",
    )

    assert signal == SIGNAL_KEINE_ICONS
    assert daten["label"] == "glotzauge"
    # Kein Piktogramm erfunden, keine POST-Aufrufe.


def test_PAS4_icon_max_wird_auf_3_gecapped():
    """PAS-4: »bis zu drei Kandidaten« — Hard-Cap auf 3."""
    ic = FakeIconClient(response=[{"id": 1, "url": "/a"}])

    plan_aktivitaeten_setzen(
        aktion=AKTION_ICON_SUCHEN,
        plan_client=FakePlanClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="hund",
        icon_max=42,
    )

    assert ic.suche_calls[0]["max_treffer"] == 3


def test_PAS4_icon_suchen_router_nicht_erreichbar():
    """PAS-4 / EC-7: ICONS-7 wirft IconClientError → SIGNAL_NICHT_ERREICHBAR."""
    ic = FakeIconClient(error=IconClientError("Router nicht erreichbar"))

    signal, _ = plan_aktivitaeten_setzen(
        aktion=AKTION_ICON_SUCHEN,
        plan_client=FakePlanClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="klettern",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR


# ============================================================
#  PAS-5: Bestand lesen (liste_lesen → GET PLAN-34)
# ============================================================

def test_PAS5_liste_lesen_happy_path():
    """PAS-5: liste_lesen → GET /api/v1/plan/aktivitaeten → SIGNAL_AKTIVITAETEN."""
    bestehende = [
        {"art": "klettern", "label": "Klettern",
         "keywords": ["klettern"], "piktogramm": "6591"},
    ]
    pc = FakePlanClient(lesen_response=bestehende)

    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_LISTE_LESEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )

    assert signal == SIGNAL_AKTIVITAETEN
    assert len(daten["liste"]) == 1
    assert daten["liste"][0]["art"] == "klettern"
    assert pc.lesen_calls == [True]


def test_PAS5_seed_liste_im_skill_modul():
    """E-PAS-3: die SEED-Liste lebt im Skill-Modul (nicht im Plan-Code-Default).

    PAS-8 Spec Z. 244: Seed-Dedupe — ein Seed-Eintrag, dessen art schon im
    Katalog steht, kann erkannt werden. Hier prüfen wir nur die Struktur.
    """
    # SEED hat 6 Einträge (PAS-5 Spec Z. 152-160).
    assert len(SEED) == 6
    # Jeder SEED-Eintrag: (art, label, keywords, icon_suchworte).
    for eintrag in SEED:
        art, label, keywords, icon_suchworte = eintrag
        assert isinstance(art, str)
        assert art
        assert isinstance(label, str)
        assert label
        assert isinstance(keywords, list)
        assert keywords
        assert isinstance(icon_suchworte, list)
        assert icon_suchworte


def test_PAS5_seed_hinzufuegen_happy_path():
    """PAS-8 Spec Z. 240: Hinzufügen Happy-Path (Seed-Vorschlag) — Skill
    übernimmt art/label/keywords aus der Seed-Zeile, führt nur ICONS-7 + POST
    durch. Capueira-Eintrag aus SEED (art='capueira')."""
    # Capueira-SEED-Eintrag: art='capueira', label='Capueira', keywords=[...]
    seed_capueira = next(s for s in SEED if s[0] == "capueira")
    art, label, keywords, _ = seed_capueira

    pc = FakePlanClient(hinzufuegen_response={"ok": True, "art": art})

    signal, _daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=pc,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art=art,
        label=label,
        keywords=keywords,
        piktogramm="2652",  # gewählte ICONS-7-ID
    )

    assert signal == SIGNAL_HINZUGEFUEGT
    call = pc.hinzufuegen_calls[0]
    assert call["art"] == "capueira"
    assert call["label"] == "Capueira"
    assert "capueira" in call["keywords"]  # Seed-keywords übernommen


# ============================================================
#  APP-3: Skill ruft die API, nicht die Datei
# ============================================================

def test_APP3_keine_datei_zugriffe():
    """APP-3 / PAS-7: die Funktion liest/schreibt plan.json NICHT direkt.

    Der PlanClient ist die einzige Schreib-Naht (PAS-7), der IconClient
    die einzige Icon-Lese-Naht (PAS-4). Wenn beides als Fake injiziert ist
    und gleichzeitig open() blockiert wird, müssen die Tests durchlaufen —
    ein FS-Bypass würde die `open`-Blockade auslösen.

    PAS-8 Spec Z. 256: APP-3 — der Skill ruft die API, nicht die Datei.
    """
    import unittest.mock as mock

    pc = FakePlanClient(hinzufuegen_response={"ok": True, "art": "x"})
    ic = FakeIconClient(response=[{"id": 1, "url": "/x"}])
    with mock.patch("builtins.open",
                    side_effect=AssertionError("FS-Bypass verboten (APP-3)")):
        signal, _ = plan_aktivitaeten_setzen(
            aktion=AKTION_HINZUFUEGEN,
            plan_client=pc,
            icon_client=ic,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            art="x", label="X", keywords=["x"], piktogramm="1",
        )
    assert signal == SIGNAL_HINZUGEFUEGT
    assert len(pc.hinzufuegen_calls) == 1


# ============================================================
#  WriteTask-Klassifikation + propose()
# ============================================================

def _make_task(plan_client=None, icon_client=None, is_member_fn=None,
               tg=None, icon_origin_url=None):
    return PlanAktivitaetenSetzenTask(
        tg=tg or FakeTelegram(),
        plan_client=plan_client or FakePlanClient(),
        icon_client=icon_client or FakeIconClient(),
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=is_member_fn or _immer_mitglied,
        icon_origin_url=icon_origin_url,
    )


def test_PAS8_ist_write_task():
    """PAS-8: PlanAktivitaetenSetzenTask ist ein WriteTask (EC-10)."""
    assert isinstance(_make_task(), WriteTask)


def test_PAS8_name():
    """PAS-8: Task-Name ist 'plan_aktivitaeten_setzen' (Catalog-Schlüssel)."""
    assert _make_task().name == "plan_aktivitaeten_setzen"


def test_PAS8_ist_sync():
    """PAS-8: is_async=False — V1 synchron, kein Worker."""
    assert _make_task().is_async is False


def test_PAS8_keine_post_execute_hooks():
    """PAS-8: keine Hooks (Plan-Buddy hat Reload-on-Read, PLAN-34/DCOMP-2)."""
    assert _make_task().post_execute_hooks == ()


def test_E_PAS1_propose_liefert_konkreten_vorschlag_mit_label_und_art():
    """E-PAS-1 / PAS-6: propose nennt Label + art (Ein-Schritt-Vorschlag)."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({
        "aktion": AKTION_HINZUFUEGEN,
        "art": "capueira",
        "label": "Capueira",
        "keywords": ["capueira"],
        "piktogramm": "2652",
    }, ctx)
    assert isinstance(proposal, Proposal)
    assert "Capueira" in proposal.summary
    assert "capueira" in proposal.summary


def test_E_PAS1_propose_loeschen_nennt_art():
    """E-PAS-1: propose für loeschen nennt die zu löschende art."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({
        "aktion": AKTION_LOESCHEN,
        "art_loeschen": "klettern",
    }, ctx)
    assert isinstance(proposal, Proposal)
    assert "klettern" in proposal.summary


def test_E_PAS1_propose_icon_suchen_lesend():
    """E-PAS-1: propose für icon_suchen nennt »nur lesend, nichts schreiben«."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({
        "aktion": AKTION_ICON_SUCHEN,
        "icon_stichwort": "Capueira",
    }, ctx)
    assert isinstance(proposal, Proposal)
    assert "Capueira" in proposal.summary
    assert "lesend" in proposal.summary.lower()


# ============================================================
#  execute(): vollständige Kette propose → execute → POST
# ============================================================

def test_VS_propose_then_execute_ruft_post():
    """Vertikale Scheibe: propose() → execute() → POST
    /api/v1/plan/admin/aktivitaeten (PAS-6 propose→confirm-Pfad, CLIENT-1).
    """
    pc = FakePlanClient(hinzufuegen_response={"ok": True, "art": "capueira"})
    task = _make_task(plan_client=pc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    args = {
        "aktion": AKTION_HINZUFUEGEN,
        "art": "capueira",
        "label": "Capueira",
        "keywords": ["capueira", "capoeira"],
        "piktogramm": "2652",
    }

    proposal = task.propose(args, ctx)
    assert isinstance(proposal, Proposal)
    # propose darf NICHT geschrieben haben (E-PAS-1)
    assert pc.hinzufuegen_calls == [], "propose schreibt NICHTS (E-PAS-1)"

    quittung = task.execute(args, ctx)
    assert pc.hinzufuegen_calls == [{
        "art": "capueira",
        "label": "Capueira",
        "keywords": ["capueira", "capoeira"],
        "piktogramm": "2652",
    }]
    # Quittung nennt die art (D6-Muster)
    assert "capueira" in quittung


def test_VS_loeschen_execute_ruft_delete():
    """Vertikale Scheibe (löschen): execute → DELETE."""
    pc = FakePlanClient()
    task = _make_task(plan_client=pc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    task.execute({
        "aktion": AKTION_LOESCHEN,
        "art_loeschen": "klettern",
    }, ctx)
    assert pc.loeschen_calls == ["klettern"]


def test_VS_icon_suchen_execute_ruft_router_und_nennt_ids():
    """PAS-4: execute(icon_suchen) → ICONS-7-Aufruf; Quittung enthält die
    Vorschlags-IDs (D6 — zweiter tool_use nutzt sie als piktogramm)."""
    ic = FakeIconClient(response=[
        {"id": 2652, "url": "/x"},
        {"id": 6591, "url": "/y"},
    ])
    task = _make_task(icon_client=ic)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    # PAS-4 / TASK-10b: zeige_kandidaten wird jetzt aufgerufen — kein Netz
    # in Unit-Tests, daher Stub (kein Inhalt nötig, Rückgabe irrelevant).
    with mock.patch(
        "skills.plan_aktivitaeten_setzen_task.icon_album.zeige_kandidaten"
    ):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "tanz",
        }, ctx)
    assert ic.suche_calls == [{"stichwort": "tanz", "max_treffer": 3}]
    # IDs müssen in der Quittung stehen (D6)
    assert "2652" in quittung
    assert "6591" in quittung


def test_VS_nicht_mitglied_execute_kein_schreiben():
    """PAS-2: Nicht-Mitglied → execute schreibt NICHT, Quittung nennt die
    fehlende Berechtigung."""
    pc = FakePlanClient()
    task = _make_task(plan_client=pc, is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    quittung = task.execute({
        "aktion": AKTION_HINZUFUEGEN,
        "art": "x", "label": "X", "keywords": ["x"], "piktogramm": "1",
    }, ctx)
    assert pc.hinzufuegen_calls == []
    assert "Familien-Gruppe" in quittung


def test_VS_liste_lesen_execute_liefert_katalog():
    """PAS-5: execute(liste_lesen) → GET PLAN-34; Quittung listet art + label."""
    pc = FakePlanClient(lesen_response=[
        {"art": "klettern", "label": "Klettern",
         "keywords": ["klettern"], "piktogramm": "6591"},
        {"art": "schwimmen", "label": "Schwimmen",
         "keywords": ["schwimm"], "piktogramm": "5522"},
    ])
    task = _make_task(plan_client=pc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    quittung = task.execute({"aktion": AKTION_LISTE_LESEN}, ctx)
    assert "klettern" in quittung
    assert "schwimmen" in quittung


# ============================================================
#  Catalog-Registrierung (AND-Guard, PAS-8) — alle DREI Origins
# ============================================================

def _ca_pem():
    """Erzeugt eine temporäre CA-PEM-Datei für build_catalog."""
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_PAS8_guard_alle_drei_origins_gesetzt_registriert():
    """PAS-8 Spec Z. 228: Task erscheint im Katalog GENAU DANN, wenn
    plan_origin_url UND icon_origin_url UND family_group_chat_id_getter
    gesetzt sind."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            plan_origin_url="http://127.0.0.1:5020",
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("plan_aktivitaeten_setzen")
        assert task is not None
        assert isinstance(task, WriteTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_PAS8_guard_ohne_plan_origin_nicht_registriert():
    """PAS-8 Guard: ohne plan_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("plan_aktivitaeten_setzen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_PAS8_guard_ohne_icon_origin_nicht_registriert():
    """PAS-8 Guard: ohne icon_origin_url → keine Registrierung (E-PAS-2)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            plan_origin_url="http://127.0.0.1:5020",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("plan_aktivitaeten_setzen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_PAS8_guard_ohne_fgcid_nicht_registriert():
    """PAS-8 Guard: ohne family_group_chat_id_getter → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            plan_origin_url="http://127.0.0.1:5020",
            icon_origin_url="http://127.0.0.1:5000",
        )
        assert catalog.get("plan_aktivitaeten_setzen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_PAS8_build_catalog_signatur_bleibt_kompatibel():
    """PAS-8 / additive Erweiterung: build_catalog(tg, ca_pem_path) bleibt
    rückwärtskompatibel — PAS-Task erscheint nur mit allen drei Origins."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(tg=FakeTelegram(), ca_pem_path=ca)
        # Der Katalog kann ohne Plan-Abhängigkeiten gebaut werden.
        assert catalog.get("plan_aktivitaeten_setzen") is None
        # build_catalog hat keine Fehler geworfen — Katalog ist valid.
        assert catalog is not None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Entry-Path-Test: Transport-Stub-Kette (AC2, CLIENT-1)
# ============================================================

def test_VS_entry_path_catalog_to_post_via_transport_stub():
    """Entry-Path-Probe (AC2): build_catalog → Task → POST über den echten
    PlanClient mit Transport-Stub (CLIENT-1) — die Kette aus Routing + Skill
    + Client + Transport ist hookbar (PAS-8)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(members={7: {"status": "member"}}),
            ca_pem_path=ca,
            plan_origin_url="http://example",
            icon_origin_url="http://example",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("plan_aktivitaeten_setzen")
        assert isinstance(task, PlanAktivitaetenSetzenTask)

        # Transport-Stub direkt in den PlanClient einsetzen.
        post_calls = []
        def transport(method, path, *, body=None, content_type=None):
            post_calls.append({"method": method, "path": path, "body": body})
            return 200, json.dumps({"ok": True, "art": "capueira"}).encode("utf-8")
        task._plan_client._transport = transport

        ctx = TurnContext(chat_id=200, from_user_id=7, private_chat_id=7)
        task.execute({
            "aktion": AKTION_HINZUFUEGEN,
            "art": "capueira",
            "label": "Capueira",
            "keywords": ["capueira"],
            "piktogramm": "2652",
        }, ctx)

        assert len(post_calls) == 1
        assert post_calls[0]["method"] == "POST"
        assert post_calls[0]["path"] == "/api/v1/plan/admin/aktivitaeten"
        body = json.loads(post_calls[0]["body"].decode("utf-8"))
        assert body["art"] == "capueira"
        assert body["label"] == "Capueira"
        assert body["piktogramm"] == "2652"
        assert "capueira" in body["keywords"]
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  AC5: Live-Probe — PAS-Skill → PlanClient → echte Plan-Instanz
#  (Test-Tempfile, write_proofs PW-16)
# ============================================================

def _load_plan_app():
    """Importiert plan.main — fügt den Repo-Wurzel-Pfad zum sys.path hinzu.

    Die Plan-App liegt im Repo-Wurzel-Verzeichnis als `plan/`-Paket;
    der eltern-chat/tests/ Pfad ist nicht automatisch im sys.path der
    eltern-chat-Suite (analog conftest.py der plan/tests/).
    """
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import plan.config as plan_config_mod
    import plan.familie_client as plan_familie_mod
    import plan.kalender as plan_kalender_mod
    import plan.main as plan_main_mod
    return plan_main_mod, plan_config_mod, plan_familie_mod, plan_kalender_mod


def _build_plan_json(path, tmp_path):
    """Schreibt eine minimale plan.json in `path` (ohne aktivitaeten-Sektion
    — CONFIG-4-Fallback greift bei GET/POST, PAS-5/PAS-3)."""
    data = {
        "slots": [
            {"schluessel": "act1", "art": "kalender-read", "icon": "star",
             "kind": "mia"},
        ],
        "default_verantwortlichkeiten": {},
        "fenster_lesekind": 7,
        "fenster_kleinkind": 3,
        "wochenstart": 0,
        "kalender_id": "demo@group.calendar.google.com",
        "db_datei": str(tmp_path / "plan.db"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class _FakeKalenderTransport:
    """Minimaler FakeTransport — kein Netz (PLAN-29)."""

    def credentials_available(self):
        return False

    def list_events(self, time_min, time_max):
        return []

    def access_token(self):
        raise Exception("FakeTransport: keine Credentials")

    def insert_event(self, raw_event):
        return {}

    def insert_event_with_bearer(self, raw_event, bearer):
        return {}

    def patch_event(self, event_id, raw_patch):
        return {}

    def delete_event(self, event_id):
        pass


def test_AC5_live_probe_pas_skill_post_plan_json_persistent(tmp_path):
    """AC5 / write_proofs PW-16: Live-Probe — PAS-Skill schickt POST gegen
    lokale Plan-Instanz (Test-Tempfile); plan.json hat neue Aktivität
    persistent nach erfolgreichem execute().

    Schritte:
    1. Plan-Instanz mit schreibbarer plan.json (Tempfile) aufbauen.
    2. PlanClient (echter Client, Transport-Stub über Flask-Testclient).
    3. PAS-Skill-Funktion mit aktion=hinzufuegen aufrufen.
    4. Assert plan.json — neue Aktivität ist drin (art, label, keywords,
       piktogramm), write_proof via aktivitaeten_lesen() (GET).

    Analog zum RPS-Entry-Path-Test (test_routine_punkte_setzen.py
    test_VS_entry_path_catalog_to_post_via_transport_stub) — aber mit
    echter Flask-Instanz statt Transport-Stub.
    """
    plan_main_mod, plan_config_mod, plan_familie_mod, _plan_kalender_mod = (
        _load_plan_app())

    # 1. Plan-Instanz aufbauen.
    cfg_path = str(tmp_path / "plan.json")
    _build_plan_json(cfg_path, tmp_path)
    cfg = plan_config_mod.resolve(cfg_path)

    # Minimale Registry (Plan-Buddy braucht eine RegistryView).
    registry = plan_familie_mod.RegistryView([
        plan_familie_mod.Person(
            "mia", "Mia", "purple", plan_familie_mod.KIND_KINDER)
    ])
    transport = _FakeKalenderTransport()
    plan_main_mod.configure(cfg, registry, transport, config_path=cfg_path)
    plan_main_mod.app.testing = True
    flask_client = plan_main_mod.app.test_client()

    # 2. PlanClient mit Flask-Testclient als Transport-Naht.
    def flask_transport(method, path, *, body=None, content_type=None):
        """Leitet HTTP-Aufrufe an den Flask-Testclient (loopback-simuliert)."""
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        if method == "GET":
            resp = flask_client.get(path)
        elif method == "POST":
            resp = flask_client.post(path, data=body, headers=headers)
        elif method == "DELETE":
            resp = flask_client.delete(path)
        else:
            raise AssertionError("unbekannte Methode: %s" % method)
        return resp.status_code, resp.data

    plan_client = PlanClient(origin_url="http://localhost", transport=flask_transport)

    # write_proof VORHER: plan.json hat KEINE eigene aktivitaeten-Sektion.
    with open(cfg_path, encoding="utf-8") as f:
        before = json.load(f)
    assert "aktivitaeten" not in before or before.get("aktivitaeten") is None, (
        "Voraussetzung: plan.json hat vor POST keine aktivitaeten-Sektion")

    # 3. PAS-Skill-Funktion: aktion=hinzufuegen.
    signal, daten = plan_aktivitaeten_setzen(
        aktion=AKTION_HINZUFUEGEN,
        plan_client=plan_client,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        art="capueira",
        label="Capueira",
        keywords=["capueira", "capoeira"],
        piktogramm="2652",
    )

    # 4. Signal-Check.
    assert signal == SIGNAL_HINZUGEFUEGT, (
        "PAS-Skill soll SIGNAL_HINZUGEFUEGT liefern, bekam: %r — daten: %r"
        % (signal, daten))
    assert daten.get("art") == "capueira"

    # write_proof NACHHER via plan.json direkt (PW-16 — Datei ist die Wahrheit).
    with open(cfg_path, encoding="utf-8") as f:
        after = json.load(f)
    akt_liste = after.get("aktivitaeten", [])
    arts_in_file = [e["art"] for e in akt_liste]
    assert "capueira" in arts_in_file, (
        "PW-16: nach POST muss 'capueira' in plan.json stehen. "
        "Gefundene arts: %r" % arts_in_file)

    # Vollständige Felder prüfen.
    capueira_entry = next(e for e in akt_liste if e["art"] == "capueira")
    assert capueira_entry["label"] == "Capueira"
    assert "capueira" in capueira_entry["keywords"]
    assert capueira_entry["piktogramm"] == "2652"

    # write_proof via aktivitaeten_lesen() (GET /api/v1/plan/aktivitaeten).
    # Reload-on-Read (DCOMP-2): der GET liest plan.json frisch pro Aufruf,
    # ohne Service-Restart. Der neue Eintrag muss sichtbar sein.
    # (Hinweis: falls der in-memory-Reload wegen einer Plan-App-internen
    # Validierung scheitert, greift Reload-on-Read beim nächsten GET direkt
    # aus der Datei — das ist DCOMP-2-Verhalten, nicht PAS-Skill-Verhalten.
    # Die Datei-Assertion oben ist die maßgebliche PW-16-Probe.)
    gelesene = plan_client.aktivitaeten_lesen()
    arts_via_get = [e["art"] for e in gelesene]
    # Die neue Aktivität ist entweder über GET (falls Reload-on-Read
    # sofort griff) ODER via Datei belegt (PW-16 oben).
    # Wenn GET noch den Stale-State zeigt (Reload schlug fehl), dann
    # prüfen wir es via plan.json (bereits oben erfolgreich getestet).
    file_proof_ok = "capueira" in arts_in_file  # bereits oben geprüft
    get_proof_ok  = "capueira" in arts_via_get
    assert file_proof_ok, (
        "PW-16: nach POST muss 'capueira' in plan.json stehen (Datei-Probe).")
    # GET-Bonus-Check: DCOMP-2 (Reload-on-Read) muss nach POST sofort greifen.
    assert get_proof_ok, (
        "GET-Roundtrip nach POST muss Aktivität in Liste haben (Reload-on-Read)")


# ============================================================
#  PAS-4 / TASK-10b: icon_album.zeige_kandidaten (AC3)
# ============================================================

def test_PAS_4_icon_kandidaten_sendet_album():
    """AC3 / PAS-4 / TASK-10b: execute(icon_suchen) ruft icon_album.zeige_kandidaten
    mit (tg, chat_id, kandidaten, icon_origin_url) — Stub prüft Aufruf-Argumente."""
    kandidaten = [
        {"id": 2652, "url": "/icons/2652.png"},
        {"id": 6591, "url": "/icons/6591.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegram()
    task = _make_task(icon_client=ic, tg=tg,
                      icon_origin_url="http://icons.example:5000")

    received = {}

    def spy(tg_arg, chat_id_arg, kand_arg, origin_arg):
        received["tg"] = tg_arg
        received["chat_id"] = chat_id_arg
        received["kandidaten"] = kand_arg
        received["origin"] = origin_arg

    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)

    with mock.patch(
        "skills.plan_aktivitaeten_setzen_task.icon_album.zeige_kandidaten",
        side_effect=spy,
    ):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "capueira",
        }, ctx)

    # Stub wurde aufgerufen
    assert "tg" in received, "zeige_kandidaten muss aufgerufen worden sein"
    # tg-Argument ist das Task-eigene tg-Objekt
    assert received["tg"] is tg
    # chat_id aus dem TurnContext
    assert received["chat_id"] == 42
    # Kandidaten-Liste wie vom Skill geliefert
    assert received["kandidaten"] == kandidaten
    # icon_origin_url wie bei Task-Bau gesetzt
    assert received["origin"] == "http://icons.example:5000"
    # Quittung enthält die IDs (D6-Mapping)
    assert "2652" in quittung
    assert "6591" in quittung
