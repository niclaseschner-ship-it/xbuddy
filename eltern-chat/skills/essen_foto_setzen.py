"""Essens-Foto setzen — specs/buddies/essen.md (ESSEN-22 Pfad 2).

Aufrufbare, trigger-agnostische Funktion (analog FSE-1 / E-RZS-1-Muster):
nimmt Foto-Bytes + Ziel-Information (Gericht-ID ODER Basis-Item-ID) und ruft
zuerst Photo-Buddy (PHOTO-13) und dann — je nach Ziel — entweder
ESSEN-19a (PATCH /api/v1/essen/katalog/gerichte/<id>) oder schreibt in
xbuddy-data/essen/foto_overrides.json.

ESSEN-22 Pfad 2 atomar (E-EC-7): EIN Confirm pro Operation.
aktion='hochladen' führt Upload + Schreiben in EINEM Schritt durch:
- Photo-Buddy Upload (PHOTO-13)
- je nach ziel.typ: PATCH ESSEN-19a (Gericht) ODER Override-JSON schreiben (Basis-Item)
Kein zweistufiges propose→Schritt2-Confirm mehr.

Ziel-Dict-Form:
  {"typ": "gericht",    "gericht_id": "<id>"}
  {"typ": "basis_item", "item_id": "<id>"}

Override-Schreib-Pfad als Parameter (kein Modul-Default — analog S2-Fix):
der Task setzt `overrides_pfad` auf den echten xbuddy-data-Pfad, Tests
übergeben einen Tmp-Pfad.

Ausgang: Ergebnis-Tuple `(signal, daten)`:
  (SIGNAL_GERICHT_PATCH,          {"gericht_id": <str>, "medien_id": <str>})
                                  — Upload + PATCH ESSEN-19a erfolgreich.
  (SIGNAL_OVERRIDE_GESCHRIEBEN,   {"item_id": <str>, "medien_id": <str>})
                                  — Upload + foto_overrides.json geschrieben.
  (SIGNAL_ZIEL_UNBEKANNT,         {"medien_id": <str>})
                                  — Upload ok, aber Ziel-typ nicht erkannt.
  (SIGNAL_ABGELEHNT,              {})
                                  — Nicht-Mitglied.
  (SIGNAL_GRENZE,                 {"detail": <str>})
                                  — 4xx vom Buddy (ESSEN-19a / PHOTO-13).
  (SIGNAL_NICHT_ERREICHBAR,       {"detail": <str>})
                                  — Buddy nicht erreichbar.
  (SIGNAL_NICHTS_ZU_TUN,          {})
                                  — Eingabe unvollständig / unbekannte Aktion.
  (SIGNAL_ABGEBROCHEN,            {})
                                  — aktion='abbruch'.
"""

import json
import logging
import os

from skills.essen_client import EssenClientError
from skills.photo_client import PhotoClientError

logger = logging.getLogger(__name__)


# ESSEN-22 / FSE-1: Ergebnis-Signale.
SIGNAL_GERICHT_PATCH        = "gericht_patch"
SIGNAL_OVERRIDE_GESCHRIEBEN = "override_geschrieben"
SIGNAL_ABGELEHNT            = "abgelehnt"
SIGNAL_GRENZE               = "grenze"
SIGNAL_NICHT_ERREICHBAR     = "nicht_erreichbar"
SIGNAL_NICHTS_ZU_TUN        = "nichts_zu_tun"
SIGNAL_ZIEL_UNBEKANNT       = "ziel_unbekannt"
SIGNAL_ABGEBROCHEN          = "abgebrochen"

# Aktionen (atomar: hochladen macht Upload+Schreiben in einem Schritt).
AKTION_HOCHLADEN            = "hochladen"
AKTION_ABBRUCH              = "abbruch"

# Rückwärtskompatible Aliasse für Test-Naht (nicht als öffentliche Skill-Aktionen).
AKTION_PATCH_GERICHT        = "patch_gericht"
AKTION_SCHREIBE_OVERRIDE    = "schreibe_override"


def essen_foto_setzen(*, aktion, photo_client, essen_client, ziel,
                      is_member_fn, from_user_id,
                      medium_bytes=None, filename=None, content_type=None,
                      medien_id=None, overrides_pfad=None):
    """Essens-Foto setzen — aufrufbare Funktion (ESSEN-22 Pfad 2, atomar).

    aktion='hochladen': Upload an Photo-Buddy + sofort Schreiben je ziel.typ.
    EIN Confirm pro Operation (E-EC-7) — kein zweiter Tool-Call mehr nötig.

    Parameter:
      `aktion`          — AKTION_HOCHLADEN / AKTION_ABBRUCH.
      `photo_client`    — PhotoClient-Instanz (PHOTO-13).
      `essen_client`    — EssenClient-Instanz (ESSEN-19a).
      `ziel`            — Dict {"typ": "gericht", "gericht_id": "..."}
                          ODER {"typ": "basis_item", "item_id": "..."}.
      `is_member_fn`    — Callable `(user_id) -> bool`.
      `from_user_id`    — Telegram-User-ID des Aufrufers.

      Bei AKTION_HOCHLADEN:
        `medium_bytes`  — Foto-Bytes (JPEG/PNG).
        `filename`      — Dateiname für multipart-Header.
        `content_type`  — MIME-Typ.
        `overrides_pfad` — absoluter Pfad zu foto_overrides.json
                           (bei Basis-Item-Ziel erforderlich).

    Ergebnis: (signal, daten) — siehe Modul-Docstring.
    """
    # Berechtigung — live geprüft, identisch zum FSE-/RZS-Muster (EC-2).
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "essen_foto_setzen: User %s ist kein Familienmitglied — abgelehnt",
            from_user_id)
        return SIGNAL_ABGELEHNT, {}

    if aktion == AKTION_HOCHLADEN:
        return _hochladen_und_schreiben(
            photo_client, essen_client, ziel,
            medium_bytes, filename, content_type, overrides_pfad)

    if aktion == AKTION_ABBRUCH:
        logger.info("essen_foto_setzen: Abbruch durch Benutzer")
        return SIGNAL_ABGEBROCHEN, {}

    logger.warning("essen_foto_setzen: unbekannte Aktion %r — nichts zu tun",
                   aktion)
    return SIGNAL_NICHTS_ZU_TUN, {}


def _hochladen_und_schreiben(photo_client, essen_client, ziel,
                              medium_bytes, filename, content_type,
                              overrides_pfad):
    """Upload an Photo-Buddy + sofort Schreiben je ziel.typ (atomar, ESSEN-22).

    Ohne Medien-Bytes ist nichts zu tun (Modell hat das Tool auf falscher
    Spur gerufen — analog FSE-3).
    """
    if not medium_bytes:
        return SIGNAL_NICHTS_ZU_TUN, {}

    # Schritt 1: Upload an Photo-Buddy (PHOTO-13).
    try:
        response = photo_client.upload_medium(
            medium_bytes=medium_bytes,
            filename=filename or "foto.jpg",
            content_type=content_type or "image/jpeg",
        )
    except PhotoClientError as e:
        fehler_str = str(e)
        if "HTTP 4" in fehler_str:
            logger.info("essen_foto_setzen: PHOTO-13 hat Medium abgelehnt — %s",
                        e)
            return SIGNAL_GRENZE, {"detail": fehler_str}
        logger.warning("essen_foto_setzen: Photo-Buddy nicht erreichbar — %s",
                       e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}

    medien_id = response.get("id")
    logger.info("essen_foto_setzen: hochgeladen medien_id=%s ziel=%r",
                medien_id, ziel)

    # Schritt 2: atomar Schreiben je ziel.typ.
    ziel_typ = (ziel or {}).get("typ")
    if ziel_typ == "gericht":
        return _patch_gericht(essen_client, ziel, medien_id)
    if ziel_typ == "basis_item":
        return _schreibe_override(ziel, medien_id, overrides_pfad)

    logger.warning("essen_foto_setzen: Ziel-typ %r nicht erkannt nach Upload "
                   "medien_id=%s", ziel_typ, medien_id)
    return SIGNAL_ZIEL_UNBEKANNT, {"medien_id": medien_id}


def _patch_gericht(essen_client, ziel, medien_id):
    """PATCH ESSEN-19a — foto_ref auf das Gericht setzen.

    `ziel` muss {"typ": "gericht", "gericht_id": "<id>"} sein.
    Interne Helper-Funktion — wird von _hochladen_und_schreiben aufgerufen.
    """
    if not medien_id:
        return SIGNAL_NICHTS_ZU_TUN, {}

    ziel_typ = (ziel or {}).get("typ")
    gericht_id = (ziel or {}).get("gericht_id")

    if ziel_typ != "gericht" or not gericht_id:
        logger.warning("essen_foto_setzen: _patch_gericht mit Ziel %r — "
                       "Typ oder gericht_id fehlt", ziel)
        return SIGNAL_ZIEL_UNBEKANNT, {"ziel": ziel}

    try:
        essen_client.patch_gericht_bild(gericht_id, foto_ref=medien_id)
    except EssenClientError as e:
        fehler_str = str(e)
        if "HTTP 4" in fehler_str:
            logger.info("essen_foto_setzen: ESSEN-19a abgelehnt — %s", e)
            return SIGNAL_GRENZE, {"detail": fehler_str}
        logger.warning("essen_foto_setzen: Essen-Buddy nicht erreichbar — %s",
                       e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}

    logger.info("essen_foto_setzen: gericht_id=%s foto_ref=%s gesetzt",
                gericht_id, medien_id)
    return SIGNAL_GERICHT_PATCH, {"gericht_id": gericht_id,
                                   "medien_id": medien_id}


def _schreibe_override(ziel, medien_id, overrides_pfad):
    """foto_overrides.json schreiben — {item_id: medien_id}.

    Tolerant gegen fehlende Datei (anlegt sie), mergt vorhandene Einträge.
    Atomares Schreiben via .tmp-Datei + os.replace (POSIX-Garantie).

    `overrides_pfad` ist Pflicht — ohne Pfad ist SIGNAL_NICHTS_ZU_TUN die Folge.
    Interne Helper-Funktion — wird von _hochladen_und_schreiben aufgerufen.
    """
    if not medien_id:
        return SIGNAL_NICHTS_ZU_TUN, {}

    ziel_typ = (ziel or {}).get("typ")
    item_id = (ziel or {}).get("item_id")

    if ziel_typ != "basis_item" or not item_id:
        logger.warning("essen_foto_setzen: _schreibe_override mit "
                       "Ziel %r — Typ oder item_id fehlt", ziel)
        return SIGNAL_ZIEL_UNBEKANNT, {"ziel": ziel}

    if not overrides_pfad:
        logger.warning("essen_foto_setzen: overrides_pfad nicht gesetzt — "
                       "nichts zu tun")
        return SIGNAL_NICHTS_ZU_TUN, {}

    # Vorhandene Datei lesen (tolerant gegen fehlende Datei — ESSEN-22).
    bestehend = {}
    try:
        with open(overrides_pfad, encoding="utf-8") as fh:
            bestehend = json.load(fh)
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("essen_foto_setzen: foto_overrides.json lesen "
                       "fehlgeschlagen — %s; starte frisch", e)

    if not isinstance(bestehend, dict):
        logger.warning("essen_foto_setzen: foto_overrides.json hat unerwartete "
                       "Form (%r); starte frisch", bestehend)
        bestehend = {}

    # Eintrag mergen, atomar schreiben.
    bestehend[item_id] = medien_id
    verzeichnis = os.path.dirname(overrides_pfad)
    if verzeichnis:
        os.makedirs(verzeichnis, exist_ok=True)
    tmp_pfad = overrides_pfad + ".tmp"
    try:
        with open(tmp_pfad, "w", encoding="utf-8") as fh:
            json.dump(bestehend, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_pfad, overrides_pfad)
    except OSError as e:
        logger.error("essen_foto_setzen: Schreiben von foto_overrides.json "
                     "fehlgeschlagen — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": str(e)}

    logger.info("essen_foto_setzen: item_id=%s medien_id=%s in %s eingetragen",
                item_id, medien_id, overrides_pfad)
    return SIGNAL_OVERRIDE_GESCHRIEBEN, {"item_id": item_id,
                                          "medien_id": medien_id}
