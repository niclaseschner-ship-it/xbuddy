"""pytest-Bootstrap für tests/skills/ — Importpfad-Setup.

Legt eltern-chat/ auf den Importpfad, damit die Skill-Tests alle
eltern-chat-Module importieren können.

Die autouse-Fixture für den isolierten Zugangsdaten-Speicher (#84/ZD-8)
ist im übergeordneten tests/conftest.py definiert und wirkt automatisch
auch für Unterverzeichnisse.
"""

import os
import sys

# eltern-chat/ auf den Importpfad legen (zwei Ebenen über tests/skills/).
_ELTERN_CHAT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _ELTERN_CHAT not in sys.path:
    sys.path.insert(0, _ELTERN_CHAT)

# Repo-Wurzel für tools/ etc.
_REPO_ROOT = os.path.dirname(_ELTERN_CHAT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
