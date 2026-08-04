"""Pre-Flight-Tests für den EC-36 Korrektur-Hook (#844).

Prüft den `_falsch_hook` in main.py isoliert (ohne Agent-Loop):

1. A2-Pfad foto_senden: »falsch« nach erfolgreichem foto_senden-Akt löst
   HTTP DELETE auf den Photo-Buddy-Endpunkt aus, Receipt wird sealed,
   Quittung positiv, Korrektur-State gesetzt (AC2/AC6).
2. A2-Pfad einkauf_hinzufuegen Multi-Item: »falsch« nach 3-Item-Akt löst
   DELETE pro item_id aus, alle Receipts sealed (AC2/AC6).
3. Klasse-C-Pfad: »falsch« nach Pending-Vorschlag verwirft PendingStore,
   Quittung „Vorschlag verworfen", Korrektur-State gesetzt (AC1/AC6).
4. Ambiguitäts-Pfad: DELETE liefert 404 → Ambiguitäts-Quittung, Receipt
   wird trotzdem sealed (EC-10 spec Z. 586-597).
5. Trivialer Fall: »falsch« ohne Receipt + ohne Pending → Hook gibt False
   zurück, kein Send, kein State.
6. 3-fach-Iteration: »falsch« → Patch → »ja« → erneut »falsch« usw. — der
   Hook bleibt nach jeder Iteration ohne Vorgänger-Bon (sealed_at).

AC1: write_verification — Pre-Flight `test_a2_receipt_sealed` zeigt, dass
nach `_falsch_hook` jeder vorher unsealed Receipt sealed_at != NULL hat.
"""

import sqlite3

import main
from a2_receipt_store import A2ReceiptStore
from confirm import PendingProposal, PendingStore
from fakes import FakeTelegram, make_message
from history import History
from tasks import Catalog

# ============================================================
#  Helfer
# ============================================================


def _ctx(tmp_path, tg, *, a2_receipt_store=None, photo_origin=None,
         essen_origin=None, pending=None):
    """Baut einen minimalen Context mit den EC-36-Feldern."""
    return main.Context(
        tg=tg,
        bot_username="mybot",
        family_group_chat_id="-100",
        context_depth=20,
        provider=None,
        catalog=Catalog(),
        history=History(str(tmp_path / "k.db")),
        pending=pending or PendingStore(),
        a2_receipt_store=a2_receipt_store,
        photo_origin_url=photo_origin or "",
        essen_origin_url=essen_origin or "",
    )


class _StubHTTP:
    """Sammelt _http_delete-Aufrufe und liefert skriptierte Status-Codes.

    CLIENT-1-Naht: wird per `http_delete=`-Parameter direkt in
    `_falsch_hook` injiziert (kein monkeypatch). Signatur identisch zum
    Modul-Level `_http_delete(origin_url, api_path)`.
    """

    def __init__(self, statuses=None):
        # Default: alle Aufrufe sauberes 200
        self._statuses = list(statuses or [])
        self.calls = []   # [(origin, path), …]

    def __call__(self, origin_url, api_path, timeout=2.0):
        self.calls.append((origin_url, api_path))
        if self._statuses:
            return self._statuses.pop(0), b""
        return 200, b""


def _all_sealed(db_path, chat_id):
    """True, wenn alle Receipts des chat_id sealed_at != NULL haben."""
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "SELECT sealed_at FROM a2_receipts WHERE chat_id = ?",
        (int(chat_id),))
    rows = cur.fetchall()
    conn.close()
    return rows and all(r[0] is not None for r in rows)


# ============================================================
#  Pre-Flight 1 — A2 foto_senden
# ============================================================


def test_falsch_a2_foto_senden_dispatcht_photo_delete(tmp_path):
    """»falsch« nach foto_senden-A2-Akt → HTTP DELETE auf photo-Endpoint,
    Receipt sealed, positive Quittung, Korrektur-State gesetzt (AC1/AC2/AC6).

    CLIENT-1-Naht: http_delete-Stub direkt eingereicht (kein monkeypatch).
    """
    db_path = str(tmp_path / "rec.db")
    store = A2ReceiptStore(db_path)
    chat_id = 42
    store.insert("foto_senden", chat_id, "med-42",
                 'photo DELETE /api/v1/photo/medien/med-42')

    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, a2_receipt_store=store,
               photo_origin="http://127.0.0.1:5070")

    http = _StubHTTP(statuses=[200])

    handled = main._falsch_hook(make_message("falsch", chat_id=chat_id,
                                             from_user_id=7), ctx,
                                http_delete=http)

    assert handled is True
    # Genau ein DELETE-Call auf den Photo-Endpunkt
    assert http.calls == [
        ("http://127.0.0.1:5070", "/api/v1/photo/medien/med-42")]
    # Positive Quittung + Folge-Frage
    assert len(tg.sent) == 1
    assert "rückgängig" in tg.sent[0]["text"].lower()
    assert "was war falsch" in tg.sent[0]["text"].lower()
    # Receipt sealed (AC1 Pre-Flight)
    store.close()
    assert _all_sealed(db_path, chat_id)
    # Korrektur-State gesetzt
    state = ctx.pending.get_correction(chat_id)
    assert state is not None
    assert state.last_skill == "foto_senden"
    assert state.quelle == "a2"


def test_falsch_a2_receipt_sealed(tmp_path):
    """AC1 write_verification: nach `falsch`-Verarbeitung sind alle vorher
    unversiegelten Receipts der chat_id sealed."""
    db_path = str(tmp_path / "rec.db")
    store = A2ReceiptStore(db_path)
    chat_id = 99
    store.insert("foto_senden", chat_id, "med-1",
                 'photo DELETE /api/v1/photo/medien/med-1')

    # Pre-Condition
    assert len(store.fetch_unsealed_for_chat(chat_id)) == 1

    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, a2_receipt_store=store,
               photo_origin="http://127.0.0.1:5070")

    main._falsch_hook(make_message("falsch", chat_id=chat_id, from_user_id=7),
                      ctx, http_delete=_StubHTTP(statuses=[200]))

    # Post-Condition: keine unversiegelten Receipts mehr
    assert store.fetch_unsealed_for_chat(chat_id) == []
    store.close()


# ============================================================
#  Pre-Flight 2 — A2 einkauf_hinzufuegen Multi-Item
# ============================================================


def test_falsch_a2_einkauf_multi_item_dispatcht_delete_pro_item(tmp_path):
    """Multi-Item-A2: 3 Receipts → 3 DELETE-Aufrufe; alle sealed.

    Bestätigt EC-10 spec Z. 543-548 (eine Receipt-Zeile pro Ressource) im
    Korrektur-Hook-Pfad: jeder Bon löst einen eigenen Inverse-Call aus.
    """
    db_path = str(tmp_path / "rec.db")
    store = A2ReceiptStore(db_path)
    chat_id = 55
    items = [
        ("item-a", 'essen DELETE /api/v1/essen/wuensche/item-a'),
        ("item-b", 'essen DELETE /api/v1/essen/wuensche/item-b'),
        ("item-c", 'essen DELETE /api/v1/essen/wuensche/item-c'),
    ]
    store.insert_many("einkauf_hinzufuegen", chat_id, items)

    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, a2_receipt_store=store,
               essen_origin="http://127.0.0.1:5052")

    http = _StubHTTP(statuses=[200, 200, 200])

    handled = main._falsch_hook(
        make_message("falsch", chat_id=chat_id, from_user_id=7), ctx,
        http_delete=http)

    assert handled is True
    # 3 DELETE-Calls — pro item_id einer
    assert http.calls == [
        ("http://127.0.0.1:5052", "/api/v1/essen/wuensche/item-a"),
        ("http://127.0.0.1:5052", "/api/v1/essen/wuensche/item-b"),
        ("http://127.0.0.1:5052", "/api/v1/essen/wuensche/item-c"),
    ]
    # Alle Receipts sealed
    store.close()
    assert _all_sealed(db_path, chat_id)
    # Korrektur-State zeigt auf einkauf_hinzufuegen (letzter Receipt)
    state = ctx.pending.get_correction(chat_id)
    assert state.last_skill == "einkauf_hinzufuegen"


# ============================================================
#  Pre-Flight 3 — Klasse-C-Pfad
# ============================================================


def test_falsch_klasse_c_verwirft_pending_vorschlag(tmp_path):
    """»falsch« nach Klasse-C-Vorschlag → PendingStore.take() entfernt den
    Vorschlag, Quittung „Vorschlag verworfen", Korrektur-State gesetzt."""
    chat_id = 33
    pending = PendingStore()
    pending.add(PendingProposal(
        chat_id=chat_id, proposal_message_id=200,
        task_name="gericht_anlegen",
        arguments={"label": "Pizza"}))

    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, pending=pending)

    handled = main._falsch_hook(
        make_message("falsch", chat_id=chat_id, from_user_id=7), ctx)

    assert handled is True
    # Pending leer
    assert pending.open_count(chat_id) == 0
    # Quittung
    assert len(tg.sent) == 1
    assert "vorschlag verworfen" in tg.sent[0]["text"].lower()
    assert "was war falsch" in tg.sent[0]["text"].lower()
    # Korrektur-State trägt Original-Skill + Args
    state = pending.get_correction(chat_id)
    assert state is not None
    assert state.last_skill == "gericht_anlegen"
    assert state.last_args == {"label": "Pizza"}
    assert state.quelle == "klasse_c"


# ============================================================
#  Pre-Flight 4 — Ambiguitäts-Pfad (EC-10 spec Z. 586-597)
# ============================================================


def test_falsch_a2_404_quittiert_ambivalent_aber_sealt_trotzdem(tmp_path):
    """DELETE liefert 404 (Ressource verändert/weg) → Ambiguitäts-Quittung,
    Receipt trotzdem sealed (kein zweiter Versuch auf denselben Bon)."""
    db_path = str(tmp_path / "rec.db")
    store = A2ReceiptStore(db_path)
    chat_id = 77
    store.insert("foto_senden", chat_id, "med-x",
                 'photo DELETE /api/v1/photo/medien/med-x')

    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, a2_receipt_store=store,
               photo_origin="http://127.0.0.1:5070")

    handled = main._falsch_hook(
        make_message("falsch", chat_id=chat_id, from_user_id=7), ctx,
        http_delete=_StubHTTP(statuses=[404]))

    assert handled is True
    # Ambiguitäts-Quittung
    assert "zweifelsfrei zurücknehmen" in tg.sent[0]["text"].lower()
    # Receipt trotzdem sealed
    store.close()
    assert _all_sealed(db_path, chat_id)


# ============================================================
#  Pre-Flight 5 — Trivial: kein Receipt, kein Pending
# ============================================================


def test_falsch_ohne_receipt_und_ohne_pending_ist_no_op(tmp_path):
    """»falsch« ohne Vorgänger → Hook gibt False zurück, kein Send, kein State.

    Der Hook reicht den Turn an den Agenten weiter — »falsch« kann normaler
    Gesprächstext sein (z. B. »falsch geparkt«).
    """
    db_path = str(tmp_path / "rec.db")
    store = A2ReceiptStore(db_path)   # leer
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, a2_receipt_store=store)

    handled = main._falsch_hook(
        make_message("falsch", chat_id=42, from_user_id=7), ctx)

    assert handled is False
    assert tg.sent == []
    assert ctx.pending.get_correction(42) is None
    store.close()


# ============================================================
#  Pre-Flight 6 — 3-fach-Iteration
# ============================================================


def test_falsch_dreifach_iteration_jedesmal_nur_letzter_bon_greift(tmp_path):
    """»falsch« → Patch → neuer A2-Akt → »falsch« → ...: jede Iteration siegelt
    den vorigen Bon (insert() versiegelt vor Insert), der Hook greift nur auf
    den neuen unversiegelten Bon zu. Belegt: dreifache Korrektur-Sequenz ohne
    Vorgänger-Bon-Verbrennung."""
    db_path = str(tmp_path / "rec.db")
    store = A2ReceiptStore(db_path)
    chat_id = 88
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, a2_receipt_store=store,
               photo_origin="http://127.0.0.1:5070")

    http = _StubHTTP(statuses=[200, 200, 200])

    for n, med_id in enumerate(("med-1", "med-2", "med-3"), start=1):
        # Neuer A2-Akt simuliert (insert siegelt automatisch vorigen)
        store.insert("foto_senden", chat_id, med_id,
                     'photo DELETE /api/v1/photo/medien/%s' % med_id)
        # Nach jedem insert: nur 1 unsealed (insert siegelt vorigen)
        assert len(store.fetch_unsealed_for_chat(chat_id)) == 1

        # Hook löst »falsch« aus
        handled = main._falsch_hook(
            make_message("falsch", chat_id=chat_id, from_user_id=7,
                         message_id=1000 + n), ctx, http_delete=http)
        assert handled is True

    # Drei DELETE-Calls, je einer pro Iteration
    assert [c[1] for c in http.calls] == [
        "/api/v1/photo/medien/med-1",
        "/api/v1/photo/medien/med-2",
        "/api/v1/photo/medien/med-3",
    ]
    # Alle drei Receipts sealed
    store.close()
    assert _all_sealed(db_path, chat_id)


# ============================================================
#  Wortmatch _is_falsch_wort
# ============================================================


def test_is_falsch_wort_matched_nur_ganzes_wort():
    """»falsch« case-insensitiv, getrimmt — Teilstrings zählen nicht."""
    assert main._is_falsch_wort("falsch") is True
    assert main._is_falsch_wort("Falsch") is True
    assert main._is_falsch_wort("  FALSCH  ") is True
    assert main._is_falsch_wort("falschen") is False
    assert main._is_falsch_wort("ist falsch") is False
    assert main._is_falsch_wort("") is False
    assert main._is_falsch_wort(None) is False


# ============================================================
#  CLIENT-1 Test-Naht — _http_delete(transport=)
# ============================================================


def test_http_delete_nutzt_transport_stub_statt_urllib():
    """CLIENT-1 (conventions/http-client.md): _http_delete akzeptiert einen
    optionalen `transport=`-Callable. Wird er übergeben, ruft die Funktion
    NICHT urllib auf, sondern den Stub mit `(url, timeout)`.

    Belegt die saubere Test-Naht ohne monkeypatch — Geschwister-Naht zu
    den FamilieClient/GeraeteClient-Tests, die denselben Vertrag tragen.
    """
    calls = []

    def stub_transport(url, timeout):
        calls.append((url, timeout))
        return 204, b""

    status, body = main._http_delete(
        "http://127.0.0.1:5052", "/api/v1/essen/wuensche/item-x",
        timeout=1.5, transport=stub_transport)

    assert status == 204
    assert body == b""
    assert calls == [("http://127.0.0.1:5052/api/v1/essen/wuensche/item-x", 1.5)]


def test_http_delete_default_transport_kein_call_an_stub():
    """Negativ-Probe: ohne transport=-Parameter läuft der Default-Pfad
    (urllib). Wir verifizieren das indirekt — der Aufruf landet bei einem
    nicht erreichbaren Loopback-Port und liefert (0, b"") (URLError-Schluck)."""
    # Port 1 ist privilegiert + nicht gebunden — connect schlägt sofort fehl
    status, body = main._http_delete(
        "http://127.0.0.1:1", "/api/v1/x", timeout=0.1)
    assert status == 0
    assert body == b""
