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

from _markdown_button_strip import strip_markdown_buttons
from model import WRITE, GenerationRequest, Message, ProviderError, TaskResultBlock, TextBlock
from tasks import HOERSPIEL_INSTANZEN, render_form_b
from telemetry import ProviderCall, TurnTelemetry

# OPEN-LLMP-A / #1636: EINE Kosten-Quelle — die frühere Zweit-Tabelle
# (eltern-chat/providers/pricing.py) ist aufgelöst; Kosten kommen jetzt aus
# dem unified tools.llm-Preis-Strang (identische Zahlen, kein Stückwerk).
from tools.llm import estimate_cost

# HSP-43 / #1263: Prompt-Namensliste aus DERSELBEN Instanz-Konstante wie die
# HFE-enum (tasks.HOERSPIEL_INSTANZEN) — kein separater paula/neko-Hardcode im
# Prompt. Nimmt niclas automatisch mit (→ „Paula, Neko oder Niclas").
_HSP_NAMEN = [i["name"] for i in HOERSPIEL_INSTANZEN]
_HSP_IDS = [i["kind_id"] for i in HOERSPIEL_INSTANZEN]


def _oder_liste(items) -> str:
    """»a, b oder c« — Aufzählung für den System-Prompt (HSP-43)."""
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return "%s oder %s" % (", ".join(items[:-1]), items[-1])


_HSP_NAMEN_ODER = _oder_liste(_HSP_NAMEN)                       # "Paula, Neko oder Niclas"
_HSP_NAMEN_GUILL = "/".join("»%s«" % n for n in _HSP_NAMEN)    # "»Paula«/»Neko«/»Niclas«"
_HSP_IDS_BZW = " bzw. ".join("»%s«" % k for k in _HSP_IDS)     # "»paula« bzw. »neko« bzw. »niclas«"

SYSTEM_PROMPT = (
    "Du bist der Eltern-Chat von XBuddy — ein freundlicher Assistent in der "
    "Familien-Gruppe. Du hilfst den Eltern, indem du Aufgaben aus deinem "
    "Aufgaben-Katalog erledigst und allgemeine Wissensfragen beantwortest.\n\n"
    "Regeln:\n"
    "- ⚠️ **HARTES VERBOT — kein Markdown-Knopf in deiner Antwort (EC-41).** "
    "Schreibe in deiner Bot-Antwort NIEMALS einen Knopf, einen Mini-App-Link "
    "oder eine Aufforderung-zum-Klicken als Markdown-Text. Konkret verboten "
    "(Beispiele aus realen Halluzinationen): `[**Routine-Anpassen-Mini-App öffnen**]`, "
    "`[**App öffnen**]`, »👉 Öffne die App mit diesem Knopf:«, »Knopf unten«, "
    "»klick auf den Button«, »Mit diesem Knopf öffnest du …«. Telegram rendert "
    "Markdown NICHT als klickbaren Knopf — die Familie sieht literalen Text "
    "und der Knopf fehlt. Mini-App-Knöpfe entstehen AUSSCHLIESSLICH dadurch, "
    "dass du eines der fünf Mini-App-Skills aufrufst (einkauf_zeigen, "
    "hoerspiel_oeffnen, routine_anpassen_oeffnen, seiten_uebersicht, "
    "wetter_regeln_oeffnen) — der Skill "
    "liefert den echten Inline-Button als Telegram-Anhang. "
    "**NACH einem erfolgreichen Mini-App-Skill-Aufruf:** NUR den vom Skill "
    "gelieferten Text in deine Antwort formulieren (oder leicht umformulieren) — "
    "KEIN zusätzlicher Knopf-Hinweis danach, KEIN »👉 Öffne mit dem Knopf«-"
    "Verweis, NICHT den Knopf in Worten erwähnen, NICHT »Hier ist die App, klick …«-"
    "Phrasen schreiben. Der Inline-Knopf ist schon da, die Familie sieht ihn — sag "
    "NICHTS zusätzlich dazu. Wenn du in deiner Antwort gerade eine Knopf-Phrase "
    "formulieren willst und kein Tool im selben Turn aufgerufen hast: STOPP, "
    "rufe stattdessen das passende Mini-App-Skill auf.\n"
    "- Antworte auf Deutsch, knapp und freundlich.\n"
    "- Trennlinie XBuddy-Zustand vs. Welt-Wissen (EC-30): Aussagen über "
    "XBuddy-Zustand — Familien-Mitglieder, Kalender-Inhalte, Berechtigungen, "
    "Buddy-Daten (Routinen, Plan-Aktivitäten, Wünsche, Termine, Fotos, "
    "Seiten-Übersicht) — beantwortest du AUSSCHLIESSLICH über eine Katalog-"
    "Aufgabe. Du erfindest oder schätzt keinen XBuddy-Zustand. Allgemeine "
    "Wissensfragen ohne XBuddy-Bezug — technische Anleitungen, Sach-Fragen, "
    "Erklärungen (z. B. 'Wie installiere ich ein Zertifikat?', 'Was bedeutet "
    "HTTPS?') — beantwortest du direkt aus deinem Wissen, ohne Werkzeug-"
    "Aufruf. Erfinde keine System-Fähigkeiten, die du nicht hast.\n"
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
    "- **A2-Undo-Hinweis wortwörtlich (EC-10 A2):** Wenn ein Skill-Result eine "
    "Zeile mit dem Wort `falsch` enthält (Undo-Hinweis), übernimm diese Zeile "
    "wortwörtlich in deine Antwort an die Familie — nicht kürzen, nicht "
    "umformulieren.\n"
    "- Beziehe dich auf den bisherigen Gesprächsverlauf, wenn eine Anfrage "
    "daran anknüpft.\n\n"
    "Proaktives Pairing-Angebot (EC-44, konservativer Start):\n"
    "Wenn jemand sinngemäß ein Gerät EINRICHTEN will — »App aufs Handy/Tablet«, "
    "»wie installiere ich«, »neues Gerät einrichten«, »App öffnen/koppeln« — "
    "kann ein fehlender Cookie der stille Grund für spätere Zugriffsprobleme "
    "sein. Biete dann EINMAL kurz den bestehenden Einrichtungs-/Pairing-Link an "
    "(»geraet_anlegen« für ein neues Gerät, »cookie_nachschicken« zum Erneuern) "
    "— als ANGEBOT, NIE als Behauptung: du kennst den Kopplungs-Status NICHT, "
    "sag also nie »du bist nicht gekoppelt« o. Ä. Formuliere es als kurze Frage "
    "(»soll ich dir den Einrichtungs-Link schicken?«); stimmt die Person zu, "
    "rufe das Werkzeug auf. Genau EINE kurze Rückfrage — will sie nicht oder hat "
    "den Cookie schon, lass es fallen und hilf ganz normal weiter. NUR bei "
    "Einrichtungs-Wunsch anbieten, NICHT bei bloßem »geht nicht«/»lädt nicht«/"
    "»weiße Seite« (die überlappen mit echten Nicht-Auth-Bugs).\n\n"
    "Termine aus Bild (TAB-4, EC-30-Trennlinie):\n"
    "⚠️ HARTES GEBOT — enthält eine Nachricht ein Foto UND ein Termin-Signalwort "
    "im Begleittext (z. B. »termin«, »termine«, »kalender«, »eintragen«, »plan«, "
    "»schulplan«, »kursplan«), SOFORT das Werkzeug »termine_aus_bild« aufrufen. "
    "KEINE Termin-Liste aus dem bisherigen Gesprächsverlauf oder dem eigenen Wissen "
    "antworten — auch wenn Termine im Kontext bekannt sind. Das Bild MUSS von der "
    "Extraktion ausgewertet werden; eine Kontext-Antwort übersieht Termine, die nur "
    "im Foto stehen (#1334 Live-Befund). Fehlt kein Signalwort → nicht aufrufen "
    "(kommentarloses Foto → `foto_senden`).\n\n"
    "Hörspiel-Folge-Erzeugen (HFE-6, EC-30-Trennlinie):\n"
    "WICHTIG: bei JEDER Hörspiel-/Hörbuch-/Folgen-Anfrage SOFORT das Werkzeug "
    "»hoerspiel_folge_erzeugen« aufrufen — KEINE eigenen Rückfragen stellen, der "
    "Skill macht die Diskussion. Trigger-Phrasen (nicht abschließend): »Neues "
    "Hörbuch«, »Neues Hörspiel«, »Neue Folge«, »Hörbuch anlegen«, »Hörspiel "
    "machen«, »Mach Paula eine Folge«, »Schreib eine Folge«, »Folge erzeugen«, "
    "»Welche Themen gibt es?«, »Vorschläge?«, »Was könnte ich Paula erzählen?«. "
    "Die Eltern-Diskussion (was, worüber, mit wem, wie) findet IM Skill statt, "
    "nicht im Agent.\n"
    "Themen-Anfrage-Phrasen (= leere oder vage Idee) — rufe das Werkzeug mit "
    "einer LEEREN »idee« auf, der Skill holt eine Themen-Liste (HFE-3 Sub-Case 1).\n"
    "Konkret-aber-unvollständige-Idee — wenn die Idee vorhanden aber noch "
    "ausbaufähig ist (z. B. »mach eine Folge über Mut«), setze »idee_diskussion: true« "
    "und gib die bisherige Idee in »idee« mit. Das Signal zeigt dem Skill, "
    "dass du noch Rückfragen stellen möchtest (HFE-3 Sub-Case 2).\n"
    "Eltern-Signal-Phrasen — beenden die Diskussion und lösen den Vorschlag-Endpoint "
    "aus: »los«, »los gehts«, »los, schreib«, »mach das«, »passt so«, »okay so«, "
    "»fang an«, »jetzt vertonen«, »schreib jetzt«. Bei diesen Phrasen das Werkzeug "
    "»hoerspiel_folge_erzeugen« mit der zusammengeführten konkreten Idee und "
    "»idee_diskussion: false« aufrufen — der Skill geht dann den Standard-Pfad "
    "zum Vorschlag-Endpoint (HFE-3, HFE-6). WICHTIG: Diese Phrasen lösen den "
    "Vorschlag NUR aus, solange noch KEIN Vorschlag vorliegt. Wurde gerade eine "
    "Folge vorgeschlagen (Bot-Nachricht »Vertonen? Antworte nur mit »ja«…«), rufe "
    "»hoerspiel_folge_erzeugen« bei einer solchen Phrase NICHT erneut auf — die "
    "Bestätigung läuft deterministisch außerhalb von dir über EC-10. Erneutes "
    "Aufrufen würde nur neu texten statt zu vertonen.\n"
    "Hörspiel-Settings (Anti-Redundanz, E-HOE-2 / Refs #1028) — Anliegen, die "
    "in der Hörspiel-Mini-App eingestellt werden (Voice / Stimme, LLM-Anbieter, "
    "LLM-Modell, Playback-Tempo, Pausen zwischen Absätzen) sind KEIN HFE- und KEIN "
    "HOE-Trigger. Antwort: »<Was>… wählst/änderst du in der Hörspiel-Mini-App "
    f"<von Kindname>.« — wenn die Mutter ein Kind nennt ({_HSP_NAMEN_GUILL}), trage "
    "den Namen im Verweis explizit mit, weil die Settings pro Hörspiel-Instanz "
    "gepflegt werden (HSP-34 ist per-kind). Bei Mehrdeutigkeit ohne Kindname "
    f"stelle EINE kurze Rückfrage: »Für {_HSP_NAMEN_ODER}?« — analog HFE — und "
    "antworte erst danach mit dem Verweis.\n"
    "Beispiele beiläufige Settings-Erwähnung (KEIN Tool-Call): »wechsel bei "
    "Neko auf mistral« → »Anbieter und Modell von Neko wählst du in der "
    "Hörspiel-Mini-App von Neko.«; »wechsel auf onyx«, »mit shimmer vertonen«, "
    f"»andere Stimme« (#995) → Rückfrage »Für {_HSP_NAMEN_ODER}?«, dann »Voice "
    "wählst du in der Hörspiel-Mini-App von <Name>.«; »Tempo ändern« / "
    "»Pausen tunen« → analog mit Kind-Verweis. Die Stimme im aktiven "
    "HFE-Vorschlag ist die in der Mini-App gesetzte und nicht im Chat "
    "überschreibbar — »ja mit onyx« wird gelesen als »ja« (Confirm), die "
    "Voice-Phrase verworfen.\n"
    "WICHTIG: kein Settings-Inhalt im Chat-Text ausgeben — NUR den "
    "Türöffner-Button senden (HOE-4). »Knopf unten« oder »Button« NICHT "
    "versprechen — der Button kommt automatisch mit dem Tool-Call. "
    "Beiläufige Settings-Erwähnung (z. B. »Voice von Neko ändern«, "
    "»wechsel auf mistral«) → sprachlicher Verweis OHNE Tool-Call OHNE "
    "Button (Anti-Redundanz-Grundregel bleibt).\n"
    f"kind_id-Wahl (HFE-3, E-HFE-6): Nennt die Mutter einen Namen ({_HSP_NAMEN_GUILL}), "
    f"setze kind_id entsprechend ({_HSP_IDS_BZW}). Bei Mehrdeutigkeit — kein "
    f"Name im Satz — stelle EINE kurze Rückfrage: »Für {_HSP_NAMEN_ODER}?«."
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

# #310 (T310-S3): synthetischer tool_result-Inhalt, der das vorgeschlagene
# WRITE-tool_use im persistierten Verlauf paart (EC-10). EC-7: er sagt ehrlich,
# dass der Vorschlag NUR vorgelegt wurde — nicht, dass der Write lief.
# #331: parametrisiert nach Task-Namen, damit das Modell in Folge-Turns klar
# erkennt, WELCHES Werkzeug erneut aufzurufen ist (statt den Vorschlag als
# „läuft schon" zu lesen und den Tool-Call zu überspringen).
def _proposal_pending(task_name):
    """Gibt den synthetischen tool_result-Text für einen vorgelegten WRITE-
    Vorschlag zurück (EC-10, #331).

    Der Text macht drei Dinge klar:
    (a) Es wurde ein VORSCHLAG vorgelegt — die Aufgabe ist NICHT ausgeführt.
    (b) Das Werkzeug führt den Schritt-für-Schritt-Dialog selbst (Auswahl aus
        den Registries/Listen) — das Modell stellt diese Fragen NICHT.
    (c) Um die Aufgabe auszuführen (jetzt oder später), ist immer das Werkzeug
        erneut aufzurufen.

    Kein „erst nach Bestätigung"-Framing — das poisoned das Modell dahin,
    den Dialog als „warte auf Ja" zu lesen statt das Werkzeug neu aufzurufen.
    """
    return (
        "Vorschlag vorgelegt, das Werkzeug «%(name)s» auszuführen. "
        "Das Werkzeug führt den nötigen Schritt-für-Schritt-Dialog selbst "
        "(Auswahl aus den jeweiligen Registries/Listen) — du stellst diese "
        "Fragen NICHT. Um die Aufgabe auszuführen (jetzt oder später), "
        "rufe immer das Werkzeug «%(name)s» auf." % {"name": task_name}
    )


def _flush_task_events(store, chat_id, called_skills, error_skills):
    """Persistiert Task-Events für alle eindeutig gerufenen Skills eines Turns
    (EC-35). Ist `store` None, ist diese Funktion ein No-op (Sandbox-Pfad).

    Outcome-Regel: hat ein Skill irgendwann in diesem Turn geworfen (er steht
    in `error_skills`), bekommt er outcome='error'; sonst 'success'.
    Deduplizierung liegt schon in `called_skills` (Set).
    """
    if store is None:
        return
    for name in called_skills:
        outcome = "error" if name in error_skills else "success"
        store.insert(name, chat_id, outcome)


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
            except Exception:  # Renewal ist Komfort, kein Gate
                logging.debug("Typing-Renewal-Aufruf fehlgeschlagen (geschluckt)",
                              exc_info=True)


def _call_provider(provider, request, telemetry):
    """Ruft `provider.generate(request)` auf, misst Wall-Clock, hebt Token-Counts
    in die Telemetrie und kapselt den `ProviderError`-Stub.

    Gibt die `GenerationResponse` zurück.  Wirft `ProviderError` weiter
    (nach Anhängen des Stub-Calls und Setzen von `err.telemetry`).

    Wird innerhalb des `_TypingRenewal`-Kontextmanagers von `run_turn`
    aufgerufen — der Renewal-Thread läuft also bereits, wenn dieser Aufruf
    startet (#165).
    """
    # EC-23 (#268): Wall-Clock-Wrapper um den Provider-Call. Im Fehlerfall
    # hängen wir einen Stub-Call an die Telemetrie (model_id soweit bekannt,
    # wall_ms gemessen, tokens=0, est_cost=None) und setzen `err.telemetry`,
    # bevor wir weiterwerfen — die Orchestrierung persistiert das.
    _start = time.monotonic()
    try:
        response = provider.generate(request)
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

    return response


def _correction_system_suffix(correction_state):
    """Baut den System-Prompt-Anhang für den EC-36-Korrektur-Folge-Turn (#844).

    Der Suffix sagt dem LLM offen, dass der vorige Akt zurückgenommen wurde
    und die nächste User-Nachricht den Patch trägt. Es darf rückfragen, wenn
    der Patch unklar ist (spec Z. 1177-1182), und es darf den Skill wechseln,
    wenn die User-Antwort gar nicht mehr zum alten Skill gehört (Cross-Skill-
    Exit, spec Z. 1184-1191). Der Wortlaut nennt explizit den vorigen
    `last_skill`, damit das LLM bei einem Re-Propose denselben Skill wieder
    ruft (mit gepatchten Args) statt einen ähnlichen zu raten. Re-Propose
    durchläuft IMMER das zweistufige Confirm-Gate (spec Z. 1193-1201) — das
    erzwingt das Framework selbst: der auto_confirm-Branch unten prüft den
    Korrektur-State und fällt auf den propose-Pfad zurück, selbst wenn ein
    A2-Skill (z. B. einkauf_hinzufuegen mit auto_confirm=True) erneut
    aufgerufen wird. Ohne diesen Gate-Zwang würde das Vertrauen aus der
    A2-Klausel — das nach `falsch` verbraucht ist — fälschlich weiterleben.
    """
    last_skill = correction_state.last_skill or "unbekannt"
    return (
        "\n\nKORREKTUR-STATE (EC-36, #844):\n"
        "Der vorige Schreibakt/Vorschlag des Skills «%s» wurde gerade per "
        "»falsch« vom User zurückgenommen. "
        "Was tatsächlich rückgängig gemacht wurde (oder klemmt — Ambiguitäts-"
        "Quittung), steht in der vorherigen Bot-Quittung im Verlauf — verlass "
        "dich auf diese Quittung, erwähne entfernte Ressourcen NICHT als noch "
        "vorhanden, frage nicht nach erneutem Löschen. "
        "Die folgende User-Nachricht trägt "
        "die Korrektur (z. B. »eigentlich Brötchen«, »Donnerstag 17 statt 16«). "
        "Baue daraus einen neuen Aufruf desselben Skills mit gepatchten "
        "Argumenten — das System legt ihn als Vorschlag vor (Confirm-Gate). "
        "Ist die Korrektur unklar (z. B. »alle Termine einen Tag nach vorne« "
        "ohne klare Auswahl), stelle eine knappe Rückfrage statt zu raten. "
        "Will der User einen anderen Skill (z. B. nach »falsch« zum Termin: "
        "»eigentlich Plan-Aktivität«), rufe den passenden Skill — der Korrektur-"
        "Pfad wird damit verlassen." % last_skill
    )


def run_turn(history_messages, user_message, provider, catalog, turn_context,
             max_iterations=MAX_ITERATIONS, before_provider_call=None,
             chat_action_renewer=None, tg=None, task_events_store=None,
             correction_state=None):
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

    `tg` (TASK-10c Form (b)): optionaler Telegram-Client für den Form-(b)-
    Übersetzer (`render_form_b`). Gibt ein Skill ein `{text, presentation}`-
    Dict zurück, sendet das Framework über diesen Client die Bot-Nachricht
    und legt eine Quittungs-Zeichenkette als `content` in den TaskResultBlock.
    Ist `tg=None`, fällt der Übersetzer auf den reinen `text`-Teil zurück.

    `task_events_store` (EC-35): optionale `TaskEventsStore`-Instanz. Ist sie
    gesetzt, schreibt `run_turn` am Ende des Turns für jeden eindeutig gerufenen
    Skill einen Event-Eintrag (Deduplizierung: zwei Aufrufe desselben Skills =
    ein Event). Ist sie None (Default), wird kein Event geschrieben — die
    Sandbox- und Test-Kompatibilität bleibt unverändert. Für Live-Aktivierung
    muss main.py `task_events_store=ctx.task_events_store` durchreichen.

    `correction_state` (EC-36 Korrektur-Hook, #844): optionaler
    `confirm.CorrectionState`. Ist er gesetzt, hängt run_turn einen Suffix an
    den SYSTEM_PROMPT — das LLM sieht, dass der vorige Akt zurückgenommen
    wurde und die User-Nachricht den Patch trägt. Lebenszyklus liegt bei der
    Orchestrierung (main.py löscht den State nach jedem Turn).

    Wirft `model.ProviderError` weiter, wenn der Anbieter scheitert (EC-14) —
    die Behandlung liegt bei der Orchestrierung.
    """
    messages = list(history_messages) + [user_message]
    task_defs = catalog.task_defs()
    # EC-36 (#844): System-Prompt-Erweiterung im Korrektur-Folge-Turn.
    effective_system = SYSTEM_PROMPT
    if correction_state is not None:
        effective_system = SYSTEM_PROMPT + _correction_system_suffix(correction_state)
    # EC-23 (#268): Sammler für die Provider-Calls dieses Turns. Auch ohne
    # einen einzigen Call bleibt das Objekt gesetzt — die Orchestrierung
    # erkennt an `has_calls()`, ob ein Suffix anzuhängen ist (AC2/AC3).
    telemetry = TurnTelemetry()

    # EC-35: Deduplizierter Skill-Tracker. Set — ein Skill taucht pro Turn
    # nur einmal auf, egal wie oft das Modell ihn in diesem Turn aufruft.
    # `_called_skills`: {task_name} für Erfolg-Pfad.
    # `_error_skills`: {task_name} für Skills, die im letzten Aufruf geworfen
    # haben. (Letzter Aufruf bestimmt outcome, falls mehrere Pfade möglich.)
    _called_skills: set = set()
    _error_skills: set = set()
    # EC-41 mechanische Sperre: trackt, ob im selben Turn ein Tool-Call mit
    # Inline-Button gefeuert hat (TASK-10c Form (b) `inline_button`). Der
    # Markdown-Strip-Filter im finalen reply_text-Pfad nutzt dieses Flag, um
    # parallele Markdown-Knopf-Halluzinationen extra aggressiv zu entfernen
    # (Live-Befund 2026-06-22 chat 464143432, Refs #1075).
    _inline_button_emitted = False

    for _ in range(max_iterations):
        if before_provider_call is not None:
            # Issue #156: Typing-Indikator vor JEDEM Provider-Call, nicht nur
            # vor dem ersten — sonst läuft er in Tool-Loops aus. Komfort, kein
            # Gate: Fehler werden geschluckt.
            try:
                before_provider_call()
            except Exception:  # Indikator darf den Turn nicht abbrechen
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

        request = GenerationRequest(
            system=effective_system, messages=messages, task_defs=task_defs,
            correlation_id=getattr(turn_context, "turn_id", None))
        with (_renewal if _renewal is not None else _NullContext()):
            # Issue #165: Renewal-Thread hält den Typing-Indikator für die
            # Dauer des Provider-Calls lebendig; _call_provider kapselt den
            # generate-Aufruf, Wall-Clock-Messung, Usage-Lift und
            # ProviderError-Stub (EC-23/#268).
            response = _call_provider(provider, request, telemetry)

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
            # EC-41 mechanische Sperre: Markdown-Knopf-Halluzinationen aus dem
            # finalen LLM-Antwort-Text entfernen, BEVOR er ins Transkript geht
            # (und damit vor dem Telegram-Send in main.py). Bei Tool-Call mit
            # Inline-Button im selben Turn wird der Stripper extra aggressiv.
            # Live-Befund 2026-06-22 (Refs #1075): mistral-medium-2508 ignoriert
            # EC-41-Disziplin im SYSTEM_PROMPT trotz dreier Härtungs-Stufen.
            reply_text = strip_markdown_buttons(
                reply_text, inline_button_emitted=_inline_button_emitted)
            if not reply_text:
                reply_text = _EMPTY_REPLY
            transcript = (messages[len(history_messages):]
                          + [Message(role="assistant", blocks=[TextBlock(reply_text)])])
            # EC-35: Task-Events für alle in diesem Turn eindeutig gerufenen
            # Skills persistieren (Erfolgs-Pfad). Outcome: 'error' wenn der
            # Skill geworfen hat, sonst 'success'. Dedupliziert via Set.
            _flush_task_events(task_events_store, turn_context.chat_id,
                               _called_skills, _error_skills)
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
            #
            # Ausnahme: auto_confirm=True (E-EIN-1 Direkt-Modus). Skill schreibt
            # sofort ohne Bestätigungs-Gate, weil die Wirkung schmerzlos
            # rückgängig zu machen ist (z. B. Einkaufs-Item per Mini-App-Geste
            # entfernbar). Frame ruft execute() direkt via Catalog.
            #
            # GEGEN-AUSNAHME EC-36 (spec Z. 1193-1201): im Korrektur-State
            # (Re-Propose nach »falsch«) wird auto_confirm IGNORIERT. Das
            # Vertrauen aus der A2-Klausel war auf den ursprünglichen Anstoß
            # bezogen; nach »falsch« ist es verbraucht — der gepatchte Aufruf
            # läuft IMMER durch das zweistufige Confirm-Gate, selbst für
            # Skills wie einkauf_hinzufuegen (auto_confirm=True). Der Branch
            # fällt im Korrektur-State stattdessen in den propose-Pfad unten.
            if (task.kind == WRITE
                    and getattr(task, "auto_confirm", False)
                    and correction_state is None):
                try:
                    write_result = catalog.execute_write_task(
                        task, call.arguments, turn_context)
                except Exception as e:
                    # EC-35: Skill ist fehlgeschlagen — als error tracken.
                    _called_skills.add(call.task)
                    _error_skills.add(call.task)
                    result_blocks.append(TaskResultBlock(
                        call_id=call.call_id,
                        content="Aufgabe fehlgeschlagen: %s" % e,
                        is_error=True))
                    continue
                # EC-35: erfolgreicher auto_confirm Write — als success tracken.
                _called_skills.add(call.task)
                reply = write_result.reply if write_result else ""
                result_blocks.append(TaskResultBlock(
                    call_id=call.call_id,
                    content=reply or "OK",
                    is_error=False))
                continue

            if task.kind == WRITE:
                try:
                    proposal = task.propose(call.arguments, turn_context)
                except Exception as e:  # Aufgabe isoliert melden
                    result_blocks.append(TaskResultBlock(
                        call_id=call.call_id,
                        content="Aufgabe nicht möglich: %s" % e, is_error=True))
                    continue
                # #310 (T310-S3): das vorgeschlagene tool_use MUSS gepaart
                # werden, sonst sitzt ein unpaariges tool_use in der Mitte der
                # persistierten History → Folge-Turn schickt es ungepaart an
                # Anthropic → 400. Wir hängen einen SYNTHETISCHEN TaskResultBlock
                # mit derselben call_id an (als User-Zug, wie ein echtes
                # tool_result). Das tool_use bleibt damit sichtbar — das Modell
                # sieht für WRITE-Aufgaben weiterhin seinen Werkzeug-Aufruf
                # (sonst dieselbe Vergiftung wie der Ursprungs-Bug, nur fürs
                # Eintragen). EC-7 (Ehrlichkeit): der Result-Text behauptet NICHT,
                # der Write sei ausgeführt — nur dass der Vorschlag vorliegt; die
                # Ausführung passiert erst nach Bestätigung (EC-10).
                messages.append(Message(role="user", blocks=[TaskResultBlock(
                    call_id=call.call_id,
                    content=_proposal_pending(task.name),
                    is_error=False)]))
                # EC-35: WRITE-Vorschlag = abort für diesen Skill.
                if task_events_store is not None:
                    task_events_store.insert(call.task, turn_context.chat_id,
                                             "abort")
                # Den reinen Vorschlagstext hängt die Orchestrierung an (via
                # _format_proposal) — er ist nicht Teil des Loop-Transkripts.
                return AgentResult(proposal=proposal, pending_call=call,
                                   telemetry=telemetry,
                                   transcript=messages[len(history_messages):])

            # EC-9: lesende Aufgabe — direkt ausführen, Ergebnis zurückspeisen.
            try:
                content = task.run(call.arguments, turn_context)
            except Exception as e:  # Aufgabe isoliert melden
                # EC-35: Skill geworfen — als error tracken.
                _called_skills.add(call.task)
                _error_skills.add(call.task)
                result_blocks.append(TaskResultBlock(
                    call_id=call.call_id,
                    content="Fehler bei der Aufgabe: %s" % e, is_error=True))
                continue
            # EC-35: lesender Skill erfolgreich abgeschlossen.
            _called_skills.add(call.task)
            # TASK-10c Form (b): dict mit text+presentation → Framework übersetzt.
            # Der Skill sendet nichts selbst; render_form_b sendet via tg und gibt
            # eine Quittungs-Zeichenkette zurück, die als content gesetzt wird.
            if (isinstance(content, dict)
                    and "text" in content
                    and "presentation" in content):
                _chat_id = turn_context.chat_id if turn_context else None
                # EC-41: Vor render_form_b prüfen, ob ein Inline-Button gerendert
                # wird — die Quittungs-Zeichenkette enthält dann "Inline-Button" /
                # "Inline-Buttons" / "WebApp-Link". Flag triggert die aggressive
                # Stripper-Stufe im finalen reply_text.
                _presentation = content.get("presentation") or {}
                if ("inline_button" in _presentation
                        or "inline_buttons" in _presentation
                        or "webapp_link" in _presentation):
                    _inline_button_emitted = True
                content = (render_form_b(content, tg, _chat_id)
                           if tg is not None else content.get("text", ""))
            result_blocks.append(TaskResultBlock(
                call_id=call.call_id, content=content, is_error=False))

        # Ergebnisse als Nutzer-Zug zurückgeben, Schleife fortsetzen.
        messages.append(Message(role="user", blocks=result_blocks))

    # Obergrenze erreicht — sauber abbrechen statt endlos zu schleifen.
    # #310: den Abbruch-Text als finalen Assistant-TextBlock ans Transkript
    # hängen (neue Liste, nicht `messages` mutieren — EC-13), damit die
    # persistierte History auch hier den vollen Tool-Turn-Verlauf bis zur
    # Antwort trägt (gleiche Reihenfolge wie der Erfolgs-Pfad).
    # EC-35: Max-Iterationen-Abbruch → gave_up → alle bekannten Skills als
    # abort persistieren.
    if task_events_store is not None:
        for name in _called_skills:
            task_events_store.insert(name, turn_context.chat_id, "abort")
    transcript = (messages[len(history_messages):]
                  + [Message(role="assistant", blocks=[TextBlock(_GAVE_UP)])])
    return AgentResult(reply_text=_GAVE_UP, telemetry=telemetry,
                       transcript=transcript)
