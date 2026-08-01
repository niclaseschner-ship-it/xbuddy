"""Tests für tools/ca/make-ca.sh — die XBuddy-Root-CA + Server-Cert (#36).

Lauf: python3 -m pytest tools/ca/tests/ -v

Die Suite ruft das echte Skript in einem temporären Verzeichnis auf (nie ins
Repo schreibend) und belegt mit openssl, dass das Server-Zertifikat gegen die
erzeugte Root-CA verifiziert (URL-11) und die SAN-Einträge der Origin trägt.
"""

import os
import subprocess
from datetime import UTC, datetime

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(_HERE), "make-ca.sh")


def _have(cmd):
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(
    not (_have("openssl") and _have("bash")),
    reason="openssl und bash werden für die CA-Tests benötigt",
)


@pytest.fixture(scope="module")
def ca(tmp_path_factory):
    """Führt make-ca.sh einmal in einem Tempdir aus und liefert die Pfade."""
    out = tmp_path_factory.mktemp("ca-out")
    res = subprocess.run(
        ["bash", SCRIPT, "--out", str(out),
         "--san", "DNS:xbuddy-hub.local,IP:192.168.0.78"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, f"make-ca.sh fehlgeschlagen:\n{res.stderr}"
    return {
        "ca_cert": os.path.join(out, "rootCA.pem"),
        "ca_key": os.path.join(out, "rootCA-key.pem"),
        "srv_cert": os.path.join(out, "server-cert.pem"),
        "srv_key": os.path.join(out, "server-key.pem"),
        "out": str(out),
    }


def test_alle_artefakte_erzeugt(ca):
    """Skript legt CA und Server-Cert samt Schlüsseln an."""
    for key in ("ca_cert", "ca_key", "srv_cert", "srv_key"):
        assert os.path.isfile(ca[key]), f"{key} fehlt"


def test_schluessel_sind_nur_fuer_eigentuemer_lesbar(ca):
    """Private Keys tragen Modus 600 — Geheimnisse (CLAUDE.md §8)."""
    for key in ("ca_key", "srv_key"):
        mode = os.stat(ca[key]).st_mode & 0o777
        assert mode == 0o600, f"{key} hat Modus {oct(mode)}, erwartet 0o600"


def test_server_cert_verifiziert_gegen_ca(ca):
    """URL-11: das Server-Cert ist von der erzeugten Root-CA signiert."""
    res = subprocess.run(
        ["openssl", "verify", "-CAfile", ca["ca_cert"], ca["srv_cert"]],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, f"openssl verify fehlgeschlagen:\n{res.stdout}{res.stderr}"
    assert "OK" in res.stdout


def test_server_cert_traegt_san_eintraege(ca):
    """Das Server-Cert trägt die per --san übergebenen SAN-Einträge der Origin."""
    res = subprocess.run(
        ["openssl", "x509", "-in", ca["srv_cert"], "-noout", "-ext", "subjectAltName"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0
    assert "xbuddy-hub.local" in res.stdout
    assert "192.168.0.78" in res.stdout


def test_root_ca_ist_eine_ca(ca):
    """Das Root-Zertifikat trägt die CA-Basis-Constraint."""
    res = subprocess.run(
        ["openssl", "x509", "-in", ca["ca_cert"], "-noout", "-text"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0
    assert "CA:TRUE" in res.stdout


def test_server_cert_laufzeit_unter_398_tagen(ca):
    """CAV-8: Das Server-Cert hat eine Laufzeit von höchstens 398 Tagen
    (CA/Browser-Forum-Limit, Apple lehnt längere aktiv ab — #76)."""
    res = subprocess.run(
        ["openssl", "x509", "-in", ca["srv_cert"], "-noout",
         "-startdate", "-enddate"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    # openssl gibt "notBefore=May 23 10:00:00 2026 GMT" / "notAfter=..." aus
    dates = {}
    for line in res.stdout.strip().splitlines():
        key, _, value = line.partition("=")
        dates[key.strip()] = value.strip()
    fmt = "%b %d %H:%M:%S %Y %Z"
    not_before = datetime.strptime(dates["notBefore"], fmt).replace(tzinfo=UTC)
    not_after = datetime.strptime(dates["notAfter"], fmt).replace(tzinfo=UTC)
    delta_days = (not_after - not_before).days
    assert delta_days <= 398, (
        f"Server-Cert-Laufzeit {delta_days} Tage > 398 — verletzt CAV-8 "
        f"(CA/B-Forum-Limit, Apple-Strenge)."
    )


def test_ca_lauf_ist_idempotent(ca):
    """Erneuter Lauf verwendet dieselbe Root-CA wieder (Trust-Anker bleibt gültig)."""
    with open(ca["ca_cert"], "rb") as f:
        ca_vorher = f.read()
    res = subprocess.run(
        ["bash", SCRIPT, "--out", ca["out"],
         "--san", "DNS:xbuddy-hub.local,IP:192.168.0.78"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "wiederverwendet" in res.stdout
    with open(ca["ca_cert"], "rb") as f:
        assert f.read() == ca_vorher, "Root-CA wurde beim zweiten Lauf verändert"
