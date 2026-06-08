"""Seiten finden — specs/platform/seiten-registry.md (SREG-5/SREG-6).

Aufrufbare, trigger-agnostische Funktion (SREG-6): liest das Seiten-Inventar
aus der Seiten-Registry (`GET /api/v1/seiten`) und liefert eine gefilterte
Liste von Einträgen an den Aufrufer zurück.

Eingang: optionaler Such-/Filter-Begriff. Ausgang: Ergebnis-Signal als String
(„beantwortet", „abgelehnt", „nicht_erreichbar") + die Eintrags-Liste.

Die Funktion kennt ihren Aufrufer nicht (E-TER-1-Analog); der V1-Trigger ist
die Eltern-Chat-Aufgabe `SeitenFindenTask` (SREG-6, seiten_finden_task.py).

PBE-2 / SREG-11: Für N Panel-Instanzen liefert das Inventar N Editor-Einträge
(typ='eltern', pfad enthält '<panel_id>/bearbeiten'). Diese erscheinen im
Ergebnis wie alle anderen Einträge — der Filter kann sie gezielt ansprechen.
"""

import logging

from skills.seiten_client import SeitenClientError

logger = logging.getLogger(__name__)


# SREG-6: Ergebnis-Signale der Funktion.
SIGNAL_BEANTWORTET   = "beantwortet"
SIGNAL_ABGELEHNT     = "abgelehnt"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"

# Antwort-Texte (EC-7, EC-22 analog).
_ANTWORT_NICHT_ERREICHBAR = (
    "Die Seiten-Registry ist gerade nicht erreichbar — ich kann gerade keine "
    "Seiten zeigen, bitte gleich nochmal probieren.")

_ANTWORT_KEINE_TREFFER = "Ich habe keine passenden Seiten gefunden."

_ANTWORT_ALLE_SEITEN_LEER = "Es sind noch keine Seiten registriert."


def filtere_eintraege(eintraege, suchbegriff=None):
    """Filtert eine Inventar-Liste nach einem optionalen Suchbegriff (SREG-6).

    Ohne `suchbegriff` (leer oder None) wird die vollständige Liste geliefert.
    Mit `suchbegriff` wird case-insensitiv in `label`, `pfad`, `synonyme` und
    `typ` gesucht. Zurückgegeben werden Dicts mit den relevanten Feldern.

    PBE-2 / SREG-11: Editor-Einträge (typ='eltern', pfad enthält '/bearbeiten')
    erscheinen im Ergebnis wie alle anderen Einträge und sind filterbar.
    """
    if not eintraege:
        return []

    if not suchbegriff or not str(suchbegriff).strip():
        # Kein Filter → alle Einträge
        return list(eintraege)

    q = str(suchbegriff).strip().lower()
    treffer = []
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        # Suche in label, pfad, typ
        label = str(eintrag.get("label") or "").lower()
        pfad  = str(eintrag.get("pfad") or "").lower()
        typ   = str(eintrag.get("typ") or "").lower()
        # Suche in synonyme (Liste von Strings)
        synonyme_text = " ".join(
            str(s) for s in (eintrag.get("synonyme") or [])
        ).lower()

        if (q in label or q in pfad or q in typ or q in synonyme_text):
            treffer.append(eintrag)
    return treffer


def formatiere_eintraege(eintraege, *, display_url_origin=None):
    """Formatiert eine Inventar-Liste als lesbaren Antwort-Text (SREG-6).

    Liefert einen deterministischen Text (EC-12), kein LLM. Jeder Eintrag
    erscheint als eine Zeile: `[typ] label — url`.

    SREG-5: Bei gesetzter `display_url_origin` wird jeder Link als volle URL
    gebildet (`origin.rstrip("/") + pfad`, GAA-3.7-Muster). Bei leerer oder
    None-Origin wird der Pfad als Fallback verwendet (SREG-7).
    """
    if not eintraege:
        return ""
    origin = (display_url_origin or "").rstrip("/")
    zeilen = []
    for e in eintraege:
        label = e.get("label") or e.get("pfad") or "(unbekannt)"
        pfad  = e.get("pfad") or ""
        typ   = e.get("typ") or "?"
        link  = (origin + pfad) if origin else pfad
        zeilen.append("• [%s] %s — %s" % (typ, label, link))
    return "\n".join(zeilen)


# ============================================================
#  Haupt-Funktion
# ============================================================

def seiten_finden(tg, chat_id, from_user_id, suchbegriff,
                  seiten_client, is_member_fn,
                  display_url_origin=None):
    """Seiten finden — aufrufbare Funktion (SREG-6).

    Liest das Inventar aus der Seiten-Registry, filtert es nach `suchbegriff`
    und postet das Ergebnis in `chat_id`. Ergebnis-Signal als String (SREG-6).

    `tg`                 — Telegram-Kanal (send_message).
    `chat_id`            — Zielchat (Gruppe oder Privatchat).
    `from_user_id`       — Telegram-User-ID des Aufrufers (Berechtigung SREG-6).
    `suchbegriff`        — Optionaler Filter-/Such-Text, leer = alle Seiten zeigen.
    `seiten_client`      — SeitenClient-Instanz (oder Doppelung).
    `is_member_fn`       — Callable `(user_id) -> bool` (Live-Prüfung SREG-6).
    `display_url_origin` — Optionale Origin-URL (SREG-5/GAA-3.7). Bei gesetzter
                           Origin werden volle Links gebildet; ohne Origin
                           Pfad-Fallback (SREG-7).

    Ergebnis-Signal:
      „beantwortet"      — Antwort wurde in chat_id gepostet.
      „abgelehnt"        — Aufrufer kein Familienmitglied (SREG-6/EC-2).
      „nicht_erreichbar" — Seiten-Registry nicht da oder Fehler (EC-7).
    """
    if chat_id is None:
        logger.warning("seiten_finden: chat_id fehlt — Abbruch ohne Wirkung")
        return SIGNAL_ABGELEHNT

    # SREG-6: Berechtigung — EC-2-Mitgliedschaft (analog TER-2).
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("seiten_finden: User %s ist kein Familienmitglied — abgelehnt",
                    from_user_id)
        return SIGNAL_ABGELEHNT

    # Inventar holen
    try:
        eintraege = seiten_client.inventar()
    except SeitenClientError as e:
        logger.warning("seiten_finden: Seiten-Registry nicht erreichbar — %s", e)
        tg.send_message(chat_id, _ANTWORT_NICHT_ERREICHBAR)
        return SIGNAL_NICHT_ERREICHBAR

    # Filter anwenden
    treffer = filtere_eintraege(eintraege, suchbegriff)

    if not eintraege:
        tg.send_message(chat_id, _ANTWORT_ALLE_SEITEN_LEER)
        return SIGNAL_BEANTWORTET

    if not treffer:
        tg.send_message(chat_id, _ANTWORT_KEINE_TREFFER)
        return SIGNAL_BEANTWORTET

    antwort = formatiere_eintraege(treffer, display_url_origin=display_url_origin)
    if not antwort.strip():
        tg.send_message(chat_id, _ANTWORT_KEINE_TREFFER)
        return SIGNAL_BEANTWORTET

    tg.send_message(chat_id, antwort)
    logger.info("seiten_finden: %d Treffer (Filter=%r) an Chat %s",
                len(treffer), suchbegriff, chat_id)
    return SIGNAL_BEANTWORTET
