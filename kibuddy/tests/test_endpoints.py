"""KIBuddy-Endpoint-Tests (KIBUDDY-24, KIBUDDY-28, AC1/AC2/AC3).

Alle externen Calls (STT, LLM, TTS) sind gemockt — kein echter Azure-/Anthropic-Call.
"""

import io
import json

import kibuddy.main as main_mod
from kibuddy.session_memory import SID_COOKIE, SessionRegistry
from tools.initdata import session_cookie as _sc

# AUTH-11 (#1836-Nachzug): Sign-Key fuer den Dual-Gate auf /display/kibuddy/frage.
# Dieselbe Konstante wie kibuddy/tests/test_auth_cookie.py::TEST_BOT_TOKEN.
_AUTH_TEST_BOT_TOKEN = "123456:ABCdef_testtoken"


def _auth_cookie_setzen(client):
    """AUTH-11 (#1836-Nachzug): setzt einen validen xbuddy_session-Cookie fuer
    den Dual-Gate auf /display/kibuddy/frage. Additiv -- die `client`-Fixture
    (conftest.py) traegt keinen bot_token, deshalb wird er hier direkt im
    runtime-Dict gesetzt (dieselbe Test-Naht, die main_mod.configure() fuellt).
    Muster wie plan/tests/test_plan.py::_auth_cookie_setzen."""
    main_mod.runtime["bot_token"] = _AUTH_TEST_BOT_TOKEN
    client.set_cookie(_sc.COOKIE_NAME,
                      _sc.sign_session("tablet-kibuddy-test", _AUTH_TEST_BOT_TOKEN))

# ============================================================
#  NDJSON-Stream-Helfer (KIBUDDY-13/24)
# ============================================================

def parse_ndjson_stream(resp):
    """Parst NDJSON-Body einer Streaming-Response in eine Liste von dicts.

    Flask-Testclient gibt .data als Bytes (alle Chunks zusammengefasst).
    Jede nicht-leere Zeile wird als JSON geparst.
    """
    text = resp.data.decode("utf-8")
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    return events


def get_stream_event(resp, event_name):
    """Gibt das erste Event mit event=event_name zurück, oder None."""
    for ev in parse_ndjson_stream(resp):
        if ev.get("event") == event_name:
            return ev
    return None

# ---- parse_kibuddy_response (T865, AC1) ----

def test_parse_kibuddy_response_valid_json():
    """T865/AC1: Valides JSON → antwort + buzzwords extrahiert."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = '{"antwort": "Der Hund bellt.", "buzzwords": ["hund", "bellen", "laut"]}'
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == "Der Hund bellt."
    assert result["buzzwords"] == ["hund", "bellen", "laut"]


def test_parse_kibuddy_response_markdown_fence():
    """T865/AC1: JSON in Markdown-Fence → korrekt extrahiert."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = '```json\n{"antwort": "Test.", "buzzwords": ["a", "b", "c"]}\n```'
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == "Test."
    assert result["buzzwords"] == ["a", "b", "c"]


def test_parse_kibuddy_response_fallback_bei_kein_json():
    """T865/AC1 Fallback: Kein valides JSON → raw als antwort, buzzwords leer."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = "Das ist kein JSON."
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == raw
    assert result["buzzwords"] == []


def test_parse_kibuddy_response_buzzwords_sanitisiert():
    """T865: buzzwords werden durch validate_buzzwords bereinigt (max 3, lowercase)."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = '{"antwort": "Text.", "buzzwords": ["Hund", "KATZE", "Maus", "Extra"]}'
    result = parse_kibuddy_response(raw)
    assert result["buzzwords"] == ["hund", "katze", "maus"]  # max 3, lowercase


def test_parse_kibuddy_response_prosa_vorlauf_plus_fence():
    """Live-Bug 2026-06-15: Claude liefert Prosa + ```json-Fence parallel.
    Parser muss den JSON-Block extrahieren, nicht in Fallback fallen."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = (
        'Das hängt davon ab. Ein Apfelbaum braucht 3-4 Jahre. '
        'Hast du schon mal einen Baum gepflanzt?\n'
        '```json\n'
        '{"antwort": "Das hängt davon ab. Ein Apfelbaum braucht 3-4 Jahre.", '
        '"buzzwords": ["baum", "wachsen", "jahre"]}\n'
        '```'
    )
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == "Das hängt davon ab. Ein Apfelbaum braucht 3-4 Jahre."
    assert result["buzzwords"] == ["baum", "wachsen", "jahre"]


def test_parse_kibuddy_response_prosa_vorlauf_ohne_fence():
    """Variante: Prosa-Vorlauf + nacktes JSON ohne Fence."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = 'Hier kommt die Antwort: {"antwort": "Hallo.", "buzzwords": ["a","b","c"]}'
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == "Hallo."
    assert result["buzzwords"] == ["a", "b", "c"]


def test_parse_kibuddy_response_json_mit_trailing_text():
    """Variante: JSON gefolgt von Prosa-Trailing."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = '{"antwort": "Test.", "buzzwords": ["a","b","c"]}\n\nNoch ein Hinweis.'
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == "Test."
    assert result["buzzwords"] == ["a", "b", "c"]


def test_parse_kibuddy_response_balancierte_klammern_im_string():
    """Edge-Case: { im JSON-String-Wert darf den Klammern-Counter nicht verwirren."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = '{"antwort": "Ein Apfel {} ist eine Frucht.", "buzzwords": ["a","b","c"]}'
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == "Ein Apfel {} ist eine Frucht."
    assert result["buzzwords"] == ["a", "b", "c"]


def test_parse_kibuddy_response_fehlende_felder_fallback():
    """T865: JSON ohne erwartete Felder → antwort leer-string, buzzwords leer."""
    from kibuddy.llm_service import parse_kibuddy_response
    raw = '{"something": "else"}'
    result = parse_kibuddy_response(raw)
    assert result["antwort"] == ""
    assert result["buzzwords"] == []


# ---- /healthz ----

def test_healthz(client):
    """SVC-1: GET /healthz → 200."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ---- GET /display/kibuddy/frage ----

def test_display_frage_view(client):
    """KIBUDDY-2: GET /display/kibuddy/frage → 200 (Stub-Template)."""
    _auth_cookie_setzen(client)
    resp = client.get("/display/kibuddy/frage")
    assert resp.status_code == 200


# ---- POST /api/v1/kibuddy/frage — NDJSON-Stream (KIBUDDY-13/24) ----

def test_frage_happy_path(client, fake_stt, fake_llm, fake_tts):
    """AC2/T865/KIBUDDY-13: POST /frage → NDJSON-Stream mit kind- und buddy-Event.

    Stage 2 buddy-Event enthält buzzwords[] statt words[] (T865/KIBUDDY-24).
    """
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"FAKEAUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "application/x-ndjson" in resp.content_type

    kind_ev = get_stream_event(resp, "kind")
    buddy_ev = get_stream_event(resp, "buddy")

    assert kind_ev is not None, "kind-Event fehlt im Stream"
    assert buddy_ev is not None, "buddy-Event fehlt im Stream"

    assert "transkript" in kind_ev
    assert "transkript_words" in kind_ev

    assert "text" in buddy_ev
    assert "buzzwords" in buddy_ev      # T865: buzzwords statt words
    assert "tts_audio_url" in buddy_ev
    assert "words" not in buddy_ev      # T865: words[] entfaellt

    # buzzwords ist eine Liste mit max 3 Strings (T865/KIBUDDY-24).
    assert isinstance(buddy_ev["buzzwords"], list)
    for bw in buddy_ev["buzzwords"]:
        assert isinstance(bw, str)
    # STT wurde aufgerufen.
    assert len(fake_stt.calls) == 1
    # LLM wurde aufgerufen.
    assert len(fake_llm.calls) == 1
    # TTS wurde aufgerufen.
    assert len(fake_tts.calls) == 1
    # tts_audio_url zeigt auf /api/v1/kibuddy/audio/*.mp3.
    assert buddy_ev["tts_audio_url"].startswith("/api/v1/kibuddy/audio/")
    assert buddy_ev["tts_audio_url"].endswith(".mp3")


def test_frage_streaming_zwei_stages(client, fake_stt, fake_llm, fake_tts):
    """AC1 (KIBUDDY-13/T865): Stream liefert genau zwei Events: kind + buddy.

    Beide Events koennen als separates JSON geparst werden.
    Stage 1 (kind) enthaelt transkript + transkript_words (Diagnose-Liste).
    Stage 2 (buddy) enthaelt text + buzzwords + tts_audio_url (T865/KIBUDDY-24).
    """
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"FAKEAUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    events = parse_ndjson_stream(resp)

    # Genau zwei Events (kein Fehler-Event dazwischen).
    assert len(events) == 2, "Erwartet genau 2 NDJSON-Events (kind + buddy), bekommen: %d" % len(events)

    e1, e2 = events
    assert e1["event"] == "kind", "Erstes Event muss 'kind' sein"
    assert e2["event"] == "buddy", "Zweites Event muss 'buddy' sein"

    # Stage 1: kind-Felder vorhanden.
    assert "transkript" in e1
    assert isinstance(e1["transkript_words"], list)
    # transkript_words ist Diagnose-Feld — kann leer sein (T865 minimal-invasiv).

    # Stage 2: buddy-Felder vorhanden (T865: buzzwords statt words).
    assert "text" in e2
    assert isinstance(e2["buzzwords"], list)
    assert "tts_audio_url" in e2
    assert "words" not in e2


def test_frage_transkript_words_diagnose_feld(client, fake_stt, fake_llm, fake_tts):
    """T865/KIBUDDY-24: transkript_words[] ist Diagnose-Feld, bleibt im kind-Event.

    Frontend ignoriert es (Kind-Bubble text-only, KIBUDDY-19 Option C).
    In T865 liefert Backend eine leere Liste (minimal-invasiv).
    """
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    kind_ev = get_stream_event(resp, "kind")
    assert kind_ev is not None

    tw = kind_ev.get("transkript_words")
    assert isinstance(tw, list), "transkript_words muss eine Liste sein (KIBUDDY-24)"
    # In T865: leere Liste ist OK (Diagnose-Feld, Wortklassen-Filter entfällt)


def test_frage_response_schema_buzzwords(client, fake_llm):
    """T865/KIBUDDY-24: buddy-Event hat buzzwords[] (string-Liste), kein words[]."""
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    buddy_ev = get_stream_event(resp, "buddy")
    assert buddy_ev is not None
    assert "buzzwords" in buddy_ev
    assert "words" not in buddy_ev
    assert isinstance(buddy_ev["buzzwords"], list)
    for bw in buddy_ev["buzzwords"]:
        assert isinstance(bw, str)


def test_frage_ohne_audio_feld(client):
    """Kein audio-Feld → 400 (vor Stream-Start, klassisches JSON-Error)."""
    resp = client.post("/api/v1/kibuddy/frage", data={})
    assert resp.status_code == 400


def test_frage_stt_fehler_stream_error_event(client, fake_stt):
    """AC4/KIBUDDY-13: STT-Ausfall → HTTP 200 + error-Event im Stream (stage=stt).

    Kein kind-Event (STT ist fehlgeschlagen vor Stage 1).
    """
    fake_stt.fail = True
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "application/x-ndjson" in resp.content_type
    events = parse_ndjson_stream(resp)
    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0].get("stage") == "stt"
    assert "detail" in events[0]

    # Kein kind-Event — STT ist vor Stage 1 fehlgeschlagen.
    kind_ev = get_stream_event(resp, "kind")
    assert kind_ev is None


def test_frage_llm_fehler_stream_error_event(client, fake_llm):
    """AC4/KIBUDDY-13: LLM-Ausfall → HTTP 200 + kind-Event (Stage 1 OK) + error-Event (Stage 2).

    Stage 1 (kind) wurde bereits gesendet als der LLM-Fehler auftrat.
    """
    fake_llm.fail = True
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    events = parse_ndjson_stream(resp)
    assert len(events) == 2, "Erwartet kind-Event + error-Event, bekommen: %d" % len(events)
    assert events[0]["event"] == "kind"
    assert events[1]["event"] == "error"
    assert events[1].get("stage") == "llm"
    assert "detail" in events[1]


def test_frage_tts_fehler_tts_audio_url_null(client, fake_tts):
    """AC4/KIBUDDY-24 Resilienz: TTS-Ausfall → buddy-Event mit tts_audio_url=null."""
    fake_tts.fail = True
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    buddy_ev = get_stream_event(resp, "buddy")
    assert buddy_ev is not None
    assert buddy_ev["text"]  # Text ist trotzdem vorhanden.
    assert buddy_ev["tts_audio_url"] is None


def test_frage_ohne_llm_key_503(client_no_keys):
    """Kein Anthropic-Key → 503 vor Stream-Start (klassisches JSON-Error)."""
    resp = client_no_keys.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 503


# ---- POST /api/v1/kibuddy/vorlesen ----

def test_vorlesen_mit_text(client, fake_tts):
    """POST /vorlesen mit text → tts_audio_url."""
    resp = client.post("/api/v1/kibuddy/vorlesen", json={"text": "Hallo Kind!"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert "tts_audio_url" in body
    assert body["tts_audio_url"].endswith(".mp3")
    assert len(fake_tts.calls) == 1


def test_vorlesen_ohne_payload_400(client):
    resp = client.post("/api/v1/kibuddy/vorlesen", json={})
    assert resp.status_code == 400


# ---- POST /api/v1/kibuddy/reset (AC3) ----

def test_reset_loescht_session_memory(client, session_memory):
    """AC3: reset löscht Session-Memory (Mehrturn → Reset → leere History)."""
    # Erst zwei Fragen stellen (baut Memory auf).
    # .data lesen: zwingt den NDJSON-Stream-Generator zur Ausfuehrung (KIBUDDY-13).
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO_A"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO_B"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    assert len(session_memory) > 0

    # Reset.
    resp = client.post("/api/v1/kibuddy/reset")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["turns_geloescht"] > 0

    # Session-Memory ist jetzt leer.
    assert len(session_memory) == 0


def test_reset_dreifach_ablauf(client, session_memory, fake_llm):
    """AC3: Frage A, Frage B, Reset, Frage C — C hat keine Erinnerung an A/B.

    Verifiziert über die turns-Liste, die dem LLM übergeben wird.
    """
    # A. (.data lesen: NDJSON-Stream-Generator ausfuehren, KIBUDDY-13)
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    # B.
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    # Reset.
    client.post("/api/v1/kibuddy/reset")
    # C.
    fake_llm.calls.clear()
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    # Der LLM-Call für C hatte eine leere Turn-Liste (kein A/B-Kontext).
    assert len(fake_llm.calls) == 1
    _system, turns_bei_c, _user = fake_llm.calls[0]
    assert len(turns_bei_c) == 0


# ---- GET/PUT /api/v1/kibuddy/config ----

def test_config_get(client):
    resp = client.get("/api/v1/kibuddy/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "llm_provider" in body
    assert "tts_voice" in body
    assert "anthropic_key_set" in body
    # Keys sind nicht im Response.
    assert "anthropic_key" not in body
    assert "azure_key" not in body


def test_config_put_aufnahme_quelle(client):
    resp = client.put("/api/v1/kibuddy/config", json={"aufnahme-quelle": "panel"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["aufnahme_quelle"] == "panel"


def test_config_put_unbekanntes_feld_400(client):
    """V1 akzeptiert nur aufnahme-quelle (KIBUDDY-24)."""
    resp = client.put("/api/v1/kibuddy/config", json={"voice": "shimmer"})
    assert resp.status_code == 400


# ---- GET/PUT /api/v1/kibuddy/prompt ----

def test_prompt_get_default(client):
    """Kein prompt.txt → Default-Prompt (KIBUDDY-15)."""
    resp = client.get("/api/v1/kibuddy/prompt")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "prompt" in body
    assert body["prompt"]
    assert "byte-laenge" in body


def test_prompt_put_und_get(client):
    """PUT schreibt Prompt, GET liest ihn zurück (KIBUDDY-15)."""
    neuer_prompt = "Du bist ein superspaßiger KI-Buddy für Kinder!"
    put_resp = client.put("/api/v1/kibuddy/prompt", json={"prompt": neuer_prompt})
    assert put_resp.status_code == 200
    put_body = put_resp.get_json()
    assert put_body["ok"] is True

    get_resp = client.get("/api/v1/kibuddy/prompt")
    get_body = get_resp.get_json()
    assert get_body["prompt"] == neuer_prompt


def test_prompt_put_leer_400(client):
    resp = client.put("/api/v1/kibuddy/prompt", json={"prompt": ""})
    assert resp.status_code == 400


def test_prompt_put_zu_lang_400(client, runtime_config):
    """Prompt über prompt_max_bytes → 400 (KIBUDDY-21)."""
    zu_langer_prompt = "x" * (runtime_config.prompt_max_bytes + 1)
    resp = client.put("/api/v1/kibuddy/prompt", json={"prompt": zu_langer_prompt})
    assert resp.status_code == 400


# ---- Mehrturn-Memory (KIBUDDY-16) ----

def test_frage_baut_memory_auf(client, session_memory):
    """Jede Frage haengt User+Assistant-Turn an (KIBUDDY-16)."""
    # .data lesen: NDJSON-Stream-Generator ausfuehren (KIBUDDY-13).
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    assert len(session_memory) == 2  # User + Assistant.

    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    assert len(session_memory) == 4  # Zwei weitere Turns.


def test_frage_uebergibt_history_an_llm(client, fake_llm):
    """LLM bekommt bei der zweiten Frage die History der ersten (KIBUDDY-16)."""
    # .data lesen: NDJSON-Stream-Generator ausfuehren (KIBUDDY-13).
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    parse_ndjson_stream(client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    ))
    assert len(fake_llm.calls) == 2
    _sys, turns_bei_frage_1, _u = fake_llm.calls[0]
    _sys, turns_bei_frage_2, _u = fake_llm.calls[1]
    # Bei Frage 1: keine History.
    assert len(turns_bei_frage_1) == 0
    # Bei Frage 2: 2 Turns aus Frage 1 (user + assistant).
    assert len(turns_bei_frage_2) == 2


# ---- Session-Cookie-Isolation (FIX3, KIBUDDY-16) ----

def test_zwei_clients_unabhaengige_sessions(runtime_config, data_root, fake_llm, fake_stt, fake_tts):
    """FIX3: Zwei Browser (zwei Cookies) haben unabhängige Session-Memories.

    Client A und Client B schicken je eine Frage. Reset auf A löscht NICHT B.
    """
    import kibuddy.main as main_mod
    from kibuddy.session_memory import SessionRegistry

    registry = SessionRegistry()
    main_mod.configure(
        runtime_config=runtime_config,
        data_root=data_root,
        llm=fake_llm,
        stt_engine=fake_stt,
        tts_engine=fake_tts,
        session_registry=registry,
    )

    # Client A: feste Cookie-SID.
    sid_a = "client-a-sid"
    sid_b = "client-b-sid"

    with main_mod.app.test_client() as client_a:
        client_a.set_cookie("kibuddy_sid", sid_a)
        # .data lesen: NDJSON-Stream-Generator ausfuehren (KIBUDDY-13).
        parse_ndjson_stream(client_a.post(
            "/api/v1/kibuddy/frage",
            data={"audio": (io.BytesIO(b"AUDIO_A"), "audio.webm")},
            content_type="multipart/form-data",
        ))

    with main_mod.app.test_client() as client_b:
        client_b.set_cookie("kibuddy_sid", sid_b)
        parse_ndjson_stream(client_b.post(
            "/api/v1/kibuddy/frage",
            data={"audio": (io.BytesIO(b"AUDIO_B"), "audio.webm")},
            content_type="multipart/form-data",
        ))

    mem_a = registry.get_or_create(sid_a)
    mem_b = registry.get_or_create(sid_b)
    assert len(mem_a) > 0
    assert len(mem_b) > 0

    # Reset auf A löscht NICHT B.
    with main_mod.app.test_client() as client_a:
        client_a.set_cookie("kibuddy_sid", sid_a)
        reset_resp = client_a.post("/api/v1/kibuddy/reset")
    assert reset_resp.status_code == 200

    # A ist leer, B noch voll.
    assert len(registry.get_or_create(sid_a)) == 0
    assert len(mem_b) > 0


def test_neuer_client_bekommt_cookie(runtime_config, data_root, fake_llm, fake_stt, fake_tts):
    """FIX3: Ein neuer Browser (kein Cookie) bekommt kibuddy_sid gesetzt."""
    import kibuddy.main as main_mod
    from kibuddy.session_memory import SID_COOKIE, SessionRegistry

    registry = SessionRegistry()
    main_mod.configure(
        runtime_config=runtime_config,
        data_root=data_root,
        llm=fake_llm,
        stt_engine=fake_stt,
        tts_engine=fake_tts,
        session_registry=registry,
    )

    with main_mod.app.test_client() as fresh_client:
        resp = fresh_client.post(
            "/api/v1/kibuddy/frage",
            data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    # Cookie wurde gesetzt.
    cookie_header = resp.headers.get("Set-Cookie", "")
    assert SID_COOKIE in cookie_header


# ---- FIX-5: Alle Endpunkte setzen Cookie konsistent (kein Phantom-Session-Leak) ----

def test_reset_ohne_cookie_setzt_cookie(runtime_config, data_root, fake_llm, fake_stt, fake_tts):
    """FIX-5: POST /reset ohne Cookie → Response setzt Set-Cookie-Header (KIBUDDY-16)."""
    registry = SessionRegistry()
    main_mod.configure(
        runtime_config=runtime_config,
        data_root=data_root,
        llm=fake_llm,
        stt_engine=fake_stt,
        tts_engine=fake_tts,
        session_registry=registry,
    )

    with main_mod.app.test_client() as fresh_client:
        resp = fresh_client.post("/api/v1/kibuddy/reset")
    assert resp.status_code == 200
    cookie_header = resp.headers.get("Set-Cookie", "")
    assert SID_COOKIE in cookie_header


def test_config_get_ohne_cookie_setzt_cookie(runtime_config, data_root, fake_llm, fake_stt, fake_tts):
    """FIX-5: GET /config ohne Cookie → Response setzt Set-Cookie-Header."""
    registry = SessionRegistry()
    main_mod.configure(
        runtime_config=runtime_config,
        data_root=data_root,
        llm=fake_llm,
        stt_engine=fake_stt,
        tts_engine=fake_tts,
        session_registry=registry,
    )

    with main_mod.app.test_client() as fresh_client:
        resp = fresh_client.get("/api/v1/kibuddy/config")
    assert resp.status_code == 200
    cookie_header = resp.headers.get("Set-Cookie", "")
    assert SID_COOKIE in cookie_header
