"""Wünsche zeigen — specs/platform/wuensche-zeigen.md (WZE-1 … WZE-8, E-WZE-1/2).

Aufrufbare, trigger-agnostische Funktion (WZE-1, E-WZE-1-Muster): liest
die Wunschliste des Essens-Buddys (ESSEN-15) und postet eine
kategorie-gruppierte Zusammenfassung in den Anfrage-Chat (WZE-3/WZE-5).

**Eingang:**
  - `chat_id`       — Telegram-Chat, in dem die Antwort landet (WZE-3).
  - `from_user_id`  — Telegram-User-ID des Aufrufers (Berechtigung WZE-2).
  - `essen_client`  — EssenClient-Instanz (WZE-4, CLIENT-1-Naht).
  - `is_member_fn`  — Callable `(user_id) -> bool` (WZE-2, EC-2).
  - `tg`            — Telegram-Kanal (send_message).

**Ergebnis-Signale (WZE-1):**
  „beantwortet"      — Antwort im Chat gepostet.
  „leer"             — Leere Wunschliste, ehrliche Meldung gepostet (WZE-6).
  „abgelehnt"        — Kein Familienmitglied (WZE-2).
  „nicht_erreichbar" — Essens-Buddy nicht erreichbar (WZE-7, EC-7).
"""

import logging

from skills.essen_client import EssenClientError

logger = logging.getLogger(__name__)


# Ergebnis-Signale der Funktion (WZE-1).
SIGNAL_BEANTWORTET      = "beantwortet"
SIGNAL_LEER             = "leer"
SIGNAL_ABGELEHNT        = "abgelehnt"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"

# E-WZE-2: feste Kategorie-Reihenfolge (Gerichte zuerst — zentrale
# Mahlzeit-Entscheidung, dann Lebensmittel in Einkaufs-typischer Reihenfolge).
KATEGORIEN_REIHENFOLGE = ["gericht", "obst_gemuese", "brotbelag", "sonstiges"]

# WZE-5: Anzeigetitel je Kategorie (Plain-Text für Telegram).
KATEGORIE_TITEL = {
    "gericht":      "Gerichte",
    "obst_gemuese": "Obst & Gemüse",
    "brotbelag":    "Brotbelag",
    "sonstiges":    "Sonstiges",
}


def formatiere_wuensche(wuensche):
    """WZE-5: kategorie-gruppierte Zusammenfassung der Wunschliste.

    Liefert den vollständigen Bot-Text: Kategorien in fester Reihenfolge
    (E-WZE-2), je Kategorie mit Sub-Überschrift. Leere Kategorien tragen
    `- (keine)` — so ist klar, dass sie abgefragt wurden (WZE-5).

    Innerhalb einer Kategorie ist die Reihenfolge chronologisch
    (`erstellt_am` aufsteigend) — die Liste kommt bereits so vom Buddy
    (ESSEN-15: Reihenfolge ist `erstellt_am` aufsteigend).
    """
    # Gruppieren nach Kategorie in der Ankunfts-Reihenfolge (chronologisch,
    # ESSEN-15) — wir behalten die Reihenfolge aus der API-Antwort.
    gruppen = {k: [] for k in KATEGORIEN_REIHENFOLGE}
    for wunsch in wuensche:
        kategorie = wunsch.get("kategorie") or "sonstiges"
        if kategorie not in gruppen:
            kategorie = "sonstiges"
        gruppen[kategorie].append(wunsch.get("label") or "?")

    zeilen = ["Wünsche:"]
    for kat in KATEGORIEN_REIHENFOLGE:
        titel = KATEGORIE_TITEL[kat]
        items = gruppen[kat]
        zeilen.append("")
        zeilen.append("%s:" % titel)
        if items:
            for item in items:
                zeilen.append("- %s" % item)
        else:
            zeilen.append("- (keine)")

    return "\n".join(zeilen)


def wuensche_zeigen(tg, chat_id, from_user_id, essen_client, is_member_fn):
    """Wünsche zeigen — aufrufbare Funktion (WZE-1, E-WZE-1).

    Liest die Wunschliste über den EssenClient (WZE-4) und postet eine
    kategorie-gruppierte Zusammenfassung in `chat_id` (WZE-3/WZE-5).

    `tg`           — Telegram-Kanal (send_message).
    `chat_id`      — Zielchat (WZE-3).
    `from_user_id` — Telegram-User-ID des Aufrufers (WZE-2).
    `essen_client` — EssenClient-Instanz (WZE-4, CLIENT-1-Naht).
    `is_member_fn` — Callable `(user_id) -> bool` (WZE-2/EC-2).

    Ergebnis-Signal (s. Modul-Docstring).
    """
    if chat_id is None:
        logger.warning("wuensche_zeigen: chat_id fehlt — Abbruch ohne Wirkung")
        return SIGNAL_ABGELEHNT

    # WZE-2: Berechtigung — live geprüft, analog EC-2 / TER-2 / RPS-2.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("wuensche_zeigen: User %s ist kein Familienmitglied "
                    "— abgelehnt (WZE-2)", from_user_id)
        return SIGNAL_ABGELEHNT

    # WZE-4: Lesen über die Essens-Buddy-Schnittstelle (APP-3: nie Datei).
    try:
        wuensche = essen_client.get_wuensche()
    except EssenClientError as e:
        # WZE-7: ehrliche Grenze — kein Cache, kein Retry.
        logger.warning("wuensche_zeigen: Essens-Buddy nicht erreichbar — %s", e)
        tg.send_message(
            chat_id,
            "Die Wunschliste ist gerade nicht erreichbar, "
            "bitte später nochmal versuchen.")
        return SIGNAL_NICHT_ERREICHBAR

    # WZE-6: Leere Liste — ehrliche Meldung, kein Kategorie-Schema.
    if not wuensche:
        logger.info("wuensche_zeigen: leere Wunschliste — WZE-6")
        tg.send_message(chat_id, "Aktuell sind keine Wünsche in der Liste.")
        return SIGNAL_LEER

    # WZE-5: kategorie-gruppierte Zusammenfassung (E-WZE-2: feste Reihenfolge).
    antwort = formatiere_wuensche(wuensche)
    tg.send_message(chat_id, antwort)
    logger.info("wuensche_zeigen: %d Wünsche an Chat %s gepostet",
                len(wuensche), chat_id)
    return SIGNAL_BEANTWORTET
