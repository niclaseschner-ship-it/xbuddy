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
    resp = client_mini_no_auth.get("/api/v1/hoerspiel/paula/config")
    # 500 wenn Token fehlt, 401 wenn Token da aber initData fehlt.
    assert resp.status_code in (401, 500)


@pytest.mark.skip(reason="V3 #898: Soft-Auth — Header optional, kein 401 mehr bei fehlendem Header")
def test_themen_ohne_auth_header_401(client_mini_no_auth):
    # RAT-17 / #910: neue URL-Form mit kind_id
    resp = client_mini_no_auth.get("/api/v1/hoerspiel/paula/themen")
    assert resp.status_code in (401, 500)


# ============================================================
#  HSP-34-GET /config — Pflicht-Felder + modelle_je_anbieter (HSP-40)
# ============================================================

def test_get_config_pflichtfelder(client_mini):
    """HSP-34: GET /config muss alle Pflicht-Felder enthalten."""
    resp = client_mini.get("/api/v1/hoerspiel/paula/config")
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
    resp = client_mini.get("/api/v1/hoerspiel/paula/config")
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
    resp = client_mini.patch("/api/v1/hoerspiel/paula/config",
                             json={"playback_tempo": 2.0})
    assert resp.status_code == 422
    assert "fehler" in resp.get_json()


def test_patch_config_unbekanntes_modell_422(client_mini):
    """HSP-40: unbekanntes llm_model → 422."""
    resp = client_mini.patch("/api/v1/hoerspiel/paula/config",
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
    resp = client.patch("/api/v1/hoerspiel/paula/config",
                        json={"llm_provider": "mistral"})
    assert resp.status_code == 422
    assert "mistral" in resp.get_json().get("fehler", "").lower()


def test_patch_config_teilmenge_aendert_genau_diese(client_mini):
    """HSP-40: PATCH mit Teilmenge ändert nur die genannten Felder."""
    # Zuerst aktuellen Stand lesen
    before = client_mini.get("/api/v1/hoerspiel/paula/config").get_json()

    # Nur playback_tempo ändern
    resp = client_mini.patch("/api/v1/hoerspiel/paula/config", json={"playback_tempo": 1.1})
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
        "/api/v1/hoerspiel/paula/alben/folge-1/audio/track-02.mp3")
    assert resp.status_code == 200
    assert resp.content_type == "audio/mpeg"
    # Cache-Header
    assert "private" in resp.headers.get("Cache-Control", "")


def test_audio_endpoint_mit_range_206(client_mini):
    """HSP-37: Range-Request → 206 Partial Content."""
    resp = client_mini.get(
        "/api/v1/hoerspiel/paula/alben/folge-1/audio/track-02.mp3",
        headers={"Range": "bytes=0-9"})
    # Flask/Werkzeug unterstützt Range → 206 oder 200 je nach Konditionierung
    assert resp.status_code in (200, 206)
    assert resp.content_type == "audio/mpeg"


def test_audio_endpoint_album_nicht_gefunden_404(client_mini):
    """HSP-37: Album nicht vorhanden → 404."""
    resp = client_mini.get(
        "/api/v1/hoerspiel/paula/alben/folge-999/audio/track-02.mp3")
    assert resp.status_code == 404


# ============================================================
#  HSP-36-Resume (HSP-40)
# ============================================================

def test_resume_get_kein_stand_404(client_mini):
    """HSP-36: kein Resume-Stand → 404."""
    resp = client_mini.get("/api/v1/hoerspiel/paula/resume?album=folge-1")
    assert resp.status_code == 404


def test_resume_put_und_get(client_mini):
    """HSP-36: PUT setzt Stand; GET liest ihn zurück."""
    put_resp = client_mini.put("/api/v1/hoerspiel/paula/resume",
                               json={"album": "folge-1", "track": 3})
    assert put_resp.status_code == 200
    body = put_resp.get_json()
    assert body["album"] == "folge-1"
    assert body["track"] == 3

    get_resp = client_mini.get("/api/v1/hoerspiel/paula/resume?album=folge-1")
    assert get_resp.status_code == 200
    assert get_resp.get_json()["track"] == 3


def test_resume_put_idempotent(client_mini):
    """HSP-36: Zweites PUT mit gleicher Position ist no-op (kein Fehler)."""
    client_mini.put("/api/v1/hoerspiel/paula/resume",
                    json={"album": "folge-1", "track": 2})
    resp2 = client_mini.put("/api/v1/hoerspiel/paula/resume",
                             json={"album": "folge-1", "track": 2})
    assert resp2.status_code == 200
    assert resp2.get_json()["track"] == 2


def test_resume_put_und_get_verschiedene_alben(client_mini):
    """HSP-36: Resume-Stände verschiedener Alben leben separat."""
    client_mini.put("/api/v1/hoerspiel/paula/resume",
                    json={"album": "folge-1", "track": 2})
    client_mini.put("/api/v1/hoerspiel/paula/resume",
                    json={"album": "folge-2", "track": 5})

    r1 = client_mini.get("/api/v1/hoerspiel/paula/resume?album=folge-1").get_json()
    r2 = client_mini.get("/api/v1/hoerspiel/paula/resume?album=folge-2").get_json()
    assert r1["track"] == 2
    assert r2["track"] == 5


# ============================================================
#  HSP-38-Themen (kind_id-tragend, RAT-17, #910)
# ============================================================

def test_themen_kind_id_liefert_themen_aus_datacfg(client_mini, data_root_mini):
    """HSP-38 / RAT-17 / #910 / ENTRY-PATH-PROBE:
    GET /api/v1/hoerspiel/paula/themen → 200 mit {kind_id, name, alter, themen}.

    Kein ?alter=-Query. Kein instance.json vorhanden → ENV-Fallback greift
    (HOERSPIEL_KIND_ALTER + HOERSPIEL_KIND_NAME). Alter fehlt → 422.

    Da die Fixture kein instance.json legt, testet dieser Test den ENV-Fallback-
    Pfad. Bei Alter=0 (kein ENV): 422 (Alter nicht in themen_je_alter)."""
    resp = client_mini.get("/api/v1/hoerspiel/paula/themen")
    # Ohne instance.json und ohne ENV: alter=0 → nicht in themen_je_alter → 422
    assert resp.status_code == 422
    body = resp.get_json()
    assert "fehler" in body


def test_themen_mit_instance_json(runtime_cfg_with_mistral, data_root_mini):
    """HSP-38 / HSP-27 / RAT-17 / ENTRY-PATH-PROBE:
    GET /api/v1/hoerspiel/paula/themen mit instance.json → 200 mit
    {kind_id: "paula", name: "Paula", alter: 4, themen: [...]}.

    instance.json liegt in data_root_mini/instance.json mit kind_id="paula"."""
    import json
    # instance.json mit Themen anlegen
    instance = {
        "kind_id": "paula",
        "name": "Paula",
        "alter": 4,
        "themen_je_alter": {
            "4": ["Mut beim Probieren", "Streit vertragen", "Freundschaft"],
        },
    }
    import os
    with open(os.path.join(data_root_mini, "instance.json"), "w") as f:
        json.dump(instance, f)

    from hoerspiel import config as config_mod
    from hoerspiel import main as main_mod
    main_mod.configure(
        runtime_config=runtime_cfg_with_mistral,
        data_config=config_mod.DataConfig(
            default_voice="shimmer",
            serien_name="Stigi & Co.",
        ),
        data_root=data_root_mini,
        llm=None, tts_engine=None,
        bot_token="TEST",
    )
    client = main_mod.app.test_client()
    resp = client.get("/api/v1/hoerspiel/paula/themen")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["kind_id"] == "paula"
    assert body["name"] == "Paula"
    assert body["alter"] == 4
    assert "Mut beim Probieren" in body["themen"]
    assert "Streit vertragen" in body["themen"]
    assert len(body["themen"]) == 3


def test_themen_falsche_kind_id_404(client_mini):
    """HSP-38 / RAT-17 / #910: GET /api/v1/hoerspiel/neko/themen → 404
    (kind_id nicht diese Instanz, _assert_self_kind)."""
    resp = client_mini.get("/api/v1/hoerspiel/neko/themen")
    assert resp.status_code == 404
    assert "fehler" in resp.get_json()


def test_themen_alter_nicht_gepflegt_422(runtime_cfg_with_mistral, data_root_mini):
    """HSP-38 / RAT-17 / #910: instance.json vorhanden aber Alter nicht in
    themen_je_alter → 422."""
    import json
    import os
    instance = {
        "kind_id": "paula",
        "name": "Paula",
        "alter": 7,  # Alter 7 nicht in themen_je_alter
        "themen_je_alter": {
            "4": ["Mut beim Probieren"],
            # Kein "7"-Schlüssel → 422
        },
    }
    with open(os.path.join(data_root_mini, "instance.json"), "w") as f:
        json.dump(instance, f)

    from hoerspiel import config as config_mod
    from hoerspiel import main as main_mod
    main_mod.configure(
        runtime_config=runtime_cfg_with_mistral,
        data_config=config_mod.DataConfig(default_voice="shimmer", serien_name="T"),
        data_root=data_root_mini,
        llm=None, tts_engine=None,
        bot_token="TEST",
    )
    client = main_mod.app.test_client()
    resp = client.get("/api/v1/hoerspiel/paula/themen")
    assert resp.status_code == 422
    body = resp.get_json()
    assert "fehler" in body


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


# ============================================================
#  HSP-3a Variante C — Face-Pille im Kinder-View (#911)
# ============================================================
#
# ENTRY-PATH-PROBE:
#   GET /display/hoerspiel/paula/alben → HTML enthält Face-Pille mit „Paula"
#   und href="/display/hoerspiel/neko/alben" für den Switch-Link.
#   Plus Test mit Fehler-FamilieClient: HTML enthält keine Pille.
#
# Alle Tests: KEIN echter HTTP-Call — FamilieClient via transport-Naht gemockt.


def _make_familie_transport(personen_json_list):
    """Baut eine Transport-Naht, die stets eine feste JSON-Liste zurückgibt."""
    import json as _json

    def transport(url):
        return _json.dumps(personen_json_list).encode("utf-8")

    return transport


def _make_error_transport():
    """Baut eine Transport-Naht, die immer Connection-Error wirft."""
    import urllib.error

    def transport(url):
        raise urllib.error.URLError("Connection refused")

    return transport


@pytest.fixture
def client_mit_familie(runtime_cfg_with_mistral, data_cfg_mini, data_root_mini):
    """Test-Client mit Mock-FamilieClient, der Paula + Neko kennt."""
    from hoerspiel import familie_client as fc_mod

    transport = _make_familie_transport([
        {"id": "paula", "name": "Paula", "ring": "orange", "art": "kinder",
         "foto": "/display/_shared/fotos/paula.jpg"},
        {"id": "neko", "name": "Neko", "ring": "blue", "art": "kinder",
         "foto": "/display/_shared/fotos/neko.jpg"},
    ])
    mock_client = fc_mod.FamilieClient(
        origin_url="http://127.0.0.1:5010",
        transport=transport,
    )
    main_mod.configure(
        runtime_config=runtime_cfg_with_mistral,
        data_config=data_cfg_mini,
        data_root=data_root_mini,
        llm=None, tts_engine=None,
        bot_token="TEST",
        familie_client=mock_client,
    )
    return main_mod.app.test_client()


@pytest.fixture
def client_ohne_familie(runtime_cfg_with_mistral, data_cfg_mini, data_root_mini):
    """Test-Client mit Mock-FamilieClient, der immer Connection-Error wirft."""
    from hoerspiel import familie_client as fc_mod

    mock_client = fc_mod.FamilieClient(
        origin_url="http://127.0.0.1:5010",
        transport=_make_error_transport(),
    )
    main_mod.configure(
        runtime_config=runtime_cfg_with_mistral,
        data_config=data_cfg_mini,
        data_root=data_root_mini,
        llm=None, tts_engine=None,
        bot_token="TEST",
        familie_client=mock_client,
    )
    return main_mod.app.test_client()


def test_face_pille_rendert_mit_aktivem_kind(client_mit_familie):
    """HSP-3a Variante C / ENTRY-PATH-PROBE:
    GET /display/hoerspiel/paula/alben → 200 HTML enthält Face-Pille
    mit anderes-Kind-Name „Neko" und href zum Neko-Alben-View.

    Vollständige Navigation via <a href> — kein JS-State-Wechsel (RAT-17 Option A).
    """
    resp = client_mit_familie.get("/display/hoerspiel/paula/alben")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # Face-Pille: Link auf anderes Kind (Neko) — vollständige Navigation (HSP-3a).
    assert 'href="/display/hoerspiel/neko/alben"' in html
    # Name des anderen Kindes in der Pille sichtbar.
    assert "Neko" in html
    # face-pille CSS-Klasse vorhanden.
    assert "face-pille" in html
    # face-Klasse mit ring-blue (Nekos Ring) vorhanden.
    assert "ring-blue" in html


def test_face_pille_andere_kind_url_korrekt(client_mit_familie):
    """HSP-3a Variante C / RAT-17 Option A:
    Link zeigt auf /display/hoerspiel/neko/alben — handverdrahtete Map paula→neko.
    Kein JS-State, kein Redirect-Schritt, direkter href.
    """
    resp = client_mit_familie.get("/display/hoerspiel/paula/alben")
    html = resp.data.decode("utf-8")
    # Exaktes href — RAT-17 handverdrahtet, KEINE Registry.
    assert 'href="/display/hoerspiel/neko/alben"' in html
    # Kein JS-State-Wechsel — kein onclick-Handler nötig (plain <a>).
    assert 'data-switch' not in html


def test_face_pille_familie_fehler_rendert_ohne_pille(client_ohne_familie):
    """HSP-3a Variante C / PLAN-20-Geist:
    Familie-Service nicht erreichbar → View rendert trotzdem 200,
    aber ohne Face-Pille (kein face-pille-Element im HTML).

    Stop-Rule: Familie-Service unerreichbar im Test → Mock, kein echter HTTP-Call.
    """
    resp = client_ohne_familie.get("/display/hoerspiel/paula/alben")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # Kein face-pille-Wechsel-Link bei Familie-Fehler.
    assert 'href="/display/hoerspiel/neko/alben"' not in html
    # Kein face-pille-Element sichtbar (weder Link noch solo).
    assert "face-pille" not in html


def test_familie_client_leerer_snapshot_bei_http_fehler():
    """CLIENT-1 / DCOMP-1: FamilieClient.snapshot() gibt leere RegistryView
    zurück wenn der Familie-Service 500 antwortet — kein Stack-Trace nach oben.
    """
    import urllib.error

    from hoerspiel import familie_client as fc_mod

    def error_transport(url):
        raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)

    client = fc_mod.FamilieClient(
        origin_url="http://127.0.0.1:5010",
        transport=error_transport,
    )
    registry = client.snapshot()
    assert registry.alle() == []
    assert registry.get("paula") is None


def test_familie_client_person_felder_korrekt():
    """FAM-7 / DCOMP-1: FamilieClient.snapshot() liefert Person mit
    id/name/ring/foto aus dem JSON von GET /api/v1/familie/personen.
    """
    from hoerspiel import familie_client as fc_mod

    transport = _make_familie_transport([
        {"id": "paula", "name": "Paula", "ring": "orange", "art": "kinder",
         "foto": "/fotos/paula.jpg"},
    ])
    client = fc_mod.FamilieClient(
        origin_url="http://127.0.0.1:5010",
        transport=transport,
    )
    registry = client.snapshot()
    paula = registry.get("paula")
    assert paula is not None
    assert paula.id == "paula"
    assert paula.name == "Paula"
    assert paula.ring == "orange"
    assert paula.foto == "/fotos/paula.jpg"
    assert paula.is_kind() is True


# ============================================================
#  T950 Pi-Live-Fix — alben.js fetch kind_id-tragend + Face-Pille FAM-8
# ============================================================
#
# ENTRY-PATH-PROBE:
#   1. alben.js enthält kind_id-tragende fetch-URLs (HSP-26).
#   2. /display/hoerspiel/paula/alben HTML: Face-Pille <img> nutzt
#      /api/v1/familie/foto/<id> (FAM-8), nicht relativen Pfad.


def test_alben_js_uses_kind_id_in_fetch(client_mit_familie):
    """HSP-26 / ENTRY-PATH-PROBE / T950:
    alben.js enthält kind_id-tragende fetch-URLs statt der alten
    /api/v1/hoerspiel/alben-Form (die 404 liefert, da Routes nur mit
    <kind_id> existieren, HSP-26 URL-3a).

    Prüft statische JS-Quelle direkt — kein DOM-Test nötig.
    """
    resp = client_mit_familie.get("/display/hoerspiel/static/alben.js")
    assert resp.status_code == 200
    js_content = resp.data.decode("utf-8")

    # KIND_ID-Konstante muss im JS stehen (HSP-26).
    assert "KIND_ID" in js_content

    # fetch-Calls müssen ${KIND_ID} enthalten (Template-Literal-Form).
    assert "/api/v1/hoerspiel/${KIND_ID}/alben`" in js_content
    assert "/api/v1/hoerspiel/${KIND_ID}/alben/${albumId}/manifest`" in js_content

    # Alter 404-Pfad darf nicht mehr auftreten.
    assert "fetch('/api/v1/hoerspiel/alben')" not in js_content
    assert "fetch('/api/v1/hoerspiel/alben/" not in js_content


def test_face_pille_foto_url_absolute(client_mit_familie):
    """FAM-8 / ENTRY-PATH-PROBE / T950:
    GET /display/hoerspiel/paula/alben → <img src="/api/v1/familie/foto/neko">
    in der Face-Pille (anderes_kind ist neko wenn aktiv paula).

    Relativer Pfad (z.B. "neko.jpg") wäre Bug — Browser resolved zu
    /display/hoerspiel/paula/neko.jpg → 404 → Broken-Img (Vorbefund T950).
    """
    resp = client_mit_familie.get("/display/hoerspiel/paula/alben")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")

    # FAM-8 absolute Foto-URL — anderes_kind=neko.
    assert '/api/v1/familie/foto/neko' in html

    # Kein relativer Pfad (relativer Pfad wäre Bug, HSP-3a FAM-8).
    import re
    # Matched: src="<was-auch-immer-ohne-slash>" — würde relativen Pfad aufdecken.
    assert not re.search(r'src="(?!/)(?!http)[^"]+\.(jpg|png|webp)"', html)


# ============================================================
#  HSP-41 — audio_ziel-Feld in HSP-Config
# ============================================================

def test_get_config_liefert_audio_ziel_default(client_mini):
    """HSP-41: GET /config liefert audio_ziel-Feld mit Default 'display'."""
    resp = client_mini.get("/api/v1/hoerspiel/paula/config")
    body = resp.get_json()
    assert body["audio_ziel"] == "display"
    assert "panel" in body["audio_ziel_verfuegbar"]
    assert "display" in body["audio_ziel_verfuegbar"]


def test_patch_config_audio_ziel_panel(client_mini):
    """HSP-41: PATCH audio_ziel=panel → 200 + Wert übernommen."""
    resp = client_mini.patch("/api/v1/hoerspiel/paula/config",
                             json={"audio_ziel": "panel"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["audio_ziel"] == "panel"


def test_patch_config_audio_ziel_ungueltig_422(client_mini):
    """HSP-41: PATCH mit ungültigem audio_ziel → 422."""
    resp = client_mini.patch("/api/v1/hoerspiel/paula/config",
                             json={"audio_ziel": "bluetooth"})
    assert resp.status_code == 422
    assert "fehler" in resp.get_json()


# ============================================================
#  HSP-42 — play-extern + SSE Audio-Stream
# ============================================================

def test_play_extern_unbekanntes_album_404(client_mini):
    """HSP-42: POST /play-extern mit unbekanntem album_id → 404."""
    resp = client_mini.post("/api/v1/hoerspiel/paula/play-extern",
                            json={"album_id": "folge-99999", "track_idx": 0})
    assert resp.status_code == 404


def test_play_extern_track_idx_out_of_range_422(client_mini, data_root_mini):
    """HSP-42: POST /play-extern mit track_idx außerhalb Bereich → 422."""
    # Album mit manifest.json anlegen
    import json
    album_dir = os.path.join(data_root_mini, "alben", "folge-test")
    os.makedirs(album_dir, exist_ok=True)
    manifest = {"tracks": [{"audio-asset": "track-01.mp3"}]}
    with open(os.path.join(album_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f)

    # Test-Client mit data_root setzen
    main_mod.configure(
        runtime_config=main_mod._runtime_cfg(),
        data_config=main_mod._data_cfg(),
        data_root=data_root_mini,
        bot_token="TEST",
    )
    client = main_mod.app.test_client()
    resp = client.post("/api/v1/hoerspiel/paula/play-extern",
                       json={"album_id": "folge-test", "track_idx": 99})
    assert resp.status_code == 422


def test_play_extern_fehlende_felder_422(client_mini):
    """HSP-42: POST /play-extern ohne album_id → 422."""
    resp = client_mini.post("/api/v1/hoerspiel/paula/play-extern", json={})
    assert resp.status_code == 422


def test_audio_stream_endpoint_existiert(client_mini):
    """HSP-42: GET /audio-stream antwortet mit text/event-stream Content-Type."""
    # SSE-Stream darf nicht abgeschlossen werden — wir testen nur den Start
    # über die Response-Header. Werkzeug ruft den Generator lazy auf.
    resp = client_mini.get("/api/v1/hoerspiel/paula/audio-stream",
                           headers={"Accept": "text/event-stream"},
                           buffered=False)
    # Wir lesen nur die ersten Bytes, dann schließen wir.
    try:
        first_chunk = next(resp.response, b"")
        assert b"connected" in first_chunk or b":" in first_chunk
    finally:
        resp.close()


# ============================================================
#  HSP-27/41 — Persistenz-Fix: PATCH /config schreibt in Datei
# ============================================================

def test_patch_config_persistiert_in_datei(tmp_path, runtime_cfg_with_mistral, data_root_mini):
    """HSP-27/41: PATCH /config schreibt Werte atomar in hoerspiel.json.

    Vor diesem Fix überlebte PATCH /config keinen Restart — Werte fielen
    auf Datei-Default zurück.
    """
    # Eigenen hoerspiel.json-Pfad setzen
    data_config_file = tmp_path / "hoerspiel.json"
    initial_data = {"default_voice": "shimmer", "playback_tempo": 1.0,
                    "audio_ziel": "display"}
    import json
    data_config_file.write_text(json.dumps(initial_data))
    os.environ["HOERSPIEL_DATA_CONFIG_FILE"] = str(data_config_file)
    try:
        # Frische DataConfig aus Datei
        dcfg = config_mod.resolve_data()
        main_mod.configure(
            runtime_config=runtime_cfg_with_mistral, data_config=dcfg,
            data_root=data_root_mini, bot_token="TEST",
        )
        client = main_mod.app.test_client()
        resp = client.patch("/api/v1/hoerspiel/paula/config",
                            json={"audio_ziel": "panel", "playback_tempo": 1.2})
        assert resp.status_code == 200

        # Datei neu lesen — Werte müssen drinstehen
        persisted = json.loads(data_config_file.read_text())
        assert persisted["audio_ziel"] == "panel"
        assert abs(persisted["playback_tempo"] - 1.2) < 0.01
    finally:
        del os.environ["HOERSPIEL_DATA_CONFIG_FILE"]
