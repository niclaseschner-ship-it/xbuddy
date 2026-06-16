"""HSP-33..HSP-40 — Eltern-Mini-App Endpoints (Auth, Config, Audio, Resume, Themen).

Alle Tests laufen OHNE Netz, OHNE Telegram, OHNE Mistral/Anthropic-API.
Auth wird via bot_token="TEST" in den Test-Client-Fixtures durchgeleitet —
hoerspiel/main.py erlaubt "TEST" als Bypass-Token im Testmodus.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from hoerspiel import config as config_mod  # noqa: E402
from hoerspiel import main as main_mod  # noqa: E402

# ============================================================
#  Fixtures — Auth-fähiger Test-Client
# ============================================================

@pytest.fixture
def data_root_mini(tmp_path):
    """Daten-Bereich mit minimaler Bestückung für Mini-App-Tests."""
    root = tmp_path / "data"
    (root / "shared-assets").mkdir(parents=True)
    for voice in ("shimmer", "onyx"):
        (root / "shared-assets" / ("intro_%s.mp3" % voice)).write_bytes(
            b"INTRO-%s" % voice.encode())
        (root / "shared-assets" / ("outro_%s.mp3" % voice)).write_bytes(
            b"OUTRO-%s" % voice.encode())
    (root / "bible.md").write_text("# Welt-Bible\n\nStigi ist ein Stieglitz.\n")
    (root / "folgen-historie.md").write_text("## Folge 1: Test\n\nSynopse.\n")
    # Alben-Verzeichnis
    album_dir = root / "alben" / "folge-1" / "audio"
    album_dir.mkdir(parents=True)
    (album_dir / "track-02.mp3").write_bytes(b"ID3" + b"\x00" * 100)
    return str(root)


@pytest.fixture
def runtime_cfg_with_mistral():
    """RuntimeConfig mit Anthropic- + Mistral-Key für Provider-Tests."""
    return config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5053, log_level="INFO",
        llm_provider="claude", llm_model="claude-opus-4-7",
        anthropic_key="test-anthropic-key",
        mistral_key="test-mistral-key",
        azure_endpoint="https://example.invalid",
        azure_deployment="tts-hd-test",
        azure_key="test-azure-key",
    )


@pytest.fixture
def data_cfg_mini():
    return config_mod.DataConfig(
        default_voice="shimmer",
        serien_name="Stigi & Co.",
        pause_absatz_sek=0.55,
        pause_titel_sek=1.8,
        playback_tempo=1.0,
    )


@pytest.fixture
def client_mini(runtime_cfg_with_mistral, data_cfg_mini, data_root_mini):
    """Test-Client für Mini-App-Endpoints. Auth via bot_token='TEST' (Bypass)."""
    main_mod.configure(
        runtime_config=runtime_cfg_with_mistral,
        data_config=data_cfg_mini,
        data_root=data_root_mini,
        llm=None,
        tts_engine=None,
        bot_token="TEST",
    )
    return main_mod.app.test_client()


@pytest.fixture
def client_mini_no_auth(runtime_cfg_with_mistral, data_cfg_mini, data_root_mini):
    """Test-Client ohne Bot-Token → normale Auth-Prüfung."""
    main_mod.configure(
        runtime_config=runtime_cfg_with_mistral,
        data_config=data_cfg_mini,
        data_root=data_root_mini,
        llm=None,
        tts_engine=None,
        # kein bot_token gesetzt → führt zu 500 (Token fehlt)
        init_data_config={"max_age_seconds": 86400},
    )
    return main_mod.app.test_client()


# ============================================================
#  HSP-33-Auth — 401/403-Verhalten (HSP-40)
# ============================================================

@pytest.mark.skip(reason="V3 #898: Soft-Auth — Header optional, kein 401 mehr bei fehlendem Header")
def test_config_ohne_auth_header_401(client_mini_no_auth):
    """HSP-39: GET /config ohne Authorization-Header → 401 oder 500."""
    resp = client_mini_no_auth.get("/api/v1/hoerspiel/mia/config")
    # 500 wenn Token fehlt, 401 wenn Token da aber initData fehlt.
    assert resp.status_code in (401, 500)


@pytest.mark.skip(reason="V3 #898: Soft-Auth — Header optional, kein 401 mehr bei fehlendem Header")
def test_themen_ohne_auth_header_401(client_mini_no_auth):
    resp = client_mini_no_auth.get("/api/v1/hoerspiel/themen?alter=4")
    assert resp.status_code in (401, 500)


# ============================================================
#  HSP-34-GET /config — Pflicht-Felder + modelle_je_anbieter (HSP-40)
# ============================================================

def test_get_config_pflichtfelder(client_mini):
    """HSP-34: GET /config muss alle Pflicht-Felder enthalten."""
    resp = client_mini.get("/api/v1/hoerspiel/mia/config")
    assert resp.status_code == 200
    body = resp.get_json()

    # Basis-Felder
    assert "llm_provider" in body
    assert "llm_model" in body
    assert "default_voice" in body
    assert "pause_absatz_sek" in body
    assert "pause_titel_sek" in body
    assert "playback_tempo" in body

    # Key-Flags
    assert "anthropic_key_set" in body
    assert "mistral_key_set" in body
    assert "azure_key_set" in body

    # Provider + Modell-Listen
    assert "voices_verfuegbar" in body
    assert "provider_verfuegbar" in body
    assert "modelle_je_anbieter" in body

    # modelle_je_anbieter hat beide Provider
    mja = body["modelle_je_anbieter"]
    assert "claude" in mja
    assert "mistral" in mja
    assert len(mja["claude"]) >= 3
    assert len(mja["mistral"]) >= 3

    # provider_verfuegbar enthält claude (Anthropic-Key gesetzt)
    assert "claude" in body["provider_verfuegbar"]
    assert "mistral" in body["provider_verfuegbar"]


def test_get_config_werte_entsprechen_data_config(client_mini):
    """HSP-34: GET /config-Werte kommen aus DataConfig."""
    resp = client_mini.get("/api/v1/hoerspiel/mia/config")
    body = resp.get_json()
    assert abs(body["pause_absatz_sek"] - 0.55) < 0.01
    assert abs(body["pause_titel_sek"] - 1.8) < 0.01
    assert abs(body["playback_tempo"] - 1.0) < 0.01
    assert body["default_voice"] == "shimmer"


# ============================================================
#  HSP-34-PATCH /config — Validierung (HSP-40)
# ============================================================

def test_patch_config_playback_tempo_range_verletzung(client_mini):
    """HSP-40: playback_tempo=2.0 → 422."""
    resp = client_mini.patch("/api/v1/hoerspiel/mia/config",
                             json={"playback_tempo": 2.0})
    assert resp.status_code == 422
    assert "fehler" in resp.get_json()


def test_patch_config_unbekanntes_modell_422(client_mini):
    """HSP-40: unbekanntes llm_model → 422."""
    resp = client_mini.patch("/api/v1/hoerspiel/mia/config",
                             json={"llm_model": "claude-ultra-9999"})
    assert resp.status_code == 422


def test_patch_config_mistral_ohne_key_422():
    """HSP-40: llm_provider=mistral ohne Mistral-Key → 422."""
    cfg_ohne_mistral_key = config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5053, log_level="INFO",
        llm_provider="claude", llm_model="claude-opus-4-7",
        anthropic_key="ak", mistral_key=None,  # kein Mistral-Key
        azure_endpoint=None, azure_deployment=None, azure_key=None,
    )
    main_mod.configure(
        runtime_config=cfg_ohne_mistral_key,
        data_config=config_mod.DataConfig(default_voice="shimmer", serien_name="T"),
        data_root="/tmp",
        bot_token="TEST",
    )
    client = main_mod.app.test_client()
    resp = client.patch("/api/v1/hoerspiel/mia/config",
                        json={"llm_provider": "mistral"})
    assert resp.status_code == 422
    assert "mistral" in resp.get_json().get("fehler", "").lower()


def test_patch_config_teilmenge_aendert_genau_diese(client_mini):
    """HSP-40: PATCH mit Teilmenge ändert nur die genannten Felder."""
    # Zuerst aktuellen Stand lesen
    before = client_mini.get("/api/v1/hoerspiel/mia/config").get_json()

    # Nur playback_tempo ändern
    resp = client_mini.patch("/api/v1/hoerspiel/mia/config", json={"playback_tempo": 1.1})
    assert resp.status_code == 200
    body = resp.get_json()
    assert abs(body["playback_tempo"] - 1.1) < 0.01
    # Voice bleibt gleich
    assert body["default_voice"] == before["default_voice"]


# ============================================================
#  HSP-35/37-Audio — Range-Requests (HSP-40)
# ============================================================

def test_audio_endpoint_ohne_range_200(client_mini, data_root_mini):
    """HSP-37: Vollständiger Track ohne Range → 200."""
    # Track anlegen
    resp = client_mini.get(
        "/api/v1/hoerspiel/mia/alben/folge-1/audio/track-02.mp3")
    assert resp.status_code == 200
    assert resp.content_type == "audio/mpeg"
    # Cache-Header
    assert "private" in resp.headers.get("Cache-Control", "")


def test_audio_endpoint_mit_range_206(client_mini):
    """HSP-37: Range-Request → 206 Partial Content."""
    resp = client_mini.get(
        "/api/v1/hoerspiel/mia/alben/folge-1/audio/track-02.mp3",
        headers={"Range": "bytes=0-9"})
    # Flask/Werkzeug unterstützt Range → 206 oder 200 je nach Konditionierung
    assert resp.status_code in (200, 206)
    assert resp.content_type == "audio/mpeg"


def test_audio_endpoint_album_nicht_gefunden_404(client_mini):
    """HSP-37: Album nicht vorhanden → 404."""
    resp = client_mini.get(
        "/api/v1/hoerspiel/mia/alben/folge-999/audio/track-02.mp3")
    assert resp.status_code == 404


# ============================================================
#  HSP-36-Resume (HSP-40)
# ============================================================

def test_resume_get_kein_stand_404(client_mini):
    """HSP-36: kein Resume-Stand → 404."""
    resp = client_mini.get("/api/v1/hoerspiel/mia/resume?album=folge-1")
    assert resp.status_code == 404


def test_resume_put_und_get(client_mini):
    """HSP-36: PUT setzt Stand; GET liest ihn zurück."""
    put_resp = client_mini.put("/api/v1/hoerspiel/mia/resume",
                               json={"album": "folge-1", "track": 3})
    assert put_resp.status_code == 200
    body = put_resp.get_json()
    assert body["album"] == "folge-1"
    assert body["track"] == 3

    get_resp = client_mini.get("/api/v1/hoerspiel/mia/resume?album=folge-1")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["track"] == 3


def test_resume_put_idempotent(client_mini):
    """HSP-36: Zweites PUT mit gleicher Position ist no-op (kein Fehler)."""
    client_mini.put("/api/v1/hoerspiel/mia/resume",
                    json={"album": "folge-1", "track": 2})
    resp2 = client_mini.put("/api/v1/hoerspiel/mia/resume",
                             json={"album": "folge-1", "track": 2})
    assert resp2.status_code == 200
    assert resp2.get_json()["track"] == 2


def test_resume_put_und_get_verschiedene_alben(client_mini):
    """HSP-36: Resume-Stände verschiedener Alben leben separat."""
    client_mini.put("/api/v1/hoerspiel/mia/resume",
                    json={"album": "folge-1", "track": 2})
    client_mini.put("/api/v1/hoerspiel/mia/resume",
                    json={"album": "folge-2", "track": 5})

    r1 = client_mini.get("/api/v1/hoerspiel/mia/resume?album=folge-1").get_json()
    r2 = client_mini.get("/api/v1/hoerspiel/mia/resume?album=folge-2").get_json()
    assert r1["track"] == 2
    assert r2["track"] == 5


# ============================================================
#  HSP-38-Themen (HSP-40)
# ============================================================

def test_themen_alter_4_liefert_8_themen(client_mini):
    """HSP-38: ?alter=4 → 8 V1-Themen aus DataConfig."""
    resp = client_mini.get("/api/v1/hoerspiel/themen?alter=4")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["alter"] == 4
    assert len(body["themen"]) == 8
    assert "Mut beim Probieren" in body["themen"]


def test_themen_unbekanntes_alter_404(client_mini):
    """HSP-38: unbekanntes Alter → 404."""
    resp = client_mini.get("/api/v1/hoerspiel/themen?alter=7")
    assert resp.status_code == 404
    assert "fehler" in resp.get_json()


# ============================================================
#  HSP-40 — Mistral-Adapter AVAILABLE_MODELS-Konstante
# ============================================================

def test_mistral_available_models_konstante():
    """HSP-27b: AVAILABLE_MODELS enthält die 3 V1-Modelle."""
    from hoerspiel.providers.mistral import AVAILABLE_MODELS
    model_ids = [m[0] for m in AVAILABLE_MODELS]
    assert "mistral-large-2411" in model_ids
    assert "mistral-medium-2508" in model_ids
    assert "mistral-small-2503" in model_ids
    assert len(AVAILABLE_MODELS) == 3
    # Jeder Eintrag ist (id, label)
    for mid, label in AVAILABLE_MODELS:
        assert isinstance(mid, str)
        assert mid
        assert isinstance(label, str)
        assert label


def test_claude_available_models_konstante():
    """HSP-27b: Claude AVAILABLE_MODELS enthält die 3 V1-Modelle."""
    from hoerspiel.providers.claude import AVAILABLE_MODELS
    model_ids = [m[0] for m in AVAILABLE_MODELS]
    assert "claude-opus-4-7" in model_ids
    assert "claude-sonnet-4-6" in model_ids
    assert "claude-haiku-4-5" in model_ids
    assert len(AVAILABLE_MODELS) == 3


def test_mistral_provider_complete_mock():
    """HSP-40: MistralProvider.complete mit Mock-API liefert Text."""
    import unittest.mock as mock

    from hoerspiel.providers.mistral import MistralProvider

    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Test-Antwort"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    with mock.patch("httpx.post", return_value=mock_resp):
        provider = MistralProvider(api_key="test-key", model="mistral-large-2411")
        result = provider.complete("System", "User")
    assert result == "Test-Antwort"


def test_mistral_provider_http_fehler_raises_provider_error():
    """HSP-40: HTTP-Fehler von Mistral → ProviderError."""
    import unittest.mock as mock

    from hoerspiel.providers.base import ProviderError
    from hoerspiel.providers.mistral import MistralProvider

    mock_resp = mock.MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    with mock.patch("httpx.post", return_value=mock_resp):
        provider = MistralProvider(api_key="test-key")
        with pytest.raises(ProviderError):
            provider.complete("System", "User")


def test_mistral_provider_complete_structured_mock():
    """HSP-40: MistralProvider.complete_structured mit Mock-API."""
    import json
    import unittest.mock as mock

    from hoerspiel.providers.mistral import MistralProvider

    expected_args = {"titel": "Test", "text": "Text.", "folgen-nr-vorschlag": 1}
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "tool_calls": [{
                    "id": "tc1",
                    "function": {
                        "name": "folgen_vorschlag",
                        "arguments": json.dumps(expected_args),
                    },
                }],
            },
        }],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10},
    }

    with mock.patch("httpx.post", return_value=mock_resp):
        provider = MistralProvider(api_key="test-key")
        result = provider.complete_structured(
            "System", "User",
            tool_name="folgen_vorschlag",
            tool_description="Erzeuge einen Vorschlag",
            input_schema={"type": "object", "properties": {}},
        )
    assert result["titel"] == "Test"
    assert result["text"] == "Text."
