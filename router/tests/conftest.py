"""conftest.py — AUTH-7b Hard-Enforcement (T1426).

Alle 7b-Routen laufen ab T1426 im Hard-Modus.  Die bestehenden Router-Tests
waren fuer Observe (kein Gate) geschrieben und schicken keine Auth-Quelle mit.
Dieses Conftest injiziert automatisch einen Operator-IP-Header in jeden
Testclient, der ueber router_main.app.test_client() erzeugt wird — ohne jede
Testdatei anzufassen.

Mechanik: monkeypatch.setattr auf app.test_client; das Original wird
aufgerufen und bekommt anschliessend environ_base gesetzt (auth.md AUTH-7:461,
192.168.0.0/16 ist Operator-CIDR).
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from router import main as router_main

_OPERATOR_ENVIRON = {"HTTP_X_REAL_IP": "192.0.2.10"}


@pytest.fixture(autouse=True)
def inject_operator_ip(monkeypatch):
    """Injiziert Operator-IP in alle ueber router_main.app.test_client() erzeugten Clients."""
    original_test_client = router_main.app.test_client.__func__  # unbound method

    def patched_test_client(self, *args, **kwargs):
        client = original_test_client(self, *args, **kwargs)
        base = dict(_OPERATOR_ENVIRON)
        if client.environ_base:
            base.update(client.environ_base)
        client.environ_base = base
        return client

    monkeypatch.setattr(router_main.app.__class__, "test_client", patched_test_client)
