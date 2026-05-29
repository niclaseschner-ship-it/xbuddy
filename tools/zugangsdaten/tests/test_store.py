"""Tests für das atomare Schreiben in store.py — ZD-3 + DCOMP-4 (Ticket #245).

Ergänzt die Suite in tests/tools/test_zugangsdaten.py um Tests, die das
neue atomare Schreib-Muster (Temp + os.replace) direkt prüfen.

Lauf: python3 -m pytest tools/zugangsdaten/tests/ -v
"""

import os
import stat
import sys
import threading
import time

# Repo-Wurzel auf den Importpfad.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.zugangsdaten import FILE_MODE, Zugangsdaten, is_owner_only  # noqa: E402
from tools.zugangsdaten.store import Zugangsdaten as ZDStore  # noqa: E402


# ============================================================
#  AC1 + AC5 — Atomar schreiben, 0600 bleiben erhalten
# ============================================================

def test_ZD_3_atomic_no_trunc_on_target_during_write(tmp_path):
    """Kein O_TRUNC direkt auf der Zieldatei: nach store.set() existiert
    genau die finale Datei mit vollständigem Inhalt — kein Window, in dem
    die Datei leer oder halb geschrieben wäre.

    Wir prüfen, dass nach set() kein verwaistes Temp im Zielverzeichnis
    zurückbleibt und die Zieldatei den korrekten Inhalt trägt.
    """
    path = tmp_path / "zd.json"
    speicher = Zugangsdaten(path)
    speicher.set("ki-anbieter-key", "geheim")

    # Keine verwaisten Temp-Dateien.
    temps = [f for f in os.listdir(tmp_path) if ".tmp" in f or f.startswith(".zugangsdaten.")]
    assert temps == [], "verwaiste Temp-Datei nach set(): %r" % temps

    # Die Zieldatei existiert und trägt den gesetzten Wert.
    assert path.exists()
    assert speicher.get("ki-anbieter-key") == "geheim"


def test_ZD_3_file_mode_0600_preserved_after_atomic_write(tmp_path):
    """0600-Rechte bleiben nach dem atomaren os.replace erhalten (AC5)."""
    path = tmp_path / "zd.json"
    speicher = Zugangsdaten(path)
    speicher.set("google-oauth-token", "ya29.x")
    mode = stat.S_IMODE(os.stat(str(path)).st_mode)
    assert mode == FILE_MODE, "Dateirechte nach atomarem Schreiben: %04o (erwartet 0600)" % mode
    assert is_owner_only(str(path))


def test_ZD_3_existing_file_mode_tightened_after_atomic_overwrite(tmp_path):
    """Besteht die Zieldatei mit offeneren Rechten, werden sie nach dem
    atomaren Rename auf 0600 gezogen (defense-in-depth, analog GER-6)."""
    path = tmp_path / "zd.json"
    # Erst mit normalem set() anlegen, dann Rechte öffnen.
    speicher = Zugangsdaten(path)
    speicher.set("k", "v1")
    os.chmod(str(path), 0o644)
    assert stat.S_IMODE(os.stat(str(path)).st_mode) == 0o644

    # Erneutes set() — atomares Rename + os.chmod erzwingt 0600.
    speicher.set("k", "v2")
    assert stat.S_IMODE(os.stat(str(path)).st_mode) == FILE_MODE


def test_ZD_3_atomic_write_race_free_creation_under_permissive_umask(tmp_path, monkeypatch):
    """Die Temp-Datei entsteht race-frei mit 0600: self.path sieht zu keinem
    Zeitpunkt offenere Rechte, auch unter umask 0o000.

    Wir patchen os.chmod zu einer No-Op — nur die Anlage-Rechte zählen.
    """
    path = tmp_path / "zd.json"
    # os.chmod deaktivieren: zeigt, dass die Rechte schon bei Anlage stimmen.
    original_chmod = os.chmod

    def noop_chmod(*args, **kwargs):
        pass

    monkeypatch.setattr(os, "chmod", noop_chmod)
    old_umask = os.umask(0o000)
    try:
        Zugangsdaten(path).set("ki-anbieter-key", "geheim")
        assert stat.S_IMODE(os.stat(str(path)).st_mode) == FILE_MODE
    finally:
        os.umask(old_umask)
        monkeypatch.setattr(os, "chmod", original_chmod)


# ============================================================
#  AC2 — Paralleler Schreib-Test (DCOMP-4)
# ============================================================

def test_ZD_3_DCOMP4_parallel_writes_no_corrupt_read(tmp_path):
    """Parallele set()-Aufrufe hinterlassen keine korrumpierte Datei.

    Zwei Threads schreiben gleichzeitig wiederholt in denselben Speicher.
    Ein gleichzeitig lesender Thread darf niemals eine ungültige JSON-Datei
    sehen — der atomare Rename stellt sicher, dass ein Leser entweder den
    alten oder den neuen Stand sieht, nie einen halbgeschriebenen Zustand.
    """
    import json

    path = tmp_path / "parallel.json"
    speicher = Zugangsdaten(path)
    speicher.set("base", "start")

    errors = []
    stop = threading.Event()

    def writer(name, value):
        for _ in range(30):
            try:
                speicher.set(name, value)
            except Exception as e:
                errors.append("writer-%s: %s" % (name, e))
            time.sleep(0)  # yield

    def reader():
        while not stop.is_set():
            try:
                raw = path.read_text(encoding="utf-8")
                parsed = json.loads(raw)
                assert isinstance(parsed, dict), "ungültiger Speicher-Inhalt: %r" % parsed
            except FileNotFoundError:
                pass  # kurz weg während os.replace — OK
            except json.JSONDecodeError as e:
                errors.append("reader: %s — raw: %r" % (e, raw[:80]))
            time.sleep(0)

    t1 = threading.Thread(target=writer, args=("a", "wert-a"), daemon=True)
    t2 = threading.Thread(target=writer, args=("b", "wert-b"), daemon=True)
    t_reader = threading.Thread(target=reader, daemon=True)

    t_reader.start()
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    stop.set()
    t_reader.join(timeout=2)

    assert not errors, "Fehler im Parallel-Lauf:\n" + "\n".join(errors)
    # Abschließender Stand ist gültiges JSON.
    final = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(final, dict)
