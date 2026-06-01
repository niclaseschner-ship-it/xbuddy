"""Agent-Loop — siehe specs/platform/eltern-chat.md EC-4..EC-9, E-EC-4/E-EC-5
(Refs #27).

Ein eigener, dünner Tool-Calling-Loop (E-EC-5 — KEIN Framework): Anfrage →
KI-Anbieter → ggf. Aufgaben-Aufrufe → Antwort. Der Loop arbeitet ausschließlich
mit dem kanonischen Modell (model.py).

Sicherheits-Architektur (E-EC-4): Dieses Modul kennt WEDER die
Berechtigungsprüfung (authz.py) NOCH die Bestätigung schreibender Aufgaben
(confirm.py) — es importiert beide nicht. Der LLM kann diese Gates nicht
umgehen, weil er sie nie aufruft. Eine schreibende Aufgabe wird hier NICHT
ausgeführt: der Loop gibt nur einen Vorschlag zurück (EC-10); die Ausführung
nach Bestätigung passiert außerhalb.
"""

import logging
import threading
import time
from dataclasses import dataclass, field

from model import (GenerationRequest, Message, ProviderError, TaskResultBlock,
                   TextBlock, WRITE)
from providers.pricing import estimate_cost
from telemetry import ProviderCall, TurnTelemetry


SYSTEM_PROMPT = (
    "Du bist der Eltern-Chat von XBuddy — ein freundlicher Assistent in der "
    "Familien-Gruppe. Du hilfst den Eltern, indem du Aufgaben aus deinem "
    "Aufgaben-Katalog erledigst.\n\n"
    "Regeln:\n"
    "- Antworte auf Deutsch, knapp und freundlich.\n"
    "- Du führst ausschließlich Aufgaben aus deinem Katalog aus. Hast du für "
    "eine Anfrage keine passende Aufgabe, sag das ehrlich und nenne, was du "
    "stattdessen tun kannst. Erfinde keine Fähigkeiten.\n"
    "- Ist eine Anfrage unklar oder unvollständig, stelle eine gezielte "
    "Rückfrage, statt zu raten.\n"
    "- Hängt die passende Antwort vom Kontext ab (z. B. Anleitungen mit "
    "Geräte-Varianten: Windows, Android, iOS/iPadOS, macOS), frag einmal "
    "kurz nach dem fehlenden Kontext, BEVOR du ein Werkzeug aufrufst oder "
    "antwortest. Niemals mehrere Varianten gleichzeitig ausbreiten, nur "
    "weil sie alle in Frage kommen.\n"
    "- Kennst du eine angefragte Tatsache nicht sicher, sag das offen — "
    "rate keinen plausibel klingenden Pfad.\n"
    "- Merkst du im Gesprächsverlauf, dass dein letzter Schritt ein Holzweg "
    "war (etwa ein Hinweis, der am Gerät nachweislich nicht funktioniert), "
    "entschuldige dich kurz und mach mit dem nun bekannten Stand weiter — "
    "keine stille Korrektur, kein erneutes Ausbreiten aller Möglichkeiten.\n"
    "- Willst du eine schreibende Aufgabe vorschlagen, rufe das Werkzeug "
    "DIREKT auf — frage nicht zuerst in der natürlichen Sprache nach "
    "Bestätigung (kein 'antworte mit ja zum Bestätigen'). Das System holt "
    "die Bestätigung deterministisch ein, sobald du das Werkzeug aufrufst; "
    "eine zusätzliche Sprach-Vorabfrage erzeugt nur eine doppelte "
    "Bestätigung (Issue #158).\n"
    "- Beziehe dich auf den bisherigen Gesprächsverlauf, wenn eine Anfrage "
    "daran anknüpft."
)

# Obergrenze der Loop-Durchläufe — schützt vor einer Aufgaben-Schleife ohne Ende.
MAX_ITERATIONS = 6

# Renewal-Intervall für den Typing-Indikator (Issue #165). Telegram löscht den
# Indikator nach ~5 s; das Renewal kommt deshalb etwas früher (4 s), damit
# lange Provider-Calls sichtbar bleiben, ohne den Indikator zwischenzeitlich
# verschwinden zu lassen.
_TYPING_RENEWAL_INTERVAL = 4

# Fallbacks, falls der Anbieter keinen Text liefert.
_EMPTY_REPLY = "Ich habe dazu gerade keine Antwort."
_GAVE_UP = ("Ich konnte die Anfrage nicht abschließen. Bitte formuliere sie "
            "noch einmal etwas anders.")


@dataclass
class AgentResult:
    """Ergebnis eines Agenten-Durchlaufs.

    Entweder `reply_text` (fertige Antwort) ODER `proposal`/`pending_call`
    (eine schreibende Aufgabe wartet auf Bestätigung, EC-10).

    `telemetry` (EC-23/#268) trägt die aggregierten Provider-Calls dieses
    Turns. None bedeutet: kein Telemetrie-Sammler war aktiv (alte Aufrufer);
    eine Instanz ohne Calls bedeutet: keine Provider-Calls passiert (AC3).

    `transcript` (#310) ist das volle Turn-Transkript in Loop-Reihenfolge:
    die Nutzer-Nachricht (Element 0), alle Assistant-Tool-Aufrufe und
    User-Tool-Ergebnisse dieses Turns, plus der finale Assistant-Text (auf dem
    Erfolgs-Pfad). Die Orchestrierung persistiert genau diese Messages, damit
    das Modell in Folge-Turns seine eigenen Tool-Aufrufe sieht (EC-6,
    Modell-Kohärenz). Die geladene History ist NICHT enthalten — nur der neue
    Turn. Auf dem proposal-Pfad endet das Transkript mit dem letzten
    Tool-Turn; der reine Vorschlagstext hängt die Orchestrierung an.
    """
    reply_text: str = None
    proposal: object = None        # tasks.Proposal | None
    pending_call: object = None    # model.TaskCallBlock | None
    telemetry: object = None       # TurnTelemetry | None
    transcript: list = field(default_factory=list)   # list[Message] (#310)


class _NullContext:
    """No-op Kontextmanager — ersetzt `_TypingRenewal` wenn kein Renewer gesetzt."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _TypingRenewal:
    """Hintergrund-Thread, der `renewer()` alle `_TYPING_RENEWAL_INTERVAL` Sekunden
    aufruft, während ein Provider-Aufruf läuft (Issue #165).

    Genutzt als Kontextmanager: `__enter__` startet den Thread, `__exit__` stoppt
    ihn — garantiert, dass nach dem Provider-Return kein weiterer Renewal-Call
    mehr kommt. Fehler im Renewer werden geschluckt (Komfort, kein Gate).
    """

    def __init__(self, renewer, interval=_TYPING_RENEWAL_INTERVAL):
        self._renewer = renewer
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self):
        while not self._stop.wait(self._interval):
            try:
                self._renewer()
            except Exception:  # noqa: BLE001 — Renewal ist Komfort, kein Gate
                logging.debug("Typing-Renewal-Aufruf fehlgeschlagen (geschluckt)",
                              exc_info=True)


def run_turn(history_messages, user_message, provider, catalog, turn_context,
             max_iterations=MAX_ITERATIONS, before_provider_call=None,
             chat_action_renewer=None):
    """Verarbeitet eine Anfrage und liefert ein `AgentResult`.

    `history_messages` ist der geladene Gesprächskontext (EC-6), `user_message`
    die neue Anfrage. `provider` erfüllt `generate(GenerationRequest)`, `catalog`
    ist der Aufgaben-Katalog.

    `turn_context` (`tasks.TurnContext`) ist der deterministische
    Ausführungs-Kontext. Der Loop reicht ihn UNVERÄNDERT an die Aufgaben durch
    (`run`/`propose`); das Modell sieht ihn nie — sein Kanal bleibt `arguments`.

    `before_provider_call` (Issue #156): optionaler Callback ohne Argumente, der
    VOR jedem `provider.generate(...)` läuft — also auch bei jedem Tool-Loop-
    Durchgang, nicht nur beim ersten Aufruf. Die Orchestrierung nutzt ihn, um
    den Telegram-Typing-Indikator nachzulegen (Telegram löscht ihn nach ~5 s).
    Fehler des Callbacks werden geschluckt; er ist Komfort, kein Gate, und
    darf den Turn nicht abbrechen.

    `chat_action_renewer` (Issue #165): optionaler Callback ohne Argumente, der
    WÄHREND `provider.generate(...)` alle `_TYPING_RENEWAL_INTERVAL` Sekunden in
    einem Hintergrund-Thread aufgerufen wird. Damit bleibt der Typing-Indikator
    auch bei Provider-Calls >5 s sichtbar. Thread-Fehler werden geschluckt; der
    Renewer ist Komfort, kein Gate. Der Thread terminiert garantiert nach dem
    Provider-Return — kein Leak. `chat_action_renewer` ist UNABHÄNGIG von
    `before_provider_call`; beide können gleichzeitig gesetzt sein.

    Wirft `model.ProviderError` weiter, wenn der Anbieter scheitert (EC-14) —
    die Behandlung liegt bei der Orchestrierung.
    """
    messages = list(history_messages) + [user_message]
    task_defs = catalog.task_defs()
    # EC-23 (#268): Sammler für die Provider-Calls dieses Turns. Auch ohne
    # einen einzigen Call bleibt das Objekt gesetzt — die Orchestrierung
    # erkennt an `has_calls()`, ob ein Suffix anzuhängen ist (AC2/AC3).
    telemetry = TurnTelemetry()

    for _ in range(max_iterations):
        if before_provider_call is not None:
            # Issue #156: Typing-Indikator vor JEDEM Provider-Call, nicht nur
            # vor dem ersten — sonst läuft er in Tool-Loops aus. Komfort, kein
            # Gate: Fehler werden geschluckt.
            try:
                before_provider_call()
            except Exception:  # noqa: BLE001 — Indikator darf den Turn nicht abbrechen
                pass

        # Issue #165: Renewal-Thread hält den Typing-Indikator für die Dauer
        # des Provider-Calls lebendig. Kein `chat_action_renewer` → normaler Pfad
        # ohne Thread-Overhead.
        if chat_action_renewer is not None:
            # Intervall zur Laufzeit lesen — erlaubt Überschreiben im Test.
            _renewal = _TypingRenewal(chat_action_renewer,
                                      interval=_TYPING_RENEWAL_INTERVAL)
        else:
            _renewal = None

        with (_renewal if _renewal is not None else _NullContext()):
            # EC-23 (#268): Wall-Clock-Wrapper um den Provider-Call. Im
            # Fehlerfall hängen wir einen Stub-Call an die Telemetrie
            # (model_id soweit bekannt, wall_ms gemessen, tokens=0,
            # est_cost=None) und setzen `err.telemetry`, bevor wir
            # weiterwerfen — die Orchestrierung persistiert das.
            _start = time.monotonic()
            try:
                response = provider.generate(GenerationRequest(
                    system=SYSTEM_PROMPT, messages=messages, task_defs=task_defs))
            except ProviderError as err:
                wall_ms = int((time.monotonic() - _start) * 1000)
                model_id = getattr(provider, "_model", "") or ""
                telemetry.add(ProviderCall(
                    model_id=model_id,
                    input_tokens=0, output_tokens=0,
                    cache_read_tokens=0, cache_creation_tokens=0,
                    wall_ms=wall_ms,
                    est_cost_usd=None, est_cost_eur=None))
                err.telemetry = telemetry
                raise
            wall_ms = int((time.monotonic() - _start) * 1000)

        # EC-23 (#268): Token-Counts aus der anbieter-neutralen Usage in einen
        # ProviderCall heben. Liefert der Adapter keine Usage (älterer Test-
        # Mock ohne Anthropic-Anbindung), entsteht KEIN ProviderCall — sonst
        # wäre der Suffix bei jedem alten Test ein Format-Bruch, und »tokens=0,
        # est_cost=None« wäre kein ehrlicher Diagnose-Wert, sondern reine
        # Geräusche. Der reale ClaudeProvider liefert immer Usage; nur die
        # Test-Doppelungen ohne Usage produzieren den »kein Telemetrie-Eintrag«-
        # Fall.
        usage = getattr(response, "usage", None)
        if usage is not None:
            cost_usd, cost_eur = estimate_cost(
                usage.model_id,
                usage.input_tokens,
                usage.cache_read_tokens,
                usage.output_tokens)
            telemetry.add(ProviderCall(
                model_id=usage.model_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_creation_tokens=usage.cache_creation_tokens,
                wall_ms=wall_ms,
                est_cost_usd=cost_usd,
                est_cost_eur=cost_eur))

        # Keine Aufgaben-Aufrufe → fertige Antwort (EC-4).
        if not response.task_calls:
            # #310: den finalen Assistant-TextBlock ans Transkript hängen, damit
            # die persistierte History den ganzen Tool-Turn-Verlauf bis zur
            # Antwort trägt (EC-6, Modell-Kohärenz). `transcript` enthält nur den
            # neuen Turn (ab user_message), nicht die geladene History. Wir bauen
            # eine NEUE Liste statt `messages` zu mutieren — die provider-
            # sichtbare Anfrage darf nicht nachträglich um den Antwort-Block
            # wachsen (EC-13).
            reply_text = response.text or _EMPTY_REPLY
            transcript = (messages[len(history_messages):]
                          + [Message(role="assistant", blocks=[TextBlock(reply_text)])])
            return AgentResult(reply_text=reply_text, telemetry=telemetry,
                               transcript=transcript)

        # Assistant-Zug mit Text und Aufgaben-Aufrufen festhalten.
        assistant_blocks = []
        if response.text:
            assistant_blocks.append(TextBlock(response.text))
        assistant_blocks.extend(response.task_calls)
        messages.append(Message(role="assistant", blocks=assistant_blocks))

        result_blocks = []
        for call in response.task_calls:
            task = catalog.get(call.task)

            # EC-8: unbekannte Aufgabe — der Loop löst keine „kreative" Aktion
            # aus, sondern meldet die Katalog-Grenze zurück. Diese Grenze hängt
            # NICHT von der Modell-Ausgabe ab (EC-12): egal was der Anbieter
            # vorschlägt, nur registrierte Aufgaben sind ausführbar.
            if task is None:
                result_blocks.append(TaskResultBlock(
                    call_id=call.call_id,
                    content="Unbekannte Aufgabe '%s' — nicht im Katalog." % call.task,
                    is_error=True))
                continue

            # EC-10: schreibende Aufgabe — NICHT ausführen. Der Loop endet hier
            # mit einem Vorschlag; die Ausführung passiert erst nach
            # Bestätigung, außerhalb dieses Moduls (E-EC-4).
            if task.kind == WRITE:
                try:
                    proposal = task.propose(call.arguments, turn_context)
                except Exception as e:  # noqa: BLE001 — Aufgabe isoliert melden
                    result_blocks.append(TaskResultBlock(
                        call_id=call.call_id,
                        content="Aufgabe nicht möglich: %s" % e, is_error=True))
                    continue
                # #310: das Transkript endet mit dem letzten Tool-Turn (der
                # Assistant-tool_use mit diesem Aufruf wurde oben angehängt). Den
                # reinen Vorschlagstext hängt die Orchestrierung an (via
                # _format_proposal) — er ist nicht Teil des Loop-Transkripts.
                return AgentResult(proposal=proposal, pending_call=call,
                                   telemetry=telemetry,
                                   transcript=messages[len(history_messages):])

            # EC-9: lesende Aufgabe — direkt ausführen, Ergebnis zurückspeisen.
            try:
                content = task.run(call.arguments, turn_context)
            except Exception as e:  # noqa: BLE001 — Aufgabe isoliert melden
                result_blocks.append(TaskResultBlock(
                    call_id=call.call_id,
                    content="Fehler bei der Aufgabe: %s" % e, is_error=True))
                continue
            result_blocks.append(TaskResultBlock(
                call_id=call.call_id, content=content, is_error=False))

        # Ergebnisse als Nutzer-Zug zurückgeben, Schleife fortsetzen.
        messages.append(Message(role="user", blocks=result_blocks))

    # Obergrenze erreicht — sauber abbrechen statt endlos zu schleifen.
    # #310: den Abbruch-Text als finalen Assistant-TextBlock ans Transkript
    # hängen (neue Liste, nicht `messages` mutieren — EC-13), damit die
    # persistierte History auch hier den vollen Tool-Turn-Verlauf bis zur
    # Antwort trägt (gleiche Reihenfolge wie der Erfolgs-Pfad).
    transcript = (messages[len(history_messages):]
                  + [Message(role="assistant", blocks=[TextBlock(_GAVE_UP)])])
    return AgentResult(reply_text=_GAVE_UP, telemetry=telemetry,
                       transcript=transcript)
