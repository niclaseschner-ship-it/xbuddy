"""Hörspiel öffnen — specs/platform/hoerspiel-oeffnen.md (HOE-1 … HOE-7).

Aufrufbare, trigger-agnostische Funktion (HOE-1, E-HOE-1 analog E-RAO-1):
liest die Hörspiel-Konfig (Settings-Variante: GET /api/v1/hoerspiel/config)
oder die Album-Liste (Folgen-Variante: GET /api/v1/hoerspiel/alben), baut
eine kompakte Übersichts-Nachricht + Inline-Button auf die Hörspiel-Eltern-
Mini-App (HOE-4/HOE-5) und gibt ein Form-(b)-Dict zurück (TASK-10c).

TASK-10c Form (b): der Skill returnt `{text, presentation}` — der Task
reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
übersetzt `presentation` in eine Telegram-Nachricht. Der Skill sendet
NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

Schwester-Skill von routine_anpassen_oeffnen (RAO) — identischer
Mini-App-Türöffner-Pattern, andere Buddy-Naht plus Tab-Hint-Parameter
(HOE-1, E-HOE-2).

**Wesentlicher Unterschied zu RAO:** Tab-Hint-Parameter `tab_hint`
bestimmt, welcher Lese-Pfad gewählt wird und welches URL-Hash-Fragment
der Button trägt. Default bei fehlendem/unbekanntem Tab-Hint: `"einstellungen"`
(konsistent zu HSP-33-Default, HOE-1).

**Eingang:**
  - `chat_id`           — Telegram-Chat (HOE-1).
  - `from_user_id`      — Telegram-User-ID des Aufrufers (Berechtigung HOE-2).
  - `tab_hint`          — `"einstellungen"` | `"folgen"` (HOE-1/HOE-3).
  - `hoerspiel_client`  — HoerspielClient-Instanz (HOE-1, CLIENT-1-Naht).
  - `is_member_fn`      — Callable `(user_id) -> bool` (HOE-2, EC-2).
  - `mini_app_url`      — Basis-URL der Hörspiel-Eltern-Mini-App (HOE-5).
                          Leer → Fehler-Text (HOE-7).

**Ausgang:** Form-(b)-Dict `{text, presentation}`:
  - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
  - Ohne Button (Konfig-/Netz-Fehler): `presentation: {}`.
  E-HOE-3: Bei leerem Album-Bestand (Folgen-Variante) wird trotzdem ein
  Button zurückgegeben (analog E-RAO-3 — Anfangszustand, kein Endzustand).

Wirft `BerechtigungError` bei HOE-2-Verletzung.

RAT-16: Adapter-Disziplin — diese Datei enthält kein Telegram-Vokabular.
Alles Telegram-Spezifische liegt im Adapter (_task.py).
"""

import logging

from skills._errors import BerechtigungError
from skills.hoerspiel_client import HoerspielClientError

logger = logging.getLogger(__name__)

# HOE-1: Default-Tab bei fehlendem/unbekanntem Tab-Hint (HSP-33-Default).
_DEFAULT_TAB = "einstellungen"

# HOE-4: Labels pro Tab-Variante.
_LABEL_EINSTELLUNGEN = "⚙️ Einstellungen öffnen"
_LABEL_FOLGEN = "🎧 Folgen anhören"
_LABEL_FOLGEN_LEER = "🎧 Folgen-Tab öffnen"


def _baue_einstellungen_text(config_data):
    """HOE-4 Settings-Variante: kompakter Text aus GET /config.

    Erwartet Dict mit `default_voice`, `llm_provider`, `llm_model`.
    Fehlende Felder fallen auf Platzhalter zurück.
    """
    voice = config_data.get("default_voice") or "?"
    provider = config_data.get("llm_provider") or "?"
    model = config_data.get("llm_model") or "?"
    return (
        "🎧 Hörspiel-Einstellungen — Voice: %s, Anbieter: %s/%s"
        % (voice, provider, model)
    )


def _baue_folgen_text(alben_liste):
    """HOE-4 Folgen-Variante: kompakter Text aus GET /alben.

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


def _baue_uebersicht(tab_hint, hoerspiel_client, mini_app_url):
    """HOE-4/HOE-5: baut Text + presentation für die Übersichts-Nachricht.

    Führt den Lese-Pfad passend zum Tab-Hint aus.
    Liefert ein Form-(b)-Dict `{text, presentation}` (TASK-10c):
      - Standardfall: Text mit Übersicht + inline_button mit Hash-Fragment.
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

    # HOE-1: Default bei fehlendem/unbekanntem Tab-Hint
    effective_tab = tab_hint if tab_hint in ("einstellungen", "folgen") \
        else _DEFAULT_TAB

    # HOE-5: URL-Hash-Fragment an Mini-App-URL anhängen
    web_app_url = mini_app_url.rstrip("/") + "#" + effective_tab

    # HOE-4: Lese-Pfad + Button-Label abhängig vom Tab
    if effective_tab == "folgen":
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
    else:
        # Settings-Variante (einstellungen)
        try:
            config_data = hoerspiel_client.config_lesen()
        except HoerspielClientError as e:
            logger.warning(
                "hoerspiel_oeffnen: Hörspiel-Buddy (config) nicht erreichbar — %s", e)
            return {
                "text": (
                    "Der Hörspiel-Buddy ist gerade nicht erreichbar — "
                    "versuch's gleich nochmal."
                ),
                "presentation": {},
            }
        text = _baue_einstellungen_text(config_data)
        label = _LABEL_EINSTELLUNGEN

    presentation = {
        "inline_button": {
            "label": label,
            "web_app_url": web_app_url,
        }
    }
    return {"text": text, "presentation": presentation}


def hoerspiel_oeffnen(chat_id, from_user_id, tab_hint,
                      hoerspiel_client, is_member_fn, mini_app_url):
    """Hörspiel öffnen — aufrufbare Funktion (HOE-1, E-HOE-1).

    Liest Hörspiel-Konfig oder Album-Liste (abhängig von `tab_hint`),
    baut Übersichts-Text + Präsentations-Hinweis (HOE-4/HOE-5,
    TASK-10c Form (b)).

    Returnt ein Form-(b)-Dict `{text, presentation}`:
      - Mit Button: `presentation: {inline_button: {label, web_app_url}}`.
      - Ohne Button (Konfig-/Netz-Fehler): `presentation: {}`.
      E-HOE-3: Bei leerem Album-Bestand (Folgen-Variante) trotzdem Button.

    Wirft `BerechtigungError` bei HOE-2-Verletzung.
    """
    # HOE-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "hoerspiel_oeffnen: User %s nicht berechtigt (HOE-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    result = _baue_uebersicht(tab_hint, hoerspiel_client, mini_app_url)
    presentation = result.get("presentation") or {}
    button_count = 1 if "inline_button" in presentation else 0
    logger.info(
        "hoerspiel_oeffnen: tab=%s für Chat %s, Buttons=%d",
        tab_hint, chat_id, button_count,
    )
    return result
