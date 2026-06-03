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
    """URL-14-Tabellenreihenfolge: Familie-Zeile (4) steht nach Plan-Zeilen (1,3)."""
    text = _conf_text()
    pos_plan_api = text.find("location /api/v1/plan/")
    pos_familie = text.find("location /api/v1/familie/")
    assert pos_plan_api != -1, "location /api/v1/plan/ nicht gefunden"
    assert pos_familie != -1, "location /api/v1/familie/ nicht gefunden"
    assert pos_plan_api < pos_familie, (
        "URL-14-Tabellenreihenfolge: /api/v1/plan/ kommt vor /api/v1/familie/"
    )


# ============================================================
#  Wetter-Buddy: Upstream :5030 und /display/wetter/-Location (#137)
# ============================================================


def test_URL_14_wetter_upstream_zeigt_auf_5030():
    """URL-14 Zeile 2 + PORT-2: Wetter-Upstream lauscht auf Port 5030."""
    text = _conf_text()
    match = re.search(
        r"upstream\s+xbuddy_wetter\s*\{[^}]*server\s+127\.0\.0\.1:5030\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "upstream xbuddy_wetter fehlt oder zeigt nicht auf 127.0.0.1:5030 "
        "(URL-14, wetter/main.py DEFAULTS listen_port=5030, PORT-2)"
    )


def test_URL_14_wetter_location_proxypassed_an_wetter_upstream():
    """URL-14 Zeile 2: /display/wetter/ wird an xbuddy_wetter geleitet."""
    text = _conf_text()
    match = re.search(
        r"location\s+/display/wetter/\s*\{[^}]*proxy_pass\s+http://xbuddy_wetter\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /display/wetter/ fehlt oder proxypasst nicht an xbuddy_wetter "
        "(URL-14, #137)"
    )


def test_URL_14_wetter_location_steht_vor_allgemeinem_display():
    """URL-14: spezifisch vor allgemein — /display/wetter/ steht VOR /display/."""
    text = _conf_text()
    pos_wetter = text.find("location /display/wetter/")
    pos_display = text.find("location /display/ ")
    assert pos_wetter != -1, "location /display/wetter/ nicht gefunden"
    assert pos_display != -1, "location /display/ nicht gefunden"
    assert pos_wetter < pos_display, (
        "URL-14-Verstoß: /display/wetter/ muss VOR /display/ stehen "
        f"(Positionen: wetter={pos_wetter}, display={pos_display})"
    )


def test_URL_14_wetter_location_steht_nach_plan_display_location():
    """URL-14-Tabellenreihenfolge: Wetter-Zeile (2) steht nach Plan-Zeile (1)."""
    text = _conf_text()
    pos_plan_display = text.find("location /display/plan/")
    pos_wetter = text.find("location /display/wetter/")
    assert pos_plan_display != -1, "location /display/plan/ nicht gefunden"
    assert pos_wetter != -1, "location /display/wetter/ nicht gefunden"
    assert pos_plan_display < pos_wetter, (
        "URL-14-Tabellenreihenfolge: /display/plan/ kommt vor /display/wetter/"
    )


def test_URL_14_wetter_in_routing_tabelle_dokumentiert():
    """Die Routing-Tabelle im Conf-Header muss den Wetter-Block listen."""
    text = _conf_text()
    header = text.split("server {", 1)[0]
    assert "/display/wetter/" in header, (
        "Routing-Tabelle im Conf-Header listet /display/wetter/ nicht — "
        "Doku und Verhalten dürfen nicht auseinanderlaufen."
    )


# ============================================================
#  Icon-Bibliothek: vom Router serviert, KEIN nginx-alias (#135, ROU-26)
# ============================================================
#
# Korrektur zu #135: /display/_shared/icons/ wird NICHT mehr per nginx-
# `alias` ausgeliefert (scheiterte an der 0700-Home-Permission, nginx =
# www-data). Stattdessen serviert der Router die icon-root (ROU-26,
# Zwilling zu ROU-23). In der Conf heißt das: KEIN eigener icons-Block,
# und /display/_shared/icons/ fällt an den allgemeinen /display/->Router-
# Block (URL-14, ROU-26).


def test_ROU_26_kein_eigener_icons_location_block():
    """Korrektur #135: es darf KEINE eigene location /display/_shared/icons/
    mehr geben — die Icons serviert der Router über /display/ (ROU-26)."""
    text = _conf_text()
    assert "location /display/_shared/icons/" not in text, (
        "location /display/_shared/icons/ darf nicht mehr existieren — der "
        "Router serviert die Icon-Bibliothek (ROU-26, #135). Der alte "
        "nginx-alias scheiterte an der 0700-Home-Permission."
    )


def test_ROU_26_kein_alias_fuer_icon_root():
    """Es darf keine `alias`-Direktive auf die icon-root mehr geben — das war
    der gescheiterte Serving-Weg (ROU-26, #135)."""
    text = _conf_text()
    match = re.search(r"alias\s+[^\s;]+;", text)
    assert match is None, (
        "Eine `alias`-Direktive ist übrig — die Icon-Bibliothek wird vom "
        f"Router serviert (ROU-26), kein nginx-alias mehr. Gefunden: {match.group(0) if match else ''}"
    )


def test_ROU_26_icons_faellt_an_display_router_block():
    """`/display/_shared/icons/` muss vom allgemeinen /display/->Router-Block
    abgedeckt sein: dieser proxy_pass an den Router existiert (ROU-26)."""
    text = _conf_text()
    match = re.search(
        r"location\s+/display/\s*\{[^}]*proxy_pass\s+http://xbuddy_router\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /display/ fehlt oder proxypasst nicht an xbuddy_router — "
        "der Router serviert /display/_shared/icons/ über diesen Block (ROU-26, #135)"
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
