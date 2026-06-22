"""Test-Fixtures für `tools.llm`-Suite (T1082, LLMP-S11).

Die Suite läuft **ohne Netz** und ohne echtes anthropic-SDK — Vendor-Klassen
werden als Fakes injiziert (analog `kibuddy/tests/conftest.py`-Pattern mit
`FakeLLM`).
"""

import os
import sys

# Repo-Root in sys.path heben (analog `kibuddy/tests/conftest.py`), damit
# `from tools.llm import …` ohne Editable-Install funktioniert.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
