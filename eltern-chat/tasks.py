"""Aufgaben-Katalog — siehe specs/platform/eltern-chat.md EC-8/EC-9/EC-10
(Refs #27).

Dieses Modul ist der RAHMEN: ein Registrierungs-Mechanismus, die Unterscheidung
lesend/schreibend und der deterministische Ausführungs-Kontext (`TurnContext`).
Die einzelnen Aufgaben kommen je aus einer eigenen, reviewten Spec mit eigenem
Ticket (EC-8) und leben in eigenen Modulen; `build_catalog` registriert sie.

Lesende Aufgaben (EC-9) laufen direkt: `ReadTask.run()`. Schreibende Aufgaben
(EC-10) sind zweiphasig: `WriteTask.propose()` legt einen strukturierten
Vorschlag vor, `WriteTask.execute()` führt ihn erst nach Bestätigung aus. Die
Bestätigung selbst liegt außerhalb dieses Moduls und außerhalb des Agent-Loops
(confirm.py, E-EC-4).
"""

from dataclasses import dataclass

from hooks import HookContext, HookFailure, summarize_failures
from model import READ, WRITE, TaskDef


@dataclass
class TurnContext:
    """Deterministischer Ausführungs-Kontext einer Anfrage, getrennt vom Modell.

    Diese Daten reicht die Orchestrierung an eine Aufgabe durch, OHNE dass das
    Sprachmodell sie sieht oder beeinflusst (EC-12-Geist): der Modell-Kanal ist
    allein `arguments`. So kann eine Aufgabe z. B. ihren Zielchat verlässlich
    aus dem Kontext nehmen, statt einer vom Modell gelieferten ID zu vertrauen.

    `chat_id` ist der Chat der eingehenden Anfrage (Familien-Gruppe oder
    Privatchat). `private_chat_id` ist der Privatchat des Aufrufers — bei
    einer Privatchat-Anfrage identisch zu `chat_id`, bei einer Gruppen-Anfrage
    die User-ID des Aufrufers (Telegram-Privatchat-ID == User-ID). `from_user_id`
    ist die Telegram-User-ID des Aufrufers. Die Aufnahme dieser Felder ist load-
    bearing für FAA-12 (`familie_anlegen_task`): der Anlage-Dialog läuft im
    Privatchat, nicht in der Gruppe (analog ONB-3).
    """
    chat_id: object
    from_user_id: object = None
    private_chat_id: object = None


def is_from_private_chat(turn_context):
    """True, wenn die Anfrage IM Privatchat des Aufrufers gestellt wurde
    (Refs #157).

    Konvention aus `TurnContext` (s.o.): bei einer Privatchat-Anfrage sind
    `chat_id` und `private_chat_id` identisch (`main._user_message_from`
    bzw. der Bau in `handle_update`/`_execute_confirmed` setzt
    `private_chat_id = chat_id` für `chat_type == "private"`). Bei einer
    Gruppen-Anfrage steht in `chat_id` die Gruppe und in `private_chat_id`
    die User-ID — sie unterscheiden sich.

    Helfer hier in `tasks.py`, weil die drei Privatchat-Sessions (FAA/GAA/KAV)
    dieselbe Logik brauchen und `tasks.py` schon Heimat des `TurnContext`
    ist — kein zusaetzliches Modul noetig, kein Import-Zyklus.
    """
    if turn_context is None:
        return False
    pid = turn_context.private_chat_id
    if pid is None:
        return False
    return turn_context.chat_id == pid


@dataclass
class WriteTaskResult:
    """Ergebnis einer ueber das Framework ausgefuehrten Schreib-Aufgabe
    (EC-21, #140).

    `reply` ist die Quittung der Aufgabe (das, was `execute()` zurueckgegeben
    hat). `warning` ist eine optionale Familien-Warnung, die das Framework
    aus den fehlgeschlagenen Hooks zusammensetzt — leer, wenn alle Hooks
    durchgelaufen sind oder gar keine deklariert waren.

    Aufrufer bauen aus beiden Feldern die Antwort an die Familie: typisch
    `reply + "\\n\\n" + warning` (siehe `combined_text`). Die Trennung gibt
    main.py Spielraum, die Warnung anders zu formatieren, falls noetig.
    """
    reply: str
    warning: str = ""
    hook_failures: tuple = ()

    def combined_text(self):
        """Antwort + Warnung als ein Stueck Text — was an die Familie geht."""
        if not self.warning:
            return self.reply
        return "%s\n\n%s" % (self.reply, self.warning)


@dataclass
class Proposal:
    """EC-10: ein strukturierter Vorschlag — was genau geschehen würde.

    `summary` ist die menschenlesbare Beschreibung der geplanten Änderung. Die
    gebundenen Argumente werden separat geführt (confirm.py), damit die
    Ausführung exakt den vorgeschlagenen Eingaben folgt.
    """
    summary: str


class Task:
    """Basis einer Katalog-Aufgabe. Nicht direkt registrieren — `ReadTask`
    oder `WriteTask` verwenden."""

    kind = None   # von der Unterklasse gesetzt

    def __init__(self, name, description, parameters):
        self.name = name
        self.description = description
        self.parameters = parameters   # JSON-Schema der Eingaben

    def to_def(self):
        """Anbieter-neutrale Definition für den Agenten/Anbieter."""
        return TaskDef(name=self.name, description=self.description,
                       kind=self.kind, parameters=self.parameters)


class ReadTask(Task):
    """Eine lesende Aufgabe (EC-9): liefert nur Information, ändert keine Daten."""

    kind = READ

    def run(self, arguments, turn_context):
        """Führt die Aufgabe aus und liefert das Ergebnis als Text.

        `arguments` ist der Modell-Kanal; `turn_context` ist der deterministische
        Ausführungs-Kontext (`TurnContext`), den das Modell nicht beeinflusst.
        """
        raise NotImplementedError


class WriteTask(Task):
    """Eine schreibende Aufgabe (EC-10): verändert Familien-Daten.

    Eine Unterklasse darf `post_execute_hooks` setzen (EC-21, #140) — eine
    Liste zustandsloser Hooks, die nach erfolgreichem `execute()` laufen
    und typisch einen konsumierenden Buddy auffordern, seinen In-Memory-
    Cache neu zu laden. Default ist leer: ohne explizite Deklaration
    aendert sich am Verhalten nichts."""

    kind = WRITE

    # Klassenattribut — Unterklassen ueberschreiben es mit ihrer eigenen
    # Hook-Liste. Wird vom Framework gelesen, nicht von der Aufgabe selbst.
    post_execute_hooks = ()

    def propose(self, arguments, turn_context):
        """Legt einen `Proposal` vor — führt NICHTS aus."""
        raise NotImplementedError

    def execute(self, arguments, turn_context):
        """Führt die Aufgabe aus (erst nach Bestätigung aufzurufen)."""
        raise NotImplementedError


class Catalog:
    """Registry der verfügbaren Aufgaben (EC-8).

    Aufgaben werden additiv ergänzt; der bestehende Katalog bleibt unberührt.
    Ist der Katalog leer, kann der Agent keine Aufgabe ausführen — jede
    aufgaben-artige Anfrage führt dann zur ehrlichen Grenze (EC-7).
    """

    def __init__(self):
        self._tasks = {}

    def register(self, task):
        """Registriert eine Aufgabe. Doppelte Namen sind ein Fehler."""
        if not isinstance(task, (ReadTask, WriteTask)):
            raise TypeError("Aufgabe muss ReadTask oder WriteTask sein")
        if task.name in self._tasks:
            raise ValueError("Aufgabe '%s' ist bereits registriert" % task.name)
        self._tasks[task.name] = task

    def get(self, name):
        """Liefert die Aufgabe oder None, wenn sie nicht im Katalog ist."""
        return self._tasks.get(name)

    def task_defs(self):
        """Anbieter-neutrale Definitionen aller registrierten Aufgaben."""
        return [t.to_def() for t in self._tasks.values()]

    def execute_write_task(self, task, arguments, turn_context):
        """Fuehrt eine schreibende Aufgabe inkl. Post-Execute-Hooks aus
        (EC-21, #140).

        Lifecycle:
        1. `task.execute(arguments, turn_context)` — die eigentliche Aufgabe.
           Wirft sie eine Exception, propagiert die nach aussen (das
           Framework rollt nicht zurueck — der Aufrufer entscheidet, ob
           er das als Aufgaben-Fehlschlag meldet).
        2. Nach erfolgreichem `execute()`: ueber `task.post_execute_hooks`
           iterieren, jeden synchron aufrufen, Ergebnisse sammeln.
        3. Hook-Fehler **rollen die Schreib-Aufgabe nicht zurueck** (EC-21):
           die Aenderung ist durch. Mehrere fehlgeschlagene Hooks landen
           in EINER zusammengefassten Warnung an die Familie.

        Hook-Aufrufe sind isoliert: wirft ein Hook (gegen die Konvention!)
        doch eine Exception, faengt das Framework sie als HookFailure ab —
        sonst koennten weitere Hooks oder die Quittung verloren gehen.
        """
        reply = task.execute(arguments, turn_context)
        hooks = getattr(task, "post_execute_hooks", ()) or ()
        if not hooks:
            return WriteTaskResult(reply=reply)
        context = HookContext(task_name=task.name, turn_context=turn_context)
        failures = []
        for hook in hooks:
            try:
                result = hook(context)
            except Exception as e:   # noqa: BLE001 — siehe EC-21-Notiz oben
                failures.append(HookFailure(
                    consumer=getattr(hook, "consumer", task.name),
                    error="unerwarteter Fehler (%s)" % e))
                continue
            if isinstance(result, HookFailure):
                failures.append(result)
        warning = summarize_failures(failures)
        return WriteTaskResult(reply=reply, warning=warning,
                               hook_failures=tuple(failures))


def build_catalog(tg, ca_pem_path, family_registry_path=None,
                  faa_sessions=None, family_group_chat_id_getter=None,
                  geraete_registry_path=None, gaa_sessions=None,
                  cav_call_hook=None, display_url_origin=None,
                  zd_store_getter=None, kav_sessions=None,
                  plan_json_path=None):
    """Baut den Katalog für eine laufende Instanz.

    Registriert die CA-Verteilungs-Aufgabe (`ca_verteilung.md` CAV-6, lesend),
    — wenn die FAA-Abhängigkeiten vorliegen — die »Familie anlegen«-Aufgabe
    (`familie-anlegen.md` FAA-12, schreibend), — wenn die GAA-Abhängigkeiten
    vorliegen — die »Gerät anlegen«-Aufgabe (`geraet-anlegen.md` GAA-5,
    schreibend) und — wenn die KAV-Abhängigkeiten vorliegen — die »Kalender
    verbinden«-Aufgabe (`kalender-verbinden.md` KAV-3, schreibend). Die
    instanz-festen Abhängigkeiten reicht die Orchestrierung hier herein; das
    ermöglicht einer Test-Umgebung, den Katalog ohne FAA-/GAA-/KAV-Setup
    zu bauen (`build_catalog(tg, ca_path)` bleibt unverändert kompatibel zu
    den CAV-Tests). Weitere Aufgaben werden additiv ergänzt (EC-8).
    """
    # Lokale Imports: brechen den Import-Zyklus tasks <-> ca_task/faa_task/
    # gaa_task/kav_task — nicht hochziehen.
    from skills.ca_task import CaVerteilungTask

    catalog = Catalog()
    catalog.register(CaVerteilungTask(tg, ca_pem_path))

    if family_registry_path is not None and faa_sessions is not None \
            and family_group_chat_id_getter is not None:
        from skills.familie_anlegen_task import FamilieAnlegenTask
        catalog.register(FamilieAnlegenTask(
            tg, family_registry_path, faa_sessions,
            family_group_chat_id_getter))

    if geraete_registry_path is not None and gaa_sessions is not None \
            and family_group_chat_id_getter is not None:
        from skills.geraet_anlegen_task import GeraetAnlegenTask
        catalog.register(GeraetAnlegenTask(
            tg, geraete_registry_path, gaa_sessions,
            family_group_chat_id_getter,
            cav_call_hook=cav_call_hook,
            display_url_origin=display_url_origin))

    if zd_store_getter is not None and kav_sessions is not None \
            and family_group_chat_id_getter is not None:
        from skills.kalender_verbinden_task import KalenderVerbindenTask
        catalog.register(KalenderVerbindenTask(
            tg, zd_store_getter, kav_sessions,
            family_group_chat_id_getter,
            plan_json_path=plan_json_path))
    return catalog
