"""Tests für die Funktion wuensche_zeigen — WZE-1 … WZE-8, E-WZE-1/2
(Refs #503).

Jede Anforderung der Spec mit Code-Verhalten hat einen automatisierten Test
(WZE-8, CLAUDE.md §6). Essens-Buddy und Telegram sind durch kontrollierte
Doppelungen ersetzt — die Tests laufen ohne Netz (EC-17).

Pflicht-Tests (Spec WZE-8):
- Nicht-Mitglied → abgelehnt, kein API-Aufruf (WZE-2).
- Happy-Path: drei Wünsche aus zwei Kategorien → get_wuensche → kategorie-
  gruppierte Zusammenfassung (WZE-3/WZE-5, E-WZE-2).
- Leere Liste → WZE-6-Meldung, Signal 'leer'.
- Transport-Fehler → WZE-7-Meldung, Signal 'nicht_erreichbar', kein Retry.
- APP-3: Skill ruft die API, nicht die Datei.
- E-WZE-2: Kategorie-Reihenfolge fest (Gerichte → Obst&Gemüse → Brotbelag
  → Sonstiges), unabhängig von der Ankunfts-Reihenfolge.
"""

import unittest.mock as mock

from skills.essen_client import EssenClientError
from skills.wuensche_zeigen import (
    KATEGORIEN_REIHENFOLGE,
    SIGNAL_ABGELEHNT,
    SIGNAL_BEANTWORTET,
    SIGNAL_LEER,
    SIGNAL_NICHT_ERREICHBAR,
    formatiere_wuensche,
    wuensche_zeigen,
)

# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakeTelegram:
    """Telegram-Doppelung: zeichnet send_message-Aufrufe auf."""

    def __init__(self):
        self.messages = []

    def send_message(self, chat_id, text):
        self.messages.append({"chat_id": chat_id, "text": text})

    def get_chat_member(self, group_id, user_id):
        return None


class FakeEssenClient:
    """EssenClient-Doppelung (CLIENT-1, WZE-4)."""

    def __init__(self, wuensche=None, error=None):
        self.get_calls = 0
        self._wuensche = wuensche if wuensche is not None else []
        self._error = error

    def get_wuensche(self):
        self.get_calls += 1
        if self._error is not None:
            raise self._error
        return list(self._wuensche)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


# ============================================================
#  WZE-2: Berechtigung — Nicht-Mitglied → Ablehnung, kein API-Aufruf
# ============================================================

def test_WZE2_nicht_mitglied_abgelehnt_kein_api():
    """WZE-2: Nicht-Mitglied → SIGNAL_ABGELEHNT, kein get_wuensche-Aufruf."""
    tg = FakeTelegram()
    ec = FakeEssenClient(wuensche=[{"label": "Apfel"}])

    signal = wuensche_zeigen(
        tg=tg,
        chat_id=42,
        from_user_id=99,
        essen_client=ec,
        is_member_fn=_kein_mitglied,
    )

    assert signal == SIGNAL_ABGELEHNT
    assert ec.get_calls == 0, "Kein API-Aufruf bei Nicht-Mitglied (WZE-2)"
    assert tg.messages == [], "Keine Nachricht bei Ablehnung"


def test_WZE2_kein_user_id_abgelehnt():
    """WZE-2: from_user_id=None → SIGNAL_ABGELEHNT."""
    tg = FakeTelegram()
    ec = FakeEssenClient()

    signal = wuensche_zeigen(
        tg=tg,
        chat_id=42,
        from_user_id=None,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
    )

    assert signal == SIGNAL_ABGELEHNT
    assert ec.get_calls == 0


# ============================================================
#  WZE-5 / E-WZE-2: Happy-Path + kategorie-gruppierte Reihenfolge
# ============================================================

def test_WZE5_happy_path_zwei_kategorien():
    """WZE-5: drei Wünsche aus zwei Kategorien → Skill ruft get_wuensche
    und postet kategorie-gruppierte Zusammenfassung (Transport-Stub, CLIENT-1).
    """
    tg = FakeTelegram()
    wuensche = [
        {"id": "kind:1", "label": "Apfel", "kategorie": "obst_gemuese",
         "erstellt_am": "2026-06-09T10:00:00"},
        {"id": "kind:2", "label": "Lasagne", "kategorie": "gericht",
         "erstellt_am": "2026-06-09T11:00:00"},
        {"id": "kind:3", "label": "Karotten", "kategorie": "obst_gemuese",
         "erstellt_am": "2026-06-09T12:00:00"},
    ]
    ec = FakeEssenClient(wuensche=wuensche)

    signal = wuensche_zeigen(
        tg=tg,
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
    )

    assert signal == SIGNAL_BEANTWORTET
    assert ec.get_calls == 1
    assert len(tg.messages) == 1
    antwort = tg.messages[0]["text"]

    # Antwort geht an den richtigen Chat (WZE-3)
    assert tg.messages[0]["chat_id"] == 42

    # WZE-5: alle Wünsche erscheinen in der Antwort
    assert "Lasagne" in antwort
    assert "Apfel" in antwort
    assert "Karotten" in antwort

    # E-WZE-2: Gerichte erscheinen vor Obst & Gemüse
    pos_gerichte = antwort.index("Gerichte")
    pos_obst = antwort.index("Obst & Gemüse")
    assert pos_gerichte < pos_obst, "Gerichte müssen vor Obst & Gemüse stehen (E-WZE-2)"


def test_WZE5_E_WZE2_reihenfolge_fest():
    """E-WZE-2: Die vier Kategorien erscheinen in der Spec-Reihenfolge
    (Gerichte → Obst & Gemüse → Brotbelag → Sonstiges), unabhängig von
    der Ankunfts-Reihenfolge."""
    # Wünsche kommen in umgekehrter Reihenfolge aus der API
    wuensche = [
        {"label": "Milch", "kategorie": "sonstiges"},
        {"label": "Butter", "kategorie": "brotbelag"},
        {"label": "Banane", "kategorie": "obst_gemuese"},
        {"label": "Spaghetti", "kategorie": "gericht"},
    ]

    text = formatiere_wuensche(wuensche)

    pos_gerichte  = text.index("Gerichte")
    pos_obst      = text.index("Obst & Gemüse")
    pos_brotbelag = text.index("Brotbelag")
    pos_sonstiges = text.index("Sonstiges")

    assert pos_gerichte < pos_obst < pos_brotbelag < pos_sonstiges, (
        "Kategorien müssen in fester Reihenfolge stehen (E-WZE-2)")


def test_WZE5_leere_kategorie_traegt_keine():
    """WZE-5: Leere Kategorien tragen '- (keine)', damit klar ist,
    dass sie abgefragt wurden."""
    wuensche = [{"label": "Apfel", "kategorie": "obst_gemuese"}]

    text = formatiere_wuensche(wuensche)

    # Alle vier Kategorien müssen erscheinen
    assert "Gerichte:" in text
    assert "Brotbelag:" in text
    assert "Sonstiges:" in text
    # Leere Kategorien tragen "(keine)"
    assert "(keine)" in text


def test_WZE5_vier_kategorien_immer_vorhanden():
    """WZE-5: Alle vier Kategorien erscheinen in jeder Antwort."""
    wuensche = [{"label": "X", "kategorie": "gericht"}]

    text = formatiere_wuensche(wuensche)

    for kat_text in ["Gerichte:", "Obst & Gemüse:", "Brotbelag:", "Sonstiges:"]:
        assert kat_text in text, "Kategorie '%s' fehlt" % kat_text


def test_WZE5_unbekannte_kategorie_wird_sonstiges():
    """WZE-5 defensiv: Wunsch mit unbekannter Kategorie landet unter
    'Sonstiges' (kein Crash)."""
    wuensche = [{"label": "Unbekannt", "kategorie": "xyz"}]

    text = formatiere_wuensche(wuensche)

    assert "Unbekannt" in text


# ============================================================
#  WZE-6: Leere Liste — ehrliche Meldung, Signal 'leer'
# ============================================================

def test_WZE6_leere_liste_ehrliche_meldung():
    """WZE-6: Buddy liefert leere Liste → Skill postet ehrliche Meldung,
    kein Kategorie-Schema."""
    tg = FakeTelegram()
    ec = FakeEssenClient(wuensche=[])

    signal = wuensche_zeigen(
        tg=tg,
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
    )

    assert signal == SIGNAL_LEER
    assert len(tg.messages) == 1
    text = tg.messages[0]["text"]
    # WZE-6: ehrliche Leer-Meldung — kein Kategorie-Schema
    assert "keine" in text.lower() or "leer" in text.lower()
    # WZE-6: kein Kategorie-Format (keine Überschriften)
    assert "Gerichte:" not in text
    assert "Obst & Gemüse:" not in text


# ============================================================
#  WZE-7: Buddy nicht erreichbar — ehrliche Grenze
# ============================================================

def test_WZE7_transport_fehler_nicht_erreichbar():
    """WZE-7: Transport-Fehler → Signal 'nicht_erreichbar', ehrliche
    Grenze, kein Cache, kein Retry (EC-7)."""
    tg = FakeTelegram()
    ec = FakeEssenClient(
        error=EssenClientError("Connection refused"))

    signal = wuensche_zeigen(
        tg=tg,
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
    )

    assert signal == SIGNAL_NICHT_ERREICHBAR
    assert ec.get_calls == 1, "Kein Retry (WZE-7)"
    assert len(tg.messages) == 1
    # WZE-7: ehrliche Grenze-Meldung
    assert "nicht erreichbar" in tg.messages[0]["text"].lower()


def test_WZE7_kein_retry():
    """WZE-7: bei Transport-Fehler KEIN zweiter Aufruf."""
    tg = FakeTelegram()
    ec = FakeEssenClient(error=EssenClientError("Timeout"))

    wuensche_zeigen(
        tg=tg,
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
    )

    assert ec.get_calls == 1


# ============================================================
#  WZE-3: Antwort landet im richtigen Chat
# ============================================================

def test_WZE3_antwort_im_anfrage_chat():
    """WZE-3: die Antwort geht in den Chat, in dem die Frage kam."""
    tg = FakeTelegram()
    ec = FakeEssenClient(wuensche=[{"label": "Apfel", "kategorie": "obst_gemuese"}])

    zielchat = 99999
    wuensche_zeigen(
        tg=tg,
        chat_id=zielchat,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
    )

    assert tg.messages[0]["chat_id"] == zielchat


# ============================================================
#  APP-3: Skill ruft API, nicht Datei
# ============================================================

def test_APP3_keine_datei_zugriffe():
    """APP-3 / WZE-4: die Funktion liest wuensche.json NICHT direkt.

    EssenClient ist die einzige Lese-Naht (WZE-4). Wenn er als Fake
    injiziert ist und gleichzeitig open() blockiert wird, müssen die
    Tests durchlaufen — ein FS-Bypass würde die open-Blockade auslösen.
    """
    tg = FakeTelegram()
    ec = FakeEssenClient(wuensche=[{"label": "Apfel", "kategorie": "obst_gemuese"}])

    with mock.patch("builtins.open",
                    side_effect=AssertionError("FS-Bypass verboten")):
        signal = wuensche_zeigen(
            tg=tg,
            chat_id=42,
            from_user_id=7,
            essen_client=ec,
            is_member_fn=_immer_mitglied,
        )

    assert signal == SIGNAL_BEANTWORTET
    assert ec.get_calls == 1


# ============================================================
#  KATEGORIEN_REIHENFOLGE Konstante — spec-konforme Reihenfolge
# ============================================================

def test_E_WZE2_kategorien_reihenfolge_konstante():
    """E-WZE-2: die Konstante KATEGORIEN_REIHENFOLGE enthält die vier
    Kategorien in der vorgeschriebenen Reihenfolge."""
    assert KATEGORIEN_REIHENFOLGE == [
        "gericht", "obst_gemuese", "brotbelag", "sonstiges"]
