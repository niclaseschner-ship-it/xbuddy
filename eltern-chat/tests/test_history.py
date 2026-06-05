"""Tests für den Gesprächsverlauf — EC-6/EC-16, E-EC-8 (Refs #27).

#310: Tool-Turns (Task-Aufrufe/-Ergebnisse) gehören zum EC-6-Kontext und werden
mitpersistiert; das depth-Fenster darf kein halbes Tool-Paar schneiden.
"""

from history import History
from model import ImageBlock, Message, TaskCallBlock, TaskResultBlock, TextBlock


def test_EC_16_missing_db_is_created_empty(tmp_path):
    """Fehlt die DB-Datei, wird sie leer angelegt — kein Abbruch."""
    db = tmp_path / "neu.db"
    assert not db.exists()
    hist = History(str(db))
    assert db.exists()
    assert hist.load("chat-1", 20) == []
    hist.close()


def test_EC_6_append_and_load_roundtrip(tmp_path):
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [TextBlock("hallo")]))
    hist.append("chat-1", Message("assistant", [TextBlock("hallo zurück")]))
    loaded = hist.load("chat-1", 20)
    assert [m.role for m in loaded] == ["user", "assistant"]
    assert loaded[0].blocks[0].text == "hallo"
    hist.close()


def test_EC_6_context_is_separated_per_chat(tmp_path):
    """Der Kontext ist je Telegram-Chat getrennt — kein geteilter Verlauf."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("gruppe", Message("user", [TextBlock("Gruppen-Nachricht")]))
    hist.append("privat", Message("user", [TextBlock("Privat-Nachricht")]))
    assert len(hist.load("gruppe", 20)) == 1
    assert hist.load("gruppe", 20)[0].blocks[0].text == "Gruppen-Nachricht"
    assert hist.load("privat", 20)[0].blocks[0].text == "Privat-Nachricht"
    hist.close()


def test_EC_6_depth_limits_loaded_messages(tmp_path):
    hist = History(str(tmp_path / "c.db"))
    for i in range(10):
        hist.append("chat-1", Message("user", [TextBlock("nr %d" % i)]))
    loaded = hist.load("chat-1", 3)
    # die letzten 3, chronologisch
    assert [b.blocks[0].text for b in loaded] == ["nr 7", "nr 8", "nr 9"]
    hist.close()


def test_EC_6_survives_restart(tmp_path):
    """E-EC-8: der Verlauf übersteht einen Neustart der Instanz."""
    db = str(tmp_path / "persist.db")
    hist = History(db)
    hist.append("chat-1", Message("user", [TextBlock("vor dem Neustart")]))
    hist.close()

    # frische Instanz auf derselben Datei
    hist2 = History(db)
    loaded = hist2.load("chat-1", 20)
    assert len(loaded) == 1
    assert loaded[0].blocks[0].text == "vor dem Neustart"
    hist2.close()


def test_EC_6_images_are_persisted(tmp_path):
    """»das Bild von eben« — Bilder gehören in den Verlauf."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [
        TextBlock("schau mal"), ImageBlock("image/jpeg", "QUJD")]))
    loaded = hist.load("chat-1", 20)
    blocks = loaded[0].blocks
    assert isinstance(blocks[1], ImageBlock)
    assert blocks[1].data_b64 == "QUJD"
    hist.close()


# ============================================================
#  #310 — Tool-Turns persistieren + Paar-Schutz beim depth-Schnitt
# ============================================================

def test_issue_310_task_blocks_roundtrip(tmp_path):
    """AC1: ein Tool-Paar (Assistant-TaskCallBlock + User-TaskResultBlock)
    übersteht Persist+Reload mit allen Feldern — call_id verknüpft beide."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [TextBlock("welche Termine?")]))
    hist.append("chat-1", Message("assistant", [
        TextBlock("Ich schaue nach."),
        TaskCallBlock(call_id="c-1", task="termine_erfragen",
                      arguments={"ab": "heute", "tage": 7})]))
    hist.append("chat-1", Message("user", [
        TaskResultBlock(call_id="c-1", content="2 Termine", is_error=False)]))
    hist.append("chat-1", Message("assistant", [TextBlock("Du hast 2 Termine.")]))

    loaded = hist.load("chat-1", 20)
    assert [m.role for m in loaded] == ["user", "assistant", "user", "assistant"]

    call = loaded[1].blocks[1]
    assert isinstance(call, TaskCallBlock)
    assert call.call_id == "c-1"
    assert call.task == "termine_erfragen"
    assert call.arguments == {"ab": "heute", "tage": 7}

    res = loaded[2].blocks[0]
    assert isinstance(res, TaskResultBlock)
    assert res.call_id == "c-1"
    assert res.content == "2 Termine"
    assert res.is_error is False
    hist.close()


def test_issue_310_error_result_roundtrip(tmp_path):
    """AC1: auch ein Fehler-Ergebnis (is_error=True) behält beim Reload sein
    Flag. Geprüft über ein vollständiges Paar in der Fenster-Mitte (eine
    user-Message mit TaskResultBlock an der KANTE würde sonst der Paar-Schutz
    verwerfen)."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [TextBlock("mach was Unmögliches")]))
    hist.append("chat-1", Message("assistant", [
        TaskCallBlock(call_id="c-9", task="t", arguments={})]))
    hist.append("chat-1", Message("user", [
        TaskResultBlock(call_id="c-9", content="ging nicht", is_error=True)]))
    hist.append("chat-1", Message("assistant", [TextBlock("Tut mir leid.")]))

    loaded = hist.load("chat-1", 20)
    res = loaded[2].blocks[0]
    assert isinstance(res, TaskResultBlock)
    assert res.call_id == "c-9"
    assert res.content == "ging nicht"
    assert res.is_error is True
    hist.close()


def test_issue_310_unknown_kind_is_skipped(tmp_path):
    """Vorwärtskompatibilität: ein unbekannter Block-`kind` aus einer neueren
    Schema-Version wird beim Reload still übersprungen, nicht zum Crash."""
    import json
    db = str(tmp_path / "fwd.db")
    hist = History(db)
    hist.append("chat-1", Message("assistant", [TextBlock("ok")]))
    # Direkt einen Eintrag mit unbekanntem kind in die DB schreiben.
    conn = __import__("sqlite3").connect(db)
    conn.execute(
        "INSERT INTO messages (chat_id, seq, role, blocks) VALUES (?,?,?,?)",
        ("chat-1", 2, "assistant",
         json.dumps([{"kind": "text", "text": "sichtbar"},
                     {"kind": "kommt_erst_2027", "foo": "bar"}])))
    conn.commit()
    conn.close()
    loaded = hist.load("chat-1", 20)
    assert loaded[-1].blocks[0].text == "sichtbar"
    assert len(loaded[-1].blocks) == 1   # unbekannter Block fiel weg
    hist.close()


def test_issue_310_depth_drops_leading_half_pair(tmp_path):
    """AC4 (führende Kante): schneidet das depth-Fenster mitten in ein Tool-Paar,
    sodass die erste geladene Message ein TaskResultBlock (user) ohne den
    zugehörigen Aufruf ist, wird sie verworfen — sonst Anthropic-400."""
    hist = History(str(tmp_path / "c.db"))
    # seq 1: assistant tool_use | seq 2: user tool_result | seq 3: assistant text
    hist.append("chat-1", Message("assistant", [
        TaskCallBlock(call_id="c-1", task="t", arguments={})]))
    hist.append("chat-1", Message("user", [
        TaskResultBlock(call_id="c-1", content="r", is_error=False)]))
    hist.append("chat-1", Message("assistant", [TextBlock("fertig")]))

    # depth=2 lädt seq 2+3 → erste Message ist das halbe tool_result.
    loaded = hist.load("chat-1", 2)
    assert [m.role for m in loaded] == ["assistant"]
    assert loaded[0].blocks[0].text == "fertig"
    hist.close()


def test_issue_310_depth_drops_trailing_half_pair(tmp_path):
    """AC4 (abschließende Kante): endet das depth-Fenster mit einem
    Assistant-TaskCallBlock, dessen tool_result nicht mehr ins Fenster passt,
    wird die Assistant-Message verworfen — sonst Anthropic-400."""
    hist = History(str(tmp_path / "c.db"))
    # seq 1: user text | seq 2: assistant tool_use | seq 3: user tool_result
    hist.append("chat-1", Message("user", [TextBlock("frag")]))
    hist.append("chat-1", Message("assistant", [
        TaskCallBlock(call_id="c-1", task="t", arguments={})]))
    hist.append("chat-1", Message("user", [
        TaskResultBlock(call_id="c-1", content="r", is_error=False)]))

    # depth=2 lädt seq 2+3, ABER seq 2 (tool_use) + seq 3 (tool_result) ist ein
    # vollständiges Paar im Fenster — keine Kante schneidet. Stattdessen depth=2
    # ab einer anderen Last prüfen: tool_use als LETZTE.
    hist.append("chat-1", Message("assistant", [
        TaskCallBlock(call_id="c-2", task="t", arguments={})]))
    # Jetzt: …, seq 3 user tool_result, seq 4 assistant tool_use(c-2, offen).
    loaded = hist.load("chat-1", 2)   # seq 3 + seq 4
    # seq 3 (user tool_result c-1) ist führendes halbes Paar → weg;
    # seq 4 (assistant tool_use c-2) ist abschließendes halbes Paar → weg.
    assert loaded == []
    hist.close()


def test_issue_310_complete_pair_in_window_is_kept(tmp_path):
    """AC4: liegt ein vollständiges Paar im Fenster, bleibt es unangetastet —
    der Paar-Schutz greift nur bei UNPAARIGEN Blöcken, nie bei vollständigen."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [TextBlock("frag")]))
    hist.append("chat-1", Message("assistant", [
        TaskCallBlock(call_id="c-1", task="t", arguments={})]))
    hist.append("chat-1", Message("user", [
        TaskResultBlock(call_id="c-1", content="r", is_error=False)]))
    hist.append("chat-1", Message("assistant", [TextBlock("fertig")]))

    loaded = hist.load("chat-1", 20)
    assert [m.role for m in loaded] == ["user", "assistant", "user", "assistant"]
    assert isinstance(loaded[1].blocks[0], TaskCallBlock)
    assert isinstance(loaded[2].blocks[0], TaskResultBlock)
    hist.close()


def test_issue_310_drops_mid_window_unpaired_tool_use(tmp_path):
    """AC-FIX2 (T310-S3): ein unpaariges tool_use MITTEN im Fenster (nicht an
    der Kante) wird beim Laden verworfen. Das ist genau der T310-S2-W-Befund:
    der frühe WRITE-Vorschlag persistierte `[user, assistant(tool_use),
    assistant(text)]` mit einem unpaarigen tool_use in der Mitte; der
    Kanten-only-Schutz übersah ihn → Anthropic-400 im Folge-Turn. Jetzt
    überlebt der unpaarige Block an KEINER Position."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [TextBlock("trag Termin ein")]))
    # tool_use OHNE folgendes tool_result (Vorschlag aus der Zeit vor T310-S3).
    hist.append("chat-1", Message("assistant", [
        TaskCallBlock(call_id="c-7", task="termin", arguments={})]))
    hist.append("chat-1", Message("assistant", [TextBlock("Soll ich das so eintragen?")]))

    loaded = hist.load("chat-1", 20)
    # Das mittige unpaarige tool_use ist weg; seine Assistant-Message war nur
    # dieser Block → ganz weggelassen. Kein TaskCallBlock überlebt.
    for m in loaded:
        for b in m.blocks:
            assert not isinstance(b, TaskCallBlock)
    assert [m.role for m in loaded] == ["user", "assistant"]
    assert loaded[0].blocks[0].text == "trag Termin ein"
    assert loaded[1].blocks[0].text == "Soll ich das so eintragen?"
    hist.close()
