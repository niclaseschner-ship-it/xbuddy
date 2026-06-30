"""Wetter-Regeln öffnen — specs/platform/wetter-regeln-oeffnen.md (WRO-1 … WRO-8).

Aufrufbare, trigger-agnostische Funktion (WRO-1, E-WRO-1-Muster): baut eine
kompakte Übersichts-Nachricht + Inline-Button auf den Garderoben-Editor des
Wetter-Buddys (`/display/wetter/regeln`, WRO-4/WRO-5) und gibt ein
Form-(b)-Dict zurück (TASK-10c).

WRO ist reiner Türöffner ohne Lese-Call in V1 (E-WRO-3): keine Counter-Zeile,
keine Vorschau-Daten — der Button öffnet den Editor direkt.

TASK-10c Form (b): der Skill returnt `{text, presentation}` — der Task
reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
übersetzt `presentation` in eine Telegram-Nachricht. Der Skill sendet
NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

Schwester-Skill von routine_anpassen_oeffnen (RAO) — Stil-Anker gespiegelt
(eltern-chat-skills.md Klasse-B-Bauplan). Wesentlicher Unterschied: kein
Lese-Call vor dem Button (E-WRO-3 vs. RAO-4).

**Eingang:**
  - `chat_id`          — Telegram-Chat, in dem die Antwort landen wird (WRO-1).
  - `from_user_id`     — Telegram-User-ID des Aufrufers (Berechtigung WRO-2).
  - `is_member_fn`     — Callable `(user_id) -> bool` (WRO-2, EC-2).
  - `mini_app_url`     — Vollständige URL des Garderoben-Editors (WRO-5).
                         Leer → Fehler-Text ohne Button (WRO-6).

**Ausgang:** Form-(b)-Dict `{text, presentation}`:
  - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
  - Ohne Button (Konfig-Fehler): `presentation: {}`.

Wirft `BerechtigungError` bei WRO-2-Verletzung.

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische liegt im Adapter (_task.py).
"""

import logging

from skills._errors import BerechtigungError

logger = logging.getLogger(__name__)

# WRO-4: Nachrichtentext (kompakt, ohne Lese-Vorschau — E-WRO-3).
_WRO_TEXT = "👕 Garderoben-Regeln — Wetter-Kleidung festlegen"

# WRO-4: Button-Label.
_WRO_BUTTON_LABEL = "👕 Garderobe öffnen"


def wetter_regeln_oeffnen(chat_id, from_user_id, is_member_fn, mini_app_url):
    """Wetter-Regeln öffnen — aufrufbare Funktion (WRO-1, E-WRO-1).

    Baut Übersichts-Text + Präsentations-Hinweis (WRO-4/WRO-5,
    TASK-10c Form (b)). Kein Lese-Call (E-WRO-3 — reiner Türöffner).

    Returnt ein Form-(b)-Dict `{text, presentation}`:
      - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
      - Ohne Button (Konfig-Fehler): `presentation: {}`.

    Wirft `BerechtigungError` bei WRO-2-Verletzung.
    """
    # WRO-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "wetter_regeln_oeffnen: User %s nicht berechtigt (WRO-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    # WRO-6: Mini-App-URL fehlt → Fehler-Text, kein Button
    if not mini_app_url:
        logger.warning(
            "wetter_regeln_oeffnen: mini_app_url fehlt in Konfig (WRO-6)")
        return {
            "text": (
                "Die Wetter-Mini-App-URL fehlt in meiner Konfig — frag Nic."
            ),
            "presentation": {},
        }

    # TASK-10c Form (b): presentation mit inline_button-Schlüssel.
    presentation = {
        "inline_button": {
            "label": _WRO_BUTTON_LABEL,
            "web_app_url": mini_app_url,
        }
    }

    logger.info(
        "wetter_regeln_oeffnen: Garderoben-Editor-Button für Chat %s gebaut",
        chat_id,
    )
    return {"text": _WRO_TEXT, "presentation": presentation}
