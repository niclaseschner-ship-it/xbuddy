"""Wünsche zeigen — specs/platform/wuensche-zeigen.md (WZE-1 … WZE-8, E-WZE-1/2).

Aufrufbare, trigger-agnostische Funktion (WZE-1, E-WZE-1-Muster): liest
die Wunschliste des Essens-Buddys (ESSEN-15) und gibt eine
kategorie-gruppierte Zusammenfassung als Tool-Result-String zurück (EC-29).

**Eingang:**
  - `chat_id`       — Telegram-Chat, in dem die Antwort landen wird (WZE-3).
  - `from_user_id`  — Telegram-User-ID des Aufrufers (Berechtigung WZE-2).
  - `essen_client`  — EssenClient-Instanz (WZE-4, CLIENT-1-Naht).
  - `is_member_fn`  — Callable `(user_id) -> bool` (WZE-2, EC-2).

**Ergebnis (WZE-1, EC-29):**
  Die Funktion returnt in jedem Pfad einen User-tauglichen Antwort-Text
  als String (Tool-Result). Das LLM postet — die Funktion sendet selbst
  keine Telegram-Nachricht (EC-29).
  Berechtigungs-Bruch (WZE-2): wirft `BerechtigungError` — der Agent-Loop
  schreibt den Fehler-Tool-Result-Block (agent.py Fehlerpfad).
"""

import logging

from skills.essen_client import EssenClientError

logger = logging.getLogger(__name__)


class BerechtigungError(Exception):
    """Aufrufer ist kein autorisiertes Familienmitglied (WZE-2, EC-29).

    Der Agent-Loop fängt diese Exception und schreibt einen
    Fehler-Tool-Result-Block; das LLM schweigt in der Antwort.
    """


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

# WZE-6: Meldung bei leerer Wunschliste.
_ANTWORT_LEER = "Aktuell sind keine Wünsche in der Liste."

# WZE-7: Meldung wenn Essens-Buddy nicht erreichbar.
_ANTWORT_NICHT_ERREICHBAR = (
    "Die Wunschliste ist gerade nicht erreichbar, "
    "bitte später nochmal versuchen.")


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


def wuensche_zeigen(chat_id, from_user_id, essen_client, is_member_fn):
    """Wünsche zeigen — aufrufbare Funktion (WZE-1, E-WZE-1, EC-29).

    Liest die Wunschliste über den EssenClient (WZE-4) und gibt eine
    kategorie-gruppierte Zusammenfassung als Tool-Result-String zurück
    (WZE-3/WZE-5). Die Funktion sendet selbst keine Telegram-Nachricht
    — das LLM postet (EC-29).

    `chat_id`      — Zielchat (WZE-3, wird nicht von dieser Funktion genutzt,
                     aber als Kontext an den Aufrufer weitergegeben).
    `from_user_id` — Telegram-User-ID des Aufrufers (WZE-2).
    `essen_client` — EssenClient-Instanz (WZE-4, CLIENT-1-Naht).
    `is_member_fn` — Callable `(user_id) -> bool` (WZE-2/EC-2).

    Returnt User-tauglichen Antwort-Text als String (EC-29).
    Wirft `BerechtigungError` bei WZE-2-Verletzung.
    """
    # WZE-2: Berechtigung — live geprüft, analog EC-2 / TER-2 / RPS-2.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("wuensche_zeigen: User %s ist kein Familienmitglied "
                    "— abgelehnt (WZE-2)", from_user_id)
        raise BerechtigungError(
            "Du bist kein Mitglied der Familien-Gruppe.")

    # WZE-4: Lesen über die Essens-Buddy-Schnittstelle (APP-3: nie Datei).
    try:
        wuensche = essen_client.get_wuensche()
    except EssenClientError as e:
        # WZE-7: ehrliche Grenze — kein Cache, kein Retry.
        logger.warning("wuensche_zeigen: Essens-Buddy nicht erreichbar — %s", e)
        return _ANTWORT_NICHT_ERREICHBAR

    # WZE-6: Leere Liste — ehrliche Meldung, kein Kategorie-Schema.
    if not wuensche:
        logger.info("wuensche_zeigen: leere Wunschliste — WZE-6")
        return _ANTWORT_LEER

    # WZE-5: kategorie-gruppierte Zusammenfassung (E-WZE-2: feste Reihenfolge).
    antwort = formatiere_wuensche(wuensche)
    logger.info("wuensche_zeigen: %d Wünsche für Chat %s als Tool-Result",
                len(wuensche), chat_id)
    return antwort
