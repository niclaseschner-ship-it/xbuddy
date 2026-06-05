"""Tests für die Orchestrierungs-Seite der Telemetrie — EC-23/E-EC-11
(Refs #268).

Geprüft wird:
- AC2: Antworten mit Provider-Call tragen den Suffix in der Sendung.
- AC3: Antworten OHNE Provider-Call (Bestätigungs-Quittung) tragen KEINEN.
- AC4: pro Provider-Call existiert eine Zeile in provider_calls.
- AC5: unbekanntes Modell → est_cost_eur=NULL, Suffix ohne €-Teil.
- R3: ProviderError persistiert Stub-Telemetrie, Provider-Down ohne Suffix.
- R7: History speichert OHNE Suffix.
"""

import sqlite3

from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, FakeWriteTask, make_message, task_call_response
from history import History
from main import _PROVIDER_DOWN, Context, handle_update
from model import GenerationResponse, ProviderError, ProviderUsage
from tasks import Catalog
from telemetry import TelemetryStore


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _ctx(tmp_path, tg, provider, catalog=None):
    """Context mit aktiver Telemetrie-Persistenz — alle Tests teilen denselben
    DB-Pfad, damit sie die DB nach handle_update auslesen können."""
    db_path = str(tmp_path / "orch.db")
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider,
        catalog=catalog if catalog is not None else Catalog(),
        history=History(db_path),
        pending=PendingStore(),
        telemetry_store=TelemetryStore(db_path))


def _response(text="Antwort.", model_id="claude-opus-4-7",
              input_tokens=500, output_tokens=700):
    return GenerationResponse(
        text=text, task_calls=[],
        usage=ProviderUsage(input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_read_tokens=0, cache_creation_tokens=0,
                            model_id=model_id))


# ============================================================
#  AC2 — Antworten mit Provider-Call tragen Telemetrie-Suffix
# ============================================================

def test_AC2_reply_with_provider_call_has_suffix(tmp_path):
    """AC2: nach einem Provider-Call hängt der Suffix an die Telegram-Sendung."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([_response(text="Hallo!", input_tokens=400,
                                       output_tokens=300)])
    ctx = _ctx(tmp_path, tg, provider)

    handle_update(make_message("hallo", from_user_id=7), ctx)

    assert len(tg.sent) == 1
    sent_text = tg.sent[0]["text"]
    # Originaltext steht drin.
    assert sent_text.startswith("Hallo!")
    # Suffix-Marker sind enthalten.
    assert "⏱" in sent_text
    assert "🪙" in sent_text
    # Token-Summe: 700 → 0.7k
    assert "0.7k tok" in sent_text


def test_AC2_proposal_carries_suffix(tmp_path):
    """R5: der Vorschlag hat einen Provider-Call hinter sich — Suffix dran."""
    write = FakeWriteTask(name="termin", summary="Termin eintragen",
                          result="erledigt")
    catalog = Catalog()
    catalog.register(write)
    tg = FakeTelegram(members=_members(7))
    resp = GenerationResponse(
        text="", task_calls=[task_call_response("termin").task_calls[0]],
        usage=ProviderUsage(input_tokens=200, output_tokens=50,
                            cache_read_tokens=0, cache_creation_tokens=0,
                            model_id="claude-opus-4-7"))
    provider = FakeProvider([resp])
    ctx = _ctx(tmp_path, tg, provider, catalog)

    handle_update(make_message("termin?", from_user_id=7), ctx)

    assert len(tg.sent) == 1
    sent_text = tg.sent[0]["text"]
    assert sent_text.startswith("Vorschlag")
    assert "⏱" in sent_text


# ============================================================
#  AC3 — Bestätigungs-Quittungen tragen KEINEN Suffix
# ============================================================

def test_AC3_confirmation_receipt_has_no_suffix(tmp_path):
    """AC3 + R5: nach Bestätigung läuft KEIN Provider-Call mehr — die Quittung
    trägt deshalb keinen Suffix. Der Suffix gehört zum Vorschlag (oben), nicht
    zur Quittung."""
    write = FakeWriteTask(name="termin", summary="Termin eintragen",
                          result="Termin eingetragen.")
    catalog = Catalog()
    catalog.register(write)
    tg = FakeTelegram(members=_members(7))
    # Erste Runde: Provider schlägt vor (mit Usage).
    resp = GenerationResponse(
        text="", task_calls=[task_call_response("termin").task_calls[0]],
        usage=ProviderUsage(input_tokens=100, output_tokens=20,
                            cache_read_tokens=0, cache_creation_tokens=0,
                            model_id="claude-opus-4-7"))
    provider = FakeProvider([resp])
    ctx = _ctx(tmp_path, tg, provider, catalog)

    # Schritt 1: Anfrage → Vorschlag (mit Suffix).
    handle_update(make_message("termin", message_id=100, from_user_id=7), ctx)
    proposal_msg_id = tg.sent[0]["message_id"]
    proposal_text = tg.sent[0]["text"]
    assert "⏱" in proposal_text   # Vorschlag trägt Suffix

    # Schritt 2: Bestätigung → Quittung OHNE Suffix.
    handle_update(make_message("👍", message_id=101, from_user_id=7,
                               reply_to_message_id=proposal_msg_id), ctx)
    receipt_text = tg.sent[-1]["text"]
    assert "Termin eingetragen." in receipt_text
    assert "⏱" not in receipt_text
    assert "🪙" not in receipt_text


# ============================================================
#  AC4 — provider_calls hat pro Provider-Call eine Zeile
# ============================================================

def test_AC4_provider_call_persisted_per_call(tmp_path):
    """AC4: ein erfolgreicher Provider-Call → eine Zeile in provider_calls."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([_response(input_tokens=400, output_tokens=600)])
    db_path = str(tmp_path / "orch.db")
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider, catalog=Catalog(),
        history=History(db_path), pending=PendingStore(),
        telemetry_store=TelemetryStore(db_path))

    handle_update(make_message("hallo", from_user_id=7), ctx)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT model_id, input_tokens, output_tokens, est_cost_eur "
        "FROM provider_calls").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "claude-opus-4-7"
    assert rows[0][1] == 400
    assert rows[0][2] == 600
    assert rows[0][3] is not None   # bekanntes Modell → Kosten gesetzt


def test_AC4_no_persistence_for_confirmation_receipt(tmp_path):
    """AC3+AC4: eine Bestätigungs-Quittung schreibt keinen provider_calls-
    Eintrag — sie hat keinen Provider-Call hinter sich."""
    write = FakeWriteTask(name="termin", summary="x", result="ok")
    catalog = Catalog()
    catalog.register(write)
    tg = FakeTelegram(members=_members(7))
    resp = GenerationResponse(
        text="", task_calls=[task_call_response("termin").task_calls[0]],
        usage=ProviderUsage(input_tokens=10, output_tokens=10,
                            cache_read_tokens=0, cache_creation_tokens=0,
                            model_id="claude-opus-4-7"))
    provider = FakeProvider([resp])
    db_path = str(tmp_path / "orch.db")
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider, catalog=catalog,
        history=History(db_path), pending=PendingStore(),
        telemetry_store=TelemetryStore(db_path))

    # Vorschlag (Provider-Call).
    handle_update(make_message("x", message_id=100, from_user_id=7), ctx)
    proposal_msg_id = tg.sent[0]["message_id"]
    # Bestätigung (kein Provider-Call).
    handle_update(make_message("ok", message_id=101, from_user_id=7,
                               reply_to_message_id=proposal_msg_id), ctx)

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM provider_calls").fetchone()[0]
    conn.close()
    # Genau eine Zeile — die vom Vorschlag.
    assert count == 1


# ============================================================
#  AC5 — Unbekanntes Modell → est_cost_eur NULL, Suffix ohne €
# ============================================================

def test_AC5_unknown_model_persists_null_cost_and_omits_euro_suffix(tmp_path):
    """AC5: ein unbekanntes Modell führt zu est_cost_eur=NULL in der DB
    und einem Suffix OHNE €-Teil in der Sendung."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([_response(model_id="experimental-future-model",
                                       input_tokens=100, output_tokens=200)])
    db_path = str(tmp_path / "orch.db")
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider, catalog=Catalog(),
        history=History(db_path), pending=PendingStore(),
        telemetry_store=TelemetryStore(db_path))

    handle_update(make_message("hallo", from_user_id=7), ctx)

    # DB: est_cost_eur ist NULL.
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT est_cost_eur, model_id FROM provider_calls"
    ).fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] == "experimental-future-model"

    # Suffix in der Sendung enthält Wall-Clock + Tokens, aber kein €.
    sent_text = tg.sent[0]["text"]
    assert "⏱" in sent_text
    assert "🪙" in sent_text
    assert "€" not in sent_text


# ============================================================
#  R3 — ProviderError: Stub-Telemetrie persistieren, Provider-Down ohne Suffix
# ============================================================

def test_R3_provider_error_persists_stub_and_sends_clean_provider_down(tmp_path):
    """R3: bei ProviderError landet ein Stub-Call in provider_calls (für
    spätere Diagnose) UND die Provider-Down-Nachricht trägt KEINEN Suffix
    (kein Call ist erfolgreich durchgekommen)."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([ProviderError("Zeitüberschreitung")])
    db_path = str(tmp_path / "orch.db")
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider, catalog=Catalog(),
        history=History(db_path), pending=PendingStore(),
        telemetry_store=TelemetryStore(db_path))

    handle_update(make_message("hallo", from_user_id=7), ctx)

    # Provider-Down-Hinweis ohne Suffix.
    assert tg.sent[0]["text"] == _PROVIDER_DOWN
    assert "⏱" not in tg.sent[0]["text"]

    # Stub-Telemetrie liegt in der DB.
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT input_tokens, output_tokens, est_cost_eur "
        "FROM provider_calls").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == 0
    assert rows[0][1] == 0
    assert rows[0][2] is None


# ============================================================
#  R7 — History speichert OHNE Suffix
# ============================================================

def test_R7_history_stores_original_text_without_suffix(tmp_path):
    """R7: Folge-Turns dürfen die Telemetrie nicht als »Bot-Wortlaut« sehen —
    die History speichert deshalb den Originaltext OHNE Suffix."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([_response(text="Hallo!", input_tokens=100,
                                       output_tokens=200)])
    db_path = str(tmp_path / "orch.db")
    history = History(db_path)
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider, catalog=Catalog(),
        history=history, pending=PendingStore(),
        telemetry_store=TelemetryStore(db_path))

    handle_update(make_message("hallo", chat_id=42, from_user_id=7), ctx)

    # In der Sendung steht der Suffix.
    assert "⏱" in tg.sent[0]["text"]
    # In der History steht er NICHT.
    loaded = history.load(42, 20)
    assistant = [m for m in loaded if m.role == "assistant"]
    assert len(assistant) == 1
    assert assistant[0].blocks[0].text == "Hallo!"
    assert "⏱" not in assistant[0].blocks[0].text
