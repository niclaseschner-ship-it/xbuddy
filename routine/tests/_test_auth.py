"""Gemeinsame Auth-Hilfe fuer Routine-Tests (MAD-7 / T708-C).

Kein pytest-Fixture — plain Python, importierbar in jedem Test-Modul.
"""

import hashlib
import hmac
import json
import time
import urllib.parse

TEST_BOT_TOKEN = "123456:ABCdef_testtoken"


def bau_init_data(bot_token=TEST_BOT_TOKEN, user_id=42, offset_seconds=0):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC."""
    auth_date = int(time.time()) + offset_seconds
    user_json = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))
    felder = {"auth_date": str(auth_date), "user": user_json}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(felder.items()))
    secret_key = hmac.new(
        key=b"WebAppData", msg=bot_token.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        key=secret_key, msg=data_check_string.encode("utf-8"), digestmod=hashlib.sha256
    ).hexdigest()
    felder["hash"] = computed_hash
    return urllib.parse.urlencode(felder)


def patch_client_auth(flask_client, bot_token=TEST_BOT_TOKEN):
    """Setzt HTTP_AUTHORIZATION in environ_base des Clients (in-place, gibt client zurück)."""
    flask_client.environ_base["HTTP_AUTHORIZATION"] = "tma " + bau_init_data(bot_token)
    return flask_client
