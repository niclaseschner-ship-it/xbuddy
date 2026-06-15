"""KIBuddy-Prompt anpassen als Aufgaben-Katalog-Aufgabe —
specs/platform/kibuddy-prompt-anpassen.md (KPA-1/2/5/6/7/8).

Eltern verfeinern per sokratischem Mehrturn-Dialog (KPA-4) den System-Prompt
des KIBuddys, können den aktuellen Prompt auf Wunsch anzeigen lassen (KPA-5),
sehen eine Diff-Vorschau (KPA-6) und schreiben nach Bestätigung via PUT auf
/api/v1/kibuddy/prompt (KIBUDDY-24, KPA-7).

Dies ist eine **schreibende** Aufgabe (EC-10, KPA-2): das EC-10-
Bestätigungs-Gate (propose/execute) ist die einzige Bestätigung —
kein Sofort-Schreiben (KPA-2 propose→confirm). Die Diff-Vorschau ist
Pflicht vor jedem Schreibvorgang (KPA-6: kein Schreiben ohne sichtbare Diff).

Kein eigener State-Store: der Konversations-Kontext lebt im laufenden
Agent-Loop (KPA-2).

V1-Scope:
  - propose() mit aktion='anzeigen': aktuellen Prompt lesen und anzeigen
    (KPA-5). Bei >3500 Zeichen: mehrteilige Antwort mit (Teil X/Y)-Markierung.
  - propose() ohne aktion / aktion='vorschlagen': sokratischer Dialog-Start;
    bei leerem Wunsch Klär-Nachfrage (KPA-4 Schritt 1). Mit
    `neuer_prompt`-Argument: Diff-Vorschau generieren (KPA-6) und
    Bestätigungs-Frage stellen.
  - execute(): PUT /api/v1/kibuddy/prompt (KPA-7). Erfolgs- oder Fehler-
    Quittung mit .bak-Hinweis bei 500 (KIBUDDY-15).

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(KPA-1) — keine eigene Datei-Logik (KIBUDDY-15: Datenhaltung beim Buddy).
"""

import difflib
import logging

from tasks import Proposal, WriteTask

from skills.kibuddy_prompt_anpassen_client import (
    KibuddyPromptClientError,
)

logger = logging.getLogger(__name__)


# KPA-7 / EC-10: Quittungen in den Agent-Loop.
_QUITTUNG_ERFOLG = (
    "Der neue Prompt ist aktiv — der KIBuddy nutzt ihn ab der nächsten "
    "Frage.")
_QUITTUNG_ZU_LANG = (
    "Der Prompt ist zu lang (Backend meldet 400). Bitte kürze ihn und "
    "versuche es erneut.")
_QUITTUNG_ZU_KURZ = (
    "Der Prompt darf nicht leer sein (Backend meldet 400). Bitte trage "
    "einen Inhalt ein.")
_QUITTUNG_SCHREIBFEHLER = (
    "Schreibfehler auf dem Server (500) — der alte Prompt bleibt aktiv "
    "(Backup: prompt.txt.bak, KIBUDDY-15). Bitte versuche es gleich "
    "nochmal oder wende dich an den Operator.")
_QUITTUNG_NICHT_ERREICHBAR = (
    "Der KIBuddy ist gerade nicht erreichbar — bitte gleich nochmal "
    "versuchen.")
_QUITTUNG_KEIN_NEUER_PROMPT = (
    "Ich habe keinen fertigen Prompt zum Schreiben. "
    "Beschreibe bitte zuerst deine gewünschte Änderung.")

# KPA-4: Dialog-Start mit expliziter LLM-Loop-Anweisung im Sach-Ton.
# Live-Bug 2026-06-15 (Nic): ohne Loop-Hint endet der Dialog nach Eltern-Antwort
# — LLM ruft den Skill nicht erneut auf mit `neuer_prompt`. Fix: Sach-Pfad-
# Anweisung ohne []-Markup-Blöcke (Vorbild: RPS-description, foto_senden).
_DIALOG_START = (
    "Ich helfe dir, den KIBuddy-Prompt anzupassen. "
    "Stell dem Elternteil 1–3 Rückfragen zu Tonfall, Themen oder "
    "Verhaltensregeln. Sobald die Wünsche klar sind, formuliere den "
    "vollständigen neuen Prompt-Text (Baseline: aktueller Prompt — bei Bedarf "
    "via kibuddy_prompt_anpassen mit aktion='anzeigen' holen). "
    "Rufe danach diesen Task erneut auf mit "
    "aktion='vorschlagen' und neuer_prompt=<vollständiger Vorschlag>. "
    "Der Skill zeigt dann die Diff-Vorschau zur Bestätigung. "
    "Ohne diesen zweiten Aufruf mit neuer_prompt endet der Dialog ohne Wirkung.\n\n"
    "Was möchtest du am Verhalten des KIBuddys ändern? "
    "(Tonfall, Themen, bestimmte Reaktionen auf Fragen, …)")

# KPA-5: Fehler-Quittung beim Anzeige-Pfad (GET-Fehler).
_QUITTUNG_ANZEIGE_FEHLER = (
    "KIBuddy gerade nicht erreichbar — versuch es gleich nochmal.")

# KPA-5: Telegram-Zeichen-Limit pro Teil (Sicherheitsmarge vor 4096).
_TELEGRAM_MAX_ZEICHEN = 3500

# KPA-6: Diff-Vorschau-Rahmen.
_DIFF_HEADLINE = (
    "So würde dein neuer Prompt aussehen — ein letzter Blick:\n\n")
_DIFF_FOOTER = (
    "\n\nSoll ich den neuen Prompt übernehmen? "
    "Tippe **ja** zum Bestätigen, **nein** zum Verwerfen, "
    "oder beschreibe weitere Änderungen.")

# Kontextzeilen um geänderte Stellen (KPA-6: 2 Zeilen Kontext).
_DIFF_CONTEXT_LINES = 2


def _build_diff(alter_text, neuer_text):
    """Baut eine Diff-Vorschau im unified-diff-Stil (KPA-6).

    Liefert einen String mit:
      - `-`-Zeilen für entfernte Zeilen
      - `+`-Zeilen für neue Zeilen
      - `… N unveränderte Zeilen …`-Platzhalter für übersprungene Blöcke

    Vollständig identische Prompts: kurze Hinweis-Zeile statt leerer Diff.
    """
    alte_zeilen = alter_text.splitlines()
    neue_zeilen = neuer_text.splitlines()

    diff_lines = []
    for gruppe in difflib.SequenceMatcher(
            None, alte_zeilen, neue_zeilen).get_grouped_opcodes(
                _DIFF_CONTEXT_LINES):
        for tag, i1, i2, j1, j2 in gruppe:
            if tag == "equal":
                for line in alte_zeilen[i1:i2]:
                    diff_lines.append("  " + line)
            elif tag in ("replace", "delete"):
                for line in alte_zeilen[i1:i2]:
                    diff_lines.append("- " + line)
                if tag == "replace":
                    for line in neue_zeilen[j1:j2]:
                        diff_lines.append("+ " + line)
            elif tag == "insert":
                for line in neue_zeilen[j1:j2]:
                    diff_lines.append("+ " + line)

    if not diff_lines:
        return "(Kein Unterschied — der Prompt ist identisch.)"
    return "\n".join(diff_lines)


def _split_for_telegram(text: str,
                        max_per_part: int = _TELEGRAM_MAX_ZEICHEN) -> list:
    """Splittet langen Text in Teile ≤ max_per_part Zeichen (KPA-5).

    Bevorzugt Schnitte an \\n\\n-Grenzen; fällt auf \\n zurück; als letztes
    Mittel harter Schnitt. Gibt eine Liste von Teil-Strings zurück — bei
    kurzem Text ist die Liste einelementig.
    """
    if len(text) <= max_per_part:
        return [text]
    parts = []
    rest = text
    while rest:
        if len(rest) <= max_per_part:
            parts.append(rest)
            break
        # Bevorzuge letztes \n\n vor max_per_part
        cut = rest.rfind("\n\n", 0, max_per_part)
        if cut <= 0:
            cut = rest.rfind("\n", 0, max_per_part)
        if cut <= 0:
            cut = max_per_part
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    return parts


class KibuddyPromptAnpassenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »KIBuddy-Prompt anpassen«
    auslöst (KPA-8).

    V1 synchron: kein Worker-Thread, is_async=False. Das EC-10-Bestätigungs-
    Gate (propose/execute) ist die einzige Bestätigung (KPA-2: propose→confirm,
    **kein** Sofort-Schreiben).

    propose() mit `neuer_prompt`:
      - Lädt den aktuellen Prompt via GET (KPA-5-Naht).
      - Generiert Diff-Vorschau (KPA-6).
      - Stellt Bestätigungs-Frage.

    propose() ohne `neuer_prompt`:
      - Startet sokratischen Dialog (KPA-4 Schritt 1).

    execute() mit `neuer_prompt`:
      - PUT /api/v1/kibuddy/prompt (KPA-7).
      - Erfolgs-Quittung oder Fehler-Quittung mit .bak-Hinweis (KIBUDDY-15).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, kibuddy_prompt_client, family_group_chat_id_getter,
                 is_member_fn=None, tg=None, chat_id_getter=None):
        super().__init__(
            name="kibuddy_prompt_anpassen",
            description=(
                "Drei Aufruf-Pfade fuer den KIBuddy-Prompt:\n"
                "(A) ANZEIGEN (aktion='anzeigen'): aktuellen Prompt-Text "
                "holen und an die Eltern senden - bei Fragen wie "
                "\"zeig mir den Prompt\", \"wie lautet der aktuelle Prompt\", "
                "\"was steht im Prompt\".\n"
                "(B) DIALOG STARTEN (aktion='vorschlagen', neuer_prompt LEER): "
                "Klaer-Dialog mit 1-3 Rueckfragen fuehren, dann diesen Task "
                "erneut aufrufen mit Pfad C - bei Auftraegen wie "
                "\"lass mal den Prompt anpassen\", \"mach den Prompt "
                "freundlicher\", \"aendere den Tonfall\".\n"
                "(C) VORSCHLAGEN (aktion='vorschlagen' + neuer_prompt FERTIG): "
                "wenn du den vollstaendigen neuen Prompt nach Klaer-Dialog "
                "formuliert hast - der Skill validiert, zeigt Diff-Vorschau "
                "und schreibt nach Bestaetigung.\n\n"
                "KPA-4 MEHRTURN: Nach Pfad-B-Klaer-Dialog den Task ERNEUT "
                "aufrufen mit aktion='vorschlagen' und "
                "neuer_prompt=<vollstaendiger Vorschlag>. Ohne diesen "
                "zweiten Aufruf endet der Dialog ohne Wirkung."),
            parameters={
                "type": "object",
                "properties": {
                    "aktion": {
                        "type": "string",
                        "enum": ["anzeigen", "vorschlagen"],
                        "default": "vorschlagen",
                        "description": (
                            "anzeigen → aktuellen Prompt holen + zeigen "
                            "(KPA-5). Bei Eltern-Fragen wie 'zeig mir den "
                            "Prompt' / 'wie sieht der aktuelle Prompt aus' "
                            "/ 'was steht drin' → aktion=anzeigen. "
                            "vorschlagen → neuen Prompt-Text validieren + "
                            "Diff-Vorschau (KPA-6). Default: 'vorschlagen'."),
                    },
                    "neuer_prompt": {
                        "type": "string",
                        "description": (
                            "Der vollständige neue System-Prompt-Text, den "
                            "das LLM nach dem sokratischen Dialog (KPA-4) "
                            "erarbeitet hat. Nur bei aktion='vorschlagen' "
                            "relevant. Leer lassen beim ersten Dialog-Schritt "
                            "— der Skill startet dann den Klär-Dialog "
                            "(KPA-4 Schritt 1)."),
                    },
                },
                "required": [],
            })
        self._client = kibuddy_prompt_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. Von build_catalog immer
        # injiziert; None nur für Tests, die eine eigene Funktion übergeben.
        self._is_member_fn = is_member_fn
        # tg + chat_id_getter: optional, für KPA-5 Multi-Part-Send (FIX1).
        # Wenn tg gesetzt: langer Prompt wird direkt via tg.send_message
        # gesendet (analog HFE). chat_id_getter liefert die Ziel-Chat-ID,
        # falls turn_context.chat_id nicht ausreicht (Backward-Compat).
        self._tg = tg
        self._chat_id_getter = chat_id_getter

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Änderung (KPA-5/KPA-6).

        aktion='anzeigen': liest aktuellen Prompt via GET und gibt ihn zurück
        (KPA-5). Bei >3500 Zeichen mehrteilig mit (Teil X/Y)-Markierung.

        aktion='vorschlagen' (Default):
          Ohne `neuer_prompt`: sokratischer Dialog-Start (KPA-4 Schritt 1).
          Mit `neuer_prompt`: Diff-Vorschau gegen den aktuellen Prompt (KPA-6)
          + Bestätigungs-Frage. Falls GET /prompt fehlschlägt, zeigt der Skill
          einen Hinweis und bittet um erneuten Versuch.

        Kein Aufruf an PUT in dieser Phase (TASK-10: propose schreibt nie).
        """
        args = arguments or {}
        aktion = (args.get("aktion") or "vorschlagen").strip().lower()

        if aktion == "anzeigen":
            return self._propose_anzeigen(turn_context)

        # Fallback / aktion='vorschlagen'
        neuer_prompt = (args.get("neuer_prompt") or "").strip()

        if not neuer_prompt:
            # KPA-4 Schritt 1: kein fertiger Prompt → sokratischen Dialog starten.
            return Proposal(_DIALOG_START)

        # KPA-6: Diff-Vorschau gegen aktuellen Prompt.
        try:
            prompt_data = self._client.get_prompt()
            alter_prompt = prompt_data.get("prompt", "")
        except KibuddyPromptClientError as e:
            logger.warning(
                "kibuddy_prompt_anpassen: GET fehlgeschlagen für Diff — %s", e)
            # Ohne alten Prompt kein diff — trotzdem Bestätigungs-Frage stellen
            # (kein Abbruch, KPA-6-Geist: Diff ist Pflicht, aber bei GET-Fehler
            # zeigen wir den neuen Prompt ohne Vergleich).
            summary = (
                "Ich konnte den aktuellen Prompt nicht laden (KIBuddy nicht "
                "erreichbar) — hier ist dein neuer Vorschlag:\n\n"
                + neuer_prompt
                + _DIFF_FOOTER)
            return Proposal(summary)

        diff_text = _build_diff(alter_prompt, neuer_prompt)
        summary = _DIFF_HEADLINE + diff_text + _DIFF_FOOTER
        return Proposal(summary)

    def _propose_anzeigen(self, turn_context=None):
        """KPA-5: Liest den aktuellen Prompt und gibt ihn als Proposal zurück.

        Bei mehr als 3500 Zeichen und vorhandenem tg: Teile DIREKT via
        tg.send_message senden (analog HFE Multi-Part-Send, FIX1). Das
        Proposal.summary enthält dann nur einen kurzen Verweis.

        Ohne tg (Tests / Backward-Compat) oder bei kurzem Prompt: bisheriges
        Verhalten (Proposal.summary mit Volltext). Ohne tg bei langem Prompt:
        Fallback mit Warn-Quittung im summary.

        Fehler beim GET → klare Nutzer-Quittung (AC5).
        """
        try:
            prompt_data = self._client.get_prompt()
        except KibuddyPromptClientError:
            return Proposal(_QUITTUNG_ANZEIGE_FEHLER)

        prompt_text = prompt_data.get("prompt", "")
        byte_laenge = prompt_data.get("byte-laenge", len(prompt_text.encode("utf-8")))
        geaendert = prompt_data.get("geaendert-am", "unbekannt")

        header = (
            "Aktueller KIBuddy-Prompt "
            "(%s Bytes, geändert %s):\n\n" % (byte_laenge, geaendert)
        )
        volltext = header + prompt_text
        teile = _split_for_telegram(volltext)

        if len(teile) == 1:
            return Proposal(teile[0])

        # Mehrteilig: bei vorhandenem tg direkt senden (KPA-5, FIX1).
        if self._tg is not None:
            chat_id = getattr(turn_context, "chat_id", None)
            if chat_id is None and self._chat_id_getter is not None:
                chat_id = self._chat_id_getter()
            n = len(teile)
            for i, teil in enumerate(teile):
                markiert = "(Teil %d/%d)\n%s" % (i + 1, n, teil)
                try:
                    self._tg.send_message(chat_id, markiert)
                except Exception as exc:
                    logger.warning(
                        "kibuddy_prompt_anpassen: send_message fehlgeschlagen "
                        "(Teil %d/%d): %s", i + 1, n, exc)
            return Proposal("Aktueller KIBuddy-Prompt — siehe oben.")

        # Fallback ohne tg: Warn-Quittung im summary (Backward-Compat).
        logger.warning(
            "kibuddy_prompt_anpassen: langer Prompt (%d Zeichen) — "
            "Multi-Part-Send nicht verfügbar (tg fehlt)", len(volltext))
        n = len(teile)
        zusammen = "\n\n".join(
            "(Teil %d/%d)\n%s" % (i + 1, n, teil)
            for i, teil in enumerate(teile)
        )
        return Proposal(
            "Prompt zu lang für eine Nachricht — Multi-Part-Send nicht "
            "verfügbar.\n\n" + zusammen)

    def execute(self, arguments, turn_context):
        """Schreibt den neuen Prompt via PUT /api/v1/kibuddy/prompt (KPA-7).

        `neuer_prompt` muss in den Argumenten vorhanden sein (vom propose-
        Turn gebunden). Ohne Prompt: ehrliche Fehler-Quittung.

        Fehler-Pfade (KPA-7, KIBUDDY-24):
          - 400 (zu lang/kurz) → spezifische Nutzer-Quittung.
          - 500 (Schreibfehler) → Hinweis auf prompt.txt.bak (KIBUDDY-15).
          - Connection-Fehler → „nicht erreichbar"-Quittung.
        """
        args = arguments or {}
        neuer_prompt = (args.get("neuer_prompt") or "").strip()

        if not neuer_prompt:
            return _QUITTUNG_KEIN_NEUER_PROMPT

        # Berechtigungs-Prüfung: nur Familien-Mitglieder (EC-2, KPA-3).
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)
        if not is_member_fn(from_user_id):
            return ("KIBuddy-Prompt anpassen geht nur für Mitglieder "
                    "der Familien-Gruppe.")

        # KPA-7: PUT /api/v1/kibuddy/prompt.
        try:
            self._client.put_prompt(neuer_prompt)
        except KibuddyPromptClientError as e:
            status = getattr(e, "status", None)
            if status == 400:
                # Unterscheide zu lang vs. zu kurz anhand Prompt-Länge.
                if not neuer_prompt:
                    return _QUITTUNG_ZU_KURZ
                return _QUITTUNG_ZU_LANG
            if status == 500:
                return _QUITTUNG_SCHREIBFEHLER
            logger.warning(
                "kibuddy_prompt_anpassen: KIBuddy nicht erreichbar — %s", e)
            return _QUITTUNG_NICHT_ERREICHBAR

        return _QUITTUNG_ERFOLG
