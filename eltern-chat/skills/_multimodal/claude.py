"""Claude-Adapter für die multimodale Termin-Extraktion — TAB-5 (Refs #475).

Der EINZIGE Ort mit Anthropic-spezifischem JSON für den TAB-Pfad. Aufruf-Form:
ein `user`-Turn mit `[image-block, text-block]`-Content + ein hart-codiertes
`extract_termine`-Tool, das Anthropic per `tool_choice={type: "tool", name: ...}`
zur Tool-Use-Antwort zwingt. Damit landet die Termin-Liste deterministisch in
`response.content[*].input.termine` — kein Freitext-Parsing.

Datenlinie (EC-13 / E-TAB-5): nur Bild + Caption + Tool-Schema gehen raus.
Das Bild wird hier NICHT persistiert (kein Photo-Buddy-Aufruf, E-TAB-5).
"""

import base64
import logging

from skills._multimodal.base import (
    ExtractedTermin,
    MultimodalError,
    MultimodalProvider,
)

logger = logging.getLogger(__name__)


# TAB-5: hart-codiertes Tool-Schema. Die Felder spiegeln den PLAN-22-PUT-Body
# (titel/beginn/ende), soweit aus einem Bild ableitbar. Das LLM ist gezwungen,
# diese Form zu liefern — keine Freitext-Antwort, kein Modell-Formuliertes
# Schema (E-EC-4, TES-7-Vorbild).
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
                            "für zeitgebundene Termine."),
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

# TAB-5: System-Prompt der multimodalen Extraktion. Bewusst knapp — Tabelle
# UND Fließtext (TAB-6 normiert das Soll: keine reine OCR-Schicht).
_SYSTEM_PROMPT = (
    "Du bist ein präziser Termin-Extraktor. Aus einem Foto eines Plans "
    "(Schulplan, Kursplan, Vereins-Saisonübersicht) liest du ALLE Termine "
    "und gibst sie ausschließlich über das `extract_termine`-Tool zurück. "
    "Erfinde keine Termine — wenn etwas unklar ist, lass das Feld leer "
    "(der Aufrufer fragt nach).")


class ClaudeMultimodalProvider(MultimodalProvider):
    """Anthropic-Adapter für TAB-5 (multimodale Termin-Extraktion).

    `transport` ist die Test-Naht: ein Callable `(image_bytes, image_media_type,
    caption) -> list[dict]`, das den Anthropic-Aufruf ersetzt. Bleibt der Wert
    None, ruft der Adapter `anthropic.Anthropic.messages.create` mit erzwungener
    Tool-Use.
    """

    # TAB-5 / E-TAB-6: leerer Modell-Default → Fallback auf den Konversations-
    # Adapter-Default (claude-opus-4-7), der multimodal-fähig ist. V1 nimmt
    # die SELBE Modell-ID wie der Text-Pfad (cfg.provider_model), kein
    # zweiter Konfig-Slot (CLAUDE.md §6 „Lege nichts auf Vorrat an").
    _FALLBACK_MODEL = "claude-opus-4-7"
    MAX_TOKENS = 4096

    def __init__(self, api_key, model="", transport=None):
        self._api_key = api_key
        self._model = model or self._FALLBACK_MODEL
        self._transport = transport
        # Lazy-Client-Bau: nur wenn es kein transport-Doppel gibt, brauchen
        # wir den anthropic-Client.
        self._client = None

    def extract_termine(self, *, image_bytes, image_media_type, caption):
        """TAB-5: ein multimodaler Aufruf mit `image`-Content-Block und
        hart-codiertem Tool-Schema. Liefert eine Liste `ExtractedTermin`."""
        if not image_bytes:
            raise MultimodalError("kein Bild übergeben")

        if self._transport is not None:
            try:
                raw_items = self._transport(
                    image_bytes=image_bytes,
                    image_media_type=image_media_type,
                    caption=caption or "")
            except MultimodalError:
                raise
            except Exception as e:  # Transport-Fehler vereinheitlichen
                raise MultimodalError("transport-Fehler: %s" % e) from e
        else:
            raw_items = self._call_anthropic(
                image_bytes, image_media_type, caption or "")

        if not isinstance(raw_items, list):
            raise MultimodalError(
                "Anbieter-Antwort ist keine Liste (%r)" % type(raw_items).__name__)

        # Anbieter-Items in kanonische ExtractedTermin-Objekte heben — robust
        # gegen lockere LLM-Antworten (string trim, fehlende Optional-Felder).
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

    # -- Anthropic-Aufruf -------------------------------------------------

    def _call_anthropic(self, image_bytes, image_media_type, caption):
        """Ruft die Anthropic-Messages-API mit Tool-Use-Zwang auf und liefert
        `response.content[*].input["termine"]` als rohe Liste-of-Dicts.

        Tool-Choice ist hart auf das `extract_termine`-Tool gesetzt — Anthropic
        liefert dann garantiert einen `tool_use`-Block, nicht Freitext.
        """
        # Lazy-Import + Lazy-Bau: das anthropic-SDK liegt nur im Laufzeit-Pfad,
        # nicht in jeder Test-Suite.
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)

        import anthropic

        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type or "image/jpeg",
                    "data": image_b64,
                },
            },
            {
                "type": "text",
                "text": (
                    "Begleittext der Familie: %s\n\n"
                    "Bitte extrahiere ALLE Termine aus dem Bild." % caption),
            },
        ]
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self.MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                tools=[{
                    "name": _TOOL_NAME,
                    "description": _TOOL_DESCRIPTION,
                    "input_schema": _TOOL_SCHEMA,
                }],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": user_content}],
            )
        except anthropic.APIError as e:
            logger.warning("TAB-5 Claude-Aufruf fehlgeschlagen: %s", e)
            raise MultimodalError(str(e)) from e

        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", "") == "tool_use" \
                    and getattr(block, "name", "") == _TOOL_NAME:
                payload = getattr(block, "input", None)
                if not isinstance(payload, dict):
                    raise MultimodalError(
                        "Tool-Use-Antwort hat keine input-dict")
                termine = payload.get("termine")
                if not isinstance(termine, list):
                    raise MultimodalError(
                        "Tool-Use-Antwort ohne `termine`-Liste")
                return termine
        raise MultimodalError(
            "Antwort enthält keinen erwarteten `tool_use`-Block")


# Öffentlich für Tests/Skill: das Tool-Schema und die Tool-Beschreibung
# (TAB-5-Test prüft, dass die Schnittstelle stabil ist).
TOOL_NAME = _TOOL_NAME
TOOL_DESCRIPTION = _TOOL_DESCRIPTION
TOOL_SCHEMA = _TOOL_SCHEMA
