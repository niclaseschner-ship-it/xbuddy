"""Tests für A2ReceiptStore (EC-10 A2-Receipt-Klausel, #841).

Prüft:
- Schema-Bootstrap: Tabelle + Index werden angelegt (CREATE TABLE IF NOT EXISTS).
- insert() schreibt eine Zeile mit korrekten Feldern.
- Versiegelungs-Logik: insert(B) nach insert(A) → A bekommt sealed_at != NULL.
- insert_many() schreibt N Zeilen mit identischer committed_at; Versiegelung
  vorher.
- expires_at = NULL für interne Schreibziele (Default).
- AC5: neuer insert setzt sealed_at auf vorherige unversiegelte Receipts
  (gleicher chat_id), lässt andere chat_id unberührt.
"""

import sqlite3

from a2_receipt_store import A2ReceiptStore

# ============================================================
#  Hilfsfunktionen
# ============================================================

def _alle_receipts(conn):
    cur = conn.execute(
        "SELECT task_name, chat_id, resource_id, inverse_call, "
        "committed_at, expires_at, sealed_at FROM a2_receipts "
        "ORDER BY id")
    return cur.fetchall()


# ============================================================
#  Schema-Test
# ============================================================

def test_schema_bootstrap(tmp_path):
    """CREATE TABLE IF NOT EXISTS + Index werden beim __init__ angelegt."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    store.close()

    conn = sqlite3.connect(db_path)
    # Tabelle existiert
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='a2_receipts'")
    assert cur.fetchone() is not None, "Tabelle a2_receipts fehlt"
    # Index existiert
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name='idx_a2_receipts_chat'")
    assert cur.fetchone() is not None, "Index idx_a2_receipts_chat fehlt"
    conn.close()


def test_schema_bootstrap_idempotent(tmp_path):
    """Zweiter __init__ auf gleicher DB wirft keine Exception."""
    db_path = str(tmp_path / "test.db")
    store1 = A2ReceiptStore(db_path)
    store1.close()
    store2 = A2ReceiptStore(db_path)  # IF NOT EXISTS — kein Fehler
    store2.close()


# ============================================================
#  insert() — Basis
# ============================================================

def test_insert_creates_row(tmp_path):
    """insert() schreibt eine Zeile; resource_id + inverse_call korrekt."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    store.insert(
        task_name="foto_senden",
        chat_id=100,
        resource_id="med-42",
        inverse_call='photo DELETE /api/v1/photo/medien/med-42',
    )
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    assert len(rows) == 1
    task_name, chat_id, resource_id, inverse_call, committed_at, expires_at, sealed_at = rows[0]
    assert task_name == "foto_senden"
    assert chat_id == 100
    assert resource_id == "med-42"
    assert inverse_call == 'photo DELETE /api/v1/photo/medien/med-42'
    assert committed_at is not None       # datetime('now') gesetzt
    assert expires_at is None             # intern → NULL
    assert sealed_at is None              # noch nicht versiegelt


def test_insert_expires_at_null_default(tmp_path):
    """expires_at ist None für interne Schreibziele (spec Z. 563-569)."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    store.insert("einkauf_hinzufuegen", 200, "item-99",
                 'essen DELETE /api/v1/essen/wuensche/item-99')
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    assert rows[0][5] is None  # expires_at


# ============================================================
#  Versiegelung (AC5)
# ============================================================

def test_versiegelung_beim_zweiten_insert(tmp_path):
    """insert(B) versiegelt insert(A) des gleichen chat_id (AC5).

    Erwartet: nach zweitem insert hat der erste Eintrag sealed_at != NULL;
    der zweite Eintrag hat sealed_at = NULL (frisch).
    """
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    store.insert("foto_senden", 100, "med-1",
                 'photo DELETE /api/v1/photo/medien/med-1')
    store.insert("foto_senden", 100, "med-2",
                 'photo DELETE /api/v1/photo/medien/med-2')
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    assert len(rows) == 2
    sealed_at_erster = rows[0][6]
    sealed_at_zweiter = rows[1][6]
    assert sealed_at_erster is not None, "Erster Receipt muss versiegelt sein"
    assert sealed_at_zweiter is None, "Zweiter Receipt darf noch nicht versiegelt sein"


def test_versiegelung_nur_gleicher_chat_id(tmp_path):
    """Versiegelung durch insert(chat_id=100) lässt chat_id=200 unberührt."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    store.insert("einkauf_hinzufuegen", 100, "item-1",
                 'essen DELETE /api/v1/essen/wuensche/item-1')
    store.insert("einkauf_hinzufuegen", 200, "item-2",
                 'essen DELETE /api/v1/essen/wuensche/item-2')
    # Dritter Insert auf chat_id=100 → versiegelt item-1, nicht item-2
    store.insert("foto_senden", 100, "med-x",
                 'photo DELETE /api/v1/photo/medien/med-x')
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    # rows[0]: item-1, chat_id=100, muss versiegelt sein
    assert rows[0][2] == "item-1"
    assert rows[0][6] is not None, "item-1 (chat 100) muss versiegelt sein"
    # rows[1]: item-2, chat_id=200, darf nicht versiegelt sein
    assert rows[1][2] == "item-2"
    assert rows[1][6] is None, "item-2 (chat 200) darf nicht versiegelt sein"
    # rows[2]: med-x, frisch
    assert rows[2][6] is None


def test_dreifache_versiegelung_kette(tmp_path):
    """Drei aufeinanderfolgende inserts: immer nur der letzte bleibt unversiegelt."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    for i in range(3):
        store.insert("foto_senden", 100, "med-%d" % i,
                     'photo DELETE /api/v1/photo/medien/med-%d' % i)
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    assert len(rows) == 3
    # Erste zwei versiegelt
    assert rows[0][6] is not None
    assert rows[1][6] is not None
    # Letzter unversiegelt
    assert rows[2][6] is None


# ============================================================
#  insert_many() — Multi-Item
# ============================================================

def test_insert_many_drei_items(tmp_path):
    """insert_many() schreibt 3 Zeilen; alle haben identische committed_at."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    items = [
        ("item-a", 'essen DELETE /api/v1/essen/wuensche/item-a'),
        ("item-b", 'essen DELETE /api/v1/essen/wuensche/item-b'),
        ("item-c", 'essen DELETE /api/v1/essen/wuensche/item-c'),
    ]
    store.insert_many("einkauf_hinzufuegen", 300, items)
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    assert len(rows) == 3
    committed_ats = {r[4] for r in rows}
    # Alle haben dieselbe committed_at (datetime('now') in einer Transaktion)
    assert len(committed_ats) == 1, (
        "Alle drei Items müssen identische committed_at haben, "
        "got: %r" % committed_ats)
    # Alle unversiegelt
    for row in rows:
        assert row[6] is None, "Frische Items dürfen nicht versiegelt sein"


def test_insert_many_versiegelt_vorherige(tmp_path):
    """insert_many(B) nach insert(A): A wird versiegelt, B-Items unversiegelt."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    store.insert("foto_senden", 400, "med-first",
                 'photo DELETE /api/v1/photo/medien/med-first')
    items = [
        ("item-x", 'essen DELETE /api/v1/essen/wuensche/item-x'),
        ("item-y", 'essen DELETE /api/v1/essen/wuensche/item-y'),
    ]
    store.insert_many("einkauf_hinzufuegen", 400, items)
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    assert len(rows) == 3
    # Erster (med-first) versiegelt
    assert rows[0][6] is not None
    # Zweiter und dritter (item-x, item-y) unversiegelt
    assert rows[1][6] is None
    assert rows[2][6] is None


def test_insert_many_leer_macht_nichts(tmp_path):
    """insert_many() mit leerer Liste schreibt keine Zeile."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)
    store.insert_many("einkauf_hinzufuegen", 500, [])
    store.close()

    conn = sqlite3.connect(db_path)
    rows = _alle_receipts(conn)
    conn.close()

    assert rows == []


# ============================================================
#  EC-36 Korrektur-Hook (#844) — fetch_unsealed_for_chat / seal_all_for_chat
# ============================================================

def test_fetch_unsealed_for_chat_liefert_nur_unsealed(tmp_path):
    """fetch_unsealed_for_chat() liefert nur unversiegelte Receipts der chat_id.

    Nach insert(A) + insert(B) ist A versiegelt, B frisch; fetch() liefert
    nur B. Dict-Keys sind die stabile Hook-Schnittstelle.
    """
    store = A2ReceiptStore(str(tmp_path / "test.db"))
    store.insert("foto_senden", 100, "med-1",
                 'photo DELETE /api/v1/photo/medien/med-1')
    store.insert("foto_senden", 100, "med-2",
                 'photo DELETE /api/v1/photo/medien/med-2')

    rows = store.fetch_unsealed_for_chat(100)
    assert len(rows) == 1
    assert rows[0]["resource_id"] == "med-2"
    assert rows[0]["task_name"] == "foto_senden"
    assert rows[0]["inverse_call"] == 'photo DELETE /api/v1/photo/medien/med-2'
    assert rows[0]["chat_id"] == 100
    assert rows[0]["committed_at"] is not None
    assert rows[0]["expires_at"] is None
    store.close()


def test_fetch_unsealed_for_chat_ignoriert_andere_chat_id(tmp_path):
    """Receipts anderer chat_ids bleiben außen vor."""
    store = A2ReceiptStore(str(tmp_path / "test.db"))
    store.insert("foto_senden", 100, "med-1",
                 'photo DELETE /api/v1/photo/medien/med-1')
    store.insert("einkauf_hinzufuegen", 200, "item-x",
                 'essen DELETE /api/v1/essen/wuensche/item-x')

    rows_100 = store.fetch_unsealed_for_chat(100)
    rows_200 = store.fetch_unsealed_for_chat(200)
    assert len(rows_100) == 1
    assert rows_100[0]["chat_id"] == 100
    assert len(rows_200) == 1
    assert rows_200[0]["chat_id"] == 200
    store.close()


def test_fetch_unsealed_for_chat_multi_item_alle_unsealed(tmp_path):
    """Bei insert_many() sind alle N Receipts unversiegelt und werden geliefert."""
    store = A2ReceiptStore(str(tmp_path / "test.db"))
    items = [
        ("item-a", 'essen DELETE /api/v1/essen/wuensche/item-a'),
        ("item-b", 'essen DELETE /api/v1/essen/wuensche/item-b'),
        ("item-c", 'essen DELETE /api/v1/essen/wuensche/item-c'),
    ]
    store.insert_many("einkauf_hinzufuegen", 300, items)

    rows = store.fetch_unsealed_for_chat(300)
    assert len(rows) == 3
    assert [r["resource_id"] for r in rows] == ["item-a", "item-b", "item-c"]
    store.close()


def test_fetch_unsealed_for_chat_leer_nach_seal(tmp_path):
    """Nach seal_all_for_chat() ist fetch() leer."""
    store = A2ReceiptStore(str(tmp_path / "test.db"))
    store.insert("foto_senden", 100, "med-1",
                 'photo DELETE /api/v1/photo/medien/med-1')
    n_sealed = store.seal_all_for_chat(100)

    assert n_sealed == 1
    assert store.fetch_unsealed_for_chat(100) == []
    store.close()


def test_seal_all_for_chat_nur_gleicher_chat_id(tmp_path):
    """seal_all_for_chat(100) berührt chat_id=200 nicht."""
    store = A2ReceiptStore(str(tmp_path / "test.db"))
    store.insert("foto_senden", 100, "med-1",
                 'photo DELETE /api/v1/photo/medien/med-1')
    store.insert("einkauf_hinzufuegen", 200, "item-x",
                 'essen DELETE /api/v1/essen/wuensche/item-x')

    n = store.seal_all_for_chat(100)
    assert n == 1
    # chat 200 bleibt unsealed
    assert len(store.fetch_unsealed_for_chat(200)) == 1
    store.close()


def test_seal_all_for_chat_idempotent(tmp_path):
    """Zweites seal_all_for_chat() siegelt nichts mehr — Rückgabe 0."""
    store = A2ReceiptStore(str(tmp_path / "test.db"))
    store.insert("foto_senden", 100, "med-1",
                 'photo DELETE /api/v1/photo/medien/med-1')
    store.seal_all_for_chat(100)
    n2 = store.seal_all_for_chat(100)

    assert n2 == 0
    store.close()
