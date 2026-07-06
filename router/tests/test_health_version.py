"""Tests für SVC-6: Router-Fan-in /health + /version (T1311/#1311).

Lauf: python3 -m pytest router/tests/test_health_version.py -v
"""

import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from router import main as router_main


@pytest.fixture
def client():
    router_main.app.testing = True
    return router_main.app.test_client()


class _FakeResp:
    """Minimaler urlopen-Context-Manager-Stub."""

    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, handler):
    """handler(url) -> status-int, oder wirft (HTTPError/URLError)."""
    def fake_urlopen(url, timeout=None):
        return _FakeResp(handler(url))
    monkeypatch.setattr(router_main.urllib.request, 'urlopen', fake_urlopen)


# ── /health (SVC-6 Fan-in, AC1) ────────────────────────────────────────────

def test_health_route_exists_kein_404(client):
    """AC1: /health ist keine 404-Doku-Fiktion mehr, sondern eine echte Route."""
    resp = client.get('/health')
    assert resp.status_code != 404


def test_health_all_upstreams_ok_gives_200(client, monkeypatch):
    _patch_urlopen(monkeypatch, lambda url: 200)
    resp = client.get('/health')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'
    # Alle 12 Upstreams aus PORT-2 (ohne Router-Selbstport 5000, ohne eltern-chat).
    assert len(body['upstreams']) == 12
    assert all(u['healthy'] and u['reachable'] for u in body['upstreams'])
    ports = {u['port'] for u in body['upstreams']}
    assert 5000 not in ports  # Router pingt sich nicht selbst
    assert {5010, 5041, 5055} <= ports  # PORT-2-Spiegel verbatim


def test_health_down_upstream_gives_503(client, monkeypatch):
    """Ein nicht erreichbarer Upstream (Connection refused) → degraded/503."""
    def handler(url):
        if ':5030/' in url:  # wetter tot
            raise urllib.error.URLError('connection refused')
        return 200
    _patch_urlopen(monkeypatch, handler)
    resp = client.get('/health')
    assert resp.status_code == 503
    body = resp.get_json()
    assert body['status'] == 'degraded'
    wetter = next(u for u in body['upstreams'] if u['port'] == 5030)
    assert wetter['reachable'] is False
    assert wetter['healthy'] is False


def test_health_404_upstream_reachable_but_unhealthy(client, monkeypatch):
    """Prozess läuft, aber /healthz fehlt (404): reachable=True, healthy=False.
    Da alle Prozesse erreichbar sind, bleibt der Fan-in insgesamt 200/ok."""
    def handler(url):
        if ':5020/' in url:  # plan: 404 auf /healthz
            raise urllib.error.HTTPError(url, 404, 'not found', {}, None)
        return 200
    _patch_urlopen(monkeypatch, handler)
    resp = client.get('/health')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'
    plan = next(u for u in body['upstreams'] if u['port'] == 5020)
    assert plan['reachable'] is True
    assert plan['healthy'] is False
    assert plan['healthz'] == 404


# ── /version (SVC-6, AC3) ──────────────────────────────────────────────────

def test_version_route_exists(client):
    resp = client.get('/version')
    assert resp.status_code == 200


def test_version_reads_deploy_file(client, monkeypatch, tmp_path):
    """AC3: /version liefert die laufende SHA aus __XBUDDY_DATA__/deploy/version."""
    deploy_dir = tmp_path / 'deploy'
    deploy_dir.mkdir()
    (deploy_dir / 'version').write_text('feeddead1234\n')
    monkeypatch.setenv('XBUDDY_DATA_DIR', str(tmp_path))
    resp = client.get('/version')
    assert resp.status_code == 200
    assert resp.get_json() == {'version': 'feeddead1234'}


def test_version_null_when_file_missing(client, monkeypatch, tmp_path):
    monkeypatch.setenv('XBUDDY_DATA_DIR', str(tmp_path))  # keine deploy/version
    resp = client.get('/version')
    assert resp.status_code == 200
    assert resp.get_json() == {'version': None}


def test_version_is_file_based_not_git_rev_parse(monkeypatch, tmp_path):
    """SVC-6: /version darf NICHT `git rev-parse` fahren — der Wert kommt 1:1
    aus der Datei. Ein Fantasie-SHA in der Datei muss unverändert zurückkommen."""
    deploy_dir = tmp_path / 'deploy'
    deploy_dir.mkdir()
    (deploy_dir / 'version').write_text('nicht-ein-echter-git-sha\n')
    monkeypatch.setenv('XBUDDY_DATA_DIR', str(tmp_path))
    # T1311: /version ist die EINE geteilte Naht (tools.service_diagnostics),
    # nicht mehr ein router-lokaler _deploy_version-Block.
    from tools import service_diagnostics
    assert service_diagnostics._deploy_version() == 'nicht-ein-echter-git-sha'


def test_health_body_is_json_serialisable(client, monkeypatch):
    _patch_urlopen(monkeypatch, lambda url: 200)
    resp = client.get('/health')
    json.loads(resp.get_data(as_text=True))  # wirft bei kaputtem Body
