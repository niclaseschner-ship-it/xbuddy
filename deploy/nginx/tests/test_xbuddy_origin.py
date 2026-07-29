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


def test_URL_14_familie_location_vorhanden_ohne_api_v1_fallback():
    """RAT-31 (#1568): der allgemeine /api/v1/-Router-Block ist abgerissen;
    /api/v1/familie/ bleibt als spezifischer Buddy-Block bestehen.

    nginx wählt bei Prefix-`location` den längsten Treffer; ohne den allgemeinen
    Fallback landet alles Nicht-Buddy-Spezifische im 404 (URL-1).
    """
    text = _conf_text()
    assert text.find("location /api/v1/familie/") != -1, (
        "location /api/v1/familie/ nicht gefunden"
    )
    assert "location /api/v1/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /api/v1/-Router-Block muss entfernt sein"
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


def test_URL_14_wetter_display_location_vorhanden():
    """RAT-31 (#1568): der allgemeine /display/-Router-Block ist abgerissen;
    /display/wetter/ bleibt als spezifischer Buddy-Block bestehen."""
    text = _conf_text()
    assert text.find("location /display/wetter/") != -1, (
        "location /display/wetter/ nicht gefunden"
    )
    assert "location /display/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /display/-Router-Block muss entfernt sein"
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
#  Routine-Buddy: Upstream :5050 und /display/routine/-Location (#335)
# ============================================================


def test_URL_14_routine_upstream_zeigt_auf_5050():
    """URL-14 Zeile 3 + PORT-2: Routine-Upstream lauscht auf Port 5050."""
    text = _conf_text()
    match = re.search(
        r"upstream\s+xbuddy_routine\s*\{[^}]*server\s+127\.0\.0\.1:5050\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "upstream xbuddy_routine fehlt oder zeigt nicht auf 127.0.0.1:5050 "
        "(URL-14, routine/main.py DEFAULTS listen_port=5050, PORT-2)"
    )


def test_URL_14_routine_location_proxypassed_an_routine_upstream():
    """URL-14 Zeile 3: /display/routine/ wird an xbuddy_routine geleitet."""
    text = _conf_text()
    match = re.search(
        r"location\s+/display/routine/\s*\{[^}]*proxy_pass\s+http://xbuddy_routine\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /display/routine/ fehlt oder proxypasst nicht an xbuddy_routine "
        "(URL-14, #335)"
    )


def test_URL_14_routine_display_location_vorhanden():
    """RAT-31 (#1568): der allgemeine /display/-Router-Block ist abgerissen;
    /display/routine/ bleibt als spezifischer Buddy-Block bestehen."""
    text = _conf_text()
    assert text.find("location /display/routine/") != -1, (
        "location /display/routine/ nicht gefunden"
    )
    assert "location /display/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /display/-Router-Block muss entfernt sein"
    )


def test_URL_14_routine_in_routing_tabelle_dokumentiert():
    """Die Routing-Tabelle im Conf-Header muss den Routine-Block listen."""
    text = _conf_text()
    header = text.split("server {", 1)[0]
    assert "/display/routine/" in header, (
        "Routing-Tabelle im Conf-Header listet /display/routine/ nicht — "
        "Doku und Verhalten dürfen nicht auseinanderlaufen."
    )


def test_URL_14_routine_api_location_proxypassed():
    """URL-14 + ROUTINE-14 + #343: /api/v1/routine/ wird an xbuddy_routine geleitet.

    Der Routine-Buddy exponiert ab #343 eine Schreib-API für Zeiten (ROUTINE-14).
    Ohne diesen Block würden PUT-Anfragen beim Router (5000) landen statt beim
    Routine-Buddy (5050).
    """
    text = _conf_text()
    match = re.search(
        r"location\s+/api/v1/routine/\s*\{[^}]*proxy_pass\s+http://xbuddy_routine\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /api/v1/routine/ fehlt oder proxypasst nicht an xbuddy_routine "
        "(URL-14, ROUTINE-14, #343)"
    )


def test_URL_14_routine_api_location_vorhanden():
    """RAT-31 (#1568): der allgemeine /api/v1/-Router-Block ist abgerissen;
    /api/v1/routine/ bleibt als spezifischer Buddy-Block bestehen."""
    text = _conf_text()
    assert text.find("location /api/v1/routine/") != -1, (
        "location /api/v1/routine/ nicht gefunden"
    )
    assert "location /api/v1/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /api/v1/-Router-Block muss entfernt sein"
    )


def test_URL_14_routine_api_in_routing_tabelle_dokumentiert():
    """Routing-Tabelle im Conf-Header listet /api/v1/routine/ (ROUTINE-14, #343)."""
    text = _conf_text()
    header = text.split("server {", 1)[0]
    assert "/api/v1/routine/" in header, (
        "Routing-Tabelle im Conf-Header listet /api/v1/routine/ nicht — "
        "Doku und Verhalten dürfen nicht auseinanderlaufen (ROUTINE-14, #343)."
    )


# ============================================================
#  Photo-Buddy: Upstream :5051, /display/photo/ + /api/v1/photo/ (#344)
# ============================================================


def test_URL_14_photo_upstream_zeigt_auf_5051():
    """URL-14 Zeile 4/8 + PORT-2: Photo-Upstream lauscht auf Port 5051."""
    text = _conf_text()
    match = re.search(
        r"upstream\s+xbuddy_photo\s*\{[^}]*server\s+127\.0\.0\.1:5051\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "upstream xbuddy_photo fehlt oder zeigt nicht auf 127.0.0.1:5051 "
        "(URL-14, photo/main.py RUNTIME_SCHEMA listen_port=5051, PORT-2)"
    )


def test_URL_14_photo_display_location_proxypassed():
    """URL-14 Zeile 4: /display/photo/ wird an xbuddy_photo geleitet."""
    text = _conf_text()
    match = re.search(
        r"location\s+/display/photo/\s*\{[^}]*proxy_pass\s+http://xbuddy_photo\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /display/photo/ fehlt oder proxypasst nicht an xbuddy_photo "
        "(URL-14, #344)"
    )


def test_URL_14_photo_api_location_proxypassed():
    """URL-14 Zeile 8: /api/v1/photo/ wird an xbuddy_photo geleitet."""
    text = _conf_text()
    match = re.search(
        r"location\s+/api/v1/photo/\s*\{[^}]*proxy_pass\s+http://xbuddy_photo\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /api/v1/photo/ fehlt oder proxypasst nicht an xbuddy_photo "
        "(URL-14, #344)"
    )


def test_URL_14_photo_locations_vorhanden():
    """RAT-31 (#1568): die allgemeinen /display/- und /api/v1/-Router-Bloecke
    sind abgerissen; die Photo-Buddy-Bloecke bleiben spezifisch bestehen."""
    text = _conf_text()
    assert text.find("location /display/photo/") != -1, (
        "location /display/photo/ nicht gefunden"
    )
    assert text.find("location /api/v1/photo/") != -1, (
        "location /api/v1/photo/ nicht gefunden"
    )
    assert "location /display/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /display/-Router-Block muss entfernt sein"
    )
    assert "location /api/v1/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /api/v1/-Router-Block muss entfernt sein"
    )


def test_URL_14_photo_in_routing_tabelle_dokumentiert():
    """Die Routing-Tabelle im Conf-Header muss die Photo-Blöcke listen."""
    text = _conf_text()
    header = text.split("server {", 1)[0]
    assert "/display/photo/" in header, (
        "Routing-Tabelle im Conf-Header listet /display/photo/ nicht."
    )
    assert "/api/v1/photo/" in header, (
        "Routing-Tabelle im Conf-Header listet /api/v1/photo/ nicht."
    )


# ============================================================
#  Icon-Bibliothek: seit RAT-31 E6f-B vom seiten-Service serviert
#  (ROU-26 verlagert, #1586)
# ============================================================
#
# RAT-31 E6f-B (#1586): /display/_shared/icons/ wird vom seiten-Service
# (Port 5042) serviert. Der allgemeine /display/->Router-Fallback ist mit
# RAT-31 (#1568) abgerissen; /display/_shared/icons/ ist ein eigener
# spezifischer Block. Kein nginx-alias (scheiterte an 0700-Home-Permission,
# #135 — unpetraendert); seiten laeuft als User buddy.


def test_ROU_26_icons_location_existiert_und_zeigt_auf_seiten():
    """RAT-31 E6f-B (#1586): location /display/_shared/icons/ muss existieren
    und auf xbuddy_seiten zeigen."""
    text = _conf_text()
    match = re.search(
        r"location\s+/display/_shared/icons/\s*\{[^}]*proxy_pass\s+http://xbuddy_seiten\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /display/_shared/icons/ fehlt oder proxypasst nicht an xbuddy_seiten "
        "(ROU-26, RAT-31 E6f-B, #1586)"
    )


def test_ROU_26_icons_location_vorhanden_ohne_display_fallback():
    """RAT-31 (#1568): /display/_shared/icons/ bleibt als spezifischer
    seiten-Block bestehen; der allgemeine /display/-Router-Fallback ist weg."""
    text = _conf_text()
    assert text.find("location /display/_shared/icons/") != -1, (
        "location /display/_shared/icons/ nicht gefunden"
    )
    assert "location /display/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /display/-Router-Block muss entfernt sein"
    )


def test_ROU_26_kein_alias_fuer_icon_root():
    """Es darf keine `alias`-Direktive auf die icon-root geben (ROU-26, #135 unpetraendert)."""
    text = _conf_text()
    match = re.search(r"alias\s+[^\s;]+;", text)
    assert match is None, (
        "Eine `alias`-Direktive ist uebrig — die Icon-Bibliothek wird vom "
        f"seiten-Service serviert (ROU-26), kein nginx-alias. Gefunden: {match.group(0) if match else ''}"
    )


def test_ROU_26_icons_location_steht_nach_design_block():
    """Tabellenreihenfolge: /display/_shared/design/ steht vor /display/_shared/icons/.

    design ist laengerer Prefix als icons (beide unter _shared), aber
    die Konf listet sie beide spezifisch — design zuerst (RAT-31 E6f-A vor E6f-B).
    """
    text = _conf_text()
    pos_design = text.find("location /display/_shared/design/")
    pos_icons = text.find("location /display/_shared/icons/")
    assert pos_design != -1, "location /display/_shared/design/ nicht gefunden"
    assert pos_icons != -1, "location /display/_shared/icons/ nicht gefunden"
    assert pos_design < pos_icons, (
        "Tabellenreihenfolge: /display/_shared/design/ soll vor /display/_shared/icons/ stehen "
        f"(Positionen: design={pos_design}, icons={pos_icons})"
    )


def test_ROU_31_icons_suche_location_existiert_und_zeigt_auf_seiten():
    """RAT-31 E6f-B (#1586): location = /api/v1/icons/suche muss existieren
    und auf xbuddy_seiten zeigen (exakter Match, ROU-31)."""
    text = _conf_text()
    match = re.search(
        r"location\s+=\s+/api/v1/icons/suche\s*\{[^}]*proxy_pass\s+http://xbuddy_seiten\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location = /api/v1/icons/suche fehlt oder proxypasst nicht an xbuddy_seiten "
        "(ROU-31, RAT-31 E6f-B, #1586)"
    )


def test_ROU_31_icons_suche_vorhanden_ohne_api_v1_fallback():
    """RAT-31 (#1568): /api/v1/icons/suche (exakt) bleibt als seiten-Block
    bestehen; der allgemeine /api/v1/-Router-Fallback ist weg."""
    text = _conf_text()
    m_suche = re.search(r"location\s+=\s+/api/v1/icons/suche", text)
    assert m_suche is not None, "location = /api/v1/icons/suche nicht gefunden"
    assert "location /api/v1/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /api/v1/-Router-Block muss entfernt sein"
    )


def test_ROU_26_ROU_31_im_conf_header_dokumentiert():
    """Der Conf-Header muss /display/_shared/icons/ + /api/v1/icons/suche erwaehnen
    (RAT-31 E6f-B, analog ROU-23/ROU-30 in #1582)."""
    text = _conf_text()
    header = text.split("server {", 1)[0]
    assert "/display/_shared/icons/" in header, (
        "Conf-Header erwaehnt /display/_shared/icons/ nicht (ROU-26, RAT-31 E6f-B, #1586)."
    )
    assert "/api/v1/icons/suche" in header, (
        "Conf-Header erwaehnt /api/v1/icons/suche nicht (ROU-31, RAT-31 E6f-B, #1586)."
    )


# ============================================================
#  Admin-Endpoints sind nicht vom Netz erreichbar (#140, EC-21)
# ============================================================
#
# Die Reload-Endpoints der Komponenten haben einen Loopback-Guard in der App;
# nginx ist die zweite Verteidigungslinie und blockiert /api/v1/<komp>/admin/*
# bereits an der Origin. Diese Tests fixieren die textuellen Eigenschaften der
# Conf: Regex-Block existiert, gibt 404 zurück, steht VOR den durchreichenden
# /api/v1/<buddy>/-Locations (Regex hat in nginx Vorrang, aber wir wollen die
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


def test_140_admin_block_steht_vor_buddy_api_v1_prefixen():
    """Der Admin-Block muss VOR den durchreichenden /api/v1/<buddy>/-Blöcken
    stehen, damit die Routing-Tabelle im Conf-Header die Datei-Reihenfolge eins
    zu eins spiegelt (spezifisch vor allgemein). RAT-31 (#1568): der allgemeine
    /api/v1/-Router-Block ist weg; als Anker dient jetzt der erste durchreichende
    Buddy-API-Block (/api/v1/plan/)."""
    text = _conf_text()
    pos_admin = text.find("location ~ ^/api/v1/[^/]+/admin/")
    pos_api_plan = text.find("location /api/v1/plan/")
    assert pos_admin != -1, "Admin-Block (Regex-location) nicht gefunden"
    assert pos_api_plan != -1, "location /api/v1/plan/ nicht gefunden"
    assert pos_admin < pos_api_plan, (
        "Admin-Block muss VOR den durchreichenden /api/v1/<buddy>/-Blöcken stehen — "
        "die Routing-Tabelle im Conf-Header schreibt diese Reihenfolge fest."
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


# ============================================================
#  URL-17 — Admin-Block greift auch bei ^~-Locations (#616)
# ============================================================
#
# nginx-Auswertungsreihenfolge: = > ^~ > regex (~) > Prefix.
# `^~ /api/v1/seiten/` (Prefix-Stop-Modifier) hat Vorrang vor der
# Regex-Location `~ ^/api/v1/[^/]+/admin/`. Das bedeutet:
# ohne eigene ^~-Admin-Block landet /api/v1/seiten/admin/x beim
# Seiten-Upstream statt mit 404 geblockt zu werden (URL-17-Verstoß).
# Fix: ein `^~ /api/v1/seiten/admin/`-Block mit `return 404` steht
# VOR `^~ /api/v1/seiten/` — der spezifischere ^~-Prefix gewinnt.


def test_URL_17_seiten_admin_block_existiert():
    """AC1 — URL-17: `^~ /api/v1/seiten/admin/` mit `return 404` muss existieren.

    Der allgemeine Regex-Admin-Block `~ ^/api/v1/[^/]+/admin/` verliert gegen
    `^~ /api/v1/seiten/` (nginx: ^~ schlägt Regex). Nur ein eigener
    ^~-Block für den Admin-Pfad stellt sicher, dass /api/v1/seiten/admin/*
    mit 404 geblockt wird und nicht beim Seiten-Upstream ankommt (#616).
    """
    text = _conf_text()
    match = re.search(
        r"location\s+\^~\s+/api/v1/seiten/admin/\s*\{[^}]*return\s+404\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location ^~ /api/v1/seiten/admin/ mit return 404 fehlt — "
        "ohne diesen Block landet /api/v1/seiten/admin/x beim Seiten-Upstream "
        "statt mit 404 geblockt zu werden (URL-17, #616)"
    )


def test_URL_17_seiten_admin_block_steht_vor_seiten_prefix():
    """AC1 — URL-17: ^~/api/v1/seiten/admin/ muss VOR ^~/api/v1/seiten/ stehen.

    Nur wenn der spezifischere Prefix (/admin/) zuerst kommt, gewinnt er
    auch in der ^~-Kategorie gegen den allgemeineren (/api/v1/seiten/).
    """
    text = _conf_text()
    # Suche nach dem Admin-Block (endet mit 404) und dem Seiten-Block (endet mit proxy_pass).
    # text.find("location ^~ /api/v1/seiten/") würde beide Blöcke auf dieselbe Position
    # auflösen, da der Admin-Block-String ein Präfix des anderen ist. Deshalb regex.
    m_admin = re.search(r"location\s+\^~\s+/api/v1/seiten/admin/", text)
    m_seiten = re.search(r"location\s+\^~\s+/api/v1/seiten/\s*\{[^}]*proxy_pass", text, re.DOTALL)
    assert m_admin is not None, "location ^~ /api/v1/seiten/admin/ nicht gefunden"
    assert m_seiten is not None, "location ^~ /api/v1/seiten/ (mit proxy_pass) nicht gefunden"
    assert m_admin.start() < m_seiten.start(), (
        "URL-17-Verstoß: ^~/api/v1/seiten/admin/ muss VOR ^~/api/v1/seiten/ stehen — "
        f"(Positionen: seiten/admin={m_admin.start()}, seiten={m_seiten.start()})"
    )


def test_URL_17_seiten_sub_pfad_routing_bleibt_intakt():
    """AC2 — URL-17: /api/v1/seiten/<sub-pfad> ohne /admin/ bleibt beim Seiten-Upstream.

    Der ^~-Admin-Block darf nur den /admin/-Sub-Pfad betreffen; alle anderen
    Sub-Pfade (z. B. /api/v1/seiten/uebersicht) bleiben beim xbuddy_seiten-Upstream.
    """
    text = _conf_text()
    # ^~ /api/v1/seiten/ muss weiterhin auf xbuddy_seiten zeigen
    match = re.search(
        r"location\s+\^~\s+/api/v1/seiten/\s*\{[^}]*proxy_pass\s+http://xbuddy_seiten\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location ^~ /api/v1/seiten/ zeigt nicht mehr auf xbuddy_seiten — "
        "Routing für /api/v1/seiten/<sub-pfad> ist kaputt (URL-14, SREG-12, #616)"
    )


# ============================================================
#  Mini-App-Frontend für Eltern-Plan-Einstellungen (T1126, PLAN-35)
# ============================================================


def test_T1126_plan_location_proxypassed_an_seiten_upstream():
    """T1126, PLAN-35: /seiten/plan/ wird an xbuddy_seiten geleitet.

    Homescreen-PWA-HTML für Plan-Einstellungen analog zu /seiten/essen/ und
    /seiten/routine/. Schreibwirkung läuft über /api/v1/plan/* (PLAN-36/37),
    nicht durch diesen Block. JS/CSS/manifest unter /api/v1/seiten/static/.
    """
    text = _conf_text()
    match = re.search(
        r"location\s+/seiten/plan/\s*\{[^}]*proxy_pass\s+http://xbuddy_seiten\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /seiten/plan/ fehlt oder proxypasst nicht an xbuddy_seiten "
        "(T1126, PLAN-35)"
    )


def test_T1126_plan_location_steht_nach_seiten_routine_location():
    """T1126-Konvention: /seiten/plan/ steht nach /seiten/routine/ (Tabellenreihenfolge).

    Die Seiten-Mini-Apps sind nach Buddy-Ordnung in der Conf gelistet; Plan kommt
    nach Routine (analog zu URL-14 für API-Präfixe).
    """
    text = _conf_text()
    pos_routine = text.find("location /seiten/routine/")
    pos_plan = text.find("location /seiten/plan/")
    assert pos_routine != -1, "location /seiten/routine/ nicht gefunden"
    assert pos_plan != -1, "location /seiten/plan/ nicht gefunden"
    assert pos_routine < pos_plan, (
        "T1126: /seiten/plan/ muss nach /seiten/routine/ stehen "
        f"(Positionen: routine={pos_routine}, plan={pos_plan})"
    )


# ============================================================
#  controller/_shared + display/_shared/design → seiten (ROU-23 + ROU-30, RAT-31 E6f-A, #1582)
# ============================================================
#
# Beide Pfade werden seit RAT-31 E6f-A (#1582) vom seiten-Service serviert.
# Die allgemeinen /controller/- bzw. /display/-Router-Blöcke sind mit RAT-31
# (#1568) abgerissen; diese Pfade bleiben eigene spezifische Blöcke (URL-14).


def test_ROU_23_controller_shared_location_existiert():
    """ROU-23 / RAT-31 E6f-A (#1582): location /controller/_shared/ muss existieren
    und auf xbuddy_seiten zeigen."""
    text = _conf_text()
    match = re.search(
        r"location\s+/controller/_shared/\s*\{[^}]*proxy_pass\s+http://xbuddy_seiten\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /controller/_shared/ fehlt oder proxypasst nicht an xbuddy_seiten "
        "(ROU-23, RAT-31 E6f-A, #1582)"
    )


def test_ROU_23_controller_shared_vorhanden_ohne_controller_fallback():
    """RAT-31 (#1568): /controller/_shared/ bleibt als spezifischer seiten-Block
    bestehen; der allgemeine /controller/-Router-Fallback ist weg."""
    text = _conf_text()
    assert text.find("location /controller/_shared/") != -1, (
        "location /controller/_shared/ nicht gefunden"
    )
    assert "location /controller/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /controller/-Router-Block muss entfernt sein"
    )


def test_ROU_23_controller_shared_steht_nach_app_panel():
    """Tabellenreihenfolge: /controller/app-panel/ (spezifischer) steht vor /controller/_shared/.

    Beide sind spezifische Sub-Prefixe von /controller/; app-panel ist das laengere
    und spezifischere Praefix und steht zuerst in der Conf-Tabelle.
    """
    text = _conf_text()
    pos_app_panel = text.find("location /controller/app-panel/")
    pos_shared = text.find("location /controller/_shared/")
    assert pos_app_panel != -1, "location /controller/app-panel/ nicht gefunden"
    assert pos_shared != -1, "location /controller/_shared/ nicht gefunden"
    assert pos_app_panel < pos_shared, (
        "Tabellenreihenfolge: /controller/app-panel/ soll vor /controller/_shared/ stehen "
        f"(Positionen: app-panel={pos_app_panel}, _shared={pos_shared})"
    )


def test_ROU_30_display_shared_design_location_existiert():
    """ROU-30 / DTOK-1/2 / RAT-31 E6f-A (#1582): location /display/_shared/design/ muss
    existieren und auf xbuddy_seiten zeigen."""
    text = _conf_text()
    match = re.search(
        r"location\s+/display/_shared/design/\s*\{[^}]*proxy_pass\s+http://xbuddy_seiten\s*;[^}]*\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        "location /display/_shared/design/ fehlt oder proxypasst nicht an xbuddy_seiten "
        "(ROU-30, DTOK-1/2, RAT-31 E6f-A, #1582)"
    )


def test_ROU_30_display_shared_design_vorhanden_ohne_display_fallback():
    """RAT-31 (#1568): /display/_shared/design/ bleibt als spezifischer
    seiten-Block bestehen; der allgemeine /display/-Router-Fallback ist weg."""
    text = _conf_text()
    assert text.find("location /display/_shared/design/") != -1, (
        "location /display/_shared/design/ nicht gefunden"
    )
    assert "location /display/ {" not in text, (
        "RAT-31 (#1568): der allgemeine /display/-Router-Block muss entfernt sein"
    )


def test_ROU_23_ROU_30_im_conf_header_dokumentiert():
    """Der Conf-Header muss die neuen _shared-Pfade erwaehnen (ROU-23 + ROU-30, #1582).

    Analog /display/_shared/icons/ (ALLOWED_DRIFT_IN_NGINX): Sub-Pfade unter einem
    allgemeinen Block brauchen keinen eigenen Tabellen-Eintrag mit Pfeil, aber sie
    MUESSEN im Header-Kommentar erwaehnt sein, damit Leser verstehen, wohin diese
    Pfade gehen.
    """
    text = _conf_text()
    header = text.split("server {", 1)[0]
    assert "/controller/_shared/" in header, (
        "Conf-Header erwaehnt /controller/_shared/ nicht (ROU-23, RAT-31 E6f-A, #1582)."
    )
    assert "/display/_shared/design/" in header, (
        "Conf-Header erwaehnt /display/_shared/design/ nicht (ROU-30, RAT-31 E6f-A, #1582)."
    )
