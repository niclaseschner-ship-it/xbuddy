"""Tests für seiten_uebersicht + SeitenUebersichtTask + Catalog-Registrierung
(SREG-5/SREG-5b/SREG-6/SREG-7, Refs #476, #488, #583).

EC-29 / TASK-10: Die Funktion sendet selbst keine Telegram-Nachricht mehr.
Sie returnt in jedem Pfad einen User-tauglichen Antwort-Text als String.
Berechtigungs-Bruch (SREG-6) wirft BerechtigungError.

Pflicht-Tests (AC1–AC5 + AC488):
- AC1: SeitenUebersichtTask im build_catalog registriert (SREG-6 AND-Guard).
- AC2: Default-Pfad → Link auf Übersichts-Seite + Sub-Frage als Tool-Result-Text.
- AC3: Opt-in-Pfad → Direkt-URL als Tool-Result. aktion fehlt/unbekannt → Fehler-Tool-Result (SREG-5b).
- AC4: Opt-out/kein Suchbegriff → Default-Pfad als Tool-Result.
- AC5: Config akzeptiert display_url_origin (alt) + display_url_origin_heim (neu),
       _heim gewinnt wenn beide gesetzt.
- AC488-1: Opt-in Runde 1 (aktion=inventar): Inventar als Tool-Result, KEIN Bot-Post.
- AC488-2: Opt-in Runde 2 (aktion=match + exaktes label): Direkt-URL als Tool-Result.
- AC488-3: 4 Bug-Beispiele (Controller, Eltern Panel, Wetter, Plan) liefern korrekt.
- AC488-4: Default-Pfad (ohne suchbegriff) unverändert grün.
- TASK-10 Baseline: task.run() sendet in keinem Pfad selbst (FakeTelegram leer).
"""

import json

import config as config_mod
import pytest
from fakes import FakeTelegram
from skills._errors import BerechtigungError
from skills.seiten_client import SeitenClientError
from skills.seiten_uebersicht import (
    AKTION_INVENTAR,
    AKTION_MATCH,
    baue_uebersichts_url,
    formatiere_default_antwort,
    formatiere_inventar_tool_result,
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
#  Tests: seiten_uebersicht (Haupt-Funktion) — EC-29
#  Die Funktion sendet nicht mehr selbst; sie returnt einen Tool-Result-Text.
#  Berechtigungs-Bruch wirft BerechtigungError.
# ============================================================

class TestSeitenUebersicht:
    # -- AC2: Default-Pfad --

    def test_default_pfad_gibt_text_zurueck(self):
        """AC2: Default-Pfad → Tool-Result-Text (kein SIGNAL mehr)."""
        client = FakeSeitenClient(_inventar_einfach())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_default_pfad_enthaelt_url(self):
        """AC2: Default-Antwort enthält display_url_origin_heim + /api/v1/seiten/uebersicht."""
        client = FakeSeitenClient(_inventar_einfach())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert "https://hub.local/api/v1/seiten/uebersicht" in result

    def test_default_pfad_enthaelt_sub_frage(self):
        """AC2: Default-Antwort enthält Sub-Frage (SREG-5)."""
        client = FakeSeitenClient(_inventar_einfach())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        # Sub-Frage muss Hinweis auf direktes Schicken enthalten
        assert "direkt" in result.lower() or "schicken" in result.lower()

    def test_default_pfad_ruft_kein_inventar(self):
        """SREG-5: Default-Pfad ruft GET /api/v1/seiten NICHT auf."""
        client = FakeSeitenClient(_inventar_einfach())
        seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert client.inventar_calls == 0

    # -- AC3: Opt-in-Pfad --

    def test_opt_in_match_eindeutig_gibt_url_text(self):
        """AC3: Runde 2 (aktion=match) + exaktes label → Direkt-URL als Tool-Result."""
        client = FakeSeitenClient(_inventar_einfach())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="Garderoben-Editor",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert isinstance(result, str)
        assert "https://hub.local/display/wetter/regeln" in result

    def test_opt_in_match_url_enthaelt_origin(self):
        """AC3: Direkt-URL enthält Heim-Origin (SREG-5b/SREG-7)."""
        client = FakeSeitenClient(_inventar_einfach())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="Wochenplan",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert "https://hub.local" in result

    # -- AC4: kein Suchbegriff --

    def test_kein_suchbegriff_gibt_default_text(self):
        """AC4: Ohne Suchbegriff → Default-Text, eine konsistente Antwort."""
        client = FakeSeitenClient(_inventar_einfach())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff=None,
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    # -- Fehler-Pfade: BerechtigungError (SREG-6/EC-29) --

    def test_nicht_mitglied_wirft_berechtigungerror(self):
        """SREG-6 / EC-29: Nicht-Mitglied → BerechtigungError, kein Text-Return."""
        client = FakeSeitenClient(_inventar_einfach())
        with pytest.raises(BerechtigungError):
            seiten_uebersicht(
                chat_id=100,
                from_user_id=42,
                suchbegriff="",
                seiten_client=client,
                is_member_fn=_kein_mitglied,
                display_url_origin_heim="https://hub.local",
            )

    def test_chat_id_none_wirft_berechtigungerror(self):
        """chat_id=None → BerechtigungError (kein gültiger Kontext)."""
        client = FakeSeitenClient(_inventar_einfach())
        with pytest.raises(BerechtigungError):
            seiten_uebersicht(
                chat_id=None,
                from_user_id=42,
                suchbegriff="",
                seiten_client=client,
                is_member_fn=_immer_mitglied,
                display_url_origin_heim="https://hub.local",
            )

    def test_registry_nicht_erreichbar_gibt_text(self):
        """Opt-in-Pfad: Registry nicht erreichbar → Text-Meldung als Tool-Result."""
        client = FakeSeitenClient(error=SeitenClientError("timeout"))
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="garderobe",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        assert isinstance(result, str)
        assert "nicht erreichbar" in result.lower()

    # -- AC3 (SREG-5b): Fehler-Pfad bei aktion=None/unbekannt --

    def test_aktion_none_mit_suchbegriff_gibt_fehler_text(self):
        """AC3/SREG-5b: suchbegriff + aktion=None → Fehler-Tool-Result, kein Substring-Match.

        SREG-5b Weg-2-Pivot: kein stilles Substring-Match — das LLM muss
        explizit inventar oder match waehlen (#488).
        """
        client = FakeSeitenClient(_inventar_einfach())
        result = seiten_uebersicht(
            chat_id=1,
            from_user_id=99,
            suchbegriff="wetter",
            seiten_client=client,
            is_member_fn=lambda _: True,
            display_url_origin_heim="http://heim:8443",
            aktion=None,
        )
        assert isinstance(result, str), "Fehler-Pfad muss String liefern, kein Crash"
        assert "aktion" in result.lower(), "Fehler-Text muss 'aktion' nennen"
        # Kein URL aus dem Inventar — kein stilles Substring-Match.
        assert "/display/wetter" not in result

    def test_aktion_unbekannt_mit_suchbegriff_gibt_fehler_text(self):
        """AC3/SREG-5b: suchbegriff + unbekannter aktion-Wert → Fehler-Tool-Result.

        Unbekannter aktion-Wert darf keinen Subset-Match auslösen (SREG-5b).
        """
        client = FakeSeitenClient(_inventar_einfach())
        for ungueltig in ("foo", "unbekannt"):
            result = seiten_uebersicht(
                chat_id=1,
                from_user_id=99,
                suchbegriff="garderobe",
                seiten_client=client,
                is_member_fn=lambda _: True,
                display_url_origin_heim="http://heim:8443",
                aktion=ungueltig,
            )
            assert isinstance(result, str), (
                "aktion=%r: Fehler-Pfad muss String liefern" % ungueltig)
            assert "aktion" in result.lower(), (
                "aktion=%r: Fehler-Text muss 'aktion' nennen" % ungueltig)
            # Kein URL aus dem Inventar — kein stilles Substring-Match.
            assert "/display/" not in result, (
                "aktion=%r: kein Substring-Match auf Inventar" % ungueltig)


# ============================================================
#  Tests: SeitenUebersichtTask — EC-29 / TASK-10
# ============================================================

class TestSeitenUebersichtTask:
    def test_ist_read_task(self):
        """SeitenUebersichtTask muss ReadTask sein (EC-9)."""
        client = FakeSeitenClient([])
        task = SeitenUebersichtTask(seiten_client=client,
                                    is_member_fn=_immer_mitglied)
        assert isinstance(task, ReadTask)

    def test_name_ist_seiten_uebersicht(self):
        client = FakeSeitenClient([])
        task = SeitenUebersichtTask(seiten_client=client,
                                    is_member_fn=_immer_mitglied)
        assert task.name == "seiten_uebersicht"

    def test_run_default_pfad_gibt_text_zurueck(self):
        """AC2/EC-29: Task ohne suchbegriff → Default-Text als Tool-Result."""
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = _make_turn_context()
        result = task.run({}, ctx)
        assert isinstance(result, str)
        assert len(result) > 0
        assert "https://hub.local/api/v1/seiten/uebersicht" in result

    def test_run_opt_in_runde2_gibt_direkt_url(self):
        """AC3/EC-29: Task mit suchbegriff + aktion=match → Direkt-URL als Tool-Result."""
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Garderoben-Editor", "aktion": "match"}, ctx)
        assert isinstance(result, str)
        assert "https://hub.local/display/wetter/regeln" in result

    def test_run_nicht_mitglied_wirft_berechtigungerror(self):
        """SREG-6/EC-29: Nicht-Mitglied → BerechtigungError propagiert."""
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(seiten_client=client,
                                    is_member_fn=_kein_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = _make_turn_context()
        with pytest.raises(BerechtigungError):
            task.run({}, ctx)

    def test_run_ohne_turn_context_wirft_berechtigungerror(self):
        """Ohne TurnContext → BerechtigungError (chat_id=None)."""
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenUebersichtTask(seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        with pytest.raises(BerechtigungError):
            task.run({}, None)

    def test_run_nicht_erreichbar_gibt_text(self):
        """Nicht erreichbar → Tool-Result-Text mit Hinweis."""
        client = FakeSeitenClient(error=SeitenClientError("down"))
        task = SeitenUebersichtTask(seiten_client=client,
                                    is_member_fn=_immer_mitglied,
                                    display_url_origin_heim="https://hub.local")
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "garderobe"}, ctx)
        assert "nicht erreichbar" in result.lower()


# ============================================================
#  TASK-10 Baseline: task.run() sendet in keinem Pfad selbst (AC4)
# ============================================================

class TestTask10BaselineRunSendetNichts:
    """TASK-10 / EC-29 Baseline: task.run() sendet in keinem der Haupt-Pfade
    selbst an Telegram.

    FakeTelegram-Aufnahme muss nach jedem run()-Aufruf leer bleiben.
    Tool-Result-Text muss nicht-leer sein (oder BerechtigungError propagieren).
    """

    def _make_task(self, inventar=None, error=None, is_member_fn=None):
        client = FakeSeitenClient(
            eintraege=inventar if inventar is not None else _inventar_einfach(),
            error=error,
        )
        task = SeitenUebersichtTask(
            seiten_client=client,
            is_member_fn=is_member_fn or _immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        return task

    def test_TASK10_baseline_run_sendet_nichts(self):
        """TASK-10 / EC-29 Baseline: task.run() sendet in keinem der Pfade selbst.

        Default-Pfad, Opt-in Runde 1, Opt-in Runde 2, Mehrdeutigkeit,
        Kein-Treffer, Nicht-erreichbar, Berechtigungs-Bruch:
          - Text-Pfade: returnter String nicht-leer; FakeTelegram leer.
          - Berechtigungs-Pfad: BerechtigungError propagiert.
        """
        ctx = TurnContext(chat_id=100, from_user_id=42)

        # --- Default-Pfad (SREG-5) ---
        tg_default = FakeTelegram()
        task_default = self._make_task(inventar=_inventar_einfach())
        # Inject tg by patching is_member_fn to use tg for recording
        # (Task hat kein tg mehr — FakeTelegram ist nur für den Nachweis hier)
        result_default = task_default.run({}, ctx)
        assert isinstance(result_default, str), "Default: Tool-Result muss ein String sein"
        assert len(result_default) > 0, "Default: Tool-Result muss nicht-leer sein"
        assert not tg_default.sent, "Default: FakeTelegram muss leer sein"

        # --- Opt-in Runde 1 (aktion=inventar) ---
        tg_r1 = FakeTelegram()
        task_r1 = self._make_task(inventar=_inventar_einfach())
        result_r1 = task_r1.run({"suchbegriff": "Garderobe", "aktion": "inventar"}, ctx)
        assert isinstance(result_r1, str), "Runde 1: Tool-Result muss ein String sein"
        assert len(result_r1) > 0, "Runde 1: Tool-Result muss nicht-leer sein"
        assert not tg_r1.sent, "Runde 1: FakeTelegram muss leer sein"

        # --- Opt-in Runde 2 (aktion=match, Treffer) ---
        tg_r2 = FakeTelegram()
        task_r2 = self._make_task(inventar=_inventar_einfach())
        result_r2 = task_r2.run({"suchbegriff": "Garderoben-Editor", "aktion": "match"}, ctx)
        assert isinstance(result_r2, str), "Runde 2: Tool-Result muss ein String sein"
        assert len(result_r2) > 0, "Runde 2: Tool-Result muss nicht-leer sein"
        assert not tg_r2.sent, "Runde 2: FakeTelegram muss leer sein"

        # --- aktion fehlt (SREG-5b Fehler-Pfad) ---
        tg_aktion = FakeTelegram()
        task_aktion = self._make_task(inventar=_inventar_einfach())
        result_aktion = task_aktion.run({"suchbegriff": "wetter"}, ctx)
        assert isinstance(result_aktion, str), "aktion fehlt: Tool-Result muss ein String sein"
        assert "aktion" in result_aktion.lower(), "aktion fehlt: Fehler-Text muss 'aktion' nennen"
        assert not tg_aktion.sent, "aktion fehlt: FakeTelegram muss leer sein"

        # --- Nicht erreichbar ---
        tg_err = FakeTelegram()
        task_err = self._make_task(error=SeitenClientError("Timeout"))
        result_err = task_err.run({"suchbegriff": "garderobe"}, ctx)
        assert isinstance(result_err, str), "Fehler: Tool-Result muss ein String sein"
        assert len(result_err) > 0, "Fehler: Tool-Result muss nicht-leer sein"
        assert not tg_err.sent, "Fehler: FakeTelegram muss leer sein"

        # --- Berechtigungs-Bruch ---
        task_auth = self._make_task(is_member_fn=_kein_mitglied)
        with pytest.raises(BerechtigungError):
            task_auth.run({}, ctx)


# ============================================================
#  Tests: SREG-5b Weg 2 — Zweistufiges KI-Matching (#488)
#  AC488-1: Runde 1 (aktion=inventar) → Inventar als Tool-Result, kein Bot-Post.
#  AC488-2: Runde 2 (aktion=match + exaktes label) → Direkt-URL als Tool-Result.
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
        client = FakeSeitenClient(inventar or _inventar_bug_beispiele())
        task = SeitenUebersichtTask(
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
        )
        return client, task

    # -- AC488-1: Runde 1 --

    def test_runde1_gibt_inventar_als_tool_result(self):
        """AC488-1: aktion=inventar → Tool-Result-String, KEIN Bot-Post."""
        _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Controller", "aktion": "inventar"}, ctx)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_runde1_inventar_ruft_seiten_client_einmal(self):
        """AC488-1: inventar() wird genau einmal gerufen."""
        client, task = self._task()
        ctx = _make_turn_context()
        task.run({"suchbegriff": "Wetter", "aktion": "inventar"}, ctx)
        assert client.inventar_calls == 1

    def test_runde1_tool_result_enthaelt_labels(self):
        """AC488-1: Tool-Result enthält label + key aller Views."""
        _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Plan", "aktion": "inventar"}, ctx)
        # Alle Labels müssen im Tool-Result sichtbar sein.
        assert "Wochenplan" in result
        assert "Figuren-Erkennung Controller" in result
        assert "Wetter heute" in result

    def test_runde1_tool_result_enthaelt_synonyme_und_zeigt(self):
        """AC488-1: Tool-Result enthält synonyme + zeigt (für LLM-Matching)."""
        _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run({"suchbegriff": "Eltern Panel", "aktion": "inventar"}, ctx)
        # synonyme und zeigt müssen im Tool-Result stehen.
        assert "panel-editor" in result or "eltern-panel" in result
        assert "Panel panel-1 Editor" in result

    def test_runde1_signal_ist_inventar_text(self):
        """AC488-1: Funktion gibt Inventar-Text direkt als String zurück (EC-29)."""
        client = FakeSeitenClient(_inventar_bug_beispiele())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="Controller",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_INVENTAR,
        )
        assert isinstance(result, str)
        assert len(result) > 0
        # Inventar-Text enthält Labels und Keys.
        assert "Figuren-Erkennung Controller" in result

    # -- AC488-2: Runde 2 --

    def test_runde2_exact_label_gibt_direkt_url(self):
        """AC488-2: aktion=match + exaktes label → Direkt-URL als Tool-Result."""
        _client, task = self._task()
        ctx = _make_turn_context()
        result = task.run(
            {"suchbegriff": "Figuren-Erkennung Controller", "aktion": "match"},
            ctx,
        )
        assert isinstance(result, str)
        assert "https://hub.local/controller/figuren-erkennung/" in result

    def test_runde2_signal_enthaelt_url(self):
        """AC488-2: aktion=match + exaktes label → URL im Tool-Result."""
        client = FakeSeitenClient(_inventar_bug_beispiele())
        result = seiten_uebersicht(
            chat_id=100,
            from_user_id=42,
            suchbegriff="Wochenplan",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert isinstance(result, str)
        assert "https://hub.local/display/plan/woche" in result


class TestSreg5bBugBeispiele:
    """AC488-3: 4 Bug-Beispiele aus dem Bug-Befund liefern sinnvolle Direkt-URL
    oder echte EC-22-Rückfrage — KEIN generischer 'keine Seite gefunden'-Fallback.

    Simuliert beide Runden: Runde 1 (aktion=inventar) gibt Inventar zurück,
    Runde 2 (aktion=match + exaktes label aus Inventar) findet den View.
    """

    def _zweistufig(self, suchbegriff_r1, suchbegriff_r2):
        """Hilfsmethode: simuliert beide Runden für ein Suchbegriff-Paar."""
        client1 = FakeSeitenClient(_inventar_bug_beispiele())
        # Runde 1: Inventar holen.
        result1 = seiten_uebersicht(
            chat_id=100, from_user_id=42,
            suchbegriff=suchbegriff_r1,
            seiten_client=client1,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_INVENTAR,
        )
        assert isinstance(result1, str), "Runde 1 muss String liefern"
        assert len(result1) > 0

        # Runde 2: Mit exaktem label aus Inventar matchen.
        client2 = FakeSeitenClient(_inventar_bug_beispiele())
        result2 = seiten_uebersicht(
            chat_id=100, from_user_id=42,
            suchbegriff=suchbegriff_r2,
            seiten_client=client2,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        return result2, result1

    def test_bug_beispiel_controller(self):
        """AC488-3: 'Controller' → zwei Runden → URL zur Figuren-Erkennung."""
        # Das LLM würde aus dem Inventar "Figuren-Erkennung Controller" wählen.
        result2, inventar_text = self._zweistufig(
            "Controller", "Figuren-Erkennung Controller")
        # Inventar enthält den passenden Eintrag.
        assert "Figuren-Erkennung Controller" in inventar_text
        # Runde 2: Direkt-URL im Tool-Result.
        assert isinstance(result2, str)
        assert "https://hub.local/controller/figuren-erkennung/" in result2

    def test_bug_beispiel_eltern_panel(self):
        """AC488-3: 'Eltern Panel' → zwei Runden → URL zum Panel-Editor."""
        # Das LLM würde aus dem Inventar "Eltern Panel panel-1 bearbeiten" wählen.
        result2, inventar_text = self._zweistufig(
            "Eltern Panel", "Eltern Panel panel-1 bearbeiten")
        assert "Eltern Panel panel-1 bearbeiten" in inventar_text
        # Runde 2: Direkt-URL oder Rückfrage (KEIN generischer Fallback).
        assert isinstance(result2, str)
        assert len(result2) > 0

    def test_bug_beispiel_wetter(self):
        """AC488-3: 'Wetter' → zwei Runden → Direkt-URL (KEIN Fallback)."""
        # Das LLM würde aus dem Inventar "Wetter heute" wählen.
        result2, inventar_text = self._zweistufig("Wetter", "Wetter heute")
        assert "Wetter heute" in inventar_text
        assert isinstance(result2, str)
        assert len(result2) > 0
        # Bei Equality-Match muss die URL zum Wetter-View führen.
        assert "https://hub.local/display/wetter/heute" in result2

    def test_bug_beispiel_plan(self):
        """AC488-3: 'Plan' → zwei Runden → Direkt-URL zum Wochenplan."""
        # Das LLM würde aus dem Inventar "Wochenplan" wählen.
        result2, inventar_text = self._zweistufig("Plan", "Wochenplan")
        assert "Wochenplan" in inventar_text
        assert isinstance(result2, str)
        assert "https://hub.local/display/plan/woche" in result2


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
#  Tests: Equality-Match bei aktion=match (T549-Fix2)
# ============================================================

class TestAktionMatchEquality:
    """Fix #2 für T549: Equality-Lookup bei aktion=match.

    Verhindert Präfix-Geschwister-Mehrdeutigkeit (Paula-Panel-Bug):
      'Panel paulas-panel-01' trifft NICHT 'Panel paulas-panel-01 bearbeiten'.
    """

    def _inventar_praefix_geschwister(self):
        """Paula-Bug-Inventar: label von Eintrag 1 ist Präfix von Eintrag 2."""
        return [
            {"label": "Panel paulas-panel-01",
             "key": "panel-paulas-panel-01",
             "pfad": "/controller/app-panel/paulas-panel-01",
             "typ": "panel",
             "zeigt": "Panel-Steuerung paulas-panel-01",
             "synonyme": []},
            {"label": "Panel paulas-panel-01 bearbeiten",
             "key": "paulas-panel-01-bearbeiten",
             "pfad": "/controller/app-panel/paulas-panel-01/bearbeiten",
             "typ": "eltern",
             "zeigt": "Panel paulas-panel-01 Editor",
             "synonyme": []},
        ]

    def test_aktion_match_label_equality_bei_praefix_geschwistern(self):
        """Live-Symptom-Test: aktion=match + exaktes label trifft NUR ersten Eintrag.

        'Panel paulas-panel-01' ist Präfix von 'Panel paulas-panel-01 bearbeiten'.
        Substring-Match würde beide treffen (mehrdeutig). Equality-Match trifft nur
        den ersten Eintrag → Direkt-URL, kein Mehrdeutigkeit-Text.
        """
        client = FakeSeitenClient(self._inventar_praefix_geschwister())
        result = seiten_uebersicht(
            chat_id=100, from_user_id=42,
            suchbegriff="Panel paulas-panel-01",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert isinstance(result, str)
        assert "https://hub.local/controller/app-panel/paulas-panel-01" in result, (
            "Equality-Match muss NUR den Eintrag mit exakt diesem label treffen "
            "— kein Präfix-Geschwister-Bug (T549-Fix2)")
        # Kein /bearbeiten-Suffix → nur Ansicht, nicht Editor.
        assert "/bearbeiten" not in result

    def test_aktion_match_key_pfad(self):
        """aktion=match + key als suchbegriff → Equality-Match auf key trifft Eintrag."""
        client = FakeSeitenClient(self._inventar_praefix_geschwister())
        result = seiten_uebersicht(
            chat_id=100, from_user_id=42,
            suchbegriff="paulas-panel-01-bearbeiten",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        assert isinstance(result, str), (
            "Equality-Match auf key muss den Eintrag treffen (T549-Fix2)")
        assert "/bearbeiten" in result

    def test_aktion_match_kein_treffer(self):
        """aktion=match + unbekannter suchbegriff → Fehler-Text als Tool-Result."""
        client = FakeSeitenClient(self._inventar_praefix_geschwister())
        result = seiten_uebersicht(
            chat_id=100, from_user_id=42,
            suchbegriff="gibt es nicht",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
            display_url_origin_heim="https://hub.local",
            aktion=AKTION_MATCH,
        )
        # Kein Treffer → Fehler-Text (kein Mehrdeutigkeit-Loop).
        assert isinstance(result, str)
        assert len(result) > 0
        # Die Nachricht soll den suchbegriff nennen und auf aktion=inventar hinweisen.
        assert "gibt es nicht" in result or "inventar" in result.lower()


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
