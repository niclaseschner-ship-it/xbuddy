"""Gericht löschen — Drei-Phasen-Skill (EC-10 Drei-Phasen-Klausel, ESSEN-19b).

Vertikale Scheibe: Nic schickt "ich will Gerichte löschen", Skill zeigt
nummerierte Liste (Lese-Phase), Nic antwortet frei ("2 und 3"), Skill
löst Freitext → IDs auf (Auswahl-Phase via `llm_fn`), legt strukturierten
Vorschlag vor und löscht nach Bestätigung (Schreib-Phase → DELETE).

Signal-Tuple (signal, daten):
  ("liste",       {"gerichte": [...]})           — Lese-Phase: Liste zeigen.
  ("ausgewaehlt", {"gericht_ids": [...], ...})   — Auswahl aufgelöst, Proposal
  ("geloescht",   {"labels": [...]})             — DELETE(s) ausgeführt.
  ("abgelehnt",   {})                            — Nicht-Mitglied.
  ("unbekannte_ids", {"verdaechtig": [...]})     — LLM hat IDs halluziniert.
  ("leer",        {})                            — Keine Gerichte im Katalog.
  ("nichts_zu_tun", {"reason": str})             — Aufruf ohne nötige Eingabe.
  ("nicht_erreichbar", {"detail": str})          — Buddy nicht erreichbar.
  ("grenze",      {"detail": str})               — 4xx-Fehler beim DELETE.

Drei-Phasen-Klausel (EC-10, ESSEN-19b):
  Phase 1 — Lese-Phase:  aktion="liste"       → Signal "liste"
  Phase 2 — Auswahl:     aktion="auswaehlen"  → Signal "ausgewaehlt" | Fehler
  Phase 3 — Schreib:     aktion="loeschen"    → Signal "geloescht" | Fehler

Auswahl-Vertrag (EC-10): `llm_fn` bekommt nummerierte Liste + Freitext,
gibt JSON-Array von IDs zurück. Halluzinierte IDs → SIGNAL_UNBEKANNTE_IDS.
"""

import json
import logging

from skills.essen_client import EssenClientError

logger = logging.getLogger(__name__)


# Operationen (EC-10 Drei-Phasen).
AKTION_LISTE       = "liste"
AKTION_AUSWAEHLEN  = "auswaehlen"
AKTION_LOESCHEN    = "loeschen"

# Ergebnis-Signale.
SIGNAL_LISTE           = "liste"
SIGNAL_AUSGEWAEHLT     = "ausgewaehlt"
SIGNAL_GELOESCHT       = "geloescht"
SIGNAL_ABGELEHNT       = "abgelehnt"
SIGNAL_UNBEKANNTE_IDS  = "unbekannte_ids"
SIGNAL_LEER            = "leer"
SIGNAL_NICHTS_ZU_TUN   = "nichts_zu_tun"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"
SIGNAL_GRENZE          = "grenze"


def gericht_loeschen(*, aktion, essen_client, is_member_fn, from_user_id,
                     freitext=None, gericht_ids=None, llm_fn=None):
    """Gericht löschen — Drei-Phasen-Funktion (EC-10, ESSEN-19b).

    `aktion`         — AKTION_LISTE | AKTION_AUSWAEHLEN | AKTION_LOESCHEN.
    `essen_client`   — EssenClient-Instanz mit lese_gerichte() + delete_gericht().
    `is_member_fn`   — Callable `(user_id) -> bool`.
    `from_user_id`   — Telegram-User-ID des Aufrufers.
    `freitext`       — Auswahl-Freitext der Familie (Phase 2).
    `gericht_ids`    — Validierte ID-Liste für Phase 3 (aus Proposal).
    `llm_fn`         — Callable `(prompt: str) -> str` für Auswahl-Parse
                       (EC-10: strukturierte ID-Liste). None → Stub (Tests).

    Liefert (signal, daten).
    """
    # Berechtigung (GAN-2-Muster).
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "gericht_loeschen: User %s nicht in Familien-Gruppe — abgelehnt",
            from_user_id)
        return SIGNAL_ABGELEHNT, {}

    if aktion == AKTION_LISTE:
        return _lese_phase(essen_client)

    if aktion == AKTION_AUSWAEHLEN:
        return _auswahl_phase(essen_client, freitext, llm_fn)

    if aktion == AKTION_LOESCHEN:
        return _schreib_phase(essen_client, gericht_ids or [])

    logger.warning(
        "gericht_loeschen: unbekannte Aktion %r — nichts zu tun", aktion)
    return SIGNAL_NICHTS_ZU_TUN, {"reason": "unbekannte Aktion"}


# ============================================================
#  Phase 1 — Lese-Phase: GET Gerichte-Liste
# ============================================================

def _lese_phase(essen_client):
    """EC-10 Phase 1: aktuelle Gerichte-Liste holen und zurückgeben."""
    try:
        gerichte = essen_client.lese_gerichte()
    except EssenClientError as e:
        logger.warning("gericht_loeschen: Lese-Phase fehlgeschlagen — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": str(e)}

    if not gerichte:
        logger.info("gericht_loeschen: Gerichte-Katalog leer — nichts zu löschen")
        return SIGNAL_LEER, {}

    logger.info("gericht_loeschen: Lese-Phase — %d Gerichte", len(gerichte))
    return SIGNAL_LISTE, {"gerichte": list(gerichte)}


# ============================================================
#  Phase 2 — Auswahl-Phase: Freitext → validierte ID-Liste
# ============================================================

def _auswahl_phase(essen_client, freitext, llm_fn):
    """EC-10 Phase 2: Freitext-Auswahl via LLM zu ID-Liste auflösen.

    LLM-Auswahl-Vertrag (EC-10): Eingabe = nummerierte Gerichte-Liste + Freitext.
    Ausgabe = JSON-Array von Gericht-IDs aus der Liste. Halluzinierte IDs
    (nicht in der Eingabe-Liste) → SIGNAL_UNBEKANNTE_IDS.
    """
    if not freitext or not str(freitext).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Freitext"}

    # Aktuelle Gerichte-Liste für Validierung holen.
    try:
        gerichte = essen_client.lese_gerichte()
    except EssenClientError as e:
        logger.warning("gericht_loeschen: Auswahl-Phase Lese-Fehler — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": str(e)}

    if not gerichte:
        return SIGNAL_LEER, {}

    # LLM-Aufruf mit nummerierter Liste + Freitext (EC-10 Auswahl-Vertrag).
    prompt = _baue_auswahl_prompt(gerichte, str(freitext).strip())
    raw_ids = _llm_auswahl_aufloesen(prompt, llm_fn)

    if raw_ids is None:
        # LLM-Antwort nicht parsbar → nachfragen.
        logger.warning(
            "gericht_loeschen: LLM-Antwort nicht parsbar für Freitext %r",
            freitext)
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "LLM-Antwort nicht parsbar"}

    # Halluzinations-Schutz (EC-10): nur IDs aus der Eingabe-Liste erlaubt.
    bekannte_ids = {str(g.get("id", "")) for g in gerichte}
    verdaechtige = [rid for rid in raw_ids if rid not in bekannte_ids]
    if verdaechtige:
        logger.warning(
            "gericht_loeschen: LLM halluzinierte IDs %r (nicht in Liste)",
            verdaechtige)
        return SIGNAL_UNBEKANNTE_IDS, {"verdaechtig": verdaechtige}

    if not raw_ids:
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "keine IDs ausgewählt"}

    # Gerichte-Details für den Proposal anreichern.
    id_set = set(raw_ids)
    ausgewaehlt = [g for g in gerichte if str(g.get("id", "")) in id_set]
    labels = [g.get("label", "?") for g in ausgewaehlt]

    logger.info(
        "gericht_loeschen: Auswahl-Phase — %d Gerichte ausgewählt: %r",
        len(raw_ids), labels)
    return SIGNAL_AUSGEWAEHLT, {
        "gericht_ids": raw_ids,
        "labels": labels,
        "gerichte": ausgewaehlt,
    }


def _baue_auswahl_prompt(gerichte, freitext):
    """Baut den LLM-Prompt für die Auswahl-Phase (EC-10 Auswahl-Vertrag).

    Format: nummerierte Liste der Gerichte + Freitext-Anfrage der Familie.
    Erwartet: JSON-Array der Gericht-IDs.
    """
    zeilen = []
    for i, g in enumerate(gerichte, start=1):
        zeilen.append("%d. %s (id: %s)" % (i, g.get("label", "?"), g.get("id", "?")))
    liste_text = "\n".join(zeilen)
    return (
        "Gerichte-Liste:\n%s\n\n"
        "Familien-Anfrage: %s\n\n"
        "Welche Gerichte sollen gelöscht werden? "
        "Antworte NUR mit einem JSON-Array der Gericht-IDs aus der Liste, "
        "z. B. [\"1\", \"3\"]. Keine IDs erfinden, nur IDs aus der Liste verwenden."
    ) % (liste_text, freitext)


def _llm_auswahl_aufloesen(prompt, llm_fn):
    """Ruft `llm_fn(prompt)` auf und parst das JSON-Array.

    Gibt eine Liste von ID-Strings zurück oder None bei Parse-Fehler.
    `llm_fn` ist die Test-Naht — None → kein LLM-Aufruf (Tests müssen
    llm_fn immer setzen, wenn AKTION_AUSWAEHLEN getestet wird).
    """
    if llm_fn is None:
        logger.warning(
            "gericht_loeschen: kein llm_fn gesetzt — Auswahl-Phase nicht möglich")
        return None

    try:
        raw = llm_fn(prompt)
    except Exception as e:
        logger.warning("gericht_loeschen: LLM-Aufruf fehlgeschlagen — %s", e)
        return None

    if not raw:
        return None

    # JSON-Parsing: LLM kann ``` oder trailing text liefern → bereinigen.
    text = str(raw).strip()
    # Entferne Code-Fence falls vorhanden.
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text[3:]
        text = text.strip()
    # Extrahiere das erste [...] Array.
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    array_text = text[start:end + 1]

    try:
        parsed = json.loads(array_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list):
        return None

    # Alle IDs als Strings normalisieren.
    return [str(item) for item in parsed if item is not None]


# ============================================================
#  Phase 3 — Schreib-Phase: DELETE(s) ausführen
# ============================================================

def _schreib_phase(essen_client, gericht_ids):
    """EC-10 Phase 3: DELETE für alle ausgewählten Gerichte.

    Bei Fehler wird der erste Fehler gemeldet — keine Teil-Löschung
    (defensiv: bereits gelöschte IDs vor dem Fehler bleiben gelöscht,
    aber der Skill meldet den Fehler ehrlich).
    """
    if not gericht_ids:
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "keine IDs zum Löschen"}

    geloeschte_labels = []
    for gericht_id in gericht_ids:
        try:
            essen_client.delete_gericht(str(gericht_id))
            geloeschte_labels.append(str(gericht_id))
        except EssenClientError as e:
            fehler_str = str(e)
            if "HTTP 4" in fehler_str:
                logger.info(
                    "gericht_loeschen: DELETE id=%s abgelehnt — %s",
                    gericht_id, e)
                return SIGNAL_GRENZE, {"detail": fehler_str}
            logger.warning(
                "gericht_loeschen: DELETE id=%s Fehler — %s", gericht_id, e)
            return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}

    logger.info(
        "gericht_loeschen: %d Gerichte gelöscht: %r",
        len(geloeschte_labels), geloeschte_labels)
    return SIGNAL_GELOESCHT, {"labels": geloeschte_labels}
