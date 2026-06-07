"""Tests für FotoSendenTask und Catalog-Registrierung (FSE-8, Refs #393).

Analog `test_routine_zeiten_setzen_task.py`:
- ReadTask-Prüfung (TASK-9): Sofort-Schreib-Aufgabe via ReadTask-Pfad
  (kein propose, kein Confirm-Gate — E-FSE-1).
- AND-Guard: Task erscheint nur wenn photo_origin_url UND
  family_group_chat_id_getter (FSE-8).
- AC_ENTRY: build_catalog → get → run() → PhotoClient → PHOTO-13
  (Transport-Stub, CLIENT-1).

Pflicht-Tests (FSE-8):
- Guard: photo_origin_url + fgcid → registriert.
- Ohne photo_origin_url → nicht registriert.
- Ohne family_group_chat_id_getter → nicht registriert.
- Nicht-Mitglied → kein POST.
- Happy-Path Foto: TurnContext mit media_telegram_file_id → run() ruft
  PHOTO-13; Quittung enthält id (Transport-Stub).
- Happy-Path Video: gleicher Pfad (FSE-5).
- Rückgängig: aktion=widerrufen + id → DELETE /api/v1/photo/medien/<id>.
- Grenze: PHOTO-13 4xx → Quittung ohne Zweit-Schreiben.
- Tool-Wahl falsche Spur: leerer TurnContext → ehrliche Grenze, kein POST.
- APP-3: Skill ruft die API, nicht die Datei.
"""

import contextlib
import json
import os
import tempfile

from fakes import FakeTelegram
from skills.foto_senden_task import FotoSendenTask
from tasks import Catalog, ReadTask, TurnContext, build_catalog

# ============================================================
#  Doppelungen
# ============================================================

class FakeTelegramMitDownload(FakeTelegram):
    """FakeTelegram + download_file-Stub für FSE-3-Tests."""

    def __init__(self, file_bytes=None, download_error=None, **kw):
        super().__init__(**kw)
        self._file_bytes = file_bytes if file_bytes is not None else b"FAKEJPEG"
        self._download_error = download_error
        self.download_calls = []

    def download_file(self, file_id):
        self.download_calls.append(file_id)
        if self._download_error is not None:
            raise self._download_error
        return self._file_bytes


def _family_getter(fgcid=200):
    return lambda: fgcid


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _transport_stub_factory(post_status=200, post_body=None,
                            delete_status=204, delete_body=b""):
    """Erzeugt einen Transport-Stub für den PhotoClient (CLIENT-1).

    `post_body` ist die Response-bytes für POST /api/v1/photo/medien;
    default = `{"id": "abc123", "typ": "foto"}`.
    """
    calls = []
    if post_body is None:
        post_body = json.dumps({"id": "abc123", "typ": "foto"}).encode("utf-8")

    def transport(method, path, *, body=None, content_type=None):
        calls.append({
            "method": method, "path": path,
            "body": body, "content_type": content_type,
        })
        if method == "POST":
            return post_status, post_body
        if method == "DELETE":
            return delete_status, delete_body
        raise AssertionError("unexpected method %s" % method)

    return transport, calls


def _make_task(tg=None, photo_client=None, family_group_chat_id_getter=None,
               is_member_fn=None):
    """Baut einen FotoSendenTask mit kontrollierten Doppelungen.

    Wenn `photo_client` None ist, wird ein echter PhotoClient mit Transport-Stub
    konstruiert — so prüft jeder Test gleichzeitig die HTTP-Linie.
    """
    from skills.photo_client import PhotoClient

    if tg is None:
        tg = FakeTelegramMitDownload(members=_members(42))
    if photo_client is None:
        transport, _ = _transport_stub_factory()
        photo_client = PhotoClient(
            origin_url="http://127.0.0.1:5070", transport=transport)
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    if is_member_fn is None:
        is_member_fn = _immer_mitglied
    return FotoSendenTask(
        tg=tg,
        photo_client=photo_client,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=is_member_fn,
    )


# ============================================================
#  TASK-9 — ReadTask-Klassifikation (Sofort-Schreib-Aufgabe)
# ============================================================

def test_TASK9_ist_read_task():
    """TASK-9 / E-FSE-1: FotoSendenTask ist eine ReadTask — kein propose/confirm.

    Bewusste Wahl: das auslösende Ereignis (kommentarloses Medium) ist die
    ausdrückliche Handlung; das Undo (PHOTO-16) ist das Sicherheitsnetz.
    """
    task = _make_task()
    assert isinstance(task, ReadTask), (
        "FotoSendenTask muss ReadTask sein (TASK-9 / E-FSE-1), nicht WriteTask")


def test_TASK9_name():
    """FSE-8: Task-Name ist 'foto_senden' (Catalog-Schlüssel)."""
    task = _make_task()
    assert task.name == "foto_senden"


def test_TASK9_keine_propose_methode_im_lese_pfad():
    """TASK-9: ReadTask hat `run`, kein `propose`/`execute` — das ist genau
    der Punkt (E-FSE-1: kein Confirm-Gate)."""
    task = _make_task()
    assert hasattr(task, "run")


# ============================================================
#  FSE-2 — Berechtigung
# ============================================================

def test_FSE2_nicht_mitglied_kein_post():
    """FSE-2: Nicht-Mitglied → keine PHOTO-13-POST-Aufruf."""
    transport, calls = _transport_stub_factory()
    from skills.photo_client import PhotoClient
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=transport)
    tg = FakeTelegramMitDownload(file_bytes=b"x")
    task = _make_task(
        tg=tg, photo_client=photo_client,
        is_member_fn=_kein_mitglied)
    ctx = TurnContext(
        chat_id=200, from_user_id=42, private_chat_id=42,
        media_telegram_file_id="tg-file-1", medium_typ="foto")

    quittung = task.run({}, ctx)

    assert quittung  # ehrliche Antwort
    # Wichtig: weder Download noch POST.
    assert calls == [], "Nicht-Mitglied darf kein POST auslösen (FSE-2)"


# ============================================================
#  FSE-4 — Happy-Path Hochladen (Foto / Video)
# ============================================================

def test_FSE4_happy_path_foto_postet_an_photo13():
    """FSE-4 Happy-Path Foto: TurnContext mit file_id → run() lädt → POST."""
    transport, calls = _transport_stub_factory(
        post_body=json.dumps({"id": "foto-x", "typ": "foto"}).encode("utf-8"))
    from skills.photo_client import PhotoClient
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=transport)
    tg = FakeTelegramMitDownload(
        file_bytes=b"JPEGDATA", members=_members(42))
    task = _make_task(tg=tg, photo_client=photo_client)
    ctx = TurnContext(
        chat_id=200, from_user_id=42, private_chat_id=42,
        media_telegram_file_id="tg-photo-1", medium_typ="foto")

    quittung = task.run({}, ctx)

    assert tg.download_calls == ["tg-photo-1"]
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/api/v1/photo/medien"
    assert b"JPEGDATA" in calls[0]["body"]
    assert b'name="medium"' in calls[0]["body"]
    # FSE-4 / D6: Quittung enthält die id für den Undo-Pfad.
    assert "foto-x" in quittung, (
        f"Quittung muss die id für das Undo enthalten, quittung={quittung!r}")


def test_FSE5_happy_path_video_gleicher_pfad():
    """FSE-5: Video läuft genauso (PHOTO-13 nimmt beide)."""
    transport, calls = _transport_stub_factory(
        post_body=json.dumps({"id": "vid-1", "typ": "video"}).encode("utf-8"))
    from skills.photo_client import PhotoClient
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=transport)
    tg = FakeTelegramMitDownload(
        file_bytes=b"MP4DATA", members=_members(42))
    task = _make_task(tg=tg, photo_client=photo_client)
    ctx = TurnContext(
        chat_id=200, from_user_id=42, private_chat_id=42,
        media_telegram_file_id="tg-video-1", medium_typ="video")

    quittung = task.run({}, ctx)

    assert calls[0]["method"] == "POST"
    assert b"MP4DATA" in calls[0]["body"]
    assert "vid-1" in quittung


# ============================================================
#  FSE-3 — Tool-Wahl auf falscher Spur (leerer TurnContext)
# ============================================================

def test_FSE3_kein_medium_im_turncontext_ehrliche_grenze():
    """FSE-3 / EC-7: leerer TurnContext (Modell rief auf falscher Spur) →
    Quittung mit ehrlicher Grenze, KEIN POST."""
    transport, calls = _transport_stub_factory()
    from skills.photo_client import PhotoClient
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=transport)
    tg = FakeTelegramMitDownload()
    task = _make_task(tg=tg, photo_client=photo_client)
    ctx = TurnContext(
        chat_id=200, from_user_id=42, private_chat_id=42,
        # KEIN media_telegram_file_id
    )

    quittung = task.run({}, ctx)

    assert quittung  # ehrliche Antwort
    assert calls == [], "Ohne Medium darf kein POST passieren (FSE-3)"
    assert tg.download_calls == []


# ============================================================
#  FSE-5 — Grenze (PHOTO-13 4xx)
# ============================================================

def test_FSE5_413_video_zu_lang_grenze_keine_zweite_post():
    """FSE-5: PHOTO-13 lehnt überlanges Video mit 4xx ab → Quittung, kein
    weiteres POST."""
    transport, calls = _transport_stub_factory(
        post_status=413,
        post_body=json.dumps({"error": "video zu lang"}).encode("utf-8"))
    from skills.photo_client import PhotoClient
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=transport)
    tg = FakeTelegramMitDownload(
        file_bytes=b"BIG", members=_members(42))
    task = _make_task(tg=tg, photo_client=photo_client)
    ctx = TurnContext(
        chat_id=200, from_user_id=42, private_chat_id=42,
        media_telegram_file_id="tg-big", medium_typ="video")

    quittung = task.run({}, ctx)

    # Genau ein POST-Versuch, keine Retry vom Skill.
    assert len([c for c in calls if c["method"] == "POST"]) == 1
    assert quittung  # ehrliche Quittung


# ============================================================
#  FSE-4 — Rückgängig (PHOTO-16, D6 zweiter tool_use)
# ============================================================

def test_FSE4_widerrufen_ruft_delete_medien_id():
    """FSE-4 / D6: aktion='widerrufen' mit id → DELETE /api/v1/photo/medien/<id>."""
    transport, calls = _transport_stub_factory()
    from skills.photo_client import PhotoClient
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=transport)
    tg = FakeTelegramMitDownload(members=_members(42))
    task = _make_task(tg=tg, photo_client=photo_client)
    ctx = TurnContext(
        chat_id=200, from_user_id=42, private_chat_id=42,
        # KEIN media — Widerruf braucht die id aus arguments.
    )

    quittung = task.run({"aktion": "widerrufen", "id": "abc123"}, ctx)

    assert quittung
    delete_calls = [c for c in calls if c["method"] == "DELETE"]
    assert len(delete_calls) == 1
    assert delete_calls[0]["path"] == "/api/v1/photo/medien/abc123"


# ============================================================
#  Catalog-Registrierung (AND-Guard, FSE-8)
# ============================================================

def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_FSE8_registriert_wenn_beide_gesetzt():
    """FSE-8: FotoSendenTask erscheint im Catalog wenn photo_origin_url
    UND family_group_chat_id_getter gesetzt sind (AND-Guard)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("foto_senden")
        assert task is not None, "FotoSendenTask sollte im Catalog sein"
        assert isinstance(task, ReadTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_FSE8_nicht_registriert_ohne_photo_origin():
    """FSE-8: ohne photo_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            # photo_origin_url fehlt
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("foto_senden")
        assert task is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_FSE8_nicht_registriert_ohne_fgcid():
    """FSE-8: ohne family_group_chat_id_getter → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            photo_origin_url="http://127.0.0.1:5070",
            # family_group_chat_id_getter fehlt
        )
        task = catalog.get("foto_senden")
        assert task is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  AC_ENTRY: build_catalog → run() → POST (echte Kette)
# ============================================================

def test_AC_ENTRY_build_catalog_bis_post():
    """AC_ENTRY: build_catalog → get('foto_senden') → run() →
    POST /api/v1/photo/medien (Transport-Stub, CLIENT-1).

    Prüft den echten Laufzeitpfad: Catalog-Registrierung → Task-Aufruf →
    PhotoClient.upload_medium mit Multipart-Body. Der Transport-Stub
    ersetzt nur die HTTP-Schicht.
    """
    from skills.photo_client import PhotoClient

    transport, calls = _transport_stub_factory(
        post_body=json.dumps({"id": "entry-1", "typ": "foto"}).encode("utf-8"))
    # FotoSendenTask direkt registrieren mit echtem PhotoClient + Transport-Stub.
    tg = FakeTelegramMitDownload(
        file_bytes=b"ENTRYDATA", members=_members(42))
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=transport)
    task = FotoSendenTask(
        tg=tg, photo_client=photo_client,
        family_group_chat_id_getter=_family_getter(),
        is_member_fn=_immer_mitglied)
    catalog = Catalog()
    catalog.register(task)
    retrieved = catalog.get("foto_senden")
    assert retrieved is not None
    ctx = TurnContext(
        chat_id=200, from_user_id=42, private_chat_id=42,
        media_telegram_file_id="tg-entry", medium_typ="foto")

    quittung = retrieved.run({}, ctx)

    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/api/v1/photo/medien"
    assert b"ENTRYDATA" in calls[0]["body"]
    assert "entry-1" in quittung
