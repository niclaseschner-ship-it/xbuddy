# XBuddy — Entwickler-Targets.
# `make lint` prüft die Modul-Grenzen (conventions/module-boundaries.md, MOD-*)
# mit import-linter gegen .importlinter. Gate auch in CI:
# .github/workflows/lint-imports.yml.

.PHONY: lint

lint:
	lint-imports
