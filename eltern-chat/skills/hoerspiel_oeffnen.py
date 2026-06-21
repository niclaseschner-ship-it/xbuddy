# Hoerspiel oeffnen -- specs/platform/hoerspiel-oeffnen.md (HOE-1 ... HOE-7).
#
# Aufrufbare, trigger-agnostische Funktion (HOE-1, E-HOE-1 analog E-RAO-1):
# liest die Album-Liste (GET /api/v1/hoerspiel/mia/alben) als festen
# Launcher (HSP-35 aggregiert clientseitig), baut eine kompakte Folgen-
# Uebersichts-Nachricht + Inline-Button auf die Hoerspiel-Eltern-Mini-App
# (HOE-4/HOE-5) und gibt ein Form-(b)-Dict zurueck (TASK-10c).
#
# TASK-10c Form (b): der Skill returnt {text, presentation} -- der Task
# reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
# uebersetzt presentation in eine Telegram-Nachricht. Der Skill sendet
# NICHTS selbst (EC-29 "Eine Stimme im Agent-Turn").
#
# Tab-Parameter (E-HOE-2 Schaerfung 2026-06-20, Refs #1048):
#   - Default tab='folgen' -> URL endet auf #folgen (HOE-5).
#   - tab='einstellungen' -> URL endet auf #einstellungen (E-HOE-2
#     Direkt-Trigger-Ausnahme): nur bei expliziter Direkt-Bitte
#     nach Settings-Link verwenden (z.B. "schick mir die Hoerbuch settings").
#     Settings-INHALTE werden NICHT ausgegeben -- nur der Tueroeffner-Link.
#     Beilaeufige Settings-Erwaehnung -> kein Tool-Call, sprachlicher Verweis.
#
# Eingang:
#   chat_id          -- Telegram-Chat (HOE-1).
#   from_user_id     -- Telegram-User-ID des Aufrufers (Berechtigung HOE-2).
#   hoerspiel_client -- HoerspielClient-Instanz fuer mia (HOE-1, CLIENT-1).
#   is_member_fn     -- Callable (user_id) -> bool (HOE-2, EC-2).
#   mini_app_url     -- Basis-URL der Hoerspiel-Eltern-Mini-App (HOE-5).
#                       Leer -> Fehler-Text (HOE-7).
#   tab              -- Ziel-Tab: 'folgen' (Default) oder 'einstellungen'
#                       (E-HOE-2 Direkt-Trigger-Ausnahme).
#
# Ausgang: Form-(b)-Dict {text, presentation}:
#   Mit Button: presentation: {inline_button: {label, web_app_url}}.
#   Ohne Button (Konfig-/Netz-Fehler): presentation: {}.
#   E-HOE-3: Bei leerem Album-Bestand wird trotzdem ein Button zurueckgegeben
#   (analog E-RAO-3 -- Anfangszustand, kein Endzustand).
#   Gilt nur fuer tab='folgen'; tab='einstellungen' macht keinen /alben-Call.
#
# Wirft BerechtigungError bei HOE-2-Verletzung.
#
# RAT-16: Adapter-Disziplin -- diese Datei enthaelt kein Telegram-Vokabular.
# Alles Telegram-Spezifische liegt im Adapter (_task.py).

import logging

from skills._errors import BerechtigungError
from skills.hoerspiel_client import HoerspielClientError

logger = logging.getLogger(__name__)

# HOE-4: Labels fuer Folgen-Tab (E-HOE-3: auch bei leerem Bestand).
_LABEL_FOLGEN = "\U0001f3a7 Folgen anhoeren"
_LABEL_FOLGEN_LEER = "\U0001f3a7 Folgen-Tab oeffnen"

# E-HOE-2 Schaerfung: Label fuer Einstellungen-Direkt-Trigger.
_LABEL_EINSTELLUNGEN = "⚙️ Hoerspiel-Einstellungen oeffnen"

# Gueltige Tab-Werte (E-HOE-4 Hash-Tab-Deeplink).
_TAB_FOLGEN = "folgen"
_TAB_EINSTELLUNGEN = "einstellungen"


def _baue_folgen_text(alben_liste):
    # HOE-4: kompakter Folgen-Text aus GET /alben.
    # E-HOE-3: Leerer Album-Bestand -> Sonderfall-Text (Button trotzdem gesetzt).
    n = len(alben_liste)
    if n == 0:
        return (
            "\U0001f3a7 Hoerspiel — noch keine Folge vorhanden. "
            "Sag mir Bescheid, wenn ich eine schreiben soll."
        )
    # Hoechste folgen_nr = zuletzt erzeugte Folge
    try:
        letztes = max(alben_liste, key=lambda a: a.get("folgen_nr") or 0)
    except (ValueError, TypeError):
        letztes = alben_liste[-1]
    nr = letztes.get("folgen_nr") or "?"
    titel = letztes.get("titel") or "?"
    return (
        "\U0001f3a7 Hoerspiel — %d %s (zuletzt: Folge %s „%s“)"
        % (n, "Folge" if n == 1 else "Folgen", nr, titel)
    )


def _baue_uebersicht(hoerspiel_client, mini_app_url, tab=_TAB_FOLGEN):
    # HOE-4/HOE-5: baut Text + presentation fuer die Hoerspiel-Uebersichts-Nachricht.
    #
    # Liefert ein Form-(b)-Dict {text, presentation} (TASK-10c):
    #   tab='folgen' (Default): Text mit Folgen-Uebersicht + inline_button mit #folgen-Hash.
    #   tab='einstellungen' (E-HOE-2 Direkt-Trigger): Button mit #einstellungen-Hash,
    #     kein /alben-Lese-Call, kein Settings-Inhalt im Text.
    #   HOE-7 mini_app_url leer: Fehler-Text, presentation leer.
    #   HOE-7 Buddy nicht erreichbar (nur tab='folgen'): Fehler-Text, presentation leer.

    # HOE-7: Mini-App-URL fehlt -> Fehler-Text, kein Button
    if not mini_app_url:
        logger.warning("hoerspiel_oeffnen: mini_app_url fehlt in Konfig (HOE-7)")
        return {
            "text": "⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic.",
            "presentation": {},
        }

    # E-HOE-2 Direkt-Trigger-Ausnahme: Einstellungen-Tab -- kein /alben-Aufruf
    if tab == _TAB_EINSTELLUNGEN:
        web_app_url = mini_app_url.rstrip("/") + "#einstellungen"
        return {
            "text": "Hier sind die Hoerspiel-Einstellungen:",
            "presentation": {
                "inline_button": {
                    "label": _LABEL_EINSTELLUNGEN,
                    "web_app_url": web_app_url,
                }
            },
        }

    # HOE-5: fester #folgen-Hash an Mini-App-URL anhaengen (Default-Pfad)
    web_app_url = mini_app_url.rstrip("/") + "#folgen"

    # HOE-4: Lese-Pfad /alben + Button-Label
    try:
        alben_liste = hoerspiel_client.alben_lesen()
    except HoerspielClientError as e:
        logger.warning(
            "hoerspiel_oeffnen: Hoerspiel-Buddy (alben) nicht erreichbar — %s", e)
        return {
            "text": (
                "Der Hoerspiel-Buddy ist gerade nicht erreichbar — "
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
                      hoerspiel_client, is_member_fn, mini_app_url,
                      tab=_TAB_FOLGEN):
    # Hoerspiel oeffnen -- aufrufbare Funktion (HOE-1, E-HOE-1).
    #
    # Liest Album-Liste (bei tab='folgen'), baut Uebersichts-Text +
    # Praesentations-Hinweis (HOE-4/HOE-5, TASK-10c Form (b)).
    #
    # tab-Parameter (E-HOE-2 Schaerfung 2026-06-20, Refs #1048):
    #   'folgen' (Default): #folgen-Hash, Folgen-Uebersicht mit /alben-Lese-Call.
    #   'einstellungen': #einstellungen-Hash, Einstellungen-Tueroeffner
    #     (NUR bei explizitem Direkt-Trigger wie "schick mir die Hoerbuch settings").
    #     Kein /alben-Call, kein Settings-Inhalt im Text.
    #
    # Returnt ein Form-(b)-Dict {text, presentation}:
    #   Mit Button: presentation: {inline_button: {label, web_app_url}}.
    #   Ohne Button (Konfig-/Netz-Fehler): presentation: {}.
    #   E-HOE-3: Bei leerem Album-Bestand (tab='folgen') trotzdem Button.
    #
    # Wirft BerechtigungError bei HOE-2-Verletzung.

    # HOE-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "hoerspiel_oeffnen: User %s nicht berechtigt (HOE-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur fuer Eltern.")

    result = _baue_uebersicht(hoerspiel_client, mini_app_url, tab=tab)
    presentation = result.get("presentation") or {}
    button_count = 1 if "inline_button" in presentation else 0
    logger.info(
        "hoerspiel_oeffnen: tab=%s, Tueroeffner fuer Chat %s, Buttons=%d",
        tab, chat_id, button_count,
    )
    return result
