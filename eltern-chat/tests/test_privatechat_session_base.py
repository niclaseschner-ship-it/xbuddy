"""SESS-2-Basistest: PrivateChatSession-Klasse deckt das gesamte konventionsweite
Test-Pflicht-Mandat ab (conventions/privatchat-session.md SESS-2).

> "SESS-2 (kein halber persistenter Zustand nach Restart) wird durch einen
>  automatisierten Test gegen die PrivateChatSession-Basis abgedeckt — der Test
>  gilt für alle Sorten, weil sie dieselbe Basis erben."

Implementierungs-Naht: dieses File (Spec-PR #530, 2026-06-09).

Konsumenten-Specs (TAB-13/TAB-3, TES-11/TES-3, …) verweisen auf diese Klausel
und dürfen den Test nicht sortenweise duplizieren.
"""

import threading

from private_chat_session import PrivateChatSession


def test_SESS2_basis_klasse_hat_keine_persistenz_api():
    """SESS-2: Die Basis-Klasse bietet KEINE Persistenz-API an.

    SESS-2 besagt: Zustand liegt ausschließlich im Prozess-Speicher. Kein
    halber Zustand auf Disk — kein Wiederaufnahme-Pfad nach Neustart.

    Substanz: PrivateChatSession (und damit alle Subklassen) dürfen keine
    Persistenz-Methoden haben. Würde eine spätere Änderung save/restore/load
    oder einen State-Schreib-Pfad einführen, bricht dieser Test und erzwingt
    eine bewusste Konventions-Anpassung.
    """
    # Kein save/restore/persist/load/write_state-Pfad erlaubt — Spec SESS-2.
    assert not hasattr(PrivateChatSession, "save"), (
        "SESS-2: Basis-Klasse darf keine save()-Methode haben — "
        "Zustand liegt nur im Prozess-Speicher")
    assert not hasattr(PrivateChatSession, "restore"), (
        "SESS-2: Basis-Klasse darf keine restore()-Methode haben — "
        "kein Wiederaufnahme-Pfad nach Neustart")
    assert not hasattr(PrivateChatSession, "persist"), (
        "SESS-2: Basis-Klasse darf keine persist()-Methode haben")
    assert not hasattr(PrivateChatSession, "load"), (
        "SESS-2: Basis-Klasse darf keine load()-Methode haben")
    assert not hasattr(PrivateChatSession, "write_state"), (
        "SESS-2: Basis-Klasse darf keine write_state()-Methode haben")
    assert not hasattr(PrivateChatSession, "read_state"), (
        "SESS-2: Basis-Klasse darf keine read_state()-Methode haben")


def test_SESS2_instanz_schreibt_keine_disk_datei_bei_konstruktion(tmp_path, monkeypatch):
    """SESS-2: Konstruktion einer Session erzeugt keine State-Datei auf Disk.

    Disk-IO zur Konstruktionszeit wäre ein halber persistenter Zustand —
    genau das verbietet SESS-2. Der Test überwacht das Arbeitsverzeichnis:
    nach PrivateChatSession(chat_id=42) darf keine neue Datei entstanden sein.
    """
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())

    PrivateChatSession(chat_id=42, timeout_seconds=1)

    after = set(tmp_path.iterdir())
    neue_dateien = after - before
    assert neue_dateien == set(), (
        "SESS-2: Konstruktion darf keine Dateien anlegen — "
        "Zustand nur im Speicher. Neu entstandene Dateien: %s" % neue_dateien)


def test_basis_klasse_thread_initial_none():
    """Basis-Klassen-Invariante: _thread ist None direkt nach Konstruktion.

    Ohne start()-Aufruf läuft kein Worker-Thread. Das ist eine strukturelle
    Invariante der Klasse (kein automatischer Hintergrund-Thread beim Anlegen).
    """
    session = PrivateChatSession(chat_id=99, timeout_seconds=1)
    assert session._thread is None, (
        "Nach Konstruktion (kein start()) darf kein Worker-Thread laufen")


def test_basis_klasse_finished_erst_nach_worker_ende():
    """Basis-Klassen-Invariante (SESS-1): is_finished() wird erst True,
    nachdem der Worker-Thread beendet ist — nicht vorher.

    Das belegt, dass die Session NICHT beim bloßen Anlegen als „fertig" gilt.
    """
    session = PrivateChatSession(chat_id=7, timeout_seconds=1)

    started = threading.Event()
    done = threading.Event()

    def _worker():
        started.set()
        done.wait(timeout=2.0)

    session.start(_worker, ())
    started.wait(timeout=1.0)

    # Worker läuft — Session ist noch nicht finished.
    assert not session.is_finished(), (
        "Session darf nicht finished sein, solange der Worker läuft")

    # Worker freigeben → Session wird finished.
    done.set()
    session._finished.wait(timeout=2.0)
    assert session.is_finished(), (
        "Session muss finished sein, nachdem der Worker regulär beendet hat")
