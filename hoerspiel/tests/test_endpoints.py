"""HSP-17 — alle API-Endpoints in spezifizierter JSON-Form.

Seit #908 (URL-3a, HSP-26): alle Pfade tragen `mia` als kind_id.
Cross-kind-Test: Anfrage an fremde kind_id → 404 (HSP-26-Self-Check).
"""

import json
import os
import pathlib
from unittest.mock import patch


def test_folgen_vorschlag_happy_path(client, fake_llm, data_root):
    """ENTRY-PATH-PROBE: POST /folgen-vorschlag mit FakeLLM → 200 + spec-Form.

    Schreibt instance.json mit kind_id=mia und bekanntem name → beweist
    Route→load_instance→LLM-Naht: Name muss im User-Kontext des LLM-Calls landen.
    """
    # instance.json schreiben BEVOR der Request geht — load_instance liest lazy.
    (pathlib.Path(data_root) / "instance.json").write_text(
        json.dumps({"kind_id": "mia", "name": "Mia", "alter": 7,
                    "serien_name": "Stigi & Co."})
    )
    response = client.post("/api/v1/hoerspiel/mia/folgen-vorschlag",
                           json={"idee": "Stigi findet eine Feder."})
    assert response.status_code == 200
    body = response.get_json()
    assert "titel" in body
    assert "text" in body
    assert "folgen-nr-vorschlag" in body
    assert isinstance(body["folgen-nr-vorschlag"], int)
    # LLM wurde genau einmal aufgerufen (Vorschlag, keine Synopse)
    assert len(fake_llm.calls) == 1
    # Route→load_instance→LLM-Naht: geladener Name taucht im User-Kontext auf
    # (fake_llm.calls[0] = (system, user); user enthält "# Instanz-Kontext" + "Für: Mia")
    assert "Mia" in fake_llm.calls[0][1], (
        "load_instance-Name muss im User-Kontext des LLM-Calls stehen"
    )


def test_folgen_vorschlag_leere_idee(client):
    response = client.post("/api/v1/hoerspiel/mia/folgen-vorschlag", json={"idee": ""})
    assert response.status_code == 400


def test_folgen_vorschlag_ohne_anthropic_key_503(client_keyless):
    """HSP-27: kein Anthropic-Key → HTTP 503."""
    response = client_keyless.post("/api/v1/hoerspiel/mia/folgen-vorschlag",
                                   json={"idee": "x"})
    assert response.status_code == 503
    assert "fehler" in response.get_json()


def test_post_alben_baut_und_returnt_spec_form(client, data_root):
    response = client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "T", "text": "Erster Absatz.\n\nZweiter Absatz.",
        "voice": "shimmer", "idee": "x",
    })
    assert response.status_code == 200
    body = response.get_json()
    assert "album-id" in body
    assert "manifest-pfad" in body
    assert "dauer-sek-gesamt" in body
    assert isinstance(body["dauer-sek-gesamt"], int)
    assert os.path.isfile(body["manifest-pfad"])


def test_post_alben_ohne_shared_assets_412(client, data_root):
    """HSP-29: Shared-Assets fehlen → HTTP 412, kein Auto-Rebuild."""
    os.remove(os.path.join(data_root, "shared-assets", "intro_shimmer.mp3"))
    response = client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "T", "text": "Absatz.", "voice": "shimmer", "idee": "x",
    })
    assert response.status_code == 412


def test_post_alben_ungueltige_voice_400(client):
    response = client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "T", "text": "A.", "voice": "nova", "idee": "x",
    })
    assert response.status_code == 400


def test_post_alben_idempotenz_identischer_inhalt(client):
    """HSP-17: identischer Inhalt + Voice → selbe album-id, `cached=True`."""
    body = {"titel": "T", "text": "A.\n\nB.", "voice": "shimmer", "idee": "x"}
    r1 = client.post("/api/v1/hoerspiel/mia/alben", json=body).get_json()
    r2 = client.post("/api/v1/hoerspiel/mia/alben", json=body).get_json()
    assert r1["album-id"] == r2["album-id"]
    assert r2["cached"] is True


def test_get_alben_listet_freigegebene(client):
    client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "T1", "text": "A.\n\nB.", "voice": "shimmer", "idee": "x"})
    client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "T2", "text": "C.\n\nD.", "voice": "onyx", "idee": "y"})
    response = client.get("/api/v1/hoerspiel/mia/alben")
    assert response.status_code == 200
    liste = response.get_json()
    assert len(liste) == 2
    assert {a["voice"] for a in liste} == {"shimmer", "onyx"}


def test_get_manifest_form_und_404(client):
    r = client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "T", "text": "A.\n\nB.", "voice": "shimmer", "idee": "x"})
    aid = r.get_json()["album-id"]
    manifest_response = client.get("/api/v1/hoerspiel/mia/alben/%s/manifest" % aid)
    assert manifest_response.status_code == 200
    assert manifest_response.get_json()["id"] == aid

    not_found = client.get("/api/v1/hoerspiel/mia/alben/folge-999/manifest")
    assert not_found.status_code == 404


def test_get_bible_und_historie_markdown(client):
    r1 = client.get("/api/v1/hoerspiel/mia/bible")
    assert r1.status_code == 200
    assert "Stigi" in r1.get_data(as_text=True)
    r2 = client.get("/api/v1/hoerspiel/mia/folgen-historie")
    assert r2.status_code == 200
    assert "Folge 22" in r2.get_data(as_text=True)


def test_get_config_returnt_provider_und_voice(client):
    response = client.get("/api/v1/hoerspiel/mia/config")
    body = response.get_json()
    assert body["llm_provider"] == "claude"
    assert body["llm_model"] == "claude-opus-4-7"
    assert body["default_voice"] == "shimmer"
    assert body["anthropic_key_set"] is True
    assert body["azure_key_set"] is True


def test_patch_config_mistral_422(client):
    """HSP-17 / HSP-27: PATCH mit mistral → HTTP 422 + Klartext."""
    response = client.patch("/api/v1/hoerspiel/mia/config",
                            json={"llm_provider": "mistral"})
    assert response.status_code == 422
    assert "mistral" in response.get_json()["fehler"].lower()


def test_patch_config_ohne_key_422(client_keyless):
    """HSP-17: Provider-Switch ohne Key wird nicht aktiv."""
    response = client_keyless.patch("/api/v1/hoerspiel/mia/config",
                                    json={"llm_provider": "claude"})
    assert response.status_code == 422


def test_patch_config_modell_wechsel(client):
    """HSP-27b: Modell-Wechsel zu bekanntem Modell → 200 + Echo."""
    response = client.patch("/api/v1/hoerspiel/mia/config",
                            json={"llm_model": "claude-sonnet-4-6"})
    assert response.status_code == 200
    assert response.get_json()["llm_model"] == "claude-sonnet-4-6"


def test_patch_config_unbekanntes_modell_422(client):
    """HSP-27b: Unbekanntes Modell wird abgelehnt → 422."""
    response = client.patch("/api/v1/hoerspiel/mia/config",
                            json={"llm_model": "claude-opus-4-7-x"})
    assert response.status_code == 422


def test_shared_assets_status(client):
    response = client.get("/api/v1/hoerspiel/mia/shared-assets/status")
    body = response.get_json()
    for voice in ("shimmer", "onyx"):
        for art in ("intro", "outro"):
            assert body["%s.%s" % (voice, art)] is True


def test_shared_assets_rebuild_baut_alle(client, fake_tts, data_root):
    response = client.post("/api/v1/hoerspiel/mia/shared-assets/rebuild", json={})
    assert response.status_code == 200
    body = response.get_json()
    assert set(body["rebuilt"]) == {"shimmer.intro", "onyx.intro",
                                     "shimmer.outro", "onyx.outro"}
    assert body["skipped"] == []
    # FakeTTS hat vier Calls bekommen
    assert len(fake_tts.calls) == 4


def test_shared_assets_rebuild_skipped_ohne_quelltext(client, fake_tts, data_root):
    os.remove(os.path.join(data_root, "shared-assets", "intro.txt"))
    response = client.post("/api/v1/hoerspiel/mia/shared-assets/rebuild", json={})
    body = response.get_json()
    assert "shimmer.intro" in body["skipped"]
    assert "onyx.intro" in body["skipped"]
    assert "shimmer.outro" in body["rebuilt"]


def test_data_router_liefert_audio_asset(client, data_root):
    response = client.get("/display/hoerspiel/mia/data/shared-assets/intro_shimmer.mp3")
    assert response.status_code == 200
    assert b"INTRO" in response.get_data()


def test_post_alben_ohne_key_503(client_keyless):
    """HSP-27: ohne LLM-Key kann auch der Bau nicht laufen (Synopse-Call)."""
    response = client_keyless.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "T", "text": "A.", "voice": "shimmer", "idee": "x",
    })
    assert response.status_code == 503


def test_post_alben_manifest_json_form(client):
    """HSP-26: manifest.json hält die spec-Form (id, nummer, tracks, voice, ...)."""
    r = client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "Voll-Test", "text": "A.\n\nB.\n\nC.",
        "voice": "onyx", "idee": "x"}).get_json()
    with open(r["manifest-pfad"]) as f:
        manifest = json.load(f)
    for feld in ("id", "nummer", "titel", "voice", "erstellt-am",
                 "freigegeben", "cover-asset", "tracks", "pikto-hauptbegriffe"):
        assert feld in manifest
    arten = [t["art"] for t in manifest["tracks"]]
    assert arten[0] == "intro"
    assert arten[-1] == "outro"
    assert "inhalt" in arten


def test_display_alben_view(client):
    """ENTRY-PATH-PROBE: GET /display/hoerspiel/mia/alben → alben.html (HSP-26, URL-3a)."""
    response = client.get("/display/hoerspiel/mia/alben")
    assert response.status_code == 200


def test_cross_kind_data_returns_404(client):
    """HSP-26 Self-Check: Anfrage an fremde kind_id → 404 (nicht eigene Instanz)."""
    response = client.get("/display/hoerspiel/finn/data/shared-assets/intro_shimmer.mp3")
    assert response.status_code == 404
    body = response.get_json()
    assert "fehler" in body


def test_cross_kind_api_returns_404(client):
    """HSP-26 Self-Check: API-Anfrage an fremde kind_id → 404."""
    response = client.get("/api/v1/hoerspiel/finn/alben")
    assert response.status_code == 404
    body = response.get_json()
    assert "fehler" in body


def test_post_alben_multivoice_voices_param_durchgereicht(client, data_root, monkeypatch):
    """T1632: POST /alben durchreicht instance.voices an album_builder.baue_album.

    Schreibt instance.json mit Multi-Voice-Map, moxt baue_album, und prüft,
    dass voices=instance.voices tatsächlich übergeben wurde.
    """
    from hoerspiel import album_builder

    # instance.json mit Multi-Voice-Map schreiben (mia ist die Test-Instanz)
    instance_path = pathlib.Path(data_root) / "instance.json"
    instance_path.write_text(json.dumps({
        "kind_id": "mia",
        "name": "Mia",
        "alter": 7,
        "voices": {"KIM": "shimmer", "RUBEN": "onyx"},
    }))

    # baue_album mocken, um die übergebenen Parameter zu prüfen
    captured_kwargs = {}

    def mock_baue_album(**kwargs):
        captured_kwargs.update(kwargs)
        # Original nur für die Struktur aufrufen — Rückgabe vortäuschen
        from hoerspiel.album_builder import BaueErgebnis
        return BaueErgebnis(
            album_id="test-album",
            manifest_pfad=str(pathlib.Path(data_root) / "alben" / "test-album" / "manifest.json"),
            dauer_sek_gesamt=0,
            cached=False,
        )

    with patch.object(album_builder, 'baue_album', side_effect=mock_baue_album):
        response = client.post("/api/v1/hoerspiel/mia/alben", json={
            "titel": "T", "text": "Absatz.",
            "voice": "onyx", "idee": "x",
        })

    assert response.status_code == 200
    # Überprüfe: voices wurde mit der Map aus instance.json übergeben
    assert captured_kwargs.get("voices") == {"KIM": "shimmer", "RUBEN": "onyx"}, (
        "POST /alben muss instance.voices an baue_album durchreichen")


def test_post_alben_manifest_url_kind_id_verdrahtung(client):
    """AC1 / T1027: POST /alben über HTTP-Handler nutzt _self_kind_id() (HSP-26, #968).

    Die Instanz ist als 'mia' konfiguriert (RuntimeConfig.kind_id Default).
    Das Manifest muss deshalb '/display/hoerspiel/mia/data/' in den
    Pfad-Feldern tragen — nicht eine hart codierte Konstante oder eine
    fremde kind_id.
    """
    r = client.post("/api/v1/hoerspiel/mia/alben", json={
        "titel": "Manifest-URL-Test", "text": "A.\n\nB.\n\nC.",
        "voice": "shimmer", "idee": "url-test",
    })
    assert r.status_code == 200, "POST /alben muss 200 zurückgeben"
    body = r.get_json()
    assert "manifest-pfad" in body

    with open(body["manifest-pfad"]) as f:
        manifest = json.load(f)

    cover = manifest.get("cover-asset", "")
    assert "/display/hoerspiel/mia/data/" in cover, (
        "cover-asset muss '/display/hoerspiel/mia/data/' enthalten — "
        "HTTP-Handler muss _self_kind_id() an baue_album weiterreichen (#968, HSP-26). "
        "Tatsächlicher Wert: %r" % cover
    )
    assert "/display/hoerspiel/finn/data/" not in cover, (
        "cover-asset darf keine fremde kind_id ('finn/data/') enthalten"
    )

    # Mindestens ein inhalt-Track muss ebenfalls mia/data/ tragen.
    inhalt_tracks = [t for t in manifest.get("tracks", []) if t.get("art") == "inhalt"]
    assert inhalt_tracks, "mindestens ein inhalt-Track erwartet"
    track_asset = inhalt_tracks[0]["audio-asset"]
    assert "/display/hoerspiel/mia/data/" in track_asset, (
        "inhalt-track audio-asset muss mia/data/ enthalten, nicht: %r" % track_asset
    )


def test_t1382_get_config_kein_stigi_ohne_instanz_serienname(runtime_config, data_root, fake_tts):
    """T1382/AC1+AC2: GET /config ohne serien_name in hoerspiel.json und instance.json
    → serien_name im Response ist neutral leer, kein 'Stigi & Co.'-Leak.

    rot vor Fix: resolve_data-Default war DEFAULT_SERIEN_NAME='Stigi & Co.',
    _build_config_response spiegelte dcfg.serien_name direkt in die Antwort.
    grün nach Fix: neutraler Default '' + instance.json-Vorrang (wie LLM-Pfad :543).
    """
    from hoerspiel import config as config_mod
    from hoerspiel import main as main_mod

    # DataConfig ohne serien_name in hoerspiel.json — Default nach T1382-Fix: ""
    # (vor Fix: "Stigi & Co." aus DEFAULT_SERIEN_NAME).
    neutral_dcfg = config_mod.DataConfig(default_voice="shimmer", serien_name="")
    main_mod.configure(
        runtime_config=runtime_config,
        data_config=neutral_dcfg,
        data_root=data_root,
        llm=None,
        tts_engine=fake_tts,
        bot_token="TEST",
    )
    client = main_mod.app.test_client()

    # instance.json ohne serien_name → instance_cfg.serien_name = ""
    (pathlib.Path(data_root) / "instance.json").write_text(
        json.dumps({"kind_id": "mia", "name": "Mia", "alter": 4})
    )

    resp = client.get("/api/v1/hoerspiel/mia/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["serien_name"] != "Stigi & Co.", (
        "T1382/AC1: kein 'Stigi & Co.'-Leak wenn weder hoerspiel.json "
        "noch instance.json einen serien_name tragen"
    )
    assert body["serien_name"] == "", (
        "T1382/AC2: Display-serien_name muss neutral ('') sein ohne instance.json-serien_name"
    )


def test_t1382_get_config_instance_serienname_hat_vorrang(runtime_config, data_root, fake_tts):
    """T1382: instance.json serien_name überschreibt hoerspiel.json (wie LLM-Pfad).

    Wenn instance.json serien_name='Quasiluxi' trägt und hoerspiel.json keinen
    serien_name setzt, muss GET /config 'Quasiluxi' liefern — nie 'Stigi & Co.'.
    """
    from hoerspiel import config as config_mod
    from hoerspiel import main as main_mod

    neutral_dcfg = config_mod.DataConfig(default_voice="shimmer", serien_name="")
    main_mod.configure(
        runtime_config=runtime_config,
        data_config=neutral_dcfg,
        data_root=data_root,
        llm=None,
        tts_engine=fake_tts,
        bot_token="TEST",
    )
    client = main_mod.app.test_client()

    finn_serie = "Quasiluxi, Alpaki & Haski"
    (pathlib.Path(data_root) / "instance.json").write_text(
        json.dumps({"kind_id": "mia", "name": "Mia", "alter": 4,
                    "serien_name": finn_serie})
    )

    resp = client.get("/api/v1/hoerspiel/mia/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["serien_name"] == finn_serie, (
        "T1382: instance.json serien_name muss im Display-Pfad erscheinen (wie LLM-Pfad)"
    )
