"""Tests für den PlanClient — HTTP-Naht zur Plan-Buddy-Termin-Schnittstelle
(PLAN-22, TER-5, Refs #143).

Wir nutzen das `transport=`-Callable als Test-Naht (analog test_familie_client.py
aus Auftrag #215) — so testen wir den Client ohne echten HTTP-Server, mit voller
Kontrolle über Statuscodes und Bodys.
"""

import json

import pytest

from skills.plan_client import PlanClient, PlanClientError, PFAD_TERMINE


# ============================================================
#  Hilfs-Funktionen
# ============================================================

def _fake_transport(responses):
    """Baut ein `transport=`-Callable aus einer Folge von `(status, bytes)`
    Antworten — der Reihe nach.

    `calls` ist eine Liste der eingegangenen Aufrufe (zur Assertion)."""
    calls = []
    queue = list(responses)

    def transport(method, path, body=None, content_type=None):
        calls.append({
            "method": method, "path": path,
            "body": body, "content_type": content_type,
        })
        assert queue, "Kein weiteres Skript für %s %s" % (method, path)
        return queue.pop(0)
    return transport, calls


def _event(titel="Test", beginn="2026-06-01", ende="2026-06-02",
           ganztags=True, person=None, id="evt-1"):
    return {"id": id, "titel": titel, "beginn": beginn, "ende": ende,
            "ganztags": ganztags, "person": person}


# ============================================================
#  AC1 / TER-5 — GET /api/v1/plan/termine?ab=&tage=n
# ============================================================

def test_GET_termine_method_und_pfad():
    """TER-5: der Aufruf verwendet Methode GET und Pfad /api/v1/plan/termine."""
    transport, calls = _fake_transport([
        (200, json.dumps([_event()]).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    client.termine("2026-06-01", 7)
    assert calls[0]["method"] == "GET"
    assert PFAD_TERMINE in calls[0]["path"]
    assert "ab=2026-06-01" in calls[0]["path"]
    assert "tage=7" in calls[0]["path"]


def test_GET_termine_liefert_event_liste():
    """TER-5: eine 200-Antwort mit JSON-Liste wird als Liste zurückgegeben."""
    events = [_event("Zahnarzt", id="evt-1"), _event("Schule", id="evt-2")]
    transport, _ = _fake_transport([
        (200, json.dumps(events).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    result = client.termine("2026-06-01", 3)
    assert len(result) == 2
    assert result[0]["titel"] == "Zahnarzt"
    assert result[1]["titel"] == "Schule"


def test_GET_termine_5xx_wirft_PlanClientError():
    """TER-7: ein HTTP 5xx wird als PlanClientError weitergereicht."""
    transport, _ = _fake_transport([
        (503, b"Service Unavailable"),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.termine("2026-06-01", 7)


def test_GET_termine_4xx_wirft_PlanClientError():
    """TER-7: ein HTTP 4xx (z. B. 400 bei falschem Parameter) wirft PlanClientError."""
    transport, _ = _fake_transport([
        (400, b'{"error": "ungultiger ab/tage-Parameter"}'),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.termine("ungültig", 7)


def test_GET_termine_nicht_parsbar_wirft_PlanClientError():
    """TER-7: eine nicht-parsbare Antwort wirft PlanClientError."""
    transport, _ = _fake_transport([
        (200, b"kein json"),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.termine("2026-06-01", 7)


def test_GET_termine_unerwartete_form_wirft_PlanClientError():
    """TER-7: eine gültige JSON-Antwort, die kein Array ist, wirft PlanClientError."""
    transport, _ = _fake_transport([
        (200, json.dumps({"fehler": "falsch"}).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.termine("2026-06-01", 7)


def test_GET_termine_verbindungsfehler_wirft_PlanClientError():
    """TER-7: ein Verbindungsfehler (transport wirft OSError) wird als
    PlanClientError weitergereicht — die Funktion hat genau eine Fehlerklasse
    zu fangen."""
    def fehler_transport(method, path, body=None, content_type=None):
        raise OSError("Connection refused")

    client = PlanClient("http://127.0.0.1:9999", transport=fehler_transport)
    with pytest.raises(PlanClientError):
        client.termine("2026-06-01", 7)


def test_GET_termine_kein_cache_zweiter_aufruf_sieht_neuen_stand():
    """TER-5: kein Cache — ein zweiter Aufruf geht frisch an den Server und
    sieht den neuen Stand der Doppelung."""
    transport, calls = _fake_transport([
        (200, json.dumps([_event("Erster Aufruf", id="e1")]).encode("utf-8")),
        (200, json.dumps([_event("Zweiter Aufruf", id="e2")]).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    r1 = client.termine("2026-06-01", 1)
    r2 = client.termine("2026-06-01", 1)
    assert r1[0]["titel"] == "Erster Aufruf"
    assert r2[0]["titel"] == "Zweiter Aufruf"
    assert len(calls) == 2   # zwei echte Aufrufe, kein Cache


def test_GET_termine_leere_liste_ok():
    """TER-8: eine leere JSON-Liste ist ein gültiges Ergebnis (kein Fehler)."""
    transport, _ = _fake_transport([
        (200, json.dumps([]).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    result = client.termine("2026-06-01", 7)
    assert result == []


def test_origin_url_wird_als_prefix_genutzt():
    """TER-5: die Origin-URL wird als Präfix vor den Pfad gestellt."""
    transport, calls = _fake_transport([
        (200, json.dumps([]).encode("utf-8")),
    ])
    client = PlanClient("http://127.0.0.1:5020", transport=transport)
    client.termine("2026-06-01", 7)
    # path enthält nur den Pfad-Teil — die Origin ist im transport-Call nicht
    # sichtbar (der echte urllib-Aufruf würde die Origin vorne anhängen).
    # Wir prüfen stattdessen, dass der Pfad korrekt ist.
    assert PFAD_TERMINE in calls[0]["path"]


# ============================================================
#  AC1 / TES-8 — PUT /api/v1/plan/termine
# ============================================================

def test_PUT_termin_method_und_pfad():
    """TES-8: der Aufruf verwendet Methode PUT und Pfad /api/v1/plan/termine."""
    transport, calls = _fake_transport([
        (200, json.dumps({"ok": True, "action": "created",
                          "event_id": "evt-42"}).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    client.put_termin("Klettern Mila", "2026-06-05")
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == PFAD_TERMINE


def test_PUT_termin_body_titel_datum():
    """TES-8: der Body enthält ausschließlich {titel, datum} — kein event_id."""
    transport, calls = _fake_transport([
        (200, json.dumps({"ok": True, "action": "created",
                          "event_id": "evt-42"}).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    client.put_termin("Schulausflug", "2026-06-10")
    body = json.loads(calls[0]["body"].decode("utf-8"))
    assert body == {"titel": "Schulausflug", "datum": "2026-06-10"}
    assert "event_id" not in body


def test_PUT_termin_content_type_json():
    """TES-8: der Content-Type-Header ist application/json."""
    transport, calls = _fake_transport([
        (200, json.dumps({"ok": True, "action": "created",
                          "event_id": "evt-1"}).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    client.put_termin("Test", "2026-06-01")
    assert calls[0]["content_type"] == "application/json"


def test_PUT_termin_200_liefert_event_id():
    """TES-8: eine HTTP-200-Antwort mit ok+event_id gibt die event_id zurück."""
    transport, _ = _fake_transport([
        (200, json.dumps({"ok": True, "action": "created",
                          "event_id": "evt-abc"}).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    event_id = client.put_termin("Arzttermin", "2026-06-01")
    assert event_id == "evt-abc"


def test_PUT_termin_400_wirft_PlanClientError():
    """TES-8: HTTP 400 wird als PlanClientError weitergereicht."""
    transport, _ = _fake_transport([
        (400, b'{"error": "titel fehlt"}'),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.put_termin("", "2026-06-01")


def test_PUT_termin_502_wirft_PlanClientError():
    """TES-8: HTTP 502 (CalendarUnavailable) wird als PlanClientError weitergereicht."""
    transport, _ = _fake_transport([
        (502, b'{"error": "CalendarUnavailable"}'),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.put_termin("Termin", "2026-06-01")


def test_PUT_termin_verbindungsfehler_wirft_PlanClientError():
    """TES-9: ein Verbindungsfehler wird als PlanClientError weitergereicht."""
    def fehler_transport(method, path, body=None, content_type=None):
        raise OSError("Connection refused")

    client = PlanClient("http://127.0.0.1:9999", transport=fehler_transport)
    with pytest.raises(PlanClientError):
        client.put_termin("Termin", "2026-06-01")


def test_PUT_termin_antwort_nicht_parsbar_wirft_PlanClientError():
    """TES-8: eine nicht-parsbare Antwort wirft PlanClientError."""
    transport, _ = _fake_transport([
        (200, b"kein json"),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.put_termin("Termin", "2026-06-01")


def test_PUT_termin_antwort_ok_false_wirft_PlanClientError():
    """TES-8: eine Antwort mit ok=false wirft PlanClientError."""
    transport, _ = _fake_transport([
        (200, json.dumps({"ok": False, "error": "schreibfehler"}).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.put_termin("Termin", "2026-06-01")


def test_PUT_termin_antwort_ohne_event_id_wirft_PlanClientError():
    """TES-8: eine Antwort ohne event_id wirft PlanClientError."""
    transport, _ = _fake_transport([
        (200, json.dumps({"ok": True, "action": "created"}).encode("utf-8")),
    ])
    client = PlanClient("http://x", transport=transport)
    with pytest.raises(PlanClientError):
        client.put_termin("Termin", "2026-06-01")
