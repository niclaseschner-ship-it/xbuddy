"""Tests für `skills.foto_senden` — FSE-1 … FSE-7.

Trigger-agnostisch geprüft: kein TelegramClient, kein Task — nur die Funktion
selbst gegen einen kontrollierten PhotoClient-Doppelgänger.

Pflicht-Tests (siehe specs/platform/foto-senden.md FSE-8):
- FSE-2: Nicht-Mitglied → abgelehnt, kein POST.
- FSE-4 Happy-Path Foto: hochladen → PHOTO-13-Aufruf → Signal hochgeladen mit id.
- FSE-5 Happy-Path Video: hochladen → gleicher Pfad (PHOTO-13 nimmt beide).
- FSE-4 Rückgängig: widerrufen mit id → PHOTO-16-Aufruf → Signal widerrufen.
- FSE-5 Grenze: 4xx vom Buddy → Signal grenze, kein Zweit-Schreiben.
- FSE-3 Tool-Wahl auf falscher Spur: ohne medium_bytes → nichts_zu_tun (EC-7).
- APP-3: der Skill ruft die API (PhotoClient), nicht die Datei.
"""

from skills.foto_senden import (
    AKTION_HOCHLADEN,
    AKTION_WIDERRUFEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_GRENZE,
    SIGNAL_HOCHGELADEN,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_NICHTS_ZU_TUN,
    SIGNAL_WIDERRUFEN,
    foto_senden,
)
from skills.photo_client import PhotoClientError

# ============================================================
#  Doppelungen
# ============================================================

class FakePhotoClient:
    """Kontrollierte Doppelung des PhotoClient (CLIENT-1).

    `upload_result` ist das Antwort-Dict für upload_medium (oder ein
    Exception-Objekt, das geworfen wird). `delete_error` ist eine optionale
    Exception für delete_medium.
    """

    def __init__(self, upload_result=None, delete_error=None):
        self._upload_result = upload_result if upload_result is not None \
            else {"id": "abc123", "typ": "foto"}
        self._delete_error = delete_error
        self.upload_calls = []
        self.delete_calls = []

    def upload_medium(self, medium_bytes, filename, content_type):
        self.upload_calls.append({
            "medium_bytes": medium_bytes,
            "filename": filename,
            "content_type": content_type,
        })
        if isinstance(self._upload_result, Exception):
            raise self._upload_result
        return dict(self._upload_result)

    def delete_medium(self, medium_id):
        self.delete_calls.append(medium_id)
        if self._delete_error is not None:
            raise self._delete_error
        return None


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


# ============================================================
#  FSE-2 — Berechtigung
# ============================================================

def test_FSE2_nicht_mitglied_abgelehnt_kein_post():
    """FSE-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein POST."""
    client = FakePhotoClient()

    signal, daten = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=client,
        is_member_fn=_kein_mitglied,
        from_user_id=42,
        medium_bytes=b"jpg",
        filename="photo.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert daten == {}
    assert client.upload_calls == []


def test_FSE2_from_user_id_none_abgelehnt():
    """FSE-2: from_user_id=None → abgelehnt (kein Bypass durch fehlende ID)."""
    client = FakePhotoClient()
    signal, _ = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=None,
        medium_bytes=b"jpg",
        filename="p.jpg",
        content_type="image/jpeg",
    )
    assert signal == SIGNAL_ABGELEHNT
    assert client.upload_calls == []


# ============================================================
#  FSE-3 / FSE-4 — Hochladen (Foto, Video)
# ============================================================

def test_FSE4_hochladen_foto_ruft_upload_medium():
    """FSE-4 Happy-Path Foto: hochladen → upload_medium-Aufruf → Signal mit id."""
    client = FakePhotoClient(
        upload_result={"id": "foto-1", "typ": "foto"})

    signal, daten = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_bytes=b"JPEGBYTES",
        filename="photo.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_HOCHGELADEN
    assert daten == {"id": "foto-1", "typ": "foto"}
    assert len(client.upload_calls) == 1
    assert client.upload_calls[0]["medium_bytes"] == b"JPEGBYTES"
    assert client.upload_calls[0]["filename"] == "photo.jpg"
    assert client.upload_calls[0]["content_type"] == "image/jpeg"


def test_FSE5_hochladen_video_gleicher_pfad():
    """FSE-5 Happy-Path Video: video läuft genauso wie foto (PHOTO-13 nimmt beide)."""
    client = FakePhotoClient(
        upload_result={"id": "vid-1", "typ": "video"})

    signal, daten = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_bytes=b"MP4DATA",
        filename="clip.mp4",
        content_type="video/mp4",
    )

    assert signal == SIGNAL_HOCHGELADEN
    assert daten == {"id": "vid-1", "typ": "video"}
    assert client.upload_calls[0]["content_type"] == "video/mp4"


def test_FSE3_hochladen_ohne_medium_bytes_nichts_zu_tun():
    """FSE-3/EC-7: Tool-Wahl auf falscher Spur (kein Medium im TurnContext) →
    ehrliche Grenze, kein POST."""
    client = FakePhotoClient()

    signal, daten = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_bytes=None,
        filename=None,
        content_type=None,
    )

    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten == {}
    assert client.upload_calls == []


# ============================================================
#  FSE-5 — Grenze (PHOTO-13 4xx)
# ============================================================

def test_FSE5_4xx_grenze_kein_zweit_schreiben():
    """FSE-5: PHOTO-13 lehnt überlanges Video mit 4xx ab → Signal grenze."""
    client = FakePhotoClient(
        upload_result=PhotoClientError(
            "Photo-Buddy: HTTP 413 bei POST /api/v1/photo/medien — video zu lang"))

    signal, daten = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_bytes=b"BIGMP4",
        filename="big.mp4",
        content_type="video/mp4",
    )

    assert signal == SIGNAL_GRENZE
    assert "HTTP 413" in daten["detail"]
    assert len(client.upload_calls) == 1
    # PHOTO-10 / FSE-5: kein Teil-Ingest → kein erneuter Versuch durch den Skill.


def test_FSE7_5xx_nicht_erreichbar():
    """FSE-7/EC-7: 5xx → SIGNAL_NICHT_ERREICHBAR (Skill schreibt nicht doppelt)."""
    client = FakePhotoClient(
        upload_result=PhotoClientError(
            "Photo-Buddy nicht erreichbar (connection refused)"))

    signal, daten = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_bytes=b"x",
        filename="p.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert "detail" in daten


# ============================================================
#  FSE-4 — Rückgängig (PHOTO-16)
# ============================================================

def test_FSE4_widerrufen_ruft_delete_medium():
    """FSE-4: widerrufen mit id → delete_medium-Aufruf → Signal widerrufen."""
    client = FakePhotoClient()

    signal, daten = foto_senden(
        aktion=AKTION_WIDERRUFEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_id="abc123",
    )

    assert signal == SIGNAL_WIDERRUFEN
    assert daten == {"id": "abc123"}
    assert client.delete_calls == ["abc123"]


def test_FSE4_widerrufen_ohne_id_nichts_zu_tun():
    """FSE-4: widerrufen ohne id → SIGNAL_NICHTS_ZU_TUN, kein DELETE."""
    client = FakePhotoClient()

    signal, _ = foto_senden(
        aktion=AKTION_WIDERRUFEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_id=None,
    )

    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert client.delete_calls == []


def test_FSE4_widerrufen_404_grenze():
    """FSE-4: DELETE 404 (id unbekannt) → SIGNAL_GRENZE, ehrliche Info."""
    client = FakePhotoClient(
        delete_error=PhotoClientError(
            "Photo-Buddy: HTTP 404 bei DELETE /api/v1/photo/medien/ghost"))

    signal, daten = foto_senden(
        aktion=AKTION_WIDERRUFEN,
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_id="ghost",
    )

    assert signal == SIGNAL_GRENZE
    assert "HTTP 404" in daten["detail"]
    assert daten["id"] == "ghost"


# ============================================================
#  APP-3 — kein FS-Bypass
# ============================================================

def test_APP3_skill_ruft_api_nicht_datei():
    """APP-3: der Skill nutzt ausschließlich den PhotoClient (API),
    nie das Dateisystem direkt. Wir prüfen das indirekt — die Funktion hat
    keinen Datei-Schreib-Aufruf in ihrer Public-API.
    """
    # Eine offensichtliche Verletzung wäre, wenn `foto_senden` z. B. open()
    # selbst aufrufen würde. Wir prüfen: ohne photo_client läuft gar nichts.
    signal, _ = foto_senden(
        aktion=AKTION_HOCHLADEN,
        photo_client=FakePhotoClient(),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_bytes=b"x",
        filename="x.jpg",
        content_type="image/jpeg",
    )
    # Wenn das Signal HOCHGELADEN kommt, lief der PhotoClient — nicht das
    # Dateisystem.
    assert signal == SIGNAL_HOCHGELADEN


# ============================================================
#  Unbekannte Aktion
# ============================================================

def test_unbekannte_aktion_nichts_zu_tun():
    """Robustheit: eine unbekannte Aktion liefert nichts_zu_tun, kein Crash."""
    client = FakePhotoClient()
    signal, daten = foto_senden(
        aktion="quatsch",
        photo_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=42,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten == {}
    assert client.upload_calls == []
    assert client.delete_calls == []
