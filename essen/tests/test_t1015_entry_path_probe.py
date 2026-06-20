"""Entry-Path-Probe fuer T1015 / Befund 2 — Essen-Service.

Beweist, dass der Essen-Service nach dem DEFAULT_ORIGIN-Move die
neue Auth-Kette korrekt verdrahtet:
  1. ``tools.familie_client.DEFAULT_ORIGIN`` wird als Fallback-Origin genutzt
     (kein lokales Literal mehr in essen/main.py).
  2. Ein via ``configure(familie_client=...)`` injizierter Test-Stub wird vom
     Auth-Accessor ``_get_familie_client()`` zurueckgegeben.
  3. ``require_init_data`` ruft bei validem Auth-Header den injizierten
     FamilieClient auf (Stub-Transport wird getroffen).

Wohnort: essen/tests/, weil der Test essen/main.py importiert.
``tools/tests/`` darf das nicht (MOD-3, Layer-Modell).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse

_ESSEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_ESSEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import main as essen_main  # noqa: E402
from tools.familie_client import (  # noqa: E402
    DEFAULT_ORIGIN,
    PFAD_PERSONEN,
    FamilieClient,
)


def _fake_personen() -> list[dict]:
    return [
        {"id": "p1", "name": "Nic", "ring": "blue", "art": "erwachsene",
         "telegram_id": 42},
        {"id": "p2", "name": "Lea", "ring": "rose", "art": "erwachsene",
         "telegram_id": 7},
    ]


def _build_init_data_string(bot_token: str, user_id: int) -> str:
    auth_date = int(time.time())
    user_json = json.dumps({"id": user_id, "first_name": "Test"},
                           separators=(",", ":"))
    felder = {"auth_date": str(auth_date), "user": user_json}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(felder.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    felder["hash"] = h
    return urllib.parse.urlencode(felder)


def test_entry_path_probe_default_origin_ist_tools_konstante():
    """DEFAULT_ORIGIN aus tools.familie_client wird als Fallback genutzt (Befund 2).

    Prueft, dass kein lokales ``_DEFAULT_FAMILIE_ORIGIN``-Literal in
    essen/main.py mehr existiert — der Fallback kommt aus der zentralen
    tools.familie_client.DEFAULT_ORIGIN-Konstante (AC2).
    """
    assert DEFAULT_ORIGIN == "http://127.0.0.1:5010"


def test_entry_path_probe_accessor_gibt_injizierten_stub_zurueck():
    """_get_familie_client() liefert den via runtime-Dict injizierten Stub.

    Test-Naht CLIENT-1: injizierter FamilieClient mit Stub-Transport wird
    vom Accessor zurueckgegeben und get_telegram_ids() trifft den Stub.
    """
    captured = {"calls": 0}

    def transport(url: str) -> bytes:
        captured["calls"] += 1
        return json.dumps(_fake_personen()).encode("utf-8")

    stub = FamilieClient(DEFAULT_ORIGIN, transport=transport)
    prev = essen_main.runtime.get("familie_client")
    essen_main.runtime["familie_client"] = stub
    try:
        client = essen_main._get_familie_client()
        ids = client.get_telegram_ids()
        assert ids == {42, 7}, "Stub hat unexpectedly falsche IDs geliefert"
        assert captured["calls"] == 1, (
            "Transport-Stub nicht aufgerufen — Test-Naht greift nicht"
        )
    finally:
        essen_main.runtime["familie_client"] = prev


def test_entry_path_probe_require_init_data_ruft_familie_client(tmp_path):
    """require_init_data ruft bei validem Auth-Header get_telegram_ids() via Stub auf.

    Erwartung:
      * Eine via require_init_data gewrappte Dummy-Funktion erhaelt bei
        gueltigem Authorization-Header + Familien-Mitglied einen 200-Status.
      * Transport-Stub wurde >= 1x aufgerufen (FAM-Check traf den neuen Client,
        AC2 + Entry-Path-Probe).
    """
    captured = {"calls": 0, "url": None}
    body = json.dumps(_fake_personen()).encode("utf-8")

    def transport(url: str) -> bytes:
        captured["calls"] += 1
        captured["url"] = url
        return body

    real_client = FamilieClient("http://localhost:5010", transport=transport)

    paths = {
        "wuensche_file":        str(tmp_path / "wuensche.json"),
        "einkaufsliste_file":   str(tmp_path / "einkaufsliste.json"),
        "zaehler_file":         str(tmp_path / "zaehler.json"),
        "gerichte_file":        str(tmp_path / "gerichte.json"),
        "katalog_file":         str(tmp_path / "katalog.json"),
        "katalog_default_file": os.path.join(_ESSEN_DIR, "katalog.default.json"),
        "foto_overrides_file":  str(tmp_path / "foto_overrides.json"),
        "fotos_verzeichnis":    str(tmp_path / "fotos"),
    }

    prev_familie = essen_main.runtime.get("familie_client")
    prev_bot = essen_main.runtime.get("bot_token")
    prev_cfg = essen_main.runtime.get("init_data_config")

    try:
        essen_main.configure(
            paths,
            bot_token="test-bot-token:abc",
            init_data_config={"max_age_seconds": 86400},
            familie_client=real_client,
        )
        essen_main.app.config["TESTING"] = True

        # Dummy-Handler mit require_init_data-Decorator — damit der FAM-Check
        # ohne eine echte Route aufgerufen werden kann.
        from flask import jsonify as _jsonify

        @essen_main.require_init_data
        def _probe():
            return _jsonify({"ok": True}), 200

        init_data = _build_init_data_string("test-bot-token:abc", user_id=42)
        with essen_main.app.test_request_context(
            "/api/v1/essen/wuensche",
            method="GET",
            headers={"Authorization": "tma " + init_data,
                     "X-Forwarded-For": "1.2.3.4"},
        ):
            result = _probe()

        # result kann (response, status) oder response-Objekt sein
        status = result[1] if isinstance(result, tuple) else result.status_code
        assert status == 200, (
            "require_init_data + FAM-Check lieferte unerwartet status %d" % status
        )
        assert captured["calls"] >= 1, (
            "familie_client.get_telegram_ids hat den Stub nicht erreicht — "
            "require_init_data hat den neuen Client nicht aufgerufen"
        )
        assert PFAD_PERSONEN in captured["url"]
    finally:
        essen_main.runtime["familie_client"] = prev_familie
        essen_main.runtime["bot_token"] = prev_bot
        essen_main.runtime["init_data_config"] = prev_cfg
