"""Tests für hoerspiel_folge_erzeugen + HoerspielFolgeErzeugenTask —
HFE-1 … HFE-9 (specs/platform/hoerspiel-folge-erzeugen.md).

Abgedeckte ACs (HFE-9-Mindest-Abdeckung):
  HFE-2  — BerechtigungError für Nicht-Eltern, kein Buddy-Aufruf
  HFE-3  — leere/mehrdeutige Idee → ValueError (EC-22-Rückfrage), kein Buddy-Aufruf
  HFE-3  — gefüllte Idee → POST /folgen-vorschlag mit Idee im Body
  HFE-3  — HTTP 503 / 5xx vom Vorschlag-Endpoint → HoerspielClientError,
            kein Vorschlag-Block
  HFE-4  — Tool-Result-Text trägt Titel + Vorschau-Text + Bestätigungs-Block
            mit Voice
  HFE-4  — Intro/Outro NICHT in Vorschau-Text
  HFE-4  — Voice-Default: kein Voice-Hint → GET /config; Voice im Text → diese Voice
  HFE-5  — Confirm → execute() ruft POST /alben mit titel/text/voice/idee
  HFE-5  — erfolgreicher Build → Erfolgs-Bubble mit Display-URL via tg.send_message
  HFE-5  — HTTP 412 → Shared-Asset-Hinweis ohne erneuten Build-Versuch
  HFE-5  — HTTP 503/5xx → Fehler-Bubble ohne Build-Versuch
  HFE-7  — kein tg.send_* in propose() (Routing-Test)

Tests laufen ohne Netz (HFE-9): HoerspielClient wird durch FakeHoerspielClient
ersetzt (CLIENT-1 Transport-Stub-Naht).
"""

import pytest
from skills._errors import BerechtigungError
from skills.hoerspiel_client import HoerspielClientError
from skills.hoerspiel_folge_erzeugen import execute, propose
from skills.hoerspiel_folge_erzeugen_task import HoerspielFolgeErzeugenTask
from tasks import Proposal, TurnContext, WriteTask

# ============================================================
#  Doppelungen — FakeHoerspielClient (CLIENT-1)
# ============================================================


class FakeHoerspielClient:
    """Kontrollierter Doppelter des HoerspielClient (CLIENT-1)."""

    def __init__(self, *,
                 vorschlag_response=None,
                 vorschlag_error=None,
                 album_response=None,
                 album_error=None,
                 config_response=None,
                 config_error=None):
        self.vorschlag_calls = []   # [(idee,)]
        self.album_calls = []       # [{"titel", "text", "voice", "idee"}]
        self.config_calls = 0

        self._vorschlag_response = vorschlag_response or {
            "titel": "Der Schneesturm",
            "text": "Stigi entdeckt eine verschneite Höhle.",
            "folgen-nr-vorschlag": 42,
        }
        self._vorschlag_error = vorschlag_error
        self._album_response = album_response or {"album-id": "alb-7"}
        self._album_error = album_error
        self._config_response = config_response or {"default_voice": "shimmer"}
        self._config_error = config_error

    def folgen_vorschlag(self, idee: str) -> dict:
        self.vorschlag_calls.append(idee)
        if self._vorschlag_error is not None:
            raise self._vorschlag_error
        return dict(self._vorschlag_response)

    def album_bauen(self, titel: str, text: str,
                    voice: str, idee: str) -> dict:
        self.album_calls.append({
            "titel": titel, "text": text, "voice": voice, "idee": idee})
        if self._album_error is not None:
            raise self._album_error
        return dict(self._album_response)

    def config_lesen(self) -> dict:
        self.config_calls += 1
        if self._config_error is not None:
            raise self._config_error
        return dict(self._config_response)


class FakeTelegram:
    """Minimale Telegram-Doppelung — aufzeichnende send_message."""

    def __init__(self):
        self.sent = []   # [{chat_id, text}]

    def send_message(self, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 3000 + len(self.sent)}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _ctx(chat_id=42, from_user_id=7):
    return TurnContext(chat_id=chat_id, from_user_id=from_user_id)


def _make_task(*, hoerspiel_client=None, tg=None, is_member_fn=None,
               display_url_origin="https://app.example.com"):
    return HoerspielFolgeErzeugenTask(
        tg=tg or FakeTelegram(),
        hoerspiel_client=hoerspiel_client or FakeHoerspielClient(),
        display_url_origin=display_url_origin,
        is_member_fn=is_member_fn or _immer_mitglied,
    )


# ============================================================
#  HFE-2 — Berechtigung
# ============================================================


def test_HFE2_berechtigung_wirft_fehler_kein_buddy():
    """HFE-2: Nicht-Mitglied → BerechtigungError, kein Buddy-Aufruf."""
    client = FakeHoerspielClient()
    with pytest.raises(BerechtigungError):
        propose(
            hoerspiel_client=client,
            is_member_fn=_kein_mitglied,
            from_user_id=99,
            idee="Stigi findet einen geheimen Tunnel",
        )
    assert client.vorschlag_calls == [], "kein Buddy-Aufruf bei Nicht-Mitglied"


def test_HFE2_none_user_id_wirft_berechtigung_fehler():
    """HFE-2: from_user_id=None → BerechtigungError."""
    client = FakeHoerspielClient()
    with pytest.raises(BerechtigungError):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=None,
            idee="Eine tolle Idee",
        )
    assert client.vorschlag_calls == []


# ============================================================
#  HFE-3 — leere / mehrdeutige Idee (EC-22)
# ============================================================


def test_HFE3_leere_idee_raises_value_error():
    """HFE-3: leere Idee → ValueError (EC-22-Rückfrage), kein Buddy-Aufruf."""
    client = FakeHoerspielClient()
    with pytest.raises(ValueError, match=r"Worum|Idee|Beschreib"):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="",
        )
    assert client.vorschlag_calls == []


def test_HFE3_kurze_idee_raises_value_error():
    """HFE-3: Idee unter Mindest-Zeichen → ValueError, kein Buddy-Aufruf."""
    client = FakeHoerspielClient()
    with pytest.raises(ValueError, match=r"Worum|Idee|Beschreib"):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="Hi",
        )
    assert client.vorschlag_calls == []


def test_HFE3_gefuellte_idee_ruft_post_vorschlag():
    """HFE-3: gefüllte Idee → POST /folgen-vorschlag mit Idee im Body aufgerufen."""
    client = FakeHoerspielClient()
    idee = "Stigi findet einen geheimen Tunnel unter dem Garten"
    propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee=idee,
    )
    assert len(client.vorschlag_calls) == 1
    assert client.vorschlag_calls[0] == idee


def test_HFE3_http_503_wirft_client_error():
    """HFE-3: HTTP 503 vom Vorschlag-Endpoint → HoerspielClientError propagiert."""
    error_503 = HoerspielClientError("503", status=503)
    client = FakeHoerspielClient(vorschlag_error=error_503)
    with pytest.raises(HoerspielClientError) as exc_info:
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="Stigi und der Schneesturm",
        )
    assert exc_info.value.status == 503


def test_HFE3_http_5xx_wirft_client_error():
    """HFE-3: HTTP 500 vom Vorschlag-Endpoint → HoerspielClientError propagiert."""
    error_500 = HoerspielClientError("500", status=500)
    client = FakeHoerspielClient(vorschlag_error=error_500)
    with pytest.raises(HoerspielClientError):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="Stigi und das Mondlicht",
        )


# ============================================================
#  HFE-4 — Tool-Result: Titel + Vorschau + Voice + Bestätigung
# ============================================================


def test_HFE4_propose_happy_path_struktur():
    """HFE-4/ENTRY-PATH: propose() mit FakeClient → strukturierter Tool-Result-Text
    mit Titel, Vorschau-Text, Voice, Bestätigungs-Block."""
    client = FakeHoerspielClient(
        vorschlag_response={
            "titel": "Der Schneesturm",
            "text": "Stigi entdeckt eine verschneite Höhle.",
            "folgen-nr-vorschlag": 42,
        },
        config_response={"default_voice": "shimmer"},
    )
    result = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi und der Schneesturm",
    )
    assert isinstance(result, str)
    assert "Der Schneesturm" in result
    assert "Stigi entdeckt eine verschneite Höhle." in result
    assert "shimmer" in result or "onyx" in result
    # Bestätigungs-Frage
    assert "vertonen" in result.lower() or "minuten" in result.lower()


def test_HFE4_intro_outro_nicht_in_vorschau():
    """HFE-4: Intro/Outro sind Serien-Assets (HSP-8) — der Skill darf sie NICHT
    eigenständig in den Vorschau-Text einfügen. Der Buddy-Text wird unverändert
    durchgereicht; der Skill ergänzt kein Intro/Outro-Markup."""
    client = FakeHoerspielClient(
        vorschlag_response={
            "titel": "Das Geheimnis",
            "text": "Stigi entdeckt ein altes Buch im Keller.",
            "folgen-nr-vorschlag": 1,
        }
    )
    result = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Ein ganz geheimes Abenteuer",
    )
    # Der Skill selbst fügt kein Intro/Outro-Markup hinzu (HSP-8 — geteilt).
    # Der Buddy-Text enthält hier bewusst kein "intro"/"outro", sodass der
    # Test zeigt: was der Skill baut, enthält es nicht.
    text_lower = result.lower()
    assert "intro" not in text_lower, "Skill darf kein Intro-Markup einfügen (HFE-4)"
    assert "outro" not in text_lower, "Skill darf kein Outro-Markup einfügen (HFE-4)"


def test_HFE4_voice_default_aus_config_wenn_kein_hint():
    """HFE-4: kein Voice-Hint → GET /config aufgerufen, Default-Voice genutzt."""
    client = FakeHoerspielClient(
        config_response={"default_voice": "onyx"},
    )
    result = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi im Gebirge",
        voice_hint=None,
    )
    assert client.config_calls == 1, "GET /config muss aufgerufen worden sein"
    assert "onyx" in result


def test_HFE4_voice_hint_im_text_nutzt_hint():
    """HFE-4: Voice-Hint im Aufrufer-Text → diese Voice, KEIN GET /config."""
    client = FakeHoerspielClient()
    result = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi und das Mondlicht",
        voice_hint="onyx",
    )
    assert client.config_calls == 0, "GET /config darf nicht aufgerufen werden, wenn hint vorhanden"
    assert "onyx" in result


def test_HFE4_voice_shimmer_hint():
    """HFE-4: voice_hint='shimmer' → shimmer in Result, kein Config-Aufruf."""
    client = FakeHoerspielClient()
    result = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi auf der Suche nach Schatz",
        voice_hint="shimmer",
    )
    assert client.config_calls == 0
    assert "shimmer" in result


# ============================================================
#  HFE-5 — execute(): Album-Bau + Bubbles
# ============================================================


def test_HFE5_execute_ruft_album_bauen():
    """HFE-5: execute() ruft POST /alben mit titel/text/voice/idee."""
    client = FakeHoerspielClient(album_response={"album-id": "alb-99"})
    tg = FakeTelegram()
    execute(
        hoerspiel_client=client,
        tg=tg,
        chat_id=42,
        display_url_origin="https://app.example.com",
        titel="Der Schneesturm",
        text="Stigi entdeckt eine Höhle.",
        voice="shimmer",
        idee="Stigi und der Schneesturm",
    )
    assert len(client.album_calls) == 1
    call = client.album_calls[0]
    assert call["titel"] == "Der Schneesturm"
    assert call["text"] == "Stigi entdeckt eine Höhle."
    assert call["voice"] == "shimmer"
    assert call["idee"] == "Stigi und der Schneesturm"


def test_HFE5_erfolgreicher_build_sendet_erfolgs_bubble():
    """HFE-5: erfolgreicher Build → Erfolgs-Bubble mit Display-URL via tg.send_message."""
    client = FakeHoerspielClient(album_response={"album-id": "alb-77"})
    tg = FakeTelegram()
    execute(
        hoerspiel_client=client,
        tg=tg,
        chat_id=42,
        display_url_origin="https://app.example.com",
        titel="Das Abenteuer",
        text="Text.",
        voice="shimmer",
        idee="Eine Idee",
    )
    # HFE-5: Start-Bubble (vor langem Album-Bau) + Erfolgs-Bubble (danach) = 2 sends.
    assert len(tg.sent) == 2
    start_msg = tg.sent[0]["text"].lower()
    assert "schreibe" in start_msg or "vertonen" in start_msg or "minuten" in start_msg
    msg = tg.sent[1]["text"]
    assert "alb-77" in msg or "✅" in msg
    assert "app.example.com" in msg or "/display/hoerspiel" in msg


def test_HFE5_http_412_shared_asset_hinweis():
    """HFE-5: HTTP 412 → Shared-Asset-Hinweis-Bubble ohne erneuten Build-Versuch."""
    error_412 = HoerspielClientError("412 Precondition Failed", status=412)
    client = FakeHoerspielClient(album_error=error_412)
    tg = FakeTelegram()
    execute(
        hoerspiel_client=client,
        tg=tg,
        chat_id=42,
        display_url_origin="https://app.example.com",
        titel="Folge",
        text="Text.",
        voice="shimmer",
        idee="Idee",
    )
    assert len(client.album_calls) == 1, "Nur ein Versuch, kein Retry"
    # Start-Bubble + Fehler-Bubble = 2 sends.
    assert len(tg.sent) == 2
    msg = tg.sent[1]["text"].lower()
    assert "intro" in msg or "outro" in msg or "vorsynthetis" in msg or "asset" in msg


def test_HFE5_http_503_fehler_bubble():
    """HFE-5: HTTP 503 → Fehler-Bubble ohne erneuten Build-Versuch."""
    error_503 = HoerspielClientError("503 Service Unavailable", status=503)
    client = FakeHoerspielClient(album_error=error_503)
    tg = FakeTelegram()
    execute(
        hoerspiel_client=client,
        tg=tg,
        chat_id=42,
        display_url_origin="https://app.example.com",
        titel="Folge",
        text="Text.",
        voice="onyx",
        idee="Idee",
    )
    assert len(client.album_calls) == 1
    # Start-Bubble + Fehler-Bubble = 2 sends.
    assert len(tg.sent) == 2
    msg = tg.sent[1]["text"].lower()
    assert "erreichbar" in msg or "schiefgegangen" in msg or "engine" in msg


# ============================================================
#  HFE-7 — Routing: kein tg.send_* in propose()
# ============================================================


def test_HFE7_kein_tg_send_in_propose():
    """HFE-7: propose() darf KEIN tg.send_*-Aufruf ausführen (Routing-Test)."""
    # propose() nimmt kein tg-Argument — diese Funktion hat keinen Zugang zu tg.
    # Test prüft über Task-Ebene: propose() tg-Objekt ist nicht angeschlossen.
    tg = FakeTelegram()
    task = _make_task(tg=tg)
    ctx = _ctx()
    proposal = task.propose(
        {"idee": "Stigi und der Regenwald"},
        ctx,
    )
    assert isinstance(proposal, Proposal)
    assert tg.sent == [], "propose() darf kein tg.send_message aufrufen (HFE-7)"


# ============================================================
#  Task-Klassifikation
# ============================================================


def test_task_ist_write_task():
    """HFE-1/EC-10: HoerspielFolgeErzeugenTask ist ein WriteTask."""
    assert isinstance(_make_task(), WriteTask)


def test_task_name():
    """HFE-8: Task-Name ist 'hoerspiel_folge_erzeugen' (Catalog-Schlüssel)."""
    assert _make_task().name == "hoerspiel_folge_erzeugen"


def test_task_ist_sync():
    """E-HFE-4: is_async=False — V1 synchron, kein Worker."""
    assert _make_task().is_async is False


def test_task_keine_post_execute_hooks():
    """Keine Post-Execute-Hooks (kein Cache-Reload nötig)."""
    assert _make_task().post_execute_hooks == ()


# ============================================================
#  Task-Ebene: propose() → Proposal
# ============================================================


def test_task_propose_liefert_proposal():
    """HFE-3/4: Task.propose() liefert Proposal mit strukturiertem Summary."""
    task = _make_task()
    ctx = _ctx()
    proposal = task.propose({"idee": "Stigi und der Drachenturm"}, ctx)
    assert isinstance(proposal, Proposal)
    assert len(proposal.summary) > 10


def test_task_propose_berechtigung_fehler():
    """HFE-2: Task.propose() wirft BerechtigungError für Nicht-Mitglied."""
    task = _make_task(is_member_fn=_kein_mitglied)
    ctx = _ctx(from_user_id=99)
    with pytest.raises(BerechtigungError):
        task.propose({"idee": "Stigi auf dem Mond"}, ctx)


# ============================================================
#  Task-Ebene: execute() → Album-Bau + Bubble
# ============================================================


def test_task_execute_ruft_album_und_sendet():
    """HFE-5/TASK-10: Task.execute() baut Album und sendet Bubble (über Session-State)."""
    client = FakeHoerspielClient(album_response={"album-id": "alb-3"})
    tg = FakeTelegram()
    task = _make_task(hoerspiel_client=client, tg=tg)
    ctx = _ctx(chat_id=55)
    # Erst propose aufrufen um Session-State zu befüllen
    task.propose({"idee": "Stigi und der Drachenturm"}, ctx)
    task.execute({}, ctx)
    assert len(client.album_calls) == 1
    assert tg.sent[0]["chat_id"] == 55


# ============================================================
#  HFE-5 Session-State: propose→execute Brücke (Befund 1)
# ============================================================


def test_task_propose_execute_end_to_end_session_state():
    """HFE-5/Befund1/ENTRY-PATH: propose→execute mit Session-State überbrückt
    korrekt: album_bauen bekommt titel/text/voice/idee aus dem Buddy-Vorschlag."""
    client = FakeHoerspielClient(
        vorschlag_response={
            "titel": "Der Schneesturm",
            "text": "Stigi entdeckt eine verschneite Höhle.",
            "folgen-nr-vorschlag": 42,
        },
        config_response={"default_voice": "shimmer"},
        album_response={"album-id": "alb-42"},
    )
    tg = FakeTelegram()
    task = _make_task(hoerspiel_client=client, tg=tg)
    ctx = _ctx(chat_id=77, from_user_id=7)

    proposal = task.propose({"idee": "Stigi und der Schneesturm"}, ctx)
    assert isinstance(proposal, Proposal)

    # execute() ohne titel/text im arguments-Dict — Session-State trägt sie.
    task.execute({"idee": "Stigi und der Schneesturm"}, ctx)

    assert len(client.album_calls) == 1
    call = client.album_calls[0]
    # titel muss aus dem Buddy-Vorschlag stammen, nicht leer sein
    assert call["titel"] == "Der Schneesturm", (
        "titel muss aus Session-State kommen, nicht aus arguments (Befund 1)")
    assert call["text"] != "", "text darf nicht leer sein (Befund 1)"
    assert call["voice"] in ("shimmer", "onyx")
    assert call["idee"] == "Stigi und der Schneesturm"


def test_task_execute_ohne_vorherigen_propose_meldet_klar():
    """Befund1: execute() ohne vorherigen propose → klare Fehler-Bubble,
    kein album_bauen-Aufruf."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = _make_task(hoerspiel_client=client, tg=tg)
    ctx = _ctx(chat_id=99)

    result = task.execute({}, ctx)

    assert client.album_calls == [], "kein album_bauen ohne Session-State"
    assert len(tg.sent) == 1, "Fehler-Bubble muss gesendet werden"
    bubble = tg.sent[0]["text"]
    assert "verloren" in bubble.lower() or "starten" in bubble.lower(), (
        "Fehler-Bubble soll klar auf Problem hinweisen")
