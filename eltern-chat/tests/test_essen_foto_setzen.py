"""Tests für `skills.essen_foto_setzen` — ESSEN-22 Pfad 2.

Trigger-agnostisch geprüft: kein TelegramClient, kein Task — nur die Funktion
selbst gegen kontrollierte Doppelungen von PhotoClient und EssenClient.

Pflicht-Tests (AC1–AC4):
- AC1: hochladen → PHOTO-13-Aufruf → Signal foto_hochgeladen mit medien_id
       und Ziel-Information.
- AC1: Berechtigung — Nicht-Mitglied → abgelehnt, kein POST.
- AC3: patch_gericht → EssenClient.patch_gericht_bild → Signal gericht_patch.
- AC4: schreibe_override → foto_overrides.json schreiben (merge, atomar).
- AC4: schreibe_override — fehlende Datei → anlegen.
- AC4: overrides_pfad=None → nichts_zu_tun.
- Grenze: 4xx vom Buddy → Signal grenze.
- Nicht erreichbar: Connection-Fehler → Signal nicht_erreichbar.
- Unbekannte Aktion → nichts_zu_tun.
- Abbruch-Aktion → nichts_zu_tun.
"""

import json
import os
import tempfile

from skills.essen_client import EssenClientError
from skills.essen_foto_setzen import (
    AKTION_ABBRUCH,
    AKTION_HOCHLADEN,
    AKTION_PATCH_GERICHT,
    AKTION_SCHREIBE_OVERRIDE,
    SIGNAL_ABGELEHNT,
    SIGNAL_FOTO_HOCHGELADEN,
    SIGNAL_GERICHT_PATCH,
    SIGNAL_GRENZE,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_NICHTS_ZU_TUN,
    SIGNAL_OVERRIDE_GESCHRIEBEN,
    SIGNAL_ZIEL_UNBEKANNT,
    essen_foto_setzen,
)
from skills.photo_client import PhotoClientError

# ============================================================
#  Doppelungen
# ============================================================

class FakePhotoClient:
    """Kontrollierte Doppelung des PhotoClient (CLIENT-1)."""

    def __init__(self, upload_result=None):
        self._upload_result = upload_result if upload_result is not None \
            else {"id": "media-1", "typ": "foto"}
        self.upload_calls = []

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
        pass


class FakeEssenClient:
    """Kontrollierte Doppelung des EssenClient (ESSEN-19a)."""

    def __init__(self, patch_result=None, patch_error=None):
        self._patch_result = patch_result if patch_result is not None \
            else {"id": "g-1", "label": "Lasagne", "foto_ref": "media-1"}
        self._patch_error = patch_error
        self.patch_calls = []

    def patch_gericht_bild(self, gericht_id, *, foto_ref=None, bild_ref=None):
        self.patch_calls.append({
            "gericht_id": gericht_id,
            "foto_ref": foto_ref,
            "bild_ref": bild_ref,
        })
        if self._patch_error is not None:
            raise self._patch_error
        return dict(self._patch_result)

    def lese_katalog(self):
        return []


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _gericht_ziel(gericht_id="g-1"):
    return {"typ": "gericht", "gericht_id": gericht_id}


def _item_ziel(item_id="obst:apfel"):
    return {"typ": "basis_item", "item_id": item_id}


# ============================================================
#  Berechtigung
# ============================================================

def test_berechtigung_nicht_mitglied_abgelehnt():
    """Nicht-Mitglied → SIGNAL_ABGELEHNT, kein POST."""
    photo = FakePhotoClient()
    essen = FakeEssenClient()

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        photo_client=photo,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_kein_mitglied,
        from_user_id=42,
        medium_bytes=b"JPEG",
        filename="foto.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_ABGELEHNT
    assert daten == {}
    assert photo.upload_calls == []


def test_berechtigung_from_user_id_none_abgelehnt():
    """from_user_id=None → abgelehnt."""
    photo = FakePhotoClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        photo_client=photo,
        essen_client=FakeEssenClient(),
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=None,
        medium_bytes=b"x",
        filename="f.jpg",
        content_type="image/jpeg",
    )
    assert signal == SIGNAL_ABGELEHNT
    assert photo.upload_calls == []


# ============================================================
#  AC1 — Hochladen (PHOTO-13)
# ============================================================

def test_AC1_hochladen_gericht_ziel_ruft_upload():
    """AC1: hochladen mit Gericht-Ziel → PHOTO-13-Aufruf → foto_hochgeladen."""
    photo = FakePhotoClient(upload_result={"id": "m-abc", "typ": "foto"})

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        photo_client=photo,
        essen_client=FakeEssenClient(),
        ziel=_gericht_ziel("g-42"),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"JPEGBYTES",
        filename="foto.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_FOTO_HOCHGELADEN
    assert daten["medien_id"] == "m-abc"
    assert daten["ziel"] == {"typ": "gericht", "gericht_id": "g-42"}
    assert len(photo.upload_calls) == 1
    assert photo.upload_calls[0]["medium_bytes"] == b"JPEGBYTES"


def test_AC1_hochladen_item_ziel_gibt_item_zurueck():
    """AC1: hochladen mit Basis-Item-Ziel → Ziel korrekt in daten."""
    photo = FakePhotoClient(upload_result={"id": "m-xyz", "typ": "foto"})

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        photo_client=photo,
        essen_client=FakeEssenClient(),
        ziel=_item_ziel("obst:apfel"),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"JPEGDATA",
        filename="foto.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_FOTO_HOCHGELADEN
    assert daten["medien_id"] == "m-xyz"
    assert daten["ziel"] == {"typ": "basis_item", "item_id": "obst:apfel"}


def test_hochladen_ohne_bytes_nichts_zu_tun():
    """Kein Medium → nichts_zu_tun (analog FSE-3)."""
    photo = FakePhotoClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        photo_client=photo,
        essen_client=FakeEssenClient(),
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=None,
        filename=None,
        content_type=None,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert photo.upload_calls == []


def test_hochladen_4xx_grenze():
    """PHOTO-13 4xx → Signal grenze."""
    photo = FakePhotoClient(
        upload_result=PhotoClientError(
            "Photo-Buddy: HTTP 413 bei POST /api/v1/photo/medien — zu groß"))

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        photo_client=photo,
        essen_client=FakeEssenClient(),
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"BIG",
        filename="big.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_GRENZE
    assert "HTTP 413" in daten["detail"]


def test_hochladen_connection_nicht_erreichbar():
    """Connection-Fehler → Signal nicht_erreichbar."""
    photo = FakePhotoClient(
        upload_result=PhotoClientError("Photo-Buddy nicht erreichbar"))

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        photo_client=photo,
        essen_client=FakeEssenClient(),
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"x",
        filename="f.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert "detail" in daten


# ============================================================
#  AC3 — patch_gericht (ESSEN-19a)
# ============================================================

def test_AC3_patch_gericht_ruft_patch_gericht_bild():
    """AC3: patch_gericht → EssenClient.patch_gericht_bild → gericht_patch."""
    essen = FakeEssenClient()

    signal, daten = essen_foto_setzen(
        aktion=AKTION_PATCH_GERICHT,
        photo_client=FakePhotoClient(),
        essen_client=essen,
        ziel=_gericht_ziel("g-7"),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medien_id="media-99",
    )

    assert signal == SIGNAL_GERICHT_PATCH
    assert daten["gericht_id"] == "g-7"
    assert daten["medien_id"] == "media-99"
    assert len(essen.patch_calls) == 1
    assert essen.patch_calls[0]["gericht_id"] == "g-7"
    assert essen.patch_calls[0]["foto_ref"] == "media-99"


def test_AC3_patch_gericht_4xx_grenze():
    """ESSEN-19a 4xx → Signal grenze."""
    essen = FakeEssenClient(
        patch_error=EssenClientError(
            "Essens-Buddy: HTTP 404 bei PATCH /api/v1/essen/katalog/gerichte/x"))

    signal, daten = essen_foto_setzen(
        aktion=AKTION_PATCH_GERICHT,
        photo_client=FakePhotoClient(),
        essen_client=essen,
        ziel=_gericht_ziel("x"),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medien_id="m-1",
    )

    assert signal == SIGNAL_GRENZE
    assert "HTTP 404" in daten["detail"]


def test_patch_gericht_ohne_medien_id_nichts_zu_tun():
    """Ohne medien_id → nichts_zu_tun, kein PATCH."""
    essen = FakeEssenClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_PATCH_GERICHT,
        photo_client=FakePhotoClient(),
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medien_id=None,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert essen.patch_calls == []


def test_patch_gericht_falscher_ziel_typ_ziel_unbekannt():
    """Ziel-typ != 'gericht' → ziel_unbekannt."""
    essen = FakeEssenClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_PATCH_GERICHT,
        photo_client=FakePhotoClient(),
        essen_client=essen,
        ziel=_item_ziel("obst:apfel"),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medien_id="m-1",
    )
    assert signal == SIGNAL_ZIEL_UNBEKANNT
    assert essen.patch_calls == []


# ============================================================
#  AC4 — schreibe_override (foto_overrides.json)
# ============================================================

def test_AC4_schreibe_override_erstellt_datei_und_mergt():
    """AC4: schreibe_override → foto_overrides.json anlegen (merge)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "foto_overrides.json")

        signal, daten = essen_foto_setzen(
            aktion=AKTION_SCHREIBE_OVERRIDE,
            photo_client=FakePhotoClient(),
            essen_client=FakeEssenClient(),
            ziel=_item_ziel("obst:apfel"),
            is_member_fn=_immer_mitglied,
            from_user_id=42,
            medien_id="m-42",
            overrides_pfad=pfad,
        )

        assert signal == SIGNAL_OVERRIDE_GESCHRIEBEN
        assert daten["item_id"] == "obst:apfel"
        assert daten["medien_id"] == "m-42"
        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["obst:apfel"] == "m-42"


def test_AC4_schreibe_override_mergt_bestehende_eintraege():
    """AC4: schreibe_override mergt vorhandene Einträge — kein Verlust."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "foto_overrides.json")
        # Vorhandenen Eintrag anlegen.
        with open(pfad, "w", encoding="utf-8") as fh:
            json.dump({"brotbelag:butter": "old-media"}, fh)

        essen_foto_setzen(
            aktion=AKTION_SCHREIBE_OVERRIDE,
            photo_client=FakePhotoClient(),
            essen_client=FakeEssenClient(),
            ziel=_item_ziel("obst:apfel"),
            is_member_fn=_immer_mitglied,
            from_user_id=42,
            medien_id="m-new",
            overrides_pfad=pfad,
        )

        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
        # Bestehender Eintrag darf nicht verloren gehen.
        assert data["brotbelag:butter"] == "old-media"
        assert data["obst:apfel"] == "m-new"


def test_AC4_schreibe_override_toleriert_fehlende_datei():
    """AC4: fehlende foto_overrides.json → anlegen ohne Fehler."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "sub", "foto_overrides.json")
        # sub/ existiert noch nicht.

        signal, _ = essen_foto_setzen(
            aktion=AKTION_SCHREIBE_OVERRIDE,
            photo_client=FakePhotoClient(),
            essen_client=FakeEssenClient(),
            ziel=_item_ziel("sonstiges:milch"),
            is_member_fn=_immer_mitglied,
            from_user_id=42,
            medien_id="m-milk",
            overrides_pfad=pfad,
        )

        assert signal == SIGNAL_OVERRIDE_GESCHRIEBEN
        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["sonstiges:milch"] == "m-milk"


def test_AC4_schreibe_override_ohne_pfad_nichts_zu_tun():
    """AC4: overrides_pfad=None → nichts_zu_tun, kein Schreiben."""
    signal, _ = essen_foto_setzen(
        aktion=AKTION_SCHREIBE_OVERRIDE,
        photo_client=FakePhotoClient(),
        essen_client=FakeEssenClient(),
        ziel=_item_ziel("obst:apfel"),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medien_id="m-1",
        overrides_pfad=None,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN


def test_schreibe_override_ohne_medien_id_nichts_zu_tun():
    """Ohne medien_id → nichts_zu_tun."""
    signal, _ = essen_foto_setzen(
        aktion=AKTION_SCHREIBE_OVERRIDE,
        photo_client=FakePhotoClient(),
        essen_client=FakeEssenClient(),
        ziel=_item_ziel("obst:apfel"),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medien_id=None,
        overrides_pfad="/tmp/x.json",
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN


def test_schreibe_override_falscher_ziel_typ_ziel_unbekannt():
    """Ziel-typ != 'basis_item' → ziel_unbekannt, kein Schreiben."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "foto_overrides.json")
        signal, _ = essen_foto_setzen(
            aktion=AKTION_SCHREIBE_OVERRIDE,
            photo_client=FakePhotoClient(),
            essen_client=FakeEssenClient(),
            ziel=_gericht_ziel("g-1"),
            is_member_fn=_immer_mitglied,
            from_user_id=42,
            medien_id="m-1",
            overrides_pfad=pfad,
        )
        assert signal == SIGNAL_ZIEL_UNBEKANNT
        assert not os.path.exists(pfad)


# ============================================================
#  Abbruch / unbekannte Aktion
# ============================================================

def test_abbruch_aktion_nichts_zu_tun():
    """Abbruch-Aktion → nichts_zu_tun, kein API-Aufruf."""
    photo = FakePhotoClient()
    essen = FakeEssenClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_ABBRUCH,
        photo_client=photo,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert photo.upload_calls == []
    assert essen.patch_calls == []


def test_unbekannte_aktion_nichts_zu_tun():
    """Unbekannte Aktion → nichts_zu_tun, kein Crash."""
    photo = FakePhotoClient()
    signal, daten = essen_foto_setzen(
        aktion="quatsch",
        photo_client=photo,
        essen_client=FakeEssenClient(),
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten == {}
    assert photo.upload_calls == []
