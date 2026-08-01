# Hoerspiel oeffnen -- specs/platform/hoerspiel-oeffnen.md (HOE-1 ... HOE-7).
#
# **HSP-53 (2026-07-03):** Die Telegram-Eltern-Mini-App (HSP-33--40, Tab-Form,
# tma-Auth, Hash-Deeplink) ist superseded. Dieser Skill oeffnet jetzt die
# **Hoerspiel-Player-PWA** (HSP-47, /seiten/hoerspiel/player, public AUTH-6).
# Kein Tab-Parameter mehr, kein Hash-Fragment (#folgen/#einstellungen).
#
# Aufrufbare, trigger-agnostische Funktion (HOE-1, E-HOE-1 analog E-RAO-1):
# liest die Album-Liste (GET /api/v1/hoerspiel/mia/alben) als festen
# Launcher, baut eine kompakte Folgen-Uebersichts-Nachricht + URL-Button auf
# die Player-PWA (HOE-4) und gibt ein Form-(b)-Dict zurueck (TASK-10c).
#
# TASK-10c Form (b): der Skill returnt {text, presentation} -- der Task
# reicht das Dict direkt weiter; das Framework (agent.py + render_form_b)
# uebersetzt presentation in eine Telegram-Nachricht. Der Skill sendet
# NICHTS selbst (EC-29 "Eine Stimme im Agent-Turn").
#
# Eingang:
#   chat_id          -- Telegram-Chat (HOE-1).
#   from_user_id     -- Telegram-User-ID des Aufrufers (Berechtigung HOE-2).
#   hoerspiel_client -- HoerspielClient-Instanz fuer mia (HOE-1, CLIENT-1).
#   is_member_fn     -- Callable (user_id) -> bool (HOE-2, EC-2).
#   mini_app_url     -- URL der Player-PWA (HOE-5, HSP-47).
#                       Leer -> Fehler-Text (HOE-7).
#
# Ausgang: Form-(b)-Dict {text, presentation}:
#   Mit Button: presentation: {inline_buttons: [{label, url}]}.
#   Ohne Button (Konfig-/Netz-Fehler): presentation: {}.
#   E-HOE-3: Bei leerem Album-Bestand wird trotzdem ein Button zurueckgegeben
#   (analog E-RAO-3 -- Anfangszustand, kein Endzustand).
#
# Wirft BerechtigungError bei HOE-2-Verletzung.
#
# RAT-16: Adapter-Disziplin -- diese Datei enthaelt kein Telegram-Vokabular.
# Alles Telegram-Spezifische liegt im Adapter (_task.py).

import logging

from skills._errors import BerechtigungError
from skills._quittungen import nicht_erreichbar as _q_nicht_erreichbar
from skills.hoerspiel_client import HoerspielClientError

logger = logging.getLogger(__name__)

# HOE-4: Labels fuer den Player-Button (E-HOE-3: auch bei leerem Bestand).
_LABEL_FOLGEN = "\U0001f3a7 Folgen anhören"
_LABEL_FOLGEN_LEER = "\U0001f3a7 Player öffnen"


def _baue_folgen_text(alben_liste):
    # HOE-4: kompakter Folgen-Text aus GET /alben.
    # E-HOE-3: Leerer Album-Bestand -> Sonderfall-Text (Button trotzdem gesetzt).
    n = len(alben_liste)
    if n == 0:
        return (
            "\U0001f3a7 Hörspiel — noch keine Folge vorhanden. "
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
        "\U0001f3a7 Hörspiel — %d %s (zuletzt: Folge %s „%s“)"
        % (n, "Folge" if n == 1 else "Folgen", nr, titel)
    )


def _baue_uebersicht(hoerspiel_client, mini_app_url):
    # HOE-4: baut Text + presentation fuer die Hoerspiel-Uebersichts-Nachricht.
    #
    # HSP-53: oeffnet die Player-PWA (kein Tab-Modell, kein Hash-Fragment).
    #
    # Liefert ein Form-(b)-Dict {text, presentation} (TASK-10c):
    #   Normalfall: Text mit Folgen-Uebersicht + inline_buttons-URL-Button auf die PWA.
    #   HOE-7 mini_app_url leer: Fehler-Text, presentation leer.
    #   HOE-7 Buddy nicht erreichbar: Fehler-Text, presentation leer.

    # HOE-7: Player-URL fehlt -> Fehler-Text, kein Button
    if not mini_app_url:
        logger.warning("hoerspiel_oeffnen: mini_app_url fehlt in Konfig (HOE-7)")
        return {
            "text": "⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic.",
            "presentation": {},
        }

    # HSP-53: Player-PWA URL -- kein Hash-Fragment, kein Tab-Modell mehr
    pwa_url = mini_app_url.rstrip("/")

    # HOE-4: Lese-Pfad /alben + Button-Label
    try:
        alben_liste = hoerspiel_client.alben_lesen()
    except HoerspielClientError as e:
        logger.warning(
            "hoerspiel_oeffnen: Hoerspiel-Buddy (alben) nicht erreichbar — %s", e)
        return {
            "text": _q_nicht_erreichbar("Hörspiel-Buddy"),
            "presentation": {},
        }
    n = len(alben_liste)
    text = _baue_folgen_text(alben_liste)
    # E-HOE-3: Button auch bei leerem Album-Bestand
    label = _LABEL_FOLGEN_LEER if n == 0 else _LABEL_FOLGEN

    # HSP-53: URL-Button (nicht web_app), da Player-PWA oeffentlich (AUTH-6)
    presentation = {
        "inline_buttons": [
            {"label": label, "url": pwa_url}
        ]
    }
    return {"text": text, "presentation": presentation}


def hoerspiel_oeffnen(chat_id, from_user_id,
                      hoerspiel_client, is_member_fn, mini_app_url):
    # Hoerspiel oeffnen -- aufrufbare Funktion (HOE-1, E-HOE-1).
    #
    # HSP-53: oeffnet die Player-PWA (/seiten/hoerspiel/player, AUTH-6).
    # Kein Tab-Parameter mehr, kein Hash-Fragment. Liest Album-Liste,
    # baut Uebersichts-Text + URL-Button (TASK-10c Form (b)).
    #
    # Returnt ein Form-(b)-Dict {text, presentation}:
    #   Mit Button: presentation: {inline_buttons: [{label, url}]}.
    #   Ohne Button (Konfig-/Netz-Fehler): presentation: {}.
    #   E-HOE-3: Bei leerem Album-Bestand trotzdem Button.
    #
    # Wirft BerechtigungError bei HOE-2-Verletzung.

    # HOE-2: Berechtigung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "hoerspiel_oeffnen: User %s nicht berechtigt (HOE-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    result = _baue_uebersicht(hoerspiel_client, mini_app_url)
    presentation = result.get("presentation") or {}
    button_count = len(presentation.get("inline_buttons", []))
    logger.info(
        "hoerspiel_oeffnen: Player-Tueroeffner fuer Chat %s, Buttons=%d",
        chat_id, button_count,
    )
    return result
