"""Tests für `skills.essen_foto_setzen` — ESSEN-22 Pfad 2, atomar (T782).

Trigger-agnostisch geprüft: kein TelegramClient, kein Task — nur die Funktion
selbst gegen kontrollierte Doppelungen von EssenClient.

Welle 2 von #804: Upload geht jetzt über essen_client.post_foto,
nicht mehr über photo_client.upload_medium.

Pflicht-Tests (AC1–AC4):
- AC1: hochladen + Gericht-Ziel → Upload UND PATCH in EINEM Aufruf.
- AC1: hochladen + Basis-Item-Ziel → Upload UND Override-Schreiben in EINEM Aufruf.
- AC1: Berechtigung — Nicht-Mitglied → abgelehnt, kein POST.
- AC3: Quittung Gericht — 'Foto bei Gericht … gesetzt', kein 'Bestätige mit...'.
- AC3: Quittung Item — 'Foto bei Item … hinterlegt', kein 'Bestätige mit...'.
- AC4: Essen-Buddy-Fehler → kein PATCH-Aufruf.
- AC4: Upload OK, PATCH 400 → klare Fehlerquittung, kein halber Zustand.
- Ziel-leer nach Upload → SIGNAL_ZIEL_UNBEKANNT (Upload bereits passiert).
- Override-Schreiben (merge, atomar).
- Fehlende Datei → anlegen.
- overrides_pfad=None → nichts_zu_tun.
- Grenze: 4xx vom Essen-Buddy → Signal grenze.
- Nicht erreichbar: Connection-Fehler → Signal nicht_erreichbar.
- Abbruch-Aktion → abgebrochen.
- Unbekannte Aktion → nichts_zu_tun.
"""

import json
import os
import tempfile

from skills.essen_client import EssenClientError
from skills.essen_foto_setzen import (
    AKTION_ABBRUCH,
    AKTION_HOCHLADEN,
    SIGNAL_ABGEBROCHEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_GERICHT_PATCH,
    SIGNAL_GRENZE,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_NICHTS_ZU_TUN,
    SIGNAL_OVERRIDE_GESCHRIEBEN,
    SIGNAL_ZIEL_UNBEKANNT,
    essen_foto_setzen,
)

# ============================================================
#  Doppelungen
# ============================================================

class FakeEssenClient:
    """Kontrollierte Doppelung des EssenClient (ESSEN-19a + ESSEN-22 V1.2)."""

    def __init__(self, post_foto_result=None, post_foto_error=None,
                 patch_result=None, patch_error=None):
        self._post_foto_result = post_foto_result if post_foto_result is not None \
            else "media-1"
        self._post_foto_error = post_foto_error
        self._patch_result = patch_result if patch_result is not None \
            else {"id": "g-1", "label": "Lasagne", "foto_ref": "media-1"}
        self._patch_error = patch_error
        self.post_foto_calls = []
        self.patch_calls = []

    def post_foto(self, rohbytes, dateiname, content_type="image/jpeg"):
        self.post_foto_calls.append({
            "rohbytes": rohbytes,
            "dateiname": dateiname,
            "content_type": content_type,
        })
        if self._post_foto_error is not None:
            raise self._post_foto_error
        return self._post_foto_result

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
    """Nicht-Mitglied → SIGNAL_ABGELEHNT, kein Foto-Upload."""
    essen = FakeEssenClient()

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
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
    assert essen.post_foto_calls == []


def test_berechtigung_from_user_id_none_abgelehnt():
    """from_user_id=None → abgelehnt."""
    essen = FakeEssenClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=None,
        medium_bytes=b"x",
        filename="f.jpg",
        content_type="image/jpeg",
    )
    assert signal == SIGNAL_ABGELEHNT
    assert essen.post_foto_calls == []


# ============================================================
#  AC1 — Atomar: hochladen + Gericht → Upload UND PATCH
# ============================================================

def test_atomar_gericht_setzt_foto_ref():
    """AC1: hochladen mit Gericht-Ziel → Upload + PATCH in EINEM Aufruf (ESSEN-22 V1.2)."""
    essen = FakeEssenClient(post_foto_result="m-abc")

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_gericht_ziel("g-42"),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"JPEGBYTES",
        filename="foto.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_GERICHT_PATCH
    assert daten["gericht_id"] == "g-42"
    assert daten["medien_id"] == "m-abc"
    # Upload via essen_client.post_foto muss aufgerufen worden sein.
    assert len(essen.post_foto_calls) == 1
    assert essen.post_foto_calls[0]["rohbytes"] == b"JPEGBYTES"
    assert essen.post_foto_calls[0]["dateiname"] == "foto.jpg"
    # PATCH muss aufgerufen worden sein.
    assert len(essen.patch_calls) == 1
    assert essen.patch_calls[0]["gericht_id"] == "g-42"
    assert essen.patch_calls[0]["foto_ref"] == "m-abc"


def test_atomar_basis_item_schreibt_override():
    """AC1: hochladen mit Basis-Item-Ziel → Upload + Override in EINEM Aufruf."""
    essen = FakeEssenClient(post_foto_result="m-xyz")

    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "foto_overrides.json")

        signal, daten = essen_foto_setzen(
            aktion=AKTION_HOCHLADEN,
            essen_client=essen,
            ziel=_item_ziel("obst:apfel"),
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            medium_bytes=b"JPEGDATA",
            filename="foto.jpg",
            content_type="image/jpeg",
            overrides_pfad=pfad,
        )

    assert signal == SIGNAL_OVERRIDE_GESCHRIEBEN
    assert daten["item_id"] == "obst:apfel"
    assert daten["medien_id"] == "m-xyz"
    # Upload via essen_client.post_foto muss aufgerufen worden sein.
    assert len(essen.post_foto_calls) == 1
    # Kein PATCH für Basis-Item.
    assert essen.patch_calls == []


def test_hochladen_ohne_bytes_nichts_zu_tun():
    """Kein Medium → nichts_zu_tun (analog FSE-3)."""
    essen = FakeEssenClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=None,
        filename=None,
        content_type=None,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert essen.post_foto_calls == []


# ============================================================
#  AC3 — Quittungen: keine 'Bestätige mit...'-Phrase
# ============================================================

def test_quittung_gericht_format():
    """AC3: nach hochladen+Gericht → Quittung enthält gericht_id + medien_id,
    kein 'Bestätige mit...'-Text."""
    from skills import essen_foto_setzen as efs_mod
    from skills.essen_foto_setzen_task import _quittung_fuer

    quittung = _quittung_fuer(
        efs_mod.SIGNAL_GERICHT_PATCH,
        {"gericht_id": "g-7", "medien_id": "m-99"})

    assert "g-7" in quittung
    assert "m-99" in quittung
    assert "Bestätige" not in quittung
    assert "bestätige" not in quittung.lower()


def test_quittung_item_format():
    """AC3: nach hochladen+Item → Quittung enthält item_id + medien_id,
    kein 'Bestätige mit...'-Text."""
    from skills import essen_foto_setzen as efs_mod
    from skills.essen_foto_setzen_task import _quittung_fuer

    quittung = _quittung_fuer(
        efs_mod.SIGNAL_OVERRIDE_GESCHRIEBEN,
        {"item_id": "obst:birne", "medien_id": "m-birne"})

    assert "obst:birne" in quittung
    assert "m-birne" in quittung
    assert "Bestätige" not in quittung
    assert "bestätige" not in quittung.lower()


# ============================================================
#  AC4 — Fehler-Pfade: klare Quittung, kein halber Zustand
# ============================================================

def test_essen_foto_fehler_kein_patch():
    """AC4: Essen-Buddy-Upload-Fehler → kein PATCH-Aufruf."""
    essen = FakeEssenClient(
        post_foto_error=EssenClientError("Essen-Buddy nicht erreichbar"))

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"x",
        filename="f.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert "detail" in daten
    # Kein PATCH — Upload ist schon fehlgeschlagen.
    assert essen.patch_calls == []


def test_essen_fehler_nach_upload_klare_quittung():
    """AC4: Upload OK, PATCH 400 → klare Fehlerquittung."""
    essen = FakeEssenClient(
        post_foto_result="m-ok",
        patch_error=EssenClientError(
            "Essens-Buddy: HTTP 404 bei PATCH /api/v1/essen/katalog/gerichte/x"))

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_gericht_ziel("x"),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"FOTO",
        filename="foto.jpg",
        content_type="image/jpeg",
    )

    # Upload war OK (PATCH ist fehlgeschlagen).
    assert len(essen.post_foto_calls) == 1
    # Klare Fehlerquittung.
    assert signal == SIGNAL_GRENZE
    assert "HTTP 404" in daten["detail"]


def test_hochladen_4xx_grenze():
    """Essen-Buddy 4xx bei Upload → Signal grenze, kein PATCH."""
    essen = FakeEssenClient(
        post_foto_error=EssenClientError(
            "Essens-Buddy: HTTP 413 bei POST /api/v1/essen/fotos — zu groß"))

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"BIG",
        filename="big.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_GRENZE
    assert "HTTP 413" in daten["detail"]
    assert essen.patch_calls == []


def test_hochladen_connection_nicht_erreichbar():
    """Connection-Fehler → Signal nicht_erreichbar, kein PATCH."""
    essen = FakeEssenClient(
        post_foto_error=EssenClientError("Essen-Buddy nicht erreichbar"))

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"x",
        filename="f.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert "detail" in daten
    assert essen.patch_calls == []


# ============================================================
#  Ziel-leer nach Upload → SIGNAL_ZIEL_UNBEKANNT
# ============================================================

def test_hochladen_leeres_ziel_nach_upload_ziel_unbekannt():
    """Upload OK, aber Ziel leer → SIGNAL_ZIEL_UNBEKANNT (medien_id im Payload)."""
    essen = FakeEssenClient(post_foto_result="m-1")

    signal, daten = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel={},
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        medium_bytes=b"DATA",
        filename="foto.jpg",
        content_type="image/jpeg",
    )

    assert signal == SIGNAL_ZIEL_UNBEKANNT
    assert daten.get("medien_id") == "m-1"
    assert essen.patch_calls == []


# ============================================================
#  Override-Schreiben (merge, atomar)
# ============================================================

def test_atomar_schreibe_override_erstellt_datei_und_mergt():
    """hochladen+Item → foto_overrides.json anlegen (merge)."""
    essen = FakeEssenClient(post_foto_result="m-42")

    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "foto_overrides.json")

        signal, daten = essen_foto_setzen(
            aktion=AKTION_HOCHLADEN,
            essen_client=essen,
            ziel=_item_ziel("obst:apfel"),
            is_member_fn=_immer_mitglied,
            from_user_id=42,
            medium_bytes=b"FOTO",
            filename="foto.jpg",
            content_type="image/jpeg",
            overrides_pfad=pfad,
        )

        assert signal == SIGNAL_OVERRIDE_GESCHRIEBEN
        assert daten["item_id"] == "obst:apfel"
        assert daten["medien_id"] == "m-42"
        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["obst:apfel"] == "m-42"


def test_atomar_schreibe_override_mergt_bestehende_eintraege():
    """hochladen+Item mergt vorhandene Einträge — kein Verlust."""
    essen = FakeEssenClient(post_foto_result="m-new")

    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "foto_overrides.json")
        # Vorhandenen Eintrag anlegen.
        with open(pfad, "w", encoding="utf-8") as fh:
            json.dump({"brotbelag:butter": "old-media"}, fh)

        essen_foto_setzen(
            aktion=AKTION_HOCHLADEN,
            essen_client=essen,
            ziel=_item_ziel("obst:apfel"),
            is_member_fn=_immer_mitglied,
            from_user_id=42,
            medium_bytes=b"FOTO",
            filename="foto.jpg",
            content_type="image/jpeg",
            overrides_pfad=pfad,
        )

        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
        # Bestehender Eintrag darf nicht verloren gehen.
        assert data["brotbelag:butter"] == "old-media"
        assert data["obst:apfel"] == "m-new"


def test_atomar_schreibe_override_toleriert_fehlende_datei():
    """Fehlende foto_overrides.json → anlegen ohne Fehler."""
    essen = FakeEssenClient(post_foto_result="m-milk")

    with tempfile.TemporaryDirectory() as tmpdir:
        pfad = os.path.join(tmpdir, "sub", "foto_overrides.json")
        # sub/ existiert noch nicht.

        signal, _ = essen_foto_setzen(
            aktion=AKTION_HOCHLADEN,
            essen_client=essen,
            ziel=_item_ziel("sonstiges:milch"),
            is_member_fn=_immer_mitglied,
            from_user_id=42,
            medium_bytes=b"FOTO",
            filename="foto.jpg",
            content_type="image/jpeg",
            overrides_pfad=pfad,
        )

        assert signal == SIGNAL_OVERRIDE_GESCHRIEBEN
        with open(pfad, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["sonstiges:milch"] == "m-milk"


def test_hochladen_item_ziel_ohne_overrides_pfad_nichts_zu_tun():
    """hochladen+Item ohne overrides_pfad → nichts_zu_tun (Upload trotzdem passiert)."""
    essen = FakeEssenClient(post_foto_result="m-1")

    signal, _ = essen_foto_setzen(
        aktion=AKTION_HOCHLADEN,
        essen_client=essen,
        ziel=_item_ziel("obst:apfel"),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
        medium_bytes=b"FOTO",
        filename="foto.jpg",
        content_type="image/jpeg",
        overrides_pfad=None,
    )
    # Upload passiert, aber ohne Pfad kann nicht geschrieben werden.
    assert len(essen.post_foto_calls) == 1
    assert signal == SIGNAL_NICHTS_ZU_TUN


# ============================================================
#  Abbruch / unbekannte Aktion
# ============================================================

def test_abbruch_aktion_abgebrochen():
    """Abbruch-Aktion → abgebrochen, kein API-Aufruf."""
    essen = FakeEssenClient()
    signal, _ = essen_foto_setzen(
        aktion=AKTION_ABBRUCH,
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
    )
    assert signal == SIGNAL_ABGEBROCHEN
    assert essen.post_foto_calls == []
    assert essen.patch_calls == []


def test_unbekannte_aktion_nichts_zu_tun():
    """Unbekannte Aktion → nichts_zu_tun, kein Crash."""
    essen = FakeEssenClient()
    signal, daten = essen_foto_setzen(
        aktion="quatsch",
        essen_client=essen,
        ziel=_gericht_ziel(),
        is_member_fn=_immer_mitglied,
        from_user_id=42,
    )
    assert signal == SIGNAL_NICHTS_ZU_TUN
    assert daten == {}
    assert essen.post_foto_calls == []
