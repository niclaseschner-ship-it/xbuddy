"""Kanonisches, anbieter-neutrales Modell — siehe specs/platform/eltern-chat.md
E-EC-6 (Refs #27).

Der Agent-Kern (agent.py) und der Aufgaben-Katalog (tasks.py) arbeiten
ausschließlich mit diesen Typen. Anbieter-spezifisches JSON existiert nur im
jeweiligen Adapter unter providers/ und wird dort in dieses Modell übersetzt —
der Kern fasst es nie an. So bleibt der Anbieterwechsel (EC-11) eine reine
Konfigurations-Änderung.
"""

from dataclasses import dataclass, field


# ============================================================
#  Inhalts-Blöcke einer Nachricht
# ============================================================

@dataclass
class TextBlock:
    """Freitext — Anfrage des Familienmitglieds oder Antwort des Agenten."""
    text: str


@dataclass
class ImageBlock:
    """Ein geteiltes Bild (EC-4), anbieter-neutral als Base64."""
    media_type: str          # z. B. "image/jpeg"
    data_b64: str


@dataclass
class TaskCallBlock:
    """Der Agent möchte eine Katalog-Aufgabe aufrufen (EC-8)."""
    call_id: str             # eindeutige ID, verknüpft Aufruf und Ergebnis
    task: str                # Aufgaben-Bezeichnung
    arguments: dict


@dataclass
class TaskResultBlock:
    """Ergebnis einer Aufgabe, das in den Loop zurückgegeben wird."""
    call_id: str
    content: str
    is_error: bool = False


# ============================================================
#  Nachricht
# ============================================================

@dataclass
class Message:
    """Eine Gesprächs-Nachricht. `role` ist "user" oder "assistant".

    `blocks` ist eine Liste von Inhalts-Blöcken: eine Nutzer-Nachricht trägt
    Text/Bilder (und im Loop Task-Ergebnisse), eine Assistant-Nachricht Text
    und/oder Task-Aufrufe.
    """
    role: str
    blocks: list = field(default_factory=list)


# ============================================================
#  Aufgaben-Definition (was dem Anbieter als verfügbares Werkzeug gereicht wird)
# ============================================================

READ = "read"
WRITE = "write"


@dataclass
class TaskDef:
    """Anbieter-neutrale Beschreibung einer Katalog-Aufgabe.

    `kind` ist READ oder WRITE. `parameters` ist ein JSON-Schema der Eingaben.
    """
    name: str
    description: str
    kind: str
    parameters: dict


# ============================================================
#  Anfrage / Antwort an den KI-Anbieter
# ============================================================

@dataclass
class GenerationRequest:
    """Was der Agent-Kern dem Anbieter-Adapter übergibt."""
    system: str
    messages: list           # list[Message]
    task_defs: list          # list[TaskDef]


@dataclass
class GenerationResponse:
    """Was der Anbieter-Adapter zurückgibt — anbieter-neutral.

    `text` ist die Prosa-Antwort, `task_calls` die gewünschten Aufgaben-Aufrufe.
    """
    text: str
    task_calls: list = field(default_factory=list)   # list[TaskCallBlock]


# ============================================================
#  Fehler
# ============================================================

class ProviderError(Exception):
    """Der KI-Anbieter war nicht erreichbar oder hat fehlerhaft geantwortet.

    Wird vom Adapter geworfen und in der Orchestrierung zu einem klaren Hinweis
    an das Familienmitglied (EC-14) petrarbeitet.
    """
