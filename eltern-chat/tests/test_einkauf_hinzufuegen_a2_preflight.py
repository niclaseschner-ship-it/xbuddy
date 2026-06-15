"""Pre-Flight-Tests: einkauf_hinzufuegen A2-Receipt-Naht (EC-10 A2-Receipt, #841).

Prüft den Entry-Path: einkauf_hinzufuegen() → A2ReceiptStore.insert_many().

Test-Plan (AC3, AC4):
- 3-Item-Happy-Path: 3 Items angelegt → 3 Receipts mit identischer committed_at,
  inverse_call='essen_client.delete_einkauf("<item_id>")' pro Item.
- Duplikat-Skip: übersprungene Items bekommen keinen Receipt.
- Kein Receipt bei sonstigem Fehler (Rückgabe-Pfad verlässt Loop früh).
- Backward-Compat: receipt_store=None → kein Fehler, Items trotzdem geschrieben.
- Versiegelung: Folge-Aufruf versiegelt vorherige Receipts desselben chat_id.
"""

import sqlite3

from a2_receipt_store import A2ReceiptStore
from skills.einkauf_hinzufuegen import einkauf_hinzufuegen
from skills.essen_client import FEHLER_DUPLIKAT, EssenClientError

# ============================================================
#  Stubs
# ============================================================

class FakeEssenClient:
    """Minimalstub für EssenClient.hinzufuegen_einkauf().

    `responses`: Dict item_id → Exception oder True (Erfolg).
    Standard-Verhalten: 201 OK mit {"id": item_id}.
    """

    def __init__(self, responses=None):
        self._responses = responses or {}
        self.calls = []  # Liste von item_id-Strings der POST-Aufrufe

    def hinzufuegen_einkauf(self, label, bild_ref, item_id, kategorie):
        self.calls.append(str(item_id))
        resp = self._responses.get(str(item_id))
        if isinstance(resp, Exception):
            raise resp
        return {"id": str(item_id)}


class FakeIconClient:
    """IconClient-Stub: liefert immer keinen Treffer (Default-Pfad)."""

    def suche(self, label, max_treffer=1):
        return []


def _kein_mitglied(uid):
    return False


def _immer_mitglied(uid):
    return True


def _katalog_leer():
    return None


def _receipts(conn):
    cur = conn.execute(
        "SELECT task_name, chat_id, resource_id, inverse_call, committed_at, sealed_at "
        "FROM a2_receipts ORDER BY id")
    return cur.fetchall()


# ============================================================
#  Entry-Path: 3 Items → 3 Receipts
# ============================================================

def test_drei_items_drei_receipts(tmp_path):
    """AC3/AC4: 3 Items hinzugefügt → 3 Receipts mit identischer committed_at."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    essen = FakeEssenClient()
    icons = FakeIconClient()

    einkauf_hinzufuegen(
        text="Brot, Milch, Joghurt",
        from_user_id=42,
        essen_client=essen,
        icon_client=icons,
        is_member_fn=_immer_mitglied,
        katalog=None,
        receipt_store=store,
        chat_id=100,
    )

    # Alle 3 wurden angelegt
    assert len(essen.calls) == 3

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert len(rows) == 3, "Exakt 3 Receipts erwartet, got %d" % len(rows)

    # task_name und chat_id korrekt
    for row in rows:
        assert row[0] == "einkauf_hinzufuegen"
        assert row[1] == 100

    # inverse_call hat die korrekte Form
    inverse_calls = {row[3] for row in rows}
    for inv in inverse_calls:
        assert inv.startswith('essen_client.delete_einkauf("'), (
            "inverse_call hat falsche Form: %r" % inv)

    # Alle drei haben identische committed_at (insert_many in einer Transaktion)
    committed_ats = {row[4] for row in rows}
    assert len(committed_ats) == 1, (
        "Multi-Item muss identische committed_at haben, got: %r" % committed_ats)

    # Alle drei unversiegelt (frisch)
    for row in rows:
        assert row[5] is None, "Frische Receipts dürfen nicht versiegelt sein"


def test_resource_id_ist_item_id(tmp_path):
    """resource_id im Receipt entspricht der item_id aus _match_item (EIN-5)."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    # Katalog-Item mit bekannter item_id → Katalog-Match-Pfad
    katalog = [
        {"label": "Brot", "bild_ref": "123", "item_id": "brot-id-42",
         "kategorie": "backwaren"},
    ]
    essen = FakeEssenClient()
    icons = FakeIconClient()

    einkauf_hinzufuegen(
        text="Brot",
        from_user_id=42,
        essen_client=essen,
        icon_client=icons,
        is_member_fn=_immer_mitglied,
        katalog=katalog,
        receipt_store=store,
        chat_id=200,
    )

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert len(rows) == 1
    assert rows[0][2] == "brot-id-42"   # resource_id
    assert rows[0][3] == 'essen_client.delete_einkauf("brot-id-42")'


def test_duplikat_kein_receipt(tmp_path):
    """Übersprungene Duplikate bekommen keinen Receipt-Eintrag."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    essen = FakeEssenClient(responses={
        "frei:brot": EssenClientError("dup", marker=FEHLER_DUPLIKAT),
    })
    icons = FakeIconClient()

    einkauf_hinzufuegen(
        text="Brot",
        from_user_id=42,
        essen_client=essen,
        icon_client=icons,
        is_member_fn=_immer_mitglied,
        katalog=None,
        receipt_store=store,
        chat_id=300,
    )

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert rows == [], "Duplikat-Skip darf keinen Receipt schreiben"


def test_backward_compat_ohne_store(tmp_path):
    """receipt_store=None → kein Crash, Items werden trotzdem geschrieben."""
    essen = FakeEssenClient()
    icons = FakeIconClient()

    result = einkauf_hinzufuegen(
        text="Milch, Eier",
        from_user_id=42,
        essen_client=essen,
        icon_client=icons,
        is_member_fn=_immer_mitglied,
        katalog=None,
        receipt_store=None,  # kein Store
        chat_id=400,
    )

    assert len(essen.calls) == 2
    assert "Milch" in result or "Eier" in result or "dazu" in result


def test_kein_receipt_ohne_chat_id(tmp_path):
    """chat_id=None → kein Receipt (Sicherheits-Fallback)."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    essen = FakeEssenClient()
    icons = FakeIconClient()

    einkauf_hinzufuegen(
        text="Brot",
        from_user_id=42,
        essen_client=essen,
        icon_client=icons,
        is_member_fn=_immer_mitglied,
        katalog=None,
        receipt_store=store,
        chat_id=None,  # kein chat_id
    )

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert rows == [], "Ohne chat_id darf kein Receipt geschrieben werden"


# ============================================================
#  Versiegelung bei Folge-Anfrage
# ============================================================

def test_folge_anfrage_versiegelt_vorherige_receipts(tmp_path):
    """Zweiter einkauf_hinzufuegen-Aufruf versiegelt die Receipts des ersten."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    essen = FakeEssenClient()
    icons = FakeIconClient()

    # Erster Aufruf: 2 Items
    einkauf_hinzufuegen(
        text="Brot, Milch",
        from_user_id=42,
        essen_client=essen,
        icon_client=icons,
        is_member_fn=_immer_mitglied,
        katalog=None,
        receipt_store=store,
        chat_id=100,
    )

    # Zweiter Aufruf (Folge-Anfrage): 1 Item — versiegelt die vorherigen 2
    einkauf_hinzufuegen(
        text="Joghurt",
        from_user_id=42,
        essen_client=essen,
        icon_client=icons,
        is_member_fn=_immer_mitglied,
        katalog=None,
        receipt_store=store,
        chat_id=100,
    )

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert len(rows) == 3
    # Erste zwei versiegelt
    assert rows[0][5] is not None, "Erster Receipt muss versiegelt sein"
    assert rows[1][5] is not None, "Zweiter Receipt muss versiegelt sein"
    # Dritter (Joghurt) unversiegelt
    assert rows[2][5] is None, "Dritter Receipt darf noch nicht versiegelt sein"
