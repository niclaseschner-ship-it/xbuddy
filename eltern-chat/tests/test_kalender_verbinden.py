"""Tests für »Kalender verbinden« — KAV-1…KAV-10 (Refs #57).

Geprüft werden:
  * die trigger-agnostische Funktion (`kalender_verbinden`) — Auth, Aufklärung,
    OAuth-Link, Code-Empfang, Token-Tausch, ZD-Schreiben, Bestätigung.
  * die EC-8-Aufgabe (`KalenderVerbindenTask`) — Catalog-Registrierung,
    Privatchat-Adapter, Session-Mechanik.
  * reine Logik-Bausteine (`build_auth_url`, `extract_code`,
    `exchange_code_for_tokens`, `store_tokens_in_zd`).

Telegram, Google-Token-Endpunkt und der Zugangsdaten-Speicher sind durch
kontrollierte Doppelungen ersetzt (kein Netz, KAV-10). Die Patterns folgen
`test_familie_anlegen.py` (Funktion) und `test_familie_anlegen_task.py`
(Aufgabe).
"""

import json
import urllib.parse
from datetime import UTC, datetime

import pytest
from fakes import FakeTelegram
from model import WRITE
from skills import kalender_verbinden as kv
from skills.kalender_verbinden import (
    AUFKLAERUNG_TEXT,
    CODE_REMINDER,
    ERGEBNIS_ABGEBROCHEN,
    ERGEBNIS_ABGELEHNT,
    ERGEBNIS_VERBUNDEN,
    ERGEBNIS_VERBUNDEN_OHNE_KALENDER,
    KALENDER_LIST_EMPTY,
    KALENDER_LIST_FETCH_FAILED,
    NOT_AUTHORIZED,
    OAUTH_CLIENT_MISSING,
    PLAN_JSON_WRITE_FAILED,
    TOKEN_EXCHANGE_FAILED,
    ZD_NAME_ACCESS_TOKEN,
    ZD_NAME_ACCESS_TOKEN_EXPIRES_AT,
    ZD_NAME_ACCOUNT_EMAIL,
    ZD_NAME_OAUTH_CLIENT,
    ZD_NAME_OAUTH_TOKEN,
    CalendarListFetchError,
    KavInput,
    PlanJsonWriteError,
    TokenExchangeError,
    build_auth_url,
    exchange_code_for_tokens,
    extract_code,
    fetch_calendar_list,
    format_calendar_list,
    kalender_verbinden,
    parse_selection,
    store_tokens_in_zd,
)
from skills.kalender_verbinden_task import KalenderVerbindenTask, KavSession, make_kav_input
from tasks import TurnContext, build_catalog

# ============================================================
#  Test-Doppelungen — In-Memory-ZD, stream, exchange-doubles
# ============================================================


class FakeZd:
    """In-Memory-Zugangsdaten-Speicher (ZD-5).

    Die echte `Zugangsdaten`-Klasse legt eine 0600-Datei an — für Tests
    brauchen wir nur das `get`/`set`-Protokoll. Schreib-Reihenfolge wird
    in `writes` mitprotokolliert (für KAV-7-Reihenfolge-Tests).
    """

    def __init__(self, initial=None):
        self._data = dict(initial or {})
        self.writes = []

    def get(self, name, default=None):
        return self._data.get(name, default)

    def set(self, name, value):
        self._data[name] = value
        self.writes.append((name, value))

    def has(self, name):
        return name in self._data

    def snapshot(self):
        """Kopie für Vorher-Nachher-Vergleiche (KAV-9 Byte-Identität)."""
        return json.dumps(self._data, sort_keys=True)


def _zd_with_client(client_id="CID-1", client_secret="SECRET-1"):
    return FakeZd(initial={
        ZD_NAME_OAUTH_CLIENT: {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost:1"],
            }
        }
    })


def stream(*items):
    """Baut eine `next_message`-Funktion aus einer Folge von KavInput/Strings.

    Strings sind eine Kurzform für `KavInput(text=string)`. Wird die Folge
    erschöpft, liefert `next_message()` `None` — dann gilt der Aufruf als
    abgebrochen (KAV-6 Timeout).
    """
    box = list(items)

    def next_message():
        if not box:
            return None
        item = box.pop(0)
        if isinstance(item, str):
            return KavInput(text=item)
        return item
    return next_message


def fake_exchange_ok(refresh="REFRESH-1", access="ACCESS-1", expires_in=3599,
                     id_token=None):
    """Eine erfolgreiche Token-Tausch-Doppelung. Protokolliert die Aufruf-
    Argumente für Assertions (KAV-7)."""
    calls = []

    def doubled(code, client_id, client_secret):
        body = {
            "refresh_token": refresh,
            "access_token": access,
            "expires_in": expires_in,
            "token_type": "Bearer",
        }
        if id_token is not None:
            body["id_token"] = id_token
        calls.append({"code": code, "client_id": client_id,
                      "client_secret": client_secret})
        return body
    doubled.calls = calls
    return doubled


def fake_exchange_fail():
    """Eine fehlschlagende Token-Tausch-Doppelung."""
    def doubled(code, client_id, client_secret):
        raise TokenExchangeError("simulated invalid_grant")
    return doubled


def fake_fetch_email(email="user@example.com"):
    """Eine `fetch_account_email`-Doppelung, die eine feste E-Mail liefert."""
    def doubled(access_token):
        return email
    return doubled


def fake_fetch_email_empty():
    def doubled(access_token):
        return ""
    return doubled


# KAV-X: kontrollierte Doppelungen für `fetch_calendar_list` und für den
# `write_plan_json`-Schritt. Beide reichen die Aufrufer-Argumente an
# Test-Assertions weiter.

def fake_fetch_calendars(calendars=None):
    """KAV-X: liefert eine feste Kalender-Liste an `kalender_verbinden`.

    Default-Liste hat einen writable Primary plus einen weiteren writer-
    Kalender — passt zum typischen Pi-Family-Setup.
    """
    if calendars is None:
        calendars = [
            {"id": "primary-id", "summary": "Persönlich", "accessRole": "owner",
             "primary": True},
            {"id": "family@group.calendar.google.com", "summary": "Familie",
             "accessRole": "writer", "primary": False},
        ]
    calls = []

    def doubled(access_token):
        calls.append({"access_token": access_token})
        return list(calendars)
    doubled.calls = calls
    return doubled


def fake_fetch_calendars_fail():
    def doubled(access_token):
        raise CalendarListFetchError("simulated HTTP 403")
    return doubled


def fake_write_plan_json():
    """KAV-X / PLAN-32: Doppelung für den HTTP-Seam (`write_plan_json`) —
    protokolliert die aufgerufene `kalender_id` statt wirklich zu schreiben."""
    calls = []

    def doubled(kalender_id):
        calls.append({"kalender_id": kalender_id})
    doubled.calls = calls
    return doubled


def fake_write_plan_json_fail():
    def doubled(kalender_id):
        raise PlanJsonWriteError("simulated HTTP error")
    return doubled


def fake_plan_transport_ok(called=None):
    """HTTP-Transport-Doppelung für PLAN-32 PUT /api/v1/plan/admin/kalender.

    Liefert HTTP 200 mit `{ok: true}`. Protokolliert aufgerufene Methode,
    Pfad und Body in der Liste `called`, falls übergeben.
    """
    if called is None:
        called = []

    def transport(method, path, body=None, content_type=None):
        called.append({"method": method, "path": path, "body": body})
        return 200, b'{"ok": true}'
    transport.called = called
    return transport


def fake_plan_transport_fail():
    """HTTP-Transport-Doppelung, die PLAN-32 PUT mit HTTP 500 ablehnt."""
    def transport(method, path, body=None, content_type=None):
        return 500, b'{"error": "internal"}'
    return transport


# Hilfs-Konstante für die häufige Aufruf-Form mit HTTP-Seam.
_DEFAULT_PLAN_ORIGIN = "http://127.0.0.1:5020"


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _fixed_clock(t):
    return lambda: t


# ============================================================
#  KAV-1 — Catalog-Registrierung als WriteTask (Trigger-Aufhängung)
# ============================================================


def test_KAV_1_task_is_registered_in_catalog_as_write_task():
    """KAV-1 / EC-10: `build_catalog` registriert die KalenderVerbindenTask,
    wenn die KAV-Abhängigkeiten geliefert werden. Sie ist eine WriteTask."""
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        zd_store_getter=lambda: _zd_with_client(),
        kav_sessions={},
        family_group_chat_id_getter=lambda: "-100")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "kalender_verbinden" in defs
    assert defs["kalender_verbinden"].kind == WRITE
    # Die neue Aufgabe (Subjekt des Tests) bleibt registriert.
    assert "kalender_verbinden" in defs


def test_KAV_1_legacy_build_catalog_signature_still_works():
    """Rückwärts-kompatibel: `build_catalog(tg, ca_path)` ohne KAV-Abhängig-
    keiten funktioniert weiter."""
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "kalender_verbinden" not in defs


def test_KAV_1_task_has_proposal_summary_mentioning_privatchat():
    """KAV-1 / EC-10: die Aufgabe legt einen Vorschlag vor — er nennt den
    Privatchat, weil dort der Login-Link landet (KAV-3)."""
    task = KalenderVerbindenTask(
        FakeTelegram(), lambda: _zd_with_client(),
        sessions={}, family_group_chat_id_getter=lambda: "-100")
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(
            chat_id=7, from_user_id=7, private_chat_id=7))
    assert "Privatchat" in proposal.summary


# ============================================================
#  KAV-2 — Live-Berechtigung (Nicht-Mitglied wird abgewiesen)
# ============================================================


def test_KAV_2_non_member_is_rejected_and_zd_unchanged():
    """KAV-2: ein Aufruf eines Nicht-Familien-Mitglieds wird abgelehnt;
    der Zugangsdaten-Speicher bleibt byte-gleich."""
    tg = FakeTelegram(members={})   # niemand ist Mitglied
    zd = _zd_with_client()
    before = zd.snapshot()
    result = kalender_verbinden(
        tg, chat_id=9, user_id=9, family_group_chat_id="-100",
        zd=zd, next_message=stream())
    assert result.ergebnis == ERGEBNIS_ABGELEHNT
    assert zd.snapshot() == before
    # Die NOT_AUTHORIZED-Nachricht ging in den Privatchat des Aufrufers.
    assert any(NOT_AUTHORIZED in s["text"] for s in tg.sent
               if s["chat_id"] == 9)


# ============================================================
#  KAV-3 — Privatchat-Pflicht (Gruppen-Trigger landet im Privatchat)
# ============================================================


def test_KAV_3_group_trigger_addresses_callers_private_chat():
    """KAV-3 / Privatchat-Adapter: wird die Aufgabe aus dem Familien-Gruppen-
    Chat aufgerufen, startet die KAV-Anlage im Privatchat des Aufrufers
    (chat_id == user_id), nicht in der Gruppe. Beobachtungs-Punkt: die
    erste KAV-Nachricht (Aufklärungstext) landet im Privatchat."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _zd_with_client(),
        sessions=sessions, family_group_chat_id_getter=lambda: "-100")
    # Gruppen-Anfrage: chat_id = -100 (Gruppe), private_chat_id = user_id.
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt
    # Warte, bis die erste Bot-Nachricht (Aufklärung) im Privatchat liegt.
    import time
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    private_sends = [s for s in tg.sent if s["chat_id"] == user_id]
    assert private_sends, "KAV hätte mindestens eine Nachricht im Privatchat "\
                          "senden müssen (Aufklärungstext)"
    # Keine Verbinden-Nachricht ging in den Gruppen-Chat.
    group_sends = [s for s in tg.sent if s["chat_id"] == "-100"]
    assert not group_sends


def test_KAV_3_task_without_private_chat_id_redirects():
    """KAV-3: kein Privatchat-`TurnContext` → die Aufgabe leitet höflich um,
    ohne eine Session zu starten (analog FAA-12)."""
    sessions = {}
    task = KalenderVerbindenTask(
        FakeTelegram(), lambda: _zd_with_client(),
        sessions=sessions, family_group_chat_id_getter=lambda: "-100")
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=None, private_chat_id=None))
    assert "Privatchat" in receipt
    assert sessions == {}


# ============================================================
#  KAV-4 — Aufklärungstext vor dem Login-Link
# ============================================================


def test_KAV_4_aufklaerung_kommt_vor_dem_login_link():
    """KAV-4: vor dem OAuth-Link wird der Aufklärungstext gepostet.
    Reihenfolge der Nachrichten beobachtbar, Inhalt deckt »Unbestätigte App«
    + »Verbindungsfehler«-Seite ab."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    # next_message liefert sofort einen Code — die Funktion postet erst die
    # Aufklärung, dann den Link, dann verarbeitet sie den Code.
    nm = stream("http://localhost:1/?code=ABC&scope=foo")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty())
    texts = [s["text"] for s in tg.sent if s["chat_id"] == user_id]
    # Aufklärung zuerst.
    assert texts[0] == AUFKLAERUNG_TEXT
    # Der Aufklärungstext benennt den »Unbestätigte App«-Warnscreen und die
    # »Verbindungsfehler«-Seite.
    assert "nicht bestätigt" in AUFKLAERUNG_TEXT
    assert "Verbindungsfehler" in AUFKLAERUNG_TEXT
    # KAV-4 (Refs #133): bis der mobile Pfad gebaut ist, wird im
    # Aufklärungstext explizit empfohlen, am Desktop/Laptop zu verbinden —
    # Loopback-Redirect-URL ist auf Mobile-Browsern nicht zuverlässig sichtbar.
    assert "Laptop" in AUFKLAERUNG_TEXT
    assert "nicht am Handy" in AUFKLAERUNG_TEXT
    # Login-Link kommt direkt danach.
    assert "accounts.google.com" in texts[1]


# ============================================================
#  KAV-5 — Login-Link mit korrekten OAuth-Parametern
# ============================================================


def test_KAV_5_auth_url_has_required_oauth_parameters():
    """KAV-5: `build_auth_url` enthält Scopes `calendar.events` **plus**
    `calendar.readonly` (KAV-X-load-bearing), `access_type=offline`,
    `prompt=consent`, `response_type=code`, `redirect_uri=http://localhost:1`,
    die OAuth-Client-ID und einen `state`-Parameter."""
    url = build_auth_url(client_id="CID-XY", state="STATE-XY")
    parsed = urllib.parse.urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"
    q = urllib.parse.parse_qs(parsed.query)
    assert q["client_id"] == ["CID-XY"]
    assert q["redirect_uri"] == ["http://localhost:1"]
    assert q["response_type"] == ["code"]
    # KAV-5 / KAV-X: beide Scopes, space-separiert. `calendar.events` für
    # PLAN-17/PLAN-18, `calendar.readonly` für die `calendarList`-Abfrage.
    scope_value = q["scope"][0]
    assert "https://www.googleapis.com/auth/calendar.events" in scope_value
    assert "https://www.googleapis.com/auth/calendar.readonly" in scope_value
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert q["state"] == ["STATE-XY"]


def test_KAV_5_scope_includes_readonly():
    """KAV-5 / KAV-X: der OAuth-URL enthält beide Scopes, `calendar.events`
    und `calendar.readonly`. Ohne `readonly` antwortet Google bei
    `calendarList.list` mit HTTP 403 (verifiziert auf Pi 2026-05-26)."""
    url = build_auth_url(client_id="CID-XY", state="STATE-XY")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    scope_value = q["scope"][0]
    # space-separiert, beide drin.
    parts = scope_value.split(" ")
    assert "https://www.googleapis.com/auth/calendar.events" in parts
    assert "https://www.googleapis.com/auth/calendar.readonly" in parts


def test_KAV_5_state_is_unique_per_call():
    """KAV-5: jeder Verbinden-Aufruf bringt einen frischen, einmaligen State.
    Beobachtungs-Punkt: zwei Logins der gleichen Familie tragen unterschiedliche
    `state`-Parameter."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    captured_states = []

    for _ in range(2):
        zd = _zd_with_client()
        nm = stream("http://localhost:1/?code=ABC")
        kalender_verbinden(
            tg, chat_id=user_id, user_id=user_id,
            family_group_chat_id="-100", zd=zd, next_message=nm,
            exchange=fake_exchange_ok(),
            fetch_email=fake_fetch_email_empty())
        # Letzten Link finden.
        link_msgs = [s["text"] for s in tg.sent
                     if s["chat_id"] == user_id
                     and "accounts.google.com" in s["text"]]
        url_in_text = link_msgs[-1].split("\n")[-1].strip()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url_in_text).query)
        captured_states.append(q["state"][0])

    assert len(set(captured_states)) == 2


def test_KAV_5_missing_oauth_client_in_zd_aborts_cleanly():
    """KAV-5 / E-KAV-4 / Pi-Deploy-Vorbedingung: fehlt der OAuth-Client-Eintrag
    im Zugangsdaten-Speicher, gibt die Funktion eine klare Fehlermeldung an
    den User zurück und schreibt nichts."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = FakeZd(initial={})   # kein plan-google-oauth-client
    before = zd.snapshot()
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=stream(),
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty())
    assert result.ergebnis == ERGEBNIS_ABGEBROCHEN
    assert zd.snapshot() == before
    assert any(OAUTH_CLIENT_MISSING in s["text"] for s in tg.sent)


# ============================================================
#  KAV-6 — Code-Empfang im Privatchat (URL-Form und blanker Code)
# ============================================================


def test_KAV_6_extract_code_accepts_full_url():
    """KAV-6: vollständige URL `http://localhost:1/?code=ABC&scope=…`
    liefert `ABC`."""
    assert extract_code("http://localhost:1/?code=ABC&scope=foo") == "ABC"


def test_KAV_6_extract_code_accepts_url_without_scheme():
    """KAV-6: auch ohne Schema (Browser zeigt das manchmal so) wird der
    Code aus dem Query-String geholt."""
    assert extract_code("localhost:1/?code=ABCDEF") == "ABCDEF"


def test_KAV_6_extract_code_accepts_blank_code_with_whitespace():
    """KAV-6: blanker Code-String mit umliegenden Leerzeichen/Zeilenumbruch
    wird nach Trimmen direkt verwendet. Echte Google-Codes haben die Form
    `4/0A…` mit Slash und Bindestrich, deutlich länger als 16 Zeichen."""
    assert extract_code("  4/0AbCdEf-GhIjKlMnOpQr  \n") == \
        "4/0AbCdEf-GhIjKlMnOpQr"


def test_KAV_6_extract_code_rejects_implausible_messages():
    """KAV-6: eine Nachricht ohne `code=` und ohne plausible Code-Form
    (Begrüßung, Frage, leere Nachricht) liefert `None`."""
    assert extract_code("hallo?") is None
    assert extract_code("hallo!") is None
    assert extract_code("") is None
    assert extract_code(None) is None
    assert extract_code("   \n  ") is None
    assert extract_code("hi") is None  # zu kurz, hat keinen `code=`
    assert extract_code("ab cd") is None  # Leerzeichen, kein code=
    assert extract_code("hat das geklappt?") is None  # Frage


def test_KAV_6_implausible_messages_trigger_reminder_then_session_continues():
    """KAV-6: eine nicht-passende Nachricht löst eine freundliche Erinnerung
    aus, dann wartet die Funktion auf die nächste Nachricht — nicht den
    Token-Tausch."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    exchange = fake_exchange_ok()
    # Erst eine Begrüßung (nicht passend), dann der echte Code, dann „1"
    # für die Kalender-Auswahl (KAV-X).
    nm = stream("hallo!", "http://localhost:1/?code=GOOD", "1")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=exchange,
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=fake_write_plan_json())
    assert result.ergebnis == ERGEBNIS_VERBUNDEN
    assert any(CODE_REMINDER in s["text"] for s in tg.sent)
    # Token-Tausch wurde mit dem zweiten (echten) Code aufgerufen, nicht mit
    # „hallo!".
    assert len(exchange.calls) == 1
    assert exchange.calls[0]["code"] == "GOOD"


def test_KAV_6_timeout_returns_abgebrochen():
    """KAV-6: ein leerer Eingabe-Strom (entspricht 30-min-Timeout) beendet
    die Session und liefert »abgebrochen«."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    before = zd.snapshot()
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=stream(),
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty())
    assert result.ergebnis == ERGEBNIS_ABGEBROCHEN
    # KAV-9 / KAV-7: bei Abbruch wird nichts geschrieben.
    assert zd.snapshot() == before


# ============================================================
#  KAV-7 — Token-Tausch und Speicherung im Zugangsdaten-Speicher
# ============================================================


def test_KAV_7_token_exchange_posts_to_google_token_endpoint(monkeypatch):
    """KAV-7: `exchange_code_for_tokens` postet an `oauth2.googleapis.com/token`
    mit `redirect_uri=http://localhost:1`, `grant_type=authorization_code`,
    `code`, `client_id`, `client_secret`."""
    captured = {}

    class FakeResp:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["data"] = req.data
        captured["headers"] = dict(req.header_items())
        return FakeResp(json.dumps({
            "access_token": "AT", "refresh_token": "RT",
            "expires_in": 3599, "token_type": "Bearer",
        }).encode())

    monkeypatch.setattr(kv.urllib.request, "urlopen", fake_urlopen)
    tokens = exchange_code_for_tokens(
        code="THE-CODE", client_id="CID", client_secret="SEC")
    assert tokens["refresh_token"] == "RT"
    assert tokens["access_token"] == "AT"
    assert captured["url"] == "https://oauth2.googleapis.com/token"
    assert captured["method"] == "POST"
    form = urllib.parse.parse_qs(captured["data"].decode())
    assert form["code"] == ["THE-CODE"]
    assert form["client_id"] == ["CID"]
    assert form["client_secret"] == ["SEC"]
    assert form["redirect_uri"] == ["http://localhost:1"]
    assert form["grant_type"] == ["authorization_code"]


def test_KAV_7_successful_exchange_writes_four_keys_with_correct_schema():
    """KAV-7: erfolgreicher Token-Tausch schreibt die vier KAV-7-Schlüssel
    über die ZD-5-Schnittstelle. Der `plan-google-oauth-refresh-token`-Wert
    hat die von `plan/kalender.py` erwartete Form `{"refresh_token": "..."}`
    (PLAN-16 load-bearing)."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD")
    fixed = datetime(2026, 5, 26, 12, 0, 0, tzinfo=UTC)
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm,
        exchange=fake_exchange_ok(refresh="RT-1", access="AT-1",
                                  expires_in=3600),
        fetch_email=fake_fetch_email("mia@example.com"),
        clock=_fixed_clock(fixed))
    # Refresh-Token in der von PLAN-16 erwarteten Form.
    assert zd.get(ZD_NAME_OAUTH_TOKEN) == {"refresh_token": "RT-1"}
    assert zd.get(ZD_NAME_ACCESS_TOKEN) == "AT-1"
    # Expires-at = clock() + expires_in Sekunden, ISO-8601.
    assert zd.get(ZD_NAME_ACCESS_TOKEN_EXPIRES_AT) == \
        "2026-05-26T13:00:00+00:00"
    assert zd.get(ZD_NAME_ACCOUNT_EMAIL) == "mia@example.com"


def test_KAV_7_token_values_not_in_logs(caplog):
    """KAV-7 / ZD-6: Token-Werte tauchen in keinem Log auf — auch nicht im
    Erfolgs-Log."""
    import logging
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD")
    with caplog.at_level(logging.DEBUG):
        kalender_verbinden(
            tg, chat_id=user_id, user_id=user_id,
            family_group_chat_id="-100", zd=zd, next_message=nm,
            exchange=fake_exchange_ok(refresh="SECRET-RT",
                                      access="SECRET-AT"),
            fetch_email=fake_fetch_email_empty())
    log_text = caplog.text
    assert "SECRET-RT" not in log_text
    assert "SECRET-AT" not in log_text


def test_KAV_7_failed_exchange_writes_nothing():
    """KAV-7: ein Google-Fehler (HTTP 400 `invalid_grant`) schreibt nichts;
    der bestehende Speicher-Inhalt bleibt byte-gleich."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    before = zd.snapshot()
    nm = stream("http://localhost:1/?code=BAD")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm,
        exchange=fake_exchange_fail(),
        fetch_email=fake_fetch_email_empty())
    assert result.ergebnis == ERGEBNIS_ABGEBROCHEN
    assert zd.snapshot() == before
    assert any(TOKEN_EXCHANGE_FAILED in s["text"] for s in tg.sent)


def test_KAV_7_store_tokens_helper_writes_expected_keys():
    """KAV-7 (Unit-Test des Helpers): `store_tokens_in_zd` schreibt die vier
    Schlüssel mit korrektem Schema und in stabiler Reihenfolge (Refresh-Token
    zuerst, weil das die PLAN-16-load-bearing Wahrheit ist)."""
    zd = FakeZd()
    fixed = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    store_tokens_in_zd(zd, refresh_token="RT", access_token="AT",
                       expires_in=120, account_email="x@example.com",
                       clock=_fixed_clock(fixed))
    names = [name for name, _ in zd.writes]
    assert names[0] == ZD_NAME_OAUTH_TOKEN   # PLAN-16-zentral
    assert ZD_NAME_ACCESS_TOKEN in names
    assert ZD_NAME_ACCESS_TOKEN_EXPIRES_AT in names
    assert ZD_NAME_ACCOUNT_EMAIL in names
    assert zd.get(ZD_NAME_OAUTH_TOKEN) == {"refresh_token": "RT"}
    assert zd.get(ZD_NAME_ACCESS_TOKEN_EXPIRES_AT) == \
        "2026-01-01T00:02:00+00:00"


# ============================================================
#  KAV-8 — Bestätigung im Privatchat
# ============================================================


def test_KAV_8_confirmation_contains_account_email_when_available():
    """KAV-8: nach erfolgreicher Kalender-Auswahl + Speicherung enthält die
    Bestätigungs-Nachricht die `kav-account-email` — niemals den Refresh-Token."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD", "1")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(refresh="SECRET-RT"),
        fetch_email=fake_fetch_email("mia@example.com"),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=fake_write_plan_json())
    msgs = [s["text"] for s in tg.sent if s["chat_id"] == user_id]
    assert any("mia@example.com" in m for m in msgs)
    # Refresh-Token taucht in keiner Nachricht auf (ZD-6).
    assert not any("SECRET-RT" in m for m in msgs)


def test_KAV_8_confirmation_without_email_when_not_available():
    """KAV-8: ist die E-Mail nicht ableitbar, kommt eine Bestätigung ohne
    E-Mail (Spec erlaubt das via »soweit aus dem Token ableitbar«)."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD", "1")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=fake_write_plan_json())
    msgs = [s["text"] for s in tg.sent if s["chat_id"] == user_id]
    # Die formatierte Bestätigung enthält den Kalender-Namen.
    assert any("ist verbunden" in m and "Persönlich" in m for m in msgs)


def test_KAV_8_failed_exchange_preserves_existing_account_email():
    """KAV-8 / KAV-9: bei einem fehlschlagenden Token-Tausch bleibt eine
    vorher gesetzte `kav-account-email` byte-gleich (»letzter erfolgreicher
    Tausch gewinnt«)."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    zd._data[ZD_NAME_ACCOUNT_EMAIL] = "old@example.com"
    zd._data[ZD_NAME_OAUTH_TOKEN] = {"refresh_token": "OLD-RT"}
    before = zd.snapshot()
    nm = stream("http://localhost:1/?code=BAD")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm,
        exchange=fake_exchange_fail(),
        fetch_email=fake_fetch_email("new@example.com"))
    assert zd.get(ZD_NAME_ACCOUNT_EMAIL) == "old@example.com"
    assert zd.snapshot() == before


# ============================================================
#  KAV-9 — Idempotenz: letzter erfolgreicher Aufruf gewinnt
# ============================================================


def test_KAV_9_second_successful_call_overwrites_refresh_token():
    """KAV-9: ein zweiter erfolgreicher Aufruf überschreibt das Refresh-Token
    unter `plan-google-oauth-refresh-token` (PLAN-15: ein Familien-Kalender
    je Instanz)."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()

    # Erster Verbinden-Vorgang.
    nm1 = stream("http://localhost:1/?code=FIRST")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm1,
        exchange=fake_exchange_ok(refresh="RT-FIRST"),
        fetch_email=fake_fetch_email("a@example.com"))
    assert zd.get(ZD_NAME_OAUTH_TOKEN) == {"refresh_token": "RT-FIRST"}

    # Zweiter (Re-Connect) — der letzte erfolgreiche Aufruf gewinnt.
    nm2 = stream("http://localhost:1/?code=SECOND")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm2,
        exchange=fake_exchange_ok(refresh="RT-SECOND"),
        fetch_email=fake_fetch_email("b@example.com"))
    assert zd.get(ZD_NAME_OAUTH_TOKEN) == {"refresh_token": "RT-SECOND"}
    assert zd.get(ZD_NAME_ACCOUNT_EMAIL) == "b@example.com"


def test_KAV_9_failed_call_preserves_existing_refresh_token():
    """KAV-9: ein fehlgeschlagener Aufruf (KAV-7-Fehler) lässt das vorherige
    Refresh-Token unverändert — ein abgebrochener Re-Connect darf nicht zur
    stillen Trennung führen."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    zd._data[ZD_NAME_OAUTH_TOKEN] = {"refresh_token": "OLD-RT"}
    before = zd.snapshot()
    nm = stream("http://localhost:1/?code=BAD")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm,
        exchange=fake_exchange_fail(),
        fetch_email=fake_fetch_email_empty())
    assert zd.snapshot() == before


# ============================================================
#  KAV-X — Kalender-Auswahl nach Token-Erfolg
# ============================================================


def test_KAV_X_fetch_calendar_list_filters_writable(monkeypatch):
    """KAV-X: `fetch_calendar_list` filtert die `calendarList`-Antwort auf
    Kalender mit `accessRole` ∈ {owner, writer} plus jeden `primary=true`-
    Kalender. Reader-only ohne Primary-Flag wird ausgeblendet."""
    body = json.dumps({
        "items": [
            {"id": "p", "summary": "Persönlich",
             "accessRole": "owner", "primary": True},
            {"id": "fam", "summary": "Familie",
             "accessRole": "writer", "primary": False},
            {"id": "ro", "summary": "Nur lesen",
             "accessRole": "reader", "primary": False},
            {"id": "ext", "summary": "Externer Kalender (read-only)",
             "accessRole": "reader", "primary": False},
            {"id": "shared-write", "summary": "Geteilter Schreib-Kalender",
             "accessRole": "writer"},
        ]
    }).encode()

    class FakeResp:
        def read(self):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        assert req.full_url.startswith(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList")
        # KAV-X: Bearer-Token im Header.
        assert req.headers.get("Authorization") == "Bearer AT-X"
        return FakeResp()

    monkeypatch.setattr(kv.urllib.request, "urlopen", fake_urlopen)
    result = fetch_calendar_list("AT-X")
    ids = [c["id"] for c in result]
    assert ids == ["p", "fam", "shared-write"]
    # Primary-Markierung ist mit drin.
    assert result[0]["primary"] is True
    assert result[1]["primary"] is False


def test_KAV_X_fetch_calendar_list_raises_on_http_error(monkeypatch):
    """KAV-X: HTTPError bei `calendarList.list` → `CalendarListFetchError`,
    Bearer-Token taucht im Fehler-Text nicht auf (ZD-6)."""
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(kv.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(CalendarListFetchError) as exc:
        fetch_calendar_list("SECRET-AT")
    assert "SECRET-AT" not in str(exc.value)


def test_KAV_X_parse_selection_accepts_valid_numbers():
    """KAV-X: Ganzzahl im Bereich 1..N wird in den 0-basierten Index
    übersetzt; Whitespace wird gestrippt."""
    assert parse_selection("1", 3) == 0
    assert parse_selection("  2  ", 3) == 1
    assert parse_selection("3", 3) == 2


def test_KAV_X_parse_selection_accepts_robust_variants():
    """KAV-X / Refs #155: der Parser akzeptiert die übliche User-Sprache —
    extrahiert die erste Ziffer aus der Antwort und prüft den Range. Damit
    werden Antworten wie »1. bitte«, »die 3«, »2)«, »nimm 2« nicht mehr
    abgewiesen, wie im Live-Test heute geschehen."""
    assert parse_selection("1. bitte", 3) == 0
    assert parse_selection("die 3", 3) == 2
    assert parse_selection("2)", 3) == 1
    assert parse_selection("3.", 3) == 2
    assert parse_selection("nimm 2", 3) == 1


def test_KAV_X_parse_selection_rejects_invalid_input():
    """KAV-X: ungültige Eingabe (Buchstaben ohne Zahl, außerhalb des
    Bereichs, leer) liefert `None`. Wortzahlen wie »eins« bleiben in V1
    außen vor (Folge-Ticket, falls relevant)."""
    assert parse_selection("0", 3) is None
    assert parse_selection("4", 3) is None
    assert parse_selection("5", 3) is None  # out of range bei 3 Optionen
    assert parse_selection("bla", 3) is None
    assert parse_selection("", 3) is None
    assert parse_selection(None, 3) is None
    assert parse_selection("acht", 3) is None  # Wortzahl → kein Match
    assert parse_selection("eins", 3) is None  # Wortzahl → kein Match


def test_KAV_X_format_calendar_list_numbers_each_entry():
    """KAV-X: die nummerierte Anzeige enthält pro Kalender eine Zeile mit
    Index, Name, Rolle und ggf. „Primary"-Markierung."""
    cals = [
        {"id": "p", "summary": "Persönlich", "accessRole": "owner",
         "primary": True},
        {"id": "fam", "summary": "Familie", "accessRole": "writer",
         "primary": False},
    ]
    text = format_calendar_list(cals)
    assert "1. Persönlich" in text
    assert "owner" in text
    assert "Primary" in text
    assert "2. Familie" in text
    assert "writer" in text


def test_KAV_X_user_selects_calendar_writes_chosen_id():
    """KAV-X / PLAN-32: Bot postet die Liste, User schickt „2", Skill schreibt
    die `id` des **zweiten** Kalenders via HTTP PUT an den Plan-Buddy."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    write = fake_write_plan_json()
    fetch = fake_fetch_calendars()  # zwei Kalender, Default
    nm = stream("http://localhost:1/?code=GOOD", "2")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email("mia@example.com"),
        fetch_calendars=fetch, write_plan_json=write)
    assert result.ergebnis == ERGEBNIS_VERBUNDEN
    assert len(write.calls) == 1
    # Default-Liste: Index 1 (zweiter Kalender) = family@group.calendar.google.com.
    assert write.calls[0]["kalender_id"] == "family@group.calendar.google.com"
    # Liste wurde im Chat angekündigt (KAV-X-Prompt).
    msgs = [s["text"] for s in tg.sent if s["chat_id"] == user_id]
    assert any("Welchen Kalender" in m for m in msgs)


def test_KAV_X_invalid_selection_asks_again_then_continues():
    """KAV-X: User schickt „bla" → freundliche Erinnerung; danach gültige
    „1" → Skill wählt den ersten Kalender, der Schreibvorgang läuft durch."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    write = fake_write_plan_json()
    nm = stream("http://localhost:1/?code=GOOD", "bla", "5", "1")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=write)
    assert result.ergebnis == ERGEBNIS_VERBUNDEN
    # Reminder kam mindestens einmal (KAV_AUSWAHL_REMINDER, parametrisiert
    # mit der Anzahl der Kalender).
    msgs = [s["text"] for s in tg.sent if s["chat_id"] == user_id]
    reminder_substr = "Das war keine gültige Nummer"
    assert sum(1 for m in msgs if reminder_substr in m) >= 2
    # Geschrieben wurde der erste Kalender, „1" → primary-id.
    assert write.calls[0]["kalender_id"] == "primary-id"


def test_KAV_X_calendar_list_fetch_failure_returns_verbunden_ohne_kalender():
    """KAV-X: schlägt `calendarList.list` fehl, sind die Tokens trotzdem
    gespeichert (KAV-7 läuft vor KAV-X); Ergebnis ist
    `verbunden_ohne_kalender`, plan.json wird nicht angefasst."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    write = fake_write_plan_json()
    nm = stream("http://localhost:1/?code=GOOD")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(refresh="RT-1"),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars_fail(),
        write_plan_json=write)
    assert result.ergebnis == ERGEBNIS_VERBUNDEN_OHNE_KALENDER
    # Tokens sind dennoch geschrieben (KAV-7 vor KAV-X).
    assert zd.get(ZD_NAME_OAUTH_TOKEN) == {"refresh_token": "RT-1"}
    # HTTP-Schreibvorgang wurde *nicht* aufgerufen.
    assert write.calls == []
    assert any(KALENDER_LIST_FETCH_FAILED in s["text"] for s in tg.sent)


def test_KAV_X_empty_calendar_list_returns_verbunden_ohne_kalender():
    """KAV-X: liefert `calendarList.list` keine writable Kalender, gilt das
    als gescheiterte Auswahl — Tokens bleiben gespeichert, `plan.json` nicht."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    write = fake_write_plan_json()
    nm = stream("http://localhost:1/?code=GOOD")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(calendars=[]),
        write_plan_json=write)
    assert result.ergebnis == ERGEBNIS_VERBUNDEN_OHNE_KALENDER
    assert write.calls == []
    assert any(KALENDER_LIST_EMPTY in s["text"] for s in tg.sent)


def test_KAV_X_plan_json_write_failure_returns_verbunden_ohne_kalender():
    """KAV-X: schlägt der `plan.json`-Schreibvorgang fehl, sind Tokens und
    Auswahl getroffen, aber Plan-Buddy wird die alte `kalender_id` weiter
    lesen. User bekommt einen klaren Hinweis."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD", "1")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=fake_write_plan_json_fail())
    assert result.ergebnis == ERGEBNIS_VERBUNDEN_OHNE_KALENDER
    assert any(PLAN_JSON_WRITE_FAILED in s["text"] for s in tg.sent)


def test_KAV_X_http_seam_put_sends_kalender_id_to_plan_buddy():
    """KAV-X / PLAN-32 (AC_ENTRY): der lebende Schreibpfad ist der HTTP PUT
    an `PUT /api/v1/plan/admin/kalender`. Wenn `plan_origin_url` gesetzt ist,
    baut `kalender_verbinden` eine HTTP-Anfrage an den Plan-Buddy.

    Test-Naht: `write_plan_json`-Callable mit Transport-Doppelung; kein
    direkter FS-Zugriff (PLAN-32, CLAUDE.md §6 »kein toter Code«)."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    write = fake_write_plan_json()
    # Zweiten Kalender wählen (family@group.calendar.google.com).
    nm = stream("http://localhost:1/?code=GOOD", "2")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=write)
    assert result.ergebnis == ERGEBNIS_VERBUNDEN
    assert len(write.calls) == 1
    # PLAN-32: die `kalender_id` des zweiten Kalenders wird via HTTP geschrieben.
    assert write.calls[0]["kalender_id"] == "family@group.calendar.google.com"


def test_KAV_X_http_seam_failure_returns_verbunden_ohne_kalender():
    """KAV-X / PLAN-32: schlägt der HTTP-PUT fehl, liefert die Funktion
    `verbunden_ohne_kalender` und postet `PLAN_JSON_WRITE_FAILED` — Tokens bleiben."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD", "1")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(refresh="RT-1"),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=fake_write_plan_json_fail())
    assert result.ergebnis == ERGEBNIS_VERBUNDEN_OHNE_KALENDER
    assert zd.get(ZD_NAME_OAUTH_TOKEN) == {"refresh_token": "RT-1"}
    assert any(PLAN_JSON_WRITE_FAILED in s["text"] for s in tg.sent)


def test_KAV_X_timeout_during_selection_returns_verbunden_ohne_kalender():
    """KAV-X: Timeout in der Kalender-Auswahl-Schleife (Stream erschöpft)
    beendet die Funktion mit `verbunden_ohne_kalender` — Tokens bleiben."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    write = fake_write_plan_json()
    # Code abgeben, dann nichts mehr → Timeout während der Auswahl.
    nm = stream("http://localhost:1/?code=GOOD")
    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(refresh="RT-1"),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=write)
    assert result.ergebnis == ERGEBNIS_VERBUNDEN_OHNE_KALENDER
    # Tokens sind gespeichert, HTTP-Schreibvorgang *nicht* aufgerufen.
    assert zd.get(ZD_NAME_OAUTH_TOKEN) == {"refresh_token": "RT-1"}
    assert write.calls == []


# ============================================================
#  KAV-Y — Erfolgs-Quittung ohne manuellen Restart-Hinweis
#  (Refs #154 — #140 ist gemergt, der Plan-Buddy-Reload läuft als
#  post_execute_hook im Skill-Framework; eine Warn-Nachricht für den
#  Hook-Fehlerfall hängt EC-21 selbst an die Quittung.)
# ============================================================


def test_KAV_Y_bestaetigung_frei_von_manuellem_restart_hint():
    """KAV-Y / Refs #154: die finale Erfolgs-Nachricht enthält KEINEN Hinweis
    mehr auf `sudo systemctl restart xbuddy-plan` und keinen Verweis auf
    ein Folge-Ticket — der Reload läuft automatisch (post_execute_hook,
    EC-21, #140)."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD", "1")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email("mia@example.com"),
        fetch_calendars=fake_fetch_calendars(),
        write_plan_json=fake_write_plan_json())
    msgs = [s["text"] for s in tg.sent if s["chat_id"] == user_id]
    # Erfolgs-Nachricht wurde gepostet (Kalender-Name + Account-E-Mail).
    assert any("VPSJNN" in m or "Familie" in m or "Persönlich" in m
               for m in msgs)
    # KEIN manueller Restart-Hinweis, KEIN „Letzter Schritt"-Wortlaut,
    # KEIN Folge-Ticket-Verweis (Refs #154).
    assert not any("sudo systemctl restart" in m for m in msgs)
    assert not any("Letzter Schritt" in m for m in msgs)
    assert not any("Folge-Ticket" in m for m in msgs)


def test_KAV_Y_no_restart_hint_when_calendar_selection_failed():
    """KAV-Y: scheitert die Kalender-Auswahl, gibt es ebenfalls keinen
    manuellen Restart-Hinweis — die normalen Fehler-Nachrichten (KAV-X)
    decken den Fall ab, und der Reload-Hook läuft sowieso nur nach
    erfolgreichem Schreiben."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    zd = _zd_with_client()
    nm = stream("http://localhost:1/?code=GOOD")
    kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id, family_group_chat_id="-100",
        zd=zd, next_message=nm, plan_origin_url=_DEFAULT_PLAN_ORIGIN,
        exchange=fake_exchange_ok(),
        fetch_email=fake_fetch_email_empty(),
        fetch_calendars=fake_fetch_calendars_fail(),
        write_plan_json=fake_write_plan_json())
    msgs = [s["text"] for s in tg.sent if s["chat_id"] == user_id]
    assert not any("sudo systemctl restart" in m for m in msgs)
    assert not any("Folge-Ticket" in m for m in msgs)


# ============================================================
#  KAV-3-Adapter: FaaSession-artige Privatchat-Session beansprucht Chat
# ============================================================


def test_session_blocks_a_second_start():
    """Eine zweite Anlage-Anfrage, während eine Session schon läuft, wird
    abgewiesen — nicht doppelt gestartet (Pattern aus FAA-12)."""
    user_id = 7
    sessions = {user_id: KavSession(user_id)}
    task = KalenderVerbindenTask(
        FakeTelegram(members=_members(user_id)),
        lambda: _zd_with_client(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    assert "schon" in receipt.lower() or "läuft" in receipt.lower()


def test_make_kav_input_carries_text():
    """Adapter: Text-Nachricht wird zu KavInput.text (analog FAA-Adapter)."""
    from fakes import make_message
    msg = make_message("http://localhost:1/?code=XYZ")
    ki = make_kav_input(msg)
    assert isinstance(ki, KavInput)
    assert ki.text == "http://localhost:1/?code=XYZ"


# ============================================================
#  KAV-10 — Meta: jede KAV-ID hat einen Test
# ============================================================


def test_KAV_10_every_kav_id_has_at_least_one_test():
    """KAV-10: jede KAV-ID dieser Spec mit Code-Verhalten hat mindestens
    einen Test. Wir nehmen den Test-Modul-Quelltext als Beobachtungs-Punkt
    (analog des FAM-1-Stils in test_familie_anlegen)."""
    import inspect
    src = inspect.getsource(inspect.getmodule(test_KAV_1_task_is_registered_in_catalog_as_write_task))
    for kav_id in ("KAV_1", "KAV_2", "KAV_3", "KAV_4", "KAV_5", "KAV_6",
                   "KAV_7", "KAV_8", "KAV_9", "KAV_10", "KAV_X", "KAV_Y"):
        # Token kommt entweder als Funktionsname oder im Docstring vor.
        assert "test_%s" % kav_id in src or kav_id.replace("_", "-") in src, \
            "Keine Test-Funktion für %s gefunden" % kav_id.replace("_", "-")
