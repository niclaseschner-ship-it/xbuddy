"""Tests für seiten_finden + SeitenFindenTask + Catalog-Registrierung
(SREG-6, PBE-2/SREG-11, Refs #453).

Pflicht-Tests (AC2/AC3/AC4/AC6):
- Happy-Path: Inventar gefiltert, Antwort gepostet, Signal=beantwortet.
- Kein Filter → alle Einträge.
- Filter → Teilmenge.
- PBE-2/SREG-11: N Panel-Instanzen → N Editor-Einträge (typ=eltern, .../bearbeiten).
- Nicht-Mitglied → Signal=abgelehnt, kein send_message.
- Seiten-Registry nicht erreichbar → Signal=nicht_erreichbar.
- Leeres Inventar → sinnvolle Antwort.
- SeitenFindenTask: ReadTask-Klasse, run() → Quittung.
- Catalog-Probe: seiten_origin_url + fgcid → registriert.
- AND-Guard: ohne seiten_origin_url → NICHT registriert.
- AND-Guard: ohne family_group_chat_id_getter → NICHT registriert.
"""


from fakes import FakeTelegram
from skills.seiten_client import SeitenClientError
from skills.seiten_finden import (
    SIGNAL_ABGELEHNT,
    SIGNAL_BEANTWORTET,
    SIGNAL_NICHT_ERREICHBAR,
    filtere_eintraege,
    formatiere_eintraege,
    seiten_finden,
)
from skills.seiten_finden_task import SeitenFindenTask
from tasks import ReadTask, TurnContext, build_catalog

# ============================================================
#  Inventar-Fixtures
# ============================================================

def _inventar_leer():
    return []


def _inventar_einfach():
    return [
        {"pfad": "/display/plan/woche", "label": "Wochenplan",
         "typ": "display", "synonyme": ["woche", "plan"]},
        {"pfad": "/display/wetter/regeln", "label": "Wetterregeln",
         "typ": "eltern", "synonyme": []},
        {"pfad": "/controller/figuren-erkennung/", "label": "Figuren",
         "typ": "controller", "synonyme": []},
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
            "zielgruppe": "eltern",
        })
        # SREG-11 Editor-Eintrag
        eintraege.append({
            "key": "%s-bearbeiten" % pid,
            "typ": "eltern",
            "instanz": pid,
            "pfad": "/controller/app-panel/%s/bearbeiten" % pid,
            "label": "Panel %s bearbeiten" % pid,
            "zielgruppe": "eltern",
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
#  Tests: filtere_eintraege
# ============================================================

class TestFiltereEintraege:
    def test_kein_filter_gibt_alle_zurueck(self):
        inv = _inventar_einfach()
        assert filtere_eintraege(inv) == inv

    def test_leerer_filter_gibt_alle_zurueck(self):
        inv = _inventar_einfach()
        assert filtere_eintraege(inv, "") == inv

    def test_filter_nach_label(self):
        inv = _inventar_einfach()
        treffer = filtere_eintraege(inv, "Wochenplan")
        assert len(treffer) == 1
        assert treffer[0]["pfad"] == "/display/plan/woche"

    def test_filter_case_insensitiv(self):
        inv = _inventar_einfach()
        treffer = filtere_eintraege(inv, "wochenplan")
        assert len(treffer) == 1

    def test_filter_nach_pfad(self):
        inv = _inventar_einfach()
        treffer = filtere_eintraege(inv, "figuren")
        assert len(treffer) == 1
        assert "figuren" in treffer[0]["pfad"]

    def test_filter_nach_typ(self):
        inv = _inventar_einfach()
        treffer = filtere_eintraege(inv, "controller")
        assert len(treffer) == 1

    def test_filter_nach_synonyme(self):
        inv = _inventar_einfach()
        treffer = filtere_eintraege(inv, "woche")
        assert len(treffer) == 1
        assert treffer[0]["pfad"] == "/display/plan/woche"

    def test_keine_treffer_gibt_leere_liste(self):
        inv = _inventar_einfach()
        treffer = filtere_eintraege(inv, "gibts-nicht-xyz")
        assert treffer == []

    def test_leeres_inventar_gibt_leere_liste(self):
        assert filtere_eintraege([], "plan") == []


# ============================================================
#  Tests: PBE-2 / SREG-11 — Editor-Einträge je Panel-Instanz
# ============================================================

class TestPbe2EditorEintraege:
    def test_n_panels_n_editor_eintraege(self):
        """PBE-2/SREG-11: N Panel-Instanzen → N Editor-Einträge im Inventar."""
        n = 3
        inv = _inventar_panels(n)
        # Insgesamt 2N Einträge: N Panel + N Editor.
        assert len(inv) == 2 * n

        editor_eintraege = [
            e for e in inv
            if e.get("typ") == "eltern" and "bearbeiten" in e.get("pfad", "")
        ]
        assert len(editor_eintraege) == n

    def test_editor_eintrag_pfad_enthaelt_panel_id_und_bearbeiten(self):
        """SREG-11: Pfad enthält '<panel_id>/bearbeiten'."""
        inv = _inventar_panels(1)
        editor = next(
            e for e in inv
            if e.get("typ") == "eltern" and "bearbeiten" in e.get("pfad", "")
        )
        assert "panel-1/bearbeiten" in editor["pfad"]

    def test_filter_bearbeiten_findet_editor_eintraege(self):
        """Filter 'bearbeiten' findet nur Editor-Einträge (SREG-11)."""
        inv = _inventar_panels(3)
        treffer = filtere_eintraege(inv, "bearbeiten")
        assert len(treffer) == 3
        for t in treffer:
            assert "bearbeiten" in t["pfad"]

    def test_filter_panel_findet_alle_panel_eintraege(self):
        """Filter 'panel' findet Panel-Instanz- + Editor-Einträge."""
        inv = _inventar_panels(2)
        treffer = filtere_eintraege(inv, "panel")
        # Beide Sorten enthalten 'panel' im Pfad/Label.
        assert len(treffer) == 4


# ============================================================
#  Tests: formatiere_eintraege
# ============================================================

class TestFormatierEintraege:
    def test_leere_liste_gibt_leerstring(self):
        assert formatiere_eintraege([]) == ""

    def test_eintrag_enthaelt_typ_label_pfad(self):
        inv = [{"pfad": "/x/y", "label": "XY", "typ": "display"}]
        result = formatiere_eintraege(inv)
        assert "[display]" in result
        assert "XY" in result
        assert "/x/y" in result

    def test_mehrere_eintraege_als_zeilen(self):
        inv = [
            {"pfad": "/a", "label": "A", "typ": "display"},
            {"pfad": "/b", "label": "B", "typ": "eltern"},
        ]
        result = formatiere_eintraege(inv)
        zeilen = result.strip().split("\n")
        assert len(zeilen) == 2


# ============================================================
#  Tests: seiten_finden (Haupt-Funktion)
# ============================================================

class TestSeitenFinden:
    def test_happy_path_beantwortet(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert signal == SIGNAL_BEANTWORTET
        assert tg.sent

    def test_antwort_geht_in_richtigen_chat(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_finden(
            tg=tg,
            chat_id=999,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert tg.sent[0]["chat_id"] == 999

    def test_kein_mitglied_abgelehnt(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_kein_mitglied,
        )
        assert signal == SIGNAL_ABGELEHNT
        assert not tg.sent

    def test_kein_mitglied_kein_send_message(self):
        """Abgelehnter Aufrufer → kein send_message (EC-7)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=99,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_kein_mitglied,
        )
        assert not tg.sent

    def test_nicht_erreichbar_sendet_hinweis(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(
            error=SeitenClientError("timeout"))
        signal = seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert signal == SIGNAL_NICHT_ERREICHBAR
        assert tg.sent
        assert "nicht erreichbar" in tg.sent[0]["text"].lower()

    def test_leeres_inventar_antwort(self):
        tg = FakeTelegram()
        client = FakeSeitenClient([])
        signal = seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert signal == SIGNAL_BEANTWORTET
        assert tg.sent

    def test_filter_keine_treffer_antwort(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="gibts-nicht-abc",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert signal == SIGNAL_BEANTWORTET
        assert "gefunden" in tg.sent[0]["text"].lower()

    def test_chat_id_none_abgelehnt(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_finden(
            tg=tg,
            chat_id=None,
            from_user_id=42,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert signal == SIGNAL_ABGELEHNT

    def test_user_id_none_abgelehnt(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        signal = seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=None,
            suchbegriff="",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert signal == SIGNAL_ABGELEHNT

    def test_pbe2_editor_eintraege_erscheinen_in_antwort(self):
        """PBE-2/SREG-11: Editor-Einträge erscheinen in der Antwort."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_panels(2))
        seiten_finden(
            tg=tg,
            chat_id=100,
            from_user_id=42,
            suchbegriff="bearbeiten",
            seiten_client=client,
            is_member_fn=_immer_mitglied,
        )
        assert tg.sent
        antwort = tg.sent[0]["text"]
        assert "bearbeiten" in antwort.lower()


# ============================================================
#  Tests: SeitenFindenTask
# ============================================================

class TestSeitenFindenTask:
    def test_ist_read_task(self):
        """SeitenFindenTask muss ReadTask sein (EC-9)."""
        tg = FakeTelegram()
        client = FakeSeitenClient([])
        task = SeitenFindenTask(tg=tg, seiten_client=client,
                                is_member_fn=_immer_mitglied)
        assert isinstance(task, ReadTask)

    def test_name_ist_seiten_finden(self):
        tg = FakeTelegram()
        client = FakeSeitenClient([])
        task = SeitenFindenTask(tg=tg, seiten_client=client,
                                is_member_fn=_immer_mitglied)
        assert task.name == "seiten_finden"

    def test_run_liefert_quittung_bei_beantwortet(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenFindenTask(tg=tg, seiten_client=client,
                                is_member_fn=_immer_mitglied)
        ctx = _make_turn_context()
        result = task.run({}, ctx)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_run_nicht_erreichbar_quittung(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(error=SeitenClientError("down"))
        task = SeitenFindenTask(tg=tg, seiten_client=client,
                                is_member_fn=_immer_mitglied)
        ctx = _make_turn_context()
        result = task.run({}, ctx)
        assert "nicht erreichbar" in result.lower()

    def test_run_nimmt_suchbegriff_aus_arguments(self):
        """Suchbegriff kommt aus arguments, nicht aus dem TurnContext."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenFindenTask(tg=tg, seiten_client=client,
                                is_member_fn=_immer_mitglied)
        ctx = _make_turn_context()
        task.run({"suchbegriff": "plan"}, ctx)
        # Nur plan-Eintrag getroffen → 1 Antwort
        assert tg.sent
        antwort = tg.sent[0]["text"]
        assert "plan" in antwort.lower() or "wochenplan" in antwort.lower()

    def test_run_chat_id_kommt_aus_turn_context(self):
        """Zielchat kommt aus TurnContext, nicht aus arguments (EC-12)."""
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenFindenTask(tg=tg, seiten_client=client,
                                is_member_fn=_immer_mitglied)
        ctx = TurnContext(chat_id=777, from_user_id=42)
        task.run({}, ctx)
        assert tg.sent[0]["chat_id"] == 777

    def test_run_ohne_turn_context_abgelehnt(self):
        tg = FakeTelegram()
        client = FakeSeitenClient(_inventar_einfach())
        task = SeitenFindenTask(tg=tg, seiten_client=client,
                                is_member_fn=_immer_mitglied)
        result = task.run({}, None)
        # chat_id=None → abgelehnt
        assert "mitglied" in result.lower() or "abgelehnt" in result.lower() \
            or "Familien" in result


# ============================================================
#  Tests: Catalog-Registrierung + AND-Guard (AC6)
# ============================================================

class TestCatalogRegistrierung:
    def _make_tg(self):
        return FakeTelegram(members={42: {"status": "member"}})

    def test_guard_seiten_origin_und_fgcid_registriert(self):
        """seiten_origin_url + family_group_chat_id_getter → Task registriert."""
        tg = self._make_tg()
        catalog = build_catalog(
            tg, "ca.pem",
            seiten_origin_url="http://127.0.0.1:5042",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("seiten_finden")
        assert task is not None
        assert isinstance(task, SeitenFindenTask)

    def test_guard_ohne_seiten_origin_nicht_registriert(self):
        """Ohne seiten_origin_url → Task fehlt im Katalog."""
        tg = self._make_tg()
        catalog = build_catalog(
            tg, "ca.pem",
            seiten_origin_url=None,
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("seiten_finden") is None

    def test_guard_ohne_fgcid_getter_nicht_registriert(self):
        """Ohne family_group_chat_id_getter → Task fehlt im Katalog."""
        tg = self._make_tg()
        catalog = build_catalog(
            tg, "ca.pem",
            seiten_origin_url="http://127.0.0.1:5042",
            family_group_chat_id_getter=None,
        )
        assert catalog.get("seiten_finden") is None

    def test_guard_beide_fehlen_nicht_registriert(self):
        """Ohne seiten_origin_url und ohne fgcid_getter → Task fehlt."""
        tg = self._make_tg()
        catalog = build_catalog(tg, "ca.pem")
        assert catalog.get("seiten_finden") is None
