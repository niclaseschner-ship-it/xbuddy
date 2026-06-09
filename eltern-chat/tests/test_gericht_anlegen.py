"""Tests für die Funktion gericht_anlegen — GAN-1 … GAN-7, E-GAN-1 … E-GAN-3
(Refs #503).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(GAN-7, CLAUDE.md §6). Essens-Buddy, Router-Icon-Suche und Telegram sind
durch kontrollierte Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

Pflicht-Tests (Spec GAN-7):
- Nicht-Mitglied → Ablehnung, kein Schreiben (GAN-2).
- Happy-Path: icon_suchen → Kandidaten → propose → execute → POST.
- Icon-Suche ohne Treffer → Skill fragt nach anderem Wort, erfindet keine ID
  (GAN-4 / E-GAN-3).
- Buddy-409 (doppeltes Label) → kein Schreiben, ehrliche Grenze (GAN-5).
- Buddy-4xx (leeres Label) → kein Schreiben, ehrliche Grenze (GAN-5).
- APP-3: der Skill ruft die API, nicht die Datei.
"""

import unittest.mock as mock

from skills.essen_client import EssenClientError
from skills.gericht_anlegen import (
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_ANGELEGT,
    SIGNAL_GRENZE,
    SIGNAL_ICON_KANDIDATEN,
    SIGNAL_KEINE_ICONS,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_NICHTS_ZU_TUN,
    gericht_anlegen,
)
from skills.icon_client import IconClientError

# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakeEssenClient:
    """EssenClient-Doppelung (CLIENT-1, GAN-6)."""

    def __init__(self, post_response=None, post_error=None):
        self.post_calls = []
        self._post_response = post_response or {"id": "1"}
        self._post_error = post_error

    def post_gericht(self, name, icon_id):
        self.post_calls.append({"name": name, "icon_id": icon_id})
        if self._post_error is not None:
            raise self._post_error
        return dict(self._post_response)


class FakeIconClient:
    """ICONS-7-Doppelung des IconClients (CLIENT-1, GAN-4)."""

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
#  GAN-2: Berechtigung — Nicht-Mitglied → Ablehnung, kein Schreiben
# ============================================================

def test_GAN2_nicht_mitglied_kein_post():
    """GAN-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein post_gericht-Aufruf."""
    ec = FakeEssenClient()
    ic = FakeIconClient(response=[{"id": 9999, "url": "/x"}])

    signal, _ = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=ic,
        is_member_fn=_kein_mitglied,
        from_user_id=99,
        label="Lasagne",
        icon_id="9999",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert ec.post_calls == [], "Kein POST bei Nicht-Mitglied (GAN-2)"


def test_GAN2_kein_user_id_abgelehnt():
    """GAN-2: from_user_id=None → SIGNAL_ABGELEHNT."""
    ec = FakeEssenClient()

    signal, _ = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=None,
        label="X",
        icon_id="1",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert ec.post_calls == []


def test_GAN2_nicht_mitglied_kein_icon_suchen():
    """GAN-2: Nicht-Mitglied → auch kein Icon-Suchen."""
    ic = FakeIconClient()

    signal, _ = gericht_anlegen(
        aktion=AKTION_ICON_SUCHEN,
        essen_client=FakeEssenClient(),
        icon_client=ic,
        is_member_fn=_kein_mitglied,
        from_user_id=99,
        icon_stichwort="Lasagne",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert ic.suche_calls == []


# ============================================================
#  GAN-4: ICONS-7-Stichwort-Suche
# ============================================================

def test_GAN4_icon_suchen_drei_kandidaten():
    """GAN-4: icon_suchen → ICONS-7-Aufruf mit q=<wort>&max=3,
    liefert SIGNAL_ICON_KANDIDATEN mit den Treffern."""
    ic = FakeIconClient(response=[
        {"id": 1111, "url": "/display/_shared/icons/arasaac/1111.png"},
        {"id": 2222, "url": "/display/_shared/icons/arasaac/2222.png"},
        {"id": 3333, "url": "/display/_shared/icons/arasaac/3333.png"},
    ])

    signal, daten = gericht_anlegen(
        aktion=AKTION_ICON_SUCHEN,
        essen_client=FakeEssenClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Lasagne",
    )

    assert signal == SIGNAL_ICON_KANDIDATEN
    assert daten["label"] == "Lasagne"
    assert len(daten["kandidaten"]) == 3
    assert {k["id"] for k in daten["kandidaten"]} == {1111, 2222, 3333}
    assert ic.suche_calls == [{"stichwort": "Lasagne", "max_treffer": 3}]


def test_GAN4_icon_suchen_keine_treffer():
    """GAN-4 / E-GAN-3: ICONS-7 ohne Treffer → SIGNAL_KEINE_ICONS,
    Skill fragt nach anderem Wort, erfindet KEINE ID."""
    ic = FakeIconClient(response=[])

    signal, daten = gericht_anlegen(
        aktion=AKTION_ICON_SUCHEN,
        essen_client=FakeEssenClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Glubschauge",
    )

    assert signal == SIGNAL_KEINE_ICONS
    assert daten["label"] == "Glubschauge"


def test_GAN4_icon_max_wird_auf_3_gecapped():
    """GAN-4: bis zu drei Kandidaten — Hard-Cap auf 3."""
    ic = FakeIconClient(response=[{"id": 1, "url": "/a"}])

    gericht_anlegen(
        aktion=AKTION_ICON_SUCHEN,
        essen_client=FakeEssenClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Pizza",
        icon_max=42,
    )

    assert ic.suche_calls[0]["max_treffer"] == 3


def test_GAN4_icon_suchen_router_nicht_erreichbar():
    """GAN-4 / EC-7: ICONS-7 wirft IconClientError → SIGNAL_NICHT_ERREICHBAR."""
    ic = FakeIconClient(error=IconClientError("Router nicht erreichbar"))

    signal, _ = gericht_anlegen(
        aktion=AKTION_ICON_SUCHEN,
        essen_client=FakeEssenClient(),
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        icon_stichwort="Lasagne",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR


# ============================================================
#  GAN-3: Gericht hinzufügen (Happy-Path)
# ============================================================

def test_GAN3_hinzufuegen_happy_path():
    """GAN-3: hinzufügen → POST mit label + bild_ref (Transport-Stub,
    CLIENT-1)."""
    ec = FakeEssenClient(post_response={"id": "42"})
    ic = FakeIconClient()

    signal, daten = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=ic,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="Lasagne",
        icon_id="9999",
    )

    assert signal == SIGNAL_ANGELEGT
    assert daten == {"id": "42"}
    assert ec.post_calls == [{"name": "Lasagne", "icon_id": "9999"}]


def test_GAN3_hinzufuegen_ohne_label_nichts_zu_tun():
    """GAN-3: hinzufügen ohne label → SIGNAL_NICHTS_ZU_TUN, kein POST."""
    ec = FakeEssenClient()
    signal, daten = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="",
        icon_id="1",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "kein Label"
    assert ec.post_calls == []


def test_GAN3_hinzufuegen_ohne_icon_id_nichts_zu_tun():
    """GAN-4 / E-GAN-3: hinzufügen ohne icon_id → NICHTS_ZU_TUN, kein POST.

    Der Skill darf NIE eine ARASAAC-ID raten (E-GAN-3) — ohne gewählte
    ID geht's also nicht weiter.
    """
    ec = FakeEssenClient()
    signal, daten = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="Lasagne",
        icon_id="",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten["reason"] == "kein Icon"
    assert ec.post_calls == []


# ============================================================
#  GAN-5: Buddy-4xx → ehrliche Grenze, kein Schreiben (EC-7)
# ============================================================

def test_GAN5_buddy_409_duplikat_grenze():
    """GAN-5: 409 vom Buddy (doppeltes Label) → SIGNAL_GRENZE mit
    Buddy-Fehlermeldung, KEIN automatisches Re-Try (ehrliche Grenze EC-7)."""
    ec = FakeEssenClient(
        post_error=EssenClientError(
            "Essens-Buddy: HTTP 409 bei POST /api/v1/essen/katalog/gerichte "
            "— Gericht existiert bereits"))

    signal, daten = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="Lasagne",
        icon_id="9999",
    )

    assert signal == SIGNAL_GRENZE
    assert "409" in daten["detail"] or "bereits" in daten["detail"]
    assert len(ec.post_calls) == 1, "Kein Retry (GAN-5)"


def test_GAN5_buddy_400_leeres_label_grenze():
    """GAN-5: 4xx vom Buddy (leeres Label) → SIGNAL_GRENZE."""
    ec = FakeEssenClient(
        post_error=EssenClientError(
            "Essens-Buddy: HTTP 400 bei POST /api/v1/essen/katalog/gerichte"))

    signal, _ = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="X",
        icon_id="1",
    )

    assert signal == SIGNAL_GRENZE


def test_GAN5_buddy_5xx_nicht_erreichbar():
    """GAN-5: 5xx vom Buddy → SIGNAL_NICHT_ERREICHBAR."""
    ec = FakeEssenClient(
        post_error=EssenClientError(
            "Essens-Buddy: HTTP 503 bei POST /api/v1/essen/katalog/gerichte"))

    signal, _ = gericht_anlegen(
        aktion=AKTION_HINZUFUEGEN,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        label="Lasagne",
        icon_id="9999",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR


# ============================================================
#  APP-3: Skill ruft API, nicht Datei
# ============================================================

def test_APP3_keine_datei_zugriffe():
    """APP-3 / GAN-6: die Funktion schreibt gerichte.json NICHT direkt.

    EssenClient ist die einzige Schreib-Naht (GAN-6), IconClient die
    einzige Icon-Lese-Naht (GAN-4). Mit open()-Blockade müssen die Tests
    durchlaufen — ein FS-Bypass würde die Blockade auslösen.
    """
    ec = FakeEssenClient(post_response={"id": "1"})
    ic = FakeIconClient(response=[{"id": 1, "url": "/x"}])

    with mock.patch("builtins.open",
                    side_effect=AssertionError("FS-Bypass verboten")):
        signal, _ = gericht_anlegen(
            aktion=AKTION_HINZUFUEGEN,
            essen_client=ec,
            icon_client=ic,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            label="Lasagne",
            icon_id="1",
        )

    assert signal == SIGNAL_ANGELEGT
    assert len(ec.post_calls) == 1
