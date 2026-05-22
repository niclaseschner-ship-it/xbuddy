"""pytest-Bootstrap der Eltern-Chat-Suite (Refs #27, #52).

Diese Datei trägt KEINE Fixtures — sie legt nur eltern-chat/ auf den
Importpfad, damit die Tests die Module der Komponente (`agent`, `model`,
`main`, …) importieren können. pytest lädt conftest.py automatisch vor den
Test-Modulen; so steht der Pfad bereit, bevor das erste `import agent` läuft.

eltern-chat/ kann wegen des Bindestrichs im Namen kein importierbares Paket
sein und bleibt deshalb paketlos — anders als router/, familie/, plan/ und
zugangsdaten/. Die gemeinsamen Test-Doppelungen liegen in der eindeutig
benannten fakes.py (früher conftest.py; dort fehl am Platz, weil sie keine
Fixtures sind, sondern per `from fakes import` direkt importiert werden).
"""

import os
import sys

# eltern-chat/ (eine Ebene über tests/) auf den Importpfad legen.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
