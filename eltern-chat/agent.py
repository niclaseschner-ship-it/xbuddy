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

from dataclasses import dataclass

from model import (GenerationRequest, Message, TaskResultBlock, TextBlock, WRITE)


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
    "- Beziehe dich auf den bisherigen Gesprächsverlauf, wenn eine Anfrage "
    "daran anknüpft."
)

# Obergrenze der Loop-Durchläufe — schützt vor einer Aufgaben-Schleife ohne Ende.
MAX_ITERATIONS = 6

# Fallbacks, falls der Anbieter keinen Text liefert.
_EMPTY_REPLY = "Ich habe dazu gerade keine Antwort."
_GAVE_UP = ("Ich konnte die Anfrage nicht abschließen. Bitte formuliere sie "
            "noch einmal etwas anders.")


@dataclass
class AgentResult:
    """Ergebnis eines Agenten-Durchlaufs.

    Entweder `reply_text` (fertige Antwort) ODER `proposal`/`pending_call`
    (eine schreibende Aufgabe wartet auf Bestätigung, EC-10).
    """
    reply_text: str = None
    proposal: object = None        # tasks.Proposal | None
    pending_call: object = None    # model.TaskCallBlock | None


def run_turn(history_messages, user_message, provider, catalog,
             max_iterations=MAX_ITERATIONS):
    """Verarbeitet eine Anfrage und liefert ein `AgentResult`.

    `history_messages` ist der geladene Gesprächskontext (EC-6), `user_message`
    die neue Anfrage. `provider` erfüllt `generate(GenerationRequest)`, `catalog`
    ist der Aufgaben-Katalog.

    Wirft `model.ProviderError` weiter, wenn der Anbieter scheitert (EC-14) —
    die Behandlung liegt bei der Orchestrierung.
    """
    messages = list(history_messages) + [user_message]
    task_defs = catalog.task_defs()

    for _ in range(max_iterations):
        response = provider.generate(GenerationRequest(
            system=SYSTEM_PROMPT, messages=messages, task_defs=task_defs))

        # Keine Aufgaben-Aufrufe → fertige Antwort (EC-4).
        if not response.task_calls:
            return AgentResult(reply_text=response.text or _EMPTY_REPLY)

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
                    proposal = task.propose(call.arguments)
                except Exception as e:  # noqa: BLE001 — Aufgabe isoliert melden
                    result_blocks.append(TaskResultBlock(
                        call_id=call.call_id,
                        content="Aufgabe nicht möglich: %s" % e, is_error=True))
                    continue
                return AgentResult(proposal=proposal, pending_call=call)

            # EC-9: lesende Aufgabe — direkt ausführen, Ergebnis zurückspeisen.
            try:
                content = task.run(call.arguments)
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
    return AgentResult(reply_text=_GAVE_UP)
