"""Tests für hoerspiel_folge_erzeugen + HoerspielFolgeErzeugenTask —
HFE-1 … HFE-10, E-HFE-6 (specs/platform/hoerspiel-folge-erzeugen.md).

Abgedeckte ACs (HFE-9-Mindest-Abdeckung + #910-Pflicht-ACs):
  HFE-2  — BerechtigungError für Nicht-Eltern, kein Buddy-Aufruf
  HFE-3  — leere/mehrdeutige Idee → ValueError (EC-22-Rückfrage), kein Buddy-Aufruf
  HFE-3  — leere Idee + Themen verfügbar → Rückfrage mit Themen-Liste (Sub-Case 1)
  HFE-3  — leere Idee + 404 vom Themen-Endpoint → Fehler-Tool-Result-Text
  HFE-3  — leere Idee + 422 vom Themen-Endpoint → EC-22-Rückfrage ohne Themen
  HFE-3  — konkrete-aber-unvollständige Idee → Diskussions-Marker (Sub-Case 2)
  HFE-3  — Eltern-Signal nach Diskussion → Standard-Pfad zum Vorschlag-Endpoint
  HFE-3  — gefüllte Idee → POST /folgen-vorschlag mit Idee im Body
  HFE-3  — HTTP 404 vom Vorschlag-Endpoint → Fehler-Tool-Result-Text (kein Vorschlag)
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
  E-HFE-6 / #910 — kind_id Pflicht-Argument in propose(); MIA_ALTER entfernt
  E-HFE-6 / #910 — themen_lesen(kind_id) ruft GET /<kind_id>/themen; Response-Schema prüfen
  HFE-10 — Settings-Beifang-Button in erster propose()-Antwort (Sub-Case 1/2/3)
  HFE-10 — Beifang NICHT in Folge-Antworten (is_first_propose=False)
  HFE-10 — Bei leerer mini_app_base_url kein Beifang-Button, keine Fehler

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
    """Kontrollierter Doppelter des HoerspielClient (CLIENT-1).

    themen_response semantics (neu #910, HSP-38, RAT-17):
      None (default)  → HoerspielClientError(status=422) simulieren
                        (Alter nicht gepflegt — EC-22-Rückfrage ohne Themen)
      list[str]       → 200 mit {"kind_id", "name", "alter", "themen"} — Themen-Liste
      "404"           → HoerspielClientError(status=404) simulieren (kind_id unbekannt)

    Hinweis: das alte themen_response=None = "leere Liste (wie 404)"-Verhalten
    ist auf 422 umgestellt, da themen_lesen() jetzt bei 404 explizit eine
    Exception wirft (statt leere Liste). Der 422-Pfad entspricht dem alten
    "Alter nicht gepflegt"-Verhalten.
    """

    def __init__(self, *,
                 vorschlag_response=None,
                 vorschlag_error=None,
                 album_response=None,
                 album_error=None,
                 config_response=None,
                 config_error=None,
                 themen_response=None,
                 themen_error=None,
                 kind_id: str = "mia",
                 kind_name: str = "Mia",
                 kind_alter: int = 4):
        self.vorschlag_calls = []   # [idee_str]
        self.album_calls = []       # [{"titel", "text", "voice", "idee"}]
        self.config_calls = 0
        self.themen_calls = []      # [kind_id_str]

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
        # themen_response: None → 422 (Alter nicht gepflegt, Sub-Case 1 ohne Themen)
        #                  list  → 200 mit {kind_id, name, alter, themen}
        #                  "404" → 404 (kind_id unbekannt)
        self._themen_response = themen_response
        self._themen_error = themen_error
        self._kind_id = kind_id
        self._kind_name = kind_name
        self._kind_alter = kind_alter

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

    def themen_lesen(self) -> dict:
        """Neu #910 (HSP-38, RAT-17): kein kind_id-Argument mehr (Sister-Pattern).
        Client-Instanz kennt kind_id aus self._kind_id."""
        self.themen_calls.append(self._kind_id)
        if self._themen_error is not None:
            raise self._themen_error
        if self._themen_response == "404":
            raise HoerspielClientError(
                "Hörspiel-Buddy: GET /api/v1/hoerspiel/%s/themen → 404" % self._kind_id,
                status=404)
        if self._themen_response is None:
            # 422 (Alter nicht gepflegt) → nur EC-22-Rückfrage ohne Themen
            raise HoerspielClientError(
                "Hörspiel-Buddy: GET /api/v1/hoerspiel/%s/themen → 422" % self._kind_id,
                status=422)
        # 200 mit vollständigem Response-Dict (HSP-38)
        return {
            "kind_id": self._kind_id,
            "name": self._kind_name,
            "alter": self._kind_alter,
            "themen": list(self._themen_response),
        }


class FakeTelegram:
    """Minimale Telegram-Doppelung — aufzeichnende send_message + send_inline_keyboard."""

    def __init__(self):
        self.sent = []          # [{chat_id, text}]
        self.keyboards = []     # [{chat_id, text, buttons}]

    def send_message(self, chat_id, text):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 3000 + len(self.sent)}

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.keyboards.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"message_id": 4000 + len(self.keyboards)}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _ctx(chat_id=42, from_user_id=7):
    return TurnContext(chat_id=chat_id, from_user_id=from_user_id)


def _make_task(*, hoerspiel_client=None, tg=None, is_member_fn=None,
               display_url_origin="https://app.example.com",
               mini_app_base_url="https://mini.example.com"):
    return HoerspielFolgeErzeugenTask(
        tg=tg or FakeTelegram(),
        hoerspiel_client=hoerspiel_client or FakeHoerspielClient(),
        display_url_origin=display_url_origin,
        is_member_fn=is_member_fn or _immer_mitglied,
        mini_app_base_url=mini_app_base_url,
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
            kind_id="mia",
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
            kind_id="mia",
        )
    assert client.vorschlag_calls == []


# ============================================================
#  HFE-3 — leere / mehrdeutige Idee (EC-22)
# ============================================================


def test_HFE3_leere_idee_raises_value_error():
    """HFE-3: leere Idee + 422 vom Themen-Endpoint → ValueError (EC-22-Rückfrage), kein Buddy-Aufruf."""
    # themen_response=None → FakeClient gibt 422 zurück → EC-22-Rückfrage ohne Themen
    client = FakeHoerspielClient(themen_response=None)
    with pytest.raises(ValueError, match=r"Worum|Idee|Beschreib"):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="",
            kind_id="mia",
        )
    assert client.vorschlag_calls == []


def test_HFE3_kurze_idee_raises_value_error():
    """HFE-3: Idee unter Mindest-Zeichen → ValueError, kein Buddy-Aufruf."""
    client = FakeHoerspielClient(themen_response=None)
    with pytest.raises(ValueError, match=r"Worum|Idee|Beschreib"):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="Hi",
            kind_id="mia",
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
        kind_id="mia",
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
            kind_id="mia",
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
            kind_id="mia",
        )


def test_HFE3_http_404_vom_vorschlag_endpoint_fehler_text():
    """HFE-3 / E-HFE-6 / #910: HTTP 404 vom Vorschlag-Endpoint (kind_id unbekannt)
    → Fehler-Tool-Result-Text als ValueError, KEIN HoerspielClientError.
    Kein Vorschlag-Block (kein folgen_vorschlag-Aufruf ohne 404)."""
    error_404 = HoerspielClientError("404", status=404)
    client = FakeHoerspielClient(vorschlag_error=error_404)
    with pytest.raises(ValueError, match=r"finn|Hörspiel-Buddy|keinen"):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="Finn und das Abenteuer",
            kind_id="finn",  # → 404 vom Buddy (unbekannte Instanz)
        )
    # vorschlag_calls hat 1 Eintrag (404 kommt vom Aufruf selbst)
    assert len(client.vorschlag_calls) == 1


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
    result, _fields = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi und der Schneesturm",
        kind_id="mia",
    )
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
    result, _fields = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Ein ganz geheimes Abenteuer",
        kind_id="mia",
    )
    # Der Skill selbst fügt kein Intro/Outro-Markup hinzu (HSP-8 — geteilt).
    # Der Buddy-Text enthält hier bewusst kein "intro"/"outro", sodass der
    # Test zeigt: was der Skill baut, enthält es nicht.
    text_lower = result.lower()
    assert "intro" not in text_lower, "Skill darf kein Intro-Markup einfügen (HFE-4)"
    assert "outro" not in text_lower, "Skill darf kein Outro-Markup einfügen (HFE-4)"


def test_HFE4_voice_default_aus_config():
    """HFE-4 / #995: propose() liest immer GET /config (kein voice_hint mehr).
    Default-Voice aus Mini-App-Settings → in Result-Text."""
    client = FakeHoerspielClient(
        config_response={"default_voice": "onyx"},
    )
    result, _fields = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi im Gebirge",
        kind_id="mia",
    )
    assert client.config_calls == 1, "GET /config muss aufgerufen worden sein"
    assert "onyx" in result


def test_HFE4_voice_config_lesen_NACH_folgen_vorschlag_995():
    """HFE-4 / #995: Race-Fix — config_lesen läuft NACH folgen_vorschlag.

    Begründung: HFE-10 sendet den Settings-Beifang-Button vor dem 90s-LLM-Call.
    Stellt die Familie währenddessen in der Mini-App auf onyx um, soll die
    neue Voice im Bestätigungs-Block stehen. Vorher las propose() die Voice
    VOR dem LLM-Call → Stand bis zu 100 s alt (Live-Befund 2026-06-17 23:54).

    Reihenfolge: folgen_vorschlag muss VOR config_lesen passieren.
    """
    call_order: list[str] = []

    class OrderSpyClient(FakeHoerspielClient):
        def folgen_vorschlag(self, idee):
            call_order.append("folgen_vorschlag")
            return super().folgen_vorschlag(idee)

        def config_lesen(self):
            call_order.append("config_lesen")
            return super().config_lesen()

    client = OrderSpyClient(config_response={"default_voice": "onyx"})
    propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi und der Bergsee",
        kind_id="mia",
    )
    assert call_order == ["folgen_vorschlag", "config_lesen"], (
        "HFE-4 #995: Voice-Default muss NACH dem LLM-Call gelesen werden, "
        "damit Mini-App-Tune während des Wartens noch greift. "
        "Tatsächliche Reihenfolge: %r" % call_order)


def test_HFE4_kein_on_the_fly_override_hinweis_995():
    """HFE-4 / #995: Result-Text darf KEINEN Override-Hinweis tragen.

    Voice-Wechsel lebt nur in der Mini-App — Phrasen wie „oder schreib
    »shimmer« / »onyx«" laden zum on-the-fly-Override ein und sind raus.
    """
    client = FakeHoerspielClient(config_response={"default_voice": "onyx"})
    result, _fields = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi und der Mond",
        kind_id="mia",
    )
    # Konkrete Hinweis-Phrasen, die der Bot NICHT mehr senden darf
    assert "oder schreib" not in result.lower(), (
        "HFE-4 #995: Result-Text darf keinen Override-Hinweis tragen")
    assert "»shimmer«" not in result, (
        "HFE-4 #995: kein Voice-Override-Vorschlag im Result-Text")
    assert "»onyx«" not in result, (
        "HFE-4 #995: kein Voice-Override-Vorschlag im Result-Text")


def test_HFE4_voice_default_fallback_onyx_bei_config_fehler_995():
    """HFE-4 / #995: Config-Fehler → Fallback ist onyx (VOICE_DEFAULT)."""
    from skills.hoerspiel_folge_erzeugen import VOICE_DEFAULT, VOICE_ONYX

    assert VOICE_DEFAULT == VOICE_ONYX, (
        "#995: Code-Fallback muss onyx sein, nicht shimmer")

    client = FakeHoerspielClient(
        config_error=HoerspielClientError("Buddy down", status=None),
    )
    result, _fields = propose(
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        from_user_id=7,
        idee="Stigi und das Echo",
        kind_id="mia",
    )
    assert "onyx" in result, (
        "Config-Fehler → Fallback onyx (#995); Vorschlag wird trotzdem geliefert")


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
    # HSP-53: Fertig-Link zeigt auf Player-PWA
    assert "app.example.com" in msg or "/seiten/hoerspiel/player" in msg


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


def test_HFE7_propose_sendet_quittungen_direkt():
    """HFE-7-Lockerung 2026-06-12: propose() sendet zwei Direkt-Bubbles —
    den Start-Bubble (vor dem LLM-Call, Stille von 1-2 min sonst) und ggf.
    multipart-Vorschau-Stücke (Telegram-Limit 4096 Zeichen).

    Strict EC-29 (eine Stimme im Turn) gilt für den Normalfall (1 Bot-
    Nachricht aus dem Tool-Result). Bei langen Folgen + langer LLM-
    Latenz wird das gelockert; Tool-Result-Text trägt dann den Confirm-
    Block. Memory: feedback_hfe_synchron_blockt_chat_turn.md."""
    tg = FakeTelegram()
    task = _make_task(tg=tg)
    ctx = _ctx()
    proposal = task.propose(
        {"kind_id": "mia", "idee": "Stigi und der Regenwald"},
        ctx,
    )
    assert isinstance(proposal, Proposal)
    # Mindestens der Start-Bubble muss gesendet worden sein.
    assert len(tg.sent) >= 1
    assert "überlege" in tg.sent[0]["text"].lower() or \
        "nicht stören" in tg.sent[0]["text"].lower()


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
    proposal = task.propose({"kind_id": "mia", "idee": "Stigi und der Drachenturm"}, ctx)
    assert isinstance(proposal, Proposal)
    assert len(proposal.summary) > 10


def test_task_propose_berechtigung_fehler():
    """HFE-2: Task.propose() wirft BerechtigungError für Nicht-Mitglied."""
    task = _make_task(is_member_fn=_kein_mitglied)
    ctx = _ctx(from_user_id=99)
    with pytest.raises(BerechtigungError):
        task.propose({"kind_id": "mia", "idee": "Stigi auf dem Mond"}, ctx)


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
    task.propose({"kind_id": "mia", "idee": "Stigi und der Drachenturm"}, ctx)
    task.execute({}, ctx)
    # HFE-11 V1.1: execute() läuft im Daemon-Thread — Worker abwarten.
    assert task._wait_for_active_job(55, timeout=5.0)
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

    proposal = task.propose({"kind_id": "mia", "idee": "Stigi und der Schneesturm"}, ctx)
    assert isinstance(proposal, Proposal)

    # execute() ohne titel/text im arguments-Dict — Session-State trägt sie.
    task.execute({"kind_id": "mia", "idee": "Stigi und der Schneesturm"}, ctx)
    # HFE-11 V1.1: execute() läuft im Daemon-Thread — Worker abwarten.
    assert task._wait_for_active_job(77, timeout=5.0)

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

    task.execute({}, ctx)

    assert client.album_calls == [], "kein album_bauen ohne Session-State"
    assert len(tg.sent) == 1, "Fehler-Bubble muss gesendet werden"
    bubble = tg.sent[0]["text"]
    assert "verloren" in bubble.lower() or "starten" in bubble.lower(), (
        "Fehler-Bubble soll klar auf Problem hinweisen")


# ============================================================
#  HFE-9: neue Tests (HFE-3 Diskussions-Schleife + HFE-10)
# ============================================================


def test_HFE9_leere_idee_themen_verfuegbar():
    """HFE-9 / HFE-3 Sub-Case 1 / E-HFE-6 / #910: leere Idee + Themen-Liste verfügbar →
    Tool-Result-Text trägt die Themen + EC-22-Rückfrage mit Kindname.
    themen_lesen("mia") wird aufgerufen (kind_id im Pfad, nicht ?alter=).
    Kein POST /folgen-vorschlag-Aufruf."""
    themen = ["Freundschaft", "Mut", "Abenteuer", "Familie",
              "Tiere", "Natur", "Geister", "Rätsel"]
    client = FakeHoerspielClient(
        themen_response=themen,
        kind_id="mia", kind_name="Mia", kind_alter=4,
    )
    with pytest.raises(ValueError, match=r"Worum|gehen|Vorschläge|Mia") as exc_info:
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="",   # leer → Sub-Case 1
            kind_id="mia",
        )
    msg = str(exc_info.value)
    # Mindestens ein Thema aus der Liste muss enthalten sein
    assert any(t in msg for t in themen), (
        "Sub-Case 1: Themen-Liste muss im Tool-Result-Text erscheinen")
    # Kein Vorschlag-Endpoint-Aufruf
    assert client.vorschlag_calls == [], "Sub-Case 1: kein POST /folgen-vorschlag"
    # themen_lesen wurde mit kind_id "mia" aufgerufen (nicht mit alter=4)
    assert client.themen_calls == ["mia"], (
        "Sub-Case 1 / #910: themen_lesen muss mit kind_id='mia' aufgerufen werden")


def test_HFE9_leere_idee_themen_404():
    """HFE-9 / HFE-3 Sub-Case 1 / #910: leere Idee + 404 vom Themen-Endpoint
    (kind_id unbekannt) → Fehler-Tool-Result-Text (kein Vorschlag).
    Kein POST /folgen-vorschlag-Aufruf.

    Neu #910: themen_lesen() wirft jetzt HoerspielClientError(status=404)
    bei unbekannter kind_id (statt früher leere Liste zurückzugeben).
    Bei 404 in Sub-Case 1: Fehler-Tool-Result-Text statt EC-22-Rückfrage.
    """
    # themen_response="404" → FakeClient simuliert HoerspielClientError(status=404)
    client = FakeHoerspielClient(themen_response="404")
    with pytest.raises(ValueError, match=r"keinen|Hörspiel-Buddy|unbekannt") as exc_info:
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="",   # leer → Sub-Case 1
            kind_id="unbekannt",
        )
    msg = str(exc_info.value)
    # Der Fehler-Text enthält kind_id oder Hinweis auf fehlenden Buddy
    assert "unbekannt" in msg or "Hörspiel-Buddy" in msg, (
        "404-Fehlertext muss kind_id oder Buddy-Hinweis enthalten")
    assert client.vorschlag_calls == [], "kein POST /folgen-vorschlag bei 404"


def test_HFE9_leere_idee_themen_422():
    """HFE-9 / HFE-3 Sub-Case 1 / #910: leere Idee + 422 vom Themen-Endpoint
    (Alter nicht gepflegt) → EC-22-Rückfrage OHNE Themen.
    Kein POST /folgen-vorschlag-Aufruf.

    Neu #910: themen_lesen() wirft HoerspielClientError(status=422) wenn
    Alter nicht in themen_je_alter. Bei 422 → nur EC-22-Rückfrage.
    """
    # themen_response=None → FakeClient gibt 422 (Alter nicht gepflegt)
    client = FakeHoerspielClient(themen_response=None)
    with pytest.raises(ValueError, match=r"Worum|gehen|Beschreib") as exc_info:
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="",   # leer → Sub-Case 1
            kind_id="mia",
        )
    msg = str(exc_info.value)
    # Keine Themen-Liste im Text (da 422)
    assert "Freundschaft" not in msg, (
        "Sub-Case 1 (422): keine Themen-Aufzählung im Text")
    assert "Mut" not in msg, (
        "Sub-Case 1 (422): keine Themen-Aufzählung im Text")
    assert client.vorschlag_calls == [], "kein POST /folgen-vorschlag bei 422"


def test_HFE9_diskussion_marker_bei_unvollstaendiger_idee():
    """HFE-9 / HFE-3 Sub-Case 2: konkrete-aber-unvollständige Idee (idee_diskussion=True)
    → Tool-Result-Text mit JSON-Diskussions-Marker.
    Kein POST /folgen-vorschlag-Aufruf."""
    import json as _json
    client = FakeHoerspielClient()
    with pytest.raises(ValueError, match=r'diskussion') as exc_info:
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="Stigi lernt etwas über Mut",
            idee_diskussion=True,   # Sub-Case 2
            kind_id="mia",
        )
    msg = str(exc_info.value)
    # Marker-Dict muss parsebar sein
    marker = _json.loads(msg)
    assert marker.get("diskussion") is True, (
        "Sub-Case 2: diskussion=True im JSON-Marker")
    assert "idee_bisher" in marker, "Sub-Case 2: idee_bisher im JSON-Marker"
    assert "Mut" in marker["idee_bisher"] or "Stigi" in marker["idee_bisher"], (
        "Sub-Case 2: idee_bisher enthält die originale Idee")
    # Kein Vorschlag-Endpoint-Aufruf
    assert client.vorschlag_calls == [], "Sub-Case 2: kein POST /folgen-vorschlag"


# ============================================================
#  E-HFE-6 / #910 — kind_id-Pflicht: MIA_ALTER entfernt, themen_lesen(kind_id)
# ============================================================


def test_EHF6_mia_alter_konstante_nicht_vorhanden():
    """E-HFE-6 / #910: MIA_ALTER muss aus hoerspiel_folge_erzeugen.py
    entfernt worden sein — kein Modul-Attribut mehr."""
    import skills.hoerspiel_folge_erzeugen as hfe_mod
    assert not hasattr(hfe_mod, "MIA_ALTER"), (
        "E-HFE-6: MIA_ALTER muss aus dem Modul entfernt sein (#910)")


def test_EHF6_themen_lesen_url_form():
    """E-HFE-6 / #910 / HSP-38: HoerspielClient.themen_lesen(kind_id) ruft
    GET /api/v1/hoerspiel/<kind_id>/themen auf — kein ?alter=-Query.

    entry_path_probe: themen_lesen("mia") über Transport-Naht,
    URL-Konstruktion prüfen."""
    import json

    from skills.hoerspiel_client import HoerspielClient

    aufgerufen: list = []

    def transport(method, path, *, body=None, content_type=None):
        aufgerufen.append((method, path))
        if path == "/api/v1/hoerspiel/mia/themen":
            resp = json.dumps({
                "kind_id": "mia", "name": "Mia", "alter": 4,
                "themen": ["Mut beim Probieren", "Streit vertragen"],
            }).encode()
            return 200, resp
        return 404, b'{"fehler": "not found"}'

    client = HoerspielClient(
        origin_url="http://127.0.0.1:5053",
        kind_id="mia",
        transport=transport,
    )
    result = client.themen_lesen()  # kein Argument — Sister-Pattern (#910)

    assert len(aufgerufen) == 1
    method, path = aufgerufen[0]
    assert method == "GET"
    assert path == "/api/v1/hoerspiel/mia/themen", (
        "HSP-38 / RAT-17: themen_lesen muss GET /api/v1/hoerspiel/mia/themen "
        "aufrufen — kein ?alter=-Query")
    assert result["kind_id"] == "mia"
    assert result["name"] == "Mia"
    assert result["alter"] == 4
    assert "Mut beim Probieren" in result["themen"]


def test_EHF6_themen_lesen_404_raises():
    """E-HFE-6 / #910: themen_lesen bei 404 → HoerspielClientError(status=404)."""
    from skills.hoerspiel_client import HoerspielClient, HoerspielClientError

    def transport(method, path, *, body=None, content_type=None):
        return 404, b'{"fehler": "unbekannte kind_id"}'

    client = HoerspielClient(
        origin_url="http://127.0.0.1:5053",
        kind_id="finn",
        transport=transport,
    )
    with pytest.raises(HoerspielClientError) as exc_info:
        client.themen_lesen()  # kein Argument — Sister-Pattern (#910)
    assert exc_info.value.status == 404


def test_EHF6_themen_lesen_422_raises():
    """E-HFE-6 / #910: themen_lesen bei 422 → HoerspielClientError(status=422)."""
    from skills.hoerspiel_client import HoerspielClient, HoerspielClientError

    def transport(method, path, *, body=None, content_type=None):
        return 422, b'{"fehler": "Alter nicht gepflegt"}'

    client = HoerspielClient(
        origin_url="http://127.0.0.1:5053",
        kind_id="mia",
        transport=transport,
    )
    with pytest.raises(HoerspielClientError) as exc_info:
        client.themen_lesen()  # kein Argument — Sister-Pattern (#910)
    assert exc_info.value.status == 422


def test_HFE10_settings_beifang_nur_in_erster_antwort():
    """HFE-10: Settings-Beifang-Button erscheint in der ersten propose()-Antwort
    eines Turns, NICHT in Folge-Antworten.

    Szenario: Zweimaliger propose()-Aufruf auf denselben Task.
    Erster Aufruf (Sub-Case 1, leere Idee) → Beifang-Button vorhanden.
    Zweiter Aufruf (Sub-Case 1, erneute Rückfrage) → KEIN Beifang-Button.
    """
    themen = ["Abenteuer", "Freundschaft"]
    client = FakeHoerspielClient(
        themen_response=themen,
        kind_id="mia", kind_name="Mia", kind_alter=4,
    )
    tg = FakeTelegram()
    task = _make_task(
        hoerspiel_client=client, tg=tg,
        mini_app_base_url="https://mini.example.com")
    ctx = _ctx(chat_id=42, from_user_id=7)

    # Erster Aufruf: leere Idee → Sub-Case 1 → ValueError + Beifang-Button
    with pytest.raises(ValueError, match=r"Worum|gehen|Mia|Abenteuer"):
        task.propose({"kind_id": "mia", "idee": ""}, ctx)

    keyboards_nach_erstem = len(tg.keyboards)
    assert keyboards_nach_erstem == 1, (
        "HFE-10: Erster propose()-Aufruf muss Settings-Beifang-Button senden")
    beifang_btn = tg.keyboards[0]["buttons"]
    assert any("einstellungen" in str(b.get("label", "")).lower()
               or "⚙" in str(b.get("label", ""))
               for b in beifang_btn), (
        "HFE-10: Beifang-Button muss Label ⚙️ Einstellungen tragen")
    # HSP-53: url-Feld (nicht web_app_url), zeigt auf Player-PWA, kein Hash
    assert any("/seiten/hoerspiel/player" in str(b.get("url", ""))
               for b in beifang_btn), (
        "HFE-10: Beifang-Button muss url mit /seiten/hoerspiel/player tragen (HSP-53)")
    assert not any("#" in str(b.get("url", "")) for b in beifang_btn), (
        "HFE-10: Beifang-Button darf kein Hash-Fragment enthalten (kein Tab-Modell)")

    # Zweiter Aufruf: gleicher Turn, leere Idee → Sub-Case 1 → KEIN neuer Button
    with pytest.raises(ValueError, match=r"Worum|gehen|Mia|Abenteuer"):
        task.propose({"kind_id": "mia", "idee": ""}, ctx)

    assert len(tg.keyboards) == keyboards_nach_erstem, (
        "HFE-10: Folge-Antwort darf keinen weiteren Beifang-Button senden")


def test_HFE10_kein_beifang_bei_leerer_mini_app_url():
    """HFE-10: Wenn mini_app_base_url leer ist, entfällt der Beifang-Button still.
    Kein Fehler-Text, keine Exception, Rest der Antwort bleibt grün."""
    client = FakeHoerspielClient(
        themen_response=["Abenteuer"],
        kind_id="mia", kind_name="Mia", kind_alter=4,
    )
    tg = FakeTelegram()
    # mini_app_base_url="" → kein Beifang
    task = _make_task(
        hoerspiel_client=client, tg=tg,
        mini_app_base_url="")
    ctx = _ctx(chat_id=42, from_user_id=7)

    with pytest.raises(ValueError, match=r"Worum|gehen|Mia|Abenteuer") as exc_info:
        task.propose({"kind_id": "mia", "idee": ""}, ctx)

    # Keine Inline-Keyboard-Nachrichten
    assert tg.keyboards == [], (
        "HFE-10: Bei leerer mini_app_base_url kein send_inline_keyboard")
    # Aber die EC-22-Rückfrage ist trotzdem im ValueError
    msg = str(exc_info.value)
    assert "Worum" in msg or "gehen" in msg.lower() or "Abenteuer" in msg, (
        "HFE-10: EC-22-Rückfrage bleibt auch ohne Beifang erhalten")


# ============================================================
#  #910 Watchdog-Pflicht-Tests: propose() ohne kind_id + Mini-Map
# ============================================================


def test_propose_ohne_kind_id_wirft_typeerror():
    """AC-1 / HFE-3 / E-HFE-6 / #910: propose() ohne kind_id wirft TypeError.

    kind_id ist Pflicht-Argument (kein Default mehr seit Watchdog T4-Fix,
    Pfad A). Der Aufruf ohne kind_id darf die Berechtigung nicht einmal prüfen.
    entry_path_probe_result: probed.
    """
    client = FakeHoerspielClient()
    with pytest.raises(TypeError):
        propose(
            hoerspiel_client=client,
            is_member_fn=_immer_mitglied,
            from_user_id=7,
            idee="Stigi und der Regenwald",
            # kind_id absichtlich NICHT übergeben → TypeError
        )


def test_task_mini_map_kind_id_mia_nutzt_mia_client():
    """AC-3 / E-HFE-6 / #910: HoerspielFolgeErzeugenTask.propose() nutzt
    den Mia-Client aus der Mini-Map (kind_id="mia").

    Die Mini-Map _client_by_kind_id wird im Konstruktor befüllt; in V1 ist
    kind_id="mia" hartkodiert (TODO #911). Der aktive Client muss mit
    der Mia-Origin konstruiert worden sein.
    """
    from skills.hoerspiel_client import HoerspielClient

    aufgerufen: list = []

    def transport(method, path, *, body=None, content_type=None):
        aufgerufen.append((method, path))
        if "folgen-vorschlag" in path:
            import json as _json
            resp = _json.dumps({
                "titel": "Mia-Folge",
                "text": "Stigi und das Abenteuer.",
                "folgen-nr-vorschlag": 1,
            }).encode()
            return 200, resp
        if "config" in path:
            import json as _json
            return 200, _json.dumps({"default_voice": "shimmer"}).encode()
        return 404, b"{}"

    tg = FakeTelegram()
    # Task mit expliziten Origins konstruieren — Mini-Map baut eigene Clients.
    mia_origin = "http://127.0.0.1:5053"
    finn_origin = "http://127.0.0.1:5055"
    # Basis-Client (Fallback) ohne Transport — Mia-Client via Mini-Map hat Transport.
    basis_client = FakeHoerspielClient()
    mia_client = HoerspielClient(
        origin_url=mia_origin, kind_id="mia", transport=transport)

    task = HoerspielFolgeErzeugenTask(
        tg=tg,
        hoerspiel_client=basis_client,
        display_url_origin="https://app.example.com",
        is_member_fn=_immer_mitglied,
        mini_app_base_url="https://mini.example.com",
        hoerspiel_url_origin=mia_origin,
        hoerspiel_url_origin_finn=finn_origin,
    )
    # Überschreiben: Mia-Slot auf kontrollierten Client setzen.
    task._client_by_kind_id["mia"] = mia_client

    ctx = _ctx(chat_id=42, from_user_id=7)
    proposal = task.propose({"kind_id": "mia", "idee": "Stigi findet Gold"}, ctx)

    assert isinstance(proposal, Proposal), "propose() muss Proposal zurückgeben"
    # Transport wurde aufgerufen (Mia-Client genutzt, nicht basis_client)
    assert any("folgen-vorschlag" in p for _, p in aufgerufen), (
        "Mini-Map: Mia-Client muss für propose() genutzt worden sein")


# ============================================================
#  T954 — kind_id aus Tool-Call-arguments (kein 'mia'-Hardcode mehr)
# ============================================================


def test_task_uses_kind_id_from_arguments():
    """T954 / E-HFE-6 / HFE-3: Task.propose() liest kind_id aus arguments und
    wählt den passenden Client aus der Mini-Map (entry_path_probe).

    Mock-Aufruf mit arguments = {"kind_id": "finn", "idee": "..."} →
    prüft, dass der Finn-Client verwendet wird (nicht der Mia-Client).
    """
    finn_client = FakeHoerspielClient(kind_id="finn")
    mia_client = FakeHoerspielClient(kind_id="mia")
    tg = FakeTelegram()

    task = _make_task(hoerspiel_client=mia_client, tg=tg)
    # Mini-Map manuell bestücken mit kontrollierten Clients
    task._client_by_kind_id["mia"] = mia_client
    task._client_by_kind_id["finn"] = finn_client

    ctx = _ctx(chat_id=42, from_user_id=7)
    proposal = task.propose({"kind_id": "finn", "idee": "Finn findet ein Abenteuer"}, ctx)

    assert isinstance(proposal, Proposal), "propose() muss Proposal zurückgeben"
    # Finn-Client wurde aufgerufen, nicht Mia-Client
    assert len(finn_client.vorschlag_calls) == 1, (
        "T954: Finn-Client muss via kind_id='finn' aus arguments gewählt worden sein")
    assert finn_client.vorschlag_calls[0] == "Finn findet ein Abenteuer"
    assert mia_client.vorschlag_calls == [], (
        "T954: Mia-Client darf bei kind_id='finn' nicht aufgerufen werden")
    # kind_id des genutzten Clients muss 'finn' sein
    assert finn_client._kind_id == "finn"


def test_task_unbekannte_kind_id_wirft_fehler():
    """T954 / HFE-9 / AC-2 / Watchdog-Fix Pfad A: arguments mit unbekannter
    kind_id ('fremdkind') → ValueError mit Hinweis auf erlaubte Werte.
    Kein stiller Fallback auf 'mia' mehr (HFE-9 Pflicht-Argument ohne Default).
    """
    mia_client = FakeHoerspielClient(kind_id="mia")
    tg = FakeTelegram()

    task = _make_task(hoerspiel_client=mia_client, tg=tg)
    task._client_by_kind_id["mia"] = mia_client
    # 'fremdkind' ist nicht in _client_by_kind_id

    ctx = _ctx(chat_id=42, from_user_id=7)
    with pytest.raises(ValueError, match=r"fremdkind|Erlaubt|Unbekannte"):
        task.propose(
            {"kind_id": "fremdkind", "idee": "Ein Abenteuer für ein unbekanntes Kind"},
            ctx,
        )
    # Kein Buddy-Aufruf bei unbekannter kind_id
    assert mia_client.vorschlag_calls == [], (
        "T954: kein Buddy-Aufruf bei unbekannter kind_id")


def test_task_kind_id_fehlend_wirft_fehler():
    """T954 / HFE-9 / AC-2 / Watchdog-Fix Pfad A: arguments ohne kind_id-Feld →
    ValueError (HFE-9 Pflicht-Argument ohne Default).
    Kein stiller Fallback auf 'mia' mehr — agent.py fängt als is_error=True.

    test_task_kind_id_fehlend_wirft_fehler: deckt AC-2 ab.
    """
    mia_client = FakeHoerspielClient(kind_id="mia")
    tg = FakeTelegram()

    task = _make_task(hoerspiel_client=mia_client, tg=tg)
    task._client_by_kind_id["mia"] = mia_client

    ctx = _ctx(chat_id=42, from_user_id=7)
    # Kein kind_id-Feld in arguments → Pflicht-Fehler
    with pytest.raises(ValueError, match=r"kind_id|Pflicht"):
        task.propose({"idee": "Stigi im Herbstwald"}, ctx)

    # Kein Buddy-Aufruf ohne kind_id
    assert mia_client.vorschlag_calls == [], (
        "T954: kein Buddy-Aufruf bei fehlendem kind_id")


# ============================================================
#  T962 — execute() kind_id aus pending (T954-Folge-Bug)
# ============================================================


def test_execute_uses_kind_id_finn_from_pending():
    """T962 / HFE-3 / E-HFE-6 / HFE-5: execute() liest kind_id aus dem
    pending-Dict und wählt den Finn-Client, NICHT den Mia-Default.

    Szenario: propose(kind_id=finn) → pending trägt kind_id=finn →
    execute() → hfe_mod.execute aufgerufen mit Finn-Client.

    Deckt den Live-Bug vom 2026-06-16 15:44 ab: Mia-Instanz (Port 5053)
    wurde beim Finn-Album-Bau aufgerufen statt Finn (Port 5055).

    entry_path_probe_result: probed.
    """
    finn_client = FakeHoerspielClient(
        kind_id="finn",
        album_response={"album-id": "finn-alb-1"},
    )
    mia_client = FakeHoerspielClient(
        kind_id="mia",
        album_response={"album-id": "mia-alb-1"},
    )
    tg = FakeTelegram()

    task = _make_task(hoerspiel_client=mia_client, tg=tg)
    task._client_by_kind_id["mia"] = mia_client
    task._client_by_kind_id["finn"] = finn_client

    ctx = _ctx(chat_id=88, from_user_id=7)

    # propose() mit kind_id=finn → pending trägt kind_id=finn
    proposal = task.propose({"kind_id": "finn", "idee": "Finn und das Wettrennen"}, ctx)
    assert isinstance(proposal, Proposal)
    assert "kind_id" in task._pending_vorschlaege.get(88, {}), (
        "T962 AC-1: pending-Dict muss kind_id enthalten")
    assert task._pending_vorschlaege[88]["kind_id"] == "finn", (
        "T962 AC-1: pending kind_id muss 'finn' sein")

    # execute() → Finn-Client muss album_bauen() aufgerufen haben
    task.execute({}, ctx)
    # HFE-11 V1.1: execute() läuft im Daemon-Thread — Worker abwarten.
    assert task._wait_for_active_job(88, timeout=5.0)

    assert len(finn_client.album_calls) == 1, (
        "T962 AC-2: execute() muss Finn-Client für album_bauen wählen")
    assert mia_client.album_calls == [], (
        "T962 AC-2: Mia-Client darf bei kind_id='finn' NICHT aufgerufen werden")
