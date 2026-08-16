"""Foto-Analyse — multimodale Termin-Extraktion über `tools.llm` (#1262, T1262).

Neuer Foto-Adapter für den TAB-Pfad (specs/platform/termine-aus-bild.md TAB-5,
E-TAB-8): erfüllt denselben `MultimodalProvider`-Duck-Type wie der Legacy-Adapter
`_multimodal/claude.py` — `extract_termine(image_bytes, image_media_type, caption)
-> list[ExtractedTermin]` (base.py:70) — führt den Anbieter-Call aber NICHT mehr
selbst aus. Er reicht Bild + Prompt + hart-codiertes Tool-Schema an die geteilte
LLM-Provider-Library `tools.llm` (Singleshot-Sicht `get_singleshot(...)
.complete_structured(..., images=[…])`) durch. Das anbieter-spezifische JSON
(base64-Bild-Block, forced tool_use, Telemetrie) lebt damit zentral im Vendor-
Modul, nicht mehr pro eltern-chat-Adapter (LLMP-S1).

Warum eine eigene Datei statt `providers/lib_adapter.py`: der TAB-Pfad braucht das
**domänenspezifische** `extract_termine`-Tool-Schema (Termin-Liste), das nicht in
den Konversations-Pfad (EC-6) gehört — dieselbe Trennung, die schon `_multimodal/`
gegenüber `providers/` hielt.

Typen-Heimat (#1262, PR2 #1334): Diese Datei ist die kanonische HEIMAT der
Typen `ExtractedTermin` und `MultimodalError` für den Foto-Pfad — neuer Code
importiert sie von HIER (`termine_aus_bild.py` zeigt hierher). Die physischen
Klassen-Definitionen sind in dieser Datei (Löschung von `_multimodal/` in #1334
abgeschlossen).

ZD-Slot (#1509, TAB-5, E-TAB-8): der API-Key kommt aus dem
`tools.zugangsdaten`-Store über den Slot
`eltern-chat-litellm-foto-analyse-api-key` (die Lib holt ihn selbst, ZD-5) —
NICHT mehr aus `config.multimodal_api_key`. Claude ist weiterhin gepinnt (über
das `_FOTO_MODEL`-Feld und den LiteLLM-Router, der Anthropic-Modellnamen
transparent routet). Der Vendor-Teil des Slots (`litellm`) aktiviert den
LiteLLM-Motor (RAT-20/RAT-26), der `multimodal_input` deklariert (#1509).
NICHT mehr `anthropic` (Hand-Vendor) — dieser bleibt bis zum vollständigen
anthropic-Abriss (#1511) erhalten; `foto_analyse` importiert ihn NICHT.

Datenlinie (EC-13 / E-TAB-5): nur Bild + Caption + Tool-Schema gehen raus; das
Bild wird nach der Extraktion verworfen (kein Photo-Buddy-Aufruf).
"""

import logging
from dataclasses import dataclass, field

from tools.llm import LLMCapabilityError, get_singleshot
from tools.llm import ProviderError as LibProviderError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Typen-Heimat (#1262, PR2 #1334): ExtractedTermin + MultimodalError sind
#  ab jetzt PHYSISCH hier definiert (Löschung von _multimodal/). Alle
#  Konsumenten importieren von hier — keine Re-Export-Ebene mehr nötig.
# ---------------------------------------------------------------------------


@dataclass
class ExtractedTermin:
    """Ein einzelner Termin-Vorschlag aus dem multimodalen Extraktions-Aufruf
    (TAB-5). Anbieter-neutral; der konkrete Adapter füllt die Felder aus seiner
    Tool-Use-Antwort.

    Pflicht-Felder (V1, vor Plausi-Filter TAB-6):
    - `titel`     — nicht-leerer Termin-Titel.
    - `beginn`    — ISO-Datum (`YYYY-MM-DD`) oder ISO-Datetime
                    (`YYYY-MM-DDTHH:MM:SS±HH:MM`) als String.

    Optionale Felder:
    - `ende`      — Pflicht für zeitgebundene Termine (PLAN-22); wenn das LLM
                    es leer lässt, wandert der Termin in den Lücken-Sammler
                    (TAB-8.1).
    - `ganztags`  — `True`/`False`. Falls leer → vom `beginn`-Format abgeleitet
                    (kein `T` → ganztägig).
    - `personen_hinweise` — frei formulierte Personen-Hinweise (TAB-8.2);
                    **nie** Pflicht, **nie** automatisch in den Titel
                    eingearbeitet (OPEN-TES-B respektiert).
    """
    titel: str = ""
    beginn: str = ""
    ende: str = ""
    ganztags: object = None       # bool | None
    personen_hinweise: str = ""

    # Interne Lückenfeld-Markierung (TAB-8.1) — Plausi-Filter setzt sie, der
    # Lücken-Sammler liest sie. Liste fehlender Felder als kanonische Namen
    # (z. B. ["titel"], ["ende"]).
    fehlende_felder: list = field(default_factory=list)


class MultimodalError(Exception):
    """Der multimodale Anbieter war nicht erreichbar oder hat keine verwertbare
    Antwort geliefert (TAB-5, EC-14-analog).

    Der TAB-Skill fängt das und liefert das Ergebnis-Signal `provider_fehler`
    zurück (TAB-1 / EC-7).
    """


# TAB-5 (E-TAB-8): ZD-Slot-Name — EINE Wahrheitsquelle. `tools.zugangsdaten`-Store
# via `tools.llm`-Resolver (ZD-5). Vendor-Segment `litellm` aktiviert den
# LiteLLM-Motor (#1509), der `multimodal_input` deklariert und Bild-Blocks ins
# OpenAI-Vision-Format übersetzt (LiteLLM routet transparent zum Anthropic-Backend).
FOTO_ANALYSE_SLOT = "eltern-chat-litellm-foto-analyse-api-key"

# TAB-5 / E-TAB-6: Foto-Modell. Ursprünglich gespiegelt vom Legacy-Fallback
# `_multimodal/claude.py:119` (`_FALLBACK_MODEL = "claude-opus-4-7"`) — diese
# Datei ist seit der #1334-Löschung (Typen-Heimat-Wanderung hierher) nicht
# mehr im Repo. Kein Spec-Pin dahinter: der konkrete Wert lebt seither allein
# hier. Auf `claude-opus-5` gehoben (T1807, gleicher Preis, s. Handoff für den
# Katalog-Beleg). Konstruktor-Override möglich (config `multimodal_model`).
_FOTO_MODEL = "claude-opus-5"
# TAB-5: Token-Budget wie der (gelöschte) Legacy-Adapter
# `_multimodal/claude.py:120` MAX_TOKENS = 4096; ohne explizite Übergabe nähme
# die Lib DEFAULT_MAX_TOKENS=2048 — stille Halbierung, die lange Termin-Listen
# trunkieren könnte (vgl. #1084-502). T1807/AC3: claude-opus-5 erlaubt laut
# litellm-Katalog max_output_tokens 128000 — 4096 bleibt weit darunter, kein
# Cutoff-Risiko durch den Modell-Wechsel selbst.
_MAX_TOKENS = 4096


# ----------------------------------------------------------------------
#  TAB-5: hart-codiertes Tool-Schema / Description / System-Prompt.
#  WÖRTLICH übernommen aus dem Legacy `_multimodal/claude.py` (TAB-5) —
#  stabile, vom Code gehaltene Schnittstelle (E-EC-4, TES-7-Vorbild). Das LLM
#  ist gezwungen, diese Form zu liefern; keine Modell-Formulierung.
# ----------------------------------------------------------------------

_TOOL_NAME = "extract_termine"
_TOOL_DESCRIPTION = (
    "Extrahiere ALLE im Bild sichtbaren Termine (Schulplan, Kursplan, "
    "Saison-Übersicht). Sowohl tabellarische Pläne als auch Fließtext-"
    "Notizen sind zu verarbeiten. Liefere die Termine in der Reihenfolge, "
    "in der sie im Bild erscheinen. Datums-Format: ISO (YYYY-MM-DD für "
    "ganztägige Termine, YYYY-MM-DDTHH:MM:SS+HH:MM für zeitgebundene). "
    "Wenn ein Termin offensichtlich eine Uhrzeit hat, beide Felder "
    "(`beginn` und `ende`) mit ISO-Datetime füllen. Ohne Uhrzeit: nur "
    "`beginn` mit ISO-Datum, `ganztags` = true. Wenn das Bild keine Termine "
    "enthält oder unleserlich ist, eine leere Liste zurückgeben.")

_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "termine": {
            "type": "array",
            "description": "Liste der erkannten Termine.",
            "items": {
                "type": "object",
                "properties": {
                    "titel": {
                        "type": "string",
                        "description": "Termin-Titel (z. B. 'Schulausflug', 'Klettern Mila').",
                    },
                    "beginn": {
                        "type": "string",
                        "description": (
                            "ISO-Datum (YYYY-MM-DD) für ganztägige Termine "
                            "ODER ISO-Datetime (YYYY-MM-DDTHH:MM:SS+HH:MM) "
                            "für zeitgebundene Termine. "
                            "Fehlt die Jahreszahl im Bild, leite sie aus dem "
                            "Begleittext ab (z. B. 'Jahr 2026 verwenden') — "
                            "erfinde das Jahr nicht, wenn kein Hinweis vorliegt."),
                    },
                    "ende": {
                        "type": "string",
                        "description": (
                            "ISO-Datum oder ISO-Datetime. Pflicht für "
                            "zeitgebundene Termine (mit Uhrzeit). Bei "
                            "Mehrtages-Termine das End-Datum. Sonst leer."),
                    },
                    "ganztags": {
                        "type": "boolean",
                        "description": "True wenn ganztägig, False wenn zeitgebunden.",
                    },
                    "personen_hinweise": {
                        "type": "string",
                        "description": (
                            "Optionale Personen-Hinweise aus dem Plan "
                            "(z. B. 'Klasse 3b', 'für Mila'). Nie Pflicht."),
                    },
                },
                "required": ["titel", "beginn"],
            },
        },
    },
    "required": ["termine"],
}

# TAB-5 Z. 190-201: Caption ist Steuer-Kontext (Jahres-Override, Filter),
# kein Erfinden-Auftrag — E-TAB-5-Disziplin.
_SYSTEM_PROMPT = (
    "Du bist ein präziser Termin-Extraktor. Aus einem Foto eines Plans "
    "(Schulplan, Kursplan, Vereins-Saisonübersicht) liest du ALLE Termine "
    "und gibst sie ausschließlich über das `extract_termine`-Tool zurück. "
    "Erfinde keine Termine — wenn etwas unklar ist, lass das Feld leer "
    "(der Aufrufer fragt nach). "
    "Beachte den Begleittext der Nachricht als Verfeinerungs-Hinweis "
    "(z. B. 'Jahr 2026 verwenden', 'nur die Geburtstage'): wende ihn auf "
    "die im Bild enthaltenen Termine an. Fehlt eine Information im Bild "
    "(z. B. Jahreszahl), ist der Begleittext die zulässige Quelle, die "
    "Lücke zu schließen — er erfindet aber keine Termine.")


class FotoAnalyseProvider:
    """Foto-Adapter über `tools.llm` (#1262) — erfüllt den MultimodalProvider-
    Duck-Type `extract_termine(...)` (base.py:70).

    Die Lib-Singleshot-Fassade wird EINMAL im `__init__` gebaut (Slot + Modell +
    max_tokens), pro Aufruf wiederverwendet — kein Zugangsdaten-Read pro Foto
    (Spiegel `providers/lib_adapter.py:84`). Ein `LLMCapabilityError` hier ist
    ein Boot-Konfig-Fehler (fehlender Key im Foto-Slot, Capability-Mismatch) und
    propagiert klar — er wird NICHT als `MultimodalError` verschluckt (dieselbe
    Boot-vs-Laufzeit-Trennung wie lib_adapter). Erst der eigentliche Anbieter-
    Fehler zur Laufzeit (`tools.llm.ProviderError`) wird in `MultimodalError`
    übersetzt, das der TAB-Skill zu `provider_fehler` verarbeitet (TAB-5).
    """

    def __init__(self, model: str = ""):
        # Effektives Modell: config-Override (multimodal_model), sonst der
        # multimodal-fähige Foto-Default (Verhalten des Alt-Adapters erhalten).
        self._model = (model or "").strip() or _FOTO_MODEL
        # LLMCapabilityError propagiert (Boot-Fehler) — kein MultimodalError-Wrap.
        self._singleshot = get_singleshot(
            FOTO_ANALYSE_SLOT, self._model, max_tokens=_MAX_TOKENS)
        # Für Diagnose/Tests sichtbar (gleiche Modell-Quelle wie die Fassade).
        self.model = getattr(self._singleshot, "model", "") or self._model

    def extract_termine(self, *, image_bytes, image_media_type, caption):
        """TAB-5: ein multimodaler Singleshot mit `image`-Block + hart-codiertem
        forced `extract_termine`-Tool. Liefert eine Liste `ExtractedTermin`.

        Signatur identisch zum Legacy-Adapter (Duck-Type gewahrt): der TAB-Skill
        (`termine_aus_bild.py`) ruft dieselbe Form, unverändert.
        """
        if not image_bytes:
            raise MultimodalError("kein Bild übergeben")

        # Prompt-Text 1:1 wie Legacy `_multimodal/claude.py:198-200`.
        prompt = (
            "Begleittext der Familie: %s\n\n"
            "Bitte extrahiere ALLE Termine aus dem Bild." % (caption or ""))
        # Neutrale Wire-Form: Rohbytes + media_type (base64 macht der Vendor).
        images = [{
            "bytes": image_bytes,
            "media_type": image_media_type or "image/jpeg",
        }]

        try:
            result = self._singleshot.complete_structured(
                system=_SYSTEM_PROMPT,
                prompt=prompt,
                schema=_TOOL_SCHEMA,
                tool_name=_TOOL_NAME,
                tool_description=_TOOL_DESCRIPTION,
                images=images,
            )
        except LibProviderError as e:
            # TAB-5 / EC-14-analog: Anbieter nicht erreichbar / fehlerhaft →
            # MultimodalError, das der Skill zu `provider_fehler` verarbeitet.
            logger.warning("TAB-5 Foto-Analyse (Lib) fehlgeschlagen: %s", e)
            raise MultimodalError(str(e)) from e

        # Die Singleshot-Sicht liefert das GANZE tool-input-dict `{termine: […]}`
        # → `.get("termine")` auspacken (E-TAB-8).
        raw_items = result.get("termine")
        if not isinstance(raw_items, list):
            raise MultimodalError("Tool-Use-Antwort ohne `termine`-Liste")

        # Rohe Items in kanonische ExtractedTermin-Objekte heben — robust gegen
        # lockere LLM-Antworten (Spiegel Legacy `_multimodal/claude.py:156-167`).
        out = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            out.append(ExtractedTermin(
                titel=str(item.get("titel") or "").strip(),
                beginn=str(item.get("beginn") or "").strip(),
                ende=str(item.get("ende") or "").strip(),
                ganztags=item.get("ganztags"),
                personen_hinweise=str(item.get("personen_hinweise") or "").strip(),
            ))
        return out


# Öffentlich für Tests/Skill (TAB-5 Schnittstellen-Stabilität + Caption-Steuerung).
TOOL_NAME = _TOOL_NAME
TOOL_DESCRIPTION = _TOOL_DESCRIPTION
TOOL_SCHEMA = _TOOL_SCHEMA
SYSTEM_PROMPT = _SYSTEM_PROMPT

# Öffentliche Typen: kanonische Definitionen für den Foto-Pfad (#1262, #1334) +
# Boot-Konfig-Fehler-Typ (analog lib_adapter). `ExtractedTermin`/
# `MultimodalError` sind physisch hier definiert (keine Re-Export-Ebene mehr).
__all__ = [
    "FOTO_ANALYSE_SLOT",
    "SYSTEM_PROMPT",
    "TOOL_DESCRIPTION",
    "TOOL_NAME",
    "TOOL_SCHEMA",
    "ExtractedTermin",
    "FotoAnalyseProvider",
    "LLMCapabilityError",
    "MultimodalError",
]
