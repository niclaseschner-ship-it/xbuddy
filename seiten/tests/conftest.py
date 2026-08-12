"""Gemeinsame Test-Helfer der Seiten-Buddy-Suite (AUTH-11, #1832).

Vor #1832 gab es keinen geteilten `conftest.py` fuer `seiten/tests/` -- jede
Testdatei baute ihren eigenen `client()`-Fixture direkt ueber
`seiten_main.app.test_client()`. Diese Datei ergaenzt NICHTS Bestehendes,
sie stellt nur additive Helfer fuer neue AUTH-11-Tests bereit (Muster:
`routine/tests/conftest.py::mit_session_cookie`).

Kein bestehender Test importiert aus dieser Datei -- die Bestandssuite blieb
gruen, weil `require_dual_gate(mode=_AUTH_MODE)` im Test-Default-Zustand
("observe", kein ENV-Override) ohne Cookie durchlaesst und `require_init_data`
den AUTH-5-Loopback-Bypass fuer den Flask-Test-Client greift (kein
`X-Forwarded-For`-Header -> `remote_addr` bleibt 127.0.0.1). Die additiven
Helfer hier sind fuer `test_auth11_seiten.py` gedacht, das den Cookie-Pfad
UND den nicht-Loopback-Pfad explizit erzwingt.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.initdata import session_cookie as sc  # noqa: E402  # isort:skip

# Test-Bot-Token -- wortgleich zu tests/test_dual_gate_7b.py::BOT_TOKEN, damit
# ein Cookie, der mit diesem Token signiert wurde, gegen jede seiten-Test-
# Konfiguration verifiziert (kein zweites Test-Secret).
TEST_BOT_TOKEN = "123456:ABCdef_testtoken"

# Fremde (Nicht-Operator-, Nicht-Loopback-)Quell-Adresse fuer Auth-Negativ-
# Proben. X-Forwarded-For besiegt den AUTH-5-Loopback-Bypass von
# require_init_data (tools/initdata/auth_gate.py::_ist_loopback); X-Real-IP
# ist die von require_dual_gate/_client_ip gelesene Quelle (ESC-2).
_FREMDE_IP = "203.0.113.7"
EXTERN_HEADERS = {"X-Forwarded-For": _FREMDE_IP, "X-Real-IP": _FREMDE_IP}


def mit_session_cookie(flask_client, bot_token=TEST_BOT_TOKEN, subject="eltern-testgeraet"):
    """Setzt einen gueltigen `xbuddy_session`-Cookie am Test-Client (AUTH-2).

    Additiv -- setzt NUR den Cookie, aendert keinen Header/keine bestehende
    Zusicherung. `subject` ist opak (Cookie-Payload traegt keine echte
    Familien-Identitaet in den Tests, nur eine Test-Kennung)."""
    token = sc.sign_session(subject, bot_token)
    flask_client.set_cookie(sc.COOKIE_NAME, token, domain="localhost")
    return flask_client
