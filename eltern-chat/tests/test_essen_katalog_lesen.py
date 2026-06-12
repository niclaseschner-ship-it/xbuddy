"""Tests für die Funktion essen_katalog_lesen — ESSEN-22 V1.1, EC-9.

AC1: essen_katalog_lesen liefert (signal, daten) mit SIGNAL_GELESEN +
{kategorien: [...]}, SIGNAL_ABGELEHNT bei Nicht-Mitglied, SIGNAL_NICHT_ERREICHBAR
bei EssenClientError.

Prüft die trigger-agnostische Lese-Funktion: Signale, EC-2-Berechtigung,
Fehlerbehandlung. Kein propose→confirm, kein Schreiben.
"""

from skills.essen_client import EssenClientError
from skills.essen_katalog_lesen import (
    SIGNAL_ABGELEHNT,
    SIGNAL_GELESEN,
    SIGNAL_NICHT_ERREICHBAR,
    essen_katalog_lesen,
)

# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakeEssenClient:
    """Minimal-Doppelung des EssenClients für Katalog-Lese-Tests."""

    def __init__(self, katalog_response=None, katalog_error=None):
        self.lese_katalog_calls = []
        self._katalog_response = katalog_response if katalog_response is not None else []
        self._katalog_error = katalog_error

    def lese_katalog(self):
        self.lese_katalog_calls.append(True)
        if self._katalog_error is not None:
            raise self._katalog_error
        return list(self._katalog_response)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


_ITEMS_EINFACH = [
    {"id": "g-1", "label": "Lasagne", "bild_ref": "lasagne-icon",
     "kategorie": "gerichte"},
    {"id": "g-2", "label": "Pizza", "bild_ref": "pizza-icon",
     "kategorie": "gerichte"},
    {"id": "i-1", "label": "Tomate", "bild_ref": "tomate-icon",
     "kategorie": "gemuese"},
]


# ============================================================
#  EC-2: Berechtigung
# ============================================================

def test_ec2_nicht_mitglied_abgelehnt():
    """EC-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein lese_katalog()."""
    client = FakeEssenClient()
    signal, _ = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_kein_mitglied,
        from_user_id=99,
    )
    assert signal == SIGNAL_ABGELEHNT
    assert client.lese_katalog_calls == []


def test_ec2_kein_user_id_abgelehnt():
    """EC-2: from_user_id=None → SIGNAL_ABGELEHNT."""
    client = FakeEssenClient()
    signal, _ = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=None,
    )
    assert signal == SIGNAL_ABGELEHNT
    assert client.lese_katalog_calls == []


# ============================================================
#  AC1: Signal SIGNAL_GELESEN + Struktur
# ============================================================

def test_signal_gelesen_strukturiert():
    """AC1: essen_katalog_lesen liefert SIGNAL_GELESEN mit 'kategorien'-Liste."""
    client = FakeEssenClient(katalog_response=_ITEMS_EINFACH)
    signal, daten = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_GELESEN
    assert "kategorien" in daten
    assert isinstance(daten["kategorien"], list)


def test_kategorien_und_gerichte_im_output():
    """AC1: Katalog-Output enthält Items mit id, label, bild_ref, kategorie."""
    client = FakeEssenClient(katalog_response=_ITEMS_EINFACH)
    signal, daten = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_GELESEN
    items = daten["kategorien"]
    assert len(items) == len(_ITEMS_EINFACH)
    # Gericht-Item vorhanden
    gericht_ids = [item["id"] for item in items if item.get("kategorie") == "gerichte"]
    assert "g-1" in gericht_ids
    assert "g-2" in gericht_ids
    # Basis-Item vorhanden
    basis_ids = [item["id"] for item in items if item.get("kategorie") == "gemuese"]
    assert "i-1" in basis_ids


def test_lesen_ruft_lese_katalog_auf():
    """AC1: essen_katalog_lesen ruft lese_katalog() genau einmal auf."""
    client = FakeEssenClient(katalog_response=_ITEMS_EINFACH)
    essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert len(client.lese_katalog_calls) == 1


def test_leerer_katalog_signal_gelesen():
    """AC1: Leerer Katalog → SIGNAL_GELESEN mit leerer 'kategorien'-Liste."""
    client = FakeEssenClient(katalog_response=[])
    signal, daten = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_GELESEN
    assert daten["kategorien"] == []


# ============================================================
#  AC1: Fehlerbehandlung
# ============================================================

def test_signal_nicht_erreichbar_essen_client_error():
    """AC1: lese_katalog() wirft EssenClientError → SIGNAL_NICHT_ERREICHBAR."""
    client = FakeEssenClient(
        katalog_error=EssenClientError("Essens-Buddy nicht erreichbar"))
    signal, daten = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert "detail" in daten


def test_signal_abgelehnt_nicht_mitglied():
    """AC1: Nicht-Mitglied → SIGNAL_ABGELEHNT, {} als Daten."""
    client = FakeEssenClient(katalog_response=_ITEMS_EINFACH)
    signal, daten = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_kein_mitglied,
        from_user_id=42,
    )
    assert signal == SIGNAL_ABGELEHNT
    assert daten == {}


# ============================================================
#  EC-9: Kein Schreiben
# ============================================================

def test_kein_schreiben():
    """EC-9: essen_katalog_lesen verändert KEINE Daten — nur lese_katalog()."""
    class StrictFakeClient(FakeEssenClient):
        def post_gericht(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

        def hinzufuegen_einkauf(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

        def patch_gericht_bild(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

    client = StrictFakeClient(katalog_response=_ITEMS_EINFACH)
    signal, _ = essen_katalog_lesen(
        essen_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
    )
    assert signal == SIGNAL_GELESEN
