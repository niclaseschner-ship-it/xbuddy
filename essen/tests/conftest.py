"""Essens-Buddy — gemeinsame Test-Fixtures (ESSEN-26).

Alle Tests laufen ohne Netz. Die Datei-IO wird über tmp_path-Pfade (pytest)
isoliert — kein echtes essen/wuensche.json wird berührt.

Auth (MAD-7 / T708-C): client-Fixture setzt Authorization-Header automatisch
(environ_base), damit bestehende API-Tests ohne Änderung laufen. Tests die
speziell 401/403-Verhalten prüfen, bauen ihren eigenen Client ohne env.
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import main as main_mod  # noqa: E402

# ── Auth-Test-Konstanten (MAD-7 / T708-C) ─────────────────────────────────────

TEST_BOT_TOKEN = "123456:ABCdef_testtoken"


def _baue_init_data(bot_token=TEST_BOT_TOKEN, user_id=42, offset_seconds=0):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC.

    Algorithmus (eltern-chat/init_data.py, Telegram-Doku):
      secret_key = HMAC_SHA256(key=b'WebAppData', data=bot_token)
      hash       = HMAC_SHA256(key=secret_key,  data=data_check_string).hexdigest()
    """
    auth_date = int(time.time()) + offset_seconds
    user_json = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))

    felder = {
        "auth_date": str(auth_date),
        "user":      user_json,
    }

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(felder.items())
    )

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    felder["hash"] = computed_hash
    return urllib.parse.urlencode(felder)


# ── Demo-Pfade (tmp_path-isoliert) ────────────────────────────────────────

@pytest.fixture
def demo_paths(tmp_path):
    """Isolierte Datei-Pfade für alle Daten-State-Dateien.

    Katalog-Default wird aus dem echten Repo-Default gelesen, so dass
    die Tests den Default-Katalog-Inhalt prüfen können (ESSEN-12).
    """
    real_default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "katalog.default.json",
    )
    return {
        "wuensche_file":        str(tmp_path / "wuensche.json"),
        "einkaufsliste_file":   str(tmp_path / "einkaufsliste.json"),
        "zaehler_file":         str(tmp_path / "zaehler.json"),
        "gerichte_file":        str(tmp_path / "gerichte.json"),
        "katalog_file":         str(tmp_path / "katalog.json"),           # Override — fehlt = kein Override
        "katalog_default_file": real_default,
        "foto_overrides_file":  str(tmp_path / "foto_overrides.json"),    # fehlt = keine Overrides
        "fotos_verzeichnis":    str(tmp_path / "fotos"),                   # ESSEN-22 V1.2: Essen-Foto-Verzeichnis
    }


def _reset_runtime(demo_paths):
    """Setzt den gesamten module-level runtime-State zurück (Test-Isolation)."""
    main_mod.runtime["wuensche_snapshot"] = None
    main_mod.runtime["einkauf_snapshot"]  = None
    main_mod.runtime["zaehler_snapshot"]  = None
    main_mod.runtime["gerichte_snapshot"] = None
    main_mod.runtime["katalog_snapshot"]  = None
    main_mod.configure(
        demo_paths,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )


@pytest.fixture
def client(demo_paths):
    """Flask-Testclient mit isolierten Pfaden und MAD-7-Auth (T708-C).

    environ_base setzt den Authorization-Header automatisch, damit bestehende
    API-Tests ohne Änderung weiterhin 200 erhalten.
    """
    _reset_runtime(demo_paths)
    init_data = _baue_init_data()
    flask_client = main_mod.app.test_client()
    flask_client.environ_base["HTTP_AUTHORIZATION"] = "tma " + init_data
    return flask_client


@pytest.fixture
def foto_client(tmp_path):
    """Flask-Testclient mit tmp-Foto-Verzeichnis und MAD-7-Auth (T708-C)."""
    paths = {
        "wuensche_file":        str(tmp_path / "wuensche.json"),
        "einkaufsliste_file":   str(tmp_path / "einkaufsliste.json"),
        "zaehler_file":         str(tmp_path / "zaehler.json"),
        "gerichte_file":        str(tmp_path / "gerichte.json"),
        "katalog_file":         str(tmp_path / "katalog.json"),
        "katalog_default_file": os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "katalog.default.json"),
        "foto_overrides_file":  str(tmp_path / "foto_overrides.json"),
        "fotos_verzeichnis":    str(tmp_path / "fotos"),
    }
    main_mod.runtime["wuensche_snapshot"] = None
    main_mod.runtime["einkauf_snapshot"]  = None
    main_mod.runtime["zaehler_snapshot"]  = None
    main_mod.runtime["gerichte_snapshot"] = None
    main_mod.runtime["katalog_snapshot"]  = None
    main_mod.configure(
        paths,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    flask_client = main_mod.app.test_client()
    flask_client.environ_base["HTTP_AUTHORIZATION"] = "tma " + _baue_init_data()
    return flask_client


@pytest.fixture
def client_mit_wuenschen(demo_paths):
    """Client mit zwei vorbereiteten Wünschen in wuensche.json.

    Apfel (item_id 'apfel', bild_ref '2462', obst_gemuese) und
    Milch (item_id 'milch', bild_ref '2445', sonstiges).
    item_id ist Pflichtfeld (ESSEN-16-Schärfung).
    """
    daten = {
        "wuensche": [
            {
                "id": "kind:1",
                "label": "Apfel",
                "bild_ref": "2462",
                "item_id": "apfel",
                "quelle": "kind",
                "kategorie": "obst_gemuese",
                "erstellt_am": "2026-06-09T08:00:00+02:00",
            },
            {
                "id": "kind:2",
                "label": "Milch",
                "bild_ref": "2445",
                "item_id": "milch",
                "quelle": "kind",
                "kategorie": "sonstiges",
                "erstellt_am": "2026-06-09T09:00:00+02:00",
            },
        ],
        "zaehler": {"kind": 2, "eltern": 0},
    }
    with open(demo_paths["wuensche_file"], "w", encoding="utf-8") as f:
        json.dump(daten, f)

    _reset_runtime(demo_paths)
    flask_client = main_mod.app.test_client()
    flask_client.environ_base["HTTP_AUTHORIZATION"] = "tma " + _baue_init_data()
    return flask_client
