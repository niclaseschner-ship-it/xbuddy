"""Tests für den Aufgaben-Katalog-Rahmen — EC-8/EC-9/EC-10 (Refs #27, #63).

Hook-Lifecycle (EC-21, #140) sitzt am Ende: ohne Hooks bleibt das Verhalten
identisch zur Pre-#140-Welt; mit Hooks wird die Schreib-Aufgabe nicht
zurueckgerollt, und mehrere Fehler werden zu EINER Warnung zusammengefasst."""

import pytest
from fakes import FakeReadTask, FakeTelegram, FakeWriteTask
from hooks import HookContext, HookFailure, HookSuccess
from model import READ, WRITE
from tasks import (
    PRESENTATION_INLINE_BUTTON,
    PRESENTATION_INLINE_BUTTONS,
    PRESENTATION_WEBAPP_LINK,
    Catalog,
    ReadTask,
    TurnContext,
    WriteTaskResult,
    _make_is_member_fn,
    build_catalog,
    is_from_private_chat,
    render_form_b,
)


def test_EC_8_register_and_get():
    cat = Catalog()
    task = FakeReadTask(name="wetter")
    cat.register(task)
    assert cat.get("wetter") is task


def test_EC_8_unknown_task_returns_none():
    """Eine nicht registrierte Aufgabe ist nicht im Katalog."""
    assert Catalog().get("gibt_es_nicht") is None


def test_EC_8_duplicate_registration_is_rejected():
    cat = Catalog()
    cat.register(FakeReadTask(name="wetter"))
    with pytest.raises(ValueError):
        cat.register(FakeReadTask(name="wetter"))


def test_EC_8_task_defs_are_provider_neutral():
    cat = Catalog()
    cat.register(FakeReadTask(name="lesen"))
    cat.register(FakeWriteTask(name="schreiben"))
    defs = {d.name: d for d in cat.task_defs()}
    assert defs["lesen"].kind == READ
    assert defs["schreiben"].kind == WRITE


def test_EC_9_read_task_kind_is_read():
    assert FakeReadTask().kind == READ


def test_EC_10_write_task_kind_is_write():
    assert FakeWriteTask().kind == WRITE


def test_RAT31_E1_build_catalog_ca_pem_path_signature_still_works():
    """RAT-31 E1 (#1470): `build_catalog(tg, ca_pem_path)` bleibt aufrufbar,
    aber die »CA verteilen«-Aufgabe ist unter Cookie-only-hart (RAT-32)
    entfallen — `ca_verteilen` erscheint nicht mehr im Katalog. `ca_pem_path`
    bleibt vestigial in der Signatur (AC4)."""
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "ca_verteilen" not in defs


# ============================================================
#  FSE-8 / TASK-9 — Foto-Senden-Skill als Sofort-Schreib-Aufgabe
# ============================================================

def test_FSE8_guard_beide_gesetzt_registriert():
    """FSE-8: `foto_senden` erscheint im Katalog, wenn `photo_origin_url` UND
    `family_group_chat_id_getter` gesetzt sind (AND-Guard, RZS-/TES-Linie)."""
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        photo_origin_url="http://127.0.0.1:5070",
        family_group_chat_id_getter=lambda: 200,
    )
    defs = {d.name: d for d in catalog.task_defs()}
    assert "foto_senden" in defs, "FSE-8 Guard verletzt: Aufgabe fehlt im Katalog"
    # TASK-9: Sofort-Schreib-Aufgabe läuft als ReadTask (E-FSE-1, kein Confirm).
    assert defs["foto_senden"].kind == READ, (
        "TASK-9 / E-FSE-1: foto_senden muss als ReadTask laufen")


def test_FSE8_guard_ohne_photo_origin_nicht_registriert():
    """FSE-8 Guard: ohne `photo_origin_url` → Aufgabe NICHT im Katalog."""
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        # photo_origin_url fehlt
        family_group_chat_id_getter=lambda: 200,
    )
    assert catalog.get("foto_senden") is None


def test_FSE8_guard_ohne_fgcid_nicht_registriert():
    """FSE-8 Guard: ohne `family_group_chat_id_getter` → Aufgabe NICHT im Katalog."""
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        photo_origin_url="http://127.0.0.1:5070",
        # family_group_chat_id_getter fehlt
    )
    assert catalog.get("foto_senden") is None


# ============================================================
#  EC-21 / #140 — Post-Execute-Hooks im WriteTask-Lifecycle
# ============================================================


def _success_hook(label="Plan-Buddy"):
    """Test-Hook: gibt immer HookSuccess zurueck. `consumer`-Attribut, damit
    das Framework es im Fall einer unerwarteten Exception auslesen koennte."""
    def hook(context):
        return HookSuccess(details="reloaded")
    hook.consumer = label
    return hook


def _failing_hook(label="Plan-Buddy", error="HTTP 500"):
    """Test-Hook: gibt immer HookFailure zurueck."""
    def hook(context):
        return HookFailure(consumer=label, error=error)
    hook.consumer = label
    return hook


def _explosive_hook(label="Plan-Buddy"):
    """Test-Hook: wirft. Das Framework muss das als HookFailure verpacken,
    damit die Schreib-Aufgabe nicht ueber einen schlampig geschriebenen
    Hook zurueckgerollt wird."""
    def hook(context):
        raise RuntimeError("boom")
    hook.consumer = label
    return hook


def test_EC_21_write_task_without_hooks_behaves_as_before():
    """Default-Verhalten: keine Hooks ⇒ Result enthaelt nur die Quittung,
    keine Warnung. Bestaetigt die Rueckwaerts-Kompatibilitaet (#140 macht
    nichts kaputt fuer Aufgaben, die keine Hooks deklarieren)."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="erledigt")
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert isinstance(outcome, WriteTaskResult)
    assert outcome.reply == "erledigt"
    assert outcome.warning == ""
    assert outcome.hook_failures == ()
    assert outcome.combined_text() == "erledigt"
    # Die eigentliche Aufgabe ist genau einmal gelaufen.
    assert len(task.execute_calls) == 1


def test_EC_21_successful_hook_runs_after_execute():
    """Erfolgs-Pfad: execute() laeuft, dann der Hook, dann das Framework
    liefert die Quittung ohne Warnung."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="erledigt")
    task.post_execute_hooks = (_success_hook("Plan-Buddy"),)
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert outcome.reply == "erledigt"
    assert outcome.warning == ""
    assert outcome.hook_failures == ()


def test_EC_21_failed_hook_does_NOT_rollback_the_write():
    """Kern-Anforderung EC-21: ein Hook-Fehler rollt die Schreib-Aufgabe
    NICHT zurueck — die Aenderung ist durch, die Familie bekommt eine
    Warnung mit dem ausgefallenen Konsumenten."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="Kalender verbunden")
    task.post_execute_hooks = (_failing_hook("Plan-Buddy"),)
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    # execute() ist gelaufen — die Quittung ist DA, kein Rollback.
    assert outcome.reply == "Kalender verbunden"
    assert len(task.execute_calls) == 1
    # Warnung erwaehnt den ausgefallenen Konsumenten.
    assert "Plan-Buddy" in outcome.warning
    # Hook-Failures sind zusaetzlich strukturiert verfuegbar (Logging usw).
    assert len(outcome.hook_failures) == 1
    assert outcome.hook_failures[0].consumer == "Plan-Buddy"
    # combined_text bringt beide Teile in einer Familien-tauglichen Antwort.
    combined = outcome.combined_text()
    assert "Kalender verbunden" in combined
    assert "Plan-Buddy" in combined


def test_EC_21_multiple_failed_hooks_become_ONE_warning():
    """Kern-Anforderung EC-21: mehrere fehlgeschlagene Hooks einer Aufgabe
    werden in EINER zusammengefassten Warnung gemeldet, nicht je Hook."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="durch")
    task.post_execute_hooks = (
        _failing_hook("Plan-Buddy", error="HTTP 500"),
        _failing_hook("Router", error="nicht erreichbar"),
    )
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    # Eine Warnung, beide Konsumenten benannt.
    assert outcome.warning.count("Hinweis") == 1
    assert "Plan-Buddy" in outcome.warning
    assert "Router" in outcome.warning
    # Strukturierte Liste fuer Logging-Zwecke ist vollstaendig.
    assert len(outcome.hook_failures) == 2


def test_EC_21_hook_exception_is_captured_as_failure_not_propagated():
    """EC-21: ein Hook, der (gegen Konvention) wirft, darf die
    Schreib-Aufgabe nicht zerlegen. Das Framework faengt die Exception
    und verpackt sie als HookFailure."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="durch")
    task.post_execute_hooks = (_explosive_hook("Plan-Buddy"),)
    catalog.register(task)
    # Wirft NICHT.
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert outcome.reply == "durch"
    assert len(outcome.hook_failures) == 1
    assert outcome.hook_failures[0].consumer == "Plan-Buddy"


def test_EC_21_execute_exception_propagates_no_hooks_run():
    """Wenn die Aufgabe selbst wirft, wird KEIN Hook aufgerufen (es gibt
    keinen erfolgreichen Zustand, der nachgezogen werden muesste)."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result=RuntimeError("nope"))
    hook_calls = []

    def tracking_hook(context):
        hook_calls.append(context)
        return HookSuccess(details="reloaded")

    tracking_hook.consumer = "Plan-Buddy"
    task.post_execute_hooks = (tracking_hook,)
    catalog.register(task)
    with pytest.raises(RuntimeError):
        catalog.execute_write_task(task, {}, turn_context=None)
    assert hook_calls == []


def test_159_async_writetask_skips_inline_hook_iteration():
    """Refs #159: Markiert sich eine WriteTask als ``is_async=True``, kehrt
    ``execute()`` mit einer Privatchat-Kurzquittung zurueck — der eigentliche
    Schreib-Vorgang laeuft erst im Worker-Thread. Das Framework darf in dem
    Fall die Hooks NICHT inline iterieren (sie wuerden den Konsumenten
    reloaden, bevor das echte Schreiben durch ist — Live-Beleg 2026-05-26).
    Die Hooks sind dann Selbstaufgabe des Workers (siehe
    ``PrivateChatSession.start(post_execute_hooks=...)``)."""
    catalog = Catalog()
    task = FakeWriteTask(name="async_task", result="Worker gestartet")
    task.is_async = True
    hook_calls = []

    def tracking_hook(context):
        hook_calls.append(context)
        return HookSuccess()

    tracking_hook.consumer = "Plan-Buddy"
    task.post_execute_hooks = (tracking_hook,)
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert outcome.reply == "Worker gestartet"
    # Async-Pfad: Hook wird NICHT inline gerufen (Worker kuemmert sich).
    assert hook_calls == []
    # Keine Inline-Warnung — die kommt ggf. direkt vom Worker via on_warning.
    assert outcome.warning == ""
    assert outcome.hook_failures == ()


def test_EC_21_hook_context_carries_task_name_and_turn_context():
    """Der `HookContext` reicht task_name und turn_context an den Hook —
    das macht den Hook stateless (kein `self`, der Kontext kommt
    von aussen)."""
    catalog = Catalog()
    task = FakeWriteTask(name="kalender_verbinden", result="durch")
    captured = []

    def capturing_hook(context):
        captured.append(context)
        return HookSuccess()

    capturing_hook.consumer = "Plan-Buddy"
    task.post_execute_hooks = (capturing_hook,)
    catalog.register(task)
    sentinel_turn_context = object()
    catalog.execute_write_task(task, {}, turn_context=sentinel_turn_context)
    assert len(captured) == 1
    assert isinstance(captured[0], HookContext)
    assert captured[0].task_name == "kalender_verbinden"
    assert captured[0].turn_context is sentinel_turn_context


# ============================================================
#  Refs #157 — is_from_private_chat-Helfer
# ============================================================

def test_157_is_from_private_chat_true_when_chat_id_equals_private_chat_id():
    """Refs #157: Konvention aus `TurnContext` — Privatchat-Anfrage hat
    `chat_id == private_chat_id` (s. main._user_message_from-Bau)."""
    tc = TurnContext(chat_id=7, from_user_id=7, private_chat_id=7)
    assert is_from_private_chat(tc) is True


def test_157_is_from_private_chat_false_for_group_request():
    """Refs #157: Gruppen-Anfrage — chat_id ist die Gruppe, private_chat_id
    die User-ID; sie unterscheiden sich."""
    tc = TurnContext(chat_id="-100", from_user_id=7, private_chat_id=7)
    assert is_from_private_chat(tc) is False


def test_157_is_from_private_chat_false_without_private_chat_id():
    """Refs #157: Ohne `private_chat_id` (z. B. ein degenerierter Kontext)
    gilt die Anfrage nicht als „aus dem Privatchat" — defensiver Default."""
    tc = TurnContext(chat_id="-100", from_user_id=None, private_chat_id=None)
    assert is_from_private_chat(tc) is False


# ============================================================
#  TASK-7 Refactor — _make_is_member_fn Factory
# ============================================================

def test_TASK7_make_is_member_fn_returns_true_for_member():
    """TASK-7: _make_is_member_fn erzeugt eine Closure, die gegen die
    Familien-Gruppe prüft. Für ein Mitglied mit Status 'member' gibt sie True."""
    tg = FakeTelegram()

    # Fake get_chat_member: gibt ein Member-Dict zurück
    def _fake_get_chat_member(fgcid, user_id):
        return {"status": "member"}

    tg.get_chat_member = _fake_get_chat_member

    # Getter gibt die feste FGCID zurück
    def _fgcid_getter():
        return 200

    is_member_fn = _make_is_member_fn(tg, _fgcid_getter)
    assert is_member_fn(user_id=7) is True


def test_TASK7_make_is_member_fn_returns_false_for_non_member():
    """TASK-7: Für einen Nicht-Mitglied (status='left') gibt die Closure False."""
    tg = FakeTelegram()

    def _fake_get_chat_member(fgcid, user_id):
        return {"status": "left"}

    tg.get_chat_member = _fake_get_chat_member

    def _fgcid_getter():
        return 200

    is_member_fn = _make_is_member_fn(tg, _fgcid_getter)
    assert is_member_fn(user_id=7) is False


def test_TASK7_make_is_member_fn_late_evaluation_of_fgcid():
    """TASK-7 Kern-Anforderung: fgcid_getter wird SPÄT evaluiert, nicht
    beim Bau dieser Factory — und die Closure nutzt den jeweils aktuellen
    Wert des Getters, nicht einen eingefrorenen Snapshot.

    Zweiphasige Probe:
    - Phase A: fgcid=100 → Fake gibt Member-Dict → True.
    - Phase B: fgcid=-1  → Fake gibt None (unbekannte Gruppe) → False.
    Damit ist bewiesen, dass die fgcid_getter-Rückgabe das Member-Ergebnis
    steuert — echte Späte-Evaluierung End-to-End (TASK-7)."""
    tg = FakeTelegram()

    # Fake get_chat_member: gibt Member-Dict nur für die bekannte Gruppe 100;
    # bei anderen chat_ids (z.B. -1) gibt es None zurück.
    def _fake_get_chat_member(fgcid, user_id):
        if fgcid == 100:
            return {"status": "member"}
        return None

    tg.get_chat_member = _fake_get_chat_member

    fgcid_values = [100]

    def _fgcid_getter():
        return fgcid_values[0]

    is_member_fn = _make_is_member_fn(tg, _fgcid_getter)

    # Phase A: fgcid=100 → user ist Mitglied der Gruppe 100 → True
    assert is_member_fn(user_id=7) is True

    # Phase B: fgcid auf -1 ändern — nachfolgender Call nutzt neuen Wert
    fgcid_values[0] = -1
    assert is_member_fn(user_id=7) is False, (
        "Späte Evaluierung: nach Änderung von fgcid_getter muss is_member_fn "
        "den neuen fgcid-Wert nutzen und False liefern."
    )


# ============================================================
#  TAB-12 / #1262 — Foto-Analyse-Adapter im build_catalog-Live-Pfad
# ============================================================

def test_TAB1262_foto_analyse_provider_eingesteckt():
    """TAB-12 / #1262 — Live-Pfad-Probe:
    build_catalog baut den TermineAusBildTask mit dem FotoAnalyseProvider
    (tools.llm-Adapter, Foto-Slot). Die frühere multimodal_provider-Auswahl
    (Mistral vs. Claude im build_catalog, Legacy _multimodal) entfiel mit #1262
    — der Anbieter kommt jetzt aus dem Zugangsdaten-Foto-Slot über get_singleshot;
    multimodal_model wird an FotoAnalyseProvider(model=...) durchgereicht.
    """
    import skills.foto_analyse as fa_mod
    import skills.termine_aus_bild_task as tab_mod

    captured = []

    class _CapturingTermineAusBildTask(ReadTask):
        """Ersetzt TermineAusBildTask — zeichnet den übergebenen Adapter auf."""
        name = "termine_aus_bild"

        def __init__(self, tg, multimodal_provider, plan_client,
                     sessions, family_group_chat_id_getter, is_member_fn):
            captured.append(multimodal_provider)

        def execute(self, args, turn_context):
            return ""

    class _FakeFotoAnalyseProvider:
        """Baubarer Foto-Analyse-Adapter (Foto-Slot vorhanden)."""

        def __init__(self, model=""):
            self.model = model

    # build_catalog importiert lazy: `from skills.foto_analyse import
    # FotoAnalyseProvider` und `from skills.termine_aus_bild_task import
    # TermineAusBildTask` — wir patchen beide Modul-Attribute vor dem Aufruf.
    original_tab = tab_mod.TermineAusBildTask
    original_fa = fa_mod.FotoAnalyseProvider
    tab_mod.TermineAusBildTask = _CapturingTermineAusBildTask
    fa_mod.FotoAnalyseProvider = _FakeFotoAnalyseProvider
    try:
        build_catalog(
            FakeTelegram(),
            "/instanz/rootCA.pem",
            plan_origin_url="http://127.0.0.1:5000",
            tab_sessions={},
            family_group_chat_id_getter=lambda: 200,
            provider_name="claude",
            provider_api_key="claude-key",
            provider_model="",
            multimodal_model="claude-foto-modell",
        )
    finally:
        tab_mod.TermineAusBildTask = original_tab
        fa_mod.FotoAnalyseProvider = original_fa

    assert len(captured) == 1, "TermineAusBildTask wurde nicht gebaut"
    adapter = captured[0]
    assert isinstance(adapter, _FakeFotoAnalyseProvider), (
        "TAB-12/#1262: der TAB-Guard muss den FotoAnalyseProvider durchreichen, "
        "nicht %r" % type(adapter).__name__
    )
    assert adapter.model == "claude-foto-modell", (
        "multimodal_model muss an FotoAnalyseProvider(model=...) durchgereicht werden")


def test_TAB1262_capability_error_skill_abgeschaltet():
    """TAB-12 / #1262 — negativer Pfad: wirft FotoAnalyseProvider beim Bau
    LLMCapabilityError (Foto-Slot fehlt / Capability-Mismatch), bleibt »Termine
    aus Bild« abgeschaltet (kein Katalog-Eintrag) — wie der frühere Onboarding-
    Pfad ohne Key. Der übrige Katalog bleibt unberührt.
    """
    import skills.foto_analyse as fa_mod

    def _boom(model=""):
        raise fa_mod.LLMCapabilityError("Foto-Slot fehlt (Test)")

    original_fa = fa_mod.FotoAnalyseProvider
    fa_mod.FotoAnalyseProvider = _boom
    try:
        catalog = build_catalog(
            FakeTelegram(),
            "/instanz/rootCA.pem",
            plan_origin_url="http://127.0.0.1:5000",
            tab_sessions={},
            family_group_chat_id_getter=lambda: 200,
            provider_name="claude",
            provider_api_key="claude-key",
            provider_model="",
        )
    finally:
        fa_mod.FotoAnalyseProvider = original_fa

    assert catalog.get("termine_aus_bild") is None, (
        "TAB-12/#1262: bei LLMCapabilityError darf »Termine aus Bild« NICHT "
        "im Katalog sein")
    # Übriger Katalog unberührt (Smoke: eine plan-gebundene Aufgabe bleibt
    # registriert — ca_verteilen ist seit RAT-31 E1 (#1470) entfallen).
    assert catalog.get("termine_erfragen") is not None


# ============================================================
#  TASK-10c Form (b) — render_form_b-Helper
# ============================================================

class _FakeTgForRender:
    """Minimale tg-Doppelung für render_form_b-Tests."""

    def __init__(self):
        self.inline_sent = []
        self.sent = []

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.inline_sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"message_id": 8001}

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 8002}


def test_render_form_b_inline_button_ruft_send_inline_keyboard():
    """AC1/TASK-10c: render_form_b mit inline_button → send_inline_keyboard."""
    tg = _FakeTgForRender()
    result = render_form_b(
        {"text": "Einkaufsliste", "presentation": {
            "inline_button": {"label": "🛒 öffnen", "web_app_url": "https://x.example.com/app"}
        }},
        tg, chat_id=42)

    assert len(tg.inline_sent) == 1
    assert tg.inline_sent[0]["chat_id"] == 42
    assert tg.inline_sent[0]["text"] == "Einkaufsliste"
    buttons = tg.inline_sent[0]["buttons"]
    assert buttons[0]["label"] == "🛒 öffnen"
    assert buttons[0]["web_app_url"] == "https://x.example.com/app"
    assert isinstance(result, str)
    assert "Button" in result or "gesendet" in result.lower()


def test_render_form_b_webapp_link_ruft_send_inline_keyboard():
    """AC1/AC2/TASK-10c: render_form_b mit webapp_link → send_inline_keyboard."""
    tg = _FakeTgForRender()
    result = render_form_b(
        {"text": "App öffnen", "presentation": {
            "webapp_link": {"label": "Start", "url": "https://x.example.com/wa"}
        }},
        tg, chat_id=99)

    assert len(tg.inline_sent) == 1
    assert tg.inline_sent[0]["chat_id"] == 99
    buttons = tg.inline_sent[0]["buttons"]
    assert buttons[0]["label"] == "Start"
    assert buttons[0]["web_app_url"] == "https://x.example.com/wa"
    assert isinstance(result, str)


def test_render_form_b_unbekannter_key_fallback_send_message():
    """AC2/TASK-10c: Unbekannter presentation-Schlüssel → send_message (Fallback)."""
    tg = _FakeTgForRender()
    result = render_form_b(
        {"text": "Nur Text", "presentation": {"unbekannt": {"label": "x"}}},
        tg, chat_id=7)

    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 1
    assert tg.sent[0]["text"] == "Nur Text"
    assert isinstance(result, str)


def test_render_form_b_leeres_presentation_send_message():
    """AC2/TASK-10c: Leeres presentation → send_message."""
    tg = _FakeTgForRender()
    render_form_b({"text": "Nur Text", "presentation": {}}, tg, chat_id=7)

    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 1


def test_render_form_b_quittung_ist_string():
    """AC1/TASK-10c: render_form_b gibt immer einen String zurück."""
    tg = _FakeTgForRender()
    quittung = render_form_b(
        {"text": "x", "presentation": {"inline_button": {
            "label": "y", "web_app_url": "https://z.de"
        }}},
        tg, chat_id=1)
    assert isinstance(quittung, str)
    assert len(quittung) > 0


def test_presentation_constants_sind_korrekt():
    """AC2/TASK-10c: Vokabular-Konstanten haben die erwarteten Werte."""
    assert PRESENTATION_INLINE_BUTTON == "inline_button"
    assert PRESENTATION_WEBAPP_LINK == "webapp_link"


# ============================================================
#  EZG-5/EZG-6 — render_form_b Plural-Zweig (inline_buttons)
# ============================================================

def test_render_form_b_inline_buttons_plural_beide_urls_durchgereicht():
    """EZG-5/EZG-6 Linse-7: render_form_b mit inline_buttons (Plural-Liste)
    reicht BEIDE Button-Eintraege unverändert an send_inline_keyboard weiter.

    Prueft:
    - send_inline_keyboard wird genau einmal aufgerufen.
    - Erster Button hat web_app_url (Mini-App-Pfad).
    - Zweiter Button hat url (externer Browser-Pfad, PWA-Install).
    - Beide URLs sind korrekt durchgereicht (keine Stummschaltung).
    - Quittungs-String nennt die Anzahl der Buttons.
    """
    tg = _FakeTgForRender()
    app_url = "https://buddyboard.<tailscale-id>.ts.net/essen-einkauf/"
    result = render_form_b(
        {
            "text": "Einkaufsliste",
            "presentation": {
                PRESENTATION_INLINE_BUTTONS: [
                    {"label": "Liste öffnen", "web_app_url": app_url},
                    {"label": "Im Browser öffnen", "url": app_url},
                ]
            },
        },
        tg,
        chat_id=42,
    )

    assert len(tg.inline_sent) == 1, (
        "render_form_b muss send_inline_keyboard genau einmal aufrufen."
    )
    call = tg.inline_sent[0]
    assert call["chat_id"] == 42
    assert call["text"] == "Einkaufsliste"

    buttons = call["buttons"]
    assert len(buttons) == 2, (
        "Plural-Zweig: beide Buttons müssen an send_inline_keyboard gegeben werden."
    )

    # Button 1: web_app_url (Mini-App in Telegram-WebView)
    assert buttons[0]["label"] == "Liste öffnen"
    assert buttons[0].get("web_app_url") == app_url, (
        "Button 1 muss web_app_url tragen (Mini-App-Pfad, EZG-6)."
    )
    assert "url" not in buttons[0], (
        "Button 1 darf kein url-Feld enthalten — es wäre der falsche Typ."
    )

    # Button 2: url (externer Browser, PWA-Install)
    assert buttons[1]["label"] == "Im Browser öffnen"
    assert buttons[1].get("url") == app_url, (
        "Button 2 muss url tragen (externer Browser-Link, EZG-6)."
    )
    assert "web_app_url" not in buttons[1], (
        "Button 2 darf kein web_app_url-Feld enthalten — es wäre der falsche Typ."
    )

    # Quittungs-String
    assert isinstance(result, str)
    assert "2" in result or "Buttons" in result or "Button" in result, (
        "Quittung soll Anzahl der Buttons nennen."
    )


# ============================================================
#  EC-42 — anzeige_copy: optionales Klassenattribut auf Task-Basis
# ============================================================

def test_ec42_anzeige_copy_default_none_und_gesetzt():
    """EC-42 / TASK-11: anzeige_copy ist optionales Klassenattribut (Default None)
    auf der Task-Basis; fehlt es, greift description-Fallback.

    Test-Anker: eltern-chat/tests/test_tasks.py::test_ec42_anzeige_copy_default_none_und_gesetzt
    """
    # Default: FakeReadTask setzt kein anzeige_copy → None
    task_ohne = FakeReadTask(name="ohne_anzeige_copy", result="x")
    assert getattr(task_ohne, "anzeige_copy", "MISSING") is None, (
        "EC-42: ohne explizite Deklaration muss anzeige_copy None sein"
    )

    # Unterklasse setzt anzeige_copy als Klassenattribut (analog TASK-11-Bauplan)
    class TaskMitAnzeige(ReadTask):
        anzeige_copy = "Ich kann dir die Einkaufsliste öffnen"

        def __init__(self):
            super().__init__(
                name="mit_anzeige_copy",
                description="Router-Jargon, ungeeignet für Eltern",
                parameters={"type": "object", "properties": {}})

        def run(self, arguments, turn_context):
            return "ergebnis"

    task_mit = TaskMitAnzeige()
    assert task_mit.anzeige_copy == "Ich kann dir die Einkaufsliste öffnen", (
        "EC-42: gesetztes anzeige_copy muss zurückgegeben werden"
    )
    # Fallback-Logik: anzeige_copy oder description (Leser-Muster EC-42)
    assert (task_mit.anzeige_copy or task_mit.description) == task_mit.anzeige_copy
    assert (task_ohne.anzeige_copy or task_ohne.description) == task_ohne.description

    # Additiv: bestehende Aufgaben (FakeReadTask) sind durch das neue
    # Klassenattribut NICHT gebrochen — name, description, kind unverändert.
    from model import READ
    assert task_ohne.kind == READ
    assert task_ohne.name == "ohne_anzeige_copy"
