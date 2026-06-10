"""Tests für skills/icon_album.py — ID-Wahl-Album-Helper (TASK-10b).

Geprüft wird:
- Trefferzahl-Fallback: 0 → no-op, 1 → send_photo, 2/3 → send_media_group
- Reihenfolge der Kandidaten 1:1 erhalten (TASK-10b Reihenfolge-Klausel)
- Captions werden IMMER None gesetzt (TASK-10b Caption-Verbot)
- URL-Konsum: icon_origin_url + kandidat['url'] werden korrekt konkateniert
- HTTP-Fehler beim Holen eines Bildes → IconAlbumError
"""

import urllib.error

import pytest
from skills.icon_album import IconAlbumError, zeige_kandidaten

# ============================================================
#  Test-Doppelungen
# ============================================================

class FakeTelegram:
    """Minimale TG-Doppelung: zeichnet send_photo + send_media_group auf."""

    def __init__(self):
        self.photos = []       # Liste von (chat_id, file_name, file_bytes, caption)
        self.albums = []       # Liste von (chat_id, items)

    def send_photo(self, chat_id, file_name, file_bytes, caption=None):
        self.photos.append((chat_id, file_name, file_bytes, caption))
        return {"message_id": 1}

    def send_media_group(self, chat_id, items):
        self.albums.append((chat_id, list(items)))
        return [{"message_id": 1}]


class FakeOpener:
    """HTTP-Opener-Stub: liefert skriptierte Bytes für jeden open()-Aufruf."""

    def __init__(self, responses):
        """responses: Liste von bytes-Objekten, die der Reihe nach geliefert werden.
        Ein Exception-Objekt wird stattdessen geworfen."""
        self._responses = list(responses)
        self.urls = []

    def open(self, url):
        self.urls.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeHTTPResponse(item)


class _FakeHTTPResponse:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


def _kandidat(icon_id, url):
    return {"id": icon_id, "url": url}


# ============================================================
#  Trefferzahl-Fallback
# ============================================================

def test_zero_treffer_macht_nichts():
    """0 Kandidaten → no-op; kein TG-Call (TASK-10b)."""
    tg = FakeTelegram()
    opener = FakeOpener([])

    zeige_kandidaten(tg, chat_id=42, kandidaten=[],
                     icon_origin_url="https://heim:8443", opener=opener)

    assert tg.photos == []
    assert tg.albums == []
    assert opener.urls == []


def test_ein_treffer_ruft_send_photo():
    """1 Kandidat → tg.send_photo wird aufgerufen (TASK-10b)."""
    tg = FakeTelegram()
    opener = FakeOpener([b"PNG1"])
    kandidaten = [_kandidat(2326, "/display/_shared/icons/arasaac/2326.png")]

    zeige_kandidaten(tg, chat_id=42, kandidaten=kandidaten,
                     icon_origin_url="https://heim:8443", opener=opener)

    assert len(tg.photos) == 1
    assert tg.albums == []
    _, _file_name, file_bytes, caption = tg.photos[0]
    assert file_bytes == b"PNG1"
    assert caption is None, "TASK-10b: kein Caption bei Einzel-Foto"


def test_zwei_treffer_ruft_send_media_group():
    """2 Kandidaten → tg.send_media_group wird aufgerufen (TASK-10b)."""
    tg = FakeTelegram()
    opener = FakeOpener([b"PNG1", b"PNG2"])
    kandidaten = [
        _kandidat(100, "/icons/100.png"),
        _kandidat(200, "/icons/200.png"),
    ]

    zeige_kandidaten(tg, chat_id=42, kandidaten=kandidaten,
                     icon_origin_url="https://heim:8443", opener=opener)

    assert tg.photos == []
    assert len(tg.albums) == 1
    _, items = tg.albums[0]
    assert len(items) == 2


def test_drei_treffer_ruft_send_media_group():
    """3 Kandidaten → tg.send_media_group wird aufgerufen (TASK-10b)."""
    tg = FakeTelegram()
    opener = FakeOpener([b"PNG1", b"PNG2", b"PNG3"])
    kandidaten = [
        _kandidat(1, "/icons/1.png"),
        _kandidat(2, "/icons/2.png"),
        _kandidat(3, "/icons/3.png"),
    ]

    zeige_kandidaten(tg, chat_id=42, kandidaten=kandidaten,
                     icon_origin_url="https://heim:8443", opener=opener)

    assert tg.photos == []
    assert len(tg.albums) == 1
    _, items = tg.albums[0]
    assert len(items) == 3


# ============================================================
#  Reihenfolge-Invariante (TASK-10b Reihenfolge-Klausel)
# ============================================================

def test_reihenfolge_erhalten():
    """Kandidaten-Reihenfolge 1:1 erhalten — Position 0 → Item 0 im Album."""
    tg = FakeTelegram()
    opener = FakeOpener([b"ALPHA", b"BETA", b"GAMMA"])
    kandidaten = [
        _kandidat("alpha", "/icons/alpha.png"),
        _kandidat("beta",  "/icons/beta.png"),
        _kandidat("gamma", "/icons/gamma.png"),
    ]

    zeige_kandidaten(tg, chat_id=1, kandidaten=kandidaten,
                     icon_origin_url="https://heim:8443", opener=opener)

    _, items = tg.albums[0]
    # file_bytes stimmt mit der Reihenfolge überein.
    assert items[0][1] == b"ALPHA", "Position 0 muss Kandidat 0 sein"
    assert items[1][1] == b"BETA",  "Position 1 muss Kandidat 1 sein"
    assert items[2][1] == b"GAMMA", "Position 2 muss Kandidat 2 sein"


# ============================================================
#  Caption-Verbot (TASK-10b)
# ============================================================

def test_keine_captions_im_album():
    """Alle Album-Items haben caption=None (TASK-10b Caption-Verbot)."""
    tg = FakeTelegram()
    opener = FakeOpener([b"PNG1", b"PNG2"])
    kandidaten = [
        _kandidat(10, "/icons/10.png"),
        _kandidat(20, "/icons/20.png"),
    ]

    zeige_kandidaten(tg, chat_id=1, kandidaten=kandidaten,
                     icon_origin_url="https://heim:8443", opener=opener)

    _, items = tg.albums[0]
    for file_name, _file_bytes, caption in items:
        assert caption is None, (
            "TASK-10b: kein Caption erlaubt, war %r bei %s" % (caption, file_name))


# ============================================================
#  URL-Konsum
# ============================================================

def test_url_konsum_mit_origin():
    """HTTP-Fetch auf icon_origin_url + kandidat['url'] konkateniert (TASK-10b)."""
    tg = FakeTelegram()
    opener = FakeOpener([b"PNG1"])
    kandidaten = [_kandidat(2326, "/display/_shared/icons/arasaac/2326.png")]

    zeige_kandidaten(tg, chat_id=1, kandidaten=kandidaten,
                     icon_origin_url="https://heim:8443", opener=opener)

    assert len(opener.urls) == 1
    assert opener.urls[0] == (
        "https://heim:8443/display/_shared/icons/arasaac/2326.png"
    ), "URL muss origin + relativer Pfad sein, war: %r" % opener.urls[0]


def test_url_konsum_trailing_slash_in_origin():
    """Trailing-Slash in icon_origin_url wird korrekt entfernt (kein //). """
    tg = FakeTelegram()
    opener = FakeOpener([b"PNG1"])
    kandidaten = [_kandidat(1, "/icons/1.png")]

    zeige_kandidaten(tg, chat_id=1, kandidaten=kandidaten,
                     icon_origin_url="https://heim:8443/", opener=opener)

    assert opener.urls[0] == "https://heim:8443/icons/1.png"


# ============================================================
#  HTTP-Fehler → IconAlbumError
# ============================================================

def test_http_fehler_wirft_IconAlbumError():
    """HTTP-Fehler beim Holen eines Bildes → IconAlbumError (TASK-10b)."""
    tg = FakeTelegram()
    err = urllib.error.URLError("connection refused")
    opener = FakeOpener([err])
    kandidaten = [_kandidat(99, "/icons/99.png")]

    with pytest.raises(IconAlbumError):
        zeige_kandidaten(tg, chat_id=1, kandidaten=kandidaten,
                         icon_origin_url="https://heim:8443", opener=opener)


def test_http_fehler_bei_erstem_von_mehreren_wirft_IconAlbumError():
    """HTTP-Fehler beim ersten Bild in einem Album → IconAlbumError."""
    tg = FakeTelegram()
    err = urllib.error.URLError("timeout")
    opener = FakeOpener([err, b"PNG2"])
    kandidaten = [
        _kandidat(1, "/icons/1.png"),
        _kandidat(2, "/icons/2.png"),
    ]

    with pytest.raises(IconAlbumError):
        zeige_kandidaten(tg, chat_id=1, kandidaten=kandidaten,
                         icon_origin_url="https://heim:8443", opener=opener)
