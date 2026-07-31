"""pytest-Bootstrap der Eltern-Chat-Suite (Refs #27, #52, #84).

Diese Datei legt eltern-chat/ und die Repo-Wurzel auf den Importpfad, damit die
Tests die Module der Komponente (`agent`, `model`, `main`, …) sowie das
geteilte `tools`-Paket importieren können. pytest lädt conftest.py automatisch
vor den Test-Modulen; so steht der Pfad bereit, bevor das erste `import agent`
läuft.

eltern-chat/ kann wegen des Bindestrichs im Namen kein importierbares Paket
sein und bleibt deshalb paketlos — anders als router/, familie/, plan/ und
zugangsdaten/. Die gemeinsamen Test-Doppelungen liegen in der eindeutig
benannten fakes.py (früher conftest.py; dort fehl am Platz, weil sie keine
Fixtures sind, sondern per `from fakes import` direkt importiert werden).

Seit #84 (OPEN-ZD-B): Der Onboarding-Speicher liest und schreibt über den
zentralen Zugangsdaten-Speicher (`tools.zugangsdaten`). Dessen Default-Pfad
liegt neben dem Code (`tools/zugangsdaten/zugangsdaten.json`). Damit kein Test
diese reale Instanz-Datei berührt — weder direkt (test_onboarding_store) noch
indirekt über config.resolve (test_familie_anlegen_task, test_geraet_anlegen_task,
test_ca_verteilung …) —, lenkt die autouse-Fixture unten den Speicher pro Test
auf einen frischen tmp-Pfad. EINE Stelle isoliert so die ganze Suite.
"""

import os
import sys

import pytest

# eltern-chat/ (eine Ebene über tests/) auf den Importpfad legen.
_ELTERN_CHAT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ELTERN_CHAT)

# Repo-Wurzel auf den Importpfad — der zentrale Zugangsdaten-Speicher lebt unter
# tools/ und wird seit #84 vom Onboarding-Speicher importiert.
sys.path.insert(0, os.path.dirname(_ELTERN_CHAT))

from tools.instanzen import ENV_CONFIG_FILE as _INSTANZEN_ENV  # noqa: E402
from tools.zugangsdaten import ENV_STORE_FILE  # noqa: E402

# INST-1 (#1656): tasks.HOERSPIEL_INSTANZEN liest seit Welle 2b die Instanz-Liste
# über tools.instanzen. agent.py und skills/hoerspiel_folge_erzeugen_task.py leiten
# ihre Namens-/enum-Listen beim Modul-IMPORT aus dieser Liste ab. Damit die Suite
# gegen die realen Slugs (paula/neko/niclas, PORT-2) prüft — statt gegen den
# INST-6-kind1/kind2-Default —, muss INSTANZEN_CONFIG_FILE VOR dem ersten
# `import agent`/`import tasks` gesetzt sein. conftest.py lädt pytest vor allen
# Test-Modulen, deshalb hier auf Modul-Ebene (nicht als Fixture — eine Fixture
# liefe zu spät, die Konstanten sind dann schon eingefroren). Die Datei liegt
# neben conftest.py (getrackt) und trägt dieselben Test-Slugs wie
# seiten/tests/test_hsp_instanzen.py.
os.environ.setdefault(
    _INSTANZEN_ENV,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "instanzen.test.json"),
)


@pytest.fixture(autouse=True)
def _isolierter_zugangsdaten_speicher(tmp_path, monkeypatch):
    """Lenkt den zentralen Zugangsdaten-Speicher (#84/ZD-8) pro Test auf einen
    frischen tmp-Pfad, sodass kein Test die reale Instanz-Datei beschreibt."""
    monkeypatch.setenv(
        ENV_STORE_FILE, str(tmp_path / "zugangsdaten-test.json"))
