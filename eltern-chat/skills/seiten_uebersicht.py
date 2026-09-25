"""Seiten-Übersicht — specs/platform/seiten-registry.md (SREG-5/SREG-5b)
und SREG-12 (die eine Übersicht, #1946).

**SREG-5 Pivot (2026-06-15):** Dieser Skill ist ein Klasse-B
web_app-Launcher (analog routine_anpassen_oeffnen / hoerspiel_oeffnen).
Er öffnet die Übersicht per Inline-Button statt einen Text-Link zu liefern.
Seit #1946 (Nic 2026-09-25) ist das dieselbe Übersicht wie im Browser; die
eigene Mini-App-Übersicht (MAU) ist entfallen.

**SREG-5b deprecated:** Der zweistufige KI-Matching-Pfad
(aktion="inventar" / aktion="match") ist inaktiv — er ist durch die
Volltextsuche auf der Übersicht abgelöst.

TASK-10c Form (b): der Skill returnt `{text, presentation}` — der Task
reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
übersetzt `presentation` in eine Telegram-Nachricht. Der Skill sendet
NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

Schwester-Skill von routine_anpassen_oeffnen (RAO) und hoerspiel_oeffnen
(HOE) — identischer Mini-App-Türöffner-Pattern (Klasse-B-Bauplan,
eltern-chat-skills.md).

**Eingang:**
  - `chat_id`         — Telegram-Chat (nur für Logging).
  - `from_user_id`    — Telegram-User-ID des Aufrufers (Berechtigung SREG-6).
  - `is_member_fn`    — Callable `(user_id) -> bool` (SREG-6, EC-2).
  - `mini_app_url`    — volle URL der Übersicht. Leer → Fehler-Text (kein Button).

**Ausgang:** Form-(b)-Dict `{text, presentation}`:
  - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
  - Ohne Button (Konfig-Fehler): `presentation: {}`.

Wirft `BerechtigungError` bei SREG-6-Verletzung.

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische liegt im Adapter (_task.py).
"""

import logging

from skills._errors import BerechtigungError

logger = logging.getLogger(__name__)

# #1946: Pfad der einen Übersicht (SREG-12, URL-4-Konsistenz).
_UEBERSICHT_PATH = "/api/v1/seiten/uebersicht"

# Button-Label (kurz, ein-Wort-Phrase per Leitplanken).
_BUTTON_LABEL = "🏠 xbuddy öffnen"

# Intro-Text für die Übersichts-Ankündigung.
_INTRO_TEXT = "Hier siehst du alle Mini Apps und Seiten:"


def seiten_uebersicht(chat_id, from_user_id, is_member_fn, mini_app_url):
    """Seiten-Übersicht — aufrufbare Funktion (SREG-5 Pivot, #1946, EC-29).

    Baut einen Inline-Button auf die Übersicht (SREG-12). Keine
    Backend-Abfrage — die Übersicht liefert das Inventar selbst
    (Volltextsuche, SREG-5b abgelöst).

    Returnt ein Form-(b)-Dict `{text, presentation}` (TASK-10c):
      - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
      - Ohne Button (mini_app_url leer): `presentation: {}` + Fehler-Text.

    Wirft `BerechtigungError` bei SREG-6-Verletzung.
    """
    # SREG-6: Berechtigung — EC-2-Mitgliedschaft.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "seiten_uebersicht: User %s nicht berechtigt (SREG-6)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    # Konfig-Fehler: mini_app_url fehlt → Fehler-Text, kein Button.
    if not mini_app_url:
        logger.warning(
            "seiten_uebersicht: mini_app_url fehlt in Konfig (SREG-5)")
        return {
            "text": "⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic.",
            "presentation": {},
        }

    # mini_app_url ist bereits die volle URL inkl. /api/v1/seiten/uebersicht
    # (Task-Konstruktor hängt _UEBERSICHT_PATH an — analog RAO). Nicht nochmal anhängen.
    presentation = {
        "inline_button": {
            "label": _BUTTON_LABEL,
            "web_app_url": mini_app_url,
        }
    }

    button_count = 1
    logger.info(
        "seiten_uebersicht: Übersichts-Button für Chat %s, Buttons=%d",
        chat_id, button_count,
    )
    return {"text": _INTRO_TEXT, "presentation": presentation}
