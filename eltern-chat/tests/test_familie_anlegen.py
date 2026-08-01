"""Tests für »Familie anlegen« — FAA-1…FAA-11 (Refs #60, #215).

Mindest-Abdeckung nach `specs/platform/familie-anlegen.md` FAA-11. Telegram
wird durch eine kontrollierte Doppelung ersetzt (Pattern wie ONB-9): die
FakeTelegram aus `fakes.py` plus eine schmale Subklasse mit `download_file`
für FAA-6. Auch der Eingabe-Strom wird über eine kleine Doppelung
nachgebildet — `familie_anlegen` ruft `next_message()` solange auf, bis das
Skript leer ist.

Seit Auftrag #215 spricht die Skill ueber HTTP (DCOMP-1). Die Tests
ersetzen die HTTP-Schicht durch `FakeFamilieClient` — symmetrisch zu
`plan/familie_client.transport=`, ohne echten HTTP-Server. So bleibt das
Verhalten der Skill in Probe ohne Netz und ohne `familie/`-Import.
"""

import os
import struct
import zlib

from fakes import FakeTelegram
from skills.familie_anlegen import (
    CANCELLED,
    DONE_MULTI,
    NOT_AUTHORIZED,
    REJECT_FOTO_GROSS,
    REJECT_FOTO_MIME,
    REJECT_KIND,
    REJECT_NAME,
    REJECT_RING,
    REJECT_TELEGRAM_DUP,
    WRITE_FAILED,
    FaaInput,
    familie_anlegen,
)
from skills.familie_client import FamilieClientError

# ============================================================
#  Test-Doppelungen — FakeFamilieClient + FakeTelegram + Eingabe-Strom
# ============================================================

class FakeFamilieClient:
    """In-Memory-Doppelung des FamilieClient — ohne HTTP, ohne familie/-Import.

    Vorgaenger im Repo: das `FakeTransport`-Muster in
    `plan/tests/conftest.py` (PR #238). Hier ist die Naht aber direkt am
    Client (statt am `transport=`-Callable), weil die Skill den Client
    via Argument bekommt und wir die Methoden eins-zu-eins simulieren —
    so bleiben die FAA-Tests lesbar.

    `personen` ist die Liste der Personen-Dicts, die `alle_personen()`
    liefert (FAM-7-Form). `anlage_responses` ist eine Folge von
    Antwort-Dicts, die `person_anlegen()` der Reihe nach liefert — kein
    `Exception`-Item; Fehler werden ueber `anlage_error` und
    `alle_error` gesteuert (eine Exception je Aufruf-Sicht).
    """

    def __init__(self, personen=None, anlage_responses=None,
                 anlage_error=None, alle_error=None, foto_error=None):
        self._personen = list(personen or [])
        self._anlage_responses = list(anlage_responses or [])
        self._anlage_error = anlage_error
        self._alle_error = alle_error
        self._foto_error = foto_error
        self.anlage_calls = []
        self.foto_calls = []
        self.alle_calls = 0
        self._next_seq = 1

    def alle_personen(self):
        self.alle_calls += 1
        if self._alle_error is not None:
            raise self._alle_error
        return [dict(p) for p in self._personen]

    def person_anlegen(self, name, art=None, ring=None, email=None,
                       telegram_id=None):
        self.anlage_calls.append({
            "name": name, "art": art, "ring": ring,
            "email": email, "telegram_id": telegram_id,
        })
        if self._anlage_error is not None:
            raise self._anlage_error
        if self._anlage_responses:
            angelegt = self._anlage_responses.pop(0)
        else:
            # Default: server vergibt `person-<slug>-NN` als id.
            slug = _slugify(name)
            angelegt = {
                "id": "person-%s-%02d" % (slug, self._next_seq),
                "name": name,
                "ring": ring or "blue",
                "art": art or "erwachsene",
            }
            self._next_seq += 1
            if email is not None:
                angelegt["email"] = email
            if telegram_id is not None:
                angelegt["telegram_id"] = telegram_id
        # In-Memory-Snapshot fortschreiben — Folgeaufrufe sehen die neue Person.
        self._personen.append(dict(angelegt))
        return angelegt

    def foto_hochladen(self, person_id, dateiname, daten, content_type):
        self.foto_calls.append({
            "person_id": person_id, "dateiname": dateiname,
            "daten": daten, "content_type": content_type,
        })
        if self._foto_error is not None:
            raise self._foto_error


def _slugify(name):
    import re
    s = name.lower()
    for old, new in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(old, new)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "person"


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


def _member_tg(downloads=None):
    """FakeTelegramFA, in dem der Test-Aufrufer 7 Mitglied der Familien-Gruppe
    ist (FAA-2)."""
    return FakeTelegramFA(members={7: {"status": "member"}},
                          downloads=downloads or {})


# ============================================================
#  FAA-1 — Aufruf-Schnittstelle
# ============================================================

def test_FAA_1_returns_list_of_ids_for_single_person():
    """FAA-1: ein Durchlauf mit genau einer Person liefert eine Liste mit der
    vergebenen `id`."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene",     # Art
        "Emil",         # Name
        "überspringen",   # Foto
        "ok",             # Ring (Vorschlag übernehmen)
        "überspringen",   # E-Mail
        "überspringen",   # Telegram-ID
        "ok",             # Bestätigung (FAA-7)
        "nein",           # Noch jemand? (FAA-9 → Ende)
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.authorized is True
    assert res.vergebene_ids == ["person-emil-01"]
    # Genau ein Schreib-Aufruf an den FAM-12-Endpunkt.
    assert len(client.anlage_calls) == 1
    assert client.anlage_calls[0]["name"] == "Emil"


def test_FAA_1_returns_empty_list_on_immediate_cancel():
    """FAA-1: sofortiger Abbruch bei der Bestätigung der ersten Person → leere
    Liste."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "kind", "Mia", "überspringen", "ok", "überspringen",
        "nein, doch nicht",   # FAA-7: nicht-bestätigende Antwort
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == []
    # Keine FAM-12-Aufrufe.
    assert client.anlage_calls == []


def test_FAA_1_multiple_persons_in_one_call():
    """FAA-1/FAA-9: zwei Personen im selben Aufruf → zwei `id`s im Ergebnis."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        # Person 1
        "erwachsene", "Emil", "überspringen", "ok", "überspringen",
        "überspringen", "ok",
        "ja",  # noch jemand?
        # Person 2
        "kind", "Mia", "überspringen", "ok", "überspringen", "ok",
        "nein",  # Ende
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01", "person-mia-02"]
    assert len(client.anlage_calls) == 2
    assert [c["art"] for c in client.anlage_calls] == ["erwachsene", "kinder"]


# ============================================================
#  FAA-2 — Berechtigung live über die Familien-Gruppen-Mitgliedschaft
# ============================================================

def test_FAA_2_non_member_is_rejected():
    """FAA-2: ein Telegram-User, der NICHT in der Familien-Gruppe ist, wird
    abgewiesen; FAM-12 wird gar nicht aufgerufen."""
    client = FakeFamilieClient()
    # 9 ist nicht Mitglied (members enthält nur den 7er).
    tg = FakeTelegramFA(members={7: {"status": "member"}})
    res = familie_anlegen(tg, 42, 9, -100, client, stream())
    assert res.authorized is False
    assert res.vergebene_ids == []
    assert tg.sent and tg.sent[0]["text"] == NOT_AUTHORIZED
    assert client.anlage_calls == []
    assert client.alle_calls == 0


# ============================================================
#  FAA-3 — Reihenfolge & Schritt-Verhalten
# ============================================================

def test_FAA_3_repeats_question_on_empty_name():
    """FAA-3 Schritt 2: leere Antwort wiederholt die Namens-Frage."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene",
        "",                 # leerer Name → Wiederholung
        "Emil",
        "überspringen", "ok", "überspringen", "überspringen",
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    # Reject-Nachricht ist mindestens einmal gesendet.
    assert any(REJECT_NAME in s["text"] for s in tg.sent)


def test_FAA_3_repeats_question_on_invalid_art():
    """FAA-3 Schritt 1: Antwort, die nicht erkennbar auf eine Art zeigt,
    wiederholt die Frage."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "vielleicht",       # weder erwachsene noch kind → wiederholt
        "erwachsene",
        "Emil", "überspringen", "ok", "überspringen", "überspringen",
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert any(REJECT_KIND in s["text"] for s in tg.sent)


def test_FAA_3_skips_email_for_kind():
    """FAA-3 Schritt 5: bei Art „Kind" wird die E-Mail-Frage übersprungen.

    Der Test liefert nach „überspringen" beim Foto KEINE E-Mail-Antwort —
    wenn die Funktion die Frage stellen würde, würde sie auf next_message ohne
    Antwort laufen (Abbruch) und das Ergebnis wäre leer.
    """
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "kind", "Mia", "überspringen", "ok",
        # Keine E-Mail-Frage! Direkt Telegram-Schritt:
        "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-mia-01"]


def test_FAA_3_self_id_default_in_telegram_step():
    """FAA-3 Schritt 6: »ich« übernimmt die Telegram-User-ID des Aufrufers."""
    client = FakeFamilieClient()
    user_id = 100000001
    # Der Aufrufer ist Mitglied der Familien-Gruppe (FAA-2).
    tg = FakeTelegramFA(members={user_id: {"status": "member"}})
    next_msg = stream(
        "erwachsene", "Emil", "überspringen", "ok", "überspringen",
        "ich",     # Self-Default
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, user_id, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert client.anlage_calls[0]["telegram_id"] == user_id


# ============================================================
#  FAA-4 — Ring-Farbe vorschlagen + Override
# ============================================================

def test_FAA_4_suggests_first_free_palette_color():
    """FAA-4: Vorschlag ist die erste freie Palette-Farbe — bei leerer Registry
    ist das `blue`. Ein »ok« übernimmt den Vorschlag."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil", "überspringen",
        "ok",                 # Vorschlag (blue) übernehmen
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert client.anlage_calls[0]["ring"] == "blue"


def test_FAA_4_override_with_palette_word():
    """FAA-4: ein Palette-Wort übersteuert den Vorschlag."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil", "überspringen",
        "red",                # explizite Wahl statt Vorschlag
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert client.anlage_calls[0]["ring"] == "red"


def test_FAA_4_rejects_word_outside_palette():
    """FAA-4: Wort außerhalb der Palette wird abgelehnt, Frage wiederholt."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil", "überspringen",
        "magenta",   # nicht in der Palette → REJECT
        "ok",        # Vorschlag annehmen
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert any(REJECT_RING in s["text"] for s in tg.sent)


# ============================================================
#  FAA-5 — ID-Vergabe (jetzt serverseitig, FAM-12)
# ============================================================

def test_FAA_5_server_assigns_id_skill_reads_back():
    """FAA-5 (#215): FAM-12 vergibt die IDENT-1-`id` (`person-<slug>-<nn>`).
    Die Skill liest sie zurueck — kein Slug-Eigenbau mehr.

    Vorgegebene Antwort des Servers, damit der Test die Form pruefen kann."""
    client = FakeFamilieClient(anlage_responses=[
        {"id": "person-mueller-schaefer-03", "name": "Müller-Schäfer",
         "ring": "blue", "art": "erwachsene"}
    ])
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Müller-Schäfer", "überspringen", "ok",
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-mueller-schaefer-03"]


# ============================================================
#  FAA-6 — Profilbild-Annahme (PNG-Anhang, Telegram-Foto, MIME/Größe)
# ============================================================

def test_FAA_6_telegram_photo_uploaded_as_jpg():
    """FAA-6: eine Telegram-Foto-Nachricht wird als `<id>.jpg`-Multipart an
    FAM-13 hochgeladen."""
    client = FakeFamilieClient()
    tg = _member_tg(downloads={"FILE-XL": b"\xff\xd8\xff_FAKEJPEG_"})
    next_msg = stream(
        "erwachsene", "Emil",
        FaaInput(photo_file_id="FILE-XL"),
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert len(client.foto_calls) == 1
    upload = client.foto_calls[0]
    assert upload["person_id"] == "person-emil-01"
    assert upload["dateiname"] == "person-emil-01.jpg"
    assert upload["content_type"] == "image/jpeg"
    assert upload["daten"] == b"\xff\xd8\xff_FAKEJPEG_"


def test_FAA_6_png_document_uploaded_as_png():
    """FAA-6: PNG-Datei-Anhang wird als `<id>.png`-Multipart an FAM-13
    hochgeladen."""
    client = FakeFamilieClient()
    png = _png_bytes(10, 10)
    tg = _member_tg(downloads={"DOC-PNG": png})
    next_msg = stream(
        "erwachsene", "Emil",
        FaaInput(document_file_id="DOC-PNG",
                 document_mime_type="image/png",
                 document_size_hint=(10, 10)),
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert len(client.foto_calls) == 1
    upload = client.foto_calls[0]
    assert upload["content_type"] == "image/png"
    assert upload["dateiname"].endswith(".png")
    assert upload["daten"] == png


def test_FAA_6_document_oversized_is_rejected():
    """FAA-6/FAA-10: ein Datei-Anhang, dessen längste Kante die Max-Kante
    überschreitet, wird abgewiesen — kein Foto-Upload."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil",
        FaaInput(document_file_id="X",
                 document_mime_type="image/png",
                 document_size_hint=(2000, 50)),  # 2000 > 1280 (Default) → ablehnen
        "überspringen",   # nach REJECT erneut Schritt 3 — diesmal überspringen
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert any(REJECT_FOTO_GROSS in s["text"] for s in tg.sent)
    # Kein Foto-Upload — die Skill verwirft den Anhang lokal.
    assert client.foto_calls == []


def test_FAA_6_non_image_attachment_is_rejected():
    """FAA-6/FAA-10: ein Datei-Anhang ohne Bild-MIME wird abgewiesen."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil",
        FaaInput(document_file_id="X",
                 document_mime_type="application/pdf"),
        "überspringen", "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert any(REJECT_FOTO_MIME in s["text"] for s in tg.sent)
    assert client.foto_calls == []


def test_FAA_6_skipped_photo_leaves_foto_unset():
    """FAA-6: übersprungenes Foto → kein FAM-13-Aufruf."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil", "überspringen",
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert client.foto_calls == []


# ============================================================
#  FAA-7 — Bestätigungswort
# ============================================================

def test_FAA_7_confirmation_word_releases_write():
    """FAA-7: Bestätigungswort nach E-EC-7 schaltet das Schreiben frei."""
    client = FakeFamilieClient()
    tg = _member_tg()
    # "ja" ist ein E-EC-7 Bestätigungswort.
    next_msg = stream(
        "erwachsene", "Emil", "überspringen", "ok",
        "überspringen", "überspringen", "ja", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01"]
    assert len(client.anlage_calls) == 1


def test_FAA_7_non_confirming_answer_does_not_write():
    """FAA-7: eine nicht-bestätigende Antwort schreibt nicht."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil", "überspringen", "ok",
        "überspringen", "überspringen", "lieber doch nicht",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == []
    assert client.anlage_calls == []
    assert any(CANCELLED in s["text"] for s in tg.sent)


# ============================================================
#  FAA-8 — Schreiben über FAM-12 (HTTP), additiv; bestehende Personen unbeeinflusst
# ============================================================

def test_FAA_8_additive_existing_persons_unchanged():
    """FAA-8/FAM-12: bestehende Personen werden vom Client gelesen und bleiben
    unberuehrt; die neue Person geht ueber genau einen POST."""
    bestand = [
        {"id": "person-alt-eins-01", "name": "Alt Eins", "ring": "blue",
         "art": "erwachsene", "telegram_id": 1},
        {"id": "person-alt-zwei-01", "name": "Alt Zwei", "ring": "orange",
         "art": "erwachsene"},
    ]
    client = FakeFamilieClient(personen=bestand)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Neu", "überspringen", "ok",
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert len(res.vergebene_ids) == 1
    assert len(client.anlage_calls) == 1
    # Bestand erstmal bytes-gleich uebernommen (Client haelt Liste).
    assert {p["id"] for p in bestand} <= {p["id"] for p in client._personen}


def test_FAA_8_write_failure_signals_misserfolg_and_skips_foto():
    """FAA-8 (letzter Satz): scheitert FAM-12, bleibt die Person nicht
    angelegt, und es geht kein Foto-Upload los."""
    client = FakeFamilieClient(
        anlage_error=FamilieClientError("disk voll (simuliert)"))
    tg = _member_tg(downloads={"DOC": _png_bytes(8, 8)})
    next_msg = stream(
        "erwachsene", "Emil",
        FaaInput(document_file_id="DOC",
                 document_mime_type="image/png",
                 document_size_hint=(8, 8)),
        "ok", "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == []
    assert client.foto_calls == []
    assert any(WRITE_FAILED in s["text"] for s in tg.sent)


# ============================================================
#  FAA-9 — Mehr-Personen-Loop
# ============================================================

def test_FAA_9_loop_continues_then_ends():
    """FAA-9: nach einer Person fragt die Funktion „noch jemand?", führt bei
    Bestätigung zur nächsten Anlage, beendet bei nicht-bestätigender Antwort."""
    client = FakeFamilieClient()
    tg = _member_tg()
    next_msg = stream(
        # Person 1 (Erwachsene, ring „blue" als Vorschlag)
        "erwachsene", "Emil", "überspringen", "ok",
        "überspringen", "überspringen", "ok",
        "ja",  # noch jemand?
        # Person 2 (Kind, ring „orange" wird Vorschlag)
        "kind", "Mia", "überspringen", "ok", "überspringen", "ok",
        "nein",  # Ende
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == ["person-emil-01", "person-mia-02"]
    # Erfolg-Nachricht zeigt beide.
    assert any((DONE_MULTI % "person-emil-01, person-mia-02") in s["text"]
               for s in tg.sent)


# ============================================================
#  FAA-10 — Fehler-Klassen
# ============================================================

def test_FAA_10_duplicate_telegram_id_is_rejected_locally():
    """FAA-10: eine Telegram-ID, die bereits einer Person gehört, wird
    abgelehnt; Frage wird wiederholt — Pre-Check liegt auf dem Snapshot."""
    bestand = [{"id": "person-bestehend-01", "name": "B", "ring": "blue",
                "art": "erwachsene", "telegram_id": 12345}]
    client = FakeFamilieClient(personen=bestand)
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Neu", "überspringen", "ok", "überspringen",
        "12345",          # bereits vergeben → ablehnen
        "überspringen",   # ok, überspringen
        "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert len(res.vergebene_ids) == 1
    assert any(REJECT_TELEGRAM_DUP in s["text"] for s in tg.sent)


def test_FAA_10_server_unreachable_signals_misserfolg():
    """FAA-10: der Server antwortet gar nicht (Pre-Check-Aufruf
    `alle_personen` wirft) — die Skill bricht mit klarer Bot-Nachricht ab,
    nichts wird angelegt."""
    client = FakeFamilieClient(
        alle_error=FamilieClientError("Service nicht erreichbar (simuliert)"))
    tg = _member_tg()
    next_msg = stream(
        "erwachsene", "Emil", "überspringen", "ok",
        "überspringen", "überspringen", "ok", "nein",
    )
    res = familie_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_ids == []
    assert client.anlage_calls == []
    assert any(WRITE_FAILED in s["text"] for s in tg.sent)


# ============================================================
#  FAA-11 — Test-Abdeckungs-Wächter
# ============================================================

def test_FAA_11_every_requirement_has_a_test():
    """FAA-11: jede Anforderung mit Code-Verhalten hat einen Test."""
    quelle = open(os.path.abspath(__file__), encoding="utf-8").read()
    # FAA-1 .. FAA-10; FAA-11 ist dieser Test.
    for faa in range(1, 11):
        assert "def test_FAA_%d_" % faa in quelle, "FAA-%d ungetestet" % faa
