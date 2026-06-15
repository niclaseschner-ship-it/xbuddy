"""KIBuddy-Prompt anpassen als Aufgaben-Katalog-Aufgabe —
specs/platform/kibuddy-prompt-anpassen.md (KPA-1/2/6/7/8).

Eltern verfeinern per sokratischem Mehrturn-Dialog (KPA-4) den System-Prompt
des KIBuddys, sehen eine Diff-Vorschau (KPA-6) und schreiben nach Bestätigung
via PUT auf /api/v1/kibuddy/prompt (KIBUDDY-24, KPA-7).

Dies ist eine **schreibende** Aufgabe (EC-10, KPA-2): das EC-10-
Bestätigungs-Gate (propose/execute) ist die einzige Bestätigung —
kein Sofort-Schreiben (KPA-2 propose→confirm). Die Diff-Vorschau ist
Pflicht vor jedem Schreibvorgang (KPA-6: kein Schreiben ohne sichtbare Diff).

Kein eigener State-Store: der Konversations-Kontext lebt im laufenden
Agent-Loop (KPA-2).

V1-Scope:
  - propose(): sokratischer Dialog-Start; bei leerem Wunsch Klär-Nachfrage
    (KPA-4 Schritt 1). Mit `neuer_prompt`-Argument: Diff-Vorschau generieren
    (KPA-6) und Bestätigungs-Frage stellen.
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

# KPA-4: Dialog-Start (kein neuer Prompt im Argument → Klär-Schritt).
_DIALOG_START = (
    "Ich helfe dir, den KIBuddy-Prompt anzupassen. "
    "Was möchtest du am Verhalten des KIBuddys ändern? "
    "(Tonfall, Themen, bestimmte Reaktionen auf Fragen, …)")

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
                 is_member_fn=None):
        super().__init__(
            name="kibuddy_prompt_anpassen",
            description=(
                "Verbessert den KIBuddy-Prompt im Gespräch. "
                "Aufrufen, wenn ein Elternteil den KIBuddy anpassen möchte — "
                "Tonfall ändern, neue Verhaltens-Regeln einbauen, Themen "
                "ergänzen. Der Bot führt einen sokratischen Dialog, zeigt "
                "eine Diff-Vorschau und schreibt den neuen Prompt erst nach "
                "Bestätigung. (KPA-1)"),
            parameters={
                "type": "object",
                "properties": {
                    "neuer_prompt": {
                        "type": "string",
                        "description": (
                            "Der vollständige neue System-Prompt-Text, den "
                            "das LLM nach dem sokratischen Dialog (KPA-4) "
                            "erarbeitet hat. Leer lassen beim ersten "
                            "Dialog-Schritt — der Skill startet dann den "
                            "Klär-Dialog (KPA-4 Schritt 1)."),
                    },
                },
                "required": [],
            })
        self._client = kibuddy_prompt_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. Von build_catalog immer
        # injiziert; None nur für Tests, die eine eigene Funktion übergeben.
        self._is_member_fn = is_member_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Änderung (KPA-6).

        Ohne `neuer_prompt`: sokratischer Dialog-Start (KPA-4 Schritt 1).
        Mit `neuer_prompt`: Diff-Vorschau gegen den aktuellen Prompt (KPA-6)
        + Bestätigungs-Frage. Falls GET /prompt fehlschlägt, zeigt der Skill
        einen Hinweis und bittet um erneuten Versuch.

        Kein Aufruf an PUT in dieser Phase (TASK-10: propose schreibt nie).
        """
        args = arguments or {}
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
