"""Hörspiel-Folge erzeugen als Aufgaben-Katalog-Aufgabe — specs/platform/
hoerspiel-folge-erzeugen.md (HFE-1, HFE-8, EC-8/EC-10, E-HFE-1 … E-HFE-5).

Diese Aufgabe ist der V1-Trigger der `hoerspiel_folge_erzeugen`-Funktion
(HFE-1, E-HFE-1): versteht der Agent eine natürlichsprachige Bitte
(„Schreib eine Folge über Schnee"), holt er einen Folgen-Vorschlag vom
Hörspiel-Buddy — nach EC-10-Bestätigung baut er das Album.

Eine **schreibende** Aufgabe (EC-10, HFE-1): Cluster C / Capability-Karte
(E-HFE-5, A2-Klausel trifft nicht — Album-Bau ist 1–5-min-Pipeline, kein One-Shot). Die
propose/execute-Zweiteilung ist die einzige Bestätigung; kein Sofort-Undo.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(HFE-1 / E-HFE-1) — keine eigene LLM-/TTS-Logik.
"""

import contextlib
import logging
import re

from tasks import Proposal, WriteTask

import skills.hoerspiel_folge_erzeugen as hfe_mod

logger = logging.getLogger(__name__)


class HoerspielFolgeErzeugenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Hörspiel-Folge erzeugen«
    auslöst (HFE-1, HFE-8).

    V1 synchron: kein Worker-Thread, is_async=False. propose() ruft
    POST /folgen-vorschlag (20–90 s); execute() ruft POST /alben (1–5 min).
    Beide Aufrufe blockieren (E-HFE-4 — Async ist OPEN-HSP-L).

    Die EC-10-Bestätigung (propose/execute) ist die einzige Bestätigung
    (E-HFE-5 / E-HFE-3: propose→confirm, kein Sofort-Undo).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, tg, hoerspiel_client, display_url_origin: str = "",
                 family_group_chat_id_getter=None, is_member_fn=None,
                 mini_app_base_url: str = ""):
        super().__init__(
            name="hoerspiel_folge_erzeugen",
            description=(
                "Erstellt eine neue Hörspiel-Folge für Mia: schreibt einen "
                "Folgentext per KI und vertont ihn als Album.\n\n"
                "Aufrufen, wenn jemand sagt »Schreib eine Folge über …«, "
                "»Neue Folge«, »Neues Hörbuch«, »Neues Hörspiel«, »Hörbuch "
                "anlegen«, »Hörspiel machen«, »Mach Mia eine Folge«, "
                "»Schreib eine Folge«, »Folge erzeugen« — auch OHNE konkreten "
                "Inhalt/Suffix. Plus mit Inhalt: »Neue Folge über X«, »Mach "
                "Mia eine Folge zu Y«, »Hörbuch über Z«. Plus Themen-"
                "Anfrage: »Welche Themen gibt es?«, »Was könnte ich Mia "
                "erzählen?«, »Vorschläge?«.\n\n"
                "WICHTIG: bei JEDEM Hörspiel-/Hörbuch-/Folgen-Trigger SOFORT "
                "diesen Skill aufrufen — KEINE eigenen Rückfragen stellen, "
                "der Skill macht die Diskussion und holt Themen-Vorschläge "
                "selbst (HFE-3 Sub-Case 1).\n\n"
                "Parameter `idee`: die Folgen-Idee aus der Eltern-Nachricht "
                "(1–2 Sätze). LEER STRING »« setzen, wenn die Eltern noch "
                "keine konkrete Idee genannt haben (»Neues Hörbuch«, »Mach "
                "eine Folge«) — der Skill holt dann eine Themen-Liste "
                "(HFE-3 Sub-Case 1).\n\n"
                "Parameter `idee_diskussion` (bool, optional): True setzen, "
                "wenn die Idee konkret aber noch unvollständig ist und der "
                "Agent mehr Details klären will (HFE-3 Sub-Case 2).\n\n"
                "Parameter `voice` (optional): »shimmer« (weich/weiblich, "
                "Default) oder »onyx« (tief/männlich) — nur setzen, wenn die "
                "Eltern eine Voice explizit genannt haben (HFE-4).\n\n"
                "Eltern-Signal-Phrasen (beenden die Diskussion und lösen den "
                "Vorschlag-Endpoint aus): »los«, »los gehts«, »mach das«, "
                "»passt so«, »okay so«, »fang an«, »jetzt vertonen«, "
                "»schreib jetzt«. Bei diesen Phrasen diesen Task mit der "
                "zusammengeführten konkreten Idee und idee_diskussion=False "
                "aufrufen (HFE-3, HFE-6)."),
            parameters={
                "type": "object",
                "properties": {
                    "idee": {
                        "type": "string",
                        "description": (
                            "Die Folgen-Idee aus der Eltern-Nachricht, "
                            "z. B. 'Stigi findet einen geheimen Tunnel "
                            "unter dem Garten'. 1–2 Sätze. Leer lassen "
                            "für Themen-Anfrage."),
                    },
                    "idee_diskussion": {
                        "type": "boolean",
                        "description": (
                            "True wenn die Idee konkret aber noch "
                            "unvollständig ist (HFE-3 Sub-Case 2). "
                            "False (Default) für vollständige Idee."),
                    },
                    "voice": {
                        "type": "string",
                        "enum": [hfe_mod.VOICE_SHIMMER, hfe_mod.VOICE_ONYX],
                        "description": (
                            "Gewünschte Stimme: 'shimmer' (weich/weiblich) "
                            "oder 'onyx' (tief/männlich). Nur setzen, wenn "
                            "die Eltern eine Voice explizit genannt haben. "
                            "Sonst weglassen — der Skill liest den Default."),
                    },
                },
                "required": ["idee"],
            })
        self._tg = tg
        self._hoerspiel_client = hoerspiel_client
        self._display_url_origin = display_url_origin or ""
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._is_member_fn = is_member_fn
        self._mini_app_base_url = mini_app_base_url or ""
        # HFE-5: Session-State überbrückt propose→execute (Befund 1).
        # chat_id → {titel, text, voice, idee} aus dem Buddy-Vorschlag.
        # Nur eine offene Vorschlag-Session pro Chat — älter wird überschrieben.
        self._pending_vorschlaege: dict[object, dict] = {}
        # HFE-10: Tracking ob die erste propose()-Antwort im aktuellen Turn
        # für einen Chat bereits gesendet wurde. Ein Set von chat_ids.
        # Wird beim nächsten propose()-Aufruf nach EC-10-Confirm zurückgesetzt
        # (durch propose() → execute() Zyklus werden neue Turns automatisch
        # erkannt, da _pending_vorschlaege geleert wird).
        self._first_propose_done: set = set()

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — holt Folgen-Vorschlag vom Hörspiel-Buddy (HFE-3/4).

        Ruft hfe_mod.propose() auf. Bei Erfolg wird ein Proposal mit dem
        strukturierten Vorschlag-Text zurückgegeben (EC-10-Gate feuert).
        Speichert titel/text/voice/idee im Session-State, damit execute()
        sie ohne Modell-Kanal-Vertrauen bekommt (HFE-5, Befund 1).

        HFE-3 Sub-Cases 1+2: wenn propose() ein ValueError wirft (leere Idee
        oder Diskussions-Marker), propagiert die Exception zu agent.py →
        is_error=True Tool-Result → LLM formuliert Rückfrage für den User.
        Das EC-10-Gate feuert NICHT für Sub-Cases 1+2.

        HFE-10: first_propose-Tracking per chat_id; beim nächsten
        vollständigen propose()-Aufruf (Sub-Case 3) wird das Flag zurückgesetzt.
        """
        args = arguments or {}
        idee  = (args.get("idee") or "").strip()
        voice_hint = args.get("voice") or None
        idee_diskussion = bool(args.get("idee_diskussion", False))

        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)
        chat_id = turn_context.chat_id

        # HFE-10: "erste propose()-Antwort des Turns" bestimmen.
        # Heuristik: wenn für diesen Chat noch kein propose() des laufenden
        # HFE-Turns gelaufen ist, ist es die erste Antwort.
        is_first = chat_id not in self._first_propose_done
        # Als "gesehen" markieren — alle Folge-Antworten sind nicht-erste.
        self._first_propose_done.add(chat_id)

        # Wirft BerechtigungError, ValueError oder HoerspielClientError —
        # Sub-Cases 1+2 via ValueError, Sub-Case 3 via Tuple-Return.
        propose_result = hfe_mod.propose(
            hoerspiel_client=self._hoerspiel_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            idee=idee,
            voice_hint=voice_hint,
            tg=self._tg,
            chat_id=chat_id,
            mini_app_base_url=self._mini_app_base_url,
            is_first_propose=is_first,
            idee_diskussion=idee_diskussion,
        )
        # propose() gibt (result_text, fields-dict) bei Sub-Case 3 (Erfolg).
        # Backward-Compat: alte Form (nur String) wird via Text-Parser
        # geparst — wird mit dem nächsten Release entfernt.
        if isinstance(propose_result, tuple):
            result_text, fields = propose_result
            titel = fields.get("titel", "")
            text = fields.get("text", "")
            voice = fields.get("voice", "")
        else:
            result_text = propose_result
            titel, text, voice = _extrahiere_vorschlag_felder(
                result_text, voice_hint, self._hoerspiel_client)

        self._pending_vorschlaege[chat_id] = {
            "titel": titel,
            "text": text,
            "voice": voice,
            "idee": idee,
        }
        # HFE-10: Sub-Case 3 war erfolgreich — next propose() ist ein neuer
        # Turn (nach EC-10-Confirm). Flag zurücksetzen damit Beifang erneut erscheint.
        self._first_propose_done.discard(chat_id)
        logger.debug("HFE-Vorschlag im Session-State gespeichert chat_id=%s titel=%r",
                     chat_id, titel)

        # Nur bei Erfolg (Sub-Case 3): Proposal zurückgeben → EC-10-Gate feuert.
        return Proposal(result_text)

    def execute(self, arguments, turn_context):
        """Baut das Album nach EC-10-Bestätigung (HFE-5, TASK-10).

        Liest titel/text/voice/idee aus dem Session-State (Befund 1) —
        nicht aus dem Modell-Kanal `arguments`, da das Framework nur die
        ursprünglichen Tool-Call-arguments persistiert ({idee, voice?}).

        TASK-10: execute() ist außerhalb des Agent-Loops und sendet selbst.
        """
        chat_id = turn_context.chat_id
        pending = self._pending_vorschlaege.pop(chat_id, None)
        if pending is None:
            logger.warning(
                "HFE-execute: kein Session-State für chat_id=%s — "
                "Vorschlag verloren oder nie gemacht", chat_id)
            # Fehler-Bubble direkt senden (TASK-10-Kontext, analog HFE-5-Fehler).
            with contextlib.suppress(Exception):
                self._tg.send_message(
                    chat_id,
                    "Der Hörspiel-Vorschlag ist nicht mehr verfügbar — "
                    "bitte erneut starten.")
            return "Vorschlag verloren — erneut starten."

        hfe_mod.execute(
            hoerspiel_client=self._hoerspiel_client,
            tg=self._tg,
            chat_id=chat_id,
            display_url_origin=self._display_url_origin,
            titel=pending["titel"],
            text=pending["text"],
            voice=pending["voice"],
            idee=pending["idee"],
        )

        # execute() sendet selbst (TASK-10); der Rückgabe-String ist die
        # interne Quittung an den Agent-Loop (wird nach dem EC-10-Gate nicht
        # mehr an den Nutzer gepostet — er hat die Telegram-Bubble bekommen).
        return "Folge erzeugt und Bubble gesendet."


def _extrahiere_vorschlag_felder(
        result_text: str,
        voice_hint: str | None,
        hoerspiel_client,
) -> tuple[str, str, str]:
    """Extrahiert titel/text/voice aus dem strukturierten propose-Result-Text.

    Der Buddy-Vorschlag-Text hat das Format (HFE-4):
      **Folge <nr>: <titel>**\n\n<text>\n\nVoice: <voice> ...

    Wir parsen daraus Titel, Text und Voice — damit execute() die Felder
    ohne einen zweiten Buddy-Aufruf hat (Befund 1, HFE-5).
    """
    titel = ""
    text = ""
    voice = hfe_mod.VOICE_DEFAULT

    # Titel aus erster Markdown-Überschrift: **Folge N: <titel>**
    m_titel = re.search(r"\*\*Folge\s+\S+\s*:\s*(.+?)\*\*", result_text)
    if m_titel:
        titel = m_titel.group(1).strip()

    # Voice aus "Voice: <voice>" Zeile
    m_voice = re.search(r"\bVoice:\s*(shimmer|onyx)\b", result_text, re.IGNORECASE)
    if m_voice:
        voice = m_voice.group(1).lower()

    # Text: Zeilen zwischen der Überschrift und dem Voice-Block.
    # Strategie: alles nach der ersten Leerzeile bis zur "Voice:"-Zeile.
    lines = result_text.split("\n")
    text_lines: list[str] = []
    in_text = False
    for line in lines:
        if not in_text:
            # Header-Zeile überspringen, dann in_text=True nach erster Leerzeile
            if line.strip().startswith("**Folge"):
                in_text = True
                continue
        else:
            if re.match(r"\s*Voice:", line, re.IGNORECASE):
                break
            text_lines.append(line)
    text = "\n".join(text_lines).strip()

    return titel, text, voice
