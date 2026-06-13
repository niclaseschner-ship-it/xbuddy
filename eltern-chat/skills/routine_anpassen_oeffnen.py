"""Routine-Anpassen öffnen — specs/platform/routine-anpassen-oeffnen.md (RAO-1 … RAO-8).

Aufrufbare, trigger-agnostische Funktion (RAO-1, E-RAO-1-Muster): liest
die Routine-Items (ROUTINE-14, GET /api/v1/routine/items), baut eine
kompakte Übersichts-Nachricht + Inline-Button auf die Anpassen-Mini-App
(RAO-5/RAO-6) und gibt ein Form-(b)-Dict zurück (TASK-10c).

TASK-10c Form (b): der Skill returnt `{text, presentation}` — der Task
reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
übersetzt `presentation` in eine Telegram-Nachricht. Der Skill sendet
NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

Schwester-Skill von einkauf_zeigen (EZG) — Stil-Anker gespiegelt
(eltern-chat-skills.md Klasse-B-Bauplan).

**Wesentlicher Unterschied zu EZG (E-RAO-3):** Auch bei leerer Items-Liste
wird ein Inline-Button zurückgegeben — eine leere Routine ist Anfangszustand,
nicht Endzustand wie eine leere Einkaufsliste.

**Eingang:**
  - `chat_id`          — Telegram-Chat, in dem die Antwort landen wird (RAO-1).
  - `from_user_id`     — Telegram-User-ID des Aufrufers (Berechtigung RAO-2).
  - `routine_client`   — RoutineClient-Instanz (RAO-4, CLIENT-1-Naht).
  - `is_member_fn`     — Callable `(user_id) -> bool` (RAO-2, EC-2).
  - `mini_app_url`     — URL der Routine-Anpassen-Mini-App (RAO-6). Leer → Fehler-Text.

**Ausgang:** Form-(b)-Dict `{text, presentation}`:
  - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
  - Ohne Button (Konfig-/Netz-Fehler): `presentation: {}`.
  E-RAO-3: Bei leerer Routine wird trotzdem ein Button zurückgegeben.

Wirft `BerechtigungError` bei RAO-2-Verletzung.

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische liegt im Adapter (_task.py).
"""

import logging

from skills._errors import BerechtigungError
from skills.routine_client import RoutineClientError

logger = logging.getLogger(__name__)

# RAO-4: Labels auf 24 Zeichen kürzen (analog EZG-4).
_MAX_LABEL_LEN = 24


def _kuerze_label(label):
    """RAO-4: Label auf max. 24 Zeichen kürzen."""
    if len(label) > _MAX_LABEL_LEN:
        return label[:_MAX_LABEL_LEN - 1] + "…"
    return label


def _baue_uebersicht(items_data, mini_app_url):
    """RAO-5/RAO-6: baut Text + presentation für die Übersichts-Nachricht.

    `items_data` — Dict {"default": [...], "einmalig_heute": [...]} (RAO-4).
    `mini_app_url` — URL der Routine-Anpassen-Mini-App (RAO-6).

    Liefert ein Form-(b)-Dict `{text, presentation}` (TASK-10c):
      - Standardfall: Text mit Counter + Zuletzt-Zeile + inline_button.
      - Leer-Fall (E-RAO-3): Klartext + inline_button (anders als EZG-5!).
      - Fehlerfall mini_app_url leer: Fehler-Text, presentation leer (RAO-7).
    """
    default_items = items_data.get("default") or []
    einmalig_items = items_data.get("einmalig_heute") or []

    default_n = len(default_items)
    einmalig_n = len(einmalig_items)

    # RAO-7: Mini-App-URL fehlt → Fehler-Text, kein Button
    if not mini_app_url:
        logger.warning(
            "routine_anpassen_oeffnen: mini_app_url fehlt in Konfig (RAO-7)")
        text = "⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic."
        return {"text": text, "presentation": {}}

    # TASK-10c Form (b): presentation mit inline_button-Schlüssel.
    presentation = {
        "inline_button": {
            "label": "🛠️ Routine öffnen",
            "web_app_url": mini_app_url,
        }
    }

    # RAO-5 / T728: Klartext-Hinweis auf RZS-Direktsatz (Zeiten-Schnellsatz).
    # RZS kann nur Zeiten (abfahrtszeit, aufstehzeit, anzieh_vorlauf_min) —
    # der Hinweis nennt nur Zeiten, NICHT Punkte (wäre falsch versprechen).
    _RZS_HINWEIS = (
        "Einzelne Zeiten (z. B. „Abfahrtszeit auf 7:50“ oder "
        "„Aufstehzeit auf 6:30“) kannst du mir auch direkt hier sagen."
    )

    # E-RAO-3: Leere Routine → Klartext + Button (Anfangszustand, nicht Endzustand)
    if default_n == 0 and einmalig_n == 0:
        text = (
            "🛠️ Die Morgenroutine ist leer — leg den ersten Punkt an.\n"
            + _RZS_HINWEIS
        )
        return {"text": text, "presentation": presentation}

    # RAO-5: Übersichts-Zeile mit Counter
    einmalig_klammer = ""
    if einmalig_n > 0:
        einmalig_klammer = "  (+%d nur heute)" % einmalig_n

    text_lines = [
        "🛠️ Morgenroutine — %d Schritte%s" % (default_n, einmalig_klammer),
    ]

    # RAO-4: Letzter Eintrag der default-Liste
    zuletzt_labels = []
    if default_items:
        letzter = default_items[-1]
        zuletzt_labels.append(_kuerze_label(letzter.get("label") or "?"))
    for item in einmalig_items[:2]:
        zuletzt_labels.append(_kuerze_label(item.get("label") or "?"))

    if zuletzt_labels:
        text_lines.append("Zuletzt drauf: %s" % ", ".join(zuletzt_labels))

    # T728: Hinweis auf RZS-Direktsatz in jedem Aufschlag (ein Schritt weniger).
    text_lines.append(_RZS_HINWEIS)

    text = "\n".join(text_lines)
    return {"text": text, "presentation": presentation}


def routine_anpassen_oeffnen(chat_id, from_user_id, routine_client,
                              is_member_fn, mini_app_url):
    """Routine-Anpassen öffnen — aufrufbare Funktion (RAO-1, E-RAO-1).

    Liest die Routine-Items (RAO-4), baut Übersichts-Text + Präsentations-
    Hinweis (RAO-5/RAO-6, TASK-10c Form (b)).

    Returnt ein Form-(b)-Dict `{text, presentation}`:
      - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
      - Ohne Button (Konfig-/Netz-Fehler): `presentation: {}`.
      E-RAO-3: Bei leerer Routine wird trotzdem ein Button zurückgegeben.

    Wirft `BerechtigungError` bei RAO-2-Verletzung.
    """
    # RAO-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "routine_anpassen_oeffnen: User %s nicht berechtigt (RAO-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    # RAO-4: Lese-Pfad — GET /api/v1/routine/items
    try:
        items_data = routine_client.get_items()
    except RoutineClientError as e:
        # RAO-7: Nicht-erreichbar → Klartext, kein Button
        logger.warning(
            "routine_anpassen_oeffnen: Routine-Buddy nicht erreichbar — %s",
            e)
        return {
            "text": (
                "Die Routine ist gerade nicht erreichbar — "
                "versuch's gleich nochmal."
            ),
            "presentation": {},
        }

    result = _baue_uebersicht(items_data, mini_app_url)
    presentation = result.get("presentation") or {}
    button_count = 1 if "inline_button" in presentation else 0
    logger.info(
        "routine_anpassen_oeffnen: default=%d, einmalig=%d für Chat %s, "
        "Buttons=%d",
        len((items_data or {}).get("default") or []),
        len((items_data or {}).get("einmalig_heute") or []),
        chat_id,
        button_count,
    )
    return result
