"""Tests für tools/logsetup.py (#166, LOG-1/LOG-2).

Die Tests prüfen die Setup-Form, nicht eine konkrete Komponente: Format
ist LOG-1, Level-Mapping per String, Idempotenz, Fallback bei
ungültigem Level.
"""

import logging
import os
import sys

import pytest

# Repo-Wurzel auf den Importpfad — wir importieren `tools` als
# implizites Namespace-Paket (PEP 420), analog test_configloader.py.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import logsetup  # noqa: E402


@pytest.fixture
def clean_root_logger():
    """Setzt Root-Logger vor und nach jedem Test zurück.

    `logging.basicConfig` ist no-op, wenn der Root-Logger schon Handler
    hat — für saubere Tests müssen wir vor jedem Test die Handler
    entfernen.
    """
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    root.handlers = []
    yield root
    root.handlers = saved_handlers
    root.level = saved_level


# ============================================================
#  LOG-1 — Format
# ============================================================

def test_setup_uses_log1_format(clean_root_logger):
    """`setup` setzt das LOG-1-Format auf dem Root-Handler."""
    logsetup.setup("INFO")

    root = clean_root_logger
    assert root.handlers, "basicConfig hätte einen Handler anlegen müssen"
    fmt = root.handlers[0].formatter
    assert fmt is not None
    # Die Formatter-Struktur in Py >= 3.2 hält das Format-Pattern als
    # `_fmt`/`_style._fmt` — wir prüfen die offizielle Konstante des
    # Moduls, damit wir nicht an Python-Interna kleben.
    assert logsetup.LOG_FORMAT == "%(asctime)s %(levelname)s %(message)s"
    assert fmt._style._fmt == logsetup.LOG_FORMAT


# ============================================================
#  LOG-2 — Level-Mapping
# ============================================================

def test_setup_default_level_is_info(clean_root_logger):
    """LOG-2: Default-Level ist INFO."""
    logsetup.setup()
    assert clean_root_logger.level == logging.INFO


def test_setup_info_level(clean_root_logger):
    """`setup("INFO")` setzt den Root-Logger auf INFO."""
    logsetup.setup("INFO")
    assert clean_root_logger.level == logging.INFO


def test_setup_debug_level(clean_root_logger):
    """`setup("DEBUG")` setzt den Root-Logger auf DEBUG (LOG-2 Override)."""
    logsetup.setup("DEBUG")
    assert clean_root_logger.level == logging.DEBUG


def test_setup_warning_level(clean_root_logger):
    """Auch `WARNING` ist ein gültiger Level (LOG-2)."""
    logsetup.setup("WARNING")
    assert clean_root_logger.level == logging.WARNING


def test_setup_level_is_case_insensitive(clean_root_logger):
    """`setup("debug")` setzt DEBUG (case-insensitive Eingabe)."""
    logsetup.setup("debug")
    assert clean_root_logger.level == logging.DEBUG


# ============================================================
#  Ungültiger Level → Fallback auf INFO + Warning
# ============================================================

def test_setup_invalid_level_falls_back_to_info(clean_root_logger, caplog):
    """Unbekannter Level-String → Warning + Fallback auf INFO.

    Silent ignorieren würde Bedienfehler verstecken, aber Hochreißen wäre
    für ein Diagnose-Werkzeug zu hart — die Komponente startet, Nic sieht
    die Warnung im Log und fixt die Config.
    """
    with caplog.at_level("WARNING"):
        logsetup.setup("PLAPPER")
        # Innerhalb des with-Blocks prüfen: `caplog.at_level` setzt den
        # Root-Level nach Verlassen des Blocks zurück.
        assert clean_root_logger.level == logging.INFO
    assert any("PLAPPER" in r.message for r in caplog.records), \
        "Warn-Log mit dem unbekannten Level erwartet"


def test_setup_non_string_level_falls_back_to_info(clean_root_logger, caplog):
    """Non-String-Eingabe (z. B. versehentlich int) → Warning + Fallback."""
    with caplog.at_level("WARNING"):
        logsetup.setup(42)
        assert clean_root_logger.level == logging.INFO
    assert any("kein String" in r.message for r in caplog.records)


# ============================================================
#  Idempotenz
# ============================================================

def test_setup_is_idempotent(clean_root_logger):
    """Mehrfachaufruf legt keine zusätzlichen Handler an.

    `logging.basicConfig` ist no-op, wenn der Root-Logger schon Handler
    hat — `logsetup` erbt dieses Verhalten.
    """
    logsetup.setup("INFO")
    handler_count_after_first = len(clean_root_logger.handlers)

    logsetup.setup("INFO")
    logsetup.setup("DEBUG")

    assert len(clean_root_logger.handlers) == handler_count_after_first
