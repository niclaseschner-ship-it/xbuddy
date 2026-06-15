"""MAD-11: Tests fuer den /api/v1/init-data/validate-Endpoint.

JS-Side-Auth-Probe-Endpoint fuer Mini-App-Mount. Validiert Authorization:
tma <initData>-Header (HMAC), prueft FAM-Mitgliedschaft, returnt 200 mit
{user_id, family_member} oder 401/403.

Loest die alten HTML-Route-Auth-Tests ab (Track-C-V1, jetzt MAD-7-konform
public — siehe test_essen_einkauf_route.py @skip-Marker).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse

import pytest
from flask import g  # noqa: F401

from seiten import main as seiten_main


BOT_TOKEN = "1234:TESTTOKEN"


@pytest.fixture
def client(tmp_path, monkeypatch):
    seiten_main.app.config["TESTING"] = True
    # Bot-Token in runtime cachen
    monkeypatch.setenv("ELTERNCHAT_BOT_TOKEN", BOT_TOKEN)
    seiten_main.runtime["init_data_config"] = {"max_age_seconds": 86400}
    yield seiten_main.app.test_client()


def _signiere_init_data(user_id: int = 42, name: str = "Nic") -> str:
    """Baut einen gueltigen initData-String fuer den Test."""
    user = {"id": user_id, "first_name": name}
    fields = {
        "auth_date": "9999999999",  # weit in der Zukunft
        "query_id": "test-query",
        "user": json.dumps(user, separators=(",", ":")),
    }
    sorted_pairs = sorted(fields.items())
    data_check = "\n".join(f"{k}={v}" for k, v in sorted_pairs)
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    fields["hash"] = h
    return urllib.parse.urlencode(fields)


def test_validate_ohne_header_liefert_401(client):
    resp = client.post("/api/v1/init-data/validate")
    assert resp.status_code == 401


def test_validate_falsches_schema_liefert_401(client):
    resp = client.post(
        "/api/v1/init-data/validate",
        headers={"Authorization": "Bearer nicht-tma"},
    )
    assert resp.status_code == 401


def test_validate_gueltiger_init_data_liefert_200(client, tmp_path):
    familie = {
        "erwachsene": [{"id": "p1", "name": "Nic", "ring": "blue", "telegram_id": 42}],
        "kinder": [],
    }
    f = tmp_path / "familie.json"
    f.write_text(json.dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_json_path"] = str(f)

    init_data = _signiere_init_data(user_id=42)
    resp = client.post(
        "/api/v1/init-data/validate",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200
    j = resp.get_json()
    assert j["user_id"] == 42
    assert j["family_member"] is True


def test_validate_fremde_user_id_liefert_403(client, tmp_path):
    familie = {
        "erwachsene": [{"id": "p1", "name": "Andere", "ring": "blue", "telegram_id": 99999}],
        "kinder": [],
    }
    f = tmp_path / "familie.json"
    f.write_text(json.dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_json_path"] = str(f)

    init_data = _signiere_init_data(user_id=42)
    resp = client.post(
        "/api/v1/init-data/validate",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 403
