"""Hörspiel-Folge erzeugen als Aufgaben-Katalog-Aufgabe — specs/platform/
hoerspiel-folge-erzeugen.md (HFE-1, HFE-8, EC-8/EC-10, E-HFE-1 … E-HFE-5).

Diese Aufgabe ist der V1-Trigger der `hoerspiel_folge_erzeugen`-Funktion
(HFE-1, E-HFE-1): versteht der Agent eine natürlichsprachige Bitte
(„Schreib eine Folge über Schnee"), holt er einen Folgen-Vorschlag vom
Hörspiel-Buddy — nach EC-10-Bestätigung baut er das Album.

Eine **schreibende** Aufgabe (EC-10, HFE-1): Klasse C (E-HFE-5, A2-Klausel
trifft nicht — Album-Bau ist 1–5-min-Pipeline, kein One-Shot). Die
propose/execute-Zweiteilung ist die einzige Bestätigung; kein Sofort-Undo.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(HFE-1 / E-HFE-1) — keine eigene LLM-/TTS-Logik.
"""

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
                 family_group_chat_id_getter=None, is_member_fn=None):
        super().__init__(
            name="hoerspiel_folge_erzeugen",
            description=(
                "Erstellt eine neue Hörspiel-Folge für Paula: schreibt einen "
                "Folgentext per KI und vertont ihn als Album.\n\n"
                "Aufrufen, wenn jemand sagt »Schreib eine Folge über …«, "
                "»Neue Folge über …«, »Mach Paula eine Folge zu …«, "
                "»Hörspiel-Folge: <Idee>«, »Neues Hörbuch über …« oder "
                "Ähnliches (HFE-6).\n\n"
                "Parameter `idee`: die Folgen-Idee aus der Eltern-Nachricht "
                "(1–2 Sätze). Ist die Idee leer oder sehr vage, diesen Task "
                "NOCH NICHT aufrufen — stattdessen erst gezielt nach der Idee "
                "fragen (EC-22).\n\n"
                "Parameter `voice` (optional): »shimmer« (weich/weiblich, "
                "Default) oder »onyx« (tief/männlich) — nur setzen, wenn die "
                "Eltern eine Voice explizit genannt haben (HFE-4)."),
            parameters={
                "type": "object",
                "properties": {
                    "idee": {
                        "type": "string",
                        "description": (
                            "Die Folgen-Idee aus der Eltern-Nachricht, "
                            "z. B. 'Stigi findet einen geheimen Tunnel "
                            "unter dem Garten'. 1–2 Sätze."),
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
        # HFE-5: Session-State überbrückt propose→execute (Befund 1).
        # chat_id → {titel, text, voice, idee} aus dem Buddy-Vorschlag.
        # Nur eine offene Vorschlag-Session pro Chat — älter wird überschrieben.
        self._pending_vorschlaege: dict[object, dict] = {}

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — holt Folgen-Vorschlag vom Hörspiel-Buddy (HFE-3/4).

        Ruft hfe_mod.propose() auf. Bei Erfolg wird ein Proposal mit dem
        strukturierten Vorschlag-Text zurückgegeben (EC-10-Gate feuert).
        Speichert titel/text/voice/idee im Session-State, damit execute()
        sie ohne Modell-Kanal-Vertrauen bekommt (HFE-5, Befund 1).

        Bei Fehler wird die Exception weitergereicht — agent.py fängt sie
        als is_error=True-Tool-Result; das LLM antwortet entsprechend.

        HFE-7: kein tg.send_*-Aufruf in dieser Methode.
        """
        args = arguments or {}
        idee  = (args.get("idee") or "").strip()
        voice_hint = args.get("voice") or None

        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)
        chat_id = turn_context.chat_id

        # Wirft BerechtigungError, ValueError oder HoerspielClientError —
        # alle propagieren zu agent.py.
        result_text = hfe_mod.propose(
            hoerspiel_client=self._hoerspiel_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            idee=idee,
            voice_hint=voice_hint,
        )

        # Felder aus dem strukturierten Vorschlag-Text extrahieren und
        # in Session-State schreiben — execute() liest daraus (HFE-5).
        titel, text, voice = _extrahiere_vorschlag_felder(result_text, voice_hint,
                                                           self._hoerspiel_client)
        self._pending_vorschlaege[chat_id] = {
            "titel": titel,
            "text": text,
            "voice": voice,
            "idee": idee,
        }
        logger.debug("HFE-Vorschlag im Session-State gespeichert chat_id=%s titel=%r",
                     chat_id, titel)

        # Nur bei Erfolg: Proposal zurückgeben → EC-10-Gate feuert (HFE-1/3).
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
            try:
                self._tg.send_message(
                    chat_id,
                    "Der Hörspiel-Vorschlag ist nicht mehr verfügbar — "
                    "bitte erneut starten.")
            except Exception:
                pass
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
