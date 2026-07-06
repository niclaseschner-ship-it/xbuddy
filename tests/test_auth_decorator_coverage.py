"""AUTH-9 — Decorator-Anwendung maschinell verriegelt (specs/platform/auth.md).

Membran zwischen Spec-Wahrheit und Code-Wahrheit: dieser Test parst die
AUTH-3-Route-Liste aus `specs/platform/auth.md` und prüft per AST des
jeweiligen Service-Moduls, dass **jede** gelistete Route den Auth-Decorator
(`@require_init_data` oder seine Cookie-Variante) im Source trägt. Fehlt der
Decorator an einer AUTH-3-Route, ist der Test rot (auth.md AUTH-9).

Phase 1 (#948) deckt **essen** ab. Die method-explizite AUTH-3-Liste enthält
zusätzlich photo/kibuddy/plan-Routen (Phase-1-Nachtrag 2026-07-06, #1321-Bau);
deren Module wandern in `MODULE_MAP`, sobald ihr Bau-Track den Decorator legt.
Bis dahin prüft dieser Test die gemappten Buddies (essen) vollständig und
meldet ungemappte AUTH-3-Buddies sichtbar als „noch nicht verriegelt" — ohne
den essen-Vertrag zu verwässern.
"""

from __future__ import annotations

import ast
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
AUTH_MD = REPO_ROOT / "specs" / "platform" / "auth.md"

# Buddy-Slug → Service-Modul (Phase 1: nur essen). #1321 ergänzt photo/kibuddy/plan.
MODULE_MAP = {
    "essen": REPO_ROOT / "essen" / "main.py",
}

# Der Auth-Decorator-Name (essen/main.py `require_init_data`; auth.md AUTH-9
# nennt die Cookie-Variante ausdrücklich mit).
_AUTH_DECORATORS = {"require_init_data"}

# Method-explizite AUTH-3-Zeile: "<pfad>   (METHOD)".
_ROUTE_LINE = re.compile(r"^(/\S+)\s+\((GET|POST|PATCH|PUT|DELETE)\)\s*$")


def _auth3_routes() -> list[tuple[str, str]]:
    """Extrahiert die method-expliziten (pfad, methode)-Paare der AUTH-3-Liste.

    Liest ausschließlich die ```-gefencten Codeblöcke im AUTH-3-Abschnitt
    (die essen-V1-Liste ist method-explizit; die photo/kibuddy/plan-Ergänzung
    steht als Prosa-Aufzählung und wird bewusst nicht mitgeparst — sie ist
    #1321-Sache und noch nicht method-explizit)."""
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
