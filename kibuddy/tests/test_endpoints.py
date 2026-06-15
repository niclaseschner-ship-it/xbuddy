"""KIBuddy-Endpoint-Tests (KIBUDDY-24, KIBUDDY-28, AC1/AC2/AC3).

Alle externen Calls (STT, LLM, TTS) sind gemockt — kein echter Azure-/Anthropic-Call.
"""

import io

# ---- /healthz ----

def test_healthz(client):
    """SVC-1: GET /healthz → 200."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ---- GET /display/kibuddy/frage ----

def test_display_frage_view(client):
    """KIBUDDY-2: GET /display/kibuddy/frage → 200 (Stub-Template)."""
    resp = client.get("/display/kibuddy/frage")
    assert resp.status_code == 200


# ---- POST /api/v1/kibuddy/frage (AC2, FIX1 Response-Schema) ----

def test_frage_happy_path(client, fake_stt, fake_llm, fake_tts):
    """AC2: POST /frage → JSON {text, transkript, words, tts_audio_url}.

    FIX1: words-Slots haben {text, is_inhaltswort}, KEIN icon_id (KIBUDDY-17).
    """
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"FAKEAUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "text" in body
    assert "transkript" in body
    assert "words" in body
    assert "tts_audio_url" in body
    # words ist eine Liste mit text/is_inhaltswort pro Wort (FIX1, KIBUDDY-17).
    assert isinstance(body["words"], list)
    for slot in body["words"]:
        assert "text" in slot
        assert "is_inhaltswort" in slot
        assert "icon_id" not in slot   # FIX1: icon_id entfällt (clientseitig)
    # STT wurde aufgerufen.
    assert len(fake_stt.calls) == 1
    # LLM wurde aufgerufen.
    assert len(fake_llm.calls) == 1
    # TTS wurde aufgerufen.
    assert len(fake_tts.calls) == 1
    # tts_audio_url zeigt auf /api/v1/kibuddy/audio/*.mp3.
    assert body["tts_audio_url"].startswith("/api/v1/kibuddy/audio/")
    assert body["tts_audio_url"].endswith(".mp3")


def test_frage_response_schema_v2(client):
    """FIX1: words[].is_inhaltswort ist bool, kein icon_id im Response."""
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    for slot in body["words"]:
        assert isinstance(slot["is_inhaltswort"], bool)
        assert "icon_id" not in slot


def test_frage_ohne_audio_feld(client):
    """Kein audio-Feld → 400."""
    resp = client.post("/api/v1/kibuddy/frage", data={})
    assert resp.status_code == 400


def test_frage_stt_fehler_503(client, fake_stt):
    """STT-Ausfall → 503."""
    fake_stt.fail = True
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 503


def test_frage_llm_fehler_503(client, fake_llm):
    """LLM-Ausfall → 503."""
    fake_llm.fail = True
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 503


def test_frage_tts_fehler_text_trotzdem_da(client, fake_tts):
    """TTS-Ausfall → 200 mit tts_audio_url=null (KIBUDDY-24 Resilienz)."""
    fake_tts.fail = True
    resp = client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["text"]  # Text ist trotzdem vorhanden.
    assert body["tts_audio_url"] is None


def test_frage_ohne_llm_key_503(client_no_keys):
    """Kein Anthropic-Key → 503 auf LLM-Calls."""
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
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO_A"), "audio.webm")},
        content_type="multipart/form-data",
    )
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO_B"), "audio.webm")},
        content_type="multipart/form-data",
    )
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
    # A.
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    # B.
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    # Reset.
    client.post("/api/v1/kibuddy/reset")
    # C.
    fake_llm.calls.clear()
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
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
    """Jede Frage hängt User+Assistant-Turn an (KIBUDDY-16)."""
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert len(session_memory) == 2  # User + Assistant.

    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    assert len(session_memory) == 4  # Zwei weitere Turns.


def test_frage_uebergibt_history_an_llm(client, fake_llm):
    """LLM bekommt bei der zweiten Frage die History der ersten (KIBUDDY-16)."""
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
    client.post(
        "/api/v1/kibuddy/frage",
        data={"audio": (io.BytesIO(b"AUDIO"), "audio.webm")},
        content_type="multipart/form-data",
    )
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
        client_a.post(
            "/api/v1/kibuddy/frage",
            data={"audio": (io.BytesIO(b"AUDIO_A"), "audio.webm")},
            content_type="multipart/form-data",
        )

    with main_mod.app.test_client() as client_b:
        client_b.set_cookie("kibuddy_sid", sid_b)
        client_b.post(
            "/api/v1/kibuddy/frage",
            data={"audio": (io.BytesIO(b"AUDIO_B"), "audio.webm")},
            content_type="multipart/form-data",
        )

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
