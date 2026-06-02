# XBuddy — Entwickler-Targets.
# `make lint` prüft die Modul-Grenzen (conventions/module-boundaries.md, MOD-*)
# mit import-linter gegen .importlinter. Gate auch in CI:
# .github/workflows/lint-imports.yml.
#
# Verifizierte Version: import-linter==2.11.* (pinnt grimp 3.14 transitiv).
# Einmalige Installation: pip install "import-linter==2.11.*"
# (in CI automatisch, lokal einmalig erforderlich).

.PHONY: lint

lint:
	lint-imports
