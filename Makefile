# XBuddy — Entwickler-Targets.
# `make lint` prüft die Modul-Grenzen (conventions/module-boundaries.md, MOD-*)
# mit import-linter gegen .importlinter. Gate auch in CI:
# .github/workflows/lint-imports.yml.
#
# Verifizierte Version: import-linter==2.11.* (pinnt grimp 3.14 transitiv).
# Einmalige Installation: pip install "import-linter==2.11.*"
# (in CI automatisch, lokal einmalig erforderlich).
#
# `make test` fährt die repo-weite pytest-Suite (pytest.ini/testpaths) —
# identisch zum CI-Gate .github/workflows/pytest.yml.
# `make ruff` prüft den Style-Lint (gepinnt), identisch zu .github/workflows/ruff.yml.

.PHONY: lint test ruff

lint:
	lint-imports

test:
	python3 -m pytest -q

ruff:
	uvx ruff@0.15.15 check
