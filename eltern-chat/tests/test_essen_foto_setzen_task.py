"""Tests für EssenFotoSetzenTask und Catalog-Registrierung (ESSEN-22 Pfad 2).

Analog `test_gericht_anlegen_task.py` / `test_foto_senden_task.py`:
- WriteTask-Prüfung (EC-10): propose→confirm-Aufgabe, Klasse C.
- AND-Guard: essen_origin_url UND photo_origin_url UND
  family_group_chat_id_getter (T531/AC5).
- propose-Tests: Vorschlag nennt Ziel + Bestätigungshinweis.
- execute-Tests: Hochladen (Schritt 1), PATCH (Schritt 2a), Override (Schritt 2b).
- Abbruch-Pfad.
- Nicht-Mitglied → kein Schreiben.

Pflicht-Tests (AC1–AC5):
- AC2: propose → confirm: Task-Vorschlag beschreibt Ziel; nach Bestätigung schreibt
  execute entweder PATCH oder foto_overrides.json.
- AC5: tasks.py-Guard — essen+photo+fgcid → registriert; fehlt eines → nicht registriert.
"""

import contextlib
import json
import os
import tempfile

from fakes import FakeTelegram
from skills.essen_foto_setzen_task import EssenFotoSetzenTask
from tasks import (
    Proposal,
    TurnContext,
    WriteTask,
    build_catalog,
)

# ============================================================
#  Doppelungen
# ============================================================

class FakeTelegramMitDownload(FakeTelegram):
    """FakeTelegram + download_file-Stub (analog FSE-Task-Tests)."""

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


def _transport_stub_photo(post_status=200, post_body=None):
    """Erzeugt einen Transport-Stub für PhotoClient (PHOTO-13)."""
    calls = []
    if post_body is None:
        post_body = json.dumps({"id": "media-stub", "typ": "foto"}).encode("utf-8")

    def transport(method, path, *, body=None, content_type=None):
        calls.append({"method": method, "path": path})
        if method == "POST":
            return post_status, post_body
        return 204, b""

    return transport, calls


def _transport_stub_essen(patch_status=200, patch_body=None):
    """Erzeugt einen Transport-Stub für EssenClient (ESSEN-19a)."""
    calls = []
    if patch_body is None:
        patch_body = json.dumps(
            {"id": "g-1", "label": "Lasagne", "foto_ref": "media-stub"}
        ).encode("utf-8")

    def transport(method, path, *, body=None, content_type=None):
        calls.append({"method": method, "path": path})
        if method == "PATCH":
            return patch_status, patch_body
        return 200, json.dumps({}).encode("utf-8")

    return transport, calls


def _make_task(tg=None, essen_client=None, photo_client=None,
               family_group_chat_id_getter=None, is_member_fn=None,
               overrides_pfad=None):
    """Baut einen EssenFotoSetzenTask mit kontrollierten Doppelungen."""
    from skills.essen_client import EssenClient
    from skills.photo_client import PhotoClient

    if tg is None:
        tg = FakeTelegramMitDownload(members=_members(42))
    if essen_client is None:
        transport, _ = _transport_stub_essen()
        essen_client = EssenClient(
            origin_url="http://127.0.0.1:5052", transport=transport)
    if photo_client is None:
        transport, _ = _transport_stub_photo()
        photo_client = PhotoClient(
            origin_url="http://127.0.0.1:5070", transport=transport)
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    if is_member_fn is None:
        is_member_fn = _immer_mitglied
    return EssenFotoSetzenTask(
        tg=tg,
        essen_client=essen_client,
        photo_client=photo_client,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=is_member_fn,
        overrides_pfad=overrides_pfad,
    )


def _ctx(from_user_id=42, file_id=None, medium_typ="foto"):
    return TurnContext(
        chat_id=200, from_user_id=from_user_id, private_chat_id=from_user_id,
        media_telegram_file_id=file_id, medium_typ=medium_typ)


def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


# ============================================================
#  WriteTask-Klassifikation (EC-10)
# ============================================================

def test_EC10_ist_write_task():
    """EC-10: EssenFotoSetzenTask ist eine WriteTask (propose→confirm)."""
    task = _make_task()
    assert isinstance(task, WriteTask), (
        "EssenFotoSetzenTask muss WriteTask sein (EC-10)")


def test_task_name():
    """AC5: Task-Name ist 'essen_foto_setzen' (Catalog-Schlüssel)."""
    task = _make_task()
    assert task.name == "essen_foto_setzen"


# ============================================================
#  T777 / ESSEN-22 V1.1: Description-Schärfung
# ============================================================

def test_description_verlangt_vorab_katalog_lesen():
    """T777/AC4: EssenFotoSetzenTask.description verlangt ausdrücklich,
    ZUERST essen_katalog_lesen aufzurufen (ESSEN-22 V1.1 Vor-Routing)."""
    task = _make_task()
    desc = task.description
    assert "essen_katalog_lesen" in desc, (
        "Description muss 'essen_katalog_lesen' enthalten — Vor-Routing-Hinweis "
        "(T777/AC4)")
    assert "ZUERST" in desc or "zuerst" in desc.lower(), (
        "Description muss 'ZUERST' enthalten — LLM-Anweisung für Vor-Routing")


def test_description_gericht_id_aus_katalog():
    """T777/AC4: gericht_id-Property-Description verlangt essen_katalog_lesen-Quelle."""
    task = _make_task()
    gericht_id_desc = task.parameters["properties"]["gericht_id"]["description"]
    assert "essen_katalog_lesen" in gericht_id_desc, (
        "gericht_id-Description muss 'essen_katalog_lesen' als Quelle nennen")
    assert "erfundenen" in gericht_id_desc or "keine erfundenen" in gericht_id_desc, (
        "gericht_id-Description muss warnen: keine erfundenen IDs")


def test_description_item_id_aus_katalog():
    """T777/AC4: item_id-Property-Description verlangt essen_katalog_lesen-Quelle."""
    task = _make_task()
    item_id_desc = task.parameters["properties"]["item_id"]["description"]
    assert "essen_katalog_lesen" in item_id_desc, (
        "item_id-Description muss 'essen_katalog_lesen' als Quelle nennen")
    assert "erfundenen" in item_id_desc or "keine erfundenen" in item_id_desc, (
        "item_id-Description muss warnen: keine erfundenen IDs")


def test_task_hat_propose_und_execute():
    """EC-10: WriteTask hat propose() und execute()."""
    task = _make_task()
    assert hasattr(task, "propose")
    assert hasattr(task, "execute")


# ============================================================
#  AC2 — propose
# ============================================================

def test_AC2_propose_hochladen_gericht_nennt_ziel():
    """AC2: propose für 'hochladen' mit gericht_id → Vorschlag nennt Gericht-Ziel."""
    task = _make_task()
    p = task.propose(
        {"aktion": "hochladen", "gericht_id": "g-5"},
        _ctx())
    assert isinstance(p, Proposal)
    assert "g-5" in p.summary


def test_AC2_propose_hochladen_item_nennt_item():
    """AC2: propose für 'hochladen' mit item_id → Vorschlag nennt Item-Ziel."""
    task = _make_task()
    p = task.propose(
        {"aktion": "hochladen", "item_id": "obst:apfel"},
        _ctx())
    assert isinstance(p, Proposal)
    assert "obst:apfel" in p.summary


def test_propose_patch_gericht_nennt_aktion():
    """propose für 'patch_gericht' → Vorschlag nennt PATCH-Aktion."""
    task = _make_task()
    p = task.propose(
        {"aktion": "patch_gericht", "gericht_id": "g-5", "medien_id": "m-1"},
        _ctx())
    assert isinstance(p, Proposal)
    assert "g-5" in p.summary or "patch" in p.summary.lower()


def test_propose_abbruch_nennt_abbruch():
    """propose für 'abbruch' → Vorschlag nennt Abbruch."""
    task = _make_task()
    p = task.propose({"aktion": "abbruch"}, _ctx())
    assert isinstance(p, Proposal)
    assert "abbruch" in p.summary.lower() or "abbrechen" in p.summary.lower()


# ============================================================
#  AC2 — execute Hochladen (Schritt 1)
# ============================================================

def test_AC2_execute_hochladen_mit_file_id_postet_photo():
    """AC2 Schritt 1: execute('hochladen') mit file_id → POST an Photo-Buddy."""
    from skills.photo_client import PhotoClient

    photo_transport, photo_calls = _transport_stub_photo(
        post_body=json.dumps({"id": "m-high", "typ": "foto"}).encode("utf-8"))
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=photo_transport)
    tg = FakeTelegramMitDownload(file_bytes=b"JPEGDATA", members=_members(42))
    task = _make_task(tg=tg, photo_client=photo_client)

    quittung = task.execute(
        {"aktion": "hochladen", "gericht_id": "g-1"},
        _ctx(file_id="tg-photo-1"))

    assert tg.download_calls == ["tg-photo-1"]
    assert len(photo_calls) == 1
    assert photo_calls[0]["method"] == "POST"
    assert "m-high" in quittung


def test_execute_hochladen_ohne_file_id_ehrliche_grenze():
    """execute('hochladen') ohne file_id → ehrliche Grenze, kein POST."""
    from skills.photo_client import PhotoClient

    photo_transport, photo_calls = _transport_stub_photo()
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=photo_transport)
    tg = FakeTelegramMitDownload()
    task = _make_task(tg=tg, photo_client=photo_client)

    quittung = task.execute(
        {"aktion": "hochladen", "gericht_id": "g-1"},
        _ctx(file_id=None))

    assert quittung  # ehrliche Antwort
    assert photo_calls == [], "Kein POST ohne file_id"


def test_execute_hochladen_nicht_mitglied_kein_post():
    """Nicht-Mitglied → kein POST."""
    from skills.photo_client import PhotoClient

    photo_transport, photo_calls = _transport_stub_photo()
    photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=photo_transport)
    tg = FakeTelegramMitDownload(file_bytes=b"x")
    task = _make_task(
        tg=tg, photo_client=photo_client, is_member_fn=_kein_mitglied)

    quittung = task.execute(
        {"aktion": "hochladen", "gericht_id": "g-1"},
        _ctx(file_id="tg-1"))

    assert quittung
    assert photo_calls == []


# ============================================================
#  AC2 — execute PATCH (Schritt 2a)
# ============================================================

def test_AC2_execute_patch_gericht_ruft_essen_buddy():
    """AC2 Schritt 2a: execute('patch_gericht') → PATCH an Essen-Buddy."""
    from skills.essen_client import EssenClient

    essen_transport, essen_calls = _transport_stub_essen()
    essen_client = EssenClient(
        origin_url="http://127.0.0.1:5052", transport=essen_transport)
    task = _make_task(essen_client=essen_client)

    quittung = task.execute(
        {"aktion": "patch_gericht", "gericht_id": "g-5", "medien_id": "m-abc"},
        _ctx())

    patch_calls = [c for c in essen_calls if c["method"] == "PATCH"]
    assert len(patch_calls) == 1
    assert "g-5" in patch_calls[0]["path"]
    assert "g-5" in quittung
    assert "m-abc" in quittung


# ============================================================
#  AC2 — execute Override (Schritt 2b)
# ============================================================

def test_AC2_execute_schreibe_override_schreibt_datei():
    """AC2 Schritt 2b: execute('schreibe_override') → foto_overrides.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "foto_overrides.json")
        task = _make_task(overrides_pfad=pfad)

        quittung = task.execute(
            {"aktion": "schreibe_override",
             "item_id": "obst:birne",
             "medien_id": "m-birne"},
            _ctx())

        assert os.path.exists(pfad)
        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["obst:birne"] == "m-birne"
        assert "obst:birne" in quittung
        assert "m-birne" in quittung


# ============================================================
#  Abbruch-Pfad
# ============================================================

def test_execute_abbruch_gibt_quittung_ohne_schreiben():
    """Abbruch → ehrliche Quittung, kein POST, kein PATCH."""
    from skills.essen_client import EssenClient
    from skills.photo_client import PhotoClient

    photo_transport, photo_calls = _transport_stub_photo()
    essen_transport, essen_calls = _transport_stub_essen()
    task = _make_task(
        photo_client=PhotoClient(
            origin_url="http://127.0.0.1:5070", transport=photo_transport),
        essen_client=EssenClient(
            origin_url="http://127.0.0.1:5052", transport=essen_transport),
    )

    quittung = task.execute({"aktion": "abbruch"}, _ctx())

    assert quittung
    assert photo_calls == []
    assert essen_calls == []


# ============================================================
#  AC5 — Catalog-Registrierung (AND-Guard)
# ============================================================

def test_AC5_registriert_wenn_alle_drei_gesetzt():
    """AC5: EssenFotoSetzenTask erscheint im Catalog wenn essen+photo+fgcid gesetzt."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("essen_foto_setzen")
        assert task is not None, "EssenFotoSetzenTask sollte im Catalog sein"
        assert isinstance(task, WriteTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC5_nicht_registriert_ohne_essen_origin():
    """AC5: ohne essen_origin_url → nicht registriert."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            # essen_origin_url fehlt
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("essen_foto_setzen")
        assert task is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC5_nicht_registriert_ohne_photo_origin():
    """AC5: ohne photo_origin_url → nicht registriert."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            # photo_origin_url fehlt
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("essen_foto_setzen")
        assert task is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC5_nicht_registriert_ohne_fgcid():
    """AC5: ohne family_group_chat_id_getter → nicht registriert."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            photo_origin_url="http://127.0.0.1:5070",
            # family_group_chat_id_getter fehlt
        )
        task = catalog.get("essen_foto_setzen")
        assert task is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Kein-Match-Pfad (aus LLM-Klassifikation heraus)
# ============================================================

def test_execute_kein_gericht_id_ohne_item_id_ehrliche_grenze():
    """Weder gericht_id noch item_id in arguments → nichts_zu_tun-Quittung."""
    task = _make_task()
    quittung = task.execute(
        {"aktion": "patch_gericht"},  # gericht_id fehlt
        _ctx())
    assert quittung  # ehrliche Grenze, kein Crash


def test_propose_schreibe_override_nennt_item_und_medien():
    """propose für 'schreibe_override' mit item_id+medien_id → beide in Vorschlag."""
    task = _make_task()
    p = task.propose(
        {"aktion": "schreibe_override",
         "item_id": "obst:apfel",
         "medien_id": "m-99"},
        _ctx())
    assert isinstance(p, Proposal)
    assert "obst:apfel" in p.summary
    assert "m-99" in p.summary


# ============================================================
#  AC3 — Live-Pfad-Test: build_catalog reicht overrides_pfad durch (ESSEN-22)
# ============================================================

def test_live_pfad_basis_item_override_funktioniert(tmp_path, monkeypatch):
    """AC3: build_catalog übergibt ESSEN_FOTO_OVERRIDES_FILE an EssenFotoSetzenTask;
    execute('schreibe_override') schreibt tatsächlich an tmp_path — kein stilles NICHTS_ZU_TUN.

    Live-Naht: simuliert den echten build_catalog-Pfad mit allen AND-Guard-Argumenten
    + ESSEN_FOTO_OVERRIDES_FILE=<tmp_path>; greift den registrierten Task,
    ruft schreibe_override aus und prüft, dass die Datei existiert.
    """
    overrides_datei = tmp_path / "foto_overrides.json"
    monkeypatch.setenv(
        "ESSEN_FOTO_OVERRIDES_FILE", str(overrides_datei))

    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegramMitDownload(members=_members(42)),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=_family_getter(),
        )
    finally:
        import contextlib
        with contextlib.suppress(OSError):
            os.unlink(ca)

    task = catalog.get("essen_foto_setzen")
    assert task is not None, "EssenFotoSetzenTask muss im Catalog sein"

    # Prüfe via Reflection, dass overrides_pfad korrekt durchgereicht wurde.
    assert task._overrides_pfad == str(overrides_datei), (
        "build_catalog muss ESSEN_FOTO_OVERRIDES_FILE als overrides_pfad übergeben; "
        "war None → Live-NO-OP (Watchdog-Befund T531-S3b-FIX1/AC3)")

    # Führe schreibe_override aus und prüfe, dass die Datei am tmp_path erscheint.
    from skills.essen_client import EssenClient
    from skills.photo_client import PhotoClient
    photo_transport, _ = _transport_stub_photo()
    essen_transport, _ = _transport_stub_essen()

    # Ersetze Clients im Task durch Stubs (Reflection) — der Task ist schon
    # aus dem Catalog, wir wollen nur den Live-Pfad durch execute testen.
    task._photo_client = PhotoClient(
        origin_url="http://127.0.0.1:5070", transport=photo_transport)
    task._essen_client = EssenClient(
        origin_url="http://127.0.0.1:5052", transport=essen_transport)
    task._is_member_fn = _immer_mitglied

    quittung = task.execute(
        {"aktion": "schreibe_override",
         "item_id": "gemuese:karotte",
         "medien_id": "m-karotte"},
        _ctx())

    assert overrides_datei.exists(), (
        "foto_overrides.json muss am ENV-Pfad geschrieben sein — "
        "kein stilles NICHTS_ZU_TUN (ESSEN-22 Pfad 2 Basis-Item)")
    with open(overrides_datei, encoding="utf-8") as fh:
        import json as _json
        data = _json.load(fh)
    assert data.get("gemuese:karotte") == "m-karotte", (
        "Override-Eintrag muss item_id → medien_id enthalten")
    assert "gemuese:karotte" in quittung, "Quittung muss item_id nennen"
    assert "m-karotte" in quittung, "Quittung muss medien_id nennen"
