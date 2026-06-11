"""Einkauf zeigen — specs/platform/einkauf-zeigen.md (EZG-1 … EZG-8).

Aufrufbare, trigger-agnostische Funktion (EZG-1, E-EZG-1-Muster): liest
die Einkaufsliste des Essens-Buddys (ESSEN-15, GET mit abgehakt=false),
baut eine kompakte Übersichts-Nachricht + Inline-Button auf die Mini App
(EZG-5/EZG-6) und gibt Text + Button-Daten zurück.

Im Unterschied zu wuensche_zeigen (WZE) sendet dieser Skill SELBST die
Nachricht über den Telegram-Client — der Inline-Button erfordert
`send_inline_keyboard`, nicht `send_message`. Das LLM bekommt eine kurze
Quittung zurück (EC-29-Geist: send-only im Task-Adapter, kein Senden im Skill
selbst — der Skill returnt Text + Button-Daten, der Task sendet).

**Eingang:**
  - `chat_id`        — Telegram-Chat, in dem die Antwort landen wird (EZG-5).
  - `from_user_id`   — Telegram-User-ID des Aufrufers (Berechtigung EZG-2).
  - `essen_client`   — EssenClient-Instanz (EZG-4, CLIENT-1-Naht).
  - `is_member_fn`   — Callable `(user_id) -> bool` (EZG-2, EC-2).
  - `mini_app_url`   — URL der Einkauf-Mini-App (EZG-6). Leer → Fehler-Text.

**Ausgang:** `(text, buttons)` — Text-String + Liste von Button-Dicts für
`send_inline_keyboard`, oder `(text, [])` im Leer- und Fehlerfall.

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
    """EZG-5/EZG-6: baut Text + Button-Liste für die Übersichts-Nachricht.

    `items` — Liste aller offenen Wunsch/Einkauf-Einträge (EZG-4).
    `mini_app_url` — URL der Einkauf-Mini-App (EZG-6).

    Liefert (text, buttons):
      - Standardfall: Text mit Counter + Zuletzt-Zeile + web_app-Button.
      - Leer-Fall: Klartext ohne Button.
    """
    wunsch_n = sum(1 for i in items if i.get("klasse") == "wunsch")
    einkauf_n = sum(1 for i in items if i.get("klasse") == "einkauf")
    gesamt_n = wunsch_n + einkauf_n

    # EZG-5: Leer-Sonderfall
    if gesamt_n == 0:
        text = ("📋 Die Einkaufsliste ist leer — nichts zu holen heute. 🎉\n"
                "Schick mir Items zum Hinzufügen, z. B. `Brot, Milch`.")
        return text, []

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

    # EZG-6: Mini-App-Button
    if not mini_app_url:
        logger.warning("einkauf_zeigen: mini_app_url fehlt in Konfig (EZG-7)")
        text = (
            text
            + "\n\n⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic."
        )
        return text, []

    buttons = [{"label": "🛒 Liste öffnen", "web_app_url": mini_app_url}]
    return text, buttons


def einkauf_zeigen(chat_id, from_user_id, essen_client, is_member_fn,
                   mini_app_url):
    """Einkauf zeigen — aufrufbare Funktion (EZG-1, E-EZG-1).

    Liest die offene Einkaufsliste (EZG-4), baut Übersichts-Text + Button
    (EZG-5/EZG-6).

    Returnt `(text, buttons)`:
      - `text`    — User-tauglicher Antwort-Text.
      - `buttons` — Liste von Button-Dicts für send_inline_keyboard, oder []
                    im Leer-/Fehlerfall.

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
        return (
            "Die Liste ist gerade nicht erreichbar — "
            "versuch's gleich nochmal.",
            [],
        )

    text, buttons = _baue_uebersicht(items, mini_app_url)
    logger.info("einkauf_zeigen: %d Items für Chat %s, Buttons=%d",
                len(items), chat_id, len(buttons))
    return text, buttons
