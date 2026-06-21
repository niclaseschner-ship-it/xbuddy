"""Tests für die Funktion gericht_loeschen — ESSEN-19b, EC-10 Drei-Phasen.

AC2: Skill Drei-Phasen-Flow + Auswahl-Parse robust + LLM-ID-Halluzinations-Schutz.
AC3: delete_gericht (via FakeEssenClient).

Alle Tests ohne Netz (Fake-Clients, kein LLM-Netz).
"""

from skills.essen_client import EssenClientError
from skills.gericht_loeschen import (
    AKTION_AUSWAEHLEN,
    AKTION_LISTE,
    AKTION_LOESCHEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_AUSGEWAEHLT,
    SIGNAL_GELOESCHT,
    SIGNAL_GRENZE,
    SIGNAL_LEER,
    SIGNAL_LISTE,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_NICHTS_ZU_TUN,
    SIGNAL_UNBEKANNTE_IDS,
    gericht_loeschen,
)

# ============================================================
#  Doppelungen
# ============================================================

class FakeEssenClient:
    """EssenClient-Doppelung für gericht_loeschen (CLIENT-1)."""

    def __init__(self, gerichte=None, delete_error=None):
        self._gerichte = gerichte or []
        self._delete_error = delete_error
        self.delete_calls = []

    def lese_gerichte(self):
        return list(self._gerichte)

    def lese_katalog(self):
        return list(self._gerichte)

    def delete_gericht(self, gericht_id):
        self.delete_calls.append(gericht_id)
        if self._delete_error:
            raise self._delete_error
        return None


def _member(uid):
    return True


def _non_member(uid):
    return False


def _llm_fn_fuer(ids):
    """LLM-Stub: gibt JSON-Array der übergebenen IDs zurück."""
    import json
    def fn(prompt):
        return json.dumps(ids)
    return fn


_GERICHTE_FIXTURE = [
    {"id": "1", "label": "Lasagne", "bild_ref": "9999", "kategorie": "gericht"},
    {"id": "2", "label": "Pizza",   "bild_ref": "1234", "kategorie": "gericht"},
    {"id": "3", "label": "Pasta",   "foto_ref": "foto-x", "kategorie": "gericht"},
]


# ============================================================
#  Berechtigung (GAN-2-Muster)
# ============================================================

def test_nicht_mitglied_gibt_signal_abgelehnt():
    """Nicht-Mitglied → SIGNAL_ABGELEHNT, kein API-Aufruf."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion=AKTION_LISTE,
        essen_client=client,
        is_member_fn=_non_member,
        from_user_id=99,
    )

    assert signal == SIGNAL_ABGELEHNT
    assert client.delete_calls == []


def test_user_id_none_gibt_signal_abgelehnt():
    """from_user_id=None → SIGNAL_ABGELEHNT."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion=AKTION_LISTE,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=None,
    )

    assert signal == SIGNAL_ABGELEHNT


# ============================================================
#  Phase 1 — Lese-Phase
# ============================================================

def test_lese_phase_gibt_signal_liste_mit_gerichten():
    """AC2: Lese-Phase liefert SIGNAL_LISTE mit Gerichte-Liste."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, daten = gericht_loeschen(
        aktion=AKTION_LISTE,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
    )

    assert signal == SIGNAL_LISTE
    assert len(daten["gerichte"]) == 3
    ids = [g["id"] for g in daten["gerichte"]]
    assert "1" in ids
    assert "2" in ids
    assert "3" in ids


def test_lese_phase_leerer_katalog_gibt_signal_leer():
    """AC2: leerer Katalog → SIGNAL_LEER."""
    client = FakeEssenClient(gerichte=[])

    signal, _ = gericht_loeschen(
        aktion=AKTION_LISTE,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
    )

    assert signal == SIGNAL_LEER


def test_lese_phase_buddy_nicht_erreichbar():
    """Lese-Phase: Buddy nicht erreichbar → SIGNAL_NICHT_ERREICHBAR."""
    class FehlerhafterClient(FakeEssenClient):
        def lese_gerichte(self):
            raise EssenClientError("Buddy down")

    client = FehlerhafterClient()

    signal, daten = gericht_loeschen(
        aktion=AKTION_LISTE,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert "detail" in daten


# ============================================================
#  Phase 2 — Auswahl-Phase (AC2: Auswahl-Parse robust)
# ============================================================

def test_auswahl_phase_freitext_ordnungszahl():
    """AC2: Freitext Ordnungszahlen '1 und 2' → IDs '1' und '2' korrekt aufgelöst."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)
    llm_fn = _llm_fn_fuer(["1", "2"])

    signal, daten = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="1 und 2",
        llm_fn=llm_fn,
    )

    assert signal == SIGNAL_AUSGEWAEHLT
    assert set(daten["gericht_ids"]) == {"1", "2"}
    assert "Lasagne" in daten["labels"]
    assert "Pizza" in daten["labels"]


def test_auswahl_phase_freitext_name():
    """AC2: Freitext Name 'Lasagne' → ID '1' aufgelöst."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)
    llm_fn = _llm_fn_fuer(["1"])

    signal, daten = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="Lasagne",
        llm_fn=llm_fn,
    )

    assert signal == SIGNAL_AUSGEWAEHLT
    assert daten["gericht_ids"] == ["1"]
    assert daten["labels"] == ["Lasagne"]


def test_auswahl_phase_llm_halluzination_gibt_signal_unbekannte_ids():
    """AC2: LLM halluziniert ID '99' (nicht in Liste) → SIGNAL_UNBEKANNTE_IDS."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)
    llm_fn = _llm_fn_fuer(["99"])  # ID 99 existiert nicht

    signal, daten = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="das letzte",
        llm_fn=llm_fn,
    )

    assert signal == SIGNAL_UNBEKANNTE_IDS
    assert "99" in daten["verdaechtig"]


def test_auswahl_phase_llm_halluzination_mix_valide_und_ungueltig():
    """AC2: LLM gibt Mix aus valider (1) und halluzinierter (99) ID → SIGNAL_UNBEKANNTE_IDS."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)
    llm_fn = _llm_fn_fuer(["1", "99"])

    signal, daten = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="1 und das unbekannte",
        llm_fn=llm_fn,
    )

    assert signal == SIGNAL_UNBEKANNTE_IDS
    assert "99" in daten["verdaechtig"]


def test_auswahl_phase_ohne_freitext_gibt_nichts_zu_tun():
    """AC2: leerer Freitext → SIGNAL_NICHTS_ZU_TUN."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="",
        llm_fn=_llm_fn_fuer(["1"]),
    )

    assert signal == SIGNAL_NICHTS_ZU_TUN


def test_auswahl_phase_ohne_llm_fn_gibt_nichts_zu_tun():
    """AC2: llm_fn=None → SIGNAL_NICHTS_ZU_TUN (Provider nicht gesetzt)."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="Lasagne",
        llm_fn=None,
    )

    assert signal == SIGNAL_NICHTS_ZU_TUN


def test_auswahl_phase_llm_antwortet_mit_code_fence():
    """AC2: LLM-Antwort mit Markdown-Fence wird korrekt geparst."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    def llm_fn_code_fence(prompt):
        return '```json\n["1", "2"]\n```'

    signal, daten = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="erste zwei",
        llm_fn=llm_fn_code_fence,
    )

    assert signal == SIGNAL_AUSGEWAEHLT
    assert set(daten["gericht_ids"]) == {"1", "2"}


def test_auswahl_phase_llm_antwortet_ungueltig_gibt_nichts_zu_tun():
    """AC2: LLM-Antwort nicht parsbar → SIGNAL_NICHTS_ZU_TUN."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion=AKTION_AUSWAEHLEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        freitext="Lasagne",
        llm_fn=lambda p: "keine IDs hier",
    )

    assert signal == SIGNAL_NICHTS_ZU_TUN


# ============================================================
#  Phase 3 — Schreib-Phase
# ============================================================

def test_schreib_phase_loescht_ein_gericht():
    """AC2: Schreib-Phase löscht ein Gericht → SIGNAL_GELOESCHT."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, daten = gericht_loeschen(
        aktion=AKTION_LOESCHEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        gericht_ids=["1"],
    )

    assert signal == SIGNAL_GELOESCHT
    assert client.delete_calls == ["1"]
    assert len(daten["labels"]) == 1


def test_schreib_phase_loescht_mehrere_gerichte():
    """AC2: Schreib-Phase löscht mehrere Gerichte → SIGNAL_GELOESCHT."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion=AKTION_LOESCHEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        gericht_ids=["1", "2"],
    )

    assert signal == SIGNAL_GELOESCHT
    assert set(client.delete_calls) == {"1", "2"}


def test_schreib_phase_buddy_4xx_gibt_signal_grenze():
    """Schreib-Phase: Buddy 4xx → SIGNAL_GRENZE (ehrliche Grenze EC-7)."""
    client = FakeEssenClient(
        gerichte=_GERICHTE_FIXTURE,
        delete_error=EssenClientError("HTTP 404 — nicht gefunden", marker="4xx"),
    )

    signal, _ = gericht_loeschen(
        aktion=AKTION_LOESCHEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        gericht_ids=["1"],
    )

    assert signal == SIGNAL_GRENZE


def test_schreib_phase_buddy_5xx_gibt_signal_nicht_erreichbar():
    """Schreib-Phase: Buddy 5xx / Verbindungsfehler → SIGNAL_NICHT_ERREICHBAR."""
    client = FakeEssenClient(
        gerichte=_GERICHTE_FIXTURE,
        delete_error=EssenClientError("HTTP 503 — Buddy down"),
    )

    signal, _ = gericht_loeschen(
        aktion=AKTION_LOESCHEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        gericht_ids=["1"],
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR


def test_schreib_phase_leere_ids_gibt_nichts_zu_tun():
    """Schreib-Phase ohne IDs → SIGNAL_NICHTS_ZU_TUN."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion=AKTION_LOESCHEN,
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
        gericht_ids=[],
    )

    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert client.delete_calls == []


# ============================================================
#  Unbekannte Aktion
# ============================================================

def test_unbekannte_aktion_gibt_nichts_zu_tun():
    """Unbekannte Aktion → SIGNAL_NICHTS_ZU_TUN."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)

    signal, _ = gericht_loeschen(
        aktion="ungueltig",
        essen_client=client,
        is_member_fn=_member,
        from_user_id=1,
    )

    assert signal == SIGNAL_NICHTS_ZU_TUN
