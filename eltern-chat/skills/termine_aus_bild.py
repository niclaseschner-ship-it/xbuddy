"""Termine aus Bild — specs/platform/termine-aus-bild.md (TAB-1 … TAB-13, Refs #475).

Aufrufbare, trigger-agnostische Funktion (TAB-1, E-TAB-1): nimmt ein Bild + den
Begleittext (Caption mit Signalwort, TAB-4) entgegen, extrahiert daraus über
einen multimodalen KI-Anbieter (TAB-5) eine Liste Termin-Vorschläge, legt sie
im Privatchat des Aufrufers vor (TAB-7), klärt ggf. Pflichtfeld-Lücken
(TAB-8.1 — max 2 Runden, TAB-8.3) und trägt die bestätigte Liste als **Bulk**
über die Plan-Buddy-Termin-Schnittstelle (TAB-9, PLAN-33) in den Familien-
Kalender ein.

Eingang: Telegram-Privatchat-ID, User-ID (TAB-2 Live-Berechtigung), Familien-
Gruppen-Chat-ID, Bild-Bytes + media_type, Caption, MultimodalProvider (TAB-5),
PlanClient (TAB-9), is_member_fn (TAB-2), next_message (Privatchat-Stream
TAB-3), typing_fn (EC-25 Best-Effort).

Ausgang: Ergebnis-Signal-String (TAB-1):
  „eingetragen"       — Bulk-PUT erfolgreich (TAB-11 N-von-M-Quittung gepostet).
  „verworfen"         — Aufrufer hat den Sammel-Vorschlag nicht bestätigt (TAB-7).
  „abgebrochen"       — Privatchat-Session-Timeout (SESS-3) oder Prozess-Restart.
  „abgelehnt"         — Berechtigung fehlt (TAB-2).
  „nicht_erreichbar"  — Plan-Buddy gar nicht erreichbar ODER 502
                        calendar_unavailable (TAB-10 erste/dritte Lage).
  „unbekannt"         — Bulk-Verbindung mitten im Aufruf abgerissen ODER 5xx
                        ohne parsbaren Body (TAB-10 zweite/vierte Lage).
  „provider_fehler"   — multimodaler Anbieter nicht erreichbar oder lieferte
                        unverwertbare Antwort (TAB-5, EC-14-analog).
  „unklar"            — leere Termin-Liste nach Plausi-Filter (TAB-6), ODER
                        Pflicht-Lücken auch nach 2 Rückfragen offen (TAB-8.3).

Datenlinie (EC-13 / E-TAB-5): das Bild geht an den multimodalen Anbieter und
wird danach verworfen. Kein Photo-Buddy-Aufruf, kein lokales Persistieren.
"""

import html
import logging
import re
import uuid
from collections.abc import Callable
from datetime import date, timedelta

import confirm
from telegram import TelegramError

from skills._multimodal import MultimodalError
from skills.plan_client import (
    PlanBulkNotReached,
    PlanBulkUnknown,
    PlanClientError,
)
from skills.typing_indicator import TypingRenewal, fire_typing

logger = logging.getLogger(__name__)


# ============================================================
#  TAB-1 — Ergebnis-Signale
# ============================================================

SIGNAL_EINGETRAGEN      = "eingetragen"
SIGNAL_VERWORFEN        = "verworfen"
SIGNAL_ABGEBROCHEN      = "abgebrochen"
SIGNAL_ABGELEHNT        = "abgelehnt"
SIGNAL_NICHT_ERREICHBAR = "nicht_erreichbar"
SIGNAL_UNBEKANNT        = "unbekannt"
SIGNAL_PROVIDER_FEHLER  = "provider_fehler"
SIGNAL_UNKLAR           = "unklar"


# ============================================================
#  TAB-4 — Signalwort-Liste (hart-codiert, deutsch)
# ============================================================

# Die Liste lebt im Code als hart-codierter String-Tupel (TAB-4) und fließt
# in die Tool-Schema-Beschreibung des EC-8-Tools ein (kein deterministischer
# Pre-Router — das LLM trifft die Wahl). Konkrete Werte: TAB-4 Spec.
SIGNAL_WORDS = (
    "termin", "termine", "kalender", "eintragen",
    "plan", "schulplan", "kursplan",
)


# ============================================================
#  TAB-6 — Plausi-Filter und Validierung
# ============================================================

# Plausi-Fenster: 400 Tage rückwärts, 2 Jahre vorwärts (TAB-6).
# 400 Tage (~13 Monate) erlaubt Kita-/Schulpläne, die saisonsweise
# wiederverwendet werden (Familien-Plan-Wiederverwendung, Refs #524).
PLAUSI_ZURUECK_TAGE = 400
PLAUSI_VORWAERTS_TAGE = 2 * 365

# TAB-9 / PLAN-33.3: harter Server-Cap bei 30 Items. Variante A (Risk 7):
# nach Plausi-Filter cappen + Hinweis im Sammel-Vorschlag.
MAX_ITEMS = 30


_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_ISO_DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?")


def _parse_beginn(beginn_str):
    """Parst ein `beginn`-Feld (ISO-Datum ODER ISO-Datetime) zu einem `date`-
    Objekt für die Plausi-Prüfung (TAB-6). Liefert `None` bei Form-Fehlern.
    """
    if not beginn_str:
        return None
    s = beginn_str.strip()
    # ISO-Datetime: YYYY-MM-DDTHH:MM[:SS][+HH:MM|Z]
    m = _ISO_DATETIME_RE.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except (ValueError, TypeError):
            return None
    # ISO-Datum: YYYY-MM-DD
    m = _ISO_DATE_RE.match(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except (ValueError, TypeError):
            return None
    return None


def _ist_zeitgebunden(item):
    """True wenn der ExtractedTermin als zeitgebunden gilt — `ende` ist dann
    PLAN-22-Pflicht (TAB-8.1 Lücken-Sammler)."""
    if item.ganztags is False:
        return True
    # `beginn` enthält ein `T` → zeitgebunden, auch wenn `ganztags` leer ist.
    return "T" in (item.beginn or "")


def validiere_und_filtere(items, heute=None):
    """TAB-6: Plausi-Filter + Schema-Vollständigkeit + Cap 30 (Risk 7).

    Liefert `(gefilterte_items, anzahl_verworfen_plausi, cap_hinweis_n,
              vergangenheits_n)`:
      - `gefilterte_items`         — Liste der überlebenden Termine (max 30).
      - `anzahl_verworfen_plausi`  — Anzahl außerhalb des Plausi-Fensters.
      - `cap_hinweis_n`            — Anzahl der durch Cap abgeschnittenen
                                     Items (für TAB-7-Hinweis); 0 wenn kein
                                     Cap nötig.
      - `vergangenheits_n`         — Anzahl der Items mit beginn_date < heute
                                     (aber innerhalb Plausi-Fenster — also
                                     nicht verworfen); für TAB-7-Hinweis.

    Items mit Pflicht-Lücken (titel leer / beginn fehlt / zeitgebunden ohne
    `ende`) bleiben **drin**, bekommen aber `fehlende_felder` gesetzt — der
    Aufrufer leitet sie in den Lücken-Sammler (TAB-8.1).
    """
    if heute is None:
        heute = date.today()
    fenster_start = heute - timedelta(days=PLAUSI_ZURUECK_TAGE)
    fenster_ende = heute + timedelta(days=PLAUSI_VORWAERTS_TAGE)
    out = []
    verworfen_plausi = 0
    vergangenheits_n = 0
    for item in items:
        # Plausi-Fenster — beginn muss parsbar sein UND im Fenster.
        beginn_date = _parse_beginn(item.beginn)
        if beginn_date is None:
            # Form-Fehler im Beginn-String → Pflicht-Lücke (TAB-8.1).
            item.fehlende_felder = list(item.fehlende_felder)
            if "beginn" not in item.fehlende_felder:
                item.fehlende_felder.append("beginn")
        elif not (fenster_start <= beginn_date <= fenster_ende):
            verworfen_plausi += 1
            continue
        else:
            # Termin liegt im Plausi-Fenster — zählen ob Vergangenheit.
            if beginn_date < heute:
                vergangenheits_n += 1

        # Schema-Vollständigkeit (TAB-6 / TAB-8.1).
        if not (item.titel or "").strip():
            item.fehlende_felder = list(item.fehlende_felder)
            if "titel" not in item.fehlende_felder:
                item.fehlende_felder.append("titel")

        if _ist_zeitgebunden(item) and not (item.ende or "").strip():
            item.fehlende_felder = list(item.fehlende_felder)
            if "ende" not in item.fehlende_felder:
                item.fehlende_felder.append("ende")

        out.append(item)

    # Cap 30 nach Plausi-Filter (Risk 7 Variante A) — Hinweis-N für TAB-7.
    cap_hinweis_n = 0
    if len(out) > MAX_ITEMS:
        cap_hinweis_n = len(out) - MAX_ITEMS
        out = out[:MAX_ITEMS]
        # Vergangenheits-Zähler auf die gecappte Liste begrenzen.
        vergangenheits_n = sum(
            1 for item in out
            if _parse_beginn(item.beginn) is not None
            and _parse_beginn(item.beginn) < heute
        )

    return out, verworfen_plausi, cap_hinweis_n, vergangenheits_n


# ============================================================
#  TAB-7 — Sammel-Vorschlag im HTML-<pre>-Block
# ============================================================

# Hart-codierte Wortlauten (TAB-7). Die Spec normiert das Soll: nummerierte
# Liste mit Datum + Titel + ggf. Uhrzeit-Spanne, im <pre>-Block, ein E-EC-7-
# Wort bestätigt alles.
_VORSCHLAG_KOPF = "Soll ich diese Termine eintragen?"
_VORSCHLAG_FUSS = "Bestätige mit »ok« / »ja« oder einem anderen Bestätigungswort."
_VORSCHLAG_CAP_HINWEIS = (
    "Hinweis: Die ersten %d Termine sind angezeigt. "
    "Sende das Bild erneut, um die weiteren %d zu erfassen.")
# TAB-7 Vergangenheits-Hinweis (Refs #524): N der M Termine liegen vor heute.
_VORSCHLAG_VERGANGENHEITS_HINWEIS = (
    "ℹ️ Hinweis: %d der %d Termine liegen vor heute. "
    "Mit ja eintragen, mit nein verwerfen.")


def _formatiere_datum_kurz(beginn_str):
    """Formatiert das `beginn`-Feld als TT.MM.JJJJ-String für TAB-7 (Datums-
    Anteil)."""
    d = _parse_beginn(beginn_str)
    if d is None:
        return beginn_str or "?"
    return "%02d.%02d.%04d" % (d.day, d.month, d.year)


def _formatiere_uhrzeit_spanne(item):
    """Liefert die Uhrzeit-Spanne `HH:MM–HH:MM` für TAB-7, oder leer."""
    beginn = item.beginn or ""
    ende = item.ende or ""
    m1 = _ISO_DATETIME_RE.match(beginn)
    m2 = _ISO_DATETIME_RE.match(ende)
    if m1 and m2:
        return "%s:%s–%s:%s" % (
            m1.group(4), m1.group(5),
            m2.group(4), m2.group(5))
    if m1:
        return "ab %s:%s Uhr" % (m1.group(4), m1.group(5))
    return ""


def baue_sammel_vorschlag(items, cap_hinweis_n=0, vergangenheits_n=0):
    """Baut den TAB-7-Sammel-Vorschlag als HTML-<pre>-Block. Titel werden
    HTML-escaped, damit `<`/`>`/`&` die `<pre>`-Klammer nicht zerstören
    (TAB-7-Spec).

    `vergangenheits_n` > 0 fügt einen Hinweis-Header ein (TAB-7, Refs #524):
    Anzahl der Items, die vor heute liegen (Familien-Plan-Wiederverwendung).

    Liefert den fertigen HTML-String. EC-27: HTML-Modus aktiviert der
    Aufrufer (telegram.send_message mit parse_mode='HTML').
    """
    gesamt = len(items)
    text = ""
    if vergangenheits_n > 0:
        text = (_VORSCHLAG_VERGANGENHEITS_HINWEIS % (vergangenheits_n, gesamt)) + "\n\n"
    zeilen = []
    for i, item in enumerate(items, start=1):
        datum = _formatiere_datum_kurz(item.beginn)
        titel = html.escape(item.titel or "?")
        zeit = _formatiere_uhrzeit_spanne(item)
        if zeit:
            zeilen.append("%d) %s — %s — %s" % (i, datum, titel, zeit))
        else:
            zeilen.append("%d) %s — %s" % (i, datum, titel))
    text = text + _VORSCHLAG_KOPF + "\n\n<pre>" + "\n".join(zeilen) + "</pre>\n\n" + _VORSCHLAG_FUSS
    if cap_hinweis_n > 0:
        text = text + "\n\n" + (_VORSCHLAG_CAP_HINWEIS % (MAX_ITEMS, cap_hinweis_n))
    return text


# ============================================================
#  TAB-8.1 — Sentinel-Lücken-Rückfrage und Parser
# ============================================================

_LUECKEN_KOPF = (
    "Bei diesen Terminen fehlt mir noch etwas — bitte die [?]-Stellen ersetzen:")

# Sentinel-Form: [?<feldname>?] mit eckigen Klammern (TAB-8.1 — kollidiert nicht
# mit HTML-Modus EC-27).
_SENTINEL_FORMAT = "[?%s?]"
_SENTINEL_RE = re.compile(r"\[\?([a-zA-Z_]+)\?\]")


def baue_luecken_nachricht(items_mit_luecken):
    """TAB-8.1: Sentinel-Nachricht mit allen Lücken auf einmal, nummeriert mit
    der **Original-Position** im Sammel-Vorschlag.

    `items_mit_luecken` — Liste von `(index_1_based, ExtractedTermin)`-Tupeln,
                          die `fehlende_felder` haben.

    Format pro Zeile (kopierbar):
        N) <Datum> — <Titel-oder-[?titel?]> — <ggf. [?ende?]>
    """
    zeilen = []
    for nummer, item in items_mit_luecken:
        # Datums-Anteil: falls beginn parsbar, hübsch formatiert; sonst sentinel.
        datum_anteil = (
            _SENTINEL_FORMAT % "beginn"
            if "beginn" in item.fehlende_felder
            else _formatiere_datum_kurz(item.beginn))
        # Titel.
        titel_anteil = (
            _SENTINEL_FORMAT % "titel"
            if "titel" in item.fehlende_felder
            else (item.titel or "?"))
        # Ende — nur wenn fehlt und zeitgebunden.
        zeile = "%d) %s — %s" % (nummer, datum_anteil, titel_anteil)
        if "ende" in item.fehlende_felder:
            zeile = zeile + " — bis " + (_SENTINEL_FORMAT % "endzeit")
        zeilen.append(zeile)
    return _LUECKEN_KOPF + "\n\n" + "\n".join(zeilen)


def parse_luecken_antwort(text, items_mit_luecken):
    """Deterministischer Parser für die Sentinel-Antwort (TAB-8.1, E-EC-4).

    Liest die Antwort-Zeilen anhand der Nummer und setzt fehlende Felder
    auf den Inhalt der entsprechenden Zeile in der Antwort.

    `items_mit_luecken` ist die gleiche Liste `(nummer, item)` wie bei
    `baue_luecken_nachricht`. Die Funktion **mutiert** die `item`-Objekte:
    erfolgreiche Lücken-Klärungen entfernen das Feld aus `fehlende_felder`.

    Liefert `True` wenn ALLE Lücken geklärt wurden, `False` sonst.
    """
    # Zeilen-Index der Antwort auf die Nummer abbilden.
    antwort_zeilen = {}
    for raw_line in (text or "").splitlines():
        # Nummer am Anfang erkennen ("3)", "3.", "3:").
        m = re.match(r"\s*(\d+)\s*[)\.:]\s*(.*)$", raw_line)
        if m:
            nummer = int(m.group(1))
            antwort_zeilen[nummer] = m.group(2)

    alle_geklaert = True
    for nummer, item in items_mit_luecken:
        antwort = antwort_zeilen.get(nummer)
        if antwort is None:
            alle_geklaert = False
            continue
        # Sentinels in der Antwort dürfen nicht stehen geblieben sein.
        if _SENTINEL_RE.search(antwort):
            alle_geklaert = False
            continue
        # Felder einzeln klären — die Antwort-Zeile parsen wir robust:
        # "—"-separierte Bestandteile zuordnen.
        teile = [p.strip() for p in re.split(r"\s+—\s+|\s+--\s+|\s+-\s+", antwort)]
        teile = [t for t in teile if t]
        if not teile:
            alle_geklaert = False
            continue
        # Heuristik: ist `beginn` fehlend → erstes Teilstück muss Datum sein.
        # Sonst (Datum war im Sentinel-Format mit-echoed) den Datums-Anteil
        # überspringen, falls er als TT.MM.JJJJ/ISO da steht.
        offset = 0
        if "beginn" in item.fehlende_felder:
            datum_str = teile[offset] if offset < len(teile) else ""
            iso = _versuche_datum_zu_iso(datum_str)
            if iso:
                item.beginn = iso
                item.fehlende_felder = [
                    f for f in item.fehlende_felder if f != "beginn"]
                offset += 1
            else:
                alle_geklaert = False
                continue
        elif offset < len(teile) and _versuche_datum_zu_iso(teile[offset]):
            # Aufrufer hat das Datum (Sentinel-Echo) mit-eingetippt — überspringen.
            offset += 1
        if "titel" in item.fehlende_felder:
            if offset < len(teile) and teile[offset]:
                item.titel = teile[offset]
                item.fehlende_felder = [
                    f for f in item.fehlende_felder if f != "titel"]
                offset += 1
            else:
                alle_geklaert = False
                continue
        if "ende" in item.fehlende_felder:
            # `ende` ist die Endzeit; baut den ISO-Datetime aus `beginn`-Datum.
            if offset < len(teile):
                ende_text = teile[offset].replace("bis", "").strip()
                ende_iso = _versuche_endzeit_zu_iso(item.beginn, ende_text)
                if ende_iso:
                    item.ende = ende_iso
                    item.fehlende_felder = [
                        f for f in item.fehlende_felder if f != "ende"]
                else:
                    alle_geklaert = False
                    continue
            else:
                alle_geklaert = False
                continue
        if item.fehlende_felder:
            alle_geklaert = False
    return alle_geklaert


def _versuche_datum_zu_iso(s):
    """Parst ein Datum (TT.MM.JJJJ oder ISO) zu einem ISO-Datum-String."""
    if not s:
        return ""
    s = s.strip()
    # Schon ISO?
    if _ISO_DATE_RE.match(s):
        return s
    # TT.MM.JJJJ
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return ""
        return d.isoformat()
    return ""


def _versuche_endzeit_zu_iso(beginn, ende_text):
    """Baut einen ISO-Datetime für `ende` aus dem `beginn`-Datum und einer
    Endzeit-Eingabe (z. B. "15:30 Uhr", "15:30")."""
    if not beginn:
        return ""
    m_beginn = _ISO_DATETIME_RE.match(beginn)
    if not m_beginn:
        return ""
    m_zeit = re.search(r"(\d{1,2}):(\d{2})", ende_text)
    if not m_zeit:
        return ""
    # Offset aus dem beginn übernehmen.
    offset_match = re.search(r"([+-]\d{2}:\d{2}|Z)$", beginn)
    offset = offset_match.group(1) if offset_match else ""
    return "%s-%s-%sT%s:%s:00%s" % (
        m_beginn.group(1), m_beginn.group(2), m_beginn.group(3),
        m_zeit.group(1).zfill(2), m_zeit.group(2),
        offset)


# ============================================================
#  TAB-10 / TAB-11 — hart-codierte Antworten (Spec normiert das Soll)
# ============================================================

_ANTWORT_ABGELEHNT = (
    "Termine aus Bild geht nur für Mitglieder der Familien-Gruppe.")
_ANTWORT_PROVIDER_FEHLER = (
    "Der KI-Anbieter konnte das Bild gerade nicht lesen — bitte gleich "
    "nochmal versuchen oder die Termine einzeln tippen.")
_ANTWORT_UNKLAR_LEER = (
    "Aus dem Bild konnte ich keine Termine ablesen — bitte gleich nochmal "
    "versuchen oder einzeln tippen.")
_ANTWORT_UNKLAR_LUECKEN = (
    "Ich konnte die Lücken auch nach zwei Versuchen nicht klären — bitte "
    "die Termine einzeln eintragen.")
_ANTWORT_VERWORFEN = (
    "Ok — keine Termine eingetragen. Wenn du es erneut versuchen möchtest, "
    "schick das Bild noch einmal mit einem Signalwort.")
_ANTWORT_NICHT_ERREICHBAR = (
    "Plan-Buddy nicht erreichbar — kein Termin eingetragen, bitte gleich "
    "nochmal probieren.")
_ANTWORT_UNBEKANNT = (
    "Verbindung zum Plan-Buddy war kurz weg — ich weiß nicht sicher, welche "
    "der Termine eingetragen wurden. Bitte einmal kurz im Wochenplan "
    "nachschauen; doppelte Einträge fängt der Plan-Buddy ab.")

# TAB-11 N-von-M-Quittung.
_QUITTUNG_KOPF = "Eingetragen ✅: %d von %d Terminen."


# ============================================================
#  TAB-1 — Haupt-Funktion
# ============================================================

def termine_aus_bild(*,
                     tg,
                     private_chat_id,
                     from_user_id,
                     family_group_chat_id,
                     image_bytes,
                     image_media_type,
                     caption,
                     multimodal_provider,
                     plan_client,
                     is_member_fn,
                     next_message: Callable,
                     typing_fn: Callable[[], None] | None = None,
                     heute=None):
    """Termine aus Bild — aufrufbare Funktion (TAB-1).

    Siehe Modul-Docstring für Vertrag und Ergebnis-Signale.

    `heute` ist für Tests injizierbar (Plausi-Fenster TAB-6).
    """
    # TAB-1: ohne Privatchat keine Konversation.
    if private_chat_id is None:
        logger.warning("termine_aus_bild: private_chat_id fehlt — Abbruch")
        return SIGNAL_ABGELEHNT

    # TAB-2: Live-Berechtigung VOR jedem Anbieter-Aufruf — das Bild geht nicht
    # raus, wenn der Aufrufer nicht Familien-Mitglied ist.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "termine_aus_bild: User %s ist kein Familienmitglied — abgelehnt",
            from_user_id)
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_ABGELEHNT)
        return SIGNAL_ABGELEHNT

    # TAB-5: multimodale Extraktion mit EC-28-Renewal des Typing-Indikators —
    # der Aufruf kann mehrere Sekunden dauern.
    fire_typing(typing_fn)
    try:
        with TypingRenewal(typing_fn):
            extrahiert = multimodal_provider.extract_termine(
                image_bytes=image_bytes,
                image_media_type=image_media_type,
                caption=caption or "")
    except MultimodalError as e:
        logger.warning("termine_aus_bild: TAB-5 provider_fehler — %s", e)
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_PROVIDER_FEHLER)
        return SIGNAL_PROVIDER_FEHLER

    # TAB-6: Plausi-Filter + Schema-Vollständigkeit + Cap 30 (Risk 7).
    gefiltert, _verworfen, cap_hinweis_n, vergangenheits_n = validiere_und_filtere(
        extrahiert, heute=heute)
    if not gefiltert:
        # Leere Liste nach Filter → „unklar" (TAB-6).
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_UNKLAR_LEER)
        return SIGNAL_UNKLAR

    # TAB-8: Lücken-Sammel-Rückfrage, max 2 Runden (TAB-8.3).
    if any(item.fehlende_felder for item in gefiltert):
        result = _luecken_runde(gefiltert, tg, private_chat_id, next_message,
                                typing_fn)
        if result is not None:
            return result  # SIGNAL_UNKLAR oder SIGNAL_ABGEBROCHEN

    # TAB-7: Sammel-Vorschlag im HTML-<pre>-Block.
    vorschlag = baue_sammel_vorschlag(
        gefiltert, cap_hinweis_n=cap_hinweis_n, vergangenheits_n=vergangenheits_n)
    fire_typing(typing_fn)
    _send(tg, private_chat_id, vorschlag, parse_mode="HTML")

    # TAB-7: auf Bestätigung warten.
    msg = next_message()
    if msg is None:
        return SIGNAL_ABGEBROCHEN
    if not confirm.is_confirmation(_get_text(msg)):
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_VERWORFEN)
        return SIGNAL_VERWORFEN

    # TAB-9: Bulk-PUT über PLAN-33. Eine request_id je Session (PLAN-33.5).
    request_id = str(uuid.uuid4())
    body_items = [_bau_plan22_body(item) for item in gefiltert]

    fire_typing(typing_fn)
    try:
        with TypingRenewal(typing_fn):
            antwort = plan_client.put_termine_bulk(request_id, body_items)
    except PlanBulkNotReached as e:
        logger.warning("termine_aus_bild: TAB-10 nicht_erreichbar — %s", e)
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_NICHT_ERREICHBAR)
        return SIGNAL_NICHT_ERREICHBAR
    except PlanBulkUnknown as e:
        logger.warning("termine_aus_bild: TAB-10 unbekannt — %s", e)
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_UNBEKANNT)
        return SIGNAL_UNBEKANNT
    except PlanClientError as e:
        # 4xx oder Form-Fehler — als „nicht_erreichbar" werten (V1, EC-7).
        logger.warning("termine_aus_bild: TAB-10 logischer Fehler — %s", e)
        fire_typing(typing_fn)
        _send(tg, private_chat_id, _ANTWORT_NICHT_ERREICHBAR)
        return SIGNAL_NICHT_ERREICHBAR

    # TAB-11: deterministische Erfolgs-Quittung im Privatchat.
    geschrieben = int(antwort.get("geschrieben", 0))
    gesamt = int(antwort.get("gesamt", len(body_items)))
    results = antwort.get("results") or []
    quittung = _baue_quittung(geschrieben, gesamt, results)
    fire_typing(typing_fn)
    _send(tg, private_chat_id, quittung)
    logger.info(
        "termine_aus_bild: TAB-9 Bulk-PUT erfolgreich (geschrieben=%d, gesamt=%d, request_id=%s)",
        geschrieben, gesamt, request_id)
    return SIGNAL_EINGETRAGEN


# ============================================================
#  TAB-8 — Lücken-Runden (max 2)
# ============================================================

def _luecken_runde(gefiltert, tg, private_chat_id, next_message, typing_fn):
    """TAB-8.1/TAB-8.3: führt bis zu 2 Sentinel-Rückfrage-Runden. Liefert
    `None` wenn alle Lücken geklärt sind (weiter zum Sammel-Vorschlag), oder
    ein Ergebnis-Signal (SIGNAL_UNKLAR / SIGNAL_ABGEBROCHEN), wenn nicht.
    """
    for runde in (1, 2):
        items_mit_luecken = [
            (i + 1, item) for i, item in enumerate(gefiltert)
            if item.fehlende_felder
        ]
        if not items_mit_luecken:
            return None  # alle geklärt — weiter

        fire_typing(typing_fn)
        _send(tg, private_chat_id, baue_luecken_nachricht(items_mit_luecken))
        msg = next_message()
        if msg is None:
            return SIGNAL_ABGEBROCHEN
        # Parser mutiert die items.
        parse_luecken_antwort(_get_text(msg), items_mit_luecken)
        if not any(item.fehlende_felder for item in gefiltert):
            return None  # nach dieser Runde alles geklärt
        # Sonst nächste Runde (sofern noch Budget).
        if runde == 2:
            # Zweite Runde lieferte keine vollständige Klärung → TAB-8.3.
            logger.info("termine_aus_bild: TAB-8.3 — 2 Runden ohne Klärung")
            fire_typing(typing_fn)
            _send(tg, private_chat_id, _ANTWORT_UNKLAR_LUECKEN)
            return SIGNAL_UNKLAR
    return None


# ============================================================
#  Hilfsfunktionen
# ============================================================

def _bau_plan22_body(item):
    """Baut den PLAN-22-PUT-Body aus einem `ExtractedTermin` (TAB-9)."""
    body = {"titel": item.titel, "beginn": item.beginn}
    if (item.ende or "").strip():
        body["ende"] = item.ende
    return body


def _baue_quittung(geschrieben, gesamt, results):
    """TAB-11: N-von-M-Quittung + Fehler-Liste mit error_code bei Teil-
    Misserfolg."""
    if geschrieben == gesamt:
        return _QUITTUNG_KOPF % (geschrieben, gesamt)
    # Teil-Misserfolg: gescheiterte Items aufzählen mit Nummer + error_code.
    fehler_zeilen = []
    for i, r in enumerate(results, start=1):
        if isinstance(r, dict) and r.get("ok") is False:
            code = r.get("error_code") or r.get("error") or "?"
            fehler_zeilen.append("Nummer %d (%s)" % (i, code))
    if fehler_zeilen:
        return _QUITTUNG_KOPF % (geschrieben, gesamt) + "\n" + ", ".join(fehler_zeilen)
    return _QUITTUNG_KOPF % (geschrieben, gesamt)


def _get_text(msg):
    """Liest den Text aus einem TabInput oder String."""
    if hasattr(msg, "text"):
        return (msg.text or "").strip()
    return (msg or "").strip()


def _send(tg, chat_id, text, parse_mode=None):
    """Sendet eine Nachricht; Telegram-Fehler werden geloggt, brechen aber
    die Funktion nicht ab (analog termin_eintragen._send)."""
    try:
        if parse_mode is not None:
            tg.send_message(chat_id, text, parse_mode=parse_mode)
        else:
            tg.send_message(chat_id, text)
    except TelegramError as e:
        logger.warning("termine_aus_bild: Senden an %s fehlgeschlagen: %s",
                       chat_id, e)
    except TypeError:
        # Backward-Compat: alte tg.send_message ohne parse_mode-Argument
        # (Test-Doppelungen). Wir fallen einfach auf den 2-arg-Aufruf zurück.
        try:
            tg.send_message(chat_id, text)
        except TelegramError as e:
            logger.warning("termine_aus_bild: Senden an %s fehlgeschlagen: %s",
                           chat_id, e)
