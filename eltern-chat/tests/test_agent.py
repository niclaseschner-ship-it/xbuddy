"""Tests für den Agent-Loop — EC-4/EC-7/EC-8/EC-9/EC-10/EC-12/EC-13/EC-14,
E-EC-4/E-EC-5 (Refs #27).

Der KI-Anbieter ist eine kontrollierte Doppelung (EC-17); geprüft wird das
Verhalten auch gegen absichtlich abwegige Modell-Ausgaben (EC-12).
"""

import agent
import pytest
from fakes import FakeProvider, FakeReadTask, FakeWriteTask, task_call_response, text_response
from model import GenerationResponse, Message, ProviderError, TaskCallBlock, TaskResultBlock, TextBlock
from tasks import Catalog, TurnContext

# Der deterministische Ausführungs-Kontext, den run_turn unverändert an die
# Aufgaben durchreicht (#63). Für die Agent-Tests ein fester Stellvertreter.
_TURN = TurnContext(chat_id=42)


def _user(text="eine Anfrage"):
    return Message("user", [TextBlock(text)])


def _catalog(*tasks):
    cat = Catalog()
    for t in tasks:
        cat.register(t)
    return cat


# -- EC-4: natürlichsprachliche Anfrage, einfache Antwort --------

def test_EC_4_plain_answer_without_task():
    provider = FakeProvider([text_response("Hallo, wie kann ich helfen?")])
    result = agent.run_turn([], _user(), provider, Catalog(), _TURN)
    assert result.reply_text == "Hallo, wie kann ich helfen?"
    assert result.proposal is None


# -- EC-9: lesende Aufgabe läuft direkt --------------------------

def test_EC_9_read_task_runs_and_result_flows_back():
    read = FakeReadTask(name="info_lesen", result="Es sind 22 Grad.")
    provider = FakeProvider([
        task_call_response("info_lesen", arguments={"ort": "Berlin"}),
        text_response("In Berlin sind es 22 Grad."),
    ])
    result = agent.run_turn([], _user(), provider, _catalog(read), _TURN)
    # Aufgabe wurde direkt ausgeführt (EC-9) ...
    assert read.run_calls == [{"ort": "Berlin"}]
    # ... das Ergebnis wurde dem Anbieter zurückgespeist ...
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert isinstance(fed_back, TaskResultBlock)
    assert fed_back.content == "Es sind 22 Grad."
    assert fed_back.is_error is False
    # ... und am Ende steht eine fertige Antwort.
    assert result.reply_text == "In Berlin sind es 22 Grad."


def test_EC_9_failing_read_task_is_reported_not_raised():
    read = FakeReadTask(name="info_lesen", result=RuntimeError("Quelle weg"))
    provider = FakeProvider([
        task_call_response("info_lesen"),
        text_response("Das hat leider nicht geklappt."),
    ])
    result = agent.run_turn([], _user(), provider, _catalog(read), _TURN)
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert fed_back.is_error is True
    assert result.reply_text == "Das hat leider nicht geklappt."


# -- #63: turn_context wird unverändert an die Aufgabe durchgereicht --

def test_turn_context_is_passed_through_to_a_read_task():
    """run_turn reicht den Ausführungs-Kontext unverändert an `task.run` —
    der Modell-Kanal bleibt allein `arguments`."""
    read = FakeReadTask(name="info_lesen")
    turn = TurnContext(chat_id=999)
    provider = FakeProvider([
        task_call_response("info_lesen", arguments={"x": 1}),
        text_response("fertig"),
    ])
    agent.run_turn([], _user(), provider, _catalog(read), turn)
    assert read.turn_contexts == [turn]


def test_turn_context_is_passed_through_to_a_write_task_propose():
    """run_turn reicht den Ausführungs-Kontext auch an `task.propose`."""
    write = FakeWriteTask(name="daten_setzen")
    turn = TurnContext(chat_id=999)
    provider = FakeProvider([task_call_response("daten_setzen")])
    agent.run_turn([], _user(), provider, _catalog(write), turn)
    assert write.turn_contexts == [turn]


# -- EC-10: schreibende Aufgabe nur nach Bestätigung -------------

def test_EC_10_write_task_yields_proposal_and_is_not_executed():
    write = FakeWriteTask(name="daten_setzen", summary="Termin am Montag eintragen")
    provider = FakeProvider([
        task_call_response("daten_setzen", arguments={"tag": "Montag"})])
    result = agent.run_turn([], _user(), provider, _catalog(write), _TURN)
    # Es entsteht ein Vorschlag ...
    assert result.proposal is not None
    assert result.proposal.summary == "Termin am Montag eintragen"
    assert result.pending_call.task == "daten_setzen"
    assert result.pending_call.arguments == {"tag": "Montag"}
    # ... propose wurde aufgerufen, execute NICHT (keine Veränderung ohne Bestätigung).
    assert write.propose_calls == [{"tag": "Montag"}]
    assert write.execute_calls == []


def test_EC_12_write_task_not_executed_even_if_model_claims_done():
    """EC-12: gegen abwegige Modell-Ausgabe — das Modell behauptet, die Aufgabe
    sei schon erledigt; ausgeführt wird trotzdem nichts ohne Bestätigung."""
    write = FakeWriteTask(name="daten_setzen")
    provider = FakeProvider([GenerationResponse(
        text="Ich habe das schon erledigt!",
        task_calls=[TaskCallBlock("c1", "daten_setzen", {})])])
    result = agent.run_turn([], _user(), provider, _catalog(write), _TURN)
    assert result.proposal is not None
    assert write.execute_calls == []


def test_EC_10_failing_propose_is_reported_not_raised():
    write = FakeWriteTask(name="daten_setzen", propose_error=ValueError("Eingabe fehlt"))
    provider = FakeProvider([
        task_call_response("daten_setzen"),
        text_response("Dafür brauche ich noch mehr Angaben."),
    ])
    result = agent.run_turn([], _user(), provider, _catalog(write), _TURN)
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert fed_back.is_error is True
    assert result.reply_text == "Dafür brauche ich noch mehr Angaben."


# -- EC-7/EC-8/EC-12: Katalog-Grenze gegen abwegige Modell-Ausgabe --

def test_EC_8_unknown_task_is_not_executed_and_reported():
    """EC-8/EC-12: ruft das Modell eine Aufgabe auf, die nicht im Katalog ist,
    wird sie nicht »kreativ« gelöst — die Grenze hängt nicht von der Ausgabe ab."""
    provider = FakeProvider([
        task_call_response("zaubere_geld_herbei"),
        text_response("Das kann ich leider nicht."),
    ])
    result = agent.run_turn([], _user(), provider, Catalog(), _TURN)
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert isinstance(fed_back, TaskResultBlock)
    assert fed_back.is_error is True
    assert "nicht im Katalog" in fed_back.content
    assert result.reply_text == "Das kann ich leider nicht."


def test_EC_7_honest_limit_when_no_task_fits():
    """EC-7: liegt eine Anfrage außerhalb der Aufgaben, antwortet der Agent
    schlicht mit Text — ohne erfundene Fähigkeiten."""
    provider = FakeProvider([text_response("Das gehört nicht zu meinen Aufgaben.")])
    result = agent.run_turn([], _user(), provider, Catalog(), _TURN)
    assert result.reply_text == "Das gehört nicht zu meinen Aufgaben."


# -- EC-13: nur Anfrage-Inhalt + Kontext gehen an den Anbieter ---

def test_EC_13_provider_receives_only_request_and_context():
    history = [Message("user", [TextBlock("frühere Anfrage")]),
               Message("assistant", [TextBlock("frühere Antwort")])]
    user = _user("neue Anfrage")
    provider = FakeProvider([text_response("ok")])
    agent.run_turn(history, user, provider, Catalog(), _TURN)
    sent = provider.requests[0]
    # genau Verlauf + neue Anfrage, nichts darüber hinaus
    assert sent.messages == history + [user]


# -- EC-14: Anbieter nicht erreichbar ----------------------------

def test_EC_14_provider_error_propagates():
    provider = FakeProvider([ProviderError("Zeitüberschreitung")])
    with pytest.raises(ProviderError):
        agent.run_turn([], _user(), provider, Catalog(), _TURN)


# -- E-EC-5: der Loop bricht sauber ab statt endlos zu schleifen --

def test_E_EC_5_loop_stops_at_iteration_limit():
    read = FakeReadTask(name="info_lesen")
    # Der Anbieter ruft in jeder Runde wieder eine Aufgabe auf.
    provider = FakeProvider([task_call_response("info_lesen") for _ in range(2)])
    result = agent.run_turn([], _user(), provider, _catalog(read), _TURN, max_iterations=2)
    assert result.proposal is None
    assert result.reply_text is not None   # sauberer Abbruch-Hinweis


# -- EC-22: bei Mehrdeutigkeit erst rückfragen, statt Varianten auszubreiten --

def test_EC_22_agent_prompt_instructs_to_ask_back_on_ambiguity():
    """EC-22 (#95): der System-Prompt enthält die Verhaltensregel, dass der
    Agent bei Mehrdeutigkeit (z. B. Geräte-Varianten) erst zurückfragt, bevor
    er ein Werkzeug aufruft oder antwortet — die Regel ist hier nur deshalb
    überhaupt prüfbar, weil sie als Klartext-Anweisung im Prompt steht (statt
    sich in jeder Aufgabe einzeln zu wiederholen)."""
    prompt = agent.SYSTEM_PROMPT
    assert "Geräte-Varianten" in prompt
    assert "fehlenden Kontext" in prompt
    # Mehrere Varianten gleichzeitig auszubreiten ist ausdrücklich verboten.
    assert "mehrere Varianten gleichzeitig" in prompt.lower() \
        or "niemals mehrere varianten gleichzeitig" in prompt.lower()


def test_EC_22_agent_prompt_instructs_to_apologise_on_dead_end():
    """EC-22 (#95): merkt der Agent, dass er einen Holzweg eingeschlagen hat
    (Beispiel iOS-Telegram-Falle 2026-05-24), entschuldigt er sich kurz und
    macht weiter — keine stille Korrektur. Die Regel steht im Prompt."""
    prompt = agent.SYSTEM_PROMPT
    assert "Holzweg" in prompt
    assert "entschuldige" in prompt.lower()


def test_agent_prompt_forbids_natural_language_confirmation_prefetch():
    """Issue #158: Der LLM darf NICHT in seiner natürlich-sprachlichen Antwort
    nach Bestätigung fragen, bevor er das Werkzeug aufruft — sonst entsteht
    eine Doppel-Bestätigung (erst LLM-Frage, dann deterministisches EC-10-
    Gate). Die Regel steht als Lebenszeichen im System-Prompt; das echte
    Modell-Verhalten ist über den Prompt erzwingbar, der Test prüft die
    Anwesenheit der Regel."""
    prompt = agent.SYSTEM_PROMPT.lower()
    # Direkt-Aufruf-Anweisung statt Sprach-Vorabfrage.
    assert "direkt" in prompt
    # Negation der Sprach-Vorabfrage („nicht zuerst", „nicht vorher" o. ä.)
    assert "nicht zuerst" in prompt or "nicht vorher" in prompt
    # Verweis auf die deterministische Bestätigung — damit klar ist, WARUM
    # die Vorabfrage entfällt.
    assert "deterministisch" in prompt or "system holt" in prompt


def test_agent_does_not_double_confirm_when_model_calls_tool_directly():
    """Issue #158 — Verhalten: Wenn das Modell der Anweisung folgt und einen
    schreibenden Tool-Call DIREKT ausgibt (ohne natürlich-sprachliche
    Vorabfrage), liefert der Agent einen Proposal — ohne dass eine zusätzliche
    Bestätigungs-Frage in der Antwort steckt. Das deterministische EC-10-Gate
    fragt erst danach."""
    write = FakeWriteTask(name="kalender_verbinden", summary="Kalender verbinden")
    provider = FakeProvider([
        # Modell folgt der Regel: KEIN Text, der nach „ja" fragt — direkt Tool-Call.
        task_call_response("kalender_verbinden", arguments={}),
    ])
    result = agent.run_turn([], _user("kann ich einen Kalender integrieren?"),
                            provider, _catalog(write), _TURN)
    # Genau ein Proposal — keine zweite Sprach-Vorabfrage des LLM dazwischen.
    assert result.proposal is not None
    assert result.reply_text is None
    # Aufgabe ist nicht ausgeführt (EC-10) — erst Bestätigung, dann execute.
    assert write.execute_calls == []
    # Nur ein einziger Provider-Call passierte — das Modell hat NICHT zuerst
    # eine Sprach-Vorabfrage gebaut, auf die der Nutzer antworten müsste.
    assert len(provider.requests) == 1


def test_agent_run_turn_calls_before_provider_call_hook_each_round():
    """Issue #156: `run_turn` ruft den optionalen `before_provider_call`-Hook
    vor JEDEM Provider-Call — auch in Tool-Loop-Iterationen. main.py nutzt
    den Hook für den Telegram-Typing-Indikator (sonst läuft er nach ~5 s aus)."""
    read = FakeReadTask(name="info_lesen", result="42")
    provider = FakeProvider([
        task_call_response("info_lesen"),
        text_response("Die Antwort ist 42."),
    ])
    calls = []
    agent.run_turn([], _user(), provider, _catalog(read), _TURN,
                   before_provider_call=lambda: calls.append("typing"))
    # Zwei Provider-Calls ⇒ Hook zweimal gerufen.
    assert calls == ["typing", "typing"]


def test_agent_run_turn_swallows_hook_errors():
    """Issue #156: der Hook ist Komfort, kein Gate — wirft er, läuft der Turn
    trotzdem durch (Telegram-Fehler im Typing-Indikator dürfen die Antwort
    nicht blockieren)."""
    provider = FakeProvider([text_response("ok")])

    def boom():
        raise RuntimeError("Telegram down")

    result = agent.run_turn([], _user(), provider, Catalog(), _TURN,
                            before_provider_call=boom)
    assert result.reply_text == "ok"


def test_EC_22_agent_asks_back_when_model_signals_missing_context():
    """EC-22 (#95): Ein Test gegen das Verhalten — bekommt der Agent vom
    Modell statt eines Tool-Aufrufs eine gezielte Rückfrage zurück, gibt er
    diese Frage als Antwort weiter (statt mit einem ungezielten Standardtext
    eine Variantensammlung auszubreiten). Das prüft hier vor allem, dass die
    Test-Doppelung des Modells einen passenden Rückfrage-Lauf abbilden kann —
    in echt formuliert der LLM die Rückfrage anhand des Prompts."""
    # Aufgabe ist registriert, aber das Modell ruft sie nicht direkt auf —
    # es fragt erst zurück.
    read = FakeReadTask(name="ca_verteilen", result="ausgeliefert")
    provider = FakeProvider([
        text_response("Auf welchem Gerät möchtest du das Zertifikat installieren?")])
    result = agent.run_turn([], _user("schick mir bitte das Zertifikat"),
                            provider, _catalog(read), _TURN)
    # Antwort ist die Rückfrage — keine Aufgabe ausgeführt.
    assert result.reply_text.startswith("Auf welchem Gerät")
    assert read.run_calls == []
    assert result.proposal is None


# ============================================================
#  #310 — AgentResult.transcript trägt den vollen Tool-Turn-Verlauf
# ============================================================

def test_issue_310_transcript_excludes_loaded_history():
    """AC2: das Transkript enthält nur den NEUEN Turn (ab user_message), nicht
    die geladene History — sonst würde die Orchestrierung History doppeln."""
    history = [Message("user", [TextBlock("alt")]),
               Message("assistant", [TextBlock("alte Antwort")])]
    user = _user("neue Anfrage")
    provider = FakeProvider([text_response("ok")])
    result = agent.run_turn(history, user, provider, Catalog(), _TURN)
    # Element 0 ist die neue user_message, dann der finale Assistant-Text.
    assert result.transcript[0] is user
    assert [m.role for m in result.transcript] == ["user", "assistant"]
    assert result.transcript[-1].blocks[0].text == "ok"


def test_issue_310_transcript_carries_tool_turns_in_order():
    """AC2: bei einer lesenden Aufgabe trägt das Transkript in Loop-Reihenfolge
    user → assistant(tool_use) → user(tool_result) → assistant(text)."""
    read = FakeReadTask(name="info_lesen", result="22 Grad")
    user = _user("wie warm?")
    provider = FakeProvider([
        task_call_response("info_lesen", call_id="c-1"),
        text_response("Es sind 22 Grad."),
    ])
    result = agent.run_turn([], user, provider, _catalog(read), _TURN)

    t = result.transcript
    assert [m.role for m in t] == ["user", "assistant", "user", "assistant"]
    assert t[0] is user
    call = t[1].blocks[-1]
    assert isinstance(call, TaskCallBlock)
    assert call.call_id == "c-1"
    res = t[2].blocks[0]
    assert isinstance(res, TaskResultBlock)
    assert res.call_id == "c-1"
    assert t[3].blocks[0].text == "Es sind 22 Grad."


def test_issue_310_proposal_transcript_pairs_tool_use():
    """AC-FIX1 + AC-FIX4 (T310-S3): auf dem proposal-Pfad bleibt das WRITE-
    tool_use im Transkript SICHTBAR (nicht weggelassen — sonst sähe das Modell
    für Schreib-Aufgaben wieder nur Text, dieselbe Vergiftung) UND es ist
    GEPAART: direkt danach ein synthetischer tool_result mit derselben call_id.
    Der reine Vorschlagstext ist NICHT Teil des Transkripts (den hängt die
    Orchestrierung an)."""
    write = FakeWriteTask(name="termin", summary="Termin eintragen")
    user = _user("trag einen Termin ein")
    provider = FakeProvider([task_call_response("termin", call_id="c-7")])
    result = agent.run_turn([], user, provider, _catalog(write), _TURN)

    assert result.proposal is not None
    t = result.transcript
    # user → assistant(tool_use) → user(synth. tool_result) — paarig.
    assert [m.role for m in t] == ["user", "assistant", "user"]
    assert t[0] is user
    call = t[1].blocks[-1]
    assert isinstance(call, TaskCallBlock)   # AC-FIX4: tool_use sichtbar
    assert call.call_id == "c-7"
    res = t[2].blocks[0]
    assert isinstance(res, TaskResultBlock)
    assert res.call_id == "c-7"              # AC-FIX1: gepaart
    assert res.is_error is False
    # EC-7: der synthetische Result behauptet NICHT, der Write sei ausgeführt.
    assert "eingetragen" not in res.content.lower()
    assert "erledigt" not in res.content.lower()


def test_issue_310_transcript_does_not_mutate_provider_request():
    """AC2/EC-13: der finale Antwort-Block landet im Transkript, NICHT
    nachträglich in der provider-sichtbaren Anfrage. Sonst würde der letzte
    Provider-Request um einen Block wachsen, den er nie gesehen hat."""
    user = _user("neue Anfrage")
    provider = FakeProvider([text_response("ok")])
    result = agent.run_turn([], user, provider, Catalog(), _TURN)
    # Die letzte (einzige) Anfrage sah genau [user] — kein Antwort-Block.
    assert provider.requests[0].messages == [user]
    # Das Transkript dagegen trägt den Antwort-Block.
    assert result.transcript[-1].blocks[0].text == "ok"


# ============================================================
#  #331 — _proposal_pending ist parametrisiert und frei von
#          „erst nach Bestätigung"-Framing
# ============================================================

def test_issue_331_proposal_pending_contains_task_name():
    """AC1/AC3(i) #331: der erzeugte synthetische tool_result-Text enthält
    den konkreten Task-Namen — das Modell erkennt in Folge-Turns, WELCHES
    Werkzeug erneut aufzurufen ist."""
    text = agent._proposal_pending("geraet_anlegen")
    assert "geraet_anlegen" in text


def test_issue_331_proposal_pending_directs_to_call_tool():
    """AC3(ii) #331: der Text trägt die Schlüssel-Direktive, das Werkzeug
    aufzurufen (nicht den Dialog selbst zu führen)."""
    text = agent._proposal_pending("mein_werkzeug")
    # Werkzeug führt den Dialog selbst
    assert "werkzeug" in text.lower()
    # Direktive: Werkzeug aufrufen
    assert "rufe" in text.lower() or "aufrufen" in text.lower() \
        or "ruf" in text.lower()


def test_issue_331_proposal_pending_no_erst_nach_bestaetigung_framing():
    """AC3(iii) #331: das alte „erst nach Bestätigung"-Framing ist nicht mehr
    im Text — es hatte das Modell dazu gebracht, auf ein „Ja" zu warten statt
    das Werkzeug erneut aufzurufen."""
    text = agent._proposal_pending("irgendeine_aufgabe")
    assert "erst nach bestätigung" not in text.lower()
    assert "nach bestätigung" not in text.lower()


def test_issue_331_proposal_pending_emitted_with_task_name_in_transcript():
    """AC1 (entry_path_probe) #331: der tatsächlich in den synthetischen
    TaskResultBlock eingefügte Text enthält den Task-Namen der aufgerufenen
    WRITE-Aufgabe (nicht einen fixen String)."""
    write = FakeWriteTask(name="kalender_verbinden", summary="Kalender verbinden")
    provider = FakeProvider([task_call_response("kalender_verbinden",
                                                call_id="c-99")])
    result = agent.run_turn([], _user("verbinde Kalender"),
                            provider, _catalog(write), _TURN)

    assert result.proposal is not None
    # Das Transkript: user → assistant(tool_use) → user(synth. tool_result)
    t = result.transcript
    synth_result = t[2].blocks[0]
    assert isinstance(synth_result, TaskResultBlock)
    assert synth_result.call_id == "c-99"
    assert synth_result.is_error is False
    # Der Text muss den Task-Namen enthalten (AC1)
    assert "kalender_verbinden" in synth_result.content
    # Altes Framing darf nicht mehr da sein (AC3(iii))
    assert "erst nach bestätigung" not in synth_result.content.lower()


# ============================================================
#  EC-30 — Welt-Wissen für allgemeine Anfragen, XBuddy-Zustand bleibt Katalog-only
# ============================================================

def test_welt_wissen_pfad_ohne_tool():
    """AC2 (EC-30): Eine allgemeine Wissensfrage ohne XBuddy-Bezug führt zu einer
    direkten Antwort ohne Tool-Aufruf. Das Modell muss kein Werkzeug aufrufen,
    um z. B. eine technische Anleitung zu liefern."""
    provider = FakeProvider([
        text_response(
            "Um ein CA-Zertifikat auf iOS 12 zu installieren: "
            "Einstellungen → Allgemein → Über → Zertifikat-Vertrauens-Einstellungen."
        )
    ])
    result = agent.run_turn(
        [], _user("Wie installiere ich ein CA-Zertifikat auf einem alten iPhone?"),
        provider, Catalog(), _TURN)
    # Direkte Antwort, kein Proposal, kein Tool-Aufruf.
    assert result.reply_text is not None
    assert "Zertifikat" in result.reply_text
    assert result.proposal is None
    # Genau ein Provider-Call, kein Werkzeug wurde aufgerufen.
    assert len(provider.requests) == 1


def test_xbuddy_zustand_bleibt_katalog():
    """AC3 (EC-30): Eine Anfrage nach XBuddy-Zustand (z. B. Geburtstag eines
    Familien-Mitglieds) wird über eine Katalog-Aufgabe abgewickelt, nicht aus
    Welt-Wissen. Welt-Wissen kennt keine familienspezifischen Daten."""
    geburtstag_task = FakeReadTask(
        name="geburtstage_lesen",
        result="Morgen hat Paul Geburtstag.")
    provider = FakeProvider([
        task_call_response("geburtstage_lesen", arguments={}),
        text_response("Morgen hat Paul Geburtstag."),
    ])
    result = agent.run_turn(
        [], _user("Wer hat morgen Geburtstag?"),
        provider, _catalog(geburtstag_task), _TURN)
    # Die Aufgabe wurde aufgerufen (Katalog-Pfad, nicht Welt-Wissen).
    assert geburtstag_task.run_calls == [{}]
    # Antwort basiert auf dem Katalog-Ergebnis.
    assert result.reply_text == "Morgen hat Paul Geburtstag."
    assert result.proposal is None


def test_EC_30_system_prompt_enthält_trennlinie():
    """AC1 (EC-30): Der System-Prompt enthält die explizite Trennlinie zwischen
    XBuddy-Zustand (Katalog) und Welt-Wissen (direkt), damit das LLM die
    richtige Pfad-Wahl trifft."""
    prompt = agent.SYSTEM_PROMPT
    # Trennlinie muss explizit benannt sein.
    assert "XBuddy-Zustand" in prompt
    assert "Katalog" in prompt or "Katalog-Aufgabe" in prompt
    # Welt-Wissen-Pfad ist explizit erlaubt.
    assert "Wissen" in prompt
    # XBuddy-Zustands-Beispiele müssen als Katalog-Pflicht markiert sein.
    assert "Kalender" in prompt or "Familien-Mitglieder" in prompt
    # EC-22-Geist (gezielte Rückfrage, keine Varianten) bleibt erhalten.
    assert "fehlenden Kontext" in prompt
    assert "Niemals mehrere Varianten" in prompt or "niemals mehrere varianten" in prompt.lower()


# ============================================================
#  EC-35 — task_events Insert-Pfad in run_turn (Refs #724)
# ============================================================

class _FakeTaskEventsStore:
    """Minimale Test-Doppelung für TaskEventsStore (EC-35)."""

    def __init__(self):
        self.inserts = []   # [(task_name, chat_id, outcome)]

    def insert(self, task_name, chat_id, outcome):
        self.inserts.append((task_name, chat_id, outcome))


def test_EC35_no_store_no_insert():
    """AC3: task_events_store=None (Default) → kein Insert, kein Fehler.
    Sandbox-Verträglichkeit: der Default-Pfad ohne Store bleibt völlig
    unchanged."""
    read = FakeReadTask(name="info_lesen", result="Ergebnis")
    provider = FakeProvider([
        task_call_response("info_lesen"),
        text_response("ok"),
    ])
    # Kein Store → kein Fehler, Ergebnis wie bisher.
    result = agent.run_turn([], _user(), provider, _catalog(read), _TURN)
    assert result.reply_text == "ok"


def test_EC35_single_skill_call_inserts_success(tmp_path):
    """AC2: ein Skill-Call im Turn → genau 1 Insert mit outcome='success'."""
    store = _FakeTaskEventsStore()
    read = FakeReadTask(name="info_lesen", result="42")
    provider = FakeProvider([
        task_call_response("info_lesen"),
        text_response("Die Antwort ist 42."),
    ])
    agent.run_turn([], _user(), provider, _catalog(read), _TURN,
                   task_events_store=store)

    assert len(store.inserts) == 1
    name, chat_id, outcome = store.inserts[0]
    assert name == "info_lesen"
    assert chat_id == 42           # TurnContext.chat_id = 42
    assert outcome == "success"


def test_EC35_two_calls_same_skill_one_insert():
    """AC4 (Deduplizierung): ein Turn mit zwei Aufrufen desselben Skills →
    genau 1 Insert. Der Anker ist 'Familie hat diesen Skill genutzt',
    nicht 'LLM hat einmal getoolt'."""
    store = _FakeTaskEventsStore()
    read = FakeReadTask(name="seiten_uebersicht", result="Seite A")
    provider = FakeProvider([
        # Erste Iteration: Skill aufgerufen.
        task_call_response("seiten_uebersicht", call_id="c-1"),
        # Zweite Iteration: NOCHMALS derselbe Skill.
        task_call_response("seiten_uebersicht", call_id="c-2"),
        text_response("Fertig."),
    ])
    agent.run_turn([], _user(), provider, _catalog(read), _TURN,
                   task_events_store=store)

    # Nur 1 Insert trotz 2 Aufrufen.
    assert len(store.inserts) == 1
    assert store.inserts[0][0] == "seiten_uebersicht"
    assert store.inserts[0][2] == "success"


def test_EC35_failing_skill_inserts_error():
    """AC2: Skill wirft → 1 Insert mit outcome='error'."""
    store = _FakeTaskEventsStore()
    read = FakeReadTask(name="info_lesen", result=RuntimeError("Quelle weg"))
    provider = FakeProvider([
        task_call_response("info_lesen"),
        text_response("Das hat nicht geklappt."),
    ])
    agent.run_turn([], _user(), provider, _catalog(read), _TURN,
                   task_events_store=store)

    assert len(store.inserts) == 1
    assert store.inserts[0][0] == "info_lesen"
    assert store.inserts[0][2] == "error"


def test_EC35_write_proposal_inserts_abort():
    """AC2: WRITE-Vorschlag (pending proposal) → Insert mit outcome='abort'
    für den involvierten Skill."""
    store = _FakeTaskEventsStore()
    write = FakeWriteTask(name="termin_eintragen", summary="Termin am Dienstag")
    provider = FakeProvider([task_call_response("termin_eintragen")])
    result = agent.run_turn([], _user(), provider, _catalog(write), _TURN,
                            task_events_store=store)

    assert result.proposal is not None
    assert len(store.inserts) == 1
    assert store.inserts[0][0] == "termin_eintragen"
    assert store.inserts[0][2] == "abort"


def test_EC35_two_different_skills_two_inserts():
    """AC2: zwei verschiedene Skills in einem Turn → zwei separate Inserts."""
    store = _FakeTaskEventsStore()
    read_a = FakeReadTask(name="skill_a", result="A")
    read_b = FakeReadTask(name="skill_b", result="B")

    from model import GenerationResponse, TaskCallBlock
    # Beide Skills werden in einer einzigen Provider-Antwort aufgerufen.
    provider = FakeProvider([
        GenerationResponse(
            text="",
            task_calls=[
                TaskCallBlock(call_id="c-a", task="skill_a", arguments={}),
                TaskCallBlock(call_id="c-b", task="skill_b", arguments={}),
            ]),
        text_response("Beide Skills liefen."),
    ])
    agent.run_turn([], _user(), provider, _catalog(read_a, read_b), _TURN,
                   task_events_store=store)

    inserted_names = {r[0] for r in store.inserts}
    assert inserted_names == {"skill_a", "skill_b"}
    assert len(store.inserts) == 2
    for _, chat_id, outcome in store.inserts:
        assert outcome == "success"
        assert chat_id == 42


def test_EC35_no_insert_when_no_skill_called():
    """Kein Insert, wenn der Provider keinen Tool-Call macht (reine Text-
    Antwort). Ein leerer Turn soll keine leere Zeile in task_events hinterlassen."""
    store = _FakeTaskEventsStore()
    provider = FakeProvider([text_response("Hallo!")])
    agent.run_turn([], _user(), provider, Catalog(), _TURN,
                   task_events_store=store)
    assert store.inserts == []


def test_EC35_chat_id_passed_correctly_from_turn_context():
    """AC2: chat_id kommt aus turn_context.chat_id — nicht hartcodiert."""
    store = _FakeTaskEventsStore()
    read = FakeReadTask(name="info_lesen", result="X")
    provider = FakeProvider([
        task_call_response("info_lesen"),
        text_response("ok"),
    ])
    turn = TurnContext(chat_id=9999)
    agent.run_turn([], _user(), provider, _catalog(read), turn,
                   task_events_store=store)

    assert len(store.inserts) == 1
    assert store.inserts[0][1] == 9999


# ============================================================
#  TASK-10c Form (b) — Framework-Übersetzer
# ============================================================

class _FakeTg:
    """Minimale tg-Doppelung für Form-(b)-Übersetzer-Tests."""

    def __init__(self):
        self.inline_sent = []
        self.sent = []

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.inline_sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"message_id": 9001}

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 9002}


class _FormBReadTask(FakeReadTask):
    """Fake-Task, der ein Form-(b)-Dict zurückgibt."""

    def __init__(self, name="form_b_task", text="Hallo Welt",
                 presentation=None):
        super().__init__(name=name, result=None)
        self._form_b = {
            "text": text,
            "presentation": presentation if presentation is not None else {
                "inline_button": {
                    "label": "🛒 Klick mich",
                    "web_app_url": "https://example.com/app",
                }
            },
        }

    def run(self, arguments, turn_context):
        self.run_calls.append(arguments)
        self.turn_contexts.append(turn_context)
        return self._form_b


def test_AC5_form_b_dict_ruft_send_inline_keyboard():
    """AC5/TASK-10c: run_turn erkennt Form-(b)-Dict + ruft send_inline_keyboard via tg."""
    task = _FormBReadTask()
    tg = _FakeTg()
    turn = TurnContext(chat_id=42)
    provider = FakeProvider([
        task_call_response("form_b_task"),
        text_response("Erledigt."),
    ])

    result = agent.run_turn([], _user(), provider, _catalog(task), turn, tg=tg)

    assert len(tg.inline_sent) == 1
    assert tg.inline_sent[0]["chat_id"] == 42
    assert "Hallo Welt" in tg.inline_sent[0]["text"]
    assert result.reply_text == "Erledigt."


def test_AC5_form_b_content_ist_quittungs_string():
    """AC5/TASK-10c: Nach dem Übersetzen liegt ein String-content im TaskResultBlock."""
    task = _FormBReadTask()
    tg = _FakeTg()
    turn = TurnContext(chat_id=42)
    provider = FakeProvider([
        task_call_response("form_b_task", call_id="c-fb"),
        text_response("ok"),
    ])

    agent.run_turn([], _user(), provider, _catalog(task), turn, tg=tg)

    # Das Framework hat den Dict durch render_form_b ersetzt.
    # Der dem Anbieter zurückgespiesene Tool-Result muss ein String sein.
    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert isinstance(fed_back, TaskResultBlock)
    assert isinstance(fed_back.content, str), "content muss nach Form-(b)-Übersetzung String sein"
    assert fed_back.is_error is False


def test_AC2_unbekannter_presentation_key_fallback_auf_send_message():
    """AC2/TASK-10c: Unbekannter presentation-Schlüssel → Fallback auf send_message."""
    task = _FormBReadTask(
        text="Fallback-Text",
        presentation={"unbekannte_variante": {"label": "test"}})
    tg = _FakeTg()
    turn = TurnContext(chat_id=42)
    provider = FakeProvider([
        task_call_response("form_b_task"),
        text_response("ok"),
    ])

    agent.run_turn([], _user(), provider, _catalog(task), turn, tg=tg)

    # Unbekannter Schlüssel → nur send_message, kein send_inline_keyboard.
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 1
    assert tg.sent[0]["text"] == "Fallback-Text"


def test_AC2_leeres_presentation_fallback_auf_send_message():
    """AC2/TASK-10c: Leeres presentation → Fallback auf send_message (nur Text)."""
    task = _FormBReadTask(text="Nur Text", presentation={})
    tg = _FakeTg()
    turn = TurnContext(chat_id=42)
    provider = FakeProvider([
        task_call_response("form_b_task"),
        text_response("ok"),
    ])

    agent.run_turn([], _user(), provider, _catalog(task), turn, tg=tg)

    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 1
    assert tg.sent[0]["text"] == "Nur Text"


def test_AC5_form_b_ohne_tg_fallback_auf_text_als_content():
    """AC5: Wenn kein tg übergeben wird, nutzt Framework text als content-Fallback."""
    task = _FormBReadTask(text="Fallback ohne tg")
    turn = TurnContext(chat_id=42)
    provider = FakeProvider([
        task_call_response("form_b_task"),
        text_response("ok"),
    ])

    # tg=None (Standard ohne tg-Parameter)
    agent.run_turn([], _user(), provider, _catalog(task), turn)

    fed_back = provider.requests[1].messages[-1].blocks[0]
    assert isinstance(fed_back, TaskResultBlock)
    assert fed_back.content == "Fallback ohne tg"


def test_AC5_webapp_link_presentation():
    """AC2/AC5/TASK-10c: webapp_link-Schlüssel → send_inline_keyboard analog inline_button."""
    task = _FormBReadTask(
        text="WebApp öffnen",
        presentation={"webapp_link": {"label": "Öffnen", "url": "https://example.com/wa"}})
    tg = _FakeTg()
    turn = TurnContext(chat_id=42)
    provider = FakeProvider([
        task_call_response("form_b_task"),
        text_response("ok"),
    ])

    agent.run_turn([], _user(), provider, _catalog(task), turn, tg=tg)

    assert len(tg.inline_sent) == 1
    assert tg.inline_sent[0]["text"] == "WebApp öffnen"
    buttons = tg.inline_sent[0]["buttons"]
    assert buttons[0]["label"] == "Öffnen"
    assert buttons[0]["web_app_url"] == "https://example.com/wa"


# ============================================================
#  T942 — EC-10 A2-Undo-Hinweis + EC-36-Korrektur-State-Klarheit
# ============================================================

def test_T942_system_prompt_enthält_a2_undo_hinweis_wortwörtlich_regel():
    """AC1 (T942): SYSTEM_PROMPT enthält die Regel, dass Zeilen mit dem Wort
    `falsch` aus Skill-Results wortwörtlich an die Familie übernommen werden —
    nicht kürzen, nicht umformulieren (EC-10 A2)."""
    prompt = agent.SYSTEM_PROMPT
    # Kernbegriff der Regel
    assert "falsch" in prompt
    # Wortwörtlich-Direktive
    assert "wortwörtlich" in prompt or "wortwoertlich" in prompt
    # Negation von Kürzen/Umformulieren
    assert "nicht kürzen" in prompt or "nicht umformulieren" in prompt


def test_T942_correction_suffix_enthält_klarheit_zur_rueckname():
    """AC2 (T942): _correction_system_suffix-Output enthält den Hinweis, dass
    die betreffenden Ressourcen NICHT als noch vorhanden zu erwähnen sind und
    auf die vorherige Bot-Quittung verwiesen wird (EC-36 — Ambiguitäts-Fall
    Z. 547-548 ist abgedeckt: Watchdog T942-S1-W Befund 1 Pragma-Fix).
    Live-Bug: Bot fragte 'Soll ich Spültabs wieder runternehmen?', obwohl
    Items bereits per DELETE entfernt waren."""
    from confirm import CorrectionState  # nur für den Test importiert
    state = CorrectionState(last_skill="einkauf_hinzufuegen",
                            last_args={}, quelle="a2")
    suffix = agent._correction_system_suffix(state)
    # Negation: entfernte Ressourcen NICHT als vorhanden erwähnen
    assert "NICHT als noch vorhanden" in suffix
    # Anker: verlass dich auf die vorherige Quittung (Ambiguitäts-Fall mit ehrlicher Quittung)
    assert "vorherigen Bot-Quittung" in suffix
    # kein erneutes Löschen
    assert "nicht nach erneutem Löschen" in suffix


# ============================================================
#  E-HOE-2 / T1048 — Agent-Integrations-Test: Direkt-Trigger-Pfad
#
#  Prüft den Live-Pfad "Direkt-Trigger → hoerspiel_oeffnen(tab='einstellungen')
#  Tool-Call + Agent-Text ohne 'Knopf unten'" via FakeProvider + FakeReadTask.
#  EC-17: kein echtes LLM nötig — FakeProvider liefert den skriptierten
#  Tool-Call; die echte run()-Implementierung des Task (mit FakeHoerspielClient)
#  liefert das echte Form-(b)-Dict zurück.
# ============================================================

class _FakeHoerspielClientForAgent:
    """Minimale HoerspielClient-Doppelung für den Agent-Integrations-Test."""

    def __init__(self):
        self.alben_calls = 0

    def alben_lesen(self):
        self.alben_calls += 1
        return []


def test_E_HOE_2_direkt_trigger_agent_ruft_hoerspiel_oeffnen_mit_einstellungen():
    """E-HOE-2 / T1048 (AC7) — HSP-53 Update (Refs #1294):
    Tab-Hash-Modell superseded; hoerspiel_oeffnen hat kein tab-Argument mehr.
    Agent-Tool-Call ohne tab → Task öffnet Player-PWA, alben_lesen() wird aufgerufen.

    Setup: FakeProvider skriptiert den Tool-Call (EC-17 — kein echtes LLM).
    """
    from unittest.mock import MagicMock

    from skills.hoerspiel_oeffnen_task import HoerspielOeffnenTask

    hoerspiel_client = _FakeHoerspielClientForAgent()
    tg = MagicMock()
    task = HoerspielOeffnenTask(
        tg=tg,
        hoerspiel_client=hoerspiel_client,
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com",
    )

    # HSP-53: kein tab-Argument mehr; leere arguments
    provider = FakeProvider([
        task_call_response("hoerspiel_oeffnen",
                           arguments={},
                           call_id="c-hoe-1"),
        text_response("Hier ist der Link zum Hörspiel-Player."),
    ])
    turn = TurnContext(chat_id=42, from_user_id=7)
    result = agent.run_turn(
        [],
        _user("schick mir die Hörbuch settings"),
        provider,
        _catalog(task),
        turn,
    )

    # Task wurde ausgeführt — agent.run_turn liefert ein Ergebnis
    assert result.reply_text is not None
    # HSP-53: Player-PWA-Pfad immer über alben_lesen() → alben_calls >= 1
    assert hoerspiel_client.alben_calls >= 1


def test_E_HOE_2_direkt_trigger_agent_text_enthaelt_nicht_knopf_unten():
    """E-HOE-2 / T1048 (AC7): Agent-Text nach Direkt-Trigger enthält NICHT
    'Knopf unten', 'klick' oder 'Button' (Phantom-Button-Versprechen).

    Der skriptierte LLM-Text wird direkt als reply_text zurückgegeben —
    Tests prüfen Wortlisten-Drift in der Agent-Antwort.
    """
    from unittest.mock import MagicMock

    from skills.hoerspiel_oeffnen_task import HoerspielOeffnenTask

    hoerspiel_client = _FakeHoerspielClientForAgent()
    tg = MagicMock()
    task = HoerspielOeffnenTask(
        tg=tg,
        hoerspiel_client=hoerspiel_client,
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com",
    )

    # Skriptierter LLM-Text: so wie ein gut instruiertes Modell antworten würde
    # HSP-53: kein tab-Argument mehr
    agent_antwort = "Hier ist der Link zu den Hörspiel-Einstellungen."
    provider = FakeProvider([
        task_call_response("hoerspiel_oeffnen",
                           arguments={},
                           call_id="c-hoe-2"),
        text_response(agent_antwort),
    ])
    turn = TurnContext(chat_id=42, from_user_id=7)
    result = agent.run_turn(
        [],
        _user("schick mir die Hörbuch settings"),
        provider,
        _catalog(task),
        turn,
    )

    text = result.reply_text or ""
    assert "Knopf unten" not in text, (
        "Agent-Text darf 'Knopf unten' nicht enthalten (Phantom-Button-Versprechen)")
    assert "klick" not in text.lower(), (
        "Agent-Text darf 'klick' nicht enthalten")
    assert "Button" not in text, (
        "Agent-Text darf 'Button' nicht enthalten (Phantom-Button-Versprechen)")


# ============================================================
#  EC-40 / #1105 — Trigger-Vokabular-Heimat im SYSTEM_PROMPT
#
#  EC-40 Soll-Norm: positives Trigger-Vokabular gehört allein in
#  die Tool-description; der System-Prompt trägt nur Negativ-/
#  Verweis-Routing (eltern-chat.md:1513-1518).
# ============================================================

def test_EC40_1105_system_prompt_traegt_keine_positiven_trigger_phrasen():
    """EC-40 / #1105 (AC3): Der SYSTEM_PROMPT enthält die positiven
    Direkt-Settings-Trigger-Phrasen (»schick mir die settings« etc.) und
    die Hörspiel-Folgen-Öffnen-Phrasen (»Hörbuch hören« etc.) NICHT mehr —
    sie sind aus dem doppelten Pflege-Ort entfernt und leben allein in der
    Tool-description von hoerspiel_oeffnen_task.py (EC-40 Implementations-Pfad).
    """
    prompt = agent.SYSTEM_PROMPT
    # Positive Direkt-Settings-Phrasen dürfen NICHT im System-Prompt stehen.
    assert "schick mir die Hörbuch settings" not in prompt, (
        "EC-40/T1105: positive Settings-Trigger-Phrase darf nicht im SYSTEM_PROMPT stehen")
    assert "Direkt-Trigger-Phrasen" not in prompt, (
        "EC-40/T1105: positive Trigger-Phrasen-Liste darf nicht im SYSTEM_PROMPT stehen")
    # Positive Hörspiel-Folgen-Phrasen dürfen NICHT im System-Prompt stehen.
    assert "Hörspiel-Folgen-Öffnen" not in prompt, (
        "EC-40/T1105: positive Folgen-Öffnen-Sektion darf nicht im SYSTEM_PROMPT stehen")
    assert "Hörbuch hören" not in prompt, (
        "EC-40/T1105: positive Folgen-Trigger-Phrase darf nicht im SYSTEM_PROMPT stehen")


def test_EC40_1105_system_prompt_traegt_negativ_regel():
    """EC-40 / #1105 (AC3): Der SYSTEM_PROMPT enthält weiter die
    Negativ-/Anti-Redundanz-Regel (EC-40 Soll-Norm): kein Settings-Inhalt
    im Chat-Text, beiläufige Erwähnung → sprachlicher Verweis OHNE Tool-Call.
    """
    prompt = agent.SYSTEM_PROMPT
    # Anti-Redundanz: kein Settings-Inhalt im Chat-Text.
    assert "kein Settings-Inhalt im Chat-Text" in prompt, (
        "EC-40/T1105: Negativ-Regel 'kein Settings-Inhalt' muss im SYSTEM_PROMPT bleiben")
    # Beiläufige-Erwähnung-Verweis-Regel bleibt.
    assert "Beiläufige Settings-Erwähnung" in prompt, (
        "EC-40/T1105: Anti-Redundanz-Grundregel 'Beiläufige Settings-Erwähnung' muss bleiben")
    assert "sprachlicher Verweis OHNE Tool-Call" in prompt, (
        "EC-40/T1105: Negativ-Routing 'sprachlicher Verweis OHNE Tool-Call' muss bleiben")


# ============================================================
#  EC-40 / #1283 — Positiv-Heimat: description trägt Trigger-Vokabular
#
#  EC-40 Positiv-Norm: die Tool-description von hoerspiel_oeffnen
#  ist die einzige Heimat des positiven Trigger-Vokabulars.
#  Dieser Test petrankert, dass sie die Kern-Begriffe beider
#  Trigger-Familien enthält — schlägt beim Editieren der
#  description fehl, wenn das Vokabular verloren geht.
# ============================================================


def test_EC40_1283_description_traegt_positives_trigger_vokabular():
    """EC-40 / #1283 (AC1+AC2): Die Tool-description von HoerspielOeffnenTask
    enthält das Kern-Trigger-Vokabular beider Familien:

    - Folgen-Trigger: 'hörbuch hören' (kanonische Beispiel-Phrase) und 'folge'
      (Kern-Begriff; deckt 'folge starten', 'folge abspielen', 'folge' ab).
    - Direkt-Settings-Trigger: 'settings' und 'einstellungen'
      (beide Schreibweisen aus dem Direkt-Settings-Abschnitt).

    Geprüft an der realen task.description-Quelle — kein hartkodiertes
    Duplikat der Phrasen-Liste im Test (AC2). Verliert eine spätere
    description-Änderung das Kern-Vokabular, schlägt dieser Test fehl.
    """
    from unittest.mock import MagicMock

    from skills.hoerspiel_oeffnen_task import HoerspielOeffnenTask

    task = HoerspielOeffnenTask(
        tg=MagicMock(),
        hoerspiel_client=MagicMock(),
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com",
    )
    desc = task.description.lower()

    # Folgen-Trigger-Vokabular (EC-40 Positiv-Heimat, Folgen-Familie)
    assert "hörbuch hören" in desc, (
        "EC-40/T1283: Folgen-Trigger 'hörbuch hören' fehlt in description — "
        "positives Vokabular gehört allein in die Tool-description (eltern-chat.md:1513-1518)")
    assert "folge" in desc, (
        "EC-40/T1283: Kern-Begriff 'folge' fehlt in description — "
        "Folgen-Trigger-Familie muss vertreten sein")

    # Direkt-Settings-Trigger-Vokabular (EC-40 Positiv-Heimat, Settings-Familie)
    assert "settings" in desc, (
        "EC-40/T1283: Direkt-Settings-Trigger 'settings' fehlt in description — "
        "positives Vokabular gehört allein in die Tool-description (eltern-chat.md:1513-1518)")
    assert "einstellungen" in desc, (
        "EC-40/T1283: Direkt-Settings-Trigger 'einstellungen' fehlt in description — "
        "Settings-Trigger-Familie muss beide Schreibweisen tragen")


# ============================================================
#  EC-44 / #1718 — Proaktives Pairing-Angebot bei App-Einrichtung
# ============================================================
def test_EC_44_system_prompt_proaktives_pairing_angebot():
    """AC (EC-44): Der SYSTEM_PROMPT trägt das proaktive Pairing-Angebot als
    ANGEBOT (nie Behauptung), mit genau EINER Rückfrage, konservativem Start
    (nur Einrichtungs-Wunsch) und Verweis auf die bestehenden Skills."""
    prompt = agent.SYSTEM_PROMPT
    low = prompt.lower()
    # Klausel benannt.
    assert "EC-44" in prompt
    # Angebot, NIE Behauptung — die verbotene Behauptung ist explizit genannt.
    assert "Behauptung" in prompt
    assert "nicht gekoppelt" in low
    # Genau EINE Rückfrage / einmal anbieten.
    assert "EINE" in prompt or "EINMAL" in prompt
    # Konservativer Start: Einrichtungs-Wunsch JA, reines "geht nicht" NICHT.
    assert "Einrichtungs" in prompt or "einrichten" in low
    assert "geht nicht" in low  # als explizit ausgeschlossene Klasse benannt
    # Kein neuer Mechanismus: verweist auf die bestehenden Skills.
    assert "geraet_anlegen" in prompt
    assert "cookie_nachschicken" in prompt


def test_EC_44_skill_descriptions_nennen_das_angebot():
    """AC (EC-44): Beide Pairing-Skills tragen den EC-44-Halbsatz in ihrer
    Description (proaktives Angebot als zusätzlicher Aufruf-Pfad)."""
    import inspect

    from skills import cookie_nachschicken_task, geraet_anlegen_task
    cns = inspect.getsource(cookie_nachschicken_task)
    gaa = inspect.getsource(geraet_anlegen_task)
    assert "EC-44" in cns and "proaktive" in cns
    assert "EC-44" in gaa and "proaktive" in gaa
