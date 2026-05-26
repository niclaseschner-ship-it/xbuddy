"""Kalender verbinden — siehe specs/platform/kalender-verbinden.md
(KAV-1…KAV-10, Refs #57).

»Kalender verbinden« ist eine aufrufbare, **trigger-agnostische** Funktion
(E-KAV-1, analog `familie_anlegen.familie_anlegen` E-FAA-1 und
`ca_verteilung.verteile_ca` E-CAV-1). Aufgerufen, führt sie ein
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
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import authz
from telegram import TelegramError


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
_REDIRECT_URI = "http://localhost:1"
_OAUTH_SCOPE = "https://www.googleapis.com/auth/calendar.events"

# KAV-6: Timeout der Privatchat-Session (analog FAA-9 / GAA-5: 30 Minuten).
SESSION_TIMEOUT_SECONDS = 30 * 60


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

# KAV-4: Aufklärungstext — deckt zwei Stolpersteine ab:
# 1) „Diese App ist nicht bestätigt" (unverified, vgl. E-KAV-3) →
#    *Erweitert → Weiter zu XBuddy*.
# 2) Browser zeigt nach dem Login eine **Verbindungsfehler-Seite** — die
#    Adressleiste enthält den Code, das ist beabsichtigt.
AUFKLAERUNG_TEXT = (
    "Ich richte den Google-Kalender für die Familie ein. Zwei Dinge vorab:\n\n"
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

BESTAETIGT_MIT_EMAIL = (
    "Geschafft — der Google-Kalender ist verbunden (%s). Der Plan-Buddy "
    "kann jetzt Termine lesen und schreiben. 🎉")

BESTAETIGT_OHNE_EMAIL = (
    "Geschafft — der Google-Kalender ist verbunden. Der Plan-Buddy kann "
    "jetzt Termine lesen und schreiben. 🎉")

ABGEBROCHEN = (
    "Ok — kein Kalender verbunden (Timeout oder du hast abgebrochen). Ruf "
    "»Kalender verbinden« einfach noch einmal auf, wenn du es nochmal "
    "versuchen willst.")


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
        clock = lambda: datetime.now(timezone.utc)  # noqa: E731

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
                      exchange=None, fetch_email=None):
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
    `clock`/`exchange`/`fetch_email` — Test-Naht: Standardwerte sprechen
                              das echte Netz; Tests reichen Doppelungen herein.

    Liefert ein `KalenderVerbindenResult`. Schreibt ausschliesslich über
    `zd.set(...)` (ZD-5).
    """
    if exchange is None:
        exchange = exchange_code_for_tokens
    if fetch_email is None:
        fetch_email = fetch_account_email

    # KAV-2: Live-Berechtigung. Die Prüfung liegt **bei der Funktion**
    # (nicht beim Aufrufer), damit die Trigger-Agnostik erhalten bleibt.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("kalender_verbinden: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
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
        _send(tg, chat_id, OAUTH_CLIENT_MISSING)
        return KalenderVerbindenResult(ergebnis=ERGEBNIS_ABGEBROCHEN)
    client_id, client_secret = client_pair

    # KAV-4: Aufklärungstext **vor** dem Login-Link.
    _send(tg, chat_id, AUFKLAERUNG_TEXT)

    # KAV-5: einmaliger State, im Prozess-Speicher gehalten (analog
    # FAA-9 (b)); Verfall implizit über das `next_message`-Timeout (KAV-6).
    state = _new_state()
    auth_url = build_auth_url(client_id, state)
    _send(tg, chat_id, LOGIN_LINK_PROMPT % auth_url)

    # KAV-6: auf die nächste Privatchat-Nachricht warten. Nicht-passende
    # Nachrichten lösen eine freundliche Erinnerung aus und warten weiter
    # — analog ONB-3 letzter Absatz.
    code = None
    while True:
        msg = next_message()
        if msg is None:
            # Timeout (30 min) oder Prozess-Ende — KAV-6.
            _send(tg, chat_id, ABGEBROCHEN)
            return KalenderVerbindenResult(ergebnis=ERGEBNIS_ABGEBROCHEN)
        text = msg.text if isinstance(msg, KavInput) else (msg or "")
        code = extract_code(text)
        if code is not None:
            break
        _send(tg, chat_id, CODE_REMINDER)

    # KAV-7: Code-Tausch beim Google-Token-Endpunkt.
    try:
        tokens = exchange(code, client_id, client_secret)
    except TokenExchangeError as e:
        # ZD-6: Token werden nie ins Log gespiegelt; wir loggen nur die
        # Tatsache des Fehlschlags.
        logging.warning("kalender_verbinden: Token-Tausch fehlgeschlagen (%s) "
                        "— nichts gespeichert", e)
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
    except Exception as e:  # noqa: BLE001 — Robustheit: kein Verbindungs-Abbruch
        logging.info("kalender_verbinden: account-email nicht ermittelbar (%s) "
                     "— Bestätigung ohne E-Mail (KAV-8)", e)
        account_email = ""

    # KAV-7: Schreiben über die ZD-5-Schnittstelle.
    store_tokens_in_zd(zd, refresh_token, access_token, expires_in,
                       account_email, clock=clock)

    # KAV-8: Bestätigung im Privatchat — Token wird nie gespiegelt (ZD-6).
    if account_email:
        _send(tg, chat_id, BESTAETIGT_MIT_EMAIL % account_email)
    else:
        _send(tg, chat_id, BESTAETIGT_OHNE_EMAIL)

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
