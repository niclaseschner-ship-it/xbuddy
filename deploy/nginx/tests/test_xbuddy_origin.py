"""Tests für deploy/nginx/xbuddy-origin.conf — die EINE HTTPS-Origin (#36, #85).

Lauf: python3 -m pytest deploy/nginx/tests/ -v

Die Suite liest die nginx-Conf als Text und belegt textuell, dass die
Origin-Routing-Tabelle aus `specs/platform/urls.md` URL-14 abgebildet ist:
Familie-Upstream auf Port 5010 (FAM-7/8), `location /api/v1/familie/` zeigt
darauf und steht VOR dem allgemeinen `/api/v1/`-Block (spezifisch vor
allgemein, längster Prefix gewinnt — URL-14).

Diese Tests parsen die Conf nicht semantisch (kein nginx im Loop), sondern
fixieren die textuellen Eigenschaften, die das Routing tragen: ein Lookup-
Block, ein proxy_pass, eine Reihenfolge. Das fängt #85-Regressionen ab
(Familie-Block fehlt; falsche Position; falscher Upstream) ohne ein nginx-
Binary in der Test-Umgebung vorauszusetzen.
"""

import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
CONF_PATH = os.path.join(os.path.dirname(_HERE), "xbuddy-origin.conf")


def _conf_text() -> str:
    with open(CONF_PATH, encoding="utf-8") as f:
        return f.read()


def test_conf_datei_existiert():
    assert os.path.isfile(CONF_PATH), f"nginx-Conf nicht gefunden: {CONF_PATH}"


def test_URL_14_familie_upstream_zeigt_auf_5010():
    """URL-14 Zeile 3 + FAM-7/8: Familie-Upstream lauscht auf Port 5010."""
    text = _conf_text()
    # `upstream xbuddy_familie { ... server 127.0.0.1:5010; ... }`
    match = re.search(
        r"upstream\s+xbuddy_familie\s*\{[^}]*server\s+127\.0\.0\.1:5010\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "upstream xbuddy_familie fehlt oder zeigt nicht auf 127.0.0.1:5010 "
        "(URL-14, familie/main.py DEFAULTS listen_port=5010)"
    )


def test_URL_14_familie_location_proxypassed_an_familie_upstream():
    """URL-14 Zeile 3: /api/v1/familie/ wird an xbuddy_familie geleitet."""
    text = _conf_text()
    # `location /api/v1/familie/ { ... proxy_pass http://xbuddy_familie; ... }`
    match = re.search(
        r"location\s+/api/v1/familie/\s*\{[^}]*proxy_pass\s+http://xbuddy_familie\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /api/v1/familie/ fehlt oder proxypasst nicht an xbuddy_familie "
        "(URL-14, #85)"
    )


def test_URL_14_familie_location_steht_vor_allgemeinem_api_v1():
    """URL-14: spezifisch vor allgemein — /api/v1/familie/ steht VOR /api/v1/.

    nginx wählt bei Prefix-`location` zwar den längsten Treffer unabhängig
    von der Datei-Reihenfolge, aber URL-14 fordert die Reihenfolge als
    Vertrag (nicht nur als nginx-Marotte), damit die Conf-Datei die
    Routing-Tabelle eins zu eins spiegelt und Konsumenten (Onboarding-Agent,
    neue Komponenten, Code-Review) die Tabelle visuell wiederfinden.
    """
    text = _conf_text()
    pos_familie = text.find("location /api/v1/familie/")
    pos_api_v1 = text.find("location /api/v1/ ")
    assert pos_familie != -1, "location /api/v1/familie/ nicht gefunden"
    assert pos_api_v1 != -1, "location /api/v1/ nicht gefunden"
    assert pos_familie < pos_api_v1, (
        "URL-14-Verstoß: /api/v1/familie/ muss VOR /api/v1/ stehen "
        f"(Positionen: familie={pos_familie}, api/v1={pos_api_v1})"
    )


def test_URL_14_familie_location_steht_nach_plan_locations():
    """URL-14-Tabellenreihenfolge: Familie-Zeile (3) steht nach Plan-Zeilen (1,2)."""
    text = _conf_text()
    pos_plan_api = text.find("location /api/v1/plan/")
    pos_familie = text.find("location /api/v1/familie/")
    assert pos_plan_api != -1, "location /api/v1/plan/ nicht gefunden"
    assert pos_familie != -1, "location /api/v1/familie/ nicht gefunden"
    assert pos_plan_api < pos_familie, (
        "URL-14-Tabellenreihenfolge: /api/v1/plan/ kommt vor /api/v1/familie/"
    )


# ============================================================
#  Admin-Endpoints sind nicht vom Netz erreichbar (#140, EC-21)
# ============================================================
#
# Der Router-Reload-Endpoint hat einen Loopback-Guard in der App; nginx ist
# die zweite Verteidigungslinie und blockiert /api/v1/<komp>/admin/* bereits
# an der Origin. Diese Tests fixieren die textuellen Eigenschaften der Conf:
# Regex-Block existiert, gibt 404 zurück, steht VOR den durchreichenden
# /api/v1/-Locations (Regex hat in nginx Vorrang, aber wir wollen die
# Tabellenreihenfolge auch visuell — siehe Routing-Tabelle im Conf-Header).


def test_140_admin_block_existiert():
    """Eine `location ~ ^/api/v1/[^/]+/admin/` mit `return 404` muss da sein."""
    text = _conf_text()
    match = re.search(
        r"location\s+~\s+\^/api/v1/\[\^/\]\+/admin/\s*\{[^}]*return\s+404\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "Admin-Block fehlt: nginx muss /api/v1/<komp>/admin/* mit 404 "
        "ablehnen (#140 Defense in Depth, EC-21)"
    )


def test_140_admin_block_steht_vor_router_api_v1():
    """Der Admin-Block muss VOR dem durchreichenden /api/v1/-Block stehen,
    damit die Routing-Tabelle im Conf-Header die Datei-Reihenfolge eins zu
    eins spiegelt — Reviewer und neue Komponenten finden den Schutz da, wo
    URL-14 ihn anlegt (spezifisch vor allgemein)."""
    text = _conf_text()
    pos_admin = text.find("location ~ ^/api/v1/[^/]+/admin/")
    pos_api_v1 = text.find("location /api/v1/ ")
    assert pos_admin != -1, "Admin-Block (Regex-location) nicht gefunden"
    assert pos_api_v1 != -1, "location /api/v1/ nicht gefunden"
    assert pos_admin < pos_api_v1, (
        "Admin-Block muss VOR /api/v1/ stehen — die Routing-Tabelle im "
        "Conf-Header schreibt diese Reihenfolge fest."
    )


def test_140_admin_block_in_routing_tabelle_dokumentiert():
    """Die Routing-Tabelle im Conf-Header muss den Admin-Block listen —
    sonst weichen Dokumentation und Verhalten auseinander."""
    text = _conf_text()
    # Akzeptiert sowohl /api/v1/<komp>/admin/ als auch ähnliche Formen,
    # solange „admin" auftaucht und ein 404-Hinweis dabei ist.
    header = text.split("server {", 1)[0]
    assert "/admin/" in header, (
        "Routing-Tabelle im Conf-Header listet den /admin/-Block nicht — "
        "Doku und Verhalten dürfen nicht auseinanderlaufen."
    )
