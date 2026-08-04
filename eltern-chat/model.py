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
    """Was der Agent-Kern dem Anbieter-Adapter übergibt.

    `correlation_id` (T1085, EC-23-Spiegel auf die JSONL-Telemetrie): die
    Turn-ID, mit der `tools.llm` den JSONL-Eintrag (`var/llm/provider_calls.jsonl`)
    an denselben Turn knüpft wie die SQLite-Doppelschreibung. Optional und als
    letztes Feld defaultet — alle bestehenden `GenerationRequest(...)`-
    Konstruktionen bleiben unverändert gültig. Adapter, die keine JSONL-
    Telemetrie schreiben (`ClaudeProvider`/`MistralProvider`), ignorieren das
    Feld; nur der `LibAgentAdapter` reicht es an die Lib durch.
    """
    system: str
    messages: list           # list[Message]
    task_defs: list          # list[TaskDef]
    correlation_id: str = None   # str | None — Turn-ID für JSONL (T1085)


@dataclass
class ProviderUsage:
    """Token-Verbrauch eines Anbieter-Aufrufs — anbieter-neutral (EC-23, #268).

    Vier Counter und die Modell-ID, mit der der Aufruf gerechnet hat. Der
    Adapter füllt diese Werte aus seiner Anbieter-spezifischen Antwort. Wenn
    der Adapter keine Usage-Daten hat (z. B. ein älterer Test-Mock), bleibt
    `GenerationResponse.usage` einfach `None`.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    model_id: str = ""


@dataclass
class GenerationResponse:
    """Was der Anbieter-Adapter zurückgibt — anbieter-neutral.

    `text` ist die Prosa-Antwort, `task_calls` die gewünschten Aufgaben-Aufrufe.
    `usage` (optional, EC-23/#268) ist der Token-Verbrauch dieses Aufrufs.
    Adapter, die keine Usage-Daten liefern, lassen das Feld auf `None` —
    die Telemetrie hängt dann einen Stub-Eintrag an (siehe `telemetry.py`).
    """
    text: str
    task_calls: list = field(default_factory=list)   # list[TaskCallBlock]
    usage: object = None                             # ProviderUsage | None


# ============================================================
#  Fehler
# ============================================================

class ProviderError(Exception):
    """Der KI-Anbieter war nicht erreichbar oder hat fehlerhaft geantwortet.

    Wird vom Adapter geworfen und in der Orchestrierung zu einem klaren Hinweis
    an das Familienmitglied (EC-14) verarbeitet.

    Optionales Attribut `telemetry` (EC-23/#268): wird vom `agent.run_turn`-
    Wrapper gesetzt, bevor er die Exception weiterwirft. Die Orchestrierung
    (`main._run_agent`) persistiert die Telemetrie dann, bevor sie den
    Provider-Down-Hinweis sendet — ein gescheiterter Provider-Call bleibt für
    die spätere Diagnose nicht verloren.
    """

    telemetry = None
