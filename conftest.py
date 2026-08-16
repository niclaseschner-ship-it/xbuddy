"""Repo-weite pytest-Fixtures.

Zentraler Telemetrie-Guard (#1821), ZWEI Schichten — Gürtel UND Hosenträger:

1. Gürtel — ENV-Umbiegen: JEDER Testlauf bekommt `XBUDDY_DATA_DIR` auf
   `tmp_path` umgebogen, NIE auf die Live-Messdatei
   `/home/buddy/xbuddy-data/llm/provider_calls.jsonl` — unabhängig davon, ob
   eine einzelne Testfunktion das selbst anfordert.

   Vorher: `tools/llm/tests/test_vendor_litellm.py` trug eine lokale
   `jsonl_path`-Fixture, die `XBUDDY_DATA_DIR` umbog — aber nur die
   Testfunktionen, die sie als Parameter anforderten, bekamen sie. Jede
   andere Testfunktion, die auf einem echten `tools.llm`-Aufrufpfad landete
   (z. B. über `LitellmVendor(...).singleshot_structured(...)` ohne die
   Fixture), fiel in `tools/llm/telemetry.py:resolve_jsonl_path()` auf den
   Default-Pfad zurück und schrieb echte Zeilen in die Live-Datei — bei
   jedem CI-Lauf auf dem selbst gehosteten Läufer.

2. Hosenträger — Nachprüfung: das Umbiegen deckt nur den ENV-Weg ab. Ein
   Test, der die Live-Datei über einen ANDEREN Weg erreicht (expliziter
   Absolutpfad, `write_call(..., env={"XBUDDY_DATA_DIR": "/home/buddy/
   xbuddy-data"})` am gerade gesetzten ENV vorbei, oder ein künftiger
   Schreiber mit eigener Pfad-Auflösung), würde vom Umbiegen allein NICHT
   erwischt. Darum merkt sich dieselbe Fixture vor dem Test `stat()` der
   Live-Datei (Größe + mtime, KEIN Read — billig) und vergleicht danach:
   weicht die Signatur ab, schlägt DIESER Test fehl, mit dem Testnamen in
   der Meldung, statt still weiterzulaufen.

Die Lösung ist `autouse=True` auf Repo-Wurzelebene: sie gilt für JEDE
Testfunktion in JEDER unter `testpaths` (pytest.ini) gelisteten Suite, ganz
ohne Parameter-Anforderung. Lokale Fixtures wie `jsonl_path` in
`tools/llm/tests/test_vendor_litellm.py` biegen danach denselben `tmp_path`
noch einmal um (redundant, aber unschädlich) und bleiben, weil sie den
konkreten Pfad für Test-Assertions zurückgeben — sie sind NICHT der
Hosenträger, das ist die Nachprüfung unten.
"""

import os

import pytest


def _live_jsonl_path() -> str:
    """Live-Telemetrie-Pfad OHNE ENV-Override.

    Spiegelt `tools.llm.telemetry.resolve_jsonl_path()` bei explizit leerem
    `env` (identischer Aufruf wie `tools/llm/tests/test_telemetry.py::
    test_resolve_jsonl_path_default`) — liest also dieselbe SSoT
    (`DEFAULT_DATA_DIR`), OHNE `tools/llm/telemetry.py` anzufassen. Lazy
    Import: läuft erst beim ersten Fixture-Aufruf, nicht beim Einsammeln
    dieser conftest.py.
    """
    from tools.llm.telemetry import resolve_jsonl_path

    return resolve_jsonl_path(env={})


def _stat_signature(path: str):
    """(Größe, mtime_ns) der Datei oder `None`, wenn sie (noch) fehlt.

    Reines `stat()` — bewusst KEIN Datei-Read: die Live-Datei hat
    vierstellige KB-Größe, ein Read pro Testfunktion wäre über die volle
    Suite spürbar, ein `stat()`-Syscall ist es nicht.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


@pytest.fixture(autouse=True)
def _xbuddy_data_dir_isolieren(tmp_path, monkeypatch, request):
    """Biegt `XBUDDY_DATA_DIR` für JEDEN Test auf `tmp_path` um UND prüft
    danach, dass die Live-Messdatei unangetastet blieb (#1821, zwei
    Schichten — siehe Modul-Docstring).

    Dieser Guard braucht keine Testfunktion, die ihn anfordert — er greift
    immer, auch bei Tests, die nichts von `tools.llm` wissen (das Umbiegen
    einer ungenutzten ENV ist für sie folgenlos, die `stat()`-Nachprüfung
    ebenso billig).
    """
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))

    live_path = _live_jsonl_path()
    vorher = _stat_signature(live_path)

    yield

    nachher = _stat_signature(live_path)
    if vorher != nachher:
        pytest.fail(
            "Live-Telemetrie-Datei %s hat sich waehrend %s veraendert "
            "(vorher=%r, nachher=%r) - dieser Test hat trotz "
            "XBUDDY_DATA_DIR-Umbiegen in die Live-Messdatei geschrieben "
            "(z. B. Absolutpfad oder eigenes env=... an write_call vorbei "
            "am Fixture-ENV)." % (live_path, request.node.nodeid, vorher, nachher),
            pytrace=False,
        )
