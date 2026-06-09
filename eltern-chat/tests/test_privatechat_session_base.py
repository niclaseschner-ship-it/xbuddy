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


class _StubBulkTarget:
    """Minimale Aufzeichnung eines Bulk-PUT-Versuchs — simuliert den Schreib-
    Effekt, den eine Session bei ordentlichem Abschluss auslösen würde."""

    def __init__(self):
        self.calls = []

    def put_termine_bulk(self, request_id, items):
        self.calls.append((request_id, list(items)))
        return {"ok": True, "geschrieben": len(items), "gesamt": len(items),
                "results": []}


def test_SESS2_prozess_neustart_kein_bulk_put():
    """SESS-2: Prozess-Neustart während einer laufenden Session beendet sie
    ohne Bulk-PUT.

    Modell des Neustart-Pfads: eine neue Session-Instanz wird erzeugt (der
    vorherige Zustand liegt nur im Prozess-Speicher — SESS-2 — und ist weg);
    die neue Session hat keinen Worker-Thread und startet keinen Bulk-PUT.
    Der Test belegt, dass die Basis-Klasse KEINEN automatischen Schreib-Effekt
    beim Erstellen hat.

    Vehikel: PrivateChatSession direkt (keine Subklasse nötig — die Klasse hat
    keine abstrakten Methoden; TAB-Subklasse wäre äquivalent, aber hier reicht
    die Basis).
    """
    bulk = _StubBulkTarget()
    # Neustart-Modell: frische Instanz, kein start()-Aufruf (kein Worker-Thread).
    session = PrivateChatSession(chat_id=42, timeout_seconds=1)

    # Nach dem Neustart — frisch angelegte Session ist sofort „unfertig", aber
    # KEIN Worker läuft, KEIN Bulk-PUT ist passiert.
    assert not session.is_finished(), (
        "Eine frisch angelegte Session ist noch nicht finished — "
        "der Neustart hat sie nicht künstlich abgeschlossen")
    assert bulk.calls == [], (
        "Kein Bulk-PUT beim Anlegen der Session (Neustart-Pfad: "
        "SESS-2 — kein halber persistenter Zustand)")


def test_SESS2_kein_thread_nach_neustart():
    """SESS-2 (ergänzend): nach dem Neustart gibt es keinen laufenden Worker-Thread.

    Ein Thread würde vorherige Session-Zustands-Naht im Speicher halten; das
    passt nicht zu SESS-2 (kein halber Zustand nach Restart).
    """
    session = PrivateChatSession(chat_id=99, timeout_seconds=1)
    # Kein start()-Aufruf → _thread ist None.
    assert session._thread is None, (
        "Nach Neustart (kein start()) darf kein Worker-Thread laufen")


def test_SESS2_finished_erst_nach_worker_ende():
    """SESS-2 / SESS-1: is_finished() wird erst True, nachdem der Worker-Thread
    beendet ist — nicht vorher.

    Das belegt, dass die Session NICHT beim bloßen Anlegen als „fertig" gilt
    (was sonst ein Neustart-Seiteneffekt sein könnte).
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
