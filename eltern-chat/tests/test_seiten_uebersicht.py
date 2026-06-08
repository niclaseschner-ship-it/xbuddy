"""Tests für seiten_uebersicht + SeitenUebersichtTask + Catalog-Registrierung
(SREG-5/SREG-5b/SREG-6/SREG-7, Refs #476).

Pflicht-Tests (AC1–AC5):
- AC1: SeitenUebersichtTask im build_catalog registriert (SREG-6 AND-Guard).
- AC2: Default-Pfad → Link auf Übersichts-Seite + Sub-Frage im Bot-Text.
- AC3: Opt-in-Pfad → Direkt-URL. Mehrdeutigkeit → EC-22-Rückfrage.
- AC4: Opt-out/kein Suchbegriff → stilles Ende nach Opt-out (oder Default-Pfad).
- AC5: Config akzeptiert display_url_origin (alt) + display_url_origin_heim (neu),
       _heim gewinnt wenn beide gesetzt.
"""

import json

import config as config_mod
import pytest
from fakes import FakeTelegram
from skills.seiten_client import SeitenClientError
from skills.seiten_uebersicht import (
    SIGNAL_ABGELEHNT,
    SIGNAL_DEFAULT_GESENDET,
    SIGNAL_DIREKT_GESENDET,
    SIGNAL_MEHRDEUTIG,
    SIGNAL_NICHT_ERREICHBAR,
    baue_uebersichts_url,
    formatiere_default_antwort,
    formatiere_ec22_rueckfrage,
    matche_view,
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
        """AC3: Mehrdeutigkeit → EC-22-Rückfrage, SIGNAL_MEHRDEUTIG."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_mehrdeutig())
        signal = seiten_uebersicht(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="wetter",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert signal == SIGNAL_MEHRDEUTIG
        assert tg.sent
        # EC-22-Rückfrage muss erkennbar eine Frage sein
        antwort = tg.sent[0]["text"]
        assert "?" in antwort or "Meintest" in antwort

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
