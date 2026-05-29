"""Termine erfragen — specs/platform/termine-erfragen.md (TER-1 … TER-10).

Aufrufbare, trigger-agnostische Funktion (TER-1, E-TER-1): liest die Termine
eines Zeitraums aus dem Familien-Kalender über die Plan-Buddy-Termin-
Schnittstelle (PLAN-22, TER-5) und antwortet dem Familienmitglied im Chat.

Eingang: Telegram-Chat-ID (Zielchat), User-ID (Berechtigung TER-2), freier
Anfragetext (Datums-Parsing TER-4). Ausgang: Ergebnis-Signal als String
(„beantwortet", „abgelehnt", „leer", „nicht_erreichbar").

Die Funktion kennt ihren Aufrufer nicht (E-TER-1); der V1-Trigger ist die
Eltern-Chat-Aufgabe `TermineErfragenTask` (TER-10, termine_erfragen_task.py).
"""

import logging
import re
from datetime import date, timedelta

from skills.plan_client import PlanClient, PlanClientError


logger = logging.getLogger(__name__)


# TER-1: Ergebnis-Signale der Funktion.
SIGNAL_BEANTWORTET   = "beantwortet"
SIGNAL_ABGELEHNT     = "abgelehnt"
SIGNAL_LEER          = "leer"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"

# TER-7: Ehrliche Antwort bei nicht erreichbarem Plan-Buddy (EC-7, EC-22).
# Wortlaut lebt im Code, Spec normiert Existenz + Inhalt.
_ANTWORT_NICHT_ERREICHBAR = (
    "Der Wochenplan ist gerade nicht erreichbar — ich kann gerade keine "
    "Termine zeigen, bitte gleich nochmal probieren.")

# TER-8: Antwort bei leerem Zeitraum.
_ANTWORT_LEER = "Im angefragten Zeitraum stehen keine Termine an."

# TER-9: Tages-Kopf-Format (URL-7: deutsche Wochentage).
_WOCHENTAGE = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
]


# ============================================================
#  TER-4 — Datums-Vokabular (hart-codiert, kein LLM, EC-12)
# ============================================================

def parse_zeitraum(text, heute=None):
    """Löst einen freien Anfragetext in (start, tage) auf (TER-4).

    Erkennt das hart-codierte Mindest-Vokabular und gibt ein Tupel
    `(start: date, tage: int)` zurück. Bei mehrdeutigen Ausdrücken
    (die die Spec in TER-4 nennt) wird `None` zurückgegeben — der
    Aufrufer stellt dann eine gezielte Rückfrage (EC-22).

    `heute` ist für Tests injizierbar (Default: `date.today()`).
    """
    if heute is None:
        heute = date.today()
    t = (text or "").lower().strip()

    # „heute"
    if "heute" in t:
        return (heute, 1)

    # „morgen"
    if "morgen" in t:
        return (heute + timedelta(days=1), 1)

    # „nächste Woche" (vor „diese Woche" prüfen)
    if "nächste woche" in t or "naechste woche" in t:
        # nächster Montag (ISO-Wochenanfang, PLAN-28 wochenstart=0=Montag)
        tage_bis_montag = (7 - heute.weekday()) % 7
        if tage_bis_montag == 0:
            tage_bis_montag = 7
        naechster_montag = heute + timedelta(days=tage_bis_montag)
        return (naechster_montag, 7)

    # „diese Woche"
    if "diese woche" in t or "dieser woche" in t:
        # bis einschließlich nächsten Sonntag, maximal 7 (TER-4)
        # weekday(): 0=Mo, 6=So
        tage_bis_sonntag = (6 - heute.weekday()) % 7
        # Wenn heute Sonntag: tage_bis_sonntag=0 → nur heute selbst → tage=1
        tage = tage_bis_sonntag + 1
        if tage > 7:
            tage = 7
        return (heute, tage)

    # „die nächsten N Tage" (1 ≤ N ≤ 31)
    match = re.search(
        r"die\s+n[äa]chsten\s+(\d+)\s+tage?", t)
    if match:
        n = int(match.group(1))
        if 1 <= n <= 31:
            return (heute, n)
        # N außerhalb des Spec-Bereichs → mehrdeutig
        return None

    # Mehrdeutige Ausdrücke, für die TER-4 eine Rückfrage vorschreibt
    # (EC-22): konkrete Wochentage ohne klare Woche-Zuordnung.
    if re.search(r"n[äa]chsten?\s+(montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag)", t):
        return None

    # Default (TER-4): „was steht an", kein erkennbarer Datums-Ausdruck
    return (heute, 7)


# ============================================================
#  TER-9 — Tagesgruppierte Ausgabe
# ============================================================

def formatiere_termine(events, start, tage):
    """Formatiert eine PLAN-17-Event-Liste als tagesgruppierte Antwort (TER-9).

    Gruppiert chronologisch nach Tag; Mehrtages-Spannen (gleiche `id`)
    erscheinen genau einmal unter dem ersten Tag im Zeitraum (TER-9/PLAN-14).
    Ganztägige Termine tragen „ganztägig" statt einer Uhrzeit.

    `start`  — erster Tag des Zeitraums (date).
    `tage`   — Anzahl Tage.

    Liefert einen deterministischen Antwort-Text (EC-12), kein LLM.
    """
    tage_range = [start + timedelta(days=i) for i in range(tage)]

    # Mehrtages-Termine (gleiche id) werden pro Zeitraum nur einmal gezeigt.
    # Wir merken uns, welche ids bereits ausgegeben wurden.
    gesehene_ids = set()

    # Ordne jedes Event dem ersten Tag zu, an dem es im Zeitraum erscheint.
    # Ein Event gehört zu einem Tag, wenn sein Beginn (date-Teil) auf diesen
    # Tag fällt oder bei Mehrtages-Spannen der Tag im [beginn, ende)-Fenster
    # liegt.
    def event_erster_tag_im_zeitraum(ev):
        """Ersten Tag im Zeitraum zurückgeben, an dem das Event relevant ist."""
        try:
            beginn_raw = ev.get("beginn")
            if not beginn_raw:
                return None
            # beginn kann datetime oder date sein (ISO-Format)
            if "T" in str(beginn_raw):
                beginn_date = date.fromisoformat(str(beginn_raw).split("T")[0])
            else:
                beginn_date = date.fromisoformat(str(beginn_raw))
        except (ValueError, AttributeError):
            return None
        # Erster Tag im Zeitraum, an dem das Event beginnt oder läuft
        for d in tage_range:
            if beginn_date <= d:
                return d
        return None

    # Tage-Bucket: tag → [events]
    tage_buckets = {d: [] for d in tage_range}
    for ev in events:
        ev_id = ev.get("id")
        erster_tag = event_erster_tag_im_zeitraum(ev)
        if erster_tag is None:
            continue
        if erster_tag not in tage_buckets:
            continue
        if ev_id is not None and ev_id in gesehene_ids:
            continue  # Mehrtages-Spanne: schon ausgegeben
        if ev_id is not None:
            gesehene_ids.add(ev_id)
        tage_buckets[erster_tag].append(ev)

    # Ausgabe aufbauen
    zeilen = []
    for d in tage_range:
        events_des_tages = tage_buckets[d]
        if not events_des_tages:
            continue
        # Tages-Kopf: Wochentag + Datum (TER-9, URL-7)
        wochentag = _WOCHENTAGE[d.weekday()]
        zeilen.append("*%s, %02d.%02d.*" % (wochentag, d.day, d.month))
        for ev in events_des_tages:
            zeilen.append(_formatiere_event(ev))

    return "\n".join(zeilen)


def _formatiere_event(ev):
    """Formatiert ein einzelnes Event als Zeile (TER-9).

    Format: „[Uhrzeit oder ganztägig] Titel [Person]"
    Mehrtages-Spannen erhalten einen Spannen-Hinweis.
    """
    # Beginn-Uhrzeit oder ganztags
    if ev.get("ganztags"):
        zeit = "ganztägig"
    else:
        beginn_raw = ev.get("beginn") or ""
        if "T" in str(beginn_raw):
            # ISO-Datetime → Uhrzeit extrahieren
            try:
                uhrzeit_teil = str(beginn_raw).split("T")[1]
                # HH:MM[:SS[...]]
                uhrzeit = uhrzeit_teil[:5]
            except (IndexError, AttributeError):
                uhrzeit = ""
            zeit = uhrzeit if uhrzeit else "ganztägig"
        else:
            zeit = "ganztägig"

    titel = ev.get("titel") or "(kein Titel)"
    person = ev.get("person")

    # Mehrtages-Spanne erkennen (TER-9/PLAN-14): ende > beginn + 1 Tag
    spanne_hinweis = ""
    if ev.get("ganztags"):
        try:
            ende_raw = ev.get("ende") or ""
            if ende_raw:
                if "T" in str(ende_raw):
                    ende_date = date.fromisoformat(str(ende_raw).split("T")[0])
                else:
                    ende_date = date.fromisoformat(str(ende_raw))
                beginn_raw = ev.get("beginn") or ""
                if beginn_raw:
                    if "T" in str(beginn_raw):
                        beginn_date = date.fromisoformat(str(beginn_raw).split("T")[0])
                    else:
                        beginn_date = date.fromisoformat(str(beginn_raw))
                    # Google gibt bei ganztägigen Terminen ende=beginn+1; bei
                    # Mehrtages-Spannen ist die Differenz >= 2 Tage
                    if (ende_date - beginn_date).days >= 2:
                        spanne_hinweis = " (bis %02d.%02d.)" % (
                            ende_date.day, ende_date.month)
        except (ValueError, AttributeError):
            pass

    teile = ["  %s %s%s" % (zeit, titel, spanne_hinweis)]
    if person:
        teile[0] += " — %s" % person
    return teile[0]


# ============================================================
#  TER-1 — Haupt-Funktion
# ============================================================

def termine_erfragen(tg, chat_id, from_user_id, anfrage_text,
                     plan_client, is_member_fn, heute=None):
    """Termine erfragen — aufrufbare Funktion (TER-1).

    Liest die Termine des aus `anfrage_text` ermittelten Zeitraums aus der
    Plan-Buddy-Termin-Schnittstelle und postet eine lesbare Zusammenfassung
    in `chat_id` (TER-3, TER-9). Ergebnis-Signal als String (TER-1).

    `tg`             — Telegram-Kanal (send_message).
    `chat_id`        — Zielchat (Gruppe oder Privatchat, TER-3).
    `from_user_id`   — Telegram-User-ID des Aufrufers (Berechtigung TER-2).
    `anfrage_text`   — Natürlichsprachiger Anfragetext (Datums-Parsing TER-4).
    `plan_client`    — PlanClient-Instanz (oder Doppelung).
    `is_member_fn`   — Callable `(user_id) -> bool` (Live-Prüfung TER-2).
    `heute`          — Injektierbar für Tests (Default: date.today()).

    Ergebnis-Signal:
      „beantwortet"      — Antwort wurde in chat_id gepostet.
      „abgelehnt"        — Aufrufer kein Familienmitglied (TER-2).
      „leer"             — Keine Termine im Zeitraum (TER-8).
      „nicht_erreichbar" — Plan-Buddy nicht da oder Fehler (TER-7).
    """
    if chat_id is None:
        # TER-1: kein Zielchat → Abbruch ohne Wirkung
        logger.warning("termine_erfragen: chat_id fehlt — Abbruch ohne Wirkung")
        return SIGNAL_ABGELEHNT

    # TER-2: Live-Berechtigungsprüfung
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("termine_erfragen: User %s ist kein Familienmitglied — abgelehnt",
                    from_user_id)
        return SIGNAL_ABGELEHNT

    # TER-4: Datums-Vokabular auflösen
    zeitraum = parse_zeitraum(anfrage_text, heute=heute)
    if zeitraum is None:
        # TER-4 EC-22: mehrdeutig → Rückfrage
        tg.send_message(
            chat_id,
            "Ich bin mir nicht sicher, welchen Zeitraum du meinst — meinst du "
            "diese Woche, nächste Woche, oder die nächsten N Tage?")
        return SIGNAL_BEANTWORTET

    start, tage = zeitraum

    # TER-5: Termine aus der Plan-Buddy-Schnittstelle holen
    try:
        events = plan_client.termine(start.isoformat(), tage)
    except PlanClientError as e:
        logger.warning("termine_erfragen: Plan-Buddy nicht erreichbar — %s", e)
        tg.send_message(chat_id, _ANTWORT_NICHT_ERREICHBAR)
        return SIGNAL_NICHT_ERREICHBAR

    # TER-8: leerer Zeitraum
    if not events:
        tg.send_message(chat_id, _ANTWORT_LEER)
        return SIGNAL_LEER

    # TER-9: tagesgruppierte Antwort aufbauen
    antwort = formatiere_termine(events, start, tage)
    if not antwort.strip():
        # Alle Events lagen außerhalb des Zeitraums (Randfall)
        tg.send_message(chat_id, _ANTWORT_LEER)
        return SIGNAL_LEER

    tg.send_message(chat_id, antwort)
    logger.info("termine_erfragen: %d Events ab %s (%d Tage) an Chat %s",
                len(events), start.isoformat(), tage, chat_id)
    return SIGNAL_BEANTWORTET
