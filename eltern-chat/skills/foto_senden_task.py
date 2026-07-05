"""Foto/Video senden als Aufgaben-Katalog-Aufgabe — specs/platform/
foto-senden.md (FSE-1 … FSE-8) und conventions/tasks.md TASK-9.

Diese Aufgabe ist der V1-Trigger der `foto_senden`-Funktion (FSE-1): versteht
der Agent ein kommentarlos gesendetes Foto oder Video (FSE-3) — oder den
Widerruf-Anstoß (FSE-4) —, ruft er dieses Tool.

Eine **Sofort-Schreib-Aufgabe** im Sinne von TASK-9 (`conventions/tasks.md`):
sie erbt von `ReadTask`, läuft synchron im Lese-Pfad des Agent-Loops
(`agent.py:367-376`) und schreibt **direkt** (PHOTO-13) — kein propose, kein
EC-10-Confirm-Gate (E-FSE-1). Das **auslösende Ereignis** (das kommentarlose
Medium) IST die ausdrückliche Handlung; die Quittung trägt das **Undo**
(PHOTO-16 mit der zurückgegebenen `id`).

Bewusste Copy der TER-/RZS-Linie (RAT-12 — keine gemeinsame Abstraktion).

TASK-9-Pflicht: die Quittung enthält die `id` und einen erreichbaren
Inverse-Aufruf (D6 — Undo als **zweiter** `tool_use`: das Modell sieht die
`id` und kann auf einen Widerruf-Anstoß hin das Tool erneut mit
`{aktion: "widerrufen", id: "..."}` aufrufen).
"""

import logging

from tasks import ReadTask

from skills import foto_senden as fs_mod
from skills._quittungen import nicht_erreichbar as _q_nicht_erreichbar
from skills.foto_senden import (
    AKTION_HOCHLADEN,
    AKTION_WIDERRUFEN,
)

logger = logging.getLogger(__name__)


# FSE-4 / TASK-9: Quittungen in den Agent-Loop.
# Die Quittung enthält die `id` UND einen Hinweis auf den Widerruf — das
# Modell sieht beides und kann auf einen Widerruf-Anstoß hin das Tool erneut
# mit `{aktion: "widerrufen", id: "..."}` aufrufen (D6 / Verdikt Phase 2,
# kein neuer Speicher, kein neuer State).
_QUITTUNG_HOCHGELADEN = (
    "Im Bilderrahmen — beim nächsten Öffnen sichtbar. "
    "Wenn du es zurücknehmen möchtest, sag »widerrufen« — id: {id}. "
    "Wenn das ein Missverständnis war, sag einfach `falsch`, ich mach es dann rückgängig.")
_QUITTUNG_WIDERRUFEN = (
    "Zurückgenommen — das Medium ist aus dem Bilderrahmen entfernt.")
_QUITTUNG_ABGELEHNT = (
    "Foto/Video senden geht nur für Mitglieder der Familien-Gruppe.")
_QUITTUNG_GRENZE = (
    "Der Photo-Buddy hat das Medium abgelehnt — meist zu groß oder zu lang. "
    "Schick es kürzer/kleiner und versuch es noch einmal.")
_QUITTUNG_GRENZE_WIDERRUF = (
    "Den Widerruf konnte ich nicht ausführen — die id ist dem Photo-Buddy "
    "nicht (mehr) bekannt.")
_QUITTUNG_NICHT_ERREICHBAR = _q_nicht_erreichbar("Photo-Buddy")
_QUITTUNG_NICHTS_ZU_TUN = (
    "Ich habe gerade kein Foto oder Video — schick mir bitte ein Medium "
    "ohne Begleittext.")


class FotoSendenTask(ReadTask):
    """Sofort-Schreib-Aufgabe (TASK-9), die »Foto/Video senden« auslöst
    (FSE-1 / FSE-8).

    Erbt bewusst von **ReadTask** (TASK-9 / E-FSE-1): das auslösende Ereignis
    (kommentarloses Medium) ist die ausdrückliche Handlung — kein EC-10-
    Confirm-Gate. Die Quittung bietet ein Undo (PHOTO-16) als Sicherheitsnetz.

    Der **Zielchat** und die **Medien-Bytes** kommen aus dem `TurnContext`,
    NIE aus den Modell-`arguments` (EC-12-Geist, analog TES/FAA/RZS): so
    bestimmt nicht das Sprachmodell, welches Medium hochgeladen wird.

    `arguments` (Modell-Kanal):
      - `aktion`: `"hochladen"` (Default) oder `"widerrufen"` (FSE-4).
      - `id`: bei `widerrufen` die zuvor zurückgegebene Medium-id (FSE-4 / D6).
    """

    def __init__(self, tg, photo_client, family_group_chat_id_getter,
                 is_member_fn=None, receipt_store=None):
        super().__init__(
            name="foto_senden",
            description=(
                "Nimmt ein kommentarloses Foto oder kurzes Video aus dem "
                "Eltern-Chat entgegen und legt es im Bilderrahmen ab — die "
                "Wirkung ist sofort. Aufrufen, wenn jemand ein Medium OHNE "
                "Begleittext geschickt hat (das ist das Intent-Signal). NICHT "
                "aufrufen, wenn das Medium mit einem Prompt kommt (z. B. "
                "'mach X mit dem Bild') — dann ist ein anderer Skill gemeint. "
                "Nach erfolgreichem Upload enthält die Quittung eine id; auf "
                "einen Widerruf-Wunsch das Tool erneut aufrufen mit "
                "{\"aktion\": \"widerrufen\", \"id\": \"<id>\"}, um das "
                "Medium aus dem Bilderrahmen zu nehmen."),
            parameters={
                "type": "object",
                "properties": {
                    "aktion": {
                        "type": "string",
                        "enum": [AKTION_HOCHLADEN, AKTION_WIDERRUFEN],
                        "description": (
                            "Standard ist 'hochladen' (Default beim ersten "
                            "Aufruf). 'widerrufen' nur dann, wenn jemand das "
                            "zuletzt gesendete Medium zurücknehmen möchte; "
                            "dafür auch `id` mitgeben."),
                    },
                    "id": {
                        "type": "string",
                        "description": (
                            "Bei aktion='widerrufen': die `id` aus der "
                            "Quittung des vorherigen Hochladens (FSE-4)."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._photo_client = photo_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. Von build_catalog immer
        # injiziert; None nur für Tests, die eine eigene Funktion übergeben
        # (analog RoutineZeitenSetzenTask).
        self._is_member_fn = is_member_fn
        # receipt_store: A2ReceiptStore-Instanz (EC-10 A2-Receipt, #841).
        # None in Tests ohne Receipt-Probe; build_catalog injiziert immer.
        self._receipt_store = receipt_store

    def run(self, arguments, turn_context):
        """Sofort-Schreib-Aufgabe (TASK-9): ruft FSE-1 direkt im Lese-Pfad.

        Die Medien-Bytes/Dateinamen/MIME-Typen werden aus dem `TurnContext`
        gelesen (`media_telegram_file_id`, `medium_typ`) und über
        `tg.download_file` heruntergeladen — die Telegram-`file_id` ist die
        deterministische Naht, nicht der Modell-Kanal (EC-12-Geist).

        Bei leerem TurnContext-Medium läuft die Funktion auf
        SIGNAL_NICHTS_ZU_TUN — das Modell hat das Tool auf falscher Spur
        gerufen (FSE-3: nur kommentarloses Medium ist Intent). EC-7
        (ehrliche Grenze).
        """
        args = arguments or {}
        aktion = args.get("aktion") or AKTION_HOCHLADEN

        # FSE-2-Adapter: is_member_fn deklarativ, von build_catalog injiziert.
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        if aktion == AKTION_WIDERRUFEN:
            # FSE-4 / D6: zweiter tool_use mit der id aus der ersten Quittung.
            medium_id = args.get("id")
            signal, daten = fs_mod.foto_senden(
                aktion=AKTION_WIDERRUFEN,
                photo_client=self._photo_client,
                is_member_fn=is_member_fn,
                from_user_id=from_user_id,
                medium_id=medium_id,
            )
            return _quittung_fuer(signal, daten)

        # FSE-3 / D4: Medien-Bytes über die TurnContext-file_id holen.
        file_id = getattr(turn_context, "media_telegram_file_id", None)
        medium_typ = getattr(turn_context, "medium_typ", None)
        if not file_id:
            # Modell hat den Skill ohne Medium gerufen → ehrliche Grenze (FSE-3).
            return _QUITTUNG_NICHTS_ZU_TUN

        try:
            medium_bytes = self._tg.download_file(file_id)
        except Exception as e:  # TelegramError u. ä. — siehe EC-7
            logger.warning("foto_senden: Download fehlgeschlagen file_id=%s: %s",
                           file_id, e)
            return _QUITTUNG_NICHT_ERREICHBAR

        filename, content_type = _filename_und_mime(medium_typ)

        signal, daten = fs_mod.foto_senden(
            aktion=AKTION_HOCHLADEN,
            photo_client=self._photo_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            medium_bytes=medium_bytes,
            filename=filename,
            content_type=content_type,
        )

        # EC-10 A2-Receipt (#841): nach erfolgreichem Upload einen Bon schreiben.
        # Versiegelung von Vorgänger-Receipts desselben chat_id ist atomar in
        # receipt_store.insert() (Versiegelungs-Klausel, spec Z. 550-556).
        if signal == fs_mod.SIGNAL_HOCHGELADEN and self._receipt_store is not None:
            medium_id = daten.get("id")
            chat_id = getattr(turn_context, "chat_id", None)
            if medium_id and chat_id is not None:
                # EC-10 spec Z. 533-535: inverse_call ist strukturierter Verweis
                # in HTTP-Form (Buddy-Endpunkt + Pfad-Parameter), parsbar als
                # "<buddy-key> <method> <api-path-with-id>". photo-Endpunkt:
                # photo_client.py:59 (PHOTO-16/FSE-4) — DELETE /api/v1/photo/medien/<id>.
                inverse_call = 'photo DELETE /api/v1/photo/medien/%s' % medium_id
                try:
                    self._receipt_store.insert(
                        task_name="foto_senden",
                        chat_id=chat_id,
                        resource_id=medium_id,
                        inverse_call=inverse_call,
                    )
                    logger.debug(
                        "foto_senden: A2-Receipt geschrieben medium_id=%s chat_id=%s",
                        medium_id, chat_id)
                except Exception as e:
                    # Receipt-Fehler bricht den erfolgreichen Upload NICHT ab
                    # (ehrliche Grenze EC-7: Upload war ok, Receipt ist Monitoring).
                    logger.warning(
                        "foto_senden: A2-Receipt-Insert fehlgeschlagen: %s", e)

        return _quittung_fuer(signal, daten)


def _quittung_fuer(signal, daten):
    """Übersetzt das (signal, daten)-Tuple in eine Agent-Loop-Quittung
    (TASK-9). Die hochgeladen-Quittung enthält die `id` für das Undo (D6)."""
    if signal == fs_mod.SIGNAL_HOCHGELADEN:
        return _QUITTUNG_HOCHGELADEN.format(id=daten.get("id", "?"))
    if signal == fs_mod.SIGNAL_WIDERRUFEN:
        return _QUITTUNG_WIDERRUFEN
    if signal == fs_mod.SIGNAL_ABGELEHNT:
        return _QUITTUNG_ABGELEHNT
    if signal == fs_mod.SIGNAL_GRENZE:
        # FSE-4: Widerruf-spezifische Grenze (404) unterscheidet sich vom
        # Hochlade-Grenze-Fall (PHOTO-13 4xx).
        if "id" in daten:
            return _QUITTUNG_GRENZE_WIDERRUF
        return _QUITTUNG_GRENZE
    if signal == fs_mod.SIGNAL_NICHT_ERREICHBAR:
        return _QUITTUNG_NICHT_ERREICHBAR
    return _QUITTUNG_NICHTS_ZU_TUN


def _filename_und_mime(medium_typ):
    """Liefert (filename, content_type) passend zum `medium_typ` aus dem
    TurnContext (FSE-5).

    V1-Heuristik: Telegram normalisiert Fotos zu JPEG; native Videos sind
    typischerweise MP4. Der Photo-Buddy nutzt magic-bytes (PHOTO-8), den
    fachlichen MIME-Typ bestimmt er selbst — der Dateiname/MIME hier ist
    nur Komfort für den Buddy.
    """
    if medium_typ == "video":
        return "video.mp4", "video/mp4"
    # Default: Foto (Telegram → JPEG).
    return "photo.jpg", "image/jpeg"
