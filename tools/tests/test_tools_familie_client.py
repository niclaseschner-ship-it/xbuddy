"""Tests fuer den gemeinsamen Familie-HTTP-Client (T1015 / Cluster-A-Option-B).

Deckt die ``get_telegram_ids()``-API ab — das ist alles, was die vier
Service-Auth-Decorators (essen, hoerspiel, routine, seiten) konsumieren.

CLIENT-1 Test-Naht: ``transport=(url) -> bytes`` als Stub im Konstruktor.
Kein echter HTTP-Server noetig.
"""

from __future__ import annotations

import json
import urllib.error

from tools.familie_client import (
    DEFAULT_ORIGIN,
    HTTP_TIMEOUT_SECONDS,
    PFAD_PERSONEN,
    FamilieClient,
    FamilieClientError,
)

# ============================================================
#  Happy-Path
# ============================================================


def _fake_personen() -> list[dict]:
    return [
        {"id": "p1", "name": "Nic", "ring": "blue", "art": "erwachsene",
         "telegram_id": 42},
        {"id": "p2", "name": "Lea", "ring": "rose", "art": "erwachsene",
         "telegram_id": 7},
        {"id": "k1", "name": "Mia", "ring": "yellow", "art": "kinder",
         "telegram_id": 99},
    ]


def test_get_telegram_ids_happy_path():
    """200-Antwort mit drei Personen → Set ihrer telegram_ids."""
    body = json.dumps(_fake_personen()).encode("utf-8")
    captured = {}

    def transport(url: str) -> bytes:
        captured["url"] = url
        return body

    client = FamilieClient("http://localhost:5010", transport=transport)
    ids = client.get_telegram_ids()

    assert ids == {42, 7, 99}
    assert captured["url"] == "http://localhost:5010" + PFAD_PERSONEN


def test_origin_url_trailing_slash_wird_gestrippt():
    body = json.dumps(_fake_personen()).encode("utf-8")
    captured = {}

    def transport(url: str) -> bytes:
        captured["url"] = url
        return body

    client = FamilieClient("http://localhost:5010/", transport=transport)
    client.get_telegram_ids()
    # Kein doppeltes // im Pfad.
    assert "//api" not in captured["url"]
    assert captured["url"] == "http://localhost:5010" + PFAD_PERSONEN


def test_person_ohne_telegram_id_wird_uebersprungen():
    """Personen ohne telegram_id sind ok — andere fallen durch."""
    payload = [
        {"id": "p1", "name": "Nic", "art": "erwachsene"},  # keine telegram_id
        {"id": "p2", "name": "Lea", "art": "erwachsene", "telegram_id": 7},
    ]
    client = FamilieClient(
        "http://x", transport=lambda url: json.dumps(payload).encode("utf-8"),
    )
    assert client.get_telegram_ids() == {7}


def test_telegram_id_als_string_wird_int_geparst():
    payload = [{"id": "p1", "name": "Nic", "art": "erwachsene",
                "telegram_id": "42"}]
    client = FamilieClient(
        "http://x", transport=lambda url: json.dumps(payload).encode("utf-8"),
    )
    assert client.get_telegram_ids() == {42}


def test_unparsbare_telegram_id_wird_uebersprungen():
    payload = [
        {"id": "p1", "name": "Nic", "art": "erwachsene", "telegram_id": "abc"},
        {"id": "p2", "name": "Lea", "art": "erwachsene", "telegram_id": 9},
    ]
    client = FamilieClient(
        "http://x", transport=lambda url: json.dumps(payload).encode("utf-8"),
    )
    assert client.get_telegram_ids() == {9}


# ============================================================
#  Fail-open-Pfade — alle liefern None
# ============================================================


def test_url_error_liefert_none():
    """Netz-Fehler → None (FAM-Check uebersprungen, Auth-Decorator-Erwartung)."""

    def transport(url: str) -> bytes:
        raise urllib.error.URLError("connection refused")

    client = FamilieClient("http://x", transport=transport)
    assert client.get_telegram_ids() is None


def test_os_error_liefert_none():
    def transport(url: str) -> bytes:
        raise OSError("no route to host")

    client = FamilieClient("http://x", transport=transport)
    assert client.get_telegram_ids() is None


def test_http_error_liefert_none():
    def transport(url: str) -> bytes:
        raise urllib.error.HTTPError(url, 503, "boom", {}, None)

    client = FamilieClient("http://x", transport=transport)
    assert client.get_telegram_ids() is None


def test_kaputtes_json_liefert_none():
    client = FamilieClient(
        "http://x", transport=lambda url: b"<<not json>>",
    )
    assert client.get_telegram_ids() is None


def test_antwort_kein_array_liefert_none():
    client = FamilieClient(
        "http://x",
        transport=lambda url: json.dumps({"personen": []}).encode("utf-8"),
    )
    assert client.get_telegram_ids() is None


def test_nicht_dict_person_wird_ignoriert():
    """Mischung aus dicts und nicht-dicts → nur dicts zaehlen."""
    payload = [
        "ungueltig",
        {"id": "p1", "name": "Nic", "art": "erwachsene", "telegram_id": 1},
    ]
    client = FamilieClient(
        "http://x", transport=lambda url: json.dumps(payload).encode("utf-8"),
    )
    assert client.get_telegram_ids() == {1}


# ============================================================
#  Konfig-Smoke
# ============================================================


def test_default_timeout_konstante():
    assert HTTP_TIMEOUT_SECONDS == 2.0  # CLIENT-2-Konvention


def test_fehler_klasse_existiert_und_ist_exception():
    assert issubclass(FamilieClientError, Exception)


def test_pfad_konstante_zeigt_auf_familie_personen():
    """CLIENT-4: Pfad-Konstante kein Magic-String."""
    assert PFAD_PERSONEN == "/api/v1/familie/personen"


def test_default_origin_konstante_exportiert():
    """CONFIG-5: DEFAULT_ORIGIN ist zentralisiert exportiert (T1015 / Befund 2)."""
    assert DEFAULT_ORIGIN == "http://127.0.0.1:5010"


# Entry-Path-Probe lebt in seiten/tests/test_t1015_entry_path_probe.py
# (Cross-Component-Auth-Test importiert seiten, gehoert architektonisch dorthin —
# MOD-3 erlaubt keinen tools→seiten-Import).
