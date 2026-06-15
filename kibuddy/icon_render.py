"""KIBuddy — Wort-für-Wort-Render mit Wortklassen-Filter (KIBUDDY-17).

Tokenisierung, Normalisierung und Wortklassen-Filter für Icon-Lookup.
Funktionswörter werden als reine Text-Token gerendert (kein Icon-Lookup).
Inhaltswörter (Nomen, Vollverben, Adjektive) gehen in den Icon-Lookup
(ICONS-7: GET /api/v1/icons/suche?q=<wort>&max=1).

V1: kein Lemma (KIBUDDY-18, OPEN-KIBUDDY-I). Reiner Substring-Match.
"""

import logging
import re
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# ~150 deutsche Funktionswörter (KIBUDDY-17, Nic-Setzung).
# Artikel, Pronomen, Präpositionen, Konjunktionen, Hilfs-/Modalverben,
# Adverbien, Partikeln — alles, was kein Nomen, kein Vollverb, kein Adjektiv ist.
# Wenn unsicher: raus aus der Liste (Lookup-Versuch ist robuster).
STOP_WORDS_DE: frozenset[str] = frozenset({
    # Bestimmte Artikel
    "der", "die", "das", "des", "dem", "den",
    # Unbestimmte Artikel
    "ein", "eine", "einer", "einem", "einen", "eines",
    # Negationsartikel
    "kein", "keine", "keinen", "keinem", "keiner", "keines",
    # Personalpronomen
    "ich", "du", "er", "sie", "es", "wir", "ihr",
    "mich", "dich", "ihn", "uns", "euch",
    "mir", "dir", "ihm", "ihnen",
    "mein", "dein", "sein", "unser", "euer", "meiner", "deiner", "seiner", "unserer", "eurer",
    "meinem", "deinem", "seinem", "unserem", "eurem",
    "meinen", "deinen", "seinen", "unseren", "euren",
    "meines", "deines", "seines", "unseres", "eures",
    "meine", "deine", "seine", "unsere", "eure", "ihre",
    # Reflexivpronomen
    "sich", "selbst",
    # Demonstrativpronomen
    "dieser", "diese", "dieses", "diesem", "diesen",
    "jener", "jene", "jenes", "jenem", "jenen",
    "derselbe", "dieselbe", "dasselbe",
    # Relativpronomen
    "welcher", "welche", "welches", "welchem", "welchen",
    # Interrogativpronomen
    "wer", "wen", "wem", "wessen", "was", "welcher",
    # Indefinitpronomen
    "man", "jemand", "niemand", "jeder", "jede", "jedes",
    "alle", "alles", "etwas", "nichts", "irgendwas",
    "viel", "wenig", "mehr", "weniger",
    # Hilfsverben
    "haben", "hat", "hatte", "habe", "habt", "hatten",
    "ist", "war", "bin", "bist", "sind", "seid", "waren",
    "werden", "wird", "wurde", "werde", "werdet", "wurden",
    # Modalverben
    "können", "kann", "konnte", "könnte",
    "müssen", "muss", "musste", "müsste",
    "wollen", "will", "wollte",
    "sollen", "soll", "sollte",
    "dürfen", "darf", "durfte", "dürfte",
    "mögen", "mag", "mochte", "möchte",
    # Präpositionen
    "in", "an", "auf", "unter", "über", "vor", "hinter",
    "neben", "zwischen", "durch", "für", "gegen", "ohne",
    "um", "bis", "seit", "von", "zu", "bei", "mit",
    "nach", "aus", "ab", "während", "trotz", "wegen",
    "innerhalb", "außerhalb", "entlang", "gegenüber",
    # Konjunktionen
    "und", "oder", "aber", "doch", "sondern", "denn",
    "weil", "da", "obwohl", "obgleich", "obschon",
    "wenn", "falls", "sofern", "solange",
    "dass", "ob", "als", "wie",
    "damit", "sodass", "so", "indem", "wobei",
    "bevor", "nachdem", "seitdem", "entweder", "weder", "sowohl", "zwar",
    # Adverbien (häufige)
    "hier", "dort", "wo", "wohin", "woher",
    "jetzt", "nun", "dann", "danach", "vorher", "bald", "noch", "schon",
    "immer", "nie", "manchmal", "oft", "selten",
    "sehr", "ganz", "ziemlich", "fast", "kaum",
    "nicht", "nein",
    "auch", "sogar", "nur", "bloß", "bereits", "wieder", "dabei", "daran", "dafür",
    "deshalb", "deswegen", "daher", "darum",
    "trotzdem", "dennoch", "jedoch", "allerdings",
    "außerdem", "zudem", "übrigens", "nämlich",
    # Partikeln
    "ja", "mal", "eben", "halt", "wohl",
    "eigentlich", "einfach", "irgendwie", "vielleicht",
    # Sonstiges
    "bzw", "usw", "etc", "d", "h",
})


def tokenisiere(text: str) -> list[dict]:
    """Tokenisiert text in Wort-Token-Liste (KIBUDDY-17 Schritte 1–6a).

    Gibt eine Liste von Dicts zurück:
      {"token": str, "typ": "inhaltswort"|"funktionswort"|"satzzeichen"}
    """
    if not text:
        return []

    tokens = []
    # Whitespace-Split, dann je Token Satzzeichen abtrennen.
    for raw in text.split():
        # Satzzeichen am Ende abschneiden (z. B. "Hund." → "Hund" + ".").
        m = re.match(r"^(.*?)([.,!?;:…\-–—]+)$", raw)
        if m:
            wort_teil = m.group(1)
            sz_teil = m.group(2)
        else:
            wort_teil = raw
            sz_teil = ""

        if wort_teil:
            normalisiert = wort_teil.lower().strip("\"'«»")
            if normalisiert in STOP_WORDS_DE:
                tokens.append({"token": wort_teil, "typ": "funktionswort"})
            else:
                tokens.append({"token": wort_teil, "typ": "inhaltswort", "normalisiert": normalisiert})
        if sz_teil:
            tokens.append({"token": sz_teil, "typ": "satzzeichen"})
    return tokens


def icon_lookup_single(wort: str, icons_base_url: str = "http://127.0.0.1:5000") -> str | None:
    """ICONS-7-Lookup: GET /api/v1/icons/suche?q=<wort>&max=1.

    Gibt die icon-URL zurück (z. B. "/display/_shared/icons/arasaac/2239.png")
    oder None bei Miss oder Fehler. Läuft synchron im Request-Frame (KIBUDDY-13).
    """
    q = urllib.parse.quote(wort, safe="")
    url = "%s/api/v1/icons/suche?q=%s&max=1" % (icons_base_url.rstrip("/"), q)
    try:
        with urllib.request.urlopen(url, timeout=1.0) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and data:
                return data[0].get("url")
    except Exception as e:
        logger.debug("icon-lookup fehlgeschlagen für %r: %s", wort, e)
    return None


def render_worte(
    text: str,
    icons_base_url: str = "http://127.0.0.1:5000",
    icon_lookup_fn=None,
) -> list[dict]:
    """Gibt eine Liste render-bereiter Wort-Slots zurück (KIBUDDY-17).

    Jeder Slot hat mindestens {"token": str, "typ": str}.
    Inhaltswörter tragen zusätzlich {"icon_url": str|None}.

    `icon_lookup_fn` ist die Test-Naht: `(wort) -> str|None`.
    Wenn None, wird `icon_lookup_single` mit `icons_base_url` benutzt.
    """
    if icon_lookup_fn is None:
        def icon_lookup_fn(wort):
            return icon_lookup_single(wort, icons_base_url)

    tokens = tokenisiere(text)
    result = []
    for tok in tokens:
        if tok["typ"] == "inhaltswort":
            normalisiert = tok.get("normalisiert", tok["token"].lower())
            icon_url = icon_lookup_fn(normalisiert)
            result.append({
                "token": tok["token"],
                "typ": "inhaltswort",
                "icon_url": icon_url,
            })
        else:
            result.append({"token": tok["token"], "typ": tok["typ"]})
    return result


def worte_zu_api_format(worte: list[dict]) -> list[dict]:
    """Konvertiert render-Wort-Liste in API-Response-Format (KIBUDDY-24).

    Gibt `words`-Liste: [{"text": str, "icon_id": str|null}].
    icon_id ist die numerische ARASAAC-ID aus der URL (oder null).
    """
    result = []
    for slot in worte:
        icon_id = None
        icon_url = slot.get("icon_url")
        if icon_url:
            # URL-Form: /display/_shared/icons/arasaac/<id>.png
            parts = icon_url.rstrip("/").split("/")
            if parts and parts[-1].endswith(".png"):
                icon_id = parts[-1][:-4]  # ID ohne .png
        result.append({"text": slot["token"], "icon_id": icon_id})
    return result
