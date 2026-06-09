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

# Vollständige Verb-Denylist aus Konvention SESS-2 Z. 50-53
# (conventions/privatchat-session.md). Wenn die Konvention erweitert wird,
# muss diese Liste mitsynchronisiert werden.
SESS2_FORBIDDEN_VERBS = (
    "save",
    "load",
    "persist",
    "restore",
    "write_state",
    "read_state",
    "serialize",
    "deserialize",
    "dump",
    "from_dict",
    "to_dict",
    "snapshot",
    "flush",
    "commit",
    "to_json",
    "from_json",
    "pickle",
)


def test_SESS2_basis_klasse_hat_keine_persistenz_api():
    """SESS-2: Die Basis-Klasse bietet KEINE Persistenz-API an.

    SESS-2 besagt: Zustand liegt ausschließlich im Prozess-Speicher. Kein
    halber Zustand auf Disk — kein Wiederaufnahme-Pfad nach Neustart.

    Substanz: PrivateChatSession (und damit alle Subklassen) dürfen keine
    Persistenz-Methoden haben. Würde eine spätere Änderung save/restore/load
    oder einen State-Schreib-Pfad einführen, bricht dieser Test und erzwingt
    eine bewusste Konventions-Anpassung.

    Denylist: SESS-2 Z. 50-53 (17 Verben).
    """
    for verb in SESS2_FORBIDDEN_VERBS:
        assert not hasattr(PrivateChatSession, verb), (
            "SESS-2: Basis-Klasse darf keine %s()-Methode haben — "
            "Zustand liegt nur im Prozess-Speicher" % verb)


def _alle_subklassen(klasse):
    """Rekursive __subclasses__() — auch transitive Erbung.

    Gibt alle direkten und indirekten Subklassen zurück, damit auch eine
    zweistufige Hierachie (Subklasse-von-Subklasse) erfasst wird.
    SESS-2 Z. 58-61: Reflection-Form.
    """
    direkt = klasse.__subclasses__()
    rekursiv = []
    for sub in direkt:
        rekursiv.extend(_alle_subklassen(sub))
    return direkt + rekursiv


def test_SESS2_subklassen_haben_keine_persistenz_api():
    """SESS-2: Subklassen-Disziplin — keine Subklasse darf eine der
    verbotenen Persistenz-Methoden definieren (Konvention SESS-2 Z. 47-56,
    Reflection-Form Z. 58-61).

    Selbst-Probe: Der Test legt eine Test-only-Subklasse an, die KEIN verbotenes
    Verb hat, und prüft dass die Reflection sie erfasst — damit läuft die Schleife
    mindestens einmal und ist nicht stillschweigend trivial (auch wenn heute keine
    echte Subklasse importiert ist).
    """
    # Selbst-Probe: saubere Subklasse anlegen, damit Reflection definitiv läuft.
    class _SaubereTestSubklasse(PrivateChatSession):
        """Test-only: hat kein verbotenes Verb — darf in der Schleife nie auslösen."""
        THREAD_NAME_PREFIX = "test-sauber"
        LOG_PREFIX = "TestSauber"

    try:
        subklassen = _alle_subklassen(PrivateChatSession)
        assert any(sub is _SaubereTestSubklasse for sub in subklassen), (
            "Selbst-Probe: _SaubereTestSubklasse muss in __subclasses__()-Reflection "
            "auftauchen — Reflection funktioniert nicht korrekt")

        for sub in subklassen:
            for verb in SESS2_FORBIDDEN_VERBS:
                assert not hasattr(sub, verb), (
                    "SESS-2: Subklasse %s darf keine %s()-Methode haben — "
                    "Zustand liegt nur im Prozess-Speicher (SESS-2 Z. 47-56)"
                    % (sub.__name__, verb))
    finally:
        # Test-only-Subklasse aus der Klassenhierarchie auflösen, damit sie
        # keine Folge-Tests beeinflusst (CPython: __subclasses__() hält
        # schwache Referenzen — Garbage-Collection reicht).
        del _SaubereTestSubklasse


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


def test_SESS2_keine_disk_datei_waehrend_session_lebensspanne(tmp_path, monkeypatch):
    """SESS-2: Während einer kompletten Session (start → deliver → set_result)
    entsteht keine Disk-Datei im Arbeitsverzeichnis.

    Erweitert den Konstruktions-Test (oben) auf die ganze Lebensspanne —
    SESS-2 trägt für die gesamte Session-Lifetime, nicht nur für die
    Instanziierung (conventions/privatchat-session.md SESS-2).
    """
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())

    session = PrivateChatSession(chat_id=4711, timeout_seconds=2)

    received = []
    finished_signal = threading.Event()

    def _worker():
        # Simuliert einen typischen Worker: eine Nachricht abholen,
        # Ergebnis setzen.
        msg = session.next_message(timeout=2.0)
        if msg is not None:
            received.append(msg)
        session.set_result({"ok": True})
        finished_signal.set()

    session.start(_worker, ())
    session.deliver("hallo")
    finished_signal.wait(timeout=3.0)
    session._finished.wait(timeout=2.0)

    after = set(tmp_path.iterdir())
    neue_dateien = after - before
    assert neue_dateien == set(), (
        "SESS-2: Während der Session-Lebensspanne (start→deliver→set_result) "
        "darf keine Disk-Datei entstehen. Neu: %s" % neue_dateien)


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
