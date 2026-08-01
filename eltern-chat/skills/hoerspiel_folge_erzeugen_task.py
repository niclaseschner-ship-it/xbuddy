"""Hörspiel-Folge erzeugen als Aufgaben-Katalog-Aufgabe — specs/platform/
hoerspiel-folge-erzeugen.md (HFE-1, HFE-8, EC-8/EC-10, E-HFE-1 … E-HFE-5,
HFE-11, HFE-12, E-HFE-4 V1.1).

Diese Aufgabe ist der V1-Trigger der `hoerspiel_folge_erzeugen`-Funktion
(HFE-1, E-HFE-1): versteht der Agent eine natürlichsprachige Bitte
(„Schreib eine Folge über Schnee"), holt er einen Folgen-Vorschlag vom
Hörspiel-Buddy — nach EC-10-Bestätigung baut er das Album.

Eine **schreibende** Aufgabe (EC-10, HFE-1): Cluster C / Capability-Karte
(E-HFE-5, A2-Klausel trifft nicht — Album-Bau ist 1–5-min-Pipeline, kein One-Shot). Die
propose/execute-Zweiteilung ist die einzige Bestätigung; kein Sofort-Undo.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(HFE-1 / E-HFE-1) — keine eigene LLM-/TTS-Logik.

V1.1 (2026-06-19, HFE-11 / HFE-12 / E-HFE-4): `execute()` läuft im
Daemon-Thread im Task, der Polling-Loop ist während des 1–5-min-Album-
Baus frei (Single-Slot pro chat_id via `_HfeJobStore`).
"""

import contextlib
import logging
import re
import threading
import time

from tasks import HOERSPIEL_INSTANZEN, Proposal, WriteTask

import skills.hoerspiel_folge_erzeugen as hfe_mod

logger = logging.getLogger(__name__)


# HSP-43 / #1263: HFE-enum + Prompt-Namen aus der EINEN eltern-chat-Instanz-Liste
# (tasks.HOERSPIEL_INSTANZEN) abgeleitet — kein separater mia/finn-Hardcode mehr.
_HFE_KIND_IDS = [i["kind_id"] for i in HOERSPIEL_INSTANZEN]
_HFE_NAMEN = [i["name"] for i in HOERSPIEL_INSTANZEN]


def _hoerspiel_origin_mit_schema(origin: str) -> str:
    """Instanz-`origin` aus der zentralen instanzen.json-Registry (z. B.
    "127.0.0.1:5053", ohne Schema) zu einer nutzbaren Client-URL machen (Option C,
    #1732). Leer bleibt leer → Default-Client-Fallback."""
    origin = (origin or "").strip().rstrip("/")
    if origin and "://" not in origin:
        origin = "http://" + origin
    return origin


def _oder_liste(items) -> str:
    """»a, b oder c« — Aufzählung für Description/Rückfrage (HSP-43)."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return "%s oder %s" % (", ".join(items[:-1]), items[-1])


_HFE_NAMEN_ODER = _oder_liste(_HFE_NAMEN)       # z. B. "Mia, Finn oder Emil"
_HFE_IDS_ODER = _oder_liste(_HFE_KIND_IDS)      # z. B. "mia, finn oder emil"


# ============================================================
#  HFE-11 — Job-Single-Slot pro Chat
# ============================================================


class _HfeJobStore:
    """In-Memory Single-Slot pro chat_id (HFE-11).

    Hält pro chat_id maximal einen Slot mit `started_at = monotonic()`.
    `try_acquire(chat_id)` ist atomar (RLock); wenn ein Slot älter als
    `timeout` (600 s) ist, gilt er als „stale" und darf überschrieben
    werden (Schutz vor silent Thread-Tod — HFE-11).

    Bewusst privat im Task-Modul: kein SESS-Eintrag, kein Eltern-Chat-
    `Context`, keine Persistenz (HFE-12 — Restart-Verlust akzeptiert).
    """

    _DEFAULT_TIMEOUT_SEC = 600.0
    # Indirektion für Tests: monkeypatchbar.
    _now = staticmethod(time.monotonic)

    def __init__(self, timeout_sec: float = _DEFAULT_TIMEOUT_SEC):
        self._timeout = float(timeout_sec)
        self._slots: dict = {}     # chat_id → started_at (monotonic)
        self._lock = threading.RLock()

    def try_acquire(self, chat_id) -> bool:
        """Versucht, einen Slot für chat_id zu belegen.

        Returns True, wenn der Slot belegt wurde (kein bisheriger Job
        ODER stale-Slot überschrieben); False, wenn ein lebender Job
        bereits läuft.
        """
        with self._lock:
            now = self._now()
            started_at = self._slots.get(chat_id)
            if started_at is not None and (now - started_at) < self._timeout:
                return False
            self._slots[chat_id] = now
            return True

    def release(self, chat_id) -> None:
        """Gibt den Slot frei (No-op, wenn nicht belegt)."""
        with self._lock:
            self._slots.pop(chat_id, None)

    def is_active(self, chat_id) -> bool:
        """True, wenn ein lebender (nicht-stale) Slot existiert."""
        with self._lock:
            started_at = self._slots.get(chat_id)
            if started_at is None:
                return False
            return (self._now() - started_at) < self._timeout


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
                # HSP-43 / #1263: Namensliste aus der Instanz-Konstante.
                f"Erstellt eine neue Hörspiel-Folge für eine Instanz "
                f"({_HFE_NAMEN_ODER}): schreibt einen Folgentext per KI und "
                "vertont ihn als Album.\n\n"
                "Aufrufen, wenn jemand sagt »Schreib eine Folge über …«, "
                "»Neue Folge«, »Neues Hörbuch«, »Neues Hörspiel«, »Hörbuch "
                "anlegen«, »Hörspiel machen«, »Mach Mia eine Folge«, "
                "»Mach Finn eine Folge«, »Schreib eine Folge«, »Folge "
                "erzeugen« — auch OHNE konkreten Inhalt/Suffix. Plus mit "
                "Inhalt: »Neue Folge über X«, »Mach Mia eine Folge zu Y«, "
                "»Hörbuch über Z«. Plus Themen-Anfrage: »Welche Themen gibt "
                "es?«, »Was könnte ich Mia erzählen?«, »Vorschläge?«.\n\n"
                "WICHTIG: bei JEDEM Hörspiel-/Hörbuch-/Folgen-Trigger SOFORT "
                "diesen Skill aufrufen — KEINE eigenen Rückfragen stellen, "
                "der Skill macht die Diskussion und holt Themen-Vorschläge "
                "selbst (HFE-3 Sub-Case 1).\n\n"
                f"Parameter `kind_id`: Pflicht-Parameter ({_HFE_IDS_ODER}) — "
                "welche Instanz die Folge bekommt (HFE-3, E-HFE-6). Bei "
                f"Mehrdeutigkeit Rückfrage stellen: »Für {_HFE_NAMEN_ODER}?«.\n\n"
                "Parameter `idee`: die Folgen-Idee aus der Eltern-Nachricht "
                "(1–2 Sätze). LEER STRING »« setzen, wenn die Eltern noch "
                "keine konkrete Idee genannt haben (»Neues Hörbuch«, »Mach "
                "eine Folge«) — der Skill holt dann eine Themen-Liste "
                "(HFE-3 Sub-Case 1).\n\n"
                "Parameter `idee_diskussion` (bool, optional): True setzen, "
                "wenn die Idee konkret aber noch unvollständig ist und der "
                "Agent mehr Details klären will (HFE-3 Sub-Case 2).\n\n"
                "Voice-Wechsel (#995): Die Stimme (shimmer/onyx) wählt die "
                "Familie ausschließlich in der Hörspiel-Mini-App-Einstellung — "
                "NICHT im Chat. Antworten wie »mit onyx vertonen« oder »auf "
                "shimmer wechseln« sind KEIN Trigger für diesen Skill. Falls "
                "danach gefragt wird, antworte: »Voice wählst du in der "
                "Hörspiel-Mini-App.«\n\n"
                "Eltern-Signal-Phrasen (beenden die Diskussion und lösen den "
                "Vorschlag-Endpoint aus): »los«, »los gehts«, »mach das«, "
                "»passt so«, »okay so«, »fang an«, »jetzt vertonen«, "
                "»schreib jetzt«. Bei diesen Phrasen diesen Task mit der "
                "zusammengeführten konkreten Idee und idee_diskussion=False "
                "aufrufen (HFE-3, HFE-6). WICHTIG: Diese Phrasen lösen den "
                "Vorschlag NUR aus, solange noch KEIN Vorschlag vorliegt. Wenn "
                "du gerade eine Folge vorgeschlagen hast (»Vertonen? Antworte "
                "nur mit »ja«…«), rufe diesen Task bei einer solchen Phrase NICHT "
                "erneut auf — die Bestätigung läuft deterministisch außerhalb von "
                "dir über EC-10. Erneutes Aufrufen würde nur neu texten statt zu "
                "vertonen."),
            parameters={
                "type": "object",
                "properties": {
                    "kind_id": {
                        "type": "string",
                        # HSP-43 / #1263: enum aus der Instanz-Konstante abgeleitet.
                        "enum": list(_HFE_KIND_IDS),
                        "description": (
                            "Für welche Instanz die Folge erzeugt werden soll: "
                            f"{_HFE_IDS_ODER}. Wenn die Mutter einen Namen nennt "
                            "(z. B. 'für Mia'), die passende kind_id setzen "
                            "(mia/finn/emil). Pflicht-Argument (HFE-3, E-HFE-6)."),
                    },
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
                },
                "required": ["kind_id", "idee"],
            })
        self._tg = tg
        self._hoerspiel_client = hoerspiel_client
        self._display_url_origin = display_url_origin or ""
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._is_member_fn = is_member_fn
        self._mini_app_base_url = mini_app_base_url or ""
        # E-HFE-6 / RAT-17 / #910 / HSP-43 / Option C (#1732): Mini-Map kind_id →
        # HoerspielClient-Instanz. Ermöglicht dem Task, bei jedem propose()-Aufruf
        # den passenden Client anhand der kind_id zu wählen (Option A: je Client eine
        # Origin). Kein hardcodiertes Slug-Dict mehr: die Origin je kind_id kommt aus
        # der zentralen `instanzen.json`-Registry (HOERSPIEL_INSTANZEN trägt das
        # `origin`-Feld). Leer/kein Origin → Default-Client-Fallback (hoerspiel_client).
        # Origin je kind_id DIREKT aus der zentralen instanzen.json-Registry
        # (tools.instanzen trägt slug+origin; HOERSPIEL_INSTANZEN bleibt bewusst
        # kind_id/name-only, INST-1-Grenze). Kein hardcodiertes Slug-Dict.
        from skills.hoerspiel_client import HoerspielClient as _HoerspielClient
        from tools import instanzen as _instanzen
        _origin_by_kind_id = {
            e["slug"]: _hoerspiel_origin_mit_schema(e.get("origin", ""))
            for e in _instanzen.lade_instanzen("hoerspiel")
        }
        self._client_by_kind_id: dict = {}
        for _kid in _HFE_KIND_IDS:
            _origin = _origin_by_kind_id.get(_kid, "")
            self._client_by_kind_id[_kid] = (
                _HoerspielClient(origin_url=_origin, kind_id=_kid)
                if _origin else self._hoerspiel_client
            )
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
        # HFE-11 (V1.1): Single-Slot pro chat_id für laufende Album-Bauten.
        # execute() startet einen Daemon-Thread; der Polling-Loop ist frei.
        self._jobstore = _HfeJobStore()
        # chat_id → Worker-Thread (Test-Helper für Join).
        self._active_threads: dict = {}
        self._active_threads_lock = threading.RLock()

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
        idee_diskussion = bool(args.get("idee_diskussion", False))

        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)
        chat_id = turn_context.chat_id

        # E-HFE-6 / RAT-17 / #910 / T954: kind_id ist Pflicht-Argument (HFE-9).
        # Kein stiller Default mehr — fehlende oder unbekannte kind_id wirft
        # ValueError → agent.py fängt als is_error=True-Tool-Result (AC-2,
        # Watchdog-Fix Pfad A). EC-10-Gate feuert NICHT.
        if "kind_id" not in args:
            raise ValueError(
                "Tool-Call ohne kind_id — HFE-9 verlangt Pflicht-Argument.")
        kind_id = args["kind_id"]
        if kind_id not in self._client_by_kind_id:
            erlaubt = ", ".join(sorted(self._client_by_kind_id))
            raise ValueError(
                f"Unbekannte kind_id {kind_id!r}. Erlaubt: {erlaubt}.")
        active_client = self._client_by_kind_id[kind_id]

        # HFE-10: "erste propose()-Antwort des Turns" bestimmen.
        # Heuristik: wenn für diesen Chat noch kein propose() des laufenden
        # HFE-Turns gelaufen ist, ist es die erste Antwort.
        is_first = chat_id not in self._first_propose_done
        # Als "gesehen" markieren — alle Folge-Antworten sind nicht-erste.
        self._first_propose_done.add(chat_id)

        # Wirft BerechtigungError, ValueError oder HoerspielClientError —
        # Sub-Cases 1+2 via ValueError, Sub-Case 3 via Tuple-Return.
        propose_result = hfe_mod.propose(
            hoerspiel_client=active_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            idee=idee,
            kind_id=kind_id,
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
            titel, text, voice = _extrahiere_vorschlag_felder(result_text)

        self._pending_vorschlaege[chat_id] = {
            "titel": titel,
            "text": text,
            "voice": voice,
            "idee": idee,
            "kind_id": kind_id,   # HFE-3/E-HFE-6: für execute()-Client-Lookup
        }
        # HFE-10: Sub-Case 3 war erfolgreich — next propose() ist ein neuer
        # Turn (nach EC-10-Confirm). Flag zurücksetzen damit Beifang erneut erscheint.
        self._first_propose_done.discard(chat_id)
        logger.debug("HFE-Vorschlag im Session-State gespeichert chat_id=%s titel=%r",
                     chat_id, titel)

        # Nur bei Erfolg (Sub-Case 3): Proposal zurückgeben → EC-10-Gate feuert.
        return Proposal(result_text)

    def execute(self, arguments, turn_context):
        """Trampolin: spawnt Daemon-Thread, returnt sofortige Quittung (HFE-11).

        V1.1 (2026-06-19, HFE-11 / E-HFE-4): `execute()` startet einen
        Daemon-Thread und returnt in < 100 ms eine kurze Quittung. Der
        Polling-Loop ist während des 1–5-min-Album-Baus frei (HFE-11).
        Bei Erfolg/Crash postet der Worker-Thread direkt via tg.send_message.

        Liest titel/text/voice/idee aus dem Session-State (Befund 1) —
        nicht aus dem Modell-Kanal `arguments`, da das Framework nur die
        ursprünglichen Tool-Call-arguments persistiert ({idee, voice?}).

        Single-Slot pro chat_id (HFE-11): Während ein Job läuft, wird ein
        zweites `execute()` mit einer „warte kurz"-Quittung beantwortet —
        kein zweiter Thread, kein zweiter HTTP-Call.

        Restart-Verlust akzeptiert (HFE-12, OPEN-HSP-L V2).

        TASK-10: execute() ist außerhalb des Agent-Loops und sendet selbst.
        TASK-5: is_async bleibt False — wir wollen, dass das Framework die
        post_execute_hooks-Iteration regulär macht (Tuple bleibt leer).
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

        # HFE-11: Single-Slot pro chat_id — Slot belegt → sofortige
        # „warte kurz"-Quittung, kein zweiter Thread, kein zweiter HTTP-Call.
        if not self._jobstore.try_acquire(chat_id):
            logger.info(
                "HFE-execute: Slot für chat_id=%s belegt — zweite Bestätigung "
                "abgewiesen (HFE-11).", chat_id)
            with contextlib.suppress(Exception):
                self._tg.send_message(
                    chat_id,
                    "Ich baue gerade noch eine Folge — bitte kurz warten.")
            # Pending-Vorschlag war für DIESE Bestätigung — restaurieren wäre
            # gefährlich (Doppel-Confirm); wir verwerfen ihn bewusst.
            return "Ich baue gerade noch eine Folge — bitte kurz warten."

        # E-HFE-6 / HFE-3: kind_id aus dem pending-Dict → passenden Client wählen
        # (analog propose()). Verhindert den Mia-Default-Bug (T962-Befund).
        kind_id = pending["kind_id"]
        active_client = self._client_by_kind_id.get(kind_id, self._hoerspiel_client)

        def _worker():
            try:
                hfe_mod.execute(
                    hoerspiel_client=active_client,
                    tg=self._tg,
                    chat_id=chat_id,
                    display_url_origin=self._display_url_origin,
                    titel=pending["titel"],
                    text=pending["text"],
                    voice=pending["voice"],
                    idee=pending["idee"],
                )
            except Exception:
                # HFE-11: Crash im Album-Bau → Fehler-Bubble + Slot frei (finally).
                logger.exception(
                    "HFE-execute Worker-Thread chat_id=%s: Album-Bau crashed",
                    chat_id)
                with contextlib.suppress(Exception):
                    self._tg.send_message(
                        chat_id,
                        "Beim Folge-Bau ist etwas schiefgegangen — "
                        "bitte erneut starten.")
            finally:
                self._jobstore.release(chat_id)
                with self._active_threads_lock:
                    self._active_threads.pop(chat_id, None)

        thread = threading.Thread(
            target=_worker,
            name="hfe-job-%s" % chat_id,
            daemon=True,
        )
        with self._active_threads_lock:
            self._active_threads[chat_id] = thread
        thread.start()
        logger.info(
            "HFE-execute: Daemon-Thread %r gestartet (chat_id=%s, titel=%r)",
            thread.name, chat_id, pending["titel"])

        # HFE-11: Sofortige Quittung (< 100 ms). Der Worker postet die
        # Erfolgs-/Fehler-Bubble selbst per tg.send_message.
        return "Folge wird gebaut, melde mich."

    def _wait_for_active_job(self, chat_id, timeout: float = 10.0) -> bool:
        """Test-Helper: joint den Worker-Thread für chat_id (oder no-op).

        Returns True, wenn der Thread nicht (mehr) lief oder rechtzeitig
        beendet wurde; False bei Timeout. Nicht für Produktiv-Code gedacht.
        """
        with self._active_threads_lock:
            thread = self._active_threads.get(chat_id)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()


def _extrahiere_vorschlag_felder(result_text: str) -> tuple[str, str, str]:
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
