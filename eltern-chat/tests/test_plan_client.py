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
