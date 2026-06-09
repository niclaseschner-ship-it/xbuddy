"""Tests für SeitenClient — SREG-3, SREG-6, CLIENT-1..4 (Refs #453).

Pattern: analog test_routine_zeiten_setzen_task.py / test_geraete_client.py.
Transport-Stub (CLIENT-1): kein Netz, kein Flask.

Pflicht-Tests:
- Happy-Path: GET /api/v1/seiten → Liste zurück.
- HTTP != 200 → SeitenClientError.
- Antwort kein JSON → SeitenClientError.
- Antwort kein Array → SeitenClientError.
- Connection-Fehler → SeitenClientError.
- Transport-Stub wird verwendet (CLIENT-1).
- Pfad ist stabil: PFAD_SEITEN == /api/v1/seiten (CLIENT-4).
"""

import json

import pytest
from skills.seiten_client import PFAD_SEITEN, SeitenClient, SeitenClientError

# ============================================================
#  Transport-Stubs (CLIENT-1)
# ============================================================

def _transport_ok(eintraege, snapshot_pending=None):
    """Stub: liefert HTTP 200 + echte SREG-3-Antwort-Form
    `{"eintraege": [...], "snapshot_pending": [...]}` (Aggregator-Output)."""
    payload = {
        "eintraege": eintraege,
        "snapshot_pending": list(snapshot_pending or []),
    }
    _body = json.dumps(payload).encode("utf-8")
    def _t(method, path, body=None, content_type=None):
        return 200, _body
    return _t


def _transport_ok_flat_list(eintraege):
    """Defensive: hypothetische zukünftige flat-list-Form."""
    _body = json.dumps(eintraege).encode("utf-8")
    def _t(method, path, body=None, content_type=None):
        return 200, _body
    return _t


def _transport_status(status, body=b"{}"):
    """Stub: liefert den angegebenen HTTP-Status."""
    def _t(method, path, body=None, content_type=None):
        return status, body
    return _t


def _transport_error(msg="verbindungsfehler"):
    """Stub: wirft OSError (simuliert Connection-Fehler)."""
    def _t(method, path, body=None, content_type=None):
        raise OSError(msg)
    return _t


def _transport_bad_json():
    """Stub: liefert HTTP 200 aber kein valides JSON."""
    def _t(method, path, body=None, content_type=None):
        return 200, b"kein-json!!"
    return _t


def _transport_not_list():
    """Stub: liefert HTTP 200 aber weder dict mit `eintraege` noch flach Liste."""
    def _t(method, path, body=None, content_type=None):
        return 200, json.dumps({"falsch": "kein-array"}).encode("utf-8")
    return _t


# ============================================================
#  Tests: Pfad-Konstante (CLIENT-4)
# ============================================================

def test_pfad_seiten_stabil():
    """PFAD_SEITEN ist die stabile CLIENT-4-Konstante."""
    assert PFAD_SEITEN == "/api/v1/seiten"


# ============================================================
#  Tests: Happy-Path
# ============================================================

def test_inventar_liefert_liste():
    """Happy-Path: GET /api/v1/seiten → Liste von Eintrags-Dicts."""
    eintraege = [
        {"pfad": "/display/plan/woche", "label": "Wochenplan", "typ": "display"},
        {"pfad": "/controller/app-panel/p1/bearbeiten",
         "label": "Panel p1 bearbeiten", "typ": "eltern"},
    ]
    client = SeitenClient("http://127.0.0.1:5042",
                          transport=_transport_ok(eintraege))
    result = client.inventar()
    assert result == eintraege


def test_inventar_leere_liste_ist_gueltig():
    """Leere Liste ist ein gültiges Ergebnis (noch keine Seiten)."""
    client = SeitenClient("http://127.0.0.1:5042",
                          transport=_transport_ok([]))
    result = client.inventar()
    assert result == []


def test_transport_wird_aufgerufen():
    """CLIENT-1: der Transport-Stub wird aufgerufen, kein urllib.request."""
    aufrufe = []
    eintraege = [{"pfad": "/x", "label": "X", "typ": "display"}]
    payload = {"eintraege": eintraege, "snapshot_pending": []}
    _body = json.dumps(payload).encode("utf-8")

    def _spy(method, path, body=None, content_type=None):
        aufrufe.append((method, path))
        return 200, _body

    client = SeitenClient("http://x.test", transport=_spy)
    client.inventar()
    assert len(aufrufe) == 1
    assert aufrufe[0] == ("GET", PFAD_SEITEN)


def test_inventar_packt_eintraege_aus_aggregator_envelope():
    """#467 Production-Bug-Regress: SREG-3 liefert dict mit `eintraege` +
    `snapshot_pending`; inventar() gibt nur die `eintraege`-Liste zurück,
    ignoriert snapshot_pending."""
    eintraege = [
        {"pfad": "/display/plan/woche", "typ": "display"},
        {"pfad": "/controller/app-panel/p1/bearbeiten", "typ": "eltern"},
    ]
    client = SeitenClient(
        "http://127.0.0.1:5042",
        transport=_transport_ok(eintraege, snapshot_pending=["pending-ref"]))
    result = client.inventar()
    assert result == eintraege  # snapshot_pending nicht im Output


def test_inventar_akzeptiert_defensive_flat_list_form():
    """Defensive: falls die Registry-Form je auf flache Liste wechselt,
    bleibt der Client kompatibel (siehe inventar-Docstring)."""
    eintraege = [{"pfad": "/x", "typ": "display"}]
    client = SeitenClient(
        "http://127.0.0.1:5042",
        transport=_transport_ok_flat_list(eintraege))
    result = client.inventar()
    assert result == eintraege


# ============================================================
#  Tests: Fehler-Pfade
# ============================================================

def test_http_500_wirft_seiten_client_error():
    """HTTP 500 → SeitenClientError."""
    client = SeitenClient("http://127.0.0.1:5042",
                          transport=_transport_status(500))
    with pytest.raises(SeitenClientError, match="HTTP 500"):
        client.inventar()


def test_http_404_wirft_seiten_client_error():
    """HTTP 404 → SeitenClientError."""
    client = SeitenClient("http://127.0.0.1:5042",
                          transport=_transport_status(404))
    with pytest.raises(SeitenClientError, match="HTTP 404"):
        client.inventar()


def test_kein_json_wirft_seiten_client_error():
    """Antwort kein gültiges JSON → SeitenClientError."""
    client = SeitenClient("http://127.0.0.1:5042",
                          transport=_transport_bad_json())
    with pytest.raises(SeitenClientError, match="parsebar"):
        client.inventar()


def test_antwort_kein_array_wirft_seiten_client_error():
    """Antwort ist Dict OHNE `eintraege`-Schlüssel → SeitenClientError."""
    client = SeitenClient("http://127.0.0.1:5042",
                          transport=_transport_not_list())
    with pytest.raises(SeitenClientError, match="unerwartete Form"):
        client.inventar()


def test_connection_fehler_wirft_seiten_client_error():
    """Connection-Fehler im Transport → SeitenClientError (CLIENT-2)."""
    client = SeitenClient("http://127.0.0.1:5042",
                          transport=_transport_error("refused"))
    with pytest.raises(SeitenClientError, match="transport-Fehler"):
        client.inventar()


def test_origin_trailing_slash_wird_entfernt():
    """Trailing-Slash in origin_url wird beim Init gestripped."""
    aufrufe = []
    _body = json.dumps([]).encode("utf-8")

    def _spy(method, path, body=None, content_type=None):
        aufrufe.append((method, path))
        return 200, _body

    client = SeitenClient("http://127.0.0.1:5042/", transport=_spy)
    client.inventar()
    # Der Transport wird mit dem stabilen Pfad aufgerufen, kein Doppelslash.
    assert aufrufe[0][1] == PFAD_SEITEN


# ============================================================
#  Tests: get_kandidaten() — PAA-3.3, #389
# ============================================================

def _transport_inventar(eintraege):
    """Stub: liefert ein Inventar mit den angegebenen Einträgen."""
    payload = {"eintraege": eintraege, "snapshot_pending": []}
    _resp = json.dumps(payload).encode("utf-8")
    def _t(method, path, body=None, content_type=None):
        return 200, _resp
    return _t


def test_get_kandidaten_filtert_nur_display_typ():
    """get_kandidaten() gibt nur Einträge mit typ=display zurück (Sorte a)."""
    eintraege = [
        {"typ": "display", "app": "wetter", "pfad": "/display/wetter/heute",
         "label": "Wetter heute", "icons": ["arasaac/24721.png"]},
        {"typ": "eltern", "app": "wetter", "pfad": "/display/wetter/regeln",
         "label": "Wetter-Regeln"},   # kein icons, kein display
        {"typ": "panel", "app": "app-panel", "pfad": "/controller/app-panel/p1",
         "label": "Panel"},
    ]
    client = SeitenClient("http://test", transport=_transport_inventar(eintraege))
    kandidaten = client.get_kandidaten()
    assert len(kandidaten) == 1
    assert kandidaten[0]["app"] == "wetter"
    assert kandidaten[0]["label"] == "Wetter heute"


def test_get_kandidaten_traegt_icons_aus_manifest():
    """get_kandidaten(): icons[] kommen aus dem Manifest-Eintrag (AC1/AC2)."""
    eintraege = [
        {"typ": "display", "app": "wetter", "pfad": "/display/wetter/heute",
         "label": "Wetter heute", "icons": ["arasaac/24721.png"]},
    ]
    client = SeitenClient("http://test", transport=_transport_inventar(eintraege))
    kandidaten = client.get_kandidaten()
    assert kandidaten[0]["icons"] == ["arasaac/24721.png"]


def test_get_kandidaten_varianten_werden_aufgeflacht():
    """AC2: Varianten werden als eigene Kandidaten aufgeflacht, mit icons[]/query."""
    eintraege = [
        {"typ": "display", "app": "plan", "pfad": "/display/plan/woche",
         "label": "Wochenplan", "icons": ["arasaac/32488.png"],
         "varianten": [
             {"slug": "woche-klein", "query": {"ansicht": "klein"},
              "label": "Wochenplan für Kleinkinder",
              "icons": ["arasaac/32488.png", "arasaac/2484.png"]},
         ]},
    ]
    client = SeitenClient("http://test", transport=_transport_inventar(eintraege))
    kandidaten = client.get_kandidaten()
    # Basis + 1 Variante
    assert len(kandidaten) == 2
    basis = kandidaten[0]
    assert basis["app"] == "plan"
    assert basis["icons"] == ["arasaac/32488.png"]
    assert "query" not in basis

    variante = kandidaten[1]
    assert variante["app"] == "plan"
    assert variante["label"] == "Wochenplan für Kleinkinder"
    assert variante["icons"] == ["arasaac/32488.png", "arasaac/2484.png"]
    assert variante["query"] == {"ansicht": "klein"}


def test_get_kandidaten_variante_erbt_eltern_icons_wenn_keine_eigenen():
    """AC2: hat eine Variante kein eigenes icons[], erbt sie die icons[] des Eltern."""
    eintraege = [
        {"typ": "display", "app": "plan", "pfad": "/display/plan/woche",
         "label": "Wochenplan", "icons": ["arasaac/32488.png"],
         "varianten": [
             {"slug": "v", "query": {"x": "y"}, "label": "Variante ohne Icons"},
         ]},
    ]
    client = SeitenClient("http://test", transport=_transport_inventar(eintraege))
    kandidaten = client.get_kandidaten()
    assert len(kandidaten) == 2
    variante = kandidaten[1]
    assert variante["icons"] == ["arasaac/32488.png"]  # geerbt


def test_get_kandidaten_leeres_inventar():
    """get_kandidaten() auf leerem Inventar liefert [] — gültiges Ergebnis."""
    client = SeitenClient("http://test", transport=_transport_ok([]))
    kandidaten = client.get_kandidaten()
    assert kandidaten == []


def test_get_kandidaten_wirft_bei_registry_fehler():
    """get_kandidaten() wirft SeitenClientError bei Registry-Fehler (AC4)."""
    client = SeitenClient("http://test", transport=_transport_status(503))
    with pytest.raises(SeitenClientError):
        client.get_kandidaten()


def test_get_kandidaten_view_aus_pfad_abgeleitet():
    """get_kandidaten(): view wird aus pfad abgeleitet wenn kein slug-Feld
    (letztes Segment von /display/app/view → view)."""
    eintraege = [
        {"typ": "display", "app": "wetter", "pfad": "/display/wetter/heute",
         "label": "Wetter", "icons": ["icon.png"]},
    ]
    client = SeitenClient("http://test", transport=_transport_inventar(eintraege))
    kandidaten = client.get_kandidaten()
    assert kandidaten[0]["view"] == "heute"
    assert kandidaten[0]["app"] == "wetter"


def test_get_kandidaten_reihenfolge_ist_inventar_reihenfolge():
    """AC3: Inventar-Reihenfolge bleibt erhalten (deterministisch, OPEN-PAA-B)."""
    eintraege = [
        {"typ": "display", "app": "wetter", "pfad": "/display/wetter/heute",
         "label": "Wetter", "icons": ["w.png"]},
        {"typ": "display", "app": "plan", "pfad": "/display/plan/woche",
         "label": "Plan", "icons": ["p.png"]},
    ]
    client = SeitenClient("http://test", transport=_transport_inventar(eintraege))
    kandidaten = client.get_kandidaten()
    assert [k["app"] for k in kandidaten] == ["wetter", "plan"]
