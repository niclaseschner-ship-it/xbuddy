"""Seiten-Übersicht — specs/platform/seiten-registry.md (SREG-5/SREG-5b)
und SREG-12 (die eine Übersicht, #1946).

**SREG-5 Pivot (2026-06-15):** Dieser Skill ist ein Klasse-B
web_app-Launcher (analog app_oeffnen, EC-46).
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

Schwester-Skill von app_oeffnen (EC-46) — identischer Mini-App-Türöffner-
Pattern (Klasse-B-Bauplan, eltern-chat-skills.md), dieselbe Knopfreihe aus
skills/app_knoepfe.py.

**Eingang:**
  - `chat_id`         — Telegram-Chat (nur für Logging).
  - `from_user_id`    — Telegram-User-ID des Aufrufers (Berechtigung SREG-6).
  - `is_member_fn`    — Callable `(user_id) -> bool` (SREG-6, EC-2).
  - `mini_app_url`    — volle URL der Übersicht. Leer → Fehler-Text (kein Button).

**Ausgang:** Form-(b)-Dict `{text, presentation}`:
  - Mit Knöpfen: `presentation: {inline_buttons: [{label, web_app_url},
    {label, url}]}` — Mini-App-Knopf + Browser-Knopf (#1953).
  - Ohne Button (Konfig-Fehler): `presentation: {}`.

Wirft `BerechtigungError` bei SREG-6-Verletzung.

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische liegt im Adapter (_task.py).
"""

import logging

from skills._errors import BerechtigungError
from skills.app_knoepfe import app_knoepfe

logger = logging.getLogger(__name__)

# #1946: Pfad der einen Übersicht (SREG-12, URL-4-Konsistenz).
_UEBERSICHT_PATH = "/api/v1/seiten/uebersicht"

# Button-Label (kurz, ein-Wort-Phrase per Leitplanken).
_BUTTON_LABEL = "🏠 xbuddy öffnen"

# Intro-Text für die Übersichts-Ankündigung. #1953: im Browser lässt sich die
# Übersicht als App installieren — das sagt jetzt der Satz, der Browser-Knopf
# trägt das einheitliche Label aus dem App-Knopf-Baustein (EC-46, #1964).
_INTRO_TEXT = ("Hier siehst du alle Mini Apps und Seiten — im Browser lässt "
               "sich die Übersicht als App installieren.")


def seiten_uebersicht(chat_id, from_user_id, is_member_fn, mini_app_url):
    """Seiten-Übersicht — aufrufbare Funktion (SREG-5 Pivot, #1946, EC-29).

    Baut einen Inline-Button auf die Übersicht (SREG-12). Keine
    Backend-Abfrage — die Übersicht liefert das Inventar selbst
    (Volltextsuche, SREG-5b abgelöst).

    Returnt ein Form-(b)-Dict `{text, presentation}` (TASK-10c):
      - Mit Knöpfen: `presentation: {inline_buttons: [web_app-Knopf,
        url-Knopf „Im Browser öffnen"]}` (#1953).
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
    # #1953 (Nic 2026-09-25): im Telegram-WebView lässt sich die Übersicht
    # nicht installieren, und eine Adresse sieht man dort nicht. Darum ein
    # zweiter, normaler URL-Knopf — Telegram öffnet url-Knöpfe im externen
    # Browser, wo die Übersicht als App installierbar ist. Dieselbe Adresse,
    # kein Credential im Link (Anmeldung im Browser: Pairing-Link, AUTH-2.a).
    # EC-46 (#1964): Knopfreihe aus dem EINEN App-Knopf-Baustein. Die
    # Übersicht ist in views.json keine `typ: pwa` — ihr Install-Hinweis
    # erscheint im Browser immer (data-immer, #1955), darum kein dritter Knopf.
    presentation = {"inline_buttons": app_knoepfe(mini_app_url, _BUTTON_LABEL)}

    button_count = len(presentation["inline_buttons"])
    logger.info(
        "seiten_uebersicht: Übersichts-Button für Chat %s, Buttons=%d",
        chat_id, button_count,
    )
    return {"text": _INTRO_TEXT, "presentation": presentation}
