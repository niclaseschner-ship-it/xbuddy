"""Tests für die `termine_aus_bild`-Funktion — specs/platform/termine-aus-bild.md
TAB-1 … TAB-11, TAB-13 (Refs #475).

Jede TAB-Anforderung mit Code-Verhalten hat einen Test (TAB-13). Keine Netz-
Aufrufe — Telegram, multimodaler Anbieter und Plan-Buddy sind durch
kontrollierte Doppelungen ersetzt (EC-17).
"""

from datetime import date

import pytest
from fakes import FakeTelegram
from skills._multimodal import ExtractedTermin, MultimodalError
from skills.plan_client import (
    PlanBulkNotReached,
    PlanBulkUnknown,
    PlanClientError,
)
from skills.termine_aus_bild import (
    MAX_ITEMS,
    SIGNAL_ABGEBROCHEN,
    SIGNAL_ABGELEHNT,
    SIGNAL_EINGETRAGEN,
    SIGNAL_NICHT_ERREICHBAR,
    SIGNAL_PROVIDER_FEHLER,
    SIGNAL_UNBEKANNT,
    SIGNAL_UNKLAR,
    SIGNAL_VERWORFEN,
    SIGNAL_WORDS,
    baue_luecken_nachricht,
    baue_sammel_vorschlag,
    parse_luecken_antwort,
    termine_aus_bild,
    validiere_und_filtere,
)

# ============================================================
#  Test-Doppelungen
# ============================================================

class StubMultimodalProvider:
    """Stub des MultimodalProvider — gibt ein vorgefertigtes Ergebnis zurück."""

    def __init__(self, items=None, error=None):
        self._items = items or []
        self._error = error
        self.calls = []

    def extract_termine(self, *, image_bytes, image_media_type, caption):
        self.calls.append({
            "image_bytes": image_bytes,
            "image_media_type": image_media_type,
            "caption": caption,
        })
        if self._error is not None:
            raise self._error
        # Defensiv kopieren, damit Tests Items wiederverwenden können.
        return [
            ExtractedTermin(
                titel=item.titel, beginn=item.beginn, ende=item.ende,
                ganztags=item.ganztags,
                personen_hinweise=item.personen_hinweise,
            )
            for item in self._items
        ]


class StubBulkPlanClient:
    """Stub des PlanClients für put_termine_bulk (TAB-9). Aufrufe werden
    aufgezeichnet; das Verhalten ist skriptbar."""

    def __init__(self, *, response=None, error=None):
        self._response = response
        self._error = error
        self.bulk_calls = []

    def put_termine_bulk(self, request_id, items):
        self.bulk_calls.append((request_id, list(items)))
        if self._error is not None:
            raise self._error
        if self._response is not None:
            return self._response
        # Default: alle eingetragen.
        results = [{"ok": True, "event_id": "evt-%d" % i}
                   for i in range(len(items))]
        return {
            "ok": True,
            "geschrieben": len(items),
            "gesamt": len(items),
            "results": results,
        }


class _Queue:
    """Trivialer next_message-Stub: gibt vorab gefüllte Nachrichten zurück."""

    def __init__(self, msgs):
        self._msgs = list(msgs)

    def __call__(self):
        if not self._msgs:
            return None
        return self._msgs.pop(0)


def _msg(text):
    """Minimaler TabInput-Ersatz für next_message-Stubs."""
    class _M:
        pass
    m = _M()
    m.text = text
    return m


# ============================================================
#  TAB-1 — Aufruf-Vertrag
# ============================================================

def test_TAB1_eingetragen_signal_minimal():
    """TAB-1: Aufruf mit Bild + Caption + plausibler Termin-Liste vom
    Anbieter-Stub liefert nach Bestätigung „eingetragen"."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [ExtractedTermin(titel="Sportfest", beginn="2026-09-15", ganztags=True)]
    provider = StubMultimodalProvider(items=items)
    plan_client = StubBulkPlanClient()
    result = termine_aus_bild(
        tg=tg,
        private_chat_id=42,
        from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake",
        image_media_type="image/jpeg",
        caption="termine eintragen",
        multimodal_provider=provider,
        plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([_msg("ok")]),
        heute=date(2026, 6, 1))
    assert result == SIGNAL_EINGETRAGEN
    assert len(plan_client.bulk_calls) == 1
    request_id, body_items = plan_client.bulk_calls[0]
    # request_id UUIDv4-Form (8-4-4-4-12, 36 chars).
    assert len(request_id) == 36
    assert body_items[0]["titel"] == "Sportfest"


def test_TAB1_ohne_private_chat_bricht_ab():
    """TAB-1: ein Aufruf ohne private_chat_id bricht ohne Wirkung ab."""
    tg = FakeTelegram()
    result = termine_aus_bild(
        tg=tg, private_chat_id=None, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=StubMultimodalProvider(),
        plan_client=StubBulkPlanClient(),
        is_member_fn=lambda uid: True,
        next_message=_Queue([]))
    assert result == SIGNAL_ABGELEHNT
    assert tg.sent == []


# ============================================================
#  TAB-2 — Berechtigung live
# ============================================================

def test_TAB2_nicht_mitglied_abgelehnt_ohne_anbieter_aufruf():
    """TAB-2: Aufruf eines Nicht-Mitglieds → „abgelehnt"; Bild geht NICHT an
    den KI-Anbieter."""
    tg = FakeTelegram(members={})
    provider = StubMultimodalProvider(items=[
        ExtractedTermin(titel="X", beginn="2026-09-15", ganztags=True)])
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=99,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=provider, plan_client=StubBulkPlanClient(),
        is_member_fn=lambda uid: False,
        next_message=_Queue([]))
    assert result == SIGNAL_ABGELEHNT
    assert provider.calls == [], "Bild hätte NICHT an den Anbieter gehen dürfen"


# ============================================================
#  TAB-4 — Signalwort-Liste hart-codiert
# ============================================================

def test_TAB4_signalwort_liste_hart_codiert():
    """TAB-4: SIGNAL_WORDS ist ein hart-codierter String-Tupel und enthält
    mindestens die in der Spec genannten Wörter."""
    assert isinstance(SIGNAL_WORDS, tuple)
    spec_minimum = {"termin", "termine", "kalender", "eintragen",
                    "plan", "schulplan", "kursplan"}
    assert spec_minimum.issubset(set(SIGNAL_WORDS))


# ============================================================
#  TAB-5 — Anbieter-Fehler → provider_fehler
# ============================================================

def test_TAB5_provider_fehler_signal_und_keine_bulk():
    """TAB-5: Anbieter wirft → „provider_fehler" + hart-codierte Antwort,
    KEIN Bulk-PUT."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    provider = StubMultimodalProvider(error=MultimodalError("simulated"))
    plan_client = StubBulkPlanClient()
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=provider, plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([]))
    assert result == SIGNAL_PROVIDER_FEHLER
    assert plan_client.bulk_calls == []
    # Hart-codierte ehrliche Antwort im Privatchat.
    assert tg.sent
    assert "KI-Anbieter" in tg.sent[-1]["text"]


# ============================================================
#  TAB-6 — Plausi-Filter + leere Liste → unklar
# ============================================================

def test_TAB6_termin_ausserhalb_plausi_wird_verworfen():
    """TAB-6: ein `beginn` außerhalb [heute-30d, heute+2J] wird verworfen."""
    heute = date(2026, 6, 1)
    items = [
        ExtractedTermin(titel="Zu früh", beginn="2025-01-01", ganztags=True),
        ExtractedTermin(titel="Zu spät", beginn="2029-01-01", ganztags=True),
        ExtractedTermin(titel="Im Fenster", beginn="2026-09-15", ganztags=True),
    ]
    gefiltert, verworfen, cap = validiere_und_filtere(items, heute=heute)
    assert verworfen == 2
    assert cap == 0
    assert len(gefiltert) == 1
    assert gefiltert[0].titel == "Im Fenster"


def test_TAB6_leere_liste_nach_filter_unklar():
    """TAB-6: bleibt nach der Filterung eine LEERE Liste, endet die Funktion
    mit „unklar" und OHNE Bulk-PUT."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [ExtractedTermin(titel="X", beginn="2025-01-01", ganztags=True)]
    provider = StubMultimodalProvider(items=items)
    plan_client = StubBulkPlanClient()
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=provider, plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([]),
        heute=date(2026, 6, 1))
    assert result == SIGNAL_UNKLAR
    assert plan_client.bulk_calls == []


def test_TAB6_termin_ohne_titel_kommt_in_luecken_sammler():
    """TAB-6: ein Termin ohne `titel` markiert das Feld als fehlend (für
    TAB-8.1), wird aber nicht im Plausi-Schritt verworfen."""
    heute = date(2026, 6, 1)
    items = [ExtractedTermin(titel="", beginn="2026-09-15", ganztags=True)]
    gefiltert, _verworfen, _cap = validiere_und_filtere(items, heute=heute)
    assert len(gefiltert) == 1
    assert "titel" in gefiltert[0].fehlende_felder


def test_TAB6_cap_30_mit_hinweis():
    """TAB-6 / Risk 7 Variante A: bei mehr als 30 plausiblen Items wird auf
    30 gecappt; der TAB-7-Vorschlag enthält einen Hinweis auf die verbleibenden."""
    heute = date(2026, 6, 1)
    items = [
        ExtractedTermin(titel="Termin %d" % i,
                        beginn="2026-09-%02d" % ((i % 28) + 1),
                        ganztags=True)
        for i in range(35)
    ]
    gefiltert, _verworfen, cap_hinweis_n = validiere_und_filtere(
        items, heute=heute)
    assert len(gefiltert) == MAX_ITEMS == 30
    assert cap_hinweis_n == 5
    # Der gebaute Sammel-Vorschlag erwähnt den Hinweis.
    vorschlag = baue_sammel_vorschlag(gefiltert, cap_hinweis_n=cap_hinweis_n)
    # Wortlaut normiert: „die ersten 30 … die weiteren 5 …" (Variante A).
    assert "30" in vorschlag
    assert "5" in vorschlag
    assert "weiteren" in vorschlag


# ============================================================
#  TAB-7 — Sammel-Vorschlag im <pre>-Block, EIN Bestätigungswort
# ============================================================

def test_TAB7_vorschlag_ist_html_pre_block_mit_escape():
    """TAB-7: nummerierte Liste im <pre>-Block; Titel mit `<`/`&`/`>` werden
    HTML-escaped, damit die <pre>-Klammer nicht zerstört wird."""
    items = [ExtractedTermin(titel="A&B<x>", beginn="2026-09-15", ganztags=True)]
    out = baue_sammel_vorschlag(items)
    assert "<pre>" in out
    assert "</pre>" in out
    assert "A&amp;B&lt;x&gt;" in out
    assert "1)" in out


def test_TAB7_ein_eecsieben_wort_loest_bulk_fuer_alle_aus():
    """TAB-7: EIN E-EC-7-Wort als Antwort löst den Bulk-PUT für ALLE Items aus."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [
        ExtractedTermin(titel="A", beginn="2026-09-15", ganztags=True),
        ExtractedTermin(titel="B", beginn="2026-09-16", ganztags=True),
    ]
    provider = StubMultimodalProvider(items=items)
    plan_client = StubBulkPlanClient()
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=provider, plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([_msg("ok")]),
        heute=date(2026, 6, 1))
    assert result == SIGNAL_EINGETRAGEN
    assert len(plan_client.bulk_calls[0][1]) == 2


def test_TAB7_nicht_bestaetigung_liefert_verworfen():
    """TAB-7: eine nicht-bestätigende Antwort → „verworfen" OHNE Bulk-PUT."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [ExtractedTermin(titel="A", beginn="2026-09-15", ganztags=True)]
    plan_client = StubBulkPlanClient()
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=StubMultimodalProvider(items=items),
        plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([_msg("nein")]),
        heute=date(2026, 6, 1))
    assert result == SIGNAL_VERWORFEN
    assert plan_client.bulk_calls == []


# ============================================================
#  TAB-8.1 — Sentinel-Lücken-Rückfrage + Parser
# ============================================================

def test_TAB81_sentinel_nachricht_mit_eckigen_klammern():
    """TAB-8.1: Sentinel-Form ist eckig `[?feldname?]`, kompatibel mit HTML-Modus."""
    item = ExtractedTermin(titel="", beginn="2026-09-15", ganztags=True)
    item.fehlende_felder = ["titel"]
    out = baue_luecken_nachricht([(3, item)])
    assert "[?titel?]" in out
    assert "3)" in out


def test_TAB81_korrekt_ersetzte_antwort_wird_geparst():
    """TAB-8.1: eine korrekt ersetzte Antwort wird deterministisch geparst."""
    item = ExtractedTermin(titel="", beginn="2026-09-15", ganztags=True)
    item.fehlende_felder = ["titel"]
    pairs = [(1, item)]
    ok = parse_luecken_antwort("1) 15.09.2026 — Sportfest", pairs)
    assert ok is True
    assert item.titel == "Sportfest"
    assert item.fehlende_felder == []


def test_TAB81_falsche_antwort_loest_zweite_rueckfrage_aus():
    """TAB-8.1: bleibt das Sentinel in der Antwort stehen, ist die Lücke
    NICHT geklärt."""
    item = ExtractedTermin(titel="", beginn="2026-09-15", ganztags=True)
    item.fehlende_felder = ["titel"]
    pairs = [(1, item)]
    ok = parse_luecken_antwort("1) 15.09.2026 — [?titel?]", pairs)
    assert ok is False
    assert "titel" in item.fehlende_felder


# ============================================================
#  TAB-8.2 — personen_hinweise sind nie Pflicht
# ============================================================

def test_TAB82_personen_hinweise_loesen_keine_rueckfrage_aus():
    """TAB-8.2: `personen_hinweise` machen keinen Lücken-Eintrag und werden
    NICHT in den Titel eingearbeitet."""
    heute = date(2026, 6, 1)
    items = [ExtractedTermin(
        titel="Klettern", beginn="2026-09-15", ganztags=True,
        personen_hinweise="für Mila")]
    gefiltert, _v, _c = validiere_und_filtere(items, heute=heute)
    assert gefiltert[0].fehlende_felder == []
    # Titel bleibt unverändert.
    assert gefiltert[0].titel == "Klettern"


# ============================================================
#  TAB-8.3 — max 2 Runden
# ============================================================

def test_TAB83_zwei_runden_ohne_klaerung_liefert_unklar():
    """TAB-8.3: zwei Sentinel-Runden ohne valide Antwort → „unklar"."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    item = ExtractedTermin(titel="", beginn="2026-09-15", ganztags=True)
    provider = StubMultimodalProvider(items=[item])
    plan_client = StubBulkPlanClient()
    # Beide Antworten lassen das Sentinel drin → keine Klärung.
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=provider, plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([
            _msg("1) 15.09.2026 — [?titel?]"),
            _msg("1) 15.09.2026 — [?titel?]"),
        ]),
        heute=date(2026, 6, 1))
    assert result == SIGNAL_UNKLAR
    assert plan_client.bulk_calls == []


# ============================================================
#  TAB-9 — Bulk-PUT-Form
# ============================================================

def test_TAB9_bulk_put_form_uuid_und_items():
    """TAB-9: PlanClient.put_termine_bulk wird mit UUIDv4 `request_id` und
    items aufgerufen; die items haben PLAN-22-Form (`titel`, `beginn`[, `ende`])."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [
        ExtractedTermin(titel="A", beginn="2026-09-15", ganztags=True),
        ExtractedTermin(titel="B",
                        beginn="2026-09-22T18:00:00+02:00",
                        ende="2026-09-22T20:00:00+02:00", ganztags=False),
    ]
    provider = StubMultimodalProvider(items=items)
    plan_client = StubBulkPlanClient()
    termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=provider, plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([_msg("ok")]),
        heute=date(2026, 6, 1))
    request_id, body_items = plan_client.bulk_calls[0]
    # UUIDv4-Länge.
    assert len(request_id) == 36
    # Items in PLAN-22-Form.
    assert body_items[0] == {"titel": "A", "beginn": "2026-09-15"}
    assert body_items[1] == {
        "titel": "B",
        "beginn": "2026-09-22T18:00:00+02:00",
        "ende": "2026-09-22T20:00:00+02:00",
    }


# ============================================================
#  TAB-10 — drei Fehler-Lagen (nicht_erreichbar / unbekannt)
# ============================================================

@pytest.mark.parametrize(("err", "expected_signal"), [
    (PlanBulkNotReached("connection refused"), SIGNAL_NICHT_ERREICHBAR),
    (PlanBulkUnknown("connection torn mid-flight"), SIGNAL_UNBEKANNT),
    (PlanClientError("HTTP 400 validation"), SIGNAL_NICHT_ERREICHBAR),
])
def test_TAB10_fehler_lagen_signal(err, expected_signal):
    """TAB-10: drei Fehler-Lagen → drei Signale (nicht_erreichbar / unbekannt /
    nicht_erreichbar als 4xx-Fall)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [ExtractedTermin(titel="A", beginn="2026-09-15", ganztags=True)]
    plan_client = StubBulkPlanClient(error=err)
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=StubMultimodalProvider(items=items),
        plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([_msg("ok")]),
        heute=date(2026, 6, 1))
    assert result == expected_signal


def test_TAB10_unbekannt_quittung_wortlaut():
    """TAB-10: bei „unbekannt" enthält die Quittung den Hinweis auf den
    Wochenplan-Nachschau-Auftrag (Spec normiert: ehrlich, keine Halluzination)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [ExtractedTermin(titel="A", beginn="2026-09-15", ganztags=True)]
    plan_client = StubBulkPlanClient(error=PlanBulkUnknown("torn"))
    termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=StubMultimodalProvider(items=items),
        plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([_msg("ok")]),
        heute=date(2026, 6, 1))
    # Wortlaut enthält ehrliche Aussage „nicht sicher" / „Wochenplan".
    letzte = tg.sent[-1]["text"]
    assert "nicht sicher" in letzte or "Wochenplan" in letzte


# ============================================================
#  TAB-11 — N-von-M-Quittung mit Fehler-Codes
# ============================================================

def test_TAB11_teilmisserfolg_quittung_listet_fehler_nummern():
    """TAB-11: HTTP 200 mit geschrieben=3 gesamt=5 → Quittung mit
    Fehler-Nummern (Nummer 3 (validation), Nummer 7 (calendar_rate_limit), …)."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [
        ExtractedTermin(titel="T%d" % i,
                        beginn="2026-09-%02d" % (i + 1),
                        ganztags=True) for i in range(5)
    ]
    response = {
        "ok": False,
        "geschrieben": 3,
        "gesamt": 5,
        "results": [
            {"ok": True, "event_id": "evt-1"},
            {"ok": True, "event_id": "evt-2"},
            {"ok": False, "error_code": "validation"},
            {"ok": True, "event_id": "evt-4"},
            {"ok": False, "error_code": "calendar_rate_limit"},
        ],
    }
    plan_client = StubBulkPlanClient(response=response)
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=StubMultimodalProvider(items=items),
        plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([_msg("ok")]),
        heute=date(2026, 6, 1))
    assert result == SIGNAL_EINGETRAGEN
    letzte = tg.sent[-1]["text"]
    assert "3 von 5" in letzte
    assert "Nummer 3" in letzte
    assert "validation" in letzte
    assert "Nummer 5" in letzte
    assert "calendar_rate_limit" in letzte


# ============================================================
#  Abbruch durch Session-Timeout (next_message → None)
# ============================================================

def test_session_timeout_liefert_abgebrochen():
    """SESS-3: next_message liefert None (Session-Timeout) → „abgebrochen"."""
    tg = FakeTelegram(members={42: {"status": "member"}})
    items = [ExtractedTermin(titel="A", beginn="2026-09-15", ganztags=True)]
    plan_client = StubBulkPlanClient()
    result = termine_aus_bild(
        tg=tg, private_chat_id=42, from_user_id=42,
        family_group_chat_id=200,
        image_bytes=b"fake", image_media_type="image/jpeg",
        caption="termine",
        multimodal_provider=StubMultimodalProvider(items=items),
        plan_client=plan_client,
        is_member_fn=lambda uid: True,
        next_message=_Queue([]),  # leerer Stream → None
        heute=date(2026, 6, 1))
    assert result == SIGNAL_ABGEBROCHEN
    assert plan_client.bulk_calls == []
