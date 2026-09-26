"""App öffnen als Aufgaben-Katalog-Aufgabe — eltern-chat.md EC-46 (#1964).

Adapter der Funktion `skills.app_oeffnen.app_oeffnen`. Eine **lesende**
Aufgabe (EC-9): verändert keine Familien-Daten. TASK-10c Form (b): run()
returnt `{text, presentation}`, das Framework sendet (EC-29).

Die App-Liste steht NICHT im Code: `to_def()` baut Beschreibung und
`enum` der Keys pro Turn aus dem Ansichts-Verzeichnis (`AppVerzeichnis`,
Seiten-Registry `GET /api/v1/seiten`). Eine neue `views.json`-Zeile ist
damit ohne Chat-Änderung erfragbar; Trigger-Wörter einer App gehören in
ihre `synonyme` (EC-40 Achse B — die App-Bezeichnungen leben im Verzeichnis).
"""

import logging

from model import TaskDef
from tasks import ReadTask

from skills import app_oeffnen as ao_mod

logger = logging.getLogger(__name__)

NAME = "app_oeffnen"

_BESCHREIBUNG = (
    "Öffnet eine App von XBuddy: schickt eine kurze Zeile und Knöpfe "
    "(Mini-App, im Browser, bei installierbaren Apps Installieren). "
    "Sofort aufrufen — NICHT erst fragen —, wenn jemand eine App, Seite, "
    "Ansicht oder ihre Einstellungen haben will; auch ohne Aktions-Verb, "
    "wenn eine Aktion (settings/einstellungen/anpassen/bearbeiten/ändern/"
    "öffnen/zeigen/schicken/geben/app/mini-app/löschen/umsortieren/sortieren/"
    "hinzufügen) mit einer App-Bezeichnung zusammenkommt. Beispiele: "
    "'gib mir die Routine settings', 'Hörbuch hören', 'Garderobe bearbeiten', "
    "'schick mir den Wochenplan', 'wer macht was'. "
    "Welche App gemeint ist, erkennst du an Label und Synonymen in der Liste "
    "unten; übergib ihren key. Passen mehrere (z. B. 'Wetter' → Wetter heute "
    "und Wetter-Regeln), übergib alle passenden keys (höchstens 3) — dann "
    "kommen beide Knopfreihen in einer Nachricht. "
    "Schreibe in deiner Antwort NIEMALS einen Knopf als Markdown-Text "
    "(z. B. '[**…öffnen**]') und versprich keinen 'Knopf unten' — der "
    "Inline-Knopf kommt automatisch über den Tool-Call dieses Skills. "
    "Abgrenzung: Einkaufsliste mit Inhalt ('was muss ich kaufen') → "
    "einkauf_zeigen; alle Apps auf einen Blick → seiten_uebersicht; neue "
    "Hörspiel-Folge schreiben → hoerspiel_folge_erzeugen; einzelne Routine-Zeit "
    "setzen ('Abfahrt auf 7:50') → routine_zeiten_setzen; beiläufige "
    "Settings-Erwähnung (Stimme, Tempo) → sprachlicher Verweis ohne Tool-Call."
)

_OHNE_VERZEICHNIS = (
    " (Das App-Verzeichnis ist gerade nicht erreichbar — rufe den Skill "
    "trotzdem mit dem vermuteten key auf, er meldet es ehrlich.)"
)


def _app_zeile(eintrag):
    synonyme = ", ".join(eintrag.get("synonyme") or [])
    zeile = "- %s: %s [%s]" % (eintrag["key"], eintrag["label"],
                               eintrag.get("zielgruppe") or "?")
    if synonyme:
        zeile += " — auch: %s" % synonyme
    return zeile


class AppOeffnenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die `app_oeffnen` auslöst (EC-46)."""

    anzeige_copy = "Ich schicke dir jede App als Knopf — frag einfach nach ihr."

    def __init__(self, is_member_fn, verzeichnis, basis_url=""):
        super().__init__(
            name=NAME,
            description=_BESCHREIBUNG,
            parameters=self._parameter([]))
        self._is_member_fn = is_member_fn
        self._verzeichnis = verzeichnis
        self._basis_url = (basis_url or "").rstrip("/")

    @staticmethod
    def _parameter(keys):
        items = {"type": "string"}
        if keys:
            items["enum"] = list(keys)
        return {
            "type": "object",
            "properties": {
                "apps": {
                    "type": "array",
                    "items": items,
                    "description": "keys der gewünschten Apps (1 bis 3).",
                },
            },
            "required": ["apps"],
        }

    def to_def(self):
        """Werkzeug-Definition mit der App-Liste aus dem Verzeichnis (pro Turn)."""
        eintraege = self._verzeichnis.eintraege()
        if eintraege:
            beschreibung = (_BESCHREIBUNG + "\nApps (key: Label [zielgruppe] — "
                            "Synonyme):\n" + "\n".join(_app_zeile(e) for e in eintraege))
        else:
            beschreibung = _BESCHREIBUNG + _OHNE_VERZEICHNIS
        return TaskDef(name=self.name, description=beschreibung, kind=self.kind,
                       parameters=self._parameter([e["key"] for e in eintraege]))

    def run(self, arguments, turn_context):
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None
        keys = (arguments or {}).get("apps") or []
        if isinstance(keys, str):
            keys = [keys]
        result = ao_mod.app_oeffnen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            keys=[str(k) for k in keys],
            eintraege=self._verzeichnis.eintraege(),
            is_member_fn=self._is_member_fn,
            basis_url=self._basis_url,
        )
        logger.info("AppOeffnenTask: chat=%s, Form-(b)-Dict zurückgegeben", chat_id)
        return result
