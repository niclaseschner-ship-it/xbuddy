"""Einkauf zeigen — specs/platform/einkauf-zeigen.md (EZG-1 … EZG-8).

Aufrufbare, trigger-agnostische Funktion (EZG-1, E-EZG-1-Muster): liest
die Einkaufsliste des Essens-Buddys (ESSEN-15, GET mit abgehakt=false),
baut eine kompakte Übersichts-Nachricht + Inline-Button auf die Mini App
(EZG-5/EZG-6) und gibt ein Form-(b)-Dict zurück (TASK-10c).

TASK-10c Form (b): der Skill returnt `{text, presentation}` — der Task
reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
übersetzt `presentation` in eine Telegram-Nachricht. Der Skill sendet
NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

**Eingang:**
  - `chat_id`        — Telegram-Chat, in dem die Antwort landen wird (EZG-5).
  - `from_user_id`   — Telegram-User-ID des Aufrufers (Berechtigung EZG-2).
  - `essen_client`   — EssenClient-Instanz (EZG-4, CLIENT-1-Naht).
  - `is_member_fn`   — Callable `(user_id) -> bool` (EZG-2, EC-2).
  - `mini_app_url`   — URL der Einkauf-Mini-App (EZG-6). Leer → kein Button.

**Ausgang:** Form-(b)-Dict `{text, presentation}`:
  - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
  - Ohne Button (Leer- oder Fehlerfall): `presentation: {}`.

Wirft `BerechtigungError` bei EZG-2-Verletzung.

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische (Tap-Handler, Button-Strukturen) liegt im
Adapter (_task.py).
"""

import logging

from skills._errors import BerechtigungError
from skills.essen_client import EssenClientError

logger = logging.getLogger(__name__)

# EZG-4: Labels auf 24 Zeichen kürzen.
_MAX_LABEL_LEN = 24


def _kuerze_label(label):
    """EZG-4: Label auf max. 24 Zeichen kürzen."""
    if len(label) > _MAX_LABEL_LEN:
        return label[:_MAX_LABEL_LEN - 1] + "…"
    return label


def _baue_uebersicht(items, mini_app_url):
    """EZG-5/EZG-6: baut Text + presentation für die Übersichts-Nachricht.

    `items` — Liste aller offenen Wunsch/Einkauf-Einträge (EZG-4).
    `mini_app_url` — URL der Einkauf-Mini-App (EZG-6).

    Liefert ein Form-(b)-Dict `{text, presentation}` (TASK-10c):
      - Standardfall: presentation mit inline_button (web_app_url).
      - Leer-Fall oder fehlende URL: presentation leer (nur Text).
    """
    wunsch_n = sum(1 for i in items if i.get("klasse") == "wunsch")
    einkauf_n = sum(1 for i in items if i.get("klasse") == "einkauf")
    gesamt_n = wunsch_n + einkauf_n

    # EZG-5: Leer-Sonderfall
    if gesamt_n == 0:
        text = ("📋 Die Einkaufsliste ist leer — nichts zu holen heute. 🎉\n"
                "Schick mir Items zum Hinzufügen, z. B. `Brot, Milch`.")
        return {"text": text, "presentation": {}}

    # EZG-4: drei zuletzt erstellte Items (erstellt_am absteigend).
    try:
        zuletzt = sorted(
            items,
            key=lambda i: i.get("erstellt_am") or "",
            reverse=True,
        )[:3]
    except Exception:
        zuletzt = items[:3]

    zuletzt_labels = [_kuerze_label(i.get("label") or "?") for i in zuletzt]
    zuletzt_str = ", ".join(zuletzt_labels)

    # EZG-5: Übersichts-Zeile
    text = (
        "📋 Einkaufsliste — %d offen (🧒 %d · 🛒 %d)\n"
        "Zuletzt dazugekommen: %s"
    ) % (gesamt_n, wunsch_n, einkauf_n, zuletzt_str)

    # EZG-6: Mini-App-Button — fehlt die URL, nur Text (kein Button-Aufsatz).
    if not mini_app_url:
        logger.warning("einkauf_zeigen: mini_app_url fehlt in Konfig (EZG-7)")
        text = (
            text
            + "\n\n⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic."
        )
        return {"text": text, "presentation": {}}

    # TASK-10c Form (b): presentation mit inline_button-Schlüssel.
    return {
        "text": text,
        "presentation": {
            "inline_button": {
                "label": "🛒 Liste öffnen",
                "web_app_url": mini_app_url,
            }
        },
    }


def einkauf_zeigen(chat_id, from_user_id, essen_client, is_member_fn,
                   mini_app_url):
    """Einkauf zeigen — aufrufbare Funktion (EZG-1, E-EZG-1).

    Liest die offene Einkaufsliste (EZG-4), baut Übersichts-Text + Präsentations-
    Hinweis (EZG-5/EZG-6, TASK-10c Form (b)).

    Returnt ein Form-(b)-Dict `{text, presentation}`:
      - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
      - Ohne Button (Leer- oder Fehlerfall): `presentation: {}`.

    Wirft `BerechtigungError` bei EZG-2-Verletzung.
    """
    # EZG-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("einkauf_zeigen: User %s nicht berechtigt (EZG-2)",
                    from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    # EZG-4: Lese-Pfad — nur offene Items beider Klassen
    try:
        items = essen_client.lese_wuensche(abgehakt=False)
    except EssenClientError as e:
        # EZG-7: Nicht-erreichbar → Klartext, kein Button
        logger.warning("einkauf_zeigen: Essens-Buddy nicht erreichbar — %s", e)
        return {
            "text": (
                "Die Liste ist gerade nicht erreichbar — "
                "versuch's gleich nochmal."
            ),
            "presentation": {},
        }

    result = _baue_uebersicht(items, mini_app_url)
    presentation = result.get("presentation") or {}
    button_count = 1 if "inline_button" in presentation else 0
    logger.info("einkauf_zeigen: %d Items für Chat %s, Buttons=%d",
                len(items), chat_id, button_count)
    return result
