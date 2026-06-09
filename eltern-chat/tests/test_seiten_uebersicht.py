"""Tests für seiten_uebersicht + SeitenUebersichtTask + Catalog-Registrierung
(SREG-5/SREG-5b/SREG-6/SREG-7, Refs #476, #488).

Pflicht-Tests (AC1–AC5 + AC488):
- AC1: SeitenUebersichtTask im build_catalog registriert (SREG-6 AND-Guard).
- AC2: Default-Pfad → Link auf Übersichts-Seite + Sub-Frage im Bot-Text.
- AC3: Opt-in-Pfad → Direkt-URL. Mehrdeutigkeit → EC-22-Rückfrage.
- AC4: Opt-out/kein Suchbegriff → stilles Ende nach Opt-out (oder Default-Pfad).
- AC5: Config akzeptiert display_url_origin (alt) + display_url_origin_heim (neu),
       _heim gewinnt wenn beide gesetzt.
- AC488-1: Opt-in Runde 1 (aktion=inventar): Inventar als Tool-Result, KEIN Bot-Post.
- AC488-2: Opt-in Runde 2 (aktion=match + exaktes label): Direkt-URL via Bot-Post.
- AC488-3: 4 Bug-Beispiele (Controller, Eltern Panel, Wetter, Plan) liefern korrekt.
- AC488-4: Default-Pfad (ohne suchbegriff) unverändert grün.
"""

import json

import config as config_mod
import pytest
from fakes import FakeTelegram
from skills.seiten_client import SeitenClientError
from skills.seiten_uebersicht import (
    AKTION_INVENTAR,
    AKTION_MATCH,
    SIGNAL_ABGELEHNT,
    SIGNAL_DEFAULT_GESENDET,
    SIGNAL_DIREKT_GESENDET,
    SIGNAL_INVENTAR_GELIEFERT,
    SIGNAL_MEHRDEUTIG,
    SIGNAL_NICHT_ERREICHBAR,
    baue_uebersichts_url,
    formatiere_default_antwort,
    formatiere_ec22_rueckfrage,
    formatiere_inventar_tool_result,
    formatiere_mehrdeutigkeit_tool_result,
    matche_view,
    matche_view_exakt,
    seiten_uebersicht,
)
from skills.seiten_uebersicht_task import SeitenUebersichtTask
from tasks import ReadTask, TurnContext, build_catalog

# ============================================================
#  Inventar-Fixtures
# ============================================================

def _inventar_einfach():
    return [
        {"pfad": "/display/wetter/regeln",
         "label": "Garderoben-Editor",
         "typ": "eltern",
         "zeigt": "Wetter-Regeln bearbeiten",
         "synonyme": ["garderobe", "wetter-regeln"]},
        {"pfad": "/display/plan/woche",
         "label": "Wochenplan",
         "typ": "display",
         "zeigt": "Der Wochenplan der Familie",
         "synonyme": ["woche", "plan"]},
        {"pfad": "/controller/figuren-erkennung/",
         "label": "Figuren-Erkennung",
         "typ": "controller",
         "zeigt": "Figuren-Erkennung Controller",
         "synonyme": []},
    ]


def _inventar_mehrdeutig():
    """Zwei Einträge, die beide 'wetter' enthalten (label/synonyme)."""
    return [
        {"pfad": "/display/wetter/heute",
         "label": "Wetter heute",
         "typ": "display",
         "zeigt": "Heutiges Wetter anzeigen",
         "synonyme": ["wetter-heute"]},
        {"pfad": "/display/wetter/regeln",
         "label": "Wetter Regeln",
         "typ": "eltern",
         "zeigt": "Wetter-Regeln bearbeiten",
         "synonyme": ["wetter-regeln", "garderobe"]},
    ]


def _inventar_panels(n=2):
    """N Panel-Instanzen: je 1 Panel- + 1 Editor-Eintrag = 2N Einträge (SREG-11)."""
    eintraege = []
    for i in range(1, n + 1):
        pid = "panel-%d" % i
        eintraege.append({
            "key": "panel-%s" % pid,
            "typ": "panel",
            "instanz": pid,
            "pfad": "/controller/app-panel/%s" % pid,
            "label": "Panel %s" % pid,
            "zeigt": "Panel-Steuerung %s" % pid,
            "zielgruppe": "eltern",
            "synonyme": [],
        })
        eintraege.append({
            "key": "%s-bearbeiten" % pid,
            "typ": "eltern",
            "instanz": pid,
            "pfad": "/controller/app-panel/%s/bearbeiten" % pid,
            "label": "Panel %s bearbeiten" % pid,
            "zeigt": "Panel %s Editor" % pid,
            "zielgruppe": "eltern",
            "synonyme": [],
        })
    return eintraege


# ============================================================
#  Doppelungen
# ============================================================

class FakeSeitenClient:
    """Kontrollierte Doppelung des SeitenClients."""

    def __init__(self, eintraege=None, error=None):
        self._eintraege = eintraege if eintraege is not None else []
        self._error = error
        self.inventar_calls = 0

    def inventar(self):
        self.inventar_calls += 1
        if self._error is not None:
            raise self._error
        return list(self._eintraege)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_turn_context(chat_id=100, from_user_id=42):
    return TurnContext(chat_id=chat_id, from_user_id=from_user_id)


# ============================================================
#  Tests: baue_uebersichts_url / formatiere_default_antwort
# ============================================================

class TestBaueUebersichtsUrl:
    def test_url_enthaelt_pfad(self):
        url = baue_uebersichts_url("https://hub.local")
        assert "/api/v1/seiten/uebersicht" in url

    def test_url_enthaelt_origin(self):
        url = baue_uebersichts_url("https://hub.local")
        assert url.startswith("https://hub.local")

    def test_kein_doppel_slash(self):
        url = baue_uebersichts_url("https://hub.local/")
        assert "//api" not in url

    def test_leere_origin_wirft_valueerror(self):
        with pytest.raises(ValueError, match="display_url_origin_heim"):
            baue_uebersichts_url("")

    def test_none_origin_wirft_valueerror(self):
        with pytest.raises(ValueError, match="display_url_origin_heim"):
            baue_uebersichts_url(None)


class TestFormatierDefaultAntwort:
    def test_enthaelt_url(self):
        text = formatiere_default_antwort("https://hub.local")
        assert "https://hub.local/api/v1/seiten/uebersicht" in text

    def test_enthaelt_sub_frage(self):
        """AC2: Sub-Frage muss im Default-Antwort-Text enthalten sein."""
        text = formatiere_default_antwort("https://hub.local")
        assert "direkt" in text.lower() or "schicken" in text.lower()

    def test_leere_origin_wirft(self):
        with pytest.raises(ValueError, match="display_url_origin_heim"):
            formatiere_default_antwort("")


# ============================================================
#  Tests: matche_view (Pro-View-Matching, SREG-5b)
# ============================================================

class TestMatcheView:
    def test_kein_suchbegriff_leer(self):
        treffer, mehrdeutig = matche_view(_inventar_einfach(), "")
        assert treffer == []
        assert not mehrdeutig

    def test_none_suchbegriff_leer(self):
        treffer, _mehrdeutig = matche_view(_inventar_einfach(), None)
        assert treffer == []

    def test_eindeutiger_treffer(self):
        treffer, mehrdeutig = matche_view(_inventar_einfach(), "Garderobe")
        assert len(treffer) == 1
        assert not mehrdeutig
        assert treffer[0]["pfad"] == "/display/wetter/regeln"

    def test_case_insensitiv(self):
        treffer, mehrdeutig = matche_view(_inventar_einfach(), "garderobe")
        assert len(treffer) == 1
        assert not mehrdeutig

    def test_suche_in_zeigt(self):
        """SREG-5b: Suche auch in zeigt-Feld."""
        treffer, mehrdeutig = matche_view(_inventar_einfach(), "wochenplan")
        # "wochenplan" ist im label von Wochenplan
        assert len(treffer) == 1
        assert not mehrdeutig

    def test_mehrdeutig_bei_mehreren_treffern(self):
        """SREG-5b: Mehrdeutigkeit wenn mind. 2 Einträge matchen."""
        treffer, mehrdeutig = matche_view(_inventar_mehrdeutig(), "wetter")
        assert len(treffer) >= 2
        assert mehrdeutig

    def test_keine_treffer(self):
        treffer, mehrdeutig = matche_view(_inventar_einfach(), "gibts-nicht-xyz")
        assert treffer == []
        assert not mehrdeutig

    def test_leeres_inventar(self):
        treffer, mehrdeutig = matche_view([], "garderobe")
        assert treffer == []
        assert not mehrdeutig

    def test_pfad_wird_nicht_gesucht(self):
        """SREG-5b: Suche nur in label/synonyme/zeigt, nicht in pfad/typ."""
        inv = [{"pfad": "/controller/spezial/seite",
                "label": "Normalseite",
                "zeigt": "Zeigt Normales",
                "synonyme": [],
                "typ": "eltern"}]
        # "spezial" ist nur im Pfad, nicht in label/synonyme/zeigt
        treffer, _ = matche_view(inv, "spezial")
        assert treffer == []


class TestFormatierEc22Rueckfrage:
    def test_enthaelt_label_der_treffer(self):
        treffer = [
            {"label": "Wetter heute", "pfad": "/display/wetter/heute"},
            {"label": "Wetter Regeln", "pfad": "/display/wetter/regeln"},
        ]
        text = formatiere_ec22_rueckfrage(treffer)
        assert "Wetter heute" in text
        assert "Wetter Regeln" in text

    def test_frageformat(self):
        treffer = [
            {"label": "Option A", "pfad": "/a"},
            {"label": "Option B", "pfad": "/b"},
        ]
        text = formatiere_ec22_rueckfrage(treffer)
        assert "?" in text or "Meintest" in text


# ============================================================
#  Tests: seiten_uebersicht (Haupt-Funktion)
# ============================================================

class TestSeitenUebersicht:
    # -- AC2: Default-Pfad --

    def test_default_pfad_signal(self):
        """AC2: Default-Pfad → SIGNAL_DEFAULT_GESENDET."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert signal == SIGNAL_DEFAULT_GESENDET

    def test_default_pfad_sendet_url(self):
        """AC2: Default-Antwort enthält display_url_origin_heim + /api/v1/seiten/uebersicht."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert tg.sent
        antwort = tg.sent[0]["text"]
        assert "https://hub.local/api/v1/seiten/uebersicht" in antwort

    def test_default_pfad_sub_frage(self):
        """AC2: Default-Antwort enthält Sub-Frage (SREG-5)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        antwort = tg.sent[0]["text"]
        # Sub-Frage muss Hinweis auf direktes Schicken enthalten
        assert "direkt" in antwort.lower() or "schicken" in antwort.lower()

    def test_default_pfad_ruft_kein_inventar(self):
        """SREG-5: Default-Pfad ruft GET /api/v1/seiten NICHT auf."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert client.inventar_calls == 0

    def test_default_pfad_antwort_in_richtigen_chat(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_uebersicht(
            tg=tg,
            chat_id=999,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert tg.sent[0]["chat_id"] == 999

    # -- AC3: Opt-in-Pfad —

    def test_opt_in_match_eindeutig(self):
        """AC3: Eindeutiger Treffer → SIGNAL_DIREKT_GESENDET + Direkt-URL."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="Garderobe",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert signal == SIGNAL_DIREKT_GESENDET
        assert tg.sent
        antwort = tg.sent[0]["text"]
        assert "https://hub.local/display/wetter/regeln" in antwort

    def test_opt_in_match_url_enthaelt_origin(self):
        """AC3: Direkt-URL enthält Heim-Origin (SREG-5b/SREG-7)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="plan",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        antwort = tg.sent[0]["text"]
        assert "https://hub.local" in antwort

    def test_mehrdeutigkeit_ec22(self):
        """AC3: Mehrdeutigkeit → EC-22-Rückfrage, SIGNAL_MEHRDEUTIG als Tupel (#549)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_mehrdeutig())
        ergebnis = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="wetter",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert isinstance(ergebnis, tuple)
        signal, kandidaten_text = ergebnis
        assert signal == SIGNAL_MEHRDEUTIG
        assert tg.sent
        # EC-22-Rückfrage muss erkennbar eine Frage sein
        antwort = tg.sent[0]["text"]
        assert "?" in antwort or "Meintest" in antwort
        # kandidaten_text muss die strukturierte Liste enthalten
        assert isinstance(kandidaten_text, str)
        assert len(kandidaten_text) > 0

    def test_mehrdeutigkeit_kein_direkt_link(self):
        """AC3: Bei Mehrdeutigkeit wird KEIN Direkt-Link geschickt."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_mehrdeutig())
        seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="wetter",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        # Nur eine Nachricht, kein Direkt-Link
        assert len(tg.sent) == 1

    # -- AC4: Opt-out / kein Folge-Turn --

    def test_opt_out_kein_match(self):
        """AC4: Kein Treffer → Fallback-Antwort (kein stilles Ende), kein Crash."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="gibts-nicht-xyz",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        # Kein crash, eine sinnvolle Antwort
        assert signal in (SIGNAL_DEFAULT_GESENDET, SIGNAL_DIREKT_GESENDET)
        assert tg.sent

    def test_kein_folge_turn_default_pfad_ohne_suchbegriff(self):
        """AC4: Ohne Suchbegriff (Timeout/Opt-out → Modell ruft Default-Pfad) →
        Default-Antwort, kein wiederholtes Nachfragen (eine Nachricht)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff=None,
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        # Genau eine Nachricht, kein wiederholtes Nachfragen
        assert len(tg.sent) == 1

    # -- Fehler-Pfade --

    def test_nicht_mitglied_abgelehnt(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_kein_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert signal == SIGNAL_ABGELEHNT
        assert not tg.sent

    def test_chat_id_none_abgelehnt(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_uebersicht(
            tg=tg,
            chat_id=None,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert signal == SIGNAL_ABGELEHNT

    def test_registry_nicht_erreichbar_opt_in(self):
        """Opt-in-Pfad: Registry nicht erreichbar → SIGNAL_NICHT_ERREICHBAR."""
        tg = FakeTelegram()
        client = FakeSeitenClient(error=SeitenClientError("timeout"))
        signal = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="garderobe",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert signal == SIGNAL_NICHT_ERREICHBAR
        assert tg.sent
        assert "nicht erreichbar" in tg.sent[0]["text"].lower()


# ============================================================
#  Tests: SeitenUebersichtTask
# ============================================================

class TestSeitenUebersichtTask:
    def test_ist_read_task(self):
        """SeitenUebersichtTask muss ReadTask sein (EC-9)."""
        tg = FakeTelegram()
        client = FakeSeitenClient([])
        task = SeitenUebersichtTask(tg=tg, seiten_client=client,
                                    is_member_fn=_immer_mitglied)
        assert isinstance(task, ReadTask)

    def test_name_ist_seiten_uebersicht(self):
        tg = FakeTelegram()
        client = FakeSeitenClient([])
        task = SeitenUebersichtTask(tg=tg, seiten_client=client,
                                    is_member_fn=_immer_mitglied)
        assert task.name == "seiten_uebersicht"

    def test_run_default_pfad(self):
        """AC2: Task ohne suchbegriff → Default-Pfad-Quittung."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(tg=tg, seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = _make_turn_context()
        result = task.run({}, ctx)
        assert isinstance(result, str)
        assert len(result) > 0
        # Default-Pfad → Link gesendet
        assert tg.sent
        assert "https://hub.local/api/v1/seiten/uebersicht" in tg.sent[0]["text"]

    def test_run_opt_in_mit_suchbegriff(self):
        """AC3: Task mit suchbegriff → Opt-in-Pfad → Direkt-URL."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(tg=tg, seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Garderobe"}, ctx)
        assert isinstance(result, str)
        assert tg.sent
        antwort = tg.sent[0]["text"]
        assert "https://hub.local/display/wetter/regeln" in antwort

    def test_run_chat_id_kommt_aus_turn_context(self):
        """Zielchat kommt aus TurnContext, nicht aus arguments (EC-12)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(tg=tg, seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = TurnContext(chat_id=777, from_user_id=42)
        task.run({}, ctx)
        assert tg.sent[0]["chat_id"] == 777

    def test_run_ohne_turn_context_abgelehnt(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(tg=tg, seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        result = task.run({}, None)
        assert "mitglied" in result.lower() or "Familien" in result

    def test_run_nicht_erreichbar_quittung(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(error=SeitenClientError("down"))
        task = SeitenUebersichtTask(tg=tg, seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "garderobe"}, ctx)
        assert "nicht erreichbar" in result.lower()


# ============================================================
#  Tests: SREG-5b Weg 2 — Zweistufiges KI-Matching (#488)
#  AC488-1: Runde 1 (aktion=inventar) → Inventar als Tool-Result, kein Bot-Post.
#  AC488-2: Runde 2 (aktion=match + exaktes label) → Direkt-URL via Bot-Post.
#  AC488-3: 4 Bug-Beispiele (Controller, Eltern Panel, Wetter, Plan).
#  AC488-4: Default-Pfad unverändert grün (kein suchbegriff).
# ============================================================

def _inventar_bug_beispiele():
    """Inventar mit den 4 Bug-Beispielen aus dem Bug-Befund (#488)."""
    return [
        {"key": "figuren-erkennung-controller",
         "pfad": "/controller/figuren-erkennung/",
         "label": "Figuren-Erkennung Controller",
         "typ": "controller",
         "zeigt": "Figuren-Erkennung Controller-App",
         "synonyme": ["figuren", "controller"]},
        {"key": "panel-1",
         "pfad": "/controller/app-panel/panel-1",
         "label": "Panel panel-1",
         "typ": "panel",
         "zeigt": "Panel-Steuerung panel-1",
         "synonyme": []},
        {"key": "panel-1-bearbeiten",
         "pfad": "/controller/app-panel/panel-1/bearbeiten",
         "label": "Eltern Panel panel-1 bearbeiten",
         "typ": "eltern",
         "zeigt": "Panel panel-1 Editor",
         "synonyme": ["panel-editor", "eltern-panel"]},
        {"key": "wetter-heute",
         "pfad": "/display/wetter/heute",
         "label": "Wetter heute",
         "typ": "display",
         "zeigt": "Heutiges Wetter anzeigen",
         "synonyme": ["wetter"]},
        {"key": "plan-woche",
         "pfad": "/display/plan/woche",
         "label": "Wochenplan",
         "typ": "display",
         "zeigt": "Der Wochenplan der Familie",
         "synonyme": ["woche", "plan"]},
    ]


class TestSreg5bWeg2OptinInventar:
    """AC488-1/AC488-2: Zweistufiges KI-Matching via aktion=inventar + aktion=match."""

    def _task(self, inventar=None):
        tg = FakeTelegram()
        client = FakeSeitenClient(inventar or _inventar_bug_beispiele())
        task = SeitenUebersichtTask(
            tg=tg, seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        return tg, client, task

    # -- AC488-1: Runde 1 --

    def test_runde1_gibt_inventar_als_tool_result(self):
        """AC488-1: aktion=inventar → Tool-Result-String, KEIN Bot-Post."""
        tg, _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Controller", "aktion": "inventar"}, ctx)
        assert isinstance(result, str)
        assert len(result) > 0
        # Kein Bot-Post in Runde 1.
        assert not tg.sent, "Runde 1: KEIN Bot-Post erwartet, aber tg.sent nicht leer"

    def test_runde1_inventar_ruft_seiten_client_einmal(self):
        """AC488-1: inventar() wird genau einmal gerufen."""
        _tg, client, task = self._task()
        ctx = _make_turn_context()
        task.run({"suchbegriff": "Wetter", "aktion": "inventar"}, ctx)
        assert client.inventar_calls == 1

    def test_runde1_tool_result_enthaelt_labels(self):
        """AC488-1: Tool-Result enthält label + key aller Views."""
        _tg, _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Plan", "aktion": "inventar"}, ctx)
        # Alle Labels müssen im Tool-Result sichtbar sein.
        assert "Wochenplan" in result
        assert "Figuren-Erkennung Controller" in result
        assert "Wetter heute" in result

    def test_runde1_tool_result_enthaelt_synonyme_und_zeigt(self):
        """AC488-1: Tool-Result enthält synonyme + zeigt (für LLM-Matching)."""
        _tg, _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Eltern Panel", "aktion": "inventar"}, ctx)
        # synonyme und zeigt müssen im Tool-Result stehen.
        assert "panel-editor" in result or "eltern-panel" in result
        assert "Panel panel-1 Editor" in result

    def test_runde1_signal_ist_inventar_geliefert(self):
        """AC488-1: Funktion gibt SIGNAL_INVENTAR_GELIEFERT-Tupel zurück."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_bug_beispiele())
        ergebnis = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="Controller",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_INVENTAR,
        )
        assert isinstance(ergebnis, tuple)
        signal, inventar_text = ergebnis
        assert signal == SIGNAL_INVENTAR_GELIEFERT
        assert isinstance(inventar_text, str)
        assert len(inventar_text) > 0
        assert not tg.sent, "KEIN Bot-Post in Runde 1"

    # -- AC488-2: Runde 2 --

    def test_runde2_exact_label_sendet_direkt_url(self):
        """AC488-2: aktion=match + exaktes label → Direkt-URL als Bot-Post."""
        tg, _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run(
            {"suchbegriff": "Figuren-Erkennung Controller", "aktion": "match"},
            ctx,
        )
        assert isinstance(result, str)
        assert tg.sent, "Runde 2: Bot-Post erwartet"
        antwort = tg.sent[0]["text"]
        assert "https://hub.local/controller/figuren-erkennung/" in antwort

    def test_runde2_signal_ist_direkt_gesendet(self):
        """AC488-2: aktion=match + exaktes label → SIGNAL_DIREKT_GESENDET."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_bug_beispiele())
        ergebnis = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="Wochenplan",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert ergebnis == SIGNAL_DIREKT_GESENDET
        assert tg.sent
        assert "https://hub.local/display/plan/woche" in tg.sent[0]["text"]


class TestSreg5bBugBeispiele:
    """AC488-3: 4 Bug-Beispiele aus dem Bug-Befund liefern sinnvolle Direkt-URL
    oder echte EC-22-Rückfrage — KEIN generischer 'keine Seite gefunden'-Fallback.

    Simuliert beide Runden: Runde 1 (aktion=inventar) gibt Inventar zurück,
    Runde 2 (aktion=match + exaktes label aus Inventar) findet den View.
    """

    def _zweistufig(self, suchbegriff_r1, suchbegriff_r2):
        """Hilfsmethode: simuliert beide Runden für ein Suchbegriff-Paar."""
        tg1 = FakeTelegram()
        client1 = FakeSeitenClient(_inventar_bug_beispiele())
        # Runde 1: Inventar holen.
        ergebnis1 = seiten_uebersicht(
            tg=tg1, chat_id=100, from_user_id=42,
            suchbegriff=suchbegriff_r1,
            seiten_client=client1,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_INVENTAR,
        )
        assert isinstance(ergebnis1, tuple), "Runde 1 muss Tupel liefern"
        signal1, inventar_text = ergebnis1
        assert signal1 == SIGNAL_INVENTAR_GELIEFERT
        assert not tg1.sent, "Kein Bot-Post in Runde 1"

        # Runde 2: Mit exaktem label aus Inventar matchen.
        tg2 = FakeTelegram()
        client2 = FakeSeitenClient(_inventar_bug_beispiele())
        ergebnis2 = seiten_uebersicht(
            tg=tg2, chat_id=100, from_user_id=42,
            suchbegriff=suchbegriff_r2,
            seiten_client=client2,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        return tg2, ergebnis2, inventar_text

    def test_bug_beispiel_controller(self):
        """AC488-3: 'Controller' → zwei Runden → URL zur Figuren-Erkennung."""
        # Das LLM würde aus dem Inventar "Figuren-Erkennung Controller" wählen.
        tg, ergebnis, inventar_text = self._zweistufig(
            "Controller", "Figuren-Erkennung Controller")
        # Inventar enthält den passenden Eintrag.
        assert "Figuren-Erkennung Controller" in inventar_text
        # Runde 2: Direkt-URL gesendet.
        assert ergebnis == SIGNAL_DIREKT_GESENDET
        assert tg.sent
        assert "https://hub.local/controller/figuren-erkennung/" in tg.sent[0]["text"]

    def test_bug_beispiel_eltern_panel(self):
        """AC488-3: 'Eltern Panel' → zwei Runden → URL zum Panel-Editor."""
        # Das LLM würde aus dem Inventar "Eltern Panel panel-1 bearbeiten" wählen.
        tg, ergebnis, inventar_text = self._zweistufig(
            "Eltern Panel", "Eltern Panel panel-1 bearbeiten")
        assert "Eltern Panel panel-1 bearbeiten" in inventar_text
        # Runde 2: Direkt-URL oder EC-22 — beides ist korrekt (KEIN generischer Fallback).
        # (#549: SIGNAL_MEHRDEUTIG wird als Tupel zurückgegeben)
        signal = ergebnis[0] if isinstance(ergebnis, tuple) else ergebnis
        assert signal in (SIGNAL_DIREKT_GESENDET, SIGNAL_MEHRDEUTIG), (
            "Erwartet Direkt-URL oder EC-22-Rückfrage, nicht generischer Fallback")
        assert tg.sent

    def test_bug_beispiel_wetter(self):
        """AC488-3: 'Wetter' → zwei Runden → Direkt-URL oder EC-22 (KEIN Fallback)."""
        # Das LLM würde aus dem Inventar "Wetter heute" wählen.
        tg, ergebnis, inventar_text = self._zweistufig("Wetter", "Wetter heute")
        assert "Wetter heute" in inventar_text
        # (#549: SIGNAL_MEHRDEUTIG wird als Tupel zurückgegeben)
        signal = ergebnis[0] if isinstance(ergebnis, tuple) else ergebnis
        assert signal in (SIGNAL_DIREKT_GESENDET, SIGNAL_MEHRDEUTIG), (
            "Erwartet Direkt-URL oder EC-22-Rückfrage, nicht generischer Fallback")
        assert tg.sent
        # Bei eindeutigem Match muss die URL zum Wetter-View führen.
        if signal == SIGNAL_DIREKT_GESENDET:
            assert "https://hub.local/display/wetter/heute" in tg.sent[0]["text"]

    def test_bug_beispiel_plan(self):
        """AC488-3: 'Plan' → zwei Runden → Direkt-URL zum Wochenplan."""
        # Das LLM würde aus dem Inventar "Wochenplan" wählen.
        tg, ergebnis, inventar_text = self._zweistufig("Plan", "Wochenplan")
        assert "Wochenplan" in inventar_text
        # (#549: SIGNAL_MEHRDEUTIG wird als Tupel zurückgegeben)
        signal = ergebnis[0] if isinstance(ergebnis, tuple) else ergebnis
        assert signal in (SIGNAL_DIREKT_GESENDET, SIGNAL_MEHRDEUTIG), (
            "Erwartet Direkt-URL oder EC-22-Rückfrage, nicht generischer Fallback")
        assert tg.sent
        if signal == SIGNAL_DIREKT_GESENDET:
            assert "https://hub.local/display/plan/woche" in tg.sent[0]["text"]


class TestFormatierInventarToolResult:
    """Unit-Tests für formatiere_inventar_tool_result()."""

    def test_enthaelt_alle_labels(self):
        inv = _inventar_bug_beispiele()
        result = formatiere_inventar_tool_result(inv)
        assert "Figuren-Erkennung Controller" in result
        assert "Wochenplan" in result
        assert "Wetter heute" in result

    def test_enthaelt_keys(self):
        inv = _inventar_bug_beispiele()
        result = formatiere_inventar_tool_result(inv)
        assert "figuren-erkennung-controller" in result
        assert "plan-woche" in result

    def test_enthaelt_synonyme(self):
        inv = _inventar_bug_beispiele()
        result = formatiere_inventar_tool_result(inv)
        assert "wetter" in result
        assert "plan" in result

    def test_enthaelt_zeigt(self):
        inv = _inventar_bug_beispiele()
        result = formatiere_inventar_tool_result(inv)
        assert "Heutiges Wetter anzeigen" in result

    def test_leeres_inventar_gibt_hinweis(self):
        result = formatiere_inventar_tool_result([])
        assert "leer" in result.lower() or "keine" in result.lower()

    def test_inventar_anzahl_im_header(self):
        inv = _inventar_bug_beispiele()
        result = formatiere_inventar_tool_result(inv)
        assert str(len(inv)) in result


# ============================================================
#  Tests: formatiere_mehrdeutigkeit_tool_result (#549)
# ============================================================

class TestFormatierMehrdeutigkeitToolResult:
    """Unit-Tests für formatiere_mehrdeutigkeit_tool_result() (#549).

    T549-Test1: Struktur-Test — kandidaten_text enthält label, key, pfad
    aller Kandidaten + Auflösungs-Anweisung.
    """

    def _treffer_mia(self):
        return [
            {"label": "Panel mias-panel-01",
             "key": "panel-mias-panel-01",
             "pfad": "/controller/app-panel/mias-panel-01"},
            {"label": "Panel mias-panel-01 bearbeiten",
             "key": "mias-panel-01-bearbeiten",
             "pfad": "/controller/app-panel/mias-panel-01/bearbeiten"},
        ]

    def test_enthaelt_labels_aller_kandidaten(self):
        """T549-Test1a: Jedes label der Treffer ist im kandidaten_text enthalten."""
        result = formatiere_mehrdeutigkeit_tool_result(self._treffer_mia())
        assert 'label: "Panel mias-panel-01"' in result
        assert 'label: "Panel mias-panel-01 bearbeiten"' in result

    def test_enthaelt_keys_aller_kandidaten(self):
        """T549-Test1b: Jedes key der Treffer ist im kandidaten_text enthalten."""
        result = formatiere_mehrdeutigkeit_tool_result(self._treffer_mia())
        assert "panel-mias-panel-01" in result
        assert "mias-panel-01-bearbeiten" in result

    def test_enthaelt_pfade_aller_kandidaten(self):
        """T549-Test1c: Jeder pfad der Treffer ist im kandidaten_text enthalten."""
        result = formatiere_mehrdeutigkeit_tool_result(self._treffer_mia())
        assert "/controller/app-panel/mias-panel-01" in result
        assert "/controller/app-panel/mias-panel-01/bearbeiten" in result

    def test_enthaelt_aufloesung_anweisung(self):
        """T549-Test1d: kandidaten_text enthält Auflösungs-Anweisung ans LLM."""
        result = formatiere_mehrdeutigkeit_tool_result(self._treffer_mia())
        assert "aktion=match" in result
        assert "Default-Fallback" in result or "Default" in result

    def test_enthaelt_nummerierung(self):
        """T549-Test1e: Kandidaten sind nummeriert (1., 2., ...)."""
        result = formatiere_mehrdeutigkeit_tool_result(self._treffer_mia())
        assert "1." in result
        assert "2." in result

    def test_eintrag_ohne_key_kein_crash(self):
        """Defensiv: Eintrag ohne key/pfad → kein crash."""
        treffer = [{"label": "Nur Label"}]
        result = formatiere_mehrdeutigkeit_tool_result(treffer)
        assert "Nur Label" in result


# ============================================================
#  Tests: SIGNAL_MEHRDEUTIG Tupel-Pfad + Roundtrip (#549)
# ============================================================

class TestMehrdeutigkeitTupelUndRoundtrip:
    """T549-Test2: SIGNAL_MEHRDEUTIG gibt Tupel zurück; Roundtrip via Task-Tool-Result.

    Simuliert den Mia-Panel-Live-Bug:
      Runde match → 2 Treffer → Tupel (SIGNAL_MEHRDEUTIG, kandidaten_text)
      → User sagt „Die Ansicht" → LLM ruft mit aktion=match + exaktem label
      → SIGNAL_DIREKT_GESENDET (kein Default-Fallback).
    """

    def _inventar_mia(self):
        return [
            {"label": "Panel mias-panel-01",
             "key": "panel-mias-panel-01",
             "pfad": "/controller/app-panel/mias-panel-01",
             "typ": "panel",
             "zeigt": "Panel-Steuerung mias-panel-01",
             "synonyme": []},
            {"label": "Panel mias-panel-01 bearbeiten",
             "key": "mias-panel-01-bearbeiten",
             "pfad": "/controller/app-panel/mias-panel-01/bearbeiten",
             "typ": "eltern",
             "zeigt": "Panel mias-panel-01 Editor",
             "synonyme": []},
        ]

    def test_signal_mehrdeutig_ist_tupel(self):
        """T549-Test2a: Bei Mehrdeutigkeit (Substring-Pfad, kein aktion=match) gibt
        seiten_uebersicht() ein Tupel zurück.

        Mit aktion=match (Fix #2) wird Equality-Lookup verwendet — kein SIGNAL_MEHRDEUTIG
        mehr bei aktion=match. Der Substring-Pfad (aktion=None) bleibt für Legacy-Fälle.
        """
        tg = FakeTelegram()
        client = FakeSeitenClient(self._inventar_mia())
        # Ohne aktion → Substring-Pfad → beide Einträge enthalten "mias-panel-01" → mehrdeutig.
        ergebnis = seiten_uebersicht(
            tg=tg,
            chat_id=100, from_user_id=42,
            suchbegriff="mias-panel-01",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=None,
        )
        assert isinstance(ergebnis, tuple), (
            "SIGNAL_MEHRDEUTIG muss als Tupel zurückgegeben werden (#549)")
        signal, kandidaten_text = ergebnis
        assert signal == SIGNAL_MEHRDEUTIG
        assert isinstance(kandidaten_text, str)
        assert len(kandidaten_text) > 0

    def test_signal_mehrdeutig_kandidaten_text_enthaelt_beide_labels(self):
        """T549-Test2b: kandidaten_text enthält beide Panel-Labels (Substring-Pfad)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(self._inventar_mia())
        ergebnis = seiten_uebersicht(
            tg=tg,
            chat_id=100, from_user_id=42,
            suchbegriff="mias-panel-01",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=None,
        )
        _, kandidaten_text = ergebnis
        assert 'label: "Panel mias-panel-01"' in kandidaten_text
        assert 'label: "Panel mias-panel-01 bearbeiten"' in kandidaten_text

    def test_task_mehrdeutig_gibt_kandidaten_text_als_tool_result(self):
        """T549-Test2c: SeitenUebersichtTask gibt kandidaten_text als Tool-Result zurück
        (Substring-Pfad, kein aktion=match).

        Mit aktion=match (Fix #2) würde Equality-Lookup verwendet; hier testen wir
        den Substring-Pfad (kein aktion), der weiterhin mehrdeutig liefert.
        """
        tg = FakeTelegram()
        client = FakeSeitenClient(self._inventar_mia())
        task = SeitenUebersichtTask(
            tg=tg, seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        ctx = _make_turn_context()
        # Kein aktion → Substring-Pfad → mehrdeutig → kandidaten_text als Tool-Result.
        result = task.run(
            {"suchbegriff": "mias-panel-01"}, ctx)
        # Task muss kandidaten_text zurückgeben (nicht statische Quittung).
        assert isinstance(result, str)
        assert 'label: "Panel mias-panel-01"' in result
        assert "aktion=match" in result

    def test_roundtrip_disambiguation_ansicht(self):
        """T549-Test2d: Roundtrip — Mehrdeutigkeits-Tool-Result → match mit exaktem label.

        Simuliert den Mia-Panel-Live-Bug (T549-Fix2):
          Runde inventar (q='mias-panel-01') → kandidaten_text mit label + key.
          Runde match (q='Panel mias-panel-01') → Equality-Lookup trifft
          NUR den ersten Eintrag → SIGNAL_DIREKT_GESENDET (kein Präfix-Geschwister-Bug).

        Mit Equality-Match bei aktion=match trifft das exakte label 'Panel mias-panel-01'
        nicht den Editor 'Panel mias-panel-01 bearbeiten' — deterministisches Lookup
        auf diszipliniertem Wert (SREG-5b).
        """
        # Runde 1: Inventar holen, um kandidaten_text zu erhalten.
        tg1 = FakeTelegram()
        client1 = FakeSeitenClient(self._inventar_mia())
        ergebnis1 = seiten_uebersicht(
            tg=tg1, chat_id=100, from_user_id=42,
            suchbegriff="mias-panel-01",
            seiten_client=client1,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_INVENTAR,
        )
        assert isinstance(ergebnis1, tuple)
        signal1, inventar_text = ergebnis1
        assert signal1 == SIGNAL_INVENTAR_GELIEFERT
        # Inventar enthält label + key beider Einträge.
        assert "Panel mias-panel-01" in inventar_text
        assert "panel-mias-panel-01" in inventar_text
        assert "Panel mias-panel-01 bearbeiten" in inventar_text
        assert not tg1.sent, "Kein Bot-Post in Runde 1"

        # Runde 2: LLM wählt exaktes label der Ansicht → Equality-Match trifft nur diesen.
        tg2 = FakeTelegram()
        client2 = FakeSeitenClient(self._inventar_mia())
        ergebnis2 = seiten_uebersicht(
            tg=tg2, chat_id=100, from_user_id=42,
            suchbegriff="Panel mias-panel-01",
            seiten_client=client2,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert ergebnis2 == SIGNAL_DIREKT_GESENDET, (
            "Equality-Match mit exaktem label muss SIGNAL_DIREKT_GESENDET liefern "
            "(T549-Fix2: kein Präfix-Geschwister-Bug)")
        assert tg2.sent
        assert "https://hub.local/controller/app-panel/mias-panel-01" in tg2.sent[0]["text"]
        # Kein /bearbeiten-Suffix → Ansicht, nicht Editor.
        assert "/bearbeiten" not in tg2.sent[0]["text"]

    def test_roundtrip_disambiguation_editor(self):
        """T549-Test2e: Roundtrip — Disambiguation auf Editor-View.

        Runde match (q='Panel mias-panel-01 bearbeiten') → SIGNAL_DIREKT_GESENDET (Editor).
        """
        tg = FakeTelegram()
        client = FakeSeitenClient(self._inventar_mia())
        ergebnis = seiten_uebersicht(
            tg=tg, chat_id=100, from_user_id=42,
            suchbegriff="Panel mias-panel-01 bearbeiten",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert ergebnis == SIGNAL_DIREKT_GESENDET, (
            "Exaktes label für Editor-View muss Direkt-URL liefern (#549)")
        assert tg.sent
        assert "/bearbeiten" in tg.sent[0]["text"]


# ============================================================
#  Tests: Equality-Match bei aktion=match (T549-Fix2)
# ============================================================

class TestAktionMatchEquality:
    """Fix #2 für T549: Equality-Lookup bei aktion=match.

    Verhindert Präfix-Geschwister-Mehrdeutigkeit (Mia-Panel-Bug):
      'Panel mias-panel-01' trifft NICHT 'Panel mias-panel-01 bearbeiten'.
    """

    def _inventar_praefix_geschwister(self):
        """Mia-Bug-Inventar: label von Eintrag 1 ist Präfix von Eintrag 2."""
        return [
            {"label": "Panel mias-panel-01",
             "key": "panel-mias-panel-01",
             "pfad": "/controller/app-panel/mias-panel-01",
             "typ": "panel",
             "zeigt": "Panel-Steuerung mias-panel-01",
             "synonyme": []},
            {"label": "Panel mias-panel-01 bearbeiten",
             "key": "mias-panel-01-bearbeiten",
             "pfad": "/controller/app-panel/mias-panel-01/bearbeiten",
             "typ": "eltern",
             "zeigt": "Panel mias-panel-01 Editor",
             "synonyme": []},
        ]

    def test_aktion_match_label_equality_bei_praefix_geschwistern(self):
        """Live-Symptom-Test: aktion=match + exaktes label trifft NUR ersten Eintrag.

        'Panel mias-panel-01' ist Präfix von 'Panel mias-panel-01 bearbeiten'.
        Substring-Match würde beide treffen (mehrdeutig). Equality-Match trifft nur
        den ersten Eintrag → SIGNAL_DIREKT_GESENDET, kein SIGNAL_MEHRDEUTIG.
        """
        tg = FakeTelegram()
        client = FakeSeitenClient(self._inventar_praefix_geschwister())
        ergebnis = seiten_uebersicht(
            tg=tg, chat_id=100, from_user_id=42,
            suchbegriff="Panel mias-panel-01",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert ergebnis == SIGNAL_DIREKT_GESENDET, (
            "Equality-Match muss NUR den Eintrag mit exakt diesem label treffen "
            "— kein Präfix-Geschwister-Bug (T549-Fix2)")
        assert tg.sent
        assert "https://hub.local/controller/app-panel/mias-panel-01" in tg.sent[0]["text"]
        # Kein /bearbeiten-Suffix → nur Ansicht, nicht Editor.
        assert "/bearbeiten" not in tg.sent[0]["text"]

    def test_aktion_match_key_pfad(self):
        """aktion=match + key als suchbegriff → Equality-Match auf key trifft Eintrag."""
        tg = FakeTelegram()
        client = FakeSeitenClient(self._inventar_praefix_geschwister())
        ergebnis = seiten_uebersicht(
            tg=tg, chat_id=100, from_user_id=42,
            suchbegriff="mias-panel-01-bearbeiten",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert ergebnis == SIGNAL_DIREKT_GESENDET, (
            "Equality-Match auf key muss den Eintrag treffen (T549-Fix2)")
        assert tg.sent
        assert "/bearbeiten" in tg.sent[0]["text"]

    def test_aktion_match_kein_treffer(self):
        """aktion=match + unbekannter suchbegriff → klares Signal, kein Default-Loop."""
        tg = FakeTelegram()
        client = FakeSeitenClient(self._inventar_praefix_geschwister())
        ergebnis = seiten_uebersicht(
            tg=tg, chat_id=100, from_user_id=42,
            suchbegriff="gibt es nicht",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        # Kein Treffer → SIGNAL_DEFAULT_GESENDET mit erklärender Nachricht.
        assert ergebnis == SIGNAL_DEFAULT_GESENDET
        assert tg.sent
        # Die Nachricht soll den suchbegriff nennen und auf aktion=inventar hinweisen.
        text = tg.sent[0]["text"]
        assert "gibt es nicht" in text or "inventar" in text.lower()
        # Kein SIGNAL_MEHRDEUTIG-Loop.
        assert not isinstance(ergebnis, tuple)


# ============================================================
#  Tests: Catalog-Registrierung + AND-Guard (AC1)
# ============================================================

class TestCatalogRegistrierung:
    def _make_tg(self):
        return FakeTelegram(members={42: {"status": "member"}})

    def test_guard_seiten_origin_und_fgcid_registriert(self):
        """AC1: seiten_origin_url + family_group_chat_id_getter → SeitenUebersichtTask registriert."""
        tg = self._make_tg()
        catalog = build_catalog(
            tg, "ca.pem",
            seiten_origin_url="http://127.0.0.1:5042",
            family_group_chat_id_getter=lambda: 200,
            display_url_origin_heim="https://hub.local",
        )
        task = catalog.get("seiten_uebersicht")
        assert task is not None
        assert isinstance(task, SeitenUebersichtTask)

    def test_guard_ohne_seiten_origin_nicht_registriert(self):
        """Ohne seiten_origin_url → Task fehlt im Katalog."""
        tg = self._make_tg()
        catalog = build_catalog(
            tg, "ca.pem",
            seiten_origin_url=None,
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("seiten_uebersicht") is None

    def test_guard_ohne_fgcid_getter_nicht_registriert(self):
        """Ohne family_group_chat_id_getter → Task fehlt im Katalog."""
        tg = self._make_tg()
        catalog = build_catalog(
            tg, "ca.pem",
            seiten_origin_url="http://127.0.0.1:5042",
            family_group_chat_id_getter=None,
        )
        assert catalog.get("seiten_uebersicht") is None

    def test_guard_beide_fehlen_nicht_registriert(self):
        """Ohne seiten_origin_url und ohne fgcid_getter → Task fehlt."""
        tg = self._make_tg()
        catalog = build_catalog(tg, "ca.pem")
        assert catalog.get("seiten_uebersicht") is None

    def test_seiten_finden_nicht_mehr_registriert(self):
        """AC1: seiten_finden (Vorgänger) ist NICHT im Katalog."""
        tg = self._make_tg()
        catalog = build_catalog(
            tg, "ca.pem",
            seiten_origin_url="http://127.0.0.1:5042",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("seiten_finden") is None


# ============================================================
#  Tests: Config-Migration (AC5) — SREG-7
# ============================================================

def _set_bot_token(monkeypatch):
    monkeypatch.setenv("ELTERNCHAT_BOT_TOKEN", "test-token-xyz")


def _missing(tmp_path):
    return str(tmp_path / "config.json")


class TestConfigMigration:
    def test_alt_only_display_url_origin(self, tmp_path, monkeypatch):
        """AC5: Nur display_url_origin (alt) gesetzt → Config.display_url_origin_heim
        erhält diesen Wert (Fallback-Pfad, SREG-7)."""
        _set_bot_token(monkeypatch)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN", raising=False)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN_HEIM", raising=False)
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "display_url_origin": "https://hub-alt.local",
        }))
        cfg = config_mod.resolve(str(cfg_file))
        assert cfg.display_url_origin_heim == "https://hub-alt.local"

    def test_neu_only_display_url_origin_heim(self, tmp_path, monkeypatch):
        """AC5: Nur display_url_origin_heim (neu) gesetzt → Config.display_url_origin_heim
        ist gesetzt (direkter Pfad, SREG-7)."""
        _set_bot_token(monkeypatch)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN", raising=False)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN_HEIM", raising=False)
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "display_url_origin_heim": "https://hub-heim.local",
        }))
        cfg = config_mod.resolve(str(cfg_file))
        assert cfg.display_url_origin_heim == "https://hub-heim.local"

    def test_beide_heim_gewinnt(self, tmp_path, monkeypatch):
        """AC5: Beide gesetzt → display_url_origin_heim hat Vorrang (SREG-7)."""
        _set_bot_token(monkeypatch)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN", raising=False)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN_HEIM", raising=False)
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "display_url_origin": "https://hub-alt.local",
            "display_url_origin_heim": "https://hub-heim.local",
        }))
        cfg = config_mod.resolve(str(cfg_file))
        assert cfg.display_url_origin_heim == "https://hub-heim.local"

    def test_tailscale_leer_als_default(self, tmp_path, monkeypatch):
        """SREG-7: display_url_origin_tailscale Default ist leer — kein Auto-Fallback."""
        _set_bot_token(monkeypatch)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN_TAILSCALE", raising=False)
        cfg = config_mod.resolve(_missing(tmp_path))
        assert cfg.display_url_origin_tailscale == ""

    def test_tailscale_aus_datei(self, tmp_path, monkeypatch):
        """SREG-7: display_url_origin_tailscale wird aus Datei gelesen."""
        _set_bot_token(monkeypatch)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN_TAILSCALE", raising=False)
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "display_url_origin_tailscale": "https://hub.tailnet.ts.net",
        }))
        cfg = config_mod.resolve(str(cfg_file))
        assert cfg.display_url_origin_tailscale == "https://hub.tailnet.ts.net"

    def test_tailscale_kein_fallback_auf_heim(self, tmp_path, monkeypatch):
        """SREG-7: Kein Auto-Fallback von Tailscale auf Heim (falsche Origin)."""
        _set_bot_token(monkeypatch)
        monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN_TAILSCALE", raising=False)
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "display_url_origin_heim": "https://hub-heim.local",
        }))
        cfg = config_mod.resolve(str(cfg_file))
        # Tailscale bleibt leer — kein Fallback auf Heim-Wert
        assert cfg.display_url_origin_tailscale == ""

    def test_config_attribute_existieren(self, tmp_path, monkeypatch):
        """AC5: Config-Objekt hat display_url_origin_heim + display_url_origin_tailscale."""
        _set_bot_token(monkeypatch)
        cfg = config_mod.resolve(_missing(tmp_path))
        assert hasattr(cfg, "display_url_origin_heim")
        assert hasattr(cfg, "display_url_origin_tailscale")
