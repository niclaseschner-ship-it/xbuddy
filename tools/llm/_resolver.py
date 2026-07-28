"""Slot- und Vendor-Auflösung für `tools.llm` (LLMP-2, LLMP-5).

Übersetzt einen Slot-Namen `<konsument>-<vendor>-<purpose>` (ZD-2-Konvention,
LLMP-5) in (a) den API-Key aus `tools.zugangsdaten` und (b) das zugehörige
`_vendor/<vendor>.py`-Modul. Die Lib trifft hier **keine** Konfigurations-
Entscheidungen — welcher Vendor unter welchem Slot lebt, ist Buddy-Sache.

Slot-Form (LLMP-5, ZD-2):

    kibuddy-anthropic-api-key
    eltern-chat-anthropic-api-key
    hoerspiel-anthropic-api-key

Drei Segmente, Bindestrich-getrennt. Der Parser identifiziert das Vendor-
Segment per Lookup gegen die vorhandenen `_vendor/<vendor>.py`-Module —
nicht per Positions-Annahme. Damit dürfen Konsumenten-Namen Bindestriche
enthalten (`eltern-chat`), ohne den Parser zu brechen.
"""

import importlib
import pkgutil
import sys
from types import ModuleType

from ._types import LLMCapabilityError


def _known_vendors() -> list[str]:
    """Listet die `_vendor/<vendor>.py`-Module zur Boot-Zeit (LLMP-4).

    Quelle ist primär das Filesystem-Verzeichnis `tools/llm/_vendor/`
    (jede `.py`-Datei außer `__init__.py` ist ein Vendor-Slug). Zusätzlich
    werden bereits in `sys.modules` registrierte `tools.llm._vendor.<x>`-
    Module mitgenommen — das deckt Test-Fixtures ab, die Vendor-Module
    dynamisch ein-/aushängen (LLMP-S11 Test-Pfad), und ist konsistent mit
    `load_vendor_module`, das letztlich `sys.modules` befüllt.
    """
    from . import _vendor
    vendors = set()
    for info in pkgutil.iter_modules(_vendor.__path__):
        if info.ispkg:
            continue
        if info.name.startswith("_"):
            continue
        vendors.add(info.name)
    # Dynamisch eingehängte Vendor-Module (Test-Fixtures, Folge-Vendoren,
    # die zur Laufzeit registriert wurden — selten in Prod, klar in Tests).
    prefix = "tools.llm._vendor."
    for mod_name in sys.modules:
        if not mod_name.startswith(prefix):
            continue
        suffix = mod_name[len(prefix):]
        if not suffix or "." in suffix or suffix.startswith("_"):
            continue
        vendors.add(suffix)
    return sorted(vendors)


def parse_slot(slot: str) -> tuple[str, str, str]:
    """Zerlegt `<konsument>-<vendor>-<purpose>` (LLMP-5).

    Liefert (caller, vendor, purpose). Mechanik (siehe LLMP-5 Doku):

      1. Slot an `-` in Segmente splitten.
      2. Bekannte Vendor-Slugs auf Modul-Ebene auflisten
         (`pkgutil.iter_modules(tools.llm._vendor.__path__)`).
      3. Eindeutiges Segment finden, das in der Vendor-Liste vorkommt — das
         ist `vendor`.
      4. Alles davor → `caller` (bindestrich-zusammengefügt), alles danach
         → `purpose`.

    Caller darf Bindestriche enthalten (`eltern-chat`), ebenso Purpose
    (`api-key`). Wenn kein Segment matcht oder mehrere matchen, wird ein
    `LLMCapabilityError` mit der Liste der bekannten Vendoren geworfen
    (LLMP-S3 Begründung: Slot-Vendor-Mismatch ist sichtbare Konfigurations-
    Entscheidung, kein `ModuleNotFoundError`).
    """
    if not isinstance(slot, str) or not slot.strip():
        raise ValueError("tools.llm: slot muss ein nicht-leerer String sein")
    parts = slot.split("-")
    if len(parts) < 3:
        raise ValueError(
            "tools.llm: slot %r folgt nicht der LLMP-5-Konvention "
            "<konsument>-<vendor>-<purpose>" % slot
        )

    vendors = _known_vendors()
    matches = [(i, seg) for i, seg in enumerate(parts) if seg in vendors]

    if not matches:
        raise LLMCapabilityError(
            "tools.llm: kein bekanntes Vendor-Segment in slot %r — "
            "bekannte Vendoren: %s (LLMP-5/LLMP-S3)"
            % (slot, ", ".join(vendors) if vendors else "(keine)")
        )
    if len(matches) > 1:
        raise LLMCapabilityError(
            "tools.llm: mehrdeutiger Slot %r — mehrere Segmente passen auf "
            "bekannte Vendoren: %s (LLMP-5)"
            % (slot, ", ".join(seg for _, seg in matches))
        )

    vendor_idx, vendor = matches[0]
    caller_parts = parts[:vendor_idx]
    purpose_parts = parts[vendor_idx + 1:]
    if not caller_parts:
        raise ValueError(
            "tools.llm: slot %r hat leeren caller-Teil (LLMP-5 verlangt "
            "<konsument>-<vendor>-<purpose>)" % slot
        )
    if not purpose_parts:
        raise ValueError(
            "tools.llm: slot %r hat leeren purpose-Teil (LLMP-5 verlangt "
            "<konsument>-<vendor>-<purpose>)" % slot
        )
    caller = "-".join(caller_parts)
    purpose = "-".join(purpose_parts)
    return caller, vendor, purpose


# LLMP-S13 (#1463): der EINE zentrale Ort für die anbieter-spezifische Modell-
# Präfix-Normalisierung. LiteLLM (der Multi-Anbieter-Motor) routet ein
# Mistral-Modell NUR mit dem Präfix `mistral/<modell>`; das Repo führt aber blanke
# Namen (`mistral-medium-2508`, HSP-27). Ohne dieses Präfix brach der #1452-Deploy
# (`LLM Provider NOT provided`). Die Normalisierung sitzt hier — vor den
# `get_*`-Sichten, an einer Stelle für alle Anbieter, NICHT pro Vendor-File. Der
# Aufrufer muss das Präfix nicht kennen.
#
# Erkennung per Modellnamen-Signatur (nicht per Vendor-Verzweigung): ein blanker
# Mistral-Modellname beginnt mit `mistral-` (bzw. den weiteren Mistral-Familien).
# Trägt der Name bereits ein `provider/`-Präfix (`azure/…`, `mistral/…`), bleibt
# er unangetastet; Claude-Modelle (`claude-…`) erkennt LiteLLM am blanken Namen
# und bleiben ebenfalls unberührt.
_MISTRAL_MODEL_PREFIXES = ("mistral-", "magistral-", "codestral-", "pixtral-", "ministral-")


def normalize_model(model: str) -> str:
    """Ergänzt das LiteLLM-Anbieter-Präfix am Modellnamen (LLMP-S13, #1463).

    Zentral vor den `get_*`-Sichten aufgerufen (`public_api._build_vendor`), an
    genau EINEM Ort für alle Anbieter — keine Pro-Vendor-Verzweigung. Regeln:

      - leerer Name (Vendor-Default greift) → unverändert leer zurück.
      - Name trägt bereits ein `provider/`-Präfix (`azure/…`, `mistral/…`) →
        unverändert (nicht doppelt präfixen).
      - blanker Mistral-Modellname (`mistral-…`, `magistral-…`, …) →
        `mistral/<name>` (LiteLLM-Routing).
      - alles andere (Claude `claude-…` u. a.) → unverändert; LiteLLM erkennt es
        am blanken Namen.
    """
    if not model or "/" in model:
        return model
    if model.startswith(_MISTRAL_MODEL_PREFIXES):
        return "mistral/" + model
    return model


def load_vendor_module(vendor: str) -> ModuleType:
    """Importiert `tools.llm._vendor.<vendor>` (LLMP-4 Re-Export-Form).

    Wenn das Modul fehlt (etwa nach manipuliertem Slot, der `parse_slot`
    nicht durchlief), übersetzt diese Funktion `ModuleNotFoundError` in
    `LLMCapabilityError` — analog `parse_slot`, damit Konfigurationsfehler
    eine einheitliche Klasse haben (LLMP-S3).
    """
    try:
        return importlib.import_module("tools.llm._vendor.%s" % vendor)
    except ModuleNotFoundError as exc:
        raise LLMCapabilityError(
            "tools.llm: Vendor-Modul %r nicht vorhanden — bekannte Vendoren: %s "
            "(LLMP-4/LLMP-S3)" % (vendor, ", ".join(_known_vendors()) or "(keine)")
        ) from exc


def resolve_api_key(slot: str) -> str | None:
    """Holt den API-Key zum Slot über `tools.zugangsdaten` (LLMP-S2, ZD-5).

    Liefert `None`, wenn der Slot nicht im Speicher liegt — der Konsument
    entscheidet, was das bedeutet (analog ZD-7).
    """
    # Lazy-Import: Test-Module, die `resolve_api_key` nicht brauchen, müssen
    # `tools.zugangsdaten` nicht laden — Test-Isolation analog
    # `kibuddy/providers/claude.py` (anthropic-SDK lazy).
    from tools.zugangsdaten import Zugangsdaten, resolve_store_path
    speicher = Zugangsdaten(resolve_store_path())
    return speicher.get(slot)


def slot_present(slot: str) -> bool:
    """Reine Präsenz-Prüfung eines Slots im Zugangsdaten-Speicher (SVC-7).

    Liefert `True`, wenn zum Slot ein nicht-leerer API-Key im Speicher liegt,
    sonst `False`. Wrapper um `resolve_api_key` — KEIN Anbieter-Call, KEIN
    Vendor-Bau, KEINE Capability-Prüfung (das erledigt erst `get_*`/`_build_vendor`
    beim echten Nutzungs-Zeitpunkt).

    Gedacht für den Startup-Preflight LLM-nutzender Services (SVC-7): der Service
    prüft die Präsenz seiner Pflicht-Slots VOR dem eager Vendor-Bau und bricht mit
    einer klaren `FEHLT: <slot>`-Zeile + Exit ab, statt mitten im Boot einen
    `LLMCapabilityError` zu werfen. So fangen die Services fehlende Slots am
    Boot-Zeitpunkt (sichtbar), nicht erst im n-ten Turn.
    """
    return bool(resolve_api_key(slot))
