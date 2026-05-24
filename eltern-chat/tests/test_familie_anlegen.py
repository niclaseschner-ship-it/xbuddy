"""Tests für »Familie anlegen« — FAA-1…FAA-11 (Refs #60).

Mindest-Abdeckung nach `specs/platform/familie-anlegen.md` FAA-11. Telegram
wird durch eine kontrollierte Doppelung ersetzt (Pattern wie ONB-9): die
FakeTelegram aus `fakes.py` plus eine schmale Subklasse mit `download_file`
für FAA-6. Auch der Eingabe-Strom wird über eine kleine Doppelung
nachgebildet — `familie_anlegen` ruft `next_message()` solange auf, bis das
Skript leer ist.
"""

import json
import os
import struct
import zlib

import pytest

# Familien-Registry wird vom Modul direkt importiert; um plan/familie an den
# Importpfad zu bringen, reicht das was eltern-chat/familie_anlegen.py tut.
import familie_anlegen as fa
from familie import registry as registry_mod
from familie_anlegen import (CANCELLED, DONE_MULTI, DONE_SINGLE, FaaInput,
                              NOT_AUTHORIZED, REJECT_FOTO_GROSS,
                              REJECT_FOTO_MIME, REJECT_KIND, REJECT_NAME,
                              REJECT_RING, REJECT_TELEGRAM_DUP, WRITE_FAILED,
                              familie_anlegen)
from fakes import FakeTelegram


# ============================================================
#  Test-Doppelungen — schlanke Eingabe-Strom + FakeTelegram + download
# ============================================================

class FakeTelegramFA(FakeTelegram):
    """FakeTelegram + `download_file` (FAA-6).

    `downloads` ist ein dict file_id -> bytes. Tests skripten so, was hinter
    welcher Telegram-file_id liegt — ohne Netz.
    """

    def __init__(self, members=None, downloads=None):
        super().__init__(members=members)
        self.downloads = dict(downloads or {})

    def download_file(self, file_id):
        if file_id not in self.downloads:
            raise AssertionError("download_file: kein Skript für %r" % file_id)
        return self.downloads[file_id]


def stream(*items):
    """Baut eine `next_message`-Funktion aus einer Folge von FaaInput/Strings.

    Strings sind eine Kurzform für `FaaInput(text=string)`. Wird die Folge
    erschöpft, liefert `next_message()` `None` — dann gilt der Aufruf als
    abgebrochen (siehe Funktions-Vertrag im Modul).
    """
    box = list(items)

    def next_message():
        if not box:
            return None
        item = box.pop(0)
        if isinstance(item, str):
            return FaaInput(text=item)
        return item
    return next_message


def _png_bytes(w=1, h=1):
    """Ein gültiges PNG der gewünschten Größe (für FAA-6-Größen-Prüfung)."""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    raw = b"\x00" * h + b"\x00\x00\x00\x00" * w * h
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _registry_path(tmp_path, settings=None):
    """Legt eine leere familie.json (mit optionalem settings-Block) an."""
    path = tmp_path / "familie.json"
    payload = {"erwachsene": [], "kinder": []}
    if settings is not None:
        payload["settings"] = settings
    path.write_text(json.dumps(payload))
    return str(path)


def _member_tg(downloads=None):
    """FakeTelegramFA, in dem der Test-Aufrufer 7 Mitglied der Familien-Gruppe
    ist (FAA-2)."""
    return FakeTelegramFA(members={7: {"status": "member"}},
                          downloads=downloads or {})


# ============================================================
#  FAA-1 — Aufruf-Schnittstelle
# ============================================================

def test_FAA_1_returns_list_of_ids_for_single_person(tmp_path):
    """FAA-1: ein Durchlauf mit genau einer Person liefert eine Liste mit der
    vergebenen `id`."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene",     # Art
        "Niclas",         # Name
        "überspringen",   # Foto
        "ok",             # Ring (Vorschlag übernehmen)
        "überspringen",   # E-Mail
        "überspringen",   # Telegram-ID
        "ok",             # Bestätigung (FAA-7)
        "nein",           # Noch jemand? (FAA-9 → Ende)
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.authorized is True
    assert res.vergebene_ids == ["niclas"]


def test_FAA_1_returns_empty_list_on_immediate_cancel(tmp_path):
    """FAA-1: sofortiger Abbruch bei der Bestätigung der ersten Person → leere
    Liste."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "kind", "Paula", "überspringen", "ok", "überspringen",
        "nein, doch nicht",   # FAA-7: nicht-bestätigende Antwort
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == []
    # `familie.json` wurde nicht angefasst.
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"] == [] and data["kinder"] == []


def test_FAA_1_multiple_persons_in_one_call(tmp_path):
    """FAA-1/FAA-9: zwei Personen im selben Aufruf → zwei `id`s im Ergebnis."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        # Person 1
        "erwachsene", "Niclas", "überspringen", "ok", "überspringen",
        "überspringen", "ok",
        "ja",  # noch jemand?
        # Person 2
        "kind", "Paula", "überspringen", "ok", "überspringen", "ok",
        "nein",  # Ende
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas", "paula"]
    data = json.loads(open(reg_path).read())
    assert [p["id"] for p in data["erwachsene"]] == ["niclas"]
    assert [p["id"] for p in data["kinder"]] == ["paula"]


# ============================================================
#  FAA-2 — Berechtigung live über die Familien-Gruppen-Mitgliedschaft
# ============================================================

def test_FAA_2_non_member_is_rejected(tmp_path):
    """FAA-2: ein Telegram-User, der NICHT in der Familien-Gruppe ist, wird
    abgewiesen; familie.json bleibt unverändert."""
    reg_path = _registry_path(tmp_path)
    # 9 ist nicht Mitglied (members enthält nur den 7er).
    tg = FakeTelegramFA(members={7: {"status": "member"}})
    res = familie_anlegen(tg, 42, 9, -100, reg_path, stream())
    assert res.authorized is False
    assert res.vergebene_ids == []
    assert tg.sent and tg.sent[0]["text"] == NOT_AUTHORIZED
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"] == [] and data["kinder"] == []


# ============================================================
#  FAA-3 — Reihenfolge & Schritt-Verhalten
# ============================================================

def test_FAA_3_repeats_question_on_empty_name(tmp_path):
    """FAA-3 Schritt 2: leere Antwort wiederholt die Namens-Frage."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene",
        "",                 # leerer Name → Wiederholung
        "Niclas",
        "überspringen", "ok", "überspringen", "überspringen",
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    # Reject-Nachricht ist mindestens einmal gesendet.
    assert any(REJECT_NAME in s["text"] for s in tg.sent)


def test_FAA_3_repeats_question_on_invalid_art(tmp_path):
    """FAA-3 Schritt 1: Antwort, die nicht erkennbar auf eine Art zeigt,
    wiederholt die Frage."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "vielleicht",       # weder erwachsene noch kind → wiederholt
        "erwachsene",
        "Niclas", "überspringen", "ok", "überspringen", "überspringen",
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    assert any(REJECT_KIND in s["text"] for s in tg.sent)


def test_FAA_3_skips_email_for_kind(tmp_path):
    """FAA-3 Schritt 5: bei Art „Kind" wird die E-Mail-Frage übersprungen.

    Der Test liefert nach „überspringen" beim Foto KEINE E-Mail-Antwort —
    wenn die Funktion die Frage stellen würde, würde sie auf next_message ohne
    Antwort laufen (Abbruch) und das Ergebnis wäre leer.
    """
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "kind", "Paula", "überspringen", "ok",
        # Keine E-Mail-Frage! Direkt Telegram-Schritt:
        "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["paula"]


def test_FAA_3_self_id_default_in_telegram_step(tmp_path):
    """FAA-3 Schritt 6: »ich« übernimmt die Telegram-User-ID des Aufrufers."""
    reg_path = _registry_path(tmp_path)
    user_id = 100000001
    # Der Aufrufer ist Mitglied der Familien-Gruppe (FAA-2).
    tg = FakeTelegramFA(members={user_id: {"status": "member"}})
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen", "ok", "überspringen",
        "ich",     # Self-Default
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, user_id, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"][0]["telegram_id"] == user_id


# ============================================================
#  FAA-4 — Ring-Farbe vorschlagen + Override
# ============================================================

def test_FAA_4_suggests_first_free_palette_color(tmp_path):
    """FAA-4: Vorschlag ist die erste freie Palette-Farbe — bei leerer Registry
    ist das `blue`. Ein »ok« übernimmt den Vorschlag."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen",
        "ok",                 # Vorschlag (blue) übernehmen
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"][0]["ring"] == "blue"


def test_FAA_4_override_with_palette_word(tmp_path):
    """FAA-4: ein Palette-Wort übersteuert den Vorschlag."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen",
        "red",                # explizite Wahl statt Vorschlag
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"][0]["ring"] == "red"


def test_FAA_4_rejects_word_outside_palette(tmp_path):
    """FAA-4: Wort außerhalb der Palette wird abgelehnt, Frage wiederholt."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen",
        "magenta",   # nicht in der Palette → REJECT
        "ok",        # Vorschlag annehmen
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    assert any(REJECT_RING in s["text"] for s in tg.sent)


# ============================================================
#  FAA-5 — ID-Vergabe + Slug-Kollision
# ============================================================

def test_FAA_5_slug_from_name(tmp_path):
    """FAA-5: Slug aus Namen (Kleinschreibung, Umlaute aufgelöst, Nicht-Wort-
    Zeichen zusammengezogen)."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Müller-Schäfer", "überspringen", "ok",
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["mueller-schaefer"]


def test_FAA_5_collision_appends_numeric_suffix(tmp_path):
    """FAA-5: Slug-Kollision wird mit `-2` aufgelöst."""
    # Registry hat schon „niclas"
    reg_path = str(tmp_path / "familie.json")
    open(reg_path, "w").write(json.dumps({
        "erwachsene": [{"id": "niclas", "name": "Niclas", "ring": "blue"}],
        "kinder": [],
    }))
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen", "ok",
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas-2"]


# ============================================================
#  FAA-6 — Profilbild-Annahme (PNG-Anhang, Telegram-Foto, MIME/Größe)
# ============================================================

def test_FAA_6_telegram_photo_lands_as_jpg(tmp_path):
    """FAA-6: eine Telegram-Foto-Nachricht landet als `<id>.jpg` im
    Foto-Verzeichnis."""
    foto_dir = tmp_path / "fotos"
    reg_path = _registry_path(
        tmp_path, settings={"foto_verzeichnis": str(foto_dir)})
    tg = _member_tg(downloads={"FILE-XL": b"\xff\xd8\xff_FAKEJPEG_"})
    next_msg = stream(
        "erwachsene", "Niclas",
        FaaInput(photo_file_id="FILE-XL"),
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    assert (foto_dir / "niclas.jpg").exists()
    assert (foto_dir / "niclas.jpg").read_bytes() == b"\xff\xd8\xff_FAKEJPEG_"
    # Eintrag in familie.json verweist auf die Datei.
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"][0]["foto"] == "niclas.jpg"


def test_FAA_6_png_document_lands_as_png(tmp_path):
    """FAA-6: PNG-Datei-Anhang landet als `<id>.png` im Foto-Verzeichnis."""
    foto_dir = tmp_path / "fotos"
    reg_path = _registry_path(
        tmp_path, settings={"foto_verzeichnis": str(foto_dir),
                            "profilbild_max_kante": 1280})
    png = _png_bytes(10, 10)
    tg = _member_tg(downloads={"DOC-PNG": png})
    next_msg = stream(
        "erwachsene", "Niclas",
        FaaInput(document_file_id="DOC-PNG",
                 document_mime_type="image/png",
                 document_size_hint=(10, 10)),
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    assert (foto_dir / "niclas.png").exists()
    assert (foto_dir / "niclas.png").read_bytes() == png


def test_FAA_6_document_oversized_is_rejected(tmp_path):
    """FAA-6/FAA-10: ein Datei-Anhang, dessen längste Kante die Max-Kante
    überschreitet, wird abgewiesen."""
    foto_dir = tmp_path / "fotos"
    reg_path = _registry_path(
        tmp_path, settings={"foto_verzeichnis": str(foto_dir),
                            "profilbild_max_kante": 100})
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas",
        FaaInput(document_file_id="X",
                 document_mime_type="image/png",
                 document_size_hint=(200, 50)),  # 200 > 100 → ablehnen
        "überspringen",   # nach REJECT erneut Schritt 3 — diesmal überspringen
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    assert any(REJECT_FOTO_GROSS in s["text"] for s in tg.sent)
    # Keine Foto-Datei (übersprungen).
    assert not foto_dir.exists() or not list(foto_dir.iterdir())


def test_FAA_6_non_image_attachment_is_rejected(tmp_path):
    """FAA-6/FAA-10: ein Datei-Anhang ohne Bild-MIME wird abgewiesen."""
    foto_dir = tmp_path / "fotos"
    reg_path = _registry_path(
        tmp_path, settings={"foto_verzeichnis": str(foto_dir)})
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas",
        FaaInput(document_file_id="X",
                 document_mime_type="application/pdf"),
        "überspringen", "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    assert any(REJECT_FOTO_MIME in s["text"] for s in tg.sent)


def test_FAA_6_skipped_photo_leaves_foto_unset(tmp_path):
    """FAA-6: übersprungenes Foto → `foto` im Eintrag bleibt ungesetzt."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen",
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    data = json.loads(open(reg_path).read())
    assert "foto" not in data["erwachsene"][0]


# ============================================================
#  FAA-7 — Bestätigungswort
# ============================================================

def test_FAA_7_confirmation_word_releases_write(tmp_path):
    """FAA-7: Bestätigungswort nach E-EC-7 schaltet das Schreiben frei."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    # "ja" ist ein E-EC-7 Bestätigungswort.
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen", "ok",
        "überspringen", "überspringen", "ja", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas"]
    data = json.loads(open(reg_path).read())
    assert [p["id"] for p in data["erwachsene"]] == ["niclas"]


def test_FAA_7_non_confirming_answer_does_not_write(tmp_path):
    """FAA-7: eine nicht-bestätigende Antwort schreibt nicht."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen", "ok",
        "überspringen", "überspringen", "lieber doch nicht",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == []
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"] == []
    assert any(CANCELLED in s["text"] for s in tg.sent)


# ============================================================
#  FAA-8 — Schreiben über FAM-11, atomar; bestehende Personen unverändert
# ============================================================

def test_FAA_8_additive_existing_persons_unchanged(tmp_path):
    """FAA-8/FAM-11: bestehende Personen bleiben bytegleich nach Anlage."""
    reg_path = str(tmp_path / "familie.json")
    open(reg_path, "w").write(json.dumps({
        "erwachsene": [
            {"id": "alt-eins", "name": "Alt Eins", "ring": "blue",
             "telegram_id": 1},
            {"id": "alt-zwei", "name": "Alt Zwei", "ring": "orange"},
        ],
        "kinder": [],
    }))
    before = json.loads(open(reg_path).read())
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Neu", "überspringen", "ok",
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["neu"]
    after = json.loads(open(reg_path).read())
    # Die ersten beiden Erwachsenen bleiben unverändert.
    assert after["erwachsene"][:2] == before["erwachsene"]
    assert after["erwachsene"][2]["id"] == "neu"


def test_FAA_8_write_failure_leaves_no_entry_and_no_photo(tmp_path, monkeypatch):
    """FAA-8 (letzter Satz): schlägt der Schreib-Aufruf fehl, bleibt weder die
    Person in der Registry noch eine Foto-Datei zurück."""
    foto_dir = tmp_path / "fotos"
    reg_path = _registry_path(
        tmp_path, settings={"foto_verzeichnis": str(foto_dir)})
    png = _png_bytes(8, 8)
    tg = _member_tg(downloads={"DOC": png})

    # registry.save wirft RegistryError (Disk-Schreibfehler simuliert).
    def fail_save(_reg, _path):
        raise registry_mod.RegistryError("disk voll (simuliert)")
    monkeypatch.setattr(registry_mod, "save", fail_save)

    next_msg = stream(
        "erwachsene", "Niclas",
        FaaInput(document_file_id="DOC",
                 document_mime_type="image/png",
                 document_size_hint=(8, 8)),
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == []
    # familie.json unverändert.
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"] == []
    # Foto-Datei wurde aufgeräumt.
    assert not (foto_dir / "niclas.png").exists()
    assert any(WRITE_FAILED in s["text"] for s in tg.sent)


# ============================================================
#  FAA-9 — Mehr-Personen-Loop
# ============================================================

def test_FAA_9_loop_continues_then_ends(tmp_path):
    """FAA-9: nach einer Person fragt die Funktion „noch jemand?", führt bei
    Bestätigung zur nächsten Anlage, beendet bei nicht-bestätigender Antwort."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        # Person 1 (Erwachsene, ring „blue" als Vorschlag)
        "erwachsene", "Niclas", "überspringen", "ok",
        "überspringen", "überspringen", "ok",
        "ja",  # noch jemand?
        # Person 2 (Kind, ring „orange" wird Vorschlag)
        "kind", "Paula", "überspringen", "ok", "überspringen", "ok",
        "nein",  # Ende
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["niclas", "paula"]
    # Erfolg-Nachricht zeigt beide.
    assert any((DONE_MULTI % "niclas, paula") in s["text"] for s in tg.sent)


# ============================================================
#  FAA-10 — Fehler-Klassen
# ============================================================

def test_FAA_10_duplicate_telegram_id_is_rejected(tmp_path):
    """FAA-10: eine Telegram-ID, die bereits einer Person gehört, wird
    abgelehnt; Frage wird wiederholt."""
    reg_path = str(tmp_path / "familie.json")
    open(reg_path, "w").write(json.dumps({
        "erwachsene": [{"id": "bestehend", "name": "B", "ring": "blue",
                        "telegram_id": 12345}],
        "kinder": [],
    }))
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Neu", "überspringen", "ok", "überspringen",
        "12345",          # bereits vergeben → ablehnen
        "überspringen",   # ok, überspringen
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == ["neu"]
    assert any(REJECT_TELEGRAM_DUP in s["text"] for s in tg.sent)
    # `bestehend` ist weiterhin alleinige Trägerin von 12345.
    data = json.loads(open(reg_path).read())
    holders = [p for p in data["erwachsene"] if p.get("telegram_id") == 12345]
    assert [p["id"] for p in holders] == ["bestehend"]


def test_FAA_10_disk_write_failure_signals_misserfolg(tmp_path, monkeypatch):
    """FAA-10: Disk-Schreibfehler signalisiert Misserfolg an den Aufrufer;
    `familie.json` bleibt unverändert. (Doppelt zu FAA-8, aber explizit als
    Fehler-Klasse.)"""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    def fail_save(_r, _p):
        raise registry_mod.RegistryError("kein Schreibrecht")
    monkeypatch.setattr(registry_mod, "save", fail_save)
    next_msg = stream(
        "erwachsene", "Niclas", "überspringen", "ok",
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_ids == []
    data = json.loads(open(reg_path).read())
    assert data["erwachsene"] == []


# ============================================================
#  FAA-11 — Test-Abdeckungs-Wächter
# ============================================================

def test_FAA_11_every_requirement_has_a_test():
    """FAA-11: jede Anforderung mit Code-Verhalten hat einen Test."""
    quelle = open(os.path.abspath(__file__), encoding="utf-8").read()
    # FAA-1 .. FAA-10; FAA-11 ist dieser Test.
    for faa in range(1, 11):
        assert "def test_FAA_%d_" % faa in quelle, "FAA-%d ungetestet" % faa
