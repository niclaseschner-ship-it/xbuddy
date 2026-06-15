"""Essens-Foto setzen als Aufgaben-Katalog-Aufgabe — specs/buddies/essen.md
(ESSEN-22 Pfad 2) und specs/platform/eltern-chat.md (EC-7 / EC-10).

Diese Aufgabe ist der Trigger der `essen_foto_setzen`-Funktion: versteht der
Agent eine Foto-Nachricht mit Essens-Caption, schlägt er das Setzen vor
(propose→confirm, EC-10 zweistufige Variante, Cluster C / Capability-Karte).

Atomarer Ablauf (E-EC-7 — EIN Confirm pro Operation):
  Agent ruft Task mit `aktion='hochladen'`: Foto holen, an Essen-Buddy
  laden (ESSEN-22 V1.2) + sofort Schreiben (PATCH ESSEN-19a bei Gericht ODER
  foto_overrides.json bei Basis-Item). Kein zweiter Tool-Call noetig.

Catalog-Name: „essen_foto_setzen".
Profil: Cluster C / Capability-Karte (propose→confirm, schreibend, ESSEN-22 Pfad 2).

Die Ziel-Ermittlung (Katalog-Lookup nach Caption-Item-Name) liegt beim
Aufrufer (LLM-Klassifikation, ESSEN-22 Vor-Routing); der Task bekommt das
Ziel als `arguments` (gericht_id ODER item_id). Der TurnContext liefert die
Medien-Bytes (media_telegram_file_id) — EC-12-Geist: nicht das Modell, sondern
die Orchestrierung bestimmt welches Foto hochgeladen wird.
"""

import logging

from tasks import Proposal, WriteTask

from skills import essen_foto_setzen as efs_mod
from skills.essen_foto_setzen import (
    AKTION_ABBRUCH,
    AKTION_HOCHLADEN,
)

logger = logging.getLogger(__name__)


# EC-10 / ESSEN-22: Quittungen in den Agent-Loop.
_QUITTUNG_GERICHT_GESETZT = (
    "Foto bei Gericht »{gericht_id}« gesetzt (medien_id: {medien_id}) — "
    "beim nächsten Öffnen sichtbar.")
_QUITTUNG_OVERRIDE_GESCHRIEBEN = (
    "Foto bei Item »{item_id}« hinterlegt (medien_id: {medien_id}) — "
    "beim nächsten Öffnen sichtbar.")
_QUITTUNG_ABGELEHNT = (
    "Essens-Foto setzen geht nur für Mitglieder der Familien-Gruppe.")
_QUITTUNG_GRENZE = (
    "Der Buddy hat die Anfrage abgelehnt: {detail}")
_QUITTUNG_NICHT_ERREICHBAR = (
    "Buddy ist gerade nicht erreichbar — bitte gleich nochmal versuchen.")
_QUITTUNG_NICHTS_ZU_TUN = (
    "Ich brauche ein Foto und eine Ziel-Information, um ein Essens-Foto "
    "zu setzen.")
_QUITTUNG_ZIEL_UNBEKANNT = (
    "Das Ziel ist mir unklar — bitte sag mir, ob es ein Gericht oder ein "
    "Basis-Item ist.")
_QUITTUNG_ABBRUCH = (
    "Abgebrochen — kein Foto gesetzt.")
_QUITTUNG_KEIN_MATCH = (
    "»{name}« ist nicht im Katalog. Um es mit einem Foto anzulegen, nutze "
    "zuerst »gericht_anlegen« (Pfad 1, GAN). Danach kann das Foto nachträglich "
    "gesetzt werden.")


class EssenFotoSetzenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Essens-Foto setzen« auslöst
    (ESSEN-22 Pfad 2, Cluster C propose→confirm per Capability-Karte, atomar E-EC-7).

    propose(): nennt Ziel und Foto, fragt nach Bestätigung (E-EC-7 — das
    Bestätigungswort »Foto setzen« ist das deterministischste Gate, das ohne
    freien Text auskommt).

    execute(): hochladen macht Upload + Schreiben in EINEM Schritt.
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, tg, essen_client,
                 family_group_chat_id_getter, is_member_fn=None,
                 overrides_pfad=None):
        super().__init__(
            name="essen_foto_setzen",
            description=(
                "Lädt ein Familien-Foto in den Essen-Buddy hoch und setzt es in "
                "einem Schritt am Gericht (foto_ref via PATCH ESSEN-19a) oder am "
                "Basis-Item (foto_overrides.json). EIN Confirm pro Operation "
                "(E-EC-7). "
                "Aufrufen, wenn jemand ein Foto MIT Essens-Caption schickt "
                "(z. B. »Lasagne« oder »essen-foto«). "
                "WICHTIG: Bevor du diesen Skill aufrufst, rufe ZUERST "
                "essen_katalog_lesen auf, um den Essens-Katalog zu lesen. "
                "Suche das Item aus der Caption (z. B. »Lasagne«) in den "
                "Gerichten oder Items. Wenn Match: rufe diesen Skill mit "
                "aktion='hochladen' + gericht_id (für Gericht-Match) ODER "
                "item_id (für Basis-Item-Match) auf. Wenn KEIN Match: schlage "
                "stattdessen gericht_anlegen vor (Pfad 1 ESSEN-22). "
                "Upload und Schreiben erfolgen atomar in einem Schritt."),
            parameters={
                "type": "object",
                "properties": {
                    "aktion": {
                        "type": "string",
                        "enum": [
                            AKTION_HOCHLADEN,
                            AKTION_ABBRUCH,
                        ],
                        "description": (
                            "'hochladen' — Foto hochladen und sofort am Ziel setzen "
                            "(Upload + PATCH/Override atomar, ESSEN-22 E-EC-7). "
                            "'abbruch' — Vorgang beenden, kein Schreiben."),
                    },
                    "gericht_id": {
                        "type": "string",
                        "description": (
                            "ID des Gerichts bei 'hochladen' (Ziel-Angabe). "
                            "MUSS aus essen_katalog_lesen-Output stammen — "
                            "keine erfundenen IDs."),
                    },
                    "item_id": {
                        "type": "string",
                        "description": (
                            "ID des Basis-Items bei 'hochladen' (Ziel-Angabe). "
                            "MUSS aus essen_katalog_lesen-Output stammen — "
                            "keine erfundenen IDs."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._essen_client = essen_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._is_member_fn = is_member_fn
        # overrides_pfad: absoluter Pfad zu xbuddy-data/essen/foto_overrides.json.
        # Von build_catalog gesetzt; None in Tests, die ihn selbst übergeben.
        self._overrides_pfad = overrides_pfad

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — nennt Aktion und Ziel, fragt nach Bestätigung.

        Für 'hochladen': beschreibt welches Ziel mit Foto versehen wird.
        """
        args = arguments or {}
        aktion = args.get("aktion") or AKTION_HOCHLADEN
        gericht_id = (args.get("gericht_id") or "").strip()
        item_id = (args.get("item_id") or "").strip()

        if aktion == AKTION_HOCHLADEN:
            if gericht_id:
                summary = (
                    "Foto für Gericht »%s« hochladen und setzen — beim nächsten "
                    "Öffnen der Essens-View sichtbar. Bestätige mit »Foto setzen«."
                    % gericht_id)
            elif item_id:
                summary = (
                    "Foto für Item »%s« hochladen und hinterlegen — beim nächsten "
                    "Öffnen der Essens-View sichtbar. Bestätige mit »Foto setzen«."
                    % item_id)
            else:
                summary = (
                    "Foto für ein Essens-Katalog-Item hochladen — bitte Ziel angeben.")
            return Proposal(summary)

        if aktion == AKTION_ABBRUCH:
            return Proposal("Vorgang abbrechen — kein Foto gesetzt.")

        return Proposal("Essens-Foto setzen (Aktion noch unklar).")

    def execute(self, arguments, turn_context):
        """Führt die essen_foto_setzen-Funktion synchron aus (ESSEN-22, atomar).

        Die Medien-Bytes werden aus dem TurnContext gelesen (media_telegram_file_id)
        — EC-12-Geist: nicht das Modell bestimmt welches Foto. Gericht-ID /
        Item-ID kommen aus den `arguments` (LLM-Klassifikation, ESSEN-22
        Vor-Routing).

        aktion='hochladen': macht Upload + Schreiben in EINEM Aufruf.
        """
        args = arguments or {}
        aktion = args.get("aktion") or AKTION_HOCHLADEN

        # is_member_fn: von build_catalog immer injiziert; None nur für Tests.
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        gericht_id = (args.get("gericht_id") or "").strip() or None
        item_id = (args.get("item_id") or "").strip() or None

        # Ziel-Dict aus arguments aufbauen.
        if gericht_id:
            ziel = {"typ": "gericht", "gericht_id": gericht_id}
        elif item_id:
            ziel = {"typ": "basis_item", "item_id": item_id}
        else:
            ziel = {}

        if aktion == AKTION_ABBRUCH:
            return _QUITTUNG_ABBRUCH

        if aktion == AKTION_HOCHLADEN:
            return self._execute_hochladen(
                is_member_fn, from_user_id, ziel, turn_context)

        return _QUITTUNG_NICHTS_ZU_TUN

    def _execute_hochladen(self, is_member_fn, from_user_id, ziel, turn_context):
        """Atomarer Schritt via TurnContext: Foto holen (EC-12-Geist) + hochladen + schreiben."""
        file_id = getattr(turn_context, "media_telegram_file_id", None)
        medium_typ = getattr(turn_context, "medium_typ", None)

        if not file_id:
            # Modell hat den Skill ohne Medium gerufen → ehrliche Grenze (EC-7).
            return _QUITTUNG_NICHTS_ZU_TUN

        try:
            medium_bytes = self._tg.download_file(file_id)
        except Exception as e:
            logger.warning(
                "essen_foto_setzen: Download fehlgeschlagen file_id=%s: %s",
                file_id, e)
            return _QUITTUNG_NICHT_ERREICHBAR

        filename, content_type = _filename_und_mime(medium_typ)

        signal, daten = efs_mod.essen_foto_setzen(
            aktion=AKTION_HOCHLADEN,
            essen_client=self._essen_client,
            ziel=ziel,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            medium_bytes=medium_bytes,
            filename=filename,
            content_type=content_type,
            overrides_pfad=self._overrides_pfad,
        )
        return _quittung_fuer(signal, daten)


def _quittung_fuer(signal, daten):
    """Übersetzt das (signal, daten)-Tuple in eine Agent-Loop-Quittung."""
    if signal == efs_mod.SIGNAL_GERICHT_PATCH:
        return _QUITTUNG_GERICHT_GESETZT.format(
            gericht_id=daten.get("gericht_id", "?"),
            medien_id=daten.get("medien_id", "?"))

    if signal == efs_mod.SIGNAL_OVERRIDE_GESCHRIEBEN:
        return _QUITTUNG_OVERRIDE_GESCHRIEBEN.format(
            item_id=daten.get("item_id", "?"),
            medien_id=daten.get("medien_id", "?"))

    if signal == efs_mod.SIGNAL_ABGELEHNT:
        return _QUITTUNG_ABGELEHNT

    if signal == efs_mod.SIGNAL_GRENZE:
        return _QUITTUNG_GRENZE.format(detail=daten.get("detail", ""))

    if signal == efs_mod.SIGNAL_NICHT_ERREICHBAR:
        return _QUITTUNG_NICHT_ERREICHBAR

    if signal == efs_mod.SIGNAL_ZIEL_UNBEKANNT:
        return _QUITTUNG_ZIEL_UNBEKANNT

    if signal == efs_mod.SIGNAL_ABGEBROCHEN:
        return _QUITTUNG_ABBRUCH

    return _QUITTUNG_NICHTS_ZU_TUN


def _filename_und_mime(medium_typ):
    """Liefert (filename, content_type) passend zum `medium_typ` (analog FSE)."""
    if medium_typ == "video":
        return "video.mp4", "video/mp4"
    return "foto.jpg", "image/jpeg"
