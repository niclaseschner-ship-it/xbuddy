"""Routine-Buddy — Tests für PUT /api/v1/routine/config (ROUTINE-14, ROUTINE-18, #343).

Abdeckung (ROUTINE-18):
  AC1   Gültiges PUT persistiert atomar + per Reload-on-Read sichtbar (DCOMP-3/DCOMP-4)
  AC2   Ungültiges Format / ungültiger Wochentags-Key / negativer vorlauf → 400, kein Teil-Write
  AC_ENTRY  Echter Runtime-Pfad: PUT trifft routine/main.py-Handler (Flask test_client)

Alle Tests laufen OHNE Netz.
"""

import json
import os
import sys
import tempfile

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod   # noqa: E402  # isort:skip
from routine import main as main_mod       # noqa: E402  # isort:skip
from routine.tests._test_auth import (    # noqa: E402  # isort:skip
    TEST_BOT_TOKEN,
    patch_client_auth,
)
from routine.tests.conftest import mit_session_cookie  # noqa: E402  # isort:skip


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def data_path_und_client(tmp_path):
    """Flask-Test-Client + data_path für Tests mit echtem Reload-on-Read.

    data_path wird als routine.json-Pfad konfiguriert, damit der
    PUT-Endpoint wirklich schreiben kann und der GET-Pfad frisch liest
    (AC_ENTRY, AC1).
    """
    data_file = tmp_path / "routine.json"
    # Grundzustand in die Datei schreiben — vier Default-Punkte
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "aufstehzeit": "07:00",
        "zeitzone": "Europe/Berlin",
        "items": [
            {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626", "quelle": "default"},
        ],
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "routine_store.json")
    cfg = config_mod.resolve_data(str(data_file))
    main_mod.configure(cfg, data_path=str(data_file), store_path=store_path,
                       bot_token=TEST_BOT_TOKEN, init_data_config={"max_age_seconds": 86400})
    client = mit_session_cookie(patch_client_auth(main_mod.app.test_client()))
    return str(data_file), client


# ============================================================
#  AC_ENTRY — Echter Runtime-Pfad: PUT trifft den Flask-Handler
# ============================================================

def test_ac_entry_put_trifft_flask_handler(data_path_und_client):
    """AC_ENTRY: PUT /api/v1/routine/config trifft routine/main.py-Handler (nicht isolierte Funktion).

    Beleg: Flask test_client PUT → HTTP 200 + {"ok": true}.
    """
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "08:15"},
                      content_type="application/json")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body.get("ok") is True


# ============================================================
#  AC1 — Gültiges PUT persistiert + Reload-on-Read sichtbar
# ============================================================

def test_ac1_gueltiges_put_persistiert_in_json(data_path_und_client):
    """AC1: gültiges PUT schreibt in routine.json (DCOMP-4, atomar)."""
    data_path, client = data_path_und_client

    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "08:00"},
                      content_type="application/json")
    assert resp.status_code == 200

    # Datei-Inhalt prüfen
    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    assert gespeichert["abfahrtszeit"] == "08:00"


def test_ac1_put_sichtbar_per_reload_on_read(data_path_und_client):
    """AC1: nach erfolgreichem PUT ist die neue Zeit per Reload-on-Read
    ohne Neustart auf /display/routine/morgen sichtbar (DCOMP-3, EC-21).
    """
    _, client = data_path_und_client

    # Neue Abfahrtszeit setzen
    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "09:30"},
                      content_type="application/json")
    assert resp.status_code == 200

    # View abrufen — neue Zeit muss ohne Service-Neustart sichtbar sein
    view_resp = client.get("/display/routine/morgen")
    assert view_resp.status_code == 200
    body = view_resp.get_data(as_text=True)
    assert "09:30" in body, (
        "Neue Abfahrtszeit '09:30' muss nach PUT per Reload-on-Read "
        "auf /display/routine/morgen sichtbar sein (ROUTINE-14, DCOMP-3)"
    )


def test_ac1_put_aufstehzeit(data_path_und_client):
    """AC1: PUT mit aufstehzeit schreibt und ist per Reload-on-Read sichtbar."""
    data_path, client = data_path_und_client

    resp = client.put("/api/v1/routine/config",
                      json={"aufstehzeit": "06:30"},
                      content_type="application/json")
    assert resp.status_code == 200

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    assert gespeichert["aufstehzeit"] == "06:30"

    # Frischer Read bringt neuen Wert
    neue_cfg = config_mod.resolve_data(data_path)
    assert neue_cfg.aufstehzeit == "06:30"


def test_ac1_put_anzieh_vorlauf_min(data_path_und_client):
    """AC1: PUT mit anzieh_vorlauf_min (int ≥ 0) persistiert."""
    data_path, client = data_path_und_client

    resp = client.put("/api/v1/routine/config",
                      json={"anzieh_vorlauf_min": 15},
                      content_type="application/json")
    assert resp.status_code == 200

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    assert gespeichert["anzieh_vorlauf_min"] == 15


def test_ac1_put_mehrere_felder_gleichzeitig(data_path_und_client):
    """AC1: PUT mit mehreren Feldern schreibt alle atomar."""
    data_path, client = data_path_und_client

    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "08:10", "aufstehzeit": "06:45", "anzieh_vorlauf_min": 10},
                      content_type="application/json")
    assert resp.status_code == 200

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    assert gespeichert["abfahrtszeit"] == "08:10"
    assert gespeichert["aufstehzeit"] == "06:45"
    assert gespeichert["anzieh_vorlauf_min"] == 10


def test_ac1_put_wochentag_map(data_path_und_client):
    """AC1: PUT mit Wochentag-Map (lowercase API-Keys) persistiert als capitalized File-Form.

    API akzeptiert lowercase (mo/di/..., ROUTINE-14); routine.json speichert
    capitalized (Mo/Di/..., ROUTINE-12) — exakt die Form, die uhr.py liest.
    """
    data_path, client = data_path_und_client

    wochentag_map = {"mo": "07:30", "di": "07:30", "mi": "07:30",
                     "do": "07:30", "fr": "07:30", "sa": "", "so": ""}
    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": wochentag_map},
                      content_type="application/json")
    assert resp.status_code == 200

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    # Datei muss capitalized Keys enthalten (ROUTINE-12: File-Format = Mo/Di/...)
    assert isinstance(gespeichert["abfahrtszeit"], dict)
    assert gespeichert["abfahrtszeit"]["Mo"] == "07:30", (
        "write_data muss lowercase 'mo' auf capitalized 'Mo' normalisieren "
        "(ROUTINE-12/-14: API-lowercase→File-capitalized)"
    )
    assert gespeichert["abfahrtszeit"]["Sa"] == "", (
        "write_data muss lowercase 'sa' auf capitalized 'Sa' normalisieren"
    )
    # lowercase-Keys dürfen NICHT mehr in der Datei stehen
    assert "mo" not in gespeichert["abfahrtszeit"], (
        "lowercase 'mo' darf nicht in routine.json stehen — uhr.py findet ihn nicht"
    )


def test_acfix2_put_wochentag_map_rendert_auf_display(data_path_und_client):
    """ACFIX2: PUT Wochentag-Map → GET /display/routine/morgen rendert die gesetzte Zeit.

    Entry-Path-Beleg (ACFIX1+ACFIX2): write_data normalisiert lowercase→capitalized,
    uhr.py findet den Key und rendert die Zeit auf /display/routine/morgen.

    Alle 7 Wochentage bekommen dieselbe Zeit — Test läuft deterministisch
    unabhängig vom aktuellen Wochentag (kein now-Mock nötig).
    """
    _, client = data_path_und_client

    # Setze für jeden Wochentag dieselbe Zeit (07:42 — leicht erkennbarer Wert)
    alle_tage = {"mo": "07:42", "di": "07:42", "mi": "07:42",
                 "do": "07:42", "fr": "07:42", "sa": "07:42", "so": "07:42"}
    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": alle_tage},
                      content_type="application/json")
    assert resp.status_code == 200

    # GET /display/routine/morgen: die gesetzte Zeit muss sichtbar sein
    view_resp = client.get("/display/routine/morgen")
    assert view_resp.status_code == 200
    body = view_resp.get_data(as_text=True)
    assert "07:42" in body, (
        "Wochentag-Map-Zeit '07:42' muss nach PUT auf /display/routine/morgen "
        "sichtbar sein — write_data muss lowercase-Keys in capitalized File-Form "
        "normalisieren, damit uhr.py die Map-Zeit findet (ROUTINE-12/-14)"
    )


def test_ac1_put_bewahrt_nicht_geaenderte_felder(data_path_und_client):
    """AC1: PUT mit nur abfahrtszeit überschreibt nicht die items-Liste."""
    data_path, client = data_path_und_client

    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "08:00"},
                      content_type="application/json")
    assert resp.status_code == 200

    with open(data_path, encoding="utf-8") as f:
        gespeichert = json.load(f)
    # items-Liste bleibt erhalten (kein Teil-Verlust durch Merge)
    assert "items" in gespeichert
    assert len(gespeichert["items"]) >= 1


# ============================================================
#  AC1 — Atomares Schreiben (DCOMP-4)
# ============================================================

def test_ac1_atomares_schreiben_via_write_data(tmp_path):
    """AC1/DCOMP-4: write_data schreibt atomar — Temp+Replace, keine halb-geschriebene Datei.

    Geprüft: nach write_data() ist die Zieldatei gültig lesbar (nicht leer/kaputt).
    """
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({"abfahrtszeit": "07:00", "items": []}))

    config_mod.write_data(str(data_file), {"abfahrtszeit": "08:00"})

    # Datei ist atomar komplett — kein kaputtes JSON
    with open(str(data_file), encoding="utf-8") as f:
        inhalt = json.load(f)
    assert inhalt["abfahrtszeit"] == "08:00"


def test_ac1_last_known_good_bei_kaputtem_read(tmp_path):
    """AC1/DCOMP-3: Reload-on-Read fällt bei kaputtem Read auf Last-Known-Good zurück.

    Simulated: data_path zeigt auf kaputte JSON-Datei → _current_config() gibt
    den letzten validen Snapshot zurück, NICHT Code-Defaults.
    """
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "09:00",  # erkennbarer Wert — kein Default
        "items": [],
        "zeitzone": "Europe/Berlin",
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    store_path = str(tmp_path / "store.json")
    guter_snapshot = config_mod.resolve_data(str(data_file))
    main_mod.configure(guter_snapshot, data_path=str(data_file), store_path=store_path)

    # Datei kaputt machen
    data_file.write_text("{ ungültiges JSON !!!")

    # _current_config() muss den Snapshot zurückgeben (nicht Code-Default '08:30')
    cfg = main_mod._current_config()
    assert cfg.abfahrtszeit == "09:00", (
        "DCOMP-3: bei kaputtem Read muss der Last-Known-Good-Snapshot "
        "zurückgegeben werden (nicht Code-Default '08:30')"
    )


# ============================================================
#  AC2 — Ungültige Eingaben → 400, kein Teil-Write
# ============================================================

def test_ac2_ungültiges_zeitformat_gibt_400(data_path_und_client):
    """AC2: ungültiges Zeitformat → 400, kein Schreiben."""
    data_path, client = data_path_und_client

    # Originale Abfahrtszeit merken
    with open(data_path) as f:
        alt = json.load(f)["abfahrtszeit"]

    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "8:30"},  # fehlendes Nullpadding
                      content_type="application/json")
    assert resp.status_code == 400

    # Datei NICHT geändert (kein Teil-Write)
    with open(data_path) as f:
        neu = json.load(f)["abfahrtszeit"]
    assert neu == alt


def test_ac2_stunden_ausserhalb_range(data_path_und_client):
    """AC2: Stunden > 23 → 400."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "25:00"},
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac2_ungültiger_wochentags_key(data_path_und_client):
    """AC2: ungültiger Wochentags-Key in Map → 400, kein Teil-Write (ROUTINE-14)."""
    data_path, client = data_path_und_client

    with open(data_path) as f:
        alt = json.load(f)["abfahrtszeit"]

    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": {"monday": "07:30"}},  # englischer Key → ungültig
                      content_type="application/json")
    assert resp.status_code == 400

    with open(data_path) as f:
        neu = json.load(f)["abfahrtszeit"]
    assert neu == alt


def test_ac2_negativer_vorlauf(data_path_und_client):
    """AC2: anzieh_vorlauf_min < 0 → 400 (ROUTINE-14)."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={"anzieh_vorlauf_min": -5},
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac2_vorlauf_als_string(data_path_und_client):
    """AC2: anzieh_vorlauf_min als String statt Integer → 400."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={"anzieh_vorlauf_min": "8"},
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac2_vorlauf_als_bool(data_path_und_client):
    """AC2: anzieh_vorlauf_min als bool → 400 (bool ist kein int im fachlichen Sinne)."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={"anzieh_vorlauf_min": True},
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac2_kein_gueltiger_schluessel(data_path_und_client):
    """AC2: Payload ohne gültigen Schlüssel → 400, kein Schreiben."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={"items": []},  # items ist nicht schreibbar über diesen Endpoint
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac2_leerer_body(data_path_und_client):
    """AC2: leerer JSON-Body → 400."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={},
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac2_kein_teil_write_bei_gemischtem_payload(data_path_und_client):
    """AC2: Payload mit einem gültigen und einem ungültigen Feld → 400, KEIN Teil-Write.

    Weder der gültige noch der ungültige Wert darf geschrieben werden.
    """
    data_path, client = data_path_und_client

    with open(data_path) as f:
        alt = json.load(f)

    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": "08:00",    # gültig
                            "anzieh_vorlauf_min": -3},  # ungültig → kein Write
                      content_type="application/json")
    assert resp.status_code == 400

    with open(data_path) as f:
        neu = json.load(f)
    # Weder abfahrtszeit noch vorlauf darf geändert sein
    assert neu.get("abfahrtszeit") == alt.get("abfahrtszeit"), \
        "Kein Teil-Write: abfahrtszeit darf nicht geändert sein"
    assert neu.get("anzieh_vorlauf_min") == alt.get("anzieh_vorlauf_min"), \
        "Kein Teil-Write: anzieh_vorlauf_min darf nicht geändert sein"


def test_ac2_wochentags_zeitformat_in_map(data_path_und_client):
    """AC2: ungültiges Zeitformat in einem Wochentags-Map-Wert → 400."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      json={"abfahrtszeit": {"mo": "7:30"}},  # fehlende Null
                      content_type="application/json")
    assert resp.status_code == 400


def test_ac2_kein_json_body(data_path_und_client):
    """AC2: fehlender/nicht-JSON-Body → 400."""
    _, client = data_path_und_client
    resp = client.put("/api/v1/routine/config",
                      data="kein json",
                      content_type="text/plain")
    assert resp.status_code == 400


# ============================================================
#  Validierungs-Einheit — config_mod.write_data direkt
# ============================================================

def test_write_data_fehlende_datei_legt_neu_an(tmp_path):
    """write_data legt routine.json neu an, wenn sie fehlt (fehlende Datei = leere Basis)."""
    data_file = tmp_path / "routine.json"
    assert not data_file.exists()

    config_mod.write_data(str(data_file), {"abfahrtszeit": "07:00"})

    assert data_file.exists()
    with open(str(data_file)) as f:
        inhalt = json.load(f)
    assert inhalt["abfahrtszeit"] == "07:00"


def test_write_data_validation_error_vor_schreiben(tmp_path):
    """write_data wirft ValidationError BEVOR die Datei berührt wird (kein Teil-Write)."""
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({"abfahrtszeit": "07:00"}))

    with pytest.raises(config_mod.ValidationError):
        config_mod.write_data(str(data_file), {"abfahrtszeit": "nein"})

    # Datei unverändert
    with open(str(data_file)) as f:
        inhalt = json.load(f)
    assert inhalt["abfahrtszeit"] == "07:00"


def test_write_data_gueltige_wochentags_keys():
    """write_data akzeptiert alle gültigen Wochentags-Keys (mo,di,mi,do,fr,sa,so)."""
    with tempfile.TemporaryDirectory() as tmp:
        data_file = os.path.join(tmp, "routine.json")
        for key in config_mod.GUELTIGE_WOCHENTAGS_KEYS:
            config_mod.write_data(data_file, {"abfahrtszeit": {key: "07:30"}})


def test_write_data_ungueltige_wochentags_keys():
    """write_data lehnt ungültige Wochentags-Keys ab (ValidationError).

    Gültig: mo,di,mi,do,fr,sa,so (lowercase, ROUTINE-14).
    Ungültig: monday, 1 (keine deutschen Kürzel).
    Leerer Key "" ist ungültig (nicht in der Menge).
    """
    with tempfile.TemporaryDirectory() as tmp:
        data_file = os.path.join(tmp, "routine.json")
        for ungueltig in ("monday", "1", ""):
            with pytest.raises(config_mod.ValidationError):
                config_mod.write_data(data_file,
                                      {"abfahrtszeit": {ungueltig: "07:30"}})


# ============================================================
#  GET /api/v1/routine/config — AC1, AC2, AC_ENTRY (ROUTINE-14, #728)
# ============================================================

def test_ac_entry_get_trifft_flask_handler(data_path_und_client):
    """AC_ENTRY: GET /api/v1/routine/config trifft routine/main.py-Handler.

    Beleg: Flask test_client GET → HTTP 200, ruft _current_config() (Reload-on-Read).
    Ohne Netz.
    """
    _, client = data_path_und_client
    resp = client.get("/api/v1/routine/config")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    # Schema-Symmetrie: alle drei PUT-akzeptierten Schlüssel im Response
    assert "abfahrtszeit" in body
    assert "aufstehzeit" in body
    assert "anzieh_vorlauf_min" in body


def test_ac1_get_liefert_aktuelle_config(data_path_und_client):
    """AC1: GET liefert 200 mit den aktuellen Zeitwerten (ROUTINE-14, #728).

    Werte im Response müssen dem Fixture-Grundzustand entsprechen.
    """
    _, client = data_path_und_client
    resp = client.get("/api/v1/routine/config")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["abfahrtszeit"] == "07:45"
    assert body["aufstehzeit"] == "07:00"
    assert body["anzieh_vorlauf_min"] == 8


def test_ac1_get_spiegelt_put_schema(data_path_und_client):
    """AC1: GET-Antwort spiegelt PUT-akzeptiertes Schema (Schema-Symmetrie, ROUTINE-14).

    PUT setzt neue Werte → GET liefert exakt dieselben Werte zurück.
    Reload-on-Read (DCOMP-3): kein Service-Restart nötig.
    """
    _, client = data_path_und_client

    # PUT setzt neue Zeiten
    put_resp = client.put("/api/v1/routine/config",
                          json={"abfahrtszeit": "09:00", "aufstehzeit": "07:30",
                                "anzieh_vorlauf_min": 12},
                          content_type="application/json")
    assert put_resp.status_code == 200

    # GET muss exakt die gesetzten Werte zurückgeben
    get_resp = client.get("/api/v1/routine/config")
    assert get_resp.status_code == 200
    body = json.loads(get_resp.data)
    assert body["abfahrtszeit"] == "09:00"
    assert body["aufstehzeit"] == "07:30"
    assert body["anzieh_vorlauf_min"] == 12


def test_ac1_get_reload_on_read_via_current_config(data_path_und_client):
    """AC1: GET ruft _current_config() (Reload-on-Read, DCOMP-3).

    Zeigt: neuer Stand in routine.json ist ohne Neustart per GET sichtbar.
    """
    data_path, client = data_path_und_client

    # Datei direkt manipulieren (simuliert externen Schreiber, z.B. Eltern-Chat)
    with open(data_path, encoding="utf-8") as f:
        inhalt = json.load(f)
    inhalt["abfahrtszeit"] = "06:55"
    data_dir = os.path.dirname(data_path)
    with tempfile.NamedTemporaryFile(
            mode="w", dir=data_dir, suffix=".tmp", delete=False,
            encoding="utf-8") as tmp:
        json.dump(inhalt, tmp)
        tmp_name = tmp.name
    os.replace(tmp_name, data_path)

    # GET muss neuen Stand sehen (Reload-on-Read, DCOMP-3)
    resp = client.get("/api/v1/routine/config")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["abfahrtszeit"] == "06:55", (
        "DCOMP-3: GET muss nach direktem Schreiben in routine.json "
        "den neuen Stand liefern (Reload-on-Read ohne Service-Restart)"
    )


def test_ac2_get_kein_data_path_liefert_500(tmp_path):
    """AC2: kein konfigurierter data_path → 500 mit ehrlichem Fehler (KEINE leeren Defaults).

    Explizit: configure() ohne data_path → GET → 500.
    """
    data_file = tmp_path / "routine.json"
    data_file.write_text(json.dumps({
        "abfahrtszeit": "07:00",
        "aufstehzeit": "06:30",
        "anzieh_vorlauf_min": 5,
        "items": [],
        "zeitzone": "Europe/Berlin",
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    cfg = config_mod.resolve_data(str(data_file))
    # data_path bewusst NICHT übergeben
    main_mod.configure(cfg, data_path=None, store_path=None,
                       bot_token=TEST_BOT_TOKEN, init_data_config={"max_age_seconds": 86400})
    client = patch_client_auth(main_mod.app.test_client())

    resp = client.get("/api/v1/routine/config")
    assert resp.status_code == 500
    body = json.loads(resp.data)
    assert "error" in body
    assert body["error"]  # ehrlicher Fehler — kein leerer String
