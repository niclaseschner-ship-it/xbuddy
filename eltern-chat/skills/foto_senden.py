"""Foto/Video senden — specs/platform/foto-senden.md (FSE-1 … FSE-8).

Aufrufbare, trigger-agnostische Funktion (FSE-1, E-RZS-1-Muster): nimmt **ein
Medium** (Foto oder kurzes Video) entgegen und ruft die Photo-Buddy-Medien-
Schnittstelle (PHOTO-13, `POST /api/v1/photo/medien`, FSE-7). Bewusste Copy
der TES-/RZS-Linie (RAT-6, RAT-12 — keine gemeinsame Schreib-Skill-Abstraktion,
bis der gemeinsame Vertrag nach dem 2.–3. *gebauten* Skill ehrlich entsteht).

E-FSE-1 — **Sofort-Wirkung mit Rückgängig** statt propose→confirm: das nackte
Medium IST die ausdrückliche Handlung; die Funktion schreibt direkt und bietet
ein Undo (PHOTO-16) an. Trotzdem wirkt sie schreibend (EC-10) — der Eltern-
Chat-Task läuft als ReadTask (TASK-9, conventions/tasks.md), weil das
auslösende Ereignis selbst die ausdrückliche Handlung ist.

Eingang: Telegram-Privatchat-ID (für Quittung im Privatchat oder
Familien-Gruppe, je nach Ziel-Chat), User-ID (Berechtigung FSE-2), gewünschte
Aktion (`hochladen` / `widerrufen`), bei `hochladen`: Medien-Bytes + Dateiname
+ Content-Type; bei `widerrufen`: medium_id. Außerdem PhotoClient (FSE-7),
is_member_fn (FSE-2).

Ausgang: Ergebnis-Tuple `(signal, daten)`:
  („hochgeladen",  {"id": <str>, "typ": <str>})  — PHOTO-13 erfolgreich.
  („widerrufen",   {"id": <str>})                — PHOTO-16 erfolgreich.
  („abgelehnt",    {})                           — Berechtigung fehlt (FSE-2).
  („grenze",       {"detail": <str>})            — PHOTO-13 4xx (FSE-5).
  („nicht_erreichbar", {"detail": <str>})        — Buddy nicht erreichbar.
  („nichts_zu_tun",{})                           — kein Medium/keine id übergeben.
"""

import logging

from skills.photo_client import PhotoClientError

logger = logging.getLogger(__name__)


# FSE-1: Ergebnis-Signale der Funktion.
SIGNAL_HOCHGELADEN     = "hochgeladen"
SIGNAL_WIDERRUFEN      = "widerrufen"
SIGNAL_ABGELEHNT       = "abgelehnt"
SIGNAL_GRENZE          = "grenze"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"
SIGNAL_NICHTS_ZU_TUN   = "nichts_zu_tun"

# FSE-1: Aktionen (E-FSE-1 / D6 — Undo als zweiter tool_use).
AKTION_HOCHLADEN  = "hochladen"
AKTION_WIDERRUFEN = "widerrufen"


def foto_senden(*, aktion, photo_client, is_member_fn, from_user_id,
                medium_bytes=None, filename=None, content_type=None,
                medium_id=None):
    """Foto/Video senden — aufrufbare Funktion (FSE-1).

    Eine **schreibende** Aufgabe mit **Sofort-Wirkung** (E-FSE-1, FSE-4): es
    gibt **kein** propose→confirm hier — die Funktion ruft direkt PHOTO-13
    (`hochladen`) bzw. PHOTO-16 (`widerrufen`). Das Undo ist das Sicherheitsnetz
    statt der Vorab-Frage.

    Parameter:
      `aktion`         — `"hochladen"` oder `"widerrufen"` (FSE-1, FSE-4).
      `photo_client`   — PhotoClient-Instanz (FSE-7).
      `is_member_fn`   — Callable `(user_id) -> bool` (FSE-2).
      `from_user_id`   — Telegram-User-ID des Aufrufers (FSE-2).
      Bei `hochladen`:
        `medium_bytes`  — die rohen Medien-Bytes (Foto JPEG / Video MP4 …).
        `filename`      — Dateiname für den multipart-Header.
        `content_type`  — MIME-Typ (`image/jpeg`, `video/mp4`, …).
      Bei `widerrufen`:
        `medium_id`     — die `id` aus der vorherigen PHOTO-13-Antwort.

    Ergebnis (signal, daten): siehe Modul-Docstring.
    """
    # FSE-2: Berechtigung — live geprüft, identisch zum RZS-/TES-Muster.
    # Die Prüfung liegt bei der Funktion (E-RZS-1), nicht beim Trigger.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("foto_senden: User %s ist kein Familienmitglied — abgelehnt",
                    from_user_id)
        return SIGNAL_ABGELEHNT, {}

    if aktion == AKTION_HOCHLADEN:
        return _hochladen(photo_client, medium_bytes, filename, content_type)
    if aktion == AKTION_WIDERRUFEN:
        return _widerrufen(photo_client, medium_id)

    logger.warning("foto_senden: unbekannte Aktion %r — nichts zu tun", aktion)
    return SIGNAL_NICHTS_ZU_TUN, {}


def _hochladen(photo_client, medium_bytes, filename, content_type):
    """FSE-3/FSE-4/FSE-7: Medium an PHOTO-13 (POST /api/v1/photo/medien).

    Ohne Medien-Bytes ist nichts zu tun (z. B. Modell ruft das Tool auf
    falscher Spur — keine Anhang-Datei im TurnContext, FSE-3-Disambiguierung).
    Antwort `{id, typ}` liefern wir an den Aufrufer durch (FSE-4 nutzt die
    `id` für das Undo-Angebot).
    """
    if not medium_bytes:
        # FSE-3: kein Medium im Trigger — der Skill greift nicht. Das passiert,
        # wenn das Modell die Funktion auf falscher Spur ruft (Text-Nachricht,
        # nicht kommentarloses Medium). Ehrliche Grenze (EC-7).
        return SIGNAL_NICHTS_ZU_TUN, {}

    try:
        response = photo_client.upload_medium(
            medium_bytes=medium_bytes,
            filename=filename or "medium",
            content_type=content_type or "application/octet-stream",
        )
    except PhotoClientError as e:
        fehler_str = str(e)
        # FSE-5: 4xx vom Buddy (z. B. Video zu lang) → klare Grenze melden.
        # Andere Fehler (5xx, Connection-refused) → „nicht erreichbar".
        if "HTTP 4" in fehler_str:
            logger.info("foto_senden: PHOTO-13 hat Medium abgelehnt — %s", e)
            return SIGNAL_GRENZE, {"detail": fehler_str}
        logger.warning("foto_senden: Photo-Buddy nicht erreichbar — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}

    medium_id = response.get("id")
    typ = response.get("typ", "")
    logger.info("foto_senden: hochgeladen id=%s typ=%s", medium_id, typ)
    return SIGNAL_HOCHGELADEN, {"id": medium_id, "typ": typ}


def _widerrufen(photo_client, medium_id):
    """FSE-4/PHOTO-16: das gerade angelegte Medium wieder löschen.

    Ohne `medium_id` ist nichts zu tun (Aufrufer hat die id verloren —
    nichts, was die Funktion noch retten könnte; ehrliche Grenze).
    """
    if not medium_id:
        return SIGNAL_NICHTS_ZU_TUN, {}

    try:
        photo_client.delete_medium(medium_id)
    except PhotoClientError as e:
        fehler_str = str(e)
        if "HTTP 4" in fehler_str:
            # 404 (id unbekannt) ist kein Grund zur Eskalation — ehrliche Info.
            logger.info("foto_senden: Widerruf fehlgeschlagen — %s", e)
            return SIGNAL_GRENZE, {"detail": fehler_str, "id": medium_id}
        logger.warning("foto_senden: Widerruf nicht durchgeführt — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str,
                                         "id": medium_id}

    logger.info("foto_senden: widerrufen id=%s", medium_id)
    return SIGNAL_WIDERRUFEN, {"id": medium_id}
