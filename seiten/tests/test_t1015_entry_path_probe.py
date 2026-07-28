"""Entry-Path-Probe fuer T1015 / Cluster-A-Option-B.

Beweist, dass die neue Auth-Kette live durch die seiten-Service-Auth laeuft:
  1. ``tools.initdata.validate_header`` (HMAC-Validierung)
  2. ``tools.familie_client.FamilieClient.get_telegram_ids`` (FAM-Check)

Der Test geht nicht ueber Mocks am Auth-Layer, sondern setzt einen echten
``FamilieClient`` mit Test-Transport (CLIENT-1) ein und prueft, dass der
Transport tatsaechlich aufgerufen wird — d. h. der Auth-Decorator hat den
neuen Client wirklich getroffen, nicht eine zurueckgebliebene Datei-Read-
Funktion.

Wohnort: seiten/tests/, weil der Test seiten/main.py importiert.
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

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from tools.familie_client import (  # noqa: E402
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


@pytest.fixture
def seiten_with_real_client(monkeypatch):
    """Baut seiten.app mit echtem FamilieClient (Test-Transport, CLIENT-1)."""
    captured = {"calls": 0, "url": None}
    body = json.dumps(_fake_personen()).encode("utf-8")

    def transport(url: str) -> bytes:
        captured["calls"] += 1
        captured["url"] = url
        return body

    real_client = FamilieClient("http://localhost:5010", transport=transport)

    # Vorigen Zustand sichern + nach yield zuruecksetzen (Test-Hygiene).
    prev = {
        "bot_token": seiten_main.runtime.get("bot_token"),
        "init_data_config": seiten_main.runtime.get("init_data_config"),
        "familie_client": seiten_main.runtime.get("familie_client"),
        "inventar_path": seiten_main.runtime.get("inventar_path"),
    }
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="test-bot-token:abc",
        init_data_config={"max_age_seconds": 86400},
        familie_client=real_client,
    )
    seiten_main.app.config["TESTING"] = True
    yield seiten_main.app.test_client(), captured
    for k, v in prev.items():
        seiten_main.runtime[k] = v


def test_entry_path_probe_auth_kette_trifft_neue_tools_module(
    seiten_with_real_client,
):
    """POST /api/v1/init-data/validate trifft die neue Auth-Kette live.

    Erwartung:
      * status 200 (HMAC + FAM-Check beide ok).
      * Transport-Stub wurde mindestens 1x aufgerufen mit /api/v1/familie/personen.
      * Antwort enthaelt user_id + family_member.
    """
    client, captured = seiten_with_real_client

    init_data = _build_init_data_string("test-bot-token:abc", user_id=42)
    resp = client.post(
        "/api/v1/init-data/validate",
        headers={"Authorization": "tma " + init_data},
    )

    assert resp.status_code == 200, (
        "Auth-Kette tools.initdata + tools.familie_client lieferte unerwartet "
        "status %d (Body: %r)" % (resp.status_code, resp.get_data(as_text=True))
    )
    assert captured["calls"] >= 1, (
        "familie_client.get_telegram_ids hat den Stub nicht erreicht — "
        "Auth-Decorator hat den neuen Client nicht aufgerufen"
    )
    assert PFAD_PERSONEN in captured["url"]

    body = resp.get_json()
    assert body["user_id"] == 42
    assert body["family_member"] is True
