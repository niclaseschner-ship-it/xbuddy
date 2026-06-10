"""Mistral-Adapter für die multimodale Termin-Extraktion — E-TAB-6 V2 (Refs #508).

Der EINZIGE Ort mit Mistral-spezifischem JSON für den TAB-Pfad. Aufruf-Form:
ein `user`-Turn mit `[image_url-block, text-block]`-Content + ein hart-codiertes
`extract_termine`-Tool, das Mistral per `tool_choice={type: "function", ...}`
zur Tool-Use-Antwort zwingt. Damit landet die Termin-Liste deterministisch in
`response.choices[0].message.tool_calls[0].function.arguments` — kein Freitext-
Parsing.

Pixtral-Ausschluss (E-TAB-6 Z.878-884): Pixtral-Modelle werden NICHT verwendet.
Mistral Medium 3.5 (`mistral-medium-3504`) ist KEINE Pixtral-Familie.

Datenlinie (EC-13 / E-TAB-5): nur Bild + Caption + Tool-Schema gehen raus.
Das Bild wird hier NICHT persistiert (kein Photo-Buddy-Aufruf, E-TAB-5).
"""

import base64
import json
import logging

import httpx

from skills._multimodal.base import (
    ExtractedTermin,
    MultimodalError,
    MultimodalProvider,
)

logger = logging.getLogger(__name__)

_MISTRAL_API_BASE = "https://api.mistral.ai/v1"
_CHAT_ENDPOINT = _MISTRAL_API_BASE + "/chat/completions"

# TAB-5: hart-codiertes Tool-Schema. Identisch mit claude.py — die Felder
# spiegeln den PLAN-22-PUT-Body (titel/beginn/ende). Das LLM ist gezwungen,
# diese Form zu liefern (E-EC-4, TES-7-Vorbild).
_TOOL_NAME = "extract_termine"
_TOOL_DESCRIPTION = (
    "Extrahiere ALLE im Bild sichtbaren Termine (Schulplan, Kursplan, "
    "Saison-Übersicht). Sowohl tabellarische Pläne als auch Fließtext-"
    "Notizen sind zu petrarbeiten. Liefere die Termine in der Reihenfolge, "
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

# TAB-5: System-Prompt der multimodalen Extraktion. Identisch mit claude.py.
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


class MistralMultimodalProvider(MultimodalProvider):
    """Mistral-Adapter für E-TAB-6 V2 (multimodale Termin-Extraktion).

    `transport` ist die Test-Naht: ein Callable `(image_bytes, image_media_type,
    caption) -> list[dict]`, das den Mistral-API-Aufruf ersetzt. Bleibt der Wert
    None, ruft der Adapter die Mistral-Chat-Completions-API mit erzwungener
    Tool-Use auf.
    """

    # E-TAB-6 V2: Mistral Medium 3.5 ist der dedizierte Multimodal-Slot.
    _FALLBACK_MODEL = "mistral-medium-3504"
    MAX_TOKENS = 4096

    def __init__(self, api_key, model="", transport=None):
        self._api_key = api_key
        self._model = model or self._FALLBACK_MODEL
        self._transport = transport

    def extract_termine(self, *, image_bytes, image_media_type, caption):
        """E-TAB-6: ein multimodaler Aufruf mit `image_url`-Content-Block und
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
            except Exception as e:
                raise MultimodalError("transport-Fehler: %s" % e) from e
        else:
            raw_items = self._call_mistral(
                image_bytes, image_media_type, caption or "")

        if not isinstance(raw_items, list):
            raise MultimodalError(
                "Anbieter-Antwort ist keine Liste (%r)" % type(raw_items).__name__)

        # Anbieter-Items in kanonische ExtractedTermin-Objekte heben.
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

    # -- Mistral-Aufruf ---------------------------------------------------

    def _call_mistral(self, image_bytes, image_media_type, caption):
        """Ruft die Mistral-Chat-Completions-API mit Tool-Use-Zwang auf und
        liefert `tool_calls[0].function.arguments["termine"]` als rohe
        Liste-of-Dicts.

        Tool-Choice ist hart auf das `extract_termine`-Tool gesetzt — Mistral
        liefert dann einen Tool-Call-Block, nicht Freitext.
        """
        image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        media_type = image_media_type or "image/jpeg"
        data_url = "data:%s;base64,%s" % (media_type, image_b64)

        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": data_url},
            },
            {
                "type": "text",
                "text": (
                    "Begleittext der Familie: %s\n\n"
                    "Bitte extrahiere ALLE Termine aus dem Bild." % caption),
            },
        ]

        payload = {
            "model": self._model,
            "max_tokens": self.MAX_TOKENS,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "tools": [{
                "type": "function",
                "function": {
                    "name": _TOOL_NAME,
                    "description": _TOOL_DESCRIPTION,
                    "parameters": _TOOL_SCHEMA,
                },
            }],
            # Mistral: erzwingt den Aufruf des angegebenen Tools.
            "tool_choice": {
                "type": "function",
                "function": {"name": _TOOL_NAME},
            },
        }

        try:
            response = httpx.post(
                _CHAT_ENDPOINT,
                headers={
                    "Authorization": "Bearer %s" % self._api_key,
                    "Content-Type": "application/json",
                },
                content=json.dumps(payload),
                timeout=120.0,
            )
        except httpx.RequestError as e:
            logger.warning("E-TAB-6 Mistral-Aufruf fehlgeschlagen: %s", e)
            raise MultimodalError("Netzwerkfehler: %s" % e) from e

        if response.status_code != 200:
            logger.warning("E-TAB-6 Mistral-Aufruf HTTP-Fehler: %s %s",
                           response.status_code, response.text)
            raise MultimodalError(
                "HTTP %d: %s" % (response.status_code, response.text))

        data = response.json()
        choices = data.get("choices") or []
        for choice in choices:
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function") or {}
                if fn.get("name") == _TOOL_NAME:
                    raw_args = fn.get("arguments") or "{}"
                    try:
                        payload_parsed = json.loads(raw_args)
                    except (json.JSONDecodeError, TypeError) as e:
                        raise MultimodalError(
                            "Tool-Use-Antwort hat kein valides JSON: %s" % e) from e
                    if not isinstance(payload_parsed, dict):
                        raise MultimodalError(
                            "Tool-Use-Antwort hat keine input-dict")
                    termine = payload_parsed.get("termine")
                    if not isinstance(termine, list):
                        raise MultimodalError(
                            "Tool-Use-Antwort ohne `termine`-Liste")
                    return termine
        raise MultimodalError(
            "Antwort enthält keinen erwarteten `tool_use`-Block")


# Öffentlich für Tests/Skill: Tool-Schema, Beschreibung und System-Prompt
# (TAB-5-Tests prüfen Schnittstellen-Stabilität und Caption-Steuerung).
TOOL_NAME = _TOOL_NAME
TOOL_DESCRIPTION = _TOOL_DESCRIPTION
TOOL_SCHEMA = _TOOL_SCHEMA
SYSTEM_PROMPT = _SYSTEM_PROMPT
