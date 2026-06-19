"""Hörspiel öffnen — specs/platform/hoerspiel-oeffnen.md (HOE-1 … HOE-7).

Aufrufbare, trigger-agnostische Funktion (HOE-1, E-HOE-1 analog E-RAO-1):
liest die Album-Liste (GET /api/v1/hoerspiel/paula/alben) als festen
Launcher (HSP-35 aggregiert clientseitig), baut eine kompakte Folgen-
Übersichts-Nachricht + Inline-Button auf den Folgen-Tab der Hörspiel-
Eltern-Mini-App (HOE-4/HOE-5) und gibt ein Form-(b)-Dict zurück (TASK-10c).

TASK-10c Form (b): der Skill returnt `{text, presentation}` — der Task
reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
übersetzt `presentation` in eine Telegram-Nachricht. Der Skill sendet
NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

Schwester-Skill von routine_anpassen_oeffnen (RAO) — identischer
Mini-App-Türöffner-Pattern, andere Buddy-Naht. Ein Tab, ein Pfad
(Folgen) — Anti-Redundanz-Setzung 2026-06-19 (E-HOE-2): Settings-Tab
wird über HOE NICHT bedient, weil die Mini-App das selbst kann.

**Eingang:**
  - `chat_id`           — Telegram-Chat (HOE-1).
  - `from_user_id`      — Telegram-User-ID des Aufrufers (Berechtigung HOE-2).
  - `hoerspiel_client`  — HoerspielClient-Instanz für paula (HOE-1, CLIENT-1-Naht).
  - `is_member_fn`      — Callable `(user_id) -> bool` (HOE-2, EC-2).
  - `mini_app_url`      — Basis-URL der Hörspiel-Eltern-Mini-App (HOE-5).
                          Leer → Fehler-Text (HOE-7).

**Ausgang:** Form-(b)-Dict `{text, presentation}`:
  - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
  - Ohne Button (Konfig-/Netz-Fehler): `presentation: {}`.
  E-HOE-3: Bei leerem Album-Bestand wird trotzdem ein Button zurückgegeben
  (analog E-RAO-3 — Anfangszustand, kein Endzustand).

Wirft `BerechtigungError` bei HOE-2-Verletzung.

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische liegt im Adapter (_task.py).
"""

import logging

from skills._errors import BerechtigungError
from skills.hoerspiel_client import HoerspielClientError

logger = logging.getLogger(__name__)

# HOE-4: Labels (Folgen-only nach Rückbau 2026-06-19, Refs #1028).
_LABEL_FOLGEN = "🎧 Folgen anhören"
_LABEL_FOLGEN_LEER = "🎧 Folgen-Tab öffnen"


def _baue_folgen_text(alben_liste):
    """HOE-4: kompakter Folgen-Text aus GET /alben.

    E-HOE-3: Leerer Album-Bestand → Sonderfall-Text (Button wird trotzdem gesetzt).
    """
    n = len(alben_liste)
    if n == 0:
        return (
            "🎧 Hörspiel — noch keine Folge vorhanden. "
            "Sag mir Bescheid, wenn ich eine schreiben soll."
        )
    # Höchste folgen_nr = zuletzt erzeugte Folge
    try:
        letztes = max(alben_liste, key=lambda a: a.get("folgen_nr") or 0)
    except (ValueError, TypeError):
        letztes = alben_liste[-1]
    nr = letztes.get("folgen_nr") or "?"
    titel = letztes.get("titel") or "?"
    return (
        '🎧 Hörspiel — %d %s (zuletzt: Folge %s „%s“)'
        % (n, "Folge" if n == 1 else "Folgen", nr, titel)
    )


def _baue_uebersicht(hoerspiel_client, mini_app_url):
    """HOE-4/HOE-5: baut Text + presentation für die Folgen-Übersichts-Nachricht.

    Liefert ein Form-(b)-Dict `{text, presentation}` (TASK-10c):
      - Standardfall: Text mit Folgen-Übersicht + inline_button mit #folgen-Hash.
      - HOE-7 mini_app_url leer: Fehler-Text, presentation leer.
      - HOE-7 Buddy nicht erreichbar: Fehler-Text, presentation leer.
    """
    # HOE-7: Mini-App-URL fehlt → Fehler-Text, kein Button
    if not mini_app_url:
        logger.warning(
            "hoerspiel_oeffnen: mini_app_url fehlt in Konfig (HOE-7)")
        return {
            "text": "⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic.",
            "presentation": {},
        }

    # HOE-5: fester #folgen-Hash an Mini-App-URL anhängen
    web_app_url = mini_app_url.rstrip("/") + "#folgen"

    # HOE-4: Lese-Pfad /alben + Button-Label
    try:
        alben_liste = hoerspiel_client.alben_lesen()
    except HoerspielClientError as e:
        logger.warning(
            "hoerspiel_oeffnen: Hörspiel-Buddy (alben) nicht erreichbar — %s", e)
        return {
            "text": (
                "Der Hörspiel-Buddy ist gerade nicht erreichbar — "
                "versuch's gleich nochmal."
            ),
            "presentation": {},
        }
    n = len(alben_liste)
    text = _baue_folgen_text(alben_liste)
    # E-HOE-3: Button auch bei leerem Album-Bestand
    label = _LABEL_FOLGEN_LEER if n == 0 else _LABEL_FOLGEN

    presentation = {
        "inline_button": {
            "label": label,
            "web_app_url": web_app_url,
        }
    }
    return {"text": text, "presentation": presentation}


def hoerspiel_oeffnen(chat_id, from_user_id,
                      hoerspiel_client, is_member_fn, mini_app_url):
    """Hörspiel öffnen — aufrufbare Funktion (HOE-1, E-HOE-1).

    Liest Album-Liste, baut Übersichts-Text + Präsentations-Hinweis
    (HOE-4/HOE-5, TASK-10c Form (b)).

    Returnt ein Form-(b)-Dict `{text, presentation}`:
      - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
      - Ohne Button (Konfig-/Netz-Fehler): `presentation: {}`.
      E-HOE-3: Bei leerem Album-Bestand trotzdem Button.

    Wirft `BerechtigungError` bei HOE-2-Verletzung.
    """
    # HOE-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "hoerspiel_oeffnen: User %s nicht berechtigt (HOE-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    result = _baue_uebersicht(hoerspiel_client, mini_app_url)
    presentation = result.get("presentation") or {}
    button_count = 1 if "inline_button" in presentation else 0
    logger.info(
        "hoerspiel_oeffnen: Folgen-Türöffner für Chat %s, Buttons=%d",
        chat_id, button_count,
    )
    return result
