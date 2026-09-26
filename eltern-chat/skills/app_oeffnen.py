"""App öffnen — der EINE registry-getriebene Öffnen-Skill (#1964, EC-46).

Nic 26.09.2026: **jede App ist im Chat erfragbar, so wie die Hörspiele —
auch die Eltern-Views — und zwar einheitlich.** Statt je App einen eigenen
Öffnen-Skill zu pflegen (früher `hoerspiel_oeffnen`, `routine_anpassen_oeffnen`,
`wetter_regeln_oeffnen`), liest dieser Skill das **Ansichts-Verzeichnis**
(`<buddy>/views.json` → Seiten-Registry, `GET /api/v1/seiten`, SREG-3) und
öffnet, was dort steht. Eine neue `views.json`-Zeile ist damit ohne
Chat-Code erfragbar.

Das Modell wählt die App per `key` (Inventar-Feld, `<app>-<slug>`). Die
Liste der Keys samt `label`, `synonyme` und `zielgruppe` bekommt es in der
Werkzeug-Beschreibung (`AppOeffnenTask.to_def`, pro Turn aus dem
zwischengespeicherten Verzeichnis).

Antwort-Form (immer gleich, EC-29 „eine Stimme"):
  - ein Satz: „<Label>“: <zeigt>  — bzw. bei mehreren Apps „Dazu passen …“;
  - je App die Knopfreihe aus `skills.app_knoepfe` (Mini-App, Browser,
    bei PWA Installieren).

Mehrdeutig (z. B. „Wetter“ → Wetter heute + Wetter-Regeln): das Modell gibt
beide Keys, der Skill schickt beide Knopfreihen in EINER Nachricht — keine
Rückfrage, weil der Tap die Frage schneller beantwortet (EC-40 „sofort
aufrufen, nicht erst fragen").

Berechtigung wie alle Öffnen-Skills vorher (HOE-2/RAO-2/WRO-2/SREG-6):
Mitglied der Familien-Gruppe (EC-2). Kind-Apps schickt der Chat den Eltern
zum Weitergeben — so tat es schon der Hörspiel-Player-Knopf.

RAT-16: kein Telegram-Vokabular hier; die Knöpfe sind vendor-neutral.
"""

import logging
import time

from skills._errors import BerechtigungError
from skills.app_knoepfe import absolute_url, app_knoepfe
from skills.seiten_client import SeitenClientError

logger = logging.getLogger(__name__)

#: Höchstens so viele Apps in einer Antwort (Mehrdeutigkeit, nicht Katalog).
MAX_APPS = 3

#: So lange gilt das zwischengespeicherte Verzeichnis (Sekunden). Das
#: Inventar ändert sich nur mit einem Deploy; fünf Minuten halten die
#: Werkzeug-Beschreibung frisch, ohne jeden Turn die Registry zu fragen.
VERZEICHNIS_TTL_SEKUNDEN = 300


class AppVerzeichnis:
    """Zwischenspeicher über dem Registry-Inventar (`SeitenClient.inventar`).

    Liefert die Einträge, die sich öffnen lassen (mit `key`, `pfad`, `label`).
    Ist die Registry nicht erreichbar, bleibt der letzte gute Stand in
    Gebrauch; gab es nie einen, ist die Liste leer (der Skill meldet das
    ehrlich, EC-7).
    """

    def __init__(self, seiten_client, ttl=VERZEICHNIS_TTL_SEKUNDEN,
                 uhr=time.monotonic):
        self._client = seiten_client
        self._ttl = ttl
        self._uhr = uhr
        self._eintraege = []
        self._geladen_um = None

    def eintraege(self):
        jetzt = self._uhr()
        if self._geladen_um is not None and jetzt - self._geladen_um < self._ttl:
            return self._eintraege
        try:
            roh = self._client.inventar()
        except SeitenClientError as e:
            logger.warning("app_oeffnen: Seiten-Registry nicht erreichbar — %s", e)
            return self._eintraege
        self._eintraege = [
            e for e in roh
            if isinstance(e, dict) and e.get("key") and e.get("pfad") and e.get("label")
        ]
        self._geladen_um = jetzt
        return self._eintraege


def _satz(apps):
    """Der eine Satz der Antwort."""
    if len(apps) == 1:
        app = apps[0]
        zeigt = (app.get("zeigt") or "").strip()
        return "„%s“: %s" % (app["label"], zeigt) if zeigt else "„%s“" % app["label"]
    namen = ["„%s“" % a["label"] for a in apps]
    return "Dazu passen %s und %s." % (", ".join(namen[:-1]), namen[-1])


def app_oeffnen(chat_id, from_user_id, keys, eintraege, is_member_fn, basis_url):
    """Öffnet eine oder mehrere Apps aus dem Verzeichnis (EC-46).

    `keys`      — Inventar-Keys, die das Modell gewählt hat (1..MAX_APPS).
    `eintraege` — Inventar-Einträge (`AppVerzeichnis.eintraege()`).
    `basis_url` — Funnel-Origin (`mini_app_base_url`), unter der alle
                  Flächen liegen (`/seiten/…`, `/api/v1/seiten/…`, `/display/…`).

    Returnt Form-(b) `{text, presentation}`; ohne Knöpfe ist `presentation` leer.
    Wirft `BerechtigungError`, wenn der Aufrufer kein Familien-Mitglied ist.
    """
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("app_oeffnen: User %s nicht berechtigt (EC-2)", from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    if not basis_url:
        logger.warning("app_oeffnen: mini_app_base_url fehlt in Konfig")
        return {"text": "⚠️ Die Mini-App-URL fehlt in meiner Konfig — frag Nic.",
                "presentation": {}}

    if not eintraege:
        return {"text": ("Das App-Verzeichnis ist gerade nicht erreichbar — bitte "
                         "gleich nochmal versuchen."),
                "presentation": {}}

    nach_key = {e["key"]: e for e in eintraege}
    gewaehlt = []
    unbekannt = []
    for key in keys:
        if key in nach_key and nach_key[key] not in gewaehlt:
            gewaehlt.append(nach_key[key])
        elif key not in nach_key:
            unbekannt.append(key)
    gewaehlt = gewaehlt[:MAX_APPS]
    if unbekannt:
        logger.info("app_oeffnen: unbekannte Keys %r", unbekannt)
    if not gewaehlt:
        return {
            "text": ("Diese App kenne ich nicht. Frag nach der Übersicht, "
                     "dann siehst du alle Apps."),
            "presentation": {},
        }

    mehrere = len(gewaehlt) > 1
    knoepfe = []
    for app in gewaehlt:
        url = absolute_url(basis_url, app["pfad"])
        knoepfe.extend(app_knoepfe(
            url, "📱 %s öffnen" % app["label"], pwa=bool(app.get("pwa")),
            name=app["label"] if mehrere else None))

    logger.info("app_oeffnen: Chat %s, Apps=%s, Knöpfe=%d",
                chat_id, [a["key"] for a in gewaehlt], len(knoepfe))
    return {"text": _satz(gewaehlt), "presentation": {"inline_buttons": knoepfe}}
