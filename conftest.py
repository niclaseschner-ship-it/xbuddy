"""Repo-weite pytest-Fixtures.

Zentraler Telemetrie-Guard (#1821): JEDER Testlauf schreibt seine
`tools.llm`-Telemetrie in einen temporären Pfad, NIE in die Live-Messdatei
`/home/buddy/xbuddy-data/llm/provider_calls.jsonl` — unabhängig davon, ob
eine einzelne Testfunktion das selbst anfordert.

Vorher: `tools/llm/tests/test_vendor_litellm.py` trug eine lokale
`jsonl_path`-Fixture, die `XBUDDY_DATA_DIR` umbog — aber nur die
Testfunktionen, die sie als Parameter anforderten, bekamen sie. Jede andere
Testfunktion, die auf einem echten `tools.llm`-Aufrufpfad landete (z. B. über
`LitellmVendor(...).singleshot_structured(...)` ohne die Fixture), fiel in
`tools/llm/telemetry.py:resolve_jsonl_path()` auf den Default-Pfad zurück und
schrieb echte Zeilen in die Live-Datei — bei jedem CI-Lauf auf dem selbst
gehosteten Läufer.

Die Lösung ist `autouse=True` auf Repo-Wurzelebene: sie gilt für JEDE
Testfunktion in JEDER unter `testpaths` (pytest.ini) gelisteten Suite, ganz
ohne Parameter-Anforderung. Lokale Fixtures wie `jsonl_path` in
`tools/llm/tests/test_vendor_litellm.py` biegen danach denselben `tmp_path`
noch einmal um (redundant, aber unschädlich) und bleiben, weil sie den
konkreten Pfad für Test-Assertions zurückgeben.
"""

import pytest


@pytest.fixture(autouse=True)
def _xbuddy_data_dir_isolieren(tmp_path, monkeypatch):
    """Biegt `XBUDDY_DATA_DIR` für JEDEN Test auf `tmp_path` um (#1821).

    Guertel zum Hosentraeger der lokalen `jsonl_path`-Fixture in
    `tools/llm/tests/test_vendor_litellm.py`: dieser Guard braucht keine
    Testfunktion, die ihn anfordert — er greift immer, auch bei Tests, die
    nichts von `tools.llm` wissen (das Umbiegen einer ungenutzten ENV ist
    für sie folgenlos).
    """
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
