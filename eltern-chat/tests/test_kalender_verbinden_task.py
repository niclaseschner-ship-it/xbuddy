"""Tests fuer die ReloadHook-Verkabelung am KalenderVerbindenTask
(Refs #140, EC-21) und das Quittungs-Verhalten je nach Aufruf-Chat
(Refs #157).

Die Anlage selbst (Privatchat-Konversation, OAuth-Login, Token-Speicherung)
wird in `test_kalender_verbinden.py` geprueft. Hier geht es um
Aufgaben-spezifische Aspekte: Reload-Hook + Quittungstext.

Seit T264 (SESS-5-Refactor): handle_update-Routing-Test (KAV-3) prüft, dass
eingehende Privatchat-Nachrichten an eine laufende KAV-Session geleitet werden
— analog TES-3 (test_termin_eintragen_task.py Z.285-361)."""

import time

from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from history import History
from hooks import ReloadHook
from main import Context, handle_update
from skills.kalender_verbinden import ZD_NAME_OAUTH_CLIENT
from skills.kalender_verbinden_task import KalenderVerbindenTask, KavSession
from tasks import TurnContext, build_catalog


class _FakeZd:
    """Minimal-ZD fuer die Quittungs-Tests — die KAV-Session wuerde mit
    diesem Client den OAuth-Login anstossen; wir testen aber nur die
    Sofort-Quittung, die Session danach laeuft bis sie auf next_message
    blockt und dort timeoutet (Test selbst beendet sie nicht ab)."""

    def __init__(self):
        self._data = {ZD_NAME_OAUTH_CLIENT: {
            "installed": {
                "client_id": "CID-1",
                "client_secret": "SECRET-1",
                "redirect_uris": ["http://localhost:1"],
            }
        }}

    def get(self, name, default=None):
        return self._data.get(name, default)

    def set(self, name, value):
        self._data[name] = value

    def has(self, name):
        return name in self._data


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def test_KAV_post_execute_hooks_contain_plan_buddy_reload():
    """EC-21 / #140: KalenderVerbindenTask deklariert mindestens einen
    ReloadHook, der den Plan-Buddy-Reload-Endpunkt anspricht. Der
    Plan-Buddy ist der Konsument der KAV-Tokens — ohne diesen Reload
    laeuft er nach KAV mit seinem alten Cache weiter (EC-21-Symptom)."""
    hooks = KalenderVerbindenTask.post_execute_hooks
    assert hooks, "KalenderVerbindenTask muss mindestens einen Hook deklarieren"
    reload_hooks = [h for h in hooks if isinstance(h, ReloadHook)]
    assert reload_hooks, "Es muss mindestens ein ReloadHook dabei sein"
    plan_hooks = [h for h in reload_hooks if "plan" in h.url.lower()]
    assert plan_hooks, ("Mindestens ein ReloadHook muss auf den Plan-Buddy "
                        "zeigen (`plan` im URL-Pfad)")
    plan_hook = plan_hooks[0]
    # Konkreter HTTP-Vertrag aus PR #151 — Pfad + Methode.
    assert "/admin/reload" in plan_hook.url
    # Consumer-Label landet in der Familien-Warnung, wenn der Reload
    # scheitert — es muss menschenlesbar sein.
    assert plan_hook.consumer == "Plan-Buddy"


def test_KAV_post_execute_hooks_is_a_class_attribute():
    """Stateless-Anforderung (#140): die Hook-Liste haengt am Klassen-
    Attribut, nicht an einer Instanz — verschiedene Familien teilen sich
    dieselben Hook-Deklarationen, ohne Per-Instanz-State."""
    assert "post_execute_hooks" in vars(KalenderVerbindenTask)


# ============================================================
#  Refs #157 — Quittung haengt am Aufruf-Chat
# ============================================================

def test_KAV_157_group_trigger_returns_switch_receipt():
    """Refs #157: Wird die Aufgabe aus dem Familien-Chat aufgerufen
    (chat_id != private_chat_id), enthaelt die Quittung den Wechsel-Hinweis
    auf den Privatchat — bestehendes Verhalten, hier explizit fixiert."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _FakeZd(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt


# ============================================================
#  Refs #159 — KAV verkabelt Hooks an die Worker-Session
# ============================================================

def test_KAV_159_is_async_flag_is_true():
    """Refs #159: KAV markiert sich als async-Task — `execute()` startet
    nur den Worker-Thread und kehrt sofort zurueck. Das Framework
    (`Catalog.execute_write_task`) liest dieses Flag, um die inline-Hook-
    Iteration zu SKIPPEN; die Hooks feuern stattdessen am Worker-Ende
    (siehe `PrivateChatSession.start(post_execute_hooks=...)`)."""
    assert KalenderVerbindenTask.is_async is True


def test_KAV_159_session_receives_post_execute_hooks(monkeypatch):
    """Refs #159: Beim `execute()` reicht KAV seine `post_execute_hooks`
    sowie einen `HookContext` und einen `on_warning`-Callback an
    `session.start(...)` — sonst feuern die Hooks am Worker-Ende
    nie. Wir spionieren `PrivateChatSession.start` an und pruefen die
    Verkabelung, ohne den OAuth-Flow oder die echte Worker-Thread-Mechanik
    auszufuehren."""
    from skills.kalender_verbinden_task import KavSession

    captured = {}

    def fake_start(self, target, args=(), post_execute_hooks=(),
                   hook_context=None, on_warning=None):
        captured["post_execute_hooks"] = post_execute_hooks
        captured["hook_context"] = hook_context
        captured["on_warning"] = on_warning
        # Worker wird im Test NICHT gestartet — sonst blockiert
        # `kalender_verbinden(...)` in `next_message()`.

    monkeypatch.setattr(KavSession, "start", fake_start)

    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _FakeZd(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    tc = TurnContext(
        chat_id="-100", from_user_id=user_id, private_chat_id=user_id)
    receipt = task.execute(arguments={}, turn_context=tc)
    # Sofort-Quittung kommt zurueck (Async-Pfad).
    assert "Privatchat" in receipt
    # Hook-Liste wurde durchgereicht — DIESELBEN Objekte wie am Klassenattribut.
    assert captured["post_execute_hooks"] == KalenderVerbindenTask.post_execute_hooks
    # HookContext traegt task_name + turn_context.
    hc = captured["hook_context"]
    assert hc is not None
    assert hc.task_name == "kalender_verbinden"
    assert hc.turn_context is tc
    # on_warning ist eine callable, die in den Privatchat des Aufrufers
    # schreibt (sonst sieht die Familie keine Reload-Warnung).
    assert callable(captured["on_warning"])
    captured["on_warning"]("TEST-WARNUNG")
    assert any(msg.get("chat_id") == user_id
               and msg.get("text") == "TEST-WARNUNG"
               for msg in tg.sent)


def test_KAV_plan_origin_url_override_sets_reload_hook_url():
    """EC-21 / Auftrag #215: Wird `KalenderVerbindenTask` mit einem
    `plan_origin_url`-Wert instanziiert, ueberschreibt die Instanz die
    Klassen-Hook-Liste — der erste ReloadHook zeigt auf den Override-Origin
    plus den stabilen Reload-Pfad."""
    from skills.kalender_verbinden_task import PLAN_BUDDY_RELOAD_PATH
    task = KalenderVerbindenTask(
        tg=None,
        zd_store_getter=lambda: None,
        sessions={},
        family_group_chat_id_getter=lambda: "-100",
        plan_origin_url="http://andere:9999",
    )
    hooks = task.post_execute_hooks
    assert hooks, "Instanz muss nach Override mindestens einen Hook haben"
    reload_hooks = [h for h in hooks if isinstance(h, ReloadHook)]
    assert reload_hooks, "Mindestens ein ReloadHook muss vorhanden sein"
    hook_url = reload_hooks[0].url
    assert hook_url == "http://andere:9999" + PLAN_BUDDY_RELOAD_PATH, (
        "ReloadHook-URL muss Override-Origin + stabilen Reload-Pfad enthalten, "
        "war: %r" % hook_url)


def test_KAV_157_private_trigger_omits_switch_receipt():
    """Refs #157 (Live-Beleg 2026-05-26): Wird die KAV-Aufgabe IM Privatchat
    des Aufrufers aufgerufen, unterdrueckt die Quittung den Wechsel-Hinweis.
    Der Aufrufer ist schon im Privatchat — die erste Frage / Aufklaerung
    folgt asynchron im selben Chat aus der KAV-Session."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _FakeZd(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" not in receipt
    # Die KAV-Session sendet ihre erste Nachricht (NOT_AUTHORIZED oder den
    # Aufklaerungstext) in den Privatchat des Aufrufers — Beleg, dass die
    # naechsten Schritte direkt hier weitergehen.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "KAV haette mindestens eine Nachricht im Privatchat senden muessen"
    assert tg.sent[0]["chat_id"] == user_id


# ============================================================
#  T285-S1 — Smoke-Test: run_kav baut typing_fn-Lambda korrekt (EC-25)
# ============================================================

_KAV_PRIVATE_CHAT_ID = 7
_KAV_FAMILY_GROUP_ID = "-100"


def test_T285_S1_kav_typing_fn_fires_per_session_step():
    """T285-S1 / AC1+AC2: run_kav() baut typing_fn-Lambda korrekt — sendet
    send_chat_action an private_chat_id, NICHT an family_group_chat_id.

    Smoke-Test für den Pfad execute() → run_kav() → kalender_verbinden():
    Die Closure in kalender_verbinden_task.py bindet private_chat_id aus dem
    TurnContext. Wir lassen die Session bis zur ersten send_message laufen
    (Aufklärungstext nach NOT_AUTHORIZED-Prüfung) und prüfen, dass davor
    fire_typing gefeuert hat.

    AC1: mindestens ein send_chat_action(private_chat_id, 'typing').
    AC2: kein send_chat_action an family_group_chat_id.
    """
    user_id = _KAV_PRIVATE_CHAT_ID
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _FakeZd(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: _KAV_FAMILY_GROUP_ID)

    ctx_turn = TurnContext(
        chat_id=_KAV_FAMILY_GROUP_ID,
        from_user_id=user_id,
        private_chat_id=user_id,
    )
    quittung = task.execute(arguments={}, turn_context=ctx_turn)
    assert quittung

    # Warten, bis die Session mindestens eine Nachricht gesendet hat
    # (Aufklärungstext = erster send_message nach fire_typing).
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "KAV haette mindestens eine Nachricht gesendet haben muessen"

    # AC1: mindestens ein Typing-Aufruf an den Privatchat.
    typing_private = [
        a for a in tg.chat_actions
        if a["chat_id"] == user_id and a["action"] == "typing"
    ]
    assert typing_private, (
        "Kein send_chat_action(chat_id=%s, action='typing') gefunden. "
        "Alle aufgezeichneten Aufrufe: %r" % (user_id, tg.chat_actions))

    # AC2: kein Typing-Aufruf an die Familien-Gruppe.
    typing_group = [
        a for a in tg.chat_actions
        if a["chat_id"] == _KAV_FAMILY_GROUP_ID
    ]
    assert not typing_group, (
        "send_chat_action wurde an family_group_chat_id=%s gesendet — "
        "typing_fn-Lambda schließt falsche ID ein. Aufrufe: %r"
        % (_KAV_FAMILY_GROUP_ID, tg.chat_actions))

    # Cleanup: Session aus der Map entfernen, damit kein Worker-Thread haengt.
    sessions.pop(user_id, None)


# ============================================================
#  KAV-3 / T264 — handle_update routet Privatchat-Nachrichten an KAV-Session
# ============================================================

def _ctx_with_kav_session(tmp_path, tg, kav_sessions,
                           family_group_chat_id="-100"):
    """Minimaler Context für den handle_update-Routing-Test (KAV-3, T264).

    Analog `_ctx_with_tes_session` in `test_termin_eintragen_task.py` (Z.285-310):
    Context hat eine kav_sessions-Map, damit handle_update eingehende
    Privatchat-Updates an die laufende Session leiten kann.
    """
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        zd_store_getter=lambda: None,
        kav_sessions=kav_sessions,
        family_group_chat_id_getter=lambda: family_group_chat_id,
    )
    return Context(
        tg=tg,
        bot_username="mybot",
        family_group_chat_id=family_group_chat_id,
        context_depth=20,
        provider=FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "kav_routing.db")),
        pending=PendingStore(),
        kav_sessions=kav_sessions,
    )


def test_handle_update_routes_to_kav_session(tmp_path):
    """KAV-3 / T264 (SESS-5-Entry-Path-Lücke): läuft eine KAV-Session in einem
    Privatchat, gehen eingehende Privatchat-Updates dorthin (statt zum Agenten)
    — analog TES-3 (test_termin_eintragen_task.py Z.312-361).

    Prüft: handle_update ruft session.deliver() auf, wenn eine aktive KAV-Session
    für den eingehenden chat_id existiert. Die Nachricht landet NICHT beim Agenten
    (FakeProvider bleibt ohne Aufruf).
    """
    user_id = 42
    tg = FakeTelegram(members={user_id: {"status": "member"}})
    kav_sessions = {}
    ctx = _ctx_with_kav_session(tmp_path, tg, kav_sessions)

    # Session manuell starten: eine KavSession in die Map eintragen.
    session = KavSession(chat_id=user_id)
    kav_sessions[user_id] = session

    # Eingabe aufzeichnen, die via deliver() ankommt.
    delivered = []

    def _run():
        msg = session.next_message()
        if msg is not None:
            delivered.append(msg)

    session.start(_run, ())
    # Warten, bis der Worker-Thread auf next_message() blockiert.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not session._queue is not None:
        time.sleep(0.01)
    time.sleep(0.05)  # Worker ist nun in next_message() blockiert.

    # handle_update aufrufen — Privatchat-Nachricht von user_id.
    msg = make_message("Kalender verbinden bitte",
                       chat_id=user_id, from_user_id=user_id,
                       chat_type="private", message_id=201)
    handle_update(msg, ctx)

    # Warten, bis deliver() die Nachricht verarbeitet hat.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not delivered:
        time.sleep(0.01)

    assert delivered, (
        "handle_update hätte die Privatchat-Nachricht an kav_sessions[%s].deliver() "
        "leiten müssen — stattdessen wurde sie nicht an die Session zugestellt" % user_id)
    assert delivered[0].text == "Kalender verbinden bitte"
    # Session wird nach _run() aus der Map entfernt — kein Agent-Aufruf.
    assert not tg.sent, "Der Agent hätte bei laufender KAV-Session nicht antworten dürfen"


# ============================================================
#  T341 — KAV ruft plan admin/kalender via HTTP (PLAN-32 / APP-3)
# ============================================================

def test_T341_kav_kalender_id_via_http_put(monkeypatch):
    """T341 / AC3: KAV schreibt die gewählte `kalender_id` per HTTP-PUT an
    `<plan_origin>/api/v1/plan/admin/kalender` — NICHT direkt in plan.json.

    Der HTTP-Call wird gemockt (kein echter Plan-Buddy-Server). Wir prüfen:
    - Es wird genau ein PUT an die korrekte URL gesendet.
    - Der Body enthält `{"kalender_id": "<gewählte-id>"}`.
    - Kein direkter FS-Write (write_kalender_id_to_plan_json wird NICHT aufgerufen).
    """
    import json
    import urllib.request

    from skills import kalender_verbinden as kv_mod
    from skills.kalender_verbinden import (
        ERGEBNIS_VERBUNDEN,
        KavInput,
        kalender_verbinden,
    )

    captured_requests = []

    class _FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req):
        captured_requests.append(req)
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    # Fake-Telegram und minimal-ZD.
    from fakes import FakeTelegram

    user_id = 99
    tg = FakeTelegram(members={user_id: {"status": "member"}})

    class _MinZd:
        def __init__(self):
            self._data = {
                kv_mod.ZD_NAME_OAUTH_CLIENT: {
                    "installed": {
                        "client_id": "CID", "client_secret": "SEC",
                        "redirect_uris": ["http://localhost:1"],
                    }
                }
            }

        def get(self, name, default=None):
            return self._data.get(name, default)

        def set(self, name, value):
            self._data[name] = value

        def has(self, name):
            return name in self._data

    messages = iter([
        KavInput(text="http://localhost:1/?code=TESTCODE"),  # OAuth-Code
        KavInput(text="1"),                                   # Kalender-Auswahl
    ])

    def next_msg():
        return next(messages, None)

    plan_origin = "http://127.0.0.1:5020"

    # Fake-Exchange und fake-calendarList — kein Netz.
    def fake_exchange(code, client_id, client_secret):
        return {"refresh_token": "RT", "access_token": "AT",
                "expires_in": 3600}

    def fake_fetch_email(access_token):
        return "test@example.com"

    def fake_fetch_calendars(access_token):
        return [{"id": "kalender-abc@group.calendar.google.com",
                 "summary": "Familienkalender", "accessRole": "owner"}]

    result = kalender_verbinden(
        tg, chat_id=user_id, user_id=user_id,
        family_group_chat_id="-100",
        zd=_MinZd(), next_message=next_msg,
        plan_origin_url=plan_origin,
        exchange=fake_exchange,
        fetch_email=fake_fetch_email,
        fetch_calendars=fake_fetch_calendars,
        # write_plan_json NICHT gesetzt → Default-Pfad (HTTP PUT).
    )

    assert result.ergebnis == ERGEBNIS_VERBUNDEN, (
        "Ergebnis sollte ERGEBNIS_VERBUNDEN sein, war: %r" % result.ergebnis)

    # Genau ein HTTP-PUT an den korrekten Endpoint.
    assert len(captured_requests) == 1, (
        "Erwartet: genau 1 HTTP-Anfrage, got: %d" % len(captured_requests))
    req = captured_requests[0]
    assert req.get_full_url() == plan_origin + "/api/v1/plan/admin/kalender", (
        "Falsche URL: %r" % req.get_full_url())
    assert req.get_method() == "PUT"
    body = json.loads(req.data)
    assert body["kalender_id"] == "kalender-abc@group.calendar.google.com", (
        "Falscher Body: %r" % body)
