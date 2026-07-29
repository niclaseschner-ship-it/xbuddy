"""URL-14 Vollständigkeits-Test: nginx-Conf vs conventions/urls.md.

Verhindert Drift zwischen der Origin-Routing-Tabelle (URL-14) und der
nginx-Realität (deploy/nginx/xbuddy-origin.conf). Beide sind getrennte
Schreibstellen, aber müssen denselben Pfad-Prefix-Satz tragen — sonst
zieht eine Seite (nginx-Conf, Onboarding, neuer Buddy) eine falsche Annahme.

Issue: #589.
"""

import re
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[1]
URLS_MD    = REPO_ROOT / "conventions" / "urls.md"
NGINX_CONF = REPO_ROOT / "deploy" / "nginx" / "xbuddy-origin.conf"

# ---------------------------------------------------------------------------
# Bewusste Drift — diese Pfad-Prefixe stehen in nginx als spezialisierte
# Blöcke oder Regex-Locations und brauchen keine eigene Zeile im
# nginx-Kommentar-Block (ALLOWED_DRIFT_IN_NGINX) oder in der URL-14-Tabelle
# (ALLOWED_DRIFT_IN_URLS).
# ---------------------------------------------------------------------------

# Prefixe, die im nginx-Kommentar-Block stehen, aber NICHT in der
# URL-14-Tabelle benötigt werden.
ALLOWED_DRIFT_IN_NGINX = {
    "/api/v1/<komp>/admin/",    # nginx Z. 15: Loopback-only 404-Fallback für alle
                                # Admin-Endpunkte (Regex-Location, #140 EC-21) —
                                # kein eigener Buddy-Upstream, bewusst nicht in
                                # URL-14 eingetragen.
    "/display/_shared/icons/",  # nginx Z. 16: ARASAAC-Sub-Pfad von /display/;
                                # fällt in der URL-14-Tabelle an den allgemeinen
                                # /display/→Router-Eintrag (URL-16, ROU-26, #135).
    "/api/v1/icons/suche",      # nginx: exakte Location (=) für Icon-Stichwort-Suche
                                # (ROU-31, RAT-31 E6f-B, #1586). Seiten-owned Route,
                                # kein eigener URL-14-Eintrag (spez. unter /api/v1/).
}

# Prefixe, die in der URL-14-Tabelle stehen, aber im nginx-Kommentar-Block
# fehlen — nginx-Kommentar-Block ist unvollständig, die Locations selbst
# existieren in der Conf.
ALLOWED_DRIFT_IN_URLS = {
    "/display/essen/",          # nginx hat location /display/essen/ (Z. 183),
                                # aber kein Kommentar-Eintrag im Routing-Block.
                                # Dokumentierte Lücke im nginx-Kommentar (#589).
    "/api/v1/essen/",           # nginx hat location /api/v1/essen/ (Z. 186),
                                # aber kein Kommentar-Eintrag im Routing-Block.
                                # Dokumentierte Lücke im nginx-Kommentar (#589).
    "/",                        # nginx hat location / { return 404; } (Z. 281),
                                # aber kein Kommentar-Eintrag im Routing-Block.
                                # Catch-all 404 gemäß URL-1 — kein Upstream.
                                # Dokumentierte Lücke im nginx-Kommentar (#589).
    "/display/kibuddy/",        # nginx hat location /display/kibuddy/ (Z. 282,
                                # proxy_pass xbuddy_kibuddy), aber kein
                                # Kommentar-Eintrag im Routing-Block. KIBUDDY-2.
                                # Dokumentierte Lücke im nginx-Kommentar (#589).
    "/api/v1/kibuddy/",         # nginx hat location /api/v1/kibuddy/ (Z. 285,
                                # proxy_pass xbuddy_kibuddy), aber kein
                                # Kommentar-Eintrag im Routing-Block. KIBUDDY-24.
                                # Dokumentierte Lücke im nginx-Kommentar (#589).
}


def _read_url14_prefixes() -> set[str]:
    """Parst URL-14-Tabelle in conventions/urls.md, gibt Set der Pfad-Prefixe.

    Sucht den ### URL-14 — Origin-Routing-Tabelle-Block und extrahiert
    alle Backtick-Werte aus Spalte 2 (Pfad-Prefix).
    """
    text = URLS_MD.read_text(encoding="utf-8")
    match = re.search(
        r"### URL-14 — Origin-Routing-Tabelle\n(.+?)(?=\n###|\Z)",
        text,
        re.DOTALL,
    )
    if not match:
        raise AssertionError(
            f"URL-14-Block nicht gefunden in {URLS_MD}. "
            "Erwartet: '### URL-14 — Origin-Routing-Tabelle'."
        )
    block = match.group(1)
    # Spalte 2 in Markdown-Tabelle hat Form `| <nr> | `<prefix>` | ...`
    # Nur Zeilen mit Pipe extrahieren, dann das erste Backtick-Token nehmen.
    prefixes = set()
    for line in block.splitlines():
        if "|" not in line:
            continue
        cols = [c.strip() for c in line.split("|")]
        # Tabellen-Zeilen haben die Form: | # | Pfad | Upstream | Bemerkung |
        # nach split("|"): ['', '#', 'Pfad', 'Upstream', 'Bemerkung', '']
        # Spalte 2 ist cols[2] (0-indexed nach dem leeren cols[0]).
        if len(cols) < 3:
            continue
        path_col = cols[2]
        # Header-Zeile und Trennlinie überspringen.
        if not path_col or path_col.startswith(("-", "Pfad")):
            continue
        m = re.match(r"`([^`]+)`", path_col)
        if m:
            prefixes.add(m.group(1))
    return prefixes


def _read_nginx_prefixes() -> set[str]:
    """Parst Routing-Kommentar-Block in deploy/nginx/xbuddy-origin.conf.

    Erwartet einen Kommentar-Block, der mit
    '# Routing-Tabelle (URL-14' beginnt. Jede Routing-Zeile hat die Form:
        #   <pfad>   → <upstream> …
    Der Pfeil-Operator trennt Pfad (links) von Upstream-Beschreibung
    (rechts). Normalisiert '/api/v1/seiten (exakt)' zu '/api/v1/seiten'.
    """
    text = NGINX_CONF.read_text(encoding="utf-8")
    match = re.search(
        r"# Routing-Tabelle \(URL-14.+?\n((?:#.*\n)+)",
        text,
    )
    if not match:
        raise AssertionError(
            f"Routing-Kommentar-Block nicht gefunden in {NGINX_CONF}. "
            "Erwartet: '# Routing-Tabelle (URL-14...'."
        )
    block = match.group(1)
    found = set()
    for line in block.splitlines():
        # Nur Zeilen mit Pfeil auswerten.
        if "→" not in line:
            continue
        # Kommentar-Prefix und Leerraum entfernen, dann linke Seite des Pfeils.
        content = re.sub(r"^#\s*", "", line)
        left = content.split("→")[0].strip()
        if not left:
            continue
        # "(exakt)"-Annotation und ähnliche Klammer-Zusätze entfernen.
        left = re.sub(r"\s*\([^)]*\)\s*$", "", left).strip()
        if left:
            found.add(left)
    return found


def test_URL14_nginx_und_urls_md_haben_gleichen_routing_satz():
    """URL-14 Vollständigkeits-Test (#589 — URL-14 Routing-Tabelle vervollständigen).

    Drift-Frühwarnung: beide Quellen MÜSSEN denselben Pfad-Prefix-Satz tragen,
    modulo dokumentierter Ausnahmen (ALLOWED_DRIFT_IN_NGINX /
    ALLOWED_DRIFT_IN_URLS). Eine Set-Diff-Meldung bei Drift zeigt direkt,
    welche Pfade synchronisiert werden müssen.
    """
    urls_md_prefixes = _read_url14_prefixes()
    nginx_prefixes   = _read_nginx_prefixes()

    nginx_nicht_in_urls = (nginx_prefixes - urls_md_prefixes) - ALLOWED_DRIFT_IN_NGINX
    urls_nicht_in_nginx = (urls_md_prefixes - nginx_prefixes) - ALLOWED_DRIFT_IN_URLS

    fehler = []
    if nginx_nicht_in_urls:
        fehler.append(
            "URL-14-Tabelle fehlt diese Prefixe (in nginx-Kommentar, nicht in urls.md):\n"
            + "\n".join(f"  - {p}" for p in sorted(nginx_nicht_in_urls))
        )
    if urls_nicht_in_nginx:
        fehler.append(
            "nginx-Kommentar-Block fehlt diese Prefixe (in urls.md, nicht in nginx):\n"
            + "\n".join(f"  - {p}" for p in sorted(urls_nicht_in_nginx))
        )

    assert not fehler, (
        "URL-14-Drift erkannt (#589 Drift-Frühwarn):\n\n"
        + "\n\n".join(fehler)
        + "\n\nFix: Beide Tabellen synchron halten (URL-14 in conventions/urls.md "
        "ist SSoT). Wenn bewusste Drift: ALLOWED_DRIFT_IN_NGINX oder "
        "ALLOWED_DRIFT_IN_URLS mit Begründung ergänzen."
    )
