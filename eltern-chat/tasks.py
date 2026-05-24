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
    """Eine schreibende Aufgabe (EC-10): verändert Familien-Daten."""

    kind = WRITE

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


def build_catalog(tg, ca_pem_path, family_registry_path=None,
                  faa_sessions=None, family_group_chat_id_getter=None):
    """Baut den Katalog für eine laufende Instanz.

    Registriert die CA-Verteilungs-Aufgabe (`ca_verteilung.md` CAV-6, lesend)
    und — wenn die FAA-Abhängigkeiten vorliegen — die »Familie anlegen«-
    Aufgabe (`familie-anlegen.md` FAA-12, schreibend). Die instanz-festen
    Abhängigkeiten reicht die Orchestrierung hier herein; das ermöglicht
    einer Test-Umgebung, den Katalog ohne FAA-Setup zu bauen (`build_catalog
    (tg, ca_path)` bleibt unverändert kompatibel zu den CAV-Tests). Weitere
    Aufgaben werden additiv ergänzt (EC-8).
    """
    # Lokale Imports: brechen den Import-Zyklus tasks <-> ca_task/faa_task —
    # nicht hochziehen.
    from ca_task import CaVerteilungTask

    catalog = Catalog()
    catalog.register(CaVerteilungTask(tg, ca_pem_path))

    if family_registry_path is not None and faa_sessions is not None \
            and family_group_chat_id_getter is not None:
        from familie_anlegen_task import FamilieAnlegenTask
        catalog.register(FamilieAnlegenTask(
            tg, family_registry_path, faa_sessions,
            family_group_chat_id_getter))
    return catalog
