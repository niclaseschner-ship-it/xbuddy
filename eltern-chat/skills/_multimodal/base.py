"""Multimodal-Provider-Protocol und Datentypen — specs/platform/termine-aus-bild.md
TAB-5 (Refs #475).

Ein `MultimodalProvider` extrahiert aus einem Bild (Foto eines Plans) eine
Liste von Termin-Vorschlägen, gerahmt durch ein hart-codiertes Tool-Schema
(TAB-5: stabil, testbar, vom Code gehalten — nicht vom Modell formuliert).

`ExtractedTermin` ist die kanonische, anbieter-neutrale Form der LLM-Antwort.
Felder spiegeln den PLAN-22-PUT-Body, soweit aus einem Bild ableitbar:
`titel`, `beginn` (ISO-Datum oder ISO-Datetime), optional `ende`, `ganztags`,
`personen_hinweise` (TAB-5/TAB-8.2).

Datenlinie (EC-13): nur das Bild + Begleittext gehen an den Anbieter — keine
weiteren Familien-Daten. Das Bild wird **nach** der Extraktion verworfen
(E-TAB-5, keine Photo-Buddy-Beleg-Linie).
"""

from dataclasses import dataclass, field


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


class MultimodalProvider:
    """Protokoll des multimodalen Anbieter-Adapters (TAB-5).

    Konkrete Adapter (V1: `ClaudeMultimodalProvider`) erfüllen `extract_termine`
    und werden über `get_multimodal_provider(name, api_key, model)` instanziiert.
    """

    def extract_termine(self, *, image_bytes, image_media_type, caption):
        """Schickt das Bild + den Begleittext an den Anbieter und liefert eine
        Liste von `ExtractedTermin`-Objekten (TAB-5).

        `image_bytes`        — Rohbytes des Bilds (Foto JPEG / PNG).
        `image_media_type`   — MIME-Typ (`image/jpeg`, `image/png`, …).
        `caption`            — Begleittext der Telegram-Nachricht (Pflicht;
                               mindestens das Signalwort, siehe TAB-4).

        Wirft `MultimodalError` bei Anbieter-Fehlern (Timeout, HTTP-Fehler,
        ungültige Tool-Use-Antwort, leere Tool-Output-Struktur). Eine
        **erfolgreich** leere Liste (Anbieter hat keine Termine erkannt) ist
        **kein** Fehler — der Skill bewertet das in TAB-6 als „leere Liste"
        → Ergebnis „unklar".
        """
        raise NotImplementedError
