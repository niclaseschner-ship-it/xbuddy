"""Tests für GerichtAnlegenTask — GAN-7, AC1–AC5 des T627-Contracts.

Pflicht-Tests (Spec GAN-7 + AC aus Contract T627-S1):
- Katalog enthält 'gericht_anlegen' genau dann, wenn essen_origin_url
  UND icon_origin_url UND family_group_chat_id_getter gesetzt sind (Guard, AC5).
- GerichtAnlegenTask ist ein WriteTask (EC-10).
- Task-Name ist 'gericht_anlegen'.
- propose() liefert Proposal mit Label + Icon-ID.
- execute() ruft POST nach Bestätigung.
- propose() schreibt NICHT (E-GAN-2).
- Icon-Suche → Album-Senden + Mapping-Quittung (GAN-4/TASK-10b).
- IconAlbumError → NICHT_ERREICHBAR-Quittung.
- Nicht-Mitglied → kein Schreiben (GAN-2).
- Buddy-409 → ehrliche Grenze-Quittung (GAN-5).
"""

import contextlib
import json
import os
import tempfile
import unittest.mock as mock

from fakes import FakeTelegram
from skills.essen_client import EssenClientError
from skills.gericht_anlegen import (
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
)
from skills.gericht_anlegen_task import GerichtAnlegenTask
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Doppelungen
# ============================================================

class FakeTelegramMitAlbum(FakeTelegram):
    """FakeTelegram mit send_photo + send_media_group für icon_album-Tests.

    send_photo-Aufrufe landen in `photos`, send_media_group-Aufrufe
    in `media_groups` — jeweils mit allen Argumenten, damit Tests die
    Reihenfolge und Anzahl prüfen können.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.photos = []          # [{chat_id, file_name, file_bytes, caption}]
        self.media_groups = []    # [{chat_id, items}]

    def send_photo(self, chat_id, file_name, file_bytes, caption=None):
        self.photos.append({
            "chat_id": chat_id,
            "file_name": file_name,
            "file_bytes": file_bytes,
            "caption": caption,
        })
        return {"message_id": 9000 + len(self.photos)}

    def send_media_group(self, chat_id, items):
        self.media_groups.append({"chat_id": chat_id, "items": list(items)})
        return [{"message_id": 9100 + i} for i in range(len(items))]


class FakeEssenClient:
    def __init__(self, post_response=None, post_error=None):
        self.post_calls = []
        self._post_response = post_response or {"id": "1"}
        self._post_error = post_error

    def post_gericht(self, name, icon_id=None, foto_ref=None):
        self.post_calls.append({"name": name, "icon_id": icon_id,
                                "foto_ref": foto_ref})
        if self._post_error is not None:
            raise self._post_error
        return dict(self._post_response)


class FakeIconClient:
    def __init__(self, response=None, error=None):
        self.suche_calls = []
        self._response = response if response is not None else []
        self._error = error

    def suche(self, stichwort, max_treffer=3):
        self.suche_calls.append({
            "stichwort": stichwort, "max_treffer": max_treffer})
        if self._error is not None:
            raise self._error
        return list(self._response)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


class FakePhotoClient:
    """PhotoClient-Doppelung für GAN-Tests (ESSEN-22 Pfad 1)."""

    def __init__(self, upload_response=None, upload_error=None):
        self.upload_calls = []
        self._upload_response = upload_response or {"id": "foto-42", "typ": "image"}
        self._upload_error = upload_error

    def upload_medium(self, medium_bytes, filename, content_type):
        self.upload_calls.append({
            "medium_bytes": medium_bytes,
            "filename": filename,
            "content_type": content_type,
        })
        if self._upload_error is not None:
            raise self._upload_error
        return dict(self._upload_response)


def _make_task(essen_client=None, icon_client=None, photo_client=None,
               is_member_fn=None, tg=None, icon_origin_url="http://icons.test"):
    return GerichtAnlegenTask(
        tg=tg or FakeTelegramMitAlbum(),
        essen_client=essen_client or FakeEssenClient(),
        icon_client=icon_client or FakeIconClient(),
        photo_client=photo_client or FakePhotoClient(),
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=is_member_fn or _immer_mitglied,
        icon_origin_url=icon_origin_url,
    )


def _ctx(chat_id=42):
    return TurnContext(chat_id=chat_id, from_user_id=7, private_chat_id=42)


# ============================================================
#  Task-Klassifikation + Grundeigenschaften
# ============================================================

def test_GAN7_ist_write_task():
    """GAN-7: GerichtAnlegenTask ist ein WriteTask (EC-10)."""
    assert isinstance(_make_task(), WriteTask)


def test_GAN7_name():
    """GAN-7: Task-Name ist 'gericht_anlegen' (Catalog-Schlüssel)."""
    assert _make_task().name == "gericht_anlegen"


def test_GAN7_ist_sync():
    """GAN-7: is_async=False — V1 synchron (analog RPS-7), kein Worker."""
    assert _make_task().is_async is False


def test_GAN7_keine_post_execute_hooks():
    """GAN-7: keine Hooks (Essens-Buddy hat Reload-on-Read, ESSEN-20)."""
    assert _make_task().post_execute_hooks == ()


# ============================================================
#  propose() — E-GAN-2 / GAN-5
# ============================================================

def test_E_GAN2_propose_liefert_konkreten_vorschlag():
    """E-GAN-2 / GAN-5: propose nennt Label + Icon-ID (Ein-Schritt-Vorschlag)."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)
    proposal = task.propose({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }, ctx)
    assert isinstance(proposal, Proposal)
    assert "Lasagne" in proposal.summary
    assert "9999" in proposal.summary


def test_E_GAN2_propose_icon_suchen_lesend():
    """E-GAN-2: propose für icon_suchen nennt 'nur lesend, nichts schreiben'."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)
    proposal = task.propose({
        "aktion": AKTION_ICON_SUCHEN,
        "icon_stichwort": "Lasagne",
    }, ctx)
    assert isinstance(proposal, Proposal)
    # Soll deutlich machen, dass kein Schreiben passiert
    assert "lesend" in proposal.summary.lower() or "schreib" in proposal.summary.lower()


# ============================================================
#  execute(): vollständige Kette propose → execute → POST
# ============================================================

def test_VS_propose_schreibt_nicht():
    """E-GAN-2: propose() schreibt NICHTS (Vorschlag-Phase, kein Effekt)."""
    ec = FakeEssenClient(post_response={"id": "1"})
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    args = {
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }

    task.propose(args, ctx)

    assert ec.post_calls == [], "propose schreibt NICHTS (E-GAN-2)"


def test_VS_execute_ruft_post():
    """GAN-3: execute() ruft POST /api/v1/essen/katalog/gerichte."""
    ec = FakeEssenClient(post_response={"id": "42"})
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    args = {
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }

    quittung = task.execute(args, ctx)

    assert ec.post_calls == [{"name": "Lasagne", "icon_id": "9999", "foto_ref": None}]
    # Quittung enthält die ID (D6-Muster)
    assert "42" in quittung


def test_VS_nicht_mitglied_execute_kein_post():
    """GAN-2: Nicht-Mitglied → execute schreibt NICHT."""
    ec = FakeEssenClient()
    task = _make_task(essen_client=ec, is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=99)

    quittung = task.execute({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }, ctx)

    assert ec.post_calls == []
    assert "Familien-Gruppe" in quittung or "Mitglied" in quittung


def test_VS_buddy_409_grenze_quittung():
    """GAN-5: Buddy-409 → Quittung enthält ehrliche Grenz-Meldung."""
    ec = FakeEssenClient(
        post_error=EssenClientError(
            "Essens-Buddy: HTTP 409 bei POST /api/v1/essen/katalog/gerichte "
            "— Gericht existiert bereits"))
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.execute({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }, ctx)

    assert len(ec.post_calls) == 1
    # Quittung nennt die Ablehnung
    assert "abgelehnt" in quittung.lower() or "409" in quittung or "bereits" in quittung


def test_VS_keine_icons_quittung():
    """GAN-4: Icon-Suche ohne Treffer → Quittung fragt nach anderem Wort."""
    ic = FakeIconClient(response=[])
    task = _make_task(icon_client=ic)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.execute({
        "aktion": AKTION_ICON_SUCHEN,
        "icon_stichwort": "GlubschaugenGericht",
    }, ctx)

    assert "gefunden" in quittung.lower() or "anderes" in quittung.lower()


# ============================================================
#  AC1 + AC2: Mapping-Quittung + Album-Senden (TASK-10b)
# ============================================================

def test_AC1_quittung_traegt_mapping_form_drei_kandidaten():
    """AC1: Quittung trägt Mapping-Form '1 = <id>, 2 = <id>, 3 = <id>'
    für drei Kandidaten (TASK-10b, GAN-4)."""
    kandidaten = [
        {"id": 2349, "url": "/icons/2349.png"},
        {"id": 8800, "url": "/icons/8800.png"},
        {"id": 7777, "url": "/icons/7777.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://icons.test")

    # icon_album._holen mocken, damit kein Netz nötig.
    with mock.patch("skills.icon_album._holen",
                    side_effect=lambda url, opener=None: b"fakepng"):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Lasagne",
        }, _ctx())

    # Mapping-Form: 1 = 2349, 2 = 8800, 3 = 7777
    assert "1 = 2349" in quittung
    assert "2 = 8800" in quittung
    assert "3 = 7777" in quittung
    assert "Piktogramm-Kandidaten" in quittung
    assert "als Bilder geschickt" in quittung
    assert "Antworte mit der ID" in quittung


def test_AC2_album_helper_wird_vor_quittung_aufgerufen():
    """AC2: icon_album.zeige_kandidaten wird aufgerufen (TASK-10b); die
    Quittung trägt das Mapping. Mock/Spy auf zeige_kandidaten."""
    kandidaten = [
        {"id": 2349, "url": "/icons/2349.png"},
        {"id": 8800, "url": "/icons/8800.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://icons.test")

    call_args = []

    def fake_zeige(tg_arg, chat_id_arg, kand_arg, origin_arg):
        call_args.append({
            "chat_id": chat_id_arg,
            "kandidaten": kand_arg,
            "origin": origin_arg,
        })

    with mock.patch("skills.gericht_anlegen_task.icon_album"
                    ".zeige_kandidaten", side_effect=fake_zeige):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Pizza",
        }, _ctx(chat_id=42))

    assert len(call_args) == 1, "zeige_kandidaten genau einmal aufgerufen"
    assert call_args[0]["chat_id"] == 42
    assert call_args[0]["origin"] == "http://icons.test"
    assert len(call_args[0]["kandidaten"]) == 2

    # Quittung trägt Mapping
    assert "1 = 2349" in quittung
    assert "2 = 8800" in quittung


def test_AC2_album_helper_argumente_korrekt():
    """AC2: zeige_kandidaten erhält tg, chat_id, kandidaten UND icon_origin_url
    in der richtigen Reihenfolge (TASK-10b Signatur-Prüfung)."""
    kandidaten = [{"id": 111, "url": "/a.png"}, {"id": 222, "url": "/b.png"}]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg,
                      icon_origin_url="http://origin.test:5000")

    received = {}

    def spy(tg_arg, chat_id_arg, kand_arg, origin_arg):
        received["tg"] = tg_arg
        received["chat_id"] = chat_id_arg
        received["kandidaten"] = kand_arg
        received["origin"] = origin_arg

    with mock.patch("skills.gericht_anlegen_task.icon_album"
                    ".zeige_kandidaten", side_effect=spy):
        task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Suppe",
        }, _ctx(chat_id=99))

    assert received["tg"] is tg
    assert received["chat_id"] == 99
    assert received["kandidaten"] == kandidaten
    assert received["origin"] == "http://origin.test:5000"


# ============================================================
#  AC1: Ein Kandidat → send_photo; drei → send_media_group
# ============================================================

def test_AC1_ein_kandidat_mapping_und_send_photo():
    """AC1 + AC2: 1 Kandidat → Mapping '1 = <id>', send_photo wird aufgerufen.

    end-to-end durch den echten Helper mit FakeTelegramMitAlbum +
    _holen-Mock (kein Netz).
    """
    kandidaten = [{"id": 5555, "url": "/icons/5555.png"}]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://ico.test")

    with mock.patch("skills.icon_album._holen",
                    return_value=b"fakepng"):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Kuchen",
        }, _ctx())

    # Genau ein send_photo, kein send_media_group
    assert len(tg.photos) == 1
    assert tg.media_groups == []
    assert tg.photos[0]["chat_id"] == 42
    assert tg.photos[0]["caption"] is None  # TASK-10b: keine Caption
    assert "1 = 5555" in quittung


def test_AC1_drei_kandidaten_send_media_group():
    """AC1 + AC2: 3 Kandidaten → send_media_group (end-to-end, FakeTG +
    _holen-Mock)."""
    kandidaten = [
        {"id": 1, "url": "/a.png"},
        {"id": 2, "url": "/b.png"},
        {"id": 3, "url": "/c.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://ico.test")

    with mock.patch("skills.icon_album._holen",
                    return_value=b"fakepng"):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Pasta",
        }, _ctx())

    # send_media_group mit 3 Items
    assert tg.photos == []
    assert len(tg.media_groups) == 1
    grp = tg.media_groups[0]
    assert grp["chat_id"] == 42
    assert len(grp["items"]) == 3
    # Captions sind alle None (TASK-10b)
    for _fname, _fbytes, fcaption in grp["items"]:
        assert fcaption is None

    # Mapping in Quittung
    assert "1 = 1" in quittung
    assert "2 = 2" in quittung
    assert "3 = 3" in quittung


# ============================================================
#  Fehlerfall: IconAlbumError → QUITTUNG_NICHT_ERREICHBAR
# ============================================================

def test_album_fehler_liefert_nicht_erreichbar_quittung():
    """GAN-4 / TASK-10b: wenn zeige_kandidaten IconAlbumError wirft,
    gibt execute() die NICHT_ERREICHBAR-Quittung zurück (kein Crash)."""
    from skills.icon_album import IconAlbumError

    kandidaten = [
        {"id": 100, "url": "/x.png"},
        {"id": 200, "url": "/y.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg)

    with mock.patch("skills.gericht_anlegen_task.icon_album"
                    ".zeige_kandidaten",
                    side_effect=IconAlbumError("Netz weg")):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Salat",
        }, _ctx())

    assert "nicht erreichbar" in quittung.lower()


# ============================================================
#  AC3: Konstruktor nimmt icon_origin_url; tasks.py reicht durch
# ============================================================

def test_AC3_konstruktor_speichert_icon_origin_url():
    """AC3: GerichtAnlegenTask-Konstruktor nimmt icon_origin_url
    und macht ihn als _icon_origin_url verfügbar."""
    task = _make_task(icon_origin_url="http://test-origin:5001")
    assert task._icon_origin_url == "http://test-origin:5001"


def test_AC3_konstruktor_ohne_icon_origin_url_ist_leer():
    """AC3: ohne icon_origin_url (Rückwärtskompatibilität) → leerer String."""
    task = GerichtAnlegenTask(
        tg=FakeTelegramMitAlbum(),
        essen_client=FakeEssenClient(),
        icon_client=FakeIconClient(),
        photo_client=FakePhotoClient(),
        family_group_chat_id_getter=lambda: 200,
    )
    assert task._icon_origin_url == ""


def test_AC_foto_konstruktor_speichert_photo_client():
    """ESSEN-22 Pfad 1: Konstruktor speichert photo_client als _photo_client."""
    pc = FakePhotoClient()
    task = _make_task(photo_client=pc)
    assert task._photo_client is pc


# ============================================================
#  ESSEN-22 Pfad 1: foto_hinzufuegen Task-Tests
# ============================================================

class FakeTelegramMitDownload(FakeTelegramMitAlbum):
    """FakeTelegram mit download_file für foto_hinzufuegen-Tests."""

    def __init__(self, file_bytes=None, download_error=None, **kw):
        super().__init__(**kw)
        self._file_bytes = file_bytes or b"\xff\xd8\xff\x00" * 10
        self._download_error = download_error
        self.download_calls = []

    def download_file(self, file_id):
        self.download_calls.append(file_id)
        if self._download_error is not None:
            raise self._download_error
        return self._file_bytes


def _ctx_foto(chat_id=42, file_id="tg-file-123", medium_typ="photo"):
    ctx = TurnContext(chat_id=chat_id, from_user_id=7, private_chat_id=42)
    ctx.media_telegram_file_id = file_id
    ctx.medium_typ = medium_typ
    return ctx


def test_FOTO_happy_path_execute_angelegt():
    """ESSEN-22 Pfad 1: execute(foto_hinzufuegen) → Upload + POST → Quittung mit ID."""
    foto_bytes = b"\xff\xd8\xff\x00" * 5
    tg = FakeTelegramMitDownload(file_bytes=foto_bytes)
    pc = FakePhotoClient(upload_response={"id": "foto-7"})
    ec = FakeEssenClient(post_response={"id": "42"})
    task = _make_task(tg=tg, photo_client=pc, essen_client=ec)

    quittung = task.execute({"aktion": "foto_hinzufuegen", "label": "Lasagne"},
                            _ctx_foto(file_id="tg-123"))

    assert "42" in quittung
    assert len(tg.download_calls) == 1
    assert tg.download_calls[0] == "tg-123"
    assert len(pc.upload_calls) == 1
    assert pc.upload_calls[0]["medium_bytes"] == foto_bytes
    assert len(ec.post_calls) == 1
    assert ec.post_calls[0]["foto_ref"] == "foto-7"


def test_FOTO_kein_file_id_nichts_zu_tun():
    """ESSEN-22 Pfad 1: kein file_id im TurnContext → Quittung kein Label/Foto."""
    tg = FakeTelegramMitDownload()
    task = _make_task(tg=tg)

    ctx = TurnContext(chat_id=42, from_user_id=7)
    # media_telegram_file_id nicht gesetzt
    quittung = task.execute({"aktion": "foto_hinzufuegen", "label": "Lasagne"}, ctx)

    assert tg.download_calls == []
    # Quittung fragt nach Inhalt
    assert quittung


def test_FOTO_download_fehler_nicht_erreichbar():
    """ESSEN-22 Pfad 1: Download-Fehler → NICHT_ERREICHBAR-Quittung."""
    tg = FakeTelegramMitDownload(download_error=OSError("Timeout"))
    task = _make_task(tg=tg)

    quittung = task.execute({"aktion": "foto_hinzufuegen", "label": "Lasagne"},
                            _ctx_foto())

    assert "nicht erreichbar" in quittung.lower()


def test_FOTO_propose_nennt_label():
    """ESSEN-22 Pfad 1: propose(foto_hinzufuegen) nennt Label."""
    task = _make_task()
    proposal = task.propose({"aktion": "foto_hinzufuegen", "label": "Lasagne"},
                            _ctx())
    assert isinstance(proposal, Proposal)
    assert "Lasagne" in proposal.summary


def test_FOTO_nicht_mitglied_kein_upload():
    """GAN-2 / ESSEN-22 Pfad 1: Nicht-Mitglied → kein Upload, Ablehnung."""
    foto_bytes = b"\xff\xd8" * 5
    tg = FakeTelegramMitDownload(file_bytes=foto_bytes)
    pc = FakePhotoClient()
    task = _make_task(tg=tg, photo_client=pc, is_member_fn=_kein_mitglied)

    quittung = task.execute({"aktion": "foto_hinzufuegen", "label": "Lasagne"},
                            _ctx_foto())

    assert pc.upload_calls == []
    assert "Familien-Gruppe" in quittung or "Mitglied" in quittung


def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_AC3_build_catalog_reicht_icon_origin_url_durch():
    """AC3: tasks.build_catalog reicht icon_origin_url an GerichtAnlegenTask durch."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegramMitAlbum(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            icon_origin_url="http://127.0.0.1:5000",
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("gericht_anlegen")
        assert task is not None
        assert task._icon_origin_url == "http://127.0.0.1:5000"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC_build_catalog_injiziert_photo_client():
    """ESSEN-22 Pfad 1: tasks.build_catalog injiziert photo_client in GerichtAnlegenTask."""
    from skills.photo_client import PhotoClient
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegramMitAlbum(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            icon_origin_url="http://127.0.0.1:5000",
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("gericht_anlegen")
        assert task is not None
        assert isinstance(task._photo_client, PhotoClient)
        assert task._photo_client._origin == "http://127.0.0.1:5070"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Catalog-Registrierung (AND-Guard, GAN-7)
# ============================================================

def test_GAN7_guard_alle_vier_gesetzt_registriert():
    """GAN-7 / AC5 (ESSEN-22 Pfad 1): Task erscheint im Katalog genau dann, wenn
    essen_origin_url UND icon_origin_url UND photo_origin_url UND
    family_group_chat_id_getter ALLE gesetzt sind."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            icon_origin_url="http://127.0.0.1:5000",
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("gericht_anlegen")
        assert task is not None
        assert isinstance(task, WriteTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_ohne_essen_origin_nicht_registriert():
    """GAN-7 Guard: ohne essen_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            icon_origin_url="http://127.0.0.1:5000",
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("gericht_anlegen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_ohne_icon_origin_nicht_registriert():
    """GAN-7 Guard: ohne icon_origin_url → keine Registrierung
    (E-GAN-3 — der Skill braucht die zentrale Icon-Suche)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            photo_origin_url="http://127.0.0.1:5070",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("gericht_anlegen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_ohne_photo_origin_nicht_registriert():
    """GAN-7 Guard (ESSEN-22 Pfad 1): ohne photo_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("gericht_anlegen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_ohne_fgcid_nicht_registriert():
    """GAN-7 Guard: ohne family_group_chat_id_getter → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            icon_origin_url="http://127.0.0.1:5000",
            photo_origin_url="http://127.0.0.1:5070",
        )
        assert catalog.get("gericht_anlegen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_build_catalog_signatur_kompatibel():
    """GAN-7 / additiv: build_catalog(tg, ca_pem_path) bleibt
    rückwärtskompatibel — essen_origin_url ist optional (Default None)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(tg=FakeTelegram(), ca_pem_path=ca)
        assert catalog.get("gericht_anlegen") is None
        assert catalog.get("ca_verteilen") is not None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  AC5: Andere Pfade — unangetastet (Smoke-Tests)
# ============================================================

def test_AC5_hinzufuegen_unberuehrt():
    """AC5: HINZUFUEGEN-Pfad bleibt unangetastet — kein Album-Aufruf."""
    tg = FakeTelegramMitAlbum()
    task = _make_task(tg=tg)
    quittung = task.execute({
        "aktion": "hinzufuegen",
        "label": "Lasagne",
        "icon_id": "9999",
    }, _ctx())
    assert tg.photos == []
    assert tg.media_groups == []
    # Quittung gehört zum Hinzufügen-Pfad
    assert "aufgenommen" in quittung.lower() or "sichtbar" in quittung.lower()


# ============================================================
#  Mapping-Quittung bei leerem kandidaten-Fall (defensiver Fallback)
# ============================================================

def test_mapping_fallback_bei_leer_kandidaten():
    """Defensiver Fallback: wenn das Signal ICON_KANDIDATEN mit leerer Liste
    käme (sollte nicht passieren), liefert die Quittung einen brauchbaren
    Text statt eines leeren Strings."""
    from skills.gericht_anlegen import SIGNAL_ICON_KANDIDATEN
    from skills.gericht_anlegen_task import _quittung_fuer

    quittung = _quittung_fuer(
        SIGNAL_ICON_KANDIDATEN,
        {"label": "Test", "kandidaten": []},
        aktion=AKTION_ICON_SUCHEN,
    )
    assert "Test" in quittung
    assert quittung  # nicht leer


# ============================================================
#  Entry-Path-Test: Catalog → Task → Transport-Stub (AC3)
# ============================================================

def test_VS_entry_path_catalog_to_post_via_transport_stub():
    """Entry-Path-Probe: build_catalog → Task → POST über den
    echten EssenClient mit Transport-Stub (CLIENT-1)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(members={7: {"status": "member"}}),
            ca_pem_path=ca,
            essen_origin_url="http://example",
            icon_origin_url="http://example",
            photo_origin_url="http://example",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("gericht_anlegen")
        assert isinstance(task, GerichtAnlegenTask)

        # Transport-Stub in den EssenClient einsetzen.
        post_calls = []
        def transport(method, path, *, body=None, content_type=None):
            post_calls.append({"method": method, "path": path, "body": body})
            return 201, json.dumps({"id": "1"}).encode("utf-8")
        task._essen_client._transport = transport

        ctx = TurnContext(chat_id=200, from_user_id=7, private_chat_id=7)
        task.execute({
            "aktion": AKTION_HINZUFUEGEN,
            "label": "Lasagne",
            "icon_id": "9999",
        }, ctx)

        assert len(post_calls) == 1
        assert post_calls[0]["method"] == "POST"
        assert post_calls[0]["path"] == "/api/v1/essen/katalog/gerichte"
        payload = json.loads(post_calls[0]["body"].decode("utf-8"))
        assert payload == {"label": "Lasagne", "bild_ref": "9999"}
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)
