"""Kalender verbinden — siehe specs/platform/kalender-verbinden.md
(KAV-1…KAV-10, Refs #57).

»Kalender verbinden« ist eine aufrufbare, **trigger-agnostische** Funktion
(E-KAV-1, analog `familie_anlegen.familie_anlegen` E-FAA-1 und
`geraet_anlegen.geraet_anlegen` E-GAA-1). Aufgerufen, führt sie ein
Familien­mitglied im Telegram-Privatchat durch den Google-OAuth-Login, fängt
den Authorization-Code via Loopback-Redirect (`http://localhost:1`) ab,
tauscht ihn beim Google-Token-Endpunkt gegen ein Refresh- und Access-Token
und legt das Refresh-Token unter dem PLAN-16-Schlüssel im
Zugangsdaten-Speicher ab.

Die Funktion kennt ihren Aufrufer nicht. Sie nimmt nur die für das Verbinden
nötigen Dinge entgegen: den Telegram-Kanal, den Privatchat (Chat-ID +
User-ID), die ID der gebundenen Familien-Gruppe (für die Live-Prüfung der
Mitgliedschaft, KAV-2 analog FAA-2), den Zugangsdaten-Speicher (Lese-/
Schreib-Schnittstelle nach `zugangsdaten.md` ZD-5) und eine
`next_message()`-Funktion, die die nächste eingehende Privatchat-Nachricht
liefert (analog FAA-9, siehe E-KAV-2). Letzteres macht den Code-Empfang
synchron und testbar.

Code-Vorbild ist der `FaaSession`-/`familie_anlegen`-Stil
(`familie_anlegen.py`). Querverweis-Kommentar an die FAA-Session ist hier
KAV-spezifisch dokumentiert; ein gemeinsamer Plattform-Baustein für die
Privatchat-Session entsteht erst beim **dritten** Vorkommen des Musters
(E-KAV-2 — CLAUDE.md §6 „dieselbe Logik zweimal").
"""

import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import authz
from telegram import TelegramError

from skills.typing_indicator import fire_typing

# ============================================================
#  Konstanten — Schlüssel-Namen (KAV-7) und Endpunkte
# ============================================================

# PLAN-16 / KAV-7: Schlüssel-Konvention im Zugangsdaten-Speicher. Die Namen
# folgen der heute in `plan/kalender.py` etablierten Konvention
# (`plan-google-oauth-*`); Plan-Buddy liest unter genau diesen Namen. Eine
# Abweichung würde Plan-Buddy beim Token-Tausch ins Leere greifen lassen
# (CLAUDE.md §6, eine Wahrheit pro Fakt).
ZD_NAME_OAUTH_CLIENT = "plan-google-oauth-client"
ZD_NAME_OAUTH_TOKEN = "plan-google-oauth-refresh-token"
ZD_NAME_ACCESS_TOKEN = "kav-access-token"
ZD_NAME_ACCESS_TOKEN_EXPIRES_AT = "kav-access-token-expires-at"
ZD_NAME_ACCOUNT_EMAIL = "kav-account-email"

# KAV-5: OAuth-Endpunkte. Loopback-Redirect mit Port 1 — Port 1 antwortet
# nie, der Browser zeigt eine Verbindungsfehler-Seite, aber die Adressleiste
# enthält den Code. Kein OOB-Flow.
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
# KAV-X: calendarList-Endpunkt — Liste der Kalender des Accounts, wird mit
# dem frischen Access-Token aus KAV-7 abgerufen.
_GOOGLE_CALENDAR_LIST_URL = (
    "https://www.googleapis.com/calendar/v3/users/me/calendarList")
_REDIRECT_URI = "http://localhost:1"
# KAV-5: zwei Scopes, space-separiert. `calendar.events` deckt PLAN-17/PLAN-18
# (Termine lesen+schreiben) ab; `calendar.readonly` ist zusätzlich nötig, weil
# `calendar.events` allein an `calendarList.list` mit HTTP 403 abgewiesen wird
# (verifiziert auf Pi 2026-05-26). Beide brauchen wir für die Kalender-Auswahl
# (KAV-X).
_OAUTH_SCOPE = ("https://www.googleapis.com/auth/calendar.events "
                "https://www.googleapis.com/auth/calendar.readonly")

# KAV-6: `SESSION_TIMEOUT_SECONDS` ist hier nur als Re-export für Aufrufer
# sichtbar — die effektive Quelle ist `private_chat_session.SESSION_TIMEOUT_SECONDS`
# (EC-20, Refs #130: Konsolidierung aus FAA/GAA/KAV).

# CLIENT-2 (#1784): HTTP-Timeout für den Plan-Buddy-Call (PLAN-32/APP-3). Das
# ist ein Loopback-Aufruf an eine XBuddy-Komponente — genau der Fall, für den
# CLIENT-2 2,0 s vorschreibt (Normalfall sub-ms). Er lief bisher OHNE Timeout,
# und `urlopen` ohne Timeout blockiert unbegrenzt (`socket.getdefaulttimeout()`
# ist None) — in einem Worker-Thread, der die `PrivateChatSession` hält. Die
# Google-Calls oben tragen ihre eigenen, größeren Budgets (8/12 s): externes
# Netz, nicht Loopback.
PLAN_HTTP_TIMEOUT_SECONDS = 2.0


# ============================================================
#  Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail
#  (KAV-4 normiert das Soll, nicht den Wortlaut)
# ============================================================

NOT_AUTHORIZED = (
    "Kalender verbinden geht nur für Mitglieder der Familien-Gruppe. "
    "Wende dich bitte an jemanden aus der Gruppe.")

OAUTH_CLIENT_MISSING = (
    "Ich kann den Google-Login gerade nicht starten — die XBuddy-OAuth-App "
    "ist auf dieser Instanz noch nicht eingerichtet. Bitte sag jemandem aus "
    "der Familie Bescheid, der die Instanz administriert.")

# KAV-4: Aufklärungstext — deckt drei Stolpersteine ab:
# 0) **Bitte am Laptop/PC verbinden, nicht am Handy.** Mobile Browser zeigen
#    die `http://localhost:1/?code=…`-URL nach dem Verbindungsfehler nicht
#    zuverlässig in der Adressleiste; vom Desktop ist sie kopierbar.
#    Folge-Ticket #133 (Web-Forwarder für mobilen Pfad).
# 1) „Diese App ist nicht bestätigt" (unverified, vgl. E-KAV-3) →
#    *Erweitert → Weiter zu XBuddy*.
# 2) Browser zeigt nach dem Login eine **Verbindungsfehler-Seite** — die
#    Adressleiste enthält den Code, das ist beabsichtigt.
AUFKLAERUNG_TEXT = (
    "Ich richte den Google-Kalender für die Familie ein. Bitte verbinde "
    "den Kalender **am Laptop oder PC, nicht am Handy** — am Ende zeigt "
    "der Browser eine Fehler-Seite mit der wichtigen URL in der "
    "Adressleiste, und auf dem Handy ist diese URL dann oft nicht mehr "
    "zu sehen. Vom Laptop/PC kannst du sie einfach kopieren. (Der mobile "
    "Pfad ist in Arbeit.)\n\n"
    "Zwei weitere Dinge vorab:\n\n"
    "1) Google zeigt dir während des Logins einen Warnscreen — »Diese App "
    "ist nicht bestätigt«. Das ist erwartet: die XBuddy-OAuth-App läuft in "
    "Produktion, ist aber noch nicht von Google verifiziert. Klick auf "
    "»Erweitert« und dann auf »Weiter zu XBuddy« (oder ähnlich).\n\n"
    "2) Nach dem Login leitet Google dich auf »http://localhost:1/?code=…« "
    "weiter und der Browser zeigt eine Verbindungsfehler-Seite "
    "(»Diese Website ist nicht erreichbar« o. ä.). Das ist normal und so "
    "beabsichtigt — die Adressleiste enthält den Anmelde-Code.\n\n"
    "Bitte kopier die **komplette URL aus der Adressleiste** und schick "
    "sie mir hier im Privatchat. (Oder nur den Code-Wert aus der URL, wenn "
    "du ihn schon herausgeschnitten hast.)\n\n"
    "Gleich kommt der Login-Link.")

LOGIN_LINK_PROMPT = "Hier ist der Login-Link:\n%s"

CODE_REMINDER = (
    "Das sah noch nicht nach der URL oder dem Code aus. Bitte schick mir "
    "die **komplette URL aus dem Browser** (sie beginnt mit "
    "»http://localhost:1/?code=…«) oder nur den **Code-Wert**.")

TOKEN_EXCHANGE_FAILED = (
    "Hm, der Code-Tausch mit Google hat nicht geklappt. Häufige Gründe: "
    "der Code ist abgelaufen (er gilt nur kurz) oder das Netz war kurz "
    "weg. Bitte ruf »Kalender verbinden« noch einmal auf.")

# KAV-Y / KAV-8: Bestätigung nennt den gewählten Kalender + Account-E-Mail
# (soweit ableitbar). Plan-Buddy übernimmt die neue `kalender_id` automatisch:
# der `kalender_verbinden_task` deklariert seinen Plan-Buddy-`ReloadHook`, das
# Skill-Framework triggert ihn nach erfolgreichem `execute()` (EC-21, #140).
# Schlägt der Hook fehl, hängt das Framework eine Warnung an die Quittung —
# darum nennen wir den manuellen Restart hier nicht mehr (Refs #154).
BESTAETIGT_MIT_EMAIL = (
    "Geschafft — der Google-Kalender »%(kalender)s« ist verbunden (%(email)s). "
    "Der Plan-Buddy hat die Änderung übernommen — neue Termine sind im "
    "Wochenplan sichtbar. 🎉")

BESTAETIGT_OHNE_EMAIL = (
    "Geschafft — der Google-Kalender »%(kalender)s« ist verbunden. Der "
    "Plan-Buddy hat die Änderung übernommen — neue Termine sind im "
    "Wochenplan sichtbar. 🎉")

# KAV-X: nummerierte Kalender-Liste — Bot postet sie nach erfolgreichem
# Token-Tausch. `%s` füllt die nummerierte Liste, eine Zeile je Kalender.
KALENDER_AUSWAHL_PROMPT = (
    "Welchen Kalender soll der Plan-Buddy benutzen? Hier ist die Liste "
    "der Kalender deines Google-Accounts (nur die, in die der Plan-Buddy "
    "auch schreiben kann):\n\n%s\n\n"
    "Schick mir bitte einfach die Nummer (1–%d).")

KALENDER_AUSWAHL_REMINDER = (
    "Das war keine gültige Nummer. Bitte schick mir nur die Nummer des "
    "Kalenders aus der Liste oben (1–%d).")

# KAV-X: Kalender-Auswahl gescheitert (calendarList-Abfrage fehlgeschlagen
# oder leere Liste). Tokens sind dennoch gespeichert (KAV-7 ist nicht
# rückgängig zu machen) — Ergebnis verbunden_ohne_kalender.
KALENDER_LIST_FETCH_FAILED = (
    "Die Tokens sind gespeichert, aber ich konnte die Liste deiner Kalender "
    "nicht abrufen. Bitte ruf »Kalender verbinden« noch einmal auf — die "
    "Tokens bleiben gültig, der Auswahl-Schritt fehlt noch.")

KALENDER_LIST_EMPTY = (
    "Die Tokens sind gespeichert, aber ich habe in deinem Google-Konto "
    "keinen Kalender mit Schreibrecht gefunden. Bitte prüf in Google "
    "Kalender, ob ein Familienkalender existiert (oder leg einen an), und "
    "ruf »Kalender verbinden« dann noch einmal auf.")

# KAV-X: plan.json-Schreibvorgang fehlgeschlagen — Tokens sind gespeichert,
# aber Plan-Buddy wird die alte `kalender_id` weiter lesen.
PLAN_JSON_WRITE_FAILED = (
    "Die Tokens sind gespeichert und die Kalender-Auswahl ist getroffen, "
    "aber ich konnte die Auswahl nicht in die Plan-Konfiguration "
    "schreiben. Bitte sag jemandem aus der Familie Bescheid, der die "
    "Instanz administriert — `plan/plan.json` muss von Hand auf den "
    "gewählten Kalender gesetzt werden.")

ABGEBROCHEN = (
    "Ok — kein Kalender verbunden (Timeout oder du hast abgebrochen). Ruf "
    "»Kalender verbinden« einfach noch einmal auf, wenn du es nochmal "
    "versuchen willst.")

# KAV-X: Abbruch *nach* erfolgreichem Token-Tausch (Timeout in der Kalender-
# Auswahl). Tokens sind gespeichert, aber `plan.json` ist unverändert.
ABGEBROCHEN_NACH_TOKEN = (
    "Ok — die Tokens sind gespeichert, aber du hast die Kalender-Auswahl "
    "nicht abgeschlossen. Ruf »Kalender verbinden« noch einmal auf, wenn "
    "du den Kalender wählen willst.")


# ============================================================
#  Eingabe-Protokoll (analog FaaInput)
# ============================================================

@dataclass
class KavInput:
    """Eine eingehende Privatchat-Nachricht des Aufrufers, KAV-spezifisch
    aufbereitet — schmaler als IncomingMessage (KAV braucht nur den Text)."""
    text: str = ""


# ============================================================
#  Ergebnis-Signal (KAV-1)
# ============================================================

# Ergebnis-Werte (KAV-1).
ERGEBNIS_VERBUNDEN = "verbunden"
ERGEBNIS_ABGEBROCHEN = "abgebrochen"
ERGEBNIS_ABGELEHNT = "abgelehnt"
# KAV-1 / KAV-X: Tokens sind gespeichert (KAV-7), aber der nachgelagerte
# Kalender-Auswahl-Schritt (calendarList-Abfrage, plan.json-Schreibvorgang)
# ist gescheitert oder vom User abgebrochen — Plan-Buddy hat eine gültige
# Token-Paarung, aber `plan.json` `kalender_id` ist nicht aktualisiert.
ERGEBNIS_VERBUNDEN_OHNE_KALENDER = "verbunden_ohne_kalender"


@dataclass
class KalenderVerbindenResult:
    """Ergebnis-Signal an den Aufrufer (KAV-1).

    `ergebnis` ist einer der Werte ERGEBNIS_VERBUNDEN, ERGEBNIS_ABGEBROCHEN,
    ERGEBNIS_ABGELEHNT. `account_email` ist die E-Mail des verbundenen
    Google-Accounts, soweit aus dem Token ableitbar (KAV-1, KAV-8).
    """
    ergebnis: str = ERGEBNIS_ABGEBROCHEN
    account_email: str = ""


# ============================================================
#  Reine Logik-Bausteine (testbar ohne Telegram, ohne Netz)
# ============================================================

def build_auth_url(client_id, state, scope=_OAUTH_SCOPE,
                   redirect_uri=_REDIRECT_URI):
    """Baut die Google-Auth-URL nach KAV-5.

    `client_id` ist die OAuth-Client-ID aus dem Zugangsdaten-Speicher
    (`plan-google-oauth-client`). `state` ist der einmalige Bind-Token
    (Replay-/Verwechslungs-Schutz, TTL 30 min im Prozess-Speicher).

    Liefert die vollständige URL.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return _GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)


def extract_code(message_text):
    """KAV-6: extrahiert den Authorization-Code aus einer Privatchat-Nachricht.

    Akzeptiert zwei Eingabe-Formen (KAV-6):
      * komplette URL mit `?code=…` oder `&code=…` (auch ohne Schema):
        Code wird per URL-Parsing aus dem Query-String geholt.
      * blanker Code-String (kein `code=`-Marker): die Nachricht wird
        getrimmt (Whitespace, Zeilenumbrüche) und direkt verwendet.

    Liefert den Code als String oder `None`, wenn nichts Plausibles im Text
    gefunden wurde (z. B. „hallo?", leere Nachricht).
    """
    if not message_text:
        return None
    text = message_text.strip()
    if not text:
        return None

    # URL-Form: enthält „?code=" oder „&code=" als Marker.
    if "?code=" in text or "&code=" in text:
        # urlparse braucht ein Schema, sonst legt es Query an netloc/path.
        # Der typische Loopback-Redirect kommt mit `http://localhost:1/...`;
        # falls jemand das Schema abgeschnitten hat, ergänzen wir es vorne.
        if "://" not in text:
            text_with_scheme = "http://" + text.lstrip("/")
        else:
            text_with_scheme = text
        try:
            parsed = urllib.parse.urlparse(text_with_scheme)
        except ValueError:
            return None
        query = urllib.parse.parse_qs(parsed.query)
        code_values = query.get("code")
        if code_values and code_values[0].strip():
            return code_values[0].strip()
        return None

    # Blanker Code: Google-Authorization-Codes sind URL-safe Strings (Buchstaben,
    # Zahlen, plus die Marker `-`, `_`, `.`, `/`). Eine Nachricht, die andere
    # Zeichen (Leerzeichen, Satzzeichen wie `!?,;`) enthält, ist eine
    # Gesprächsnachricht — kein Code. Mindestlänge 16 ist ein pragmatischer
    # Anker: heutige Google-Codes sind deutlich länger, Begrüßungen wie
    # „hallo!" deutlich kürzer (Spec: „plausible Code-Form", KAV-6).
    if any(ch in text for ch in " \n\r\t?!,;:\"'()[]{}"):
        return None
    if len(text) < 16:
        return None
    # Akzeptiere nur URL-safe Code-Zeichen.
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                  "0123456789-_./")
    if not all(ch in allowed for ch in text):
        return None
    return text


def exchange_code_for_tokens(code, client_id, client_secret,
                             token_url=_GOOGLE_TOKEN_URL,
                             redirect_uri=_REDIRECT_URI, timeout=12):
    """KAV-7: tauscht den Authorization-Code beim Google-Token-Endpunkt
    gegen ein Refresh- und Access-Token.

    Liefert das geparste Antwort-Dict (mit `access_token`, `refresh_token`,
    `expires_in`, optional `id_token`). Wirft `TokenExchangeError` bei
    HTTP-Fehlern, Netzfehlern oder unvollständigen Antworten — Token werden
    in der Fehler-Meldung nie gespiegelt (ZD-6).
    """
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        token_url, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        # ZD-6: Antwort-Body kann Tokens enthalten — nur Statuscode loggen.
        raise TokenExchangeError(
            "Token-Tausch fehlgeschlagen (HTTP %s)" % e.code)
    except urllib.error.URLError as e:
        raise TokenExchangeError("Token-Tausch fehlgeschlagen (Netz): %s" % e.reason)
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        raise TokenExchangeError("Token-Tausch lieferte keine JSON-Antwort")
    if not isinstance(parsed, dict):
        raise TokenExchangeError("Token-Tausch lieferte keine JSON-Antwort")
    if "access_token" not in parsed or "refresh_token" not in parsed:
        # KAV-7: ohne Refresh-Token ist die Verbindung nutzlos — Plan-Buddy
        # zieht Access-Token aus dem Refresh-Token nach.
        raise TokenExchangeError(
            "Token-Antwort unvollständig (refresh_token oder access_token fehlt)")
    return parsed


class TokenExchangeError(Exception):
    """Der Code-Tausch beim Google-Token-Endpunkt ist gescheitert (KAV-7).

    Token-Werte werden nie in die Fehler-Meldung kopiert (ZD-6).
    """


def fetch_account_email(access_token, userinfo_url=_GOOGLE_USERINFO_URL,
                        timeout=8):
    """Holt die Account-E-Mail vom Google-`userinfo`-Endpunkt (KAV-8).

    Liefert die E-Mail als String oder `""`, wenn sie nicht ermittelbar
    ist — etwa weil der `userinfo`-Endpunkt fehlschlägt oder der Account
    keine E-Mail veröffentlicht. KAV-8 erlaubt eine Bestätigung **ohne**
    E-Mail-Anzeige, wenn sie nicht ableitbar ist — wir behandeln einen
    Fehler also nicht als Verbindungs-Fehler.
    """
    req = urllib.request.Request(
        userinfo_url, method="GET",
        headers={"Authorization": "Bearer " + access_token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        # ZD-6: Bearer-Token niemals ins Log spiegeln — nur die Tatsache des
        # Fehlschlags.
        logging.info("kalender_verbinden: userinfo-Endpoint nicht erreichbar (%s) "
                     "— Bestätigung ohne E-Mail (KAV-8)", e)
        return ""
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    email = parsed.get("email")
    return str(email) if email else ""


def fetch_calendar_list(access_token, list_url=_GOOGLE_CALENDAR_LIST_URL,
                        timeout=12):
    """KAV-X: Liste der Kalender des Accounts vom Google-`calendarList`-
    Endpunkt holen, gefiltert auf für Plan-Buddy nutzbare Einträge.

    Filter: alle Kalender mit `accessRole` ∈ {`owner`, `writer`} (Plan-Buddy
    braucht Schreibrecht, PLAN-18) plus jeder Kalender mit `primary=true`
    (auch read-only — der Primary-Kalender ist der übliche Default-Fall).
    Reader-only Kalender ohne `primary`-Flag werden bewusst **ausgeblendet**:
    Plan-Buddy könnte in sie nicht schreiben, ein „verbunden, aber sileht
    fehl beim ersten Schreibversuch" wäre eine stille Falle für den User.

    Liefert eine Liste von Dicts mit den für die Anzeige nötigen Feldern:
    `{"id": "...", "summary": "...", "accessRole": "...", "primary": bool}`.
    Wirft `CalendarListFetchError` bei HTTP-/Netzfehlern oder Antworten,
    die kein JSON-Objekt mit `items` sind. Bearer-Token wird nie in den
    Fehler-Text gespiegelt (ZD-6).
    """
    req = urllib.request.Request(
        list_url, method="GET",
        headers={"Authorization": "Bearer " + access_token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise CalendarListFetchError(
            "calendarList.list fehlgeschlagen (HTTP %s)" % e.code)
    except urllib.error.URLError as e:
        raise CalendarListFetchError(
            "calendarList.list fehlgeschlagen (Netz): %s" % e.reason)
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        raise CalendarListFetchError("calendarList.list lieferte keine JSON-Antwort")
    if not isinstance(parsed, dict):
        raise CalendarListFetchError("calendarList.list lieferte keine JSON-Antwort")
    items = parsed.get("items") or []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        access_role = item.get("accessRole") or ""
        is_primary = bool(item.get("primary"))
        # Filter: writable OR primary.
        if access_role not in ("owner", "writer") and not is_primary:
            continue
        cal_id = item.get("id")
        summary = item.get("summary") or item.get("summaryOverride") or cal_id
        if not cal_id:
            continue
        result.append({
            "id": cal_id,
            "summary": str(summary),
            "accessRole": access_role,
            "primary": is_primary,
        })
    return result


class CalendarListFetchError(Exception):
    """Die `calendarList.list`-Abfrage ist gescheitert (KAV-X).

    Bearer-Token werden nie in die Fehler-Meldung kopiert (ZD-6).
    """


def format_calendar_list(calendars):
    """KAV-X: nummerierte Anzeige-Form der Kalender-Liste — eine Zeile je
    Kalender, mit Name + Rolle + ggf. „Primary"-Markierung.

    Liefert einen einzelnen String mit Zeilen `"1. <Name> (Rolle…)"`. Diese
    Funktion ist rein darstellend; sie schreibt nichts und liest nichts.
    """
    lines = []
    for index, cal in enumerate(calendars, start=1):
        role = cal.get("accessRole") or "reader"
        primary = cal.get("primary")
        markers = [role]
        if primary:
            markers.append("Primary")
        lines.append("%d. %s (%s)" % (index, cal["summary"], ", ".join(markers)))
    return "\n".join(lines)


def parse_selection(message_text, count):
    """KAV-X: parst die Antwort des Users als Ganzzahl im Bereich 1..count.

    Extrahiert die **erste Ziffernfolge** aus der Antwort. Damit gelten als
    gültig: »1«, »1. bitte«, »die 3«, »nimm 2«, »2)«, »3.« — alles, was den
    User in der Live-Anwendung verlangsamen würde. Wortzahlen (»eins«,
    »zwei«) bleiben in V1 außen vor (Refs #155). Eingaben ganz ohne Ziffer
    oder mit einer Ziffer außerhalb von 1..count liefern `None`.
    """
    if not message_text:
        return None
    match = re.search(r"\d+", message_text)
    if match is None:
        return None
    try:
        number = int(match.group(0))
    except ValueError:
        return None
    if number < 1 or number > count:
        return None
    return number - 1


class PlanJsonWriteError(Exception):
    """Plan-Buddy-`admin/kalender`-Schreibvorgang ist gescheitert (KAV-X, PLAN-32)."""


def store_tokens_in_zd(zd, refresh_token, access_token, expires_in,
                       account_email, clock=None):
    """KAV-7: legt die Token-Werte über die Schreib-Schnittstelle des
    Zugangsdaten-Speichers ab (`zugangsdaten.md` ZD-5).

    Schreibt die vier KAV-7-Schlüssel:
      * `plan-google-oauth-refresh-token` als `{"refresh_token": "..."}`
        — exakt das Format, das `plan/kalender.py::_access_token` heute
        liest (PLAN-16-load-bearing).
      * `kav-access-token` — Klartext.
      * `kav-access-token-expires-at` — ISO-8601 UTC, berechnet aus
        `expires_in` Sekunden.
      * `kav-account-email` — nur **wenn** sie tatsächlich vorliegt
        (KAV-8 / KAV-9: ein leerer E-Mail-Wert darf einen vorhandenen
        Wert aus einer früheren erfolgreichen Verbindung nicht
        überschreiben).

    `clock` ist eine optionale `callable()`, die die aktuelle
    `datetime` (timezone-aware UTC) liefert — für deterministische Tests.
    """
    if clock is None:
        clock = lambda: datetime.now(UTC)  # noqa: E731

    expires_at = clock() + timedelta(seconds=max(0, int(expires_in)))

    # Reihenfolge: erst das Refresh-Token (das ist die für Plan-Buddy load-
    # bearing Wahrheit), dann die Bot-internen Hilfs-Werte.
    zd.set(ZD_NAME_OAUTH_TOKEN, {"refresh_token": refresh_token})
    zd.set(ZD_NAME_ACCESS_TOKEN, access_token)
    zd.set(ZD_NAME_ACCESS_TOKEN_EXPIRES_AT, expires_at.isoformat())
    if account_email:
        zd.set(ZD_NAME_ACCOUNT_EMAIL, account_email)


# ============================================================
#  Hilfe für die State-Verwaltung (KAV-5, Prozess-Speicher)
# ============================================================

def _new_state():
    """Erzeugt einen einmaligen URL-sicheren State-Token (KAV-5).

    State ist ein zufälliger Marker, der Login-Versuch und Code-Rückkehr
    verklammert (Eindeutigkeit gegen Verwechslung paralleler Sessions
    desselben Bots). Die Bindung an User/Privatchat trägt implizit die
    Privatchat-Session-Mechanik (analog FAA-12); eine serverseitige
    Tupel-Tabelle ist nicht nötig.
    """
    return secrets.token_urlsafe(24)


def _load_oauth_client(zd):
    """Liest die OAuth-Client-Konfiguration aus dem Zugangsdaten-Speicher
    und löst die Schachtelung `{"installed": {...}}` / `{"web": {...}}` auf
    (KAV-7, analog `plan/kalender.py`).

    Liefert `(client_id, client_secret)` oder `None`, wenn der Eintrag
    fehlt oder unvollständig ist.
    """
    client = zd.get(ZD_NAME_OAUTH_CLIENT)
    if client is None:
        return None
    if isinstance(client, dict):
        inner = client.get("installed") or client.get("web") or client
    else:
        return None
    try:
        client_id = inner["client_id"]
        client_secret = inner["client_secret"]
    except (KeyError, TypeError):
        return None
    if not client_id or not client_secret:
        return None
    return (client_id, client_secret)


# ============================================================
#  Die Funktion (KAV-1)
# ============================================================

def kalender_verbinden(tg, chat_id, user_id, family_group_chat_id,
                      zd, next_message, clock=None,
                      exchange=None, fetch_email=None,
                      fetch_calendars=None, write_plan_json=None,
                      typing_fn: Callable[[], None] | None = None,
                      plan_origin_url=None):
    """Verbindet den Familien-Google-Kalender über den Privatchat (KAV-1).

    `tg`                    — Telegram-Kanal (mit `send_message`,
                              `get_chat_member`).
    `chat_id`               — Privatchat des Aufrufers (KAV-3).
    `user_id`               — Telegram-User-ID des Aufrufers (KAV-2).
    `family_group_chat_id`  — ID der gebundenen Familien-Gruppe (KAV-2 /
                              FAA-2, EC-2 Live-Berechtigung).
    `zd`                    — Zugangsdaten-Speicher (`zugangsdaten.md` ZD-5,
                              `get`/`set` analog FAA-Registry).
    `next_message`          — Callable, das den nächsten `KavInput` aus dem
                              Privatchat liefert. Liefert `None` → die
                              Funktion gilt als abgebrochen (KAV-6 Timeout).
    `plan_origin_url`       — KAV-X / PLAN-32: Origin des Plan-Buddys
                              (z. B. `http://127.0.0.1:5020`). Ist er gesetzt,
                              schreibt die Funktion die `kalender_id` über
                              `PUT /api/v1/plan/admin/kalender` (APP-3).
                              Ist er `None` → Kalender-Auswahl-Schritt übersprungen.
    `clock`/`exchange`/`fetch_email`/`fetch_calendars`/`write_plan_json` —
                              Test-Naht: Standardwerte sprechen das echte Netz;
                              Tests reichen Doppelungen herein.
    `typing_fn`             — Optionaler Callable ohne Argumente; wird vor jeder
                              send_message-Phase aufgerufen (EC-25: Typing-Indikator,
                              Best-Effort, Fehler werden geschluckt). Default None →
                              No-op (Backward-Compat). Vgl. skills/typing_indicator.py.

    Liefert ein `KalenderVerbindenResult`. Schreibt über `zd.set(...)`
    (ZD-5) und — bei erfolgreicher Kalender-Auswahl — die `kalender_id` via
    HTTP PUT an den Plan-Buddy (PLAN-32, APP-3).
    """
    if exchange is None:
        exchange = exchange_code_for_tokens
    if fetch_email is None:
        fetch_email = fetch_account_email
    if fetch_calendars is None:
        fetch_calendars = fetch_calendar_list
    if write_plan_json is None and plan_origin_url is not None:
        # PLAN-32 / APP-3: Plan-Buddy ist Eigentümer — KAV schreibt via HTTP.
        _kalender_endpoint = (
            plan_origin_url.rstrip("/") + "/api/v1/plan/admin/kalender")

        def write_plan_json(kalender_id):
            body = json.dumps({"kalender_id": kalender_id}).encode("utf-8")
            req = urllib.request.Request(
                _kalender_endpoint,
                data=body,
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(
                        req, timeout=PLAN_HTTP_TIMEOUT_SECONDS) as resp:
                    if resp.status != 200:
                        raise PlanJsonWriteError(
                            "Plan-Buddy admin/kalender antwortete HTTP %d"
                            % resp.status)
            except urllib.error.HTTPError as e:
                raise PlanJsonWriteError(
                    "Plan-Buddy admin/kalender HTTP %d: %s" % (e.code, e))
            except urllib.error.URLError as e:
                raise PlanJsonWriteError(
                    "Plan-Buddy admin/kalender nicht erreichbar: %s" % e)
            except TimeoutError as e:
                # #1784: ein Read-Timeout kommt NICHT als `URLError` heraus
                # (`socket.timeout` ist `TimeoutError`, kein `URLError`) — ohne
                # diesen Zweig würde er als roher Stacktrace aus dem
                # Worker-Thread fallen statt als KAV-Fehlermeldung im Chat.
                raise PlanJsonWriteError(
                    "Plan-Buddy admin/kalender antwortete nicht innerhalb von "
                    "%.1fs" % PLAN_HTTP_TIMEOUT_SECONDS) from e

    # KAV-2: Live-Berechtigung. Die Prüfung liegt **bei der Funktion**
    # (nicht beim Aufrufer), damit die Trigger-Agnostik erhalten bleibt.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("kalender_verbinden: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
        fire_typing(typing_fn)
        _send(tg, chat_id, NOT_AUTHORIZED)
        return KalenderVerbindenResult(ergebnis=ERGEBNIS_ABGELEHNT)

    # KAV-7: OAuth-Client muss im Zugangsdaten-Speicher liegen — er wird
    # **nicht** durch diese Funktion geschrieben (eingerichtet beim Pi-
    # Deploy, gemeinsame XBuddy-OAuth-App, E-KAV-4). Fehlt er, klare
    # Fehler-Antwort an den Aufrufer.
    client_pair = _load_oauth_client(zd)
    if client_pair is None:
        logging.warning(
            "kalender_verbinden: OAuth-Client '%s' fehlt oder ist unvollständig "
            "— Verbindung kann nicht starten (Pi-Deploy-Vorbedingung).",
            ZD_NAME_OAUTH_CLIENT)
        # Setup-Lücke (ZD-Eintrag `plan-google-oauth-client` fehlt) ist hier ein
        # Sonderfall von ABGEBROCHEN — die Spec (KAV-1) kennt drei Ergebnis-Signale
        # (verbunden/abgebrochen/abgelehnt), und ein eigenes „nicht_konfiguriert"-
        # Signal würde den Aufrufer-Vertrag erweitern ohne praktischen Nutzen heute.
        # Klare User-Meldung im Bot-Output reicht: der Aufrufer sieht „abgebrochen"
        # plus eine spezifische Begründungs-Nachricht im Chat (OAUTH_CLIENT_MISSING
        # nennt die Setup-Lücke, ohne `client_secret` zu zeigen — ZD-6).
        fire_typing(typing_fn)
        _send(tg, chat_id, OAUTH_CLIENT_MISSING)
        return KalenderVerbindenResult(ergebnis=ERGEBNIS_ABGEBROCHEN)
    client_id, client_secret = client_pair

    # KAV-4: Aufklärungstext **vor** dem Login-Link.
    fire_typing(typing_fn)
    _send(tg, chat_id, AUFKLAERUNG_TEXT)

    # KAV-5: einmaliger State, im Prozess-Speicher gehalten (analog
    # FAA-9 (b)); Verfall implizit über das `next_message`-Timeout (KAV-6).
    state = _new_state()
    auth_url = build_auth_url(client_id, state)
    fire_typing(typing_fn)
    _send(tg, chat_id, LOGIN_LINK_PROMPT % auth_url)

    # KAV-6: auf die nächste Privatchat-Nachricht warten. Nicht-passende
    # Nachrichten lösen eine freundliche Erinnerung aus und warten weiter
    # — analog ONB-3 letzter Absatz.
    code = None
    while True:
        msg = next_message()
        if msg is None:
            # Timeout (30 min) oder Prozess-Ende — KAV-6.
            fire_typing(typing_fn)
            _send(tg, chat_id, ABGEBROCHEN)
            return KalenderVerbindenResult(ergebnis=ERGEBNIS_ABGEBROCHEN)
        text = msg.text if isinstance(msg, KavInput) else (msg or "")
        code = extract_code(text)
        if code is not None:
            break
        fire_typing(typing_fn)
        _send(tg, chat_id, CODE_REMINDER)

    # KAV-7: Code-Tausch beim Google-Token-Endpunkt.
    try:
        tokens = exchange(code, client_id, client_secret)
    except TokenExchangeError as e:
        # ZD-6: Token werden nie ins Log gespiegelt; wir loggen nur die
        # Tatsache des Fehlschlags.
        logging.warning("kalender_verbinden: Token-Tausch fehlgeschlagen (%s) "
                        "— nichts gespeichert", e)
        fire_typing(typing_fn)
        _send(tg, chat_id, TOKEN_EXCHANGE_FAILED)
        return KalenderVerbindenResult(ergebnis=ERGEBNIS_ABGEBROCHEN)

    refresh_token = tokens["refresh_token"]
    access_token = tokens["access_token"]
    expires_in = tokens.get("expires_in", 0)

    # KAV-8: Account-E-Mail über den `userinfo`-Endpunkt holen. Fehlschlag
    # ist kein Verbindungs-Fehler — die Bestätigung kommt dann ohne E-Mail.
    account_email = ""
    try:
        account_email = fetch_email(access_token) or ""
    except Exception as e:  # Robustheit: kein Verbindungs-Abbruch
        logging.info("kalender_verbinden: account-email nicht ermittelbar (%s) "
                     "— Bestätigung ohne E-Mail (KAV-8)", e)
        account_email = ""

    # KAV-7: Schreiben über die ZD-5-Schnittstelle.
    store_tokens_in_zd(zd, refresh_token, access_token, expires_in,
                       account_email, clock=clock)

    # KAV-X: Kalender-Auswahl. Schlägt sie fehl, sind die Tokens trotzdem
    # gespeichert (KAV-7 ist nicht rückgängig zu machen) — Ergebnis ist dann
    # `verbunden_ohne_kalender`.
    if plan_origin_url is None:
        # Kein Ziel für die kalender_id-Schreibung — KAV-X übersprungen.
        # Tests, die nur den Token-Schritt prüfen wollen, nutzen diesen Pfad.
        logging.info("kalender_verbinden: plan_origin_url nicht gesetzt — "
                     "Kalender-Auswahl übersprungen "
                     "(KAV-X, verbunden_ohne_kalender).")
        return KalenderVerbindenResult(
            ergebnis=ERGEBNIS_VERBUNDEN_OHNE_KALENDER,
            account_email=account_email)

    # KAV-X: calendarList-Abfrage mit dem frischen Access-Token.
    try:
        calendars = fetch_calendars(access_token)
    except CalendarListFetchError as e:
        logging.warning("kalender_verbinden: calendarList-Abfrage fehlgeschlagen "
                        "(%s) — Tokens gespeichert, Kalender-Auswahl offen", e)
        fire_typing(typing_fn)
        _send(tg, chat_id, KALENDER_LIST_FETCH_FAILED)
        return KalenderVerbindenResult(
            ergebnis=ERGEBNIS_VERBUNDEN_OHNE_KALENDER,
            account_email=account_email)

    if not calendars:
        logging.warning("kalender_verbinden: calendarList ist leer (keine "
                        "writable Kalender) — Tokens gespeichert, Auswahl offen")
        fire_typing(typing_fn)
        _send(tg, chat_id, KALENDER_LIST_EMPTY)
        return KalenderVerbindenResult(
            ergebnis=ERGEBNIS_VERBUNDEN_OHNE_KALENDER,
            account_email=account_email)

    # KAV-X: nummerierte Liste posten und auf Auswahl warten.
    fire_typing(typing_fn)
    _send(tg, chat_id, KALENDER_AUSWAHL_PROMPT
          % (format_calendar_list(calendars), len(calendars)))

    chosen_index = None
    while True:
        msg = next_message()
        if msg is None:
            # KAV-X: Timeout *nach* Token-Tausch — Tokens bleiben, plan.json
            # ist unverändert. Ergebnis verbunden_ohne_kalender.
            fire_typing(typing_fn)
            _send(tg, chat_id, ABGEBROCHEN_NACH_TOKEN)
            return KalenderVerbindenResult(
                ergebnis=ERGEBNIS_VERBUNDEN_OHNE_KALENDER,
                account_email=account_email)
        text = msg.text if isinstance(msg, KavInput) else (msg or "")
        idx = parse_selection(text, len(calendars))
        if idx is not None:
            chosen_index = idx
            break
        fire_typing(typing_fn)
        _send(tg, chat_id, KALENDER_AUSWAHL_REMINDER % len(calendars))

    chosen = calendars[chosen_index]
    chosen_id = chosen["id"]
    chosen_name = chosen["summary"]

    # KAV-X / PLAN-32: kalender_id via HTTP PUT an den Plan-Buddy schreiben.
    try:
        write_plan_json(chosen_id)
    except PlanJsonWriteError as e:
        logging.error(
            "kalender_verbinden: plan.json-Schreibvorgang fehlgeschlagen (%s) — "
            "Tokens gespeichert, Kalender-Auswahl ist getroffen, aber plan.json "
            "unverändert (KAV-X)", e)
        fire_typing(typing_fn)
        _send(tg, chat_id, PLAN_JSON_WRITE_FAILED)
        return KalenderVerbindenResult(
            ergebnis=ERGEBNIS_VERBUNDEN_OHNE_KALENDER,
            account_email=account_email)

    # KAV-8 + KAV-Y: Bestätigung mit Kalender-Name. Kein manueller Restart-
    # Hinweis mehr — Plan-Buddy übernimmt die Änderung automatisch über den
    # post_execute_hook des Tasks (EC-21, #140, Refs #154). Schlägt der Hook
    # fehl, hängt das Framework eine Warnung an die Quittung (`Catalog.
    # execute_write_task`). Token-Wert wird nie gespiegelt (ZD-6).
    fire_typing(typing_fn)
    if account_email:
        _send(tg, chat_id,
              BESTAETIGT_MIT_EMAIL % {"kalender": chosen_name, "email": account_email})
    else:
        _send(tg, chat_id, BESTAETIGT_OHNE_EMAIL % {"kalender": chosen_name})

    return KalenderVerbindenResult(
        ergebnis=ERGEBNIS_VERBUNDEN, account_email=account_email)


# ============================================================
#  Helpers
# ============================================================

def _send(tg, chat_id, text):
    """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt,
    aber brechen die Funktion nicht ab — analog `familie_anlegen._send`."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logging.warning("kalender_verbinden: Senden an %s fehlgeschlagen: %s",
                        chat_id, e)
