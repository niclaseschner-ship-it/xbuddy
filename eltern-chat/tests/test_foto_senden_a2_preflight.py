"""Pre-Flight-Tests: foto_senden A2-Receipt-Naht (EC-10 A2-Receipt, #841).

Prüft den Entry-Path: FotoSendenTask.run() → A2ReceiptStore.insert().

Test-Plan (AC2, AC4):
- Happy-Path: Hochladen → Receipt geschrieben, resource_id=medium_id,
  inverse_call='photo DELETE /api/v1/photo/medien/<id>' (HTTP-Form,
  EC-10 spec Z. 533-535).
- Sequenz-Probe: Hochladen → delete-Stub aufgerufen (Widerruf simuliert).
- Kein Receipt bei Fehler-Signal (Grenze, nicht erreichbar).
- Kein Receipt, wenn receipt_store=None (Backward-Compat).
- Kein Receipt beim Widerruf-Pfad (aktion=widerrufen).
"""

import json
import sqlite3

from a2_receipt_store import A2ReceiptStore
from skills.foto_senden_task import FotoSendenTask
from skills.photo_client import PhotoClient
from tasks import TurnContext

# ============================================================
#  Hilfsfunktionen
# ============================================================

def _transport_factory(post_status=200, medium_id="med-abc",
                       delete_status=204):
    """Transport-Stub: POST → {"id": medium_id, "typ": "foto"}, DELETE → 204."""
    calls = []
    post_body = json.dumps({"id": medium_id, "typ": "foto"}).encode("utf-8")

    def transport(method, path, *, body=None, content_type=None):
        calls.append({"method": method, "path": path})
        if method == "POST":
            return post_status, post_body
        if method == "DELETE":
            return delete_status, b""
        raise AssertionError("unerwartete Methode: %s" % method)

    return transport, calls


class FakeTelegramMitDownload:
    """Minimaler Telegram-Stub mit download_file."""

    def download_file(self, file_id):
        return b"FAKEJPEG"


def _immer_mitglied(uid):
    return True


def _make_turn_context(chat_id=100, file_id="tg-file-1", medium_typ="foto"):
    """Baut einen minimalen TurnContext-Stub."""
    ctx = TurnContext(chat_id=chat_id)
    ctx.media_telegram_file_id = file_id
    ctx.medium_typ = medium_typ
    ctx.from_user_id = 42
    return ctx


def _receipts(conn):
    cur = conn.execute(
        "SELECT task_name, chat_id, resource_id, inverse_call, sealed_at "
        "FROM a2_receipts ORDER BY id")
    return cur.fetchall()


# ============================================================
#  Entry-Path: run() → receipt_store.insert()
# ============================================================

def test_hochladen_schreibt_receipt(tmp_path):
    """AC2: erfolgreicher Upload → Receipt mit resource_id=medium_id,
    inverse_call='photo DELETE /api/v1/photo/medien/<id>' (HTTP-Form,
    EC-10 spec Z. 533-535)."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    transport, calls = _transport_factory(medium_id="med-xyz")
    photo_client = PhotoClient("http://127.0.0.1:5070", transport=transport)

    task = FotoSendenTask(
        tg=FakeTelegramMitDownload(),
        photo_client=photo_client,
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=_immer_mitglied,
        receipt_store=store,
    )
    ctx = _make_turn_context(chat_id=100)
    result = task.run({}, ctx)

    # POST wurde gemacht
    assert any(c["method"] == "POST" for c in calls)
    # Quittung enthält die id
    assert "med-xyz" in result

    # Receipt wurde geschrieben
    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert len(rows) == 1
    task_name, chat_id, resource_id, inverse_call, sealed_at = rows[0]
    assert task_name == "foto_senden"
    assert chat_id == 100
    assert resource_id == "med-xyz"
    assert inverse_call == 'photo DELETE /api/v1/photo/medien/med-xyz'
    assert sealed_at is None  # frisch, noch nicht versiegelt


def test_hochladen_receipt_dann_widerruf_delete_call(tmp_path):
    """AC4-Sequenz: Hochladen schreibt Receipt; Widerruf-Pfad ruft DELETE.

    Simuliert den vollständigen Upload → Widerruf-Zyklus.
    """
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    transport, calls = _transport_factory(medium_id="med-seq")
    photo_client = PhotoClient("http://127.0.0.1:5070", transport=transport)

    task = FotoSendenTask(
        tg=FakeTelegramMitDownload(),
        photo_client=photo_client,
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=_immer_mitglied,
        receipt_store=store,
    )

    # Schritt 1: hochladen
    ctx = _make_turn_context(chat_id=100)
    task.run({}, ctx)

    post_calls = [c for c in calls if c["method"] == "POST"]
    assert len(post_calls) == 1

    # Schritt 2: widerrufen (simuliert Vor-Agent-Hook ruft delete_medium)
    task.run({"aktion": "widerrufen", "id": "med-seq"}, ctx)

    delete_calls = [c for c in calls if c["method"] == "DELETE"]
    assert len(delete_calls) == 1
    assert "med-seq" in delete_calls[0]["path"]

    store.close()


def test_kein_receipt_bei_grenze_fehler(tmp_path):
    """Kein Receipt, wenn PHOTO-13 einen 4xx (Grenze) zurückgibt."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    transport, _ = _transport_factory(post_status=413, medium_id="ignored")
    photo_client = PhotoClient("http://127.0.0.1:5070", transport=transport)

    task = FotoSendenTask(
        tg=FakeTelegramMitDownload(),
        photo_client=photo_client,
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=_immer_mitglied,
        receipt_store=store,
    )
    task.run({}, _make_turn_context(chat_id=100))

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert rows == [], "Bei Grenze-Fehler darf kein Receipt geschrieben werden"


def test_kein_receipt_ohne_store(tmp_path):
    """Backward-Compat: receipt_store=None → kein Fehler, kein Receipt."""
    transport, calls = _transport_factory(medium_id="med-no-store")
    photo_client = PhotoClient("http://127.0.0.1:5070", transport=transport)

    task = FotoSendenTask(
        tg=FakeTelegramMitDownload(),
        photo_client=photo_client,
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=_immer_mitglied,
        receipt_store=None,  # kein Store
    )
    result = task.run({}, _make_turn_context(chat_id=100))

    # Kein Crash, Upload wurde trotzdem durchgeführt
    assert any(c["method"] == "POST" for c in calls)
    assert "med-no-store" in result


def test_kein_receipt_bei_widerruf_pfad(tmp_path):
    """Widerruf-Pfad schreibt keinen Receipt (nur Hochladen ist A2-Schreibakt)."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    transport, _ = _transport_factory()
    photo_client = PhotoClient("http://127.0.0.1:5070", transport=transport)

    task = FotoSendenTask(
        tg=FakeTelegramMitDownload(),
        photo_client=photo_client,
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=_immer_mitglied,
        receipt_store=store,
    )
    task.run({"aktion": "widerrufen", "id": "some-id"},
             _make_turn_context(chat_id=100))

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert rows == [], "Widerruf schreibt keinen Receipt"


def test_receipt_versiegelung_bei_zweitem_upload(tmp_path):
    """Zweiter Upload versiegelt den ersten Receipt desselben chat_id."""
    db_path = str(tmp_path / "test.db")
    store = A2ReceiptStore(db_path)

    # Zwei separate Transports für zwei Uploads mit unterschiedlichen IDs
    calls_all = []

    counter = {"n": 0}
    ids = ["med-first", "med-second"]

    def transport(method, path, *, body=None, content_type=None):
        calls_all.append({"method": method, "path": path})
        if method == "POST":
            idx = min(counter["n"], len(ids) - 1)
            counter["n"] += 1
            body = json.dumps({"id": ids[idx], "typ": "foto"}).encode("utf-8")
            return 200, body
        return 204, b""

    photo_client = PhotoClient("http://127.0.0.1:5070", transport=transport)
    task = FotoSendenTask(
        tg=FakeTelegramMitDownload(),
        photo_client=photo_client,
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=_immer_mitglied,
        receipt_store=store,
    )

    ctx = _make_turn_context(chat_id=100)
    task.run({}, ctx)
    task.run({}, ctx)

    conn = sqlite3.connect(db_path)
    rows = _receipts(conn)
    conn.close()
    store.close()

    assert len(rows) == 2
    assert rows[0][4] is not None, "Erster Receipt muss versiegelt sein"
    assert rows[1][4] is None, "Zweiter Receipt darf noch nicht versiegelt sein"
