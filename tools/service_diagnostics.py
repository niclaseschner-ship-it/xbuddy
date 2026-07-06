"""Geteilte Diagnose-Naht der HTTP-Services (SVC-6).

EINE Definition des `/version`-Endpunkts, den der Router und alle Buddy-Services
teilen — statt 12 byte-identischer Kopien des `_deploy_version`-Blocks
(CLAUDE.md §6: dieselbe Logik nicht zweimal). Jeder Service registriert die
Route mit EINER Zeile::

    from tools.service_diagnostics import register_version
    register_version(app)

SVC-6: `/version` liefert die **beim Deploy geschriebene** Commit-SHA aus
`__XBUDDY_DATA__/deploy/version` (Default /home/buddy/xbuddy-data, ENV
XBUDDY_DATA_DIR) — **kein** `git rev-parse` zur Laufzeit (ein paralleler
Worktree/Branch-Rest würde sonst einen falschen SHA einfrieren). Der Router
behält seinen eigenen `/health`-Fan-in; nur `/version` wird hier geteilt.
"""

import os

from flask import jsonify


def _deploy_version():
    """SVC-6: laufende Commit-SHA aus der beim Deploy geschriebenen Datei
    `__XBUDDY_DATA__/deploy/version` (Default /home/buddy/xbuddy-data, ENV
    XBUDDY_DATA_DIR). Kein `git rev-parse` zur Laufzeit. Fehlt die Datei
    (noch kein Deploy), liefert /version null."""
    data_dir = os.environ.get("XBUDDY_DATA_DIR", "/home/buddy/xbuddy-data")
    path = os.path.join(data_dir, "deploy", "version")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def register_version(app):
    """Registriert `GET /version` (SVC-6) auf der Flask-`app`. EINE Zeile je
    Service; ersetzt die 12 duplizierten `_deploy_version`-Blöcke (T1311/#1311).
    Verhalten identisch zu den Kopien: file-based, kein `git rev-parse`."""

    @app.route("/version", methods=["GET"])
    def version():
        """SVC-6: liefert die laufende Deploy-Commit-SHA (oder null)."""
        return jsonify({"version": _deploy_version()}), 200

    return version
