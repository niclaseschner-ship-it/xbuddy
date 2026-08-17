"""Pre-Flight-Tests: einkauf_hinzufuegen A2-Receipt-Naht (EC-10 A2-Receipt, #841).

Prüft den Entry-Path: einkauf_hinzufuegen() → A2ReceiptStore.insert_many().

Test-Plan (AC3, AC4):
- 3-Item-Happy-Path: 3 Items angelegt → 3 Receipts mit identischer committed_at,
  inverse_call='essen DELETE /api/v1/essen/wuensche/<item_id>' pro Item
  (HTTP-Form, EC-10 spec Z. 533-535).
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
    Standard-Verhalten: 201 OK mit {"id": "test-server-id-N"} (Server-ID,
    bewusst VERSCHIEDEN von item_id, um AC1/#938 korrekt zu testen).
    """

    def __init__(self, responses=None):
        self._responses = responses or {}
        self.calls = []  # Liste von item_id-Strings der POST-Aufrufe
        self._counter = 0

    def hinzufuegen_einkauf(self, label, bild_ref, item_id, kategorie):
        self.calls.append(str(item_id))
        resp = self._responses.get(str(item_id))
        if isinstance(resp, Exception):
            raise resp
        self._counter += 1
        # Server-ID ist NICHT identisch mit item_id — simuliert echtes Server-Verhalten
        return {"id": "test-server-id-%d" % self._counter}


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

    # inverse_call hat die korrekte HTTP-Form (EC-10 spec Z. 533-535)
    inverse_calls = {row[3] for row in rows}
    for inv in inverse_calls:
        assert inv.startswith('essen DELETE /api/v1/essen/wuensche/'), (
            "inverse_call hat falsche Form: %r" % inv)

    # Alle drei haben identische committed_at (insert_many in einer Transaktion)
    committed_ats = {row[4] for row in rows}
    assert len(committed_ats) == 1, (
        "Multi-Item muss identische committed_at haben, got: %r" % committed_ats)

    # Alle drei unversiegelt (frisch)
    for row in rows:
        assert row[5] is None, "Frische Receipts dürfen nicht versiegelt sein"


def test_resource_id_ist_server_id(tmp_path):
    """AC1/#938: resource_id im Receipt ist die Server-ID aus resp["id"],
    NICHT die clientseitige item_id. Der Stub gibt bewusst eine andere ID zurück."""
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
    # Stub gibt "test-server-id-1" zurück — NICHT "brot-id-42" (client item_id)
    assert rows[0][2] == "test-server-id-1", (
        "resource_id muss Server-ID sein, got: %r" % rows[0][2])
    assert rows[0][3] == 'essen DELETE /api/v1/essen/wuensche/test-server-id-1', (
        "inverse_call muss Server-ID enthalten, got: %r" % rows[0][3])


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
    # AC3/#938: EC-10 A2-Quittungs-Wort-Pflicht — Wort `falsch` muss im Erfolgstext
    assert "falsch" in result.lower(), (
        "Einkauf-Quittung muss das Wort 'falsch' enthalten (EC-10 A2): %r" % result)


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


# ---------------------------------------------------------------------------
# #1843: Die Quittung nennt den Effekt, nicht nur das Undo-Wort
# ---------------------------------------------------------------------------

# Begriffe, an denen erkennbar ist, dass die Zeile den EFFEKT benennt. EC-10 A2
# laesst dem Skill ausdruecklich die eigene Stimme („Die konkrete Formulierung
# der Anleitung darf der Skill waehlen"), verbindlich ist der Inhalt. Deshalb
# wird hier KEIN Wortlaut festgenagelt, sondern nur, dass ueberhaupt gesagt wird,
# was passiert.
_EFFEKT_BEGRIFFE = ("liste", "runter", "rückgängig", "ruecknahme", "entferne", "nehme")


def _undo_zeile(text):
    """Die Zeile der Quittung, die das Undo-Wort traegt."""
    for zeile in text.splitlines():
        if "falsch" in zeile.lower():
            return zeile
    return ""


def test_quittung_nennt_den_effekt_nicht_nur_das_wort():
    """#1843: „sag einfach `falsch`." allein laesst Eltern raten, was dann passiert.

    Der Schmerz war der Vergleich mit der Foto-Quittung, die den Effekt nennt
    („ich mach es dann rueckgaengig") — die Einkaufs-Quittung tat es nicht.

    Wichtig fuer die Reichweite: diese Zeile geht **woertlich** an die Familie.
    Die Modell-Anweisung reicht jede Zeile mit `falsch` unveraendert durch, es
    glaettet sie also niemand nachtraeglich.
    """
    from skills.einkauf_hinzufuegen import _baue_antwort

    for anzahl in (1, 3):
        text = _baue_antwort(
            hinzugefuegt=["Milch"] * anzahl,
            uebersprungen=[],
            grenze_halt=None,
            offen_n=anzahl,
        )
        zeile = _undo_zeile(text)
        assert zeile, "Quittung enthaelt keine Undo-Zeile: %r" % text

        assert any(b in zeile.lower() for b in _EFFEKT_BEGRIFFE), (
            "Die Undo-Zeile nennt das Wort, aber nicht den Effekt (#1843, EC-10 A2).\n"
            "Zeile: %r\n"
            "Erwartet: irgendeine Formulierung, die sagt WAS passiert. Der "
            "Wortlaut ist frei — erkannt wird an einem von %r." % (zeile, _EFFEKT_BEGRIFFE)
        )
