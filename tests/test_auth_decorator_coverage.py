"""AUTH-9 — Decorator-Anwendung maschinell verriegelt (specs/platform/auth.md).

Membran zwischen Spec-Wahrheit und Code-Wahrheit: dieser Test parst die
AUTH-3-Route-Liste aus `specs/platform/auth.md` und prüft per AST des
jeweiligen Service-Moduls, dass **jede** gelistete Route den Auth-Decorator
(`@require_init_data` oder seine Cookie-Variante) im Source trägt. Fehlt der
Decorator an einer AUTH-3-Route, ist der Test rot (auth.md AUTH-9).

Phase 1 (#948) deckte **essen** ab. Der #1321-Bau (2026-07-06) hat die
method-explizite AUTH-3-Endliste um **photo/kibuddy/plan** ergänzt und den
Decorator in den drei Service-Modulen gelegt — sie sind jetzt in `MODULE_MAP`
und werden vollständig geprüft. Weitere AUTH-3-Buddies (routine/hörspiel-
eltern) wandern mit ihrem Bau-Track hinzu; bis dahin meldet der Test einen
ungemappten AUTH-3-Buddy sichtbar als „noch nicht verriegelt".
"""

from __future__ import annotations

import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTH_MD = REPO_ROOT / "specs" / "platform" / "auth.md"

# Buddy-Slug → Service-Modul. Phase 1 (#948): essen. #1321: photo/kibuddy/plan.
# Phase 2 (#1639): routine (SOFT→HART-Cookie-Migration, auth.md „AUTH-Decorator-Lib").
# Phase 3 (#1640): hoerspiel. Phase 4 (#1638): familie (PII-Datenrouten gegated).
MODULE_MAP = {
    "essen": REPO_ROOT / "essen" / "main.py",
    "photo": REPO_ROOT / "photo" / "main.py",
    "kibuddy": REPO_ROOT / "kibuddy" / "main.py",
    "plan": REPO_ROOT / "plan" / "main.py",
    "routine": REPO_ROOT / "routine" / "main.py",
    "hoerspiel": REPO_ROOT / "hoerspiel" / "main.py",
    "familie": REPO_ROOT / "familie" / "main.py",
}

# Phase-2-Route-Liste routine (#1639, method-explizit gegen die realen
# `@app.route`-Strings in routine/main.py). Spec-Wahrheit ist die AUTH-3-Prosa
# in auth.md („routine: die /api/v1/routine/*-Datenrouten … config, items");
# die method-explizite Endliste-Fence in auth.md enumeriert bisher nur
# photo/kibuddy/plan (#1321). Bis diese Fence um routine erweitert wird, hält
# der Coverage-Test die routine-AUTH-3-Endliste hier — dieselbe maschinelle
# Verriegelung wie für die gefenceten Buddies (jede Zeile = eine Flask-Route +
# Methode, gegen den AST geprüft). NICHT die Display-View /display/routine/morgen
# (AUTH-6/AUTH-7-Renderer) und nicht /healthz (SVC-6).
_ROUTINE_AUTH3_ROUTES = [
    ("/api/v1/routine/config", "GET"),
    ("/api/v1/routine/config", "PUT"),
    ("/api/v1/routine/items", "GET"),
    ("/api/v1/routine/items", "POST"),
    ("/api/v1/routine/items", "PUT"),
    ("/api/v1/routine/items/<item_id>", "DELETE"),
]

# Phase-3-Route-Liste hoerspiel (#1640, method-explizit gegen die realen
# `@app.route`-Strings in hoerspiel/main.py). Spec-Wahrheit ist die AUTH-3-Prosa
# in auth.md (Z.203/498: „hoerspiel: config, alben, alben/<id>/manifest, resume,
# themen, folgen-vorschlag"). Wie bei routine hält der Coverage-Test die
# method-explizite Endliste hier, bis die #1321-Fence sie enumeriert.
# KRITISCH — NICHT gelistet (bleiben public):
#   /api/v1/hoerspiel/<kind_id>/alben/<id>/audio/<track>.mp3  → AUTH-4 (Playback!)
#   /api/v1/hoerspiel/<kind_id>/audio-stream                  → AUTH-6 (Phase-4)
#   /healthz (SVC-6), /display/hoerspiel/* (Renderer), bible/folgen-historie
#   (nicht in der AUTH-3-Prosa-Liste — behalten ihre Klasse).
_HOERSPIEL_AUTH3_ROUTES = [
    ("/api/v1/hoerspiel/<kind_id>/config", "GET"),
    ("/api/v1/hoerspiel/<kind_id>/config", "PATCH"),
    ("/api/v1/hoerspiel/<kind_id>/alben", "GET"),
    ("/api/v1/hoerspiel/<kind_id>/alben/<album_id>/manifest", "GET"),
    ("/api/v1/hoerspiel/<kind_id>/resume", "GET"),
    ("/api/v1/hoerspiel/<kind_id>/resume", "PUT"),
    ("/api/v1/hoerspiel/<kind_id>/themen", "GET"),
    ("/api/v1/hoerspiel/<kind_id>/folgen-vorschlag", "POST"),
]

# Phase-4-Route-Liste familie (#1638, method-explizit gegen die realen
# `@app.route`-Strings in familie/main.py). Spec-Wahrheit: die AUTH-3-Prosa
# in auth.md (PII-Datenrouten der Familien-Registry sind AUTH-3-geschützt,
# da sie Namen/Fotos/Telegram-IDs enthalten). Bis die #1321-Fence diese
# Routen enumeriert, hält der Coverage-Test die Endliste hier.
# NICHT gegated (bleiben public): /healthz (SVC-1).
_FAMILIE_AUTH3_ROUTES = [
    ("/api/v1/familie/personen", "GET"),
    ("/api/v1/familie/personen/<person_id>", "GET"),
    ("/api/v1/familie/foto/<person_id>", "GET"),
    ("/api/v1/familie/personen", "POST"),
    ("/api/v1/familie/personen/<person_id>/foto", "POST"),
]

# T1389 / AUTH-7b: die Renderer-Routen (Shell/Controller/SSE) leben nicht unter
# /api/v1/<buddy>/, sondern in seiten. RAT-31-Nachzug (E6f, #1568): der frühere
# Display-Router (router/main.py) ist gelöscht — alle 7b-Fence-Routen werden jetzt
# von seiten ausgeliefert und tragen dort den Dual-Gate (auth.md AUTH-7-Fence).
# Eigener Resolver + eigene Modul-Map, damit der _buddy_of-Pfad unberührt bleibt.
MODULE_MAP_7B = {
    "seiten": REPO_ROOT / "seiten" / "main.py",
}

# Der Auth-Decorator-Name (essen/main.py `require_init_data`; auth.md AUTH-9
# nennt die Cookie-Variante ausdrücklich mit). AUTH-7b ergänzt require_dual_gate
# (mode-parametrisiert → ast.Call, nicht ast.Name).
_AUTH_DECORATORS = {"require_init_data", "require_dual_gate"}

# Method-explizite AUTH-3-Zeile: "<pfad>   (METHOD)".
_ROUTE_LINE = re.compile(r"^(/\S+)\s+\((GET|POST|PATCH|PUT|DELETE)\)\s*$")

# AUTH-7b-Fence-Zeile (auth.md AUTH-7:473-478): "<pfad>   (Prosa…)". Anderes
# Format als AUTH-3 — der Rest-Text ist Prosa (HTML-Shell / SSE / Wildcard),
# nur der Pfad (erstes Token) zählt. /controller/* ist eine Prefix-Wildcard.
_ROUTE_7B_LINE = re.compile(r"^(/\S+)\s+\(")


def _auth3_routes() -> list[tuple[str, str]]:
    """Extrahiert die method-expliziten (pfad, methode)-Paare der AUTH-3-Liste.

    Liest ALLE ```-gefencten Codeblöcke im AUTH-3-Abschnitt: die essen-V1-Liste
    UND die #1321-Endliste (photo/kibuddy/plan, method-explizit gegen die realen
    `@app.route`-Strings). Die Prosa-Aufzählung im Nachtrag bleibt unbewertet —
    Wahrheit ist der Fence."""
    text = AUTH_MD.read_text(encoding="utf-8")
    # AUTH-3-Abschnitt herausschneiden: von "### AUTH-3" bis zum nächsten "### AUTH-".
    start = text.index("### AUTH-3")
    rest = text[start + len("### AUTH-3"):]
    m = re.search(r"\n### AUTH-", rest)
    section = rest[: m.start()] if m else rest

    routen: list[tuple[str, str]] = []
    in_fence = False
    for line in section.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        treffer = _ROUTE_LINE.match(line.strip())
        if treffer:
            routen.append((treffer.group(1), treffer.group(2)))
    return routen


def _buddy_of(path: str) -> str | None:
    """/api/v1/<buddy>/... → <buddy>."""
    teile = [t for t in path.split("/") if t]
    if len(teile) >= 3 and teile[0] == "api" and teile[1] == "v1":
        return teile[2]
    return None


def _decorated_routes(module_path: pathlib.Path) -> list[dict]:
    """AST-Scan eines Service-Moduls: je Funktion die @app.route-Pfade/Methoden
    und ob ein Auth-Decorator anliegt."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    ergebnis = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        route_path = None
        methods: list[str] = []
        hat_auth = False
        for deco in node.decorator_list:
            # @require_init_data (bare Name)
            if isinstance(deco, ast.Name) and deco.id in _AUTH_DECORATORS:
                hat_auth = True
            # @require_dual_gate(mode=...) — parametrisiert → ast.Call mit Name-func
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Name) \
                    and deco.func.id in _AUTH_DECORATORS:
                hat_auth = True
            # @app.route("...", methods=[...])
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) \
                    and deco.func.attr == "route":
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    route_path = deco.args[0].value
                for kw in deco.keywords:
                    if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        methods = [
                            e.value for e in kw.value.elts
                            if isinstance(e, ast.Constant)
                        ]
        if route_path is not None:
            ergebnis.append({"path": route_path, "methods": methods, "auth": hat_auth})
    return ergebnis


def test_jede_auth3_route_traegt_den_decorator():
    """AUTH-9: jede in AUTH-3 gelistete Route eines gemappten Buddies trägt den
    Auth-Decorator im Source."""
    routen = _auth3_routes()
    assert routen, "AUTH-3-Liste leer geparst — auth.md-Format prüfen"

    # Phase-2-Nachzug (#1639): routine-AUTH-3-Routen ergänzen (Prosa-klassifiziert
    # in auth.md, method-explizit hier bis zur Fence-Erweiterung; s. _ROUTINE_AUTH3_ROUTES).
    # Phase-4-Nachzug (#1638): familie-PII-Datenrouten ergänzen.
    routen = routen + _ROUTINE_AUTH3_ROUTES + _HOERSPIEL_AUTH3_ROUTES + _FAMILIE_AUTH3_ROUTES

    # Cache je Modul.
    dekoriert = {buddy: _decorated_routes(pfad) for buddy, pfad in MODULE_MAP.items()}

    fehlend = []
    geprueft = 0
    for path, method in routen:
        buddy = _buddy_of(path)
        if buddy not in MODULE_MAP:
            continue  # ungemappter Buddy (photo/kibuddy/plan → #1321)
        geprueft += 1
        treffer = [
            r for r in dekoriert[buddy]
            if r["path"] == path and method in r["methods"]
        ]
        if not treffer:
            fehlend.append("%s (%s) — keine Flask-Route in %s"
                           % (path, method, MODULE_MAP[buddy].name))
        elif not any(r["auth"] for r in treffer):
            fehlend.append("%s (%s) — Route ohne @require_init_data" % (path, method))

    assert geprueft >= 12, (
        "Erwartet ≥12 essen-AUTH-3-Routen (inkl. DELETE gericht), geprüft: %d" % geprueft
    )
    assert not fehlend, (
        "AUTH-9-Verletzung — diese AUTH-3-Routen tragen den Decorator nicht:\n  "
        + "\n  ".join(fehlend)
    )


def test_delete_gericht_ist_in_auth3_gelistet():
    """OD5: DELETE /api/v1/essen/katalog/gerichte/<id> steht in AUTH-3."""
    routen = _auth3_routes()
    assert ("/api/v1/essen/katalog/gerichte/<gericht_id>", "DELETE") in routen, (
        "DELETE gericht_loeschen fehlt in der AUTH-3-Liste (auth.md, OD5)"
    )


# ---------------------------------------------------------------------------
# T1389 / AUTH-7b — Dual-Gate-Renderer-Routen (Shell/Display/Controller/SSE)
# ---------------------------------------------------------------------------


def _auth7b_routes() -> list[str]:
    """Extrahiert die Pfade der AUTH-7-7b-Fence-Liste (auth.md AUTH-7:473-478).

    Liest ausschließlich den ```-Fence unmittelbar nach dem 7b-Absatz („7b —
    User-Shell (Cookie)") im „### AUTH-7"-Abschnitt. Der Fence hat ein anderes
    Format als AUTH-3 (Pfad + Prosa in Klammern) — nur der Pfad zählt."""
    text = AUTH_MD.read_text(encoding="utf-8")
    start = text.index("### AUTH-7")
    rest = text[start + len("### AUTH-7"):]
    m = re.search(r"\n### AUTH-", rest)
    section = rest[: m.start()] if m else rest

    pfade: list[str] = []
    in_fence = False
    for line in section.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        treffer = _ROUTE_7B_LINE.match(line.strip())
        if treffer:
            pfade.append(treffer.group(1))
    return pfade


# Route→Modul-Resolver für 7b (RAT-31 E6f #1568, Router-Tod): ALLE 7b-Fence-Routen
# (/shell/*, /controller/*) werden von seiten ausgeliefert. Der frühere
# router/main.py (/display/<id> + SSE-Fanout) ist gelöscht; der SSE-Stream läuft
# jetzt same-origin als /shell/<panel_id>/events auf seiten.
def _module_of_7b(pfad: str) -> str | None:
    if pfad.startswith(("/shell/", "/controller/")):
        return "seiten"
    return None


def _normalize(pfad: str) -> str:
    """Vergleichsbasis: Platzhalter-Namen und Trailing-Slash abstreifen.

    Spec schreibt /display/<display_id>, Flask /display/<display_id>/; Spec
    /shell/<panel_id>, Flask ebenso. Wir vergleichen auf Segment-Präfix mit
    normalisierten <…>-Platzhaltern, damit Namens-/Slash-Drift nicht fehlschlägt.
    """
    p = re.sub(r"<[^>]+>", "<>", pfad)
    return p.rstrip("/")


def _hat_dekorierte_route(dekoriert: list[dict], spec_pfad: str) -> bool:
    """True, wenn eine dekorierte GET-Route den 7b-Spec-Pfad deckt.

    Wildcard /controller/* deckt jede dekorierte Route unter /controller/;
    sonst Präfix-Vergleich auf normalisierten Pfaden (Slash/Platzhalter-tolerant)."""
    if spec_pfad == "/controller/*":
        return any(r["auth"] and r["path"].startswith("/controller/")
                   and "GET" in r["methods"] for r in dekoriert)
    ziel = _normalize(spec_pfad)
    for r in dekoriert:
        if not r["auth"] or "GET" not in r["methods"]:
            continue
        if _normalize(r["path"]).startswith(ziel):
            return True
    return False


def test_jede_auth7b_route_traegt_den_dual_gate():
    """AUTH-9 (7b): jede AUTH-7-7b-Renderer-Route trägt require_dual_gate im
    Source ihres Moduls (alle 7b-Routen auf seiten: Shell + Controller + SSE;
    RAT-31 E6f #1568, Router-Tod)."""
    pfade = _auth7b_routes()
    assert pfade, "AUTH-7-7b-Fence leer geparst — auth.md-Format prüfen"

    dekoriert = {mod: _decorated_routes(pfad)
                 for mod, pfad in MODULE_MAP_7B.items()}

    fehlend = []
    geprueft = 0
    for pfad in pfade:
        modul = _module_of_7b(pfad)
        assert modul is not None, "7b-Pfad %s ohne Modul-Resolver" % pfad
        geprueft += 1
        if not _hat_dekorierte_route(dekoriert[modul], pfad):
            fehlend.append("%s — keine require_dual_gate-Route in %s/main.py"
                           % (pfad, modul))

    assert geprueft >= 3, (
        "Erwartet ≥3 AUTH-7-7b-Routen (shell/controller/events), "
        "geprüft: %d" % geprueft
    )
    assert not fehlend, (
        "AUTH-9-Verletzung (7b) — diese Renderer-Routen tragen den Dual-Gate "
        "nicht:\n  " + "\n  ".join(fehlend)
    )


def test_display_shared_bleibt_public_ungegatet():
    """auth.md AUTH-7 7b-Public-Ausnahme — /display/_shared/* bleibt public (kein
    Dual-Gate), sonst brechen die 7b-Views (Icons/Design-Tokens als Asset geladen).
    RAT-31 E6f (#1568): seit dem Router-Tod von seiten ausgeliefert (seiten/main.py)."""
    dekoriert = _decorated_routes(MODULE_MAP_7B["seiten"])
    shared = [r for r in dekoriert if r["path"].startswith("/display/_shared/")]
    assert shared, "/display/_shared/*-Routen in seiten nicht gefunden — Test stale?"
    verletzer = [r["path"] for r in shared if r["auth"]]
    assert not verletzer, (
        "AUTH-7:512-Verletzung — /display/_shared/* trägt den Dual-Gate "
        "(muss public bleiben): %s" % verletzer
    )


# ---------------------------------------------------------------------------
# AUTH-9 (7b) — Schärfung: ALLE nicht-_shared-7b-Routen müssen den Gate tragen
# ---------------------------------------------------------------------------
# Diese Tests prüfen nicht nur ob EINE dekorierte Route je Präfix existiert
# (wie _hat_dekorierte_route), sondern dass JEDE GET-Route unter einem 7b-Präfix
# den Dual-Gate trägt — Asset-Unterrouten eingeschlossen.
# auth.md AUTH-9 + AUTH-7 Bau-Notiz (7b-Coverage-Schärfung).

# RAT-31 E6f (#1568): der Display-Router ist tot; die 7b-Renderer-Präfixe
# /controller/* und /shell/* leben auf seiten. /display/* trägt auf seiten nur
# noch die public _shared-Assets (kein gegateter Content mehr).
_7B_CONTROLLER_PREFIXES = ("/controller/",)
_7B_SEITEN_PREFIXES = ("/shell/",)
# 301-Redirect-Routen und _shared-Pfade sind explizit ausgenommen:
#   /display/_shared/* → public (AUTH-4, AUTH-7 7b-Public-Ausnahme)
#   /controller/_shared/* → public (AUTH-4, ROU-23)
_SHARED_EXEMPT = ("/_shared/",)
_REDIRECT_EXEMPT = frozenset({
    "/controller/app-panel/<panel_id>",  # 301 → /controller/app-panel/<id>/
})

# AUTH-4-Public-Routen unter /shell/ (T1448-S3-fix, auth.md AUTH-4):
#   manifest.json — Browser holt PWA-Manifeste credential-los (Fetch-Spec);
#                   gegated 401 bricht PWA-Install (#1437).
#   <path:asset>  — icon-*.png (WebAPK-Installer credential-los, SHELL-PWA AC2).
#                   sw.js laeuft ueber die Literal-Route shell_sw_view (gated, require_dual_gate
#                   AST-sichtbar); shell_asset_view bedient nur public Icons (AUTH-4).
#   Behavioral-Membran: test_shell_sw_js_bleibt_gated_ohne_quelle (tests/test_dual_gate_7b.py)
#   belegt, dass sw.js trotz public-asset-Route 401 liefert (Literal-Route greift zuerst).
_AUTH4_PUBLIC_SEITEN_EXEMPT = frozenset({
    "/shell/<panel_id>/manifest.json",  # AUTH-4: PWA-Manifest public (heim_shell_manifest)
    "/shell/<panel_id>/<path:asset>",   # AUTH-4: icon-*.png public (shell_asset_view)
})


def _is_7b_candidate(route: dict, prefixes: tuple) -> bool:
    """True, wenn die Route unter einem 7b-Präfix liegt, nicht _shared und nicht
    ein 301-Redirect-Stub oder AUTH-4-Public-Route ist, und GET bedient."""
    path = route["path"]
    if "GET" not in route["methods"]:
        return False
    if path in _REDIRECT_EXEMPT:
        return False
    if path in _AUTH4_PUBLIC_SEITEN_EXEMPT:
        return False
    if not any(path.startswith(p) for p in prefixes):
        return False
    return not any(exempt in path for exempt in _SHARED_EXEMPT)


def test_alle_nichtshared_7b_controller_routen_tragen_dual_gate():
    """AUTH-9-Schärfung: ALLE GET-Routen unter /controller/* (außer _shared)
    müssen require_dual_gate tragen. Asset-Unterrouten
    (/controller/app-panel/<id>/<asset>) sind eingeschlossen.
    RAT-31 E6f (#1568): seit dem Router-Tod von seiten ausgeliefert; es gibt
    keine eigenständigen Router-Routen mehr — die 7b-Fläche lebt auf seiten."""
    dekoriert = _decorated_routes(MODULE_MAP_7B["seiten"])
    kandidaten = [r for r in dekoriert if _is_7b_candidate(r, _7B_CONTROLLER_PREFIXES)]
    assert kandidaten, (
        "Keine 7b-Controller-Kandidaten gefunden — Präfix-Liste oder AST-Scan prüfen"
    )
    fehlend = [r["path"] for r in kandidaten if not r["auth"]]
    assert not fehlend, (
        "AUTH-9-Schärfung (controller): diese 7b-Routen tragen require_dual_gate NICHT "
        "(Asset-Unterrouten müssen ebenfalls gegatet sein):\n  "
        + "\n  ".join(fehlend)
    )


def test_alle_nichtshared_7b_seiten_routen_tragen_dual_gate():
    """AUTH-9-Schärfung: ALLE GET-Routen unter /shell/* müssen require_dual_gate tragen.

    Ausnahmen (AUTH-4-Public, T1448-S3-fix):
      - manifest.json  → heim_shell_manifest (public, Fetch-Spec, #1437)
      - <path:asset>   → shell_asset_view (public, icon-*.png AUTH-4)
    sw.js traegt den Gate ueber die Literal-Route shell_sw_view (AST-sichtbar).
    Behavioral-Membran: test_shell_sw_js_bleibt_gated_ohne_quelle (test_dual_gate_7b.py).
    """
    dekoriert = _decorated_routes(MODULE_MAP_7B["seiten"])
    kandidaten = [r for r in dekoriert if _is_7b_candidate(r, _7B_SEITEN_PREFIXES)]
    assert kandidaten, (
        "Keine 7b-Seiten-Kandidaten gefunden — Präfix-Liste oder AST-Scan prüfen"
    )
    fehlend = [r["path"] for r in kandidaten if not r["auth"]]
    assert not fehlend, (
        "AUTH-9-Schärfung (seiten): diese 7b-Routen tragen require_dual_gate NICHT "
        "(HTML-Shell und sw.js-Literal-Route muessen gegatet sein):\n  "
        + "\n  ".join(fehlend)
    )
