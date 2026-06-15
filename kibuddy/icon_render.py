"""KIBuddy — Wort-für-Wort-Tokenisierung mit Wortklassen-Filter (KIBUDDY-17).

Tokenisierung, Normalisierung und Wortklassen-Filter.
Funktionswörter werden als is_inhaltswort=false markiert.
Inhaltswörter (Nomen, Vollverben, Adjektive) erhalten is_inhaltswort=true.

Icon-Lookup läuft clientseitig im Browser (KIBUDDY-17 letzer Absatz):
Der Server liefert nur {text, is_inhaltswort}; die View-JS ruft
/api/v1/icons/suche parallel per fetch() auf — kein serverseitiger
ICONS-7-Call mehr.

V1: kein Lemma (KIBUDDY-18, OPEN-KIBUDDY-I). Reiner Substring-Match.
Funktionswort-Liste: $KIBUDDY_DATA_ROOT/funktionswort-liste.txt (KIBUDDY-17.3,
KIBUDDY-21). Fallback: kibuddy/data/funktionswort-liste.default.txt (Code-seitig
mitgeliefert). Cached beim ersten Aufruf, kein Reload pro Request.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent

# Modul-Level-Cache für die Stop-Words (einmalig pro Service-Boot).
_stop_words_cache: frozenset[str] | None = None


def load_stop_words(data_root: Path | str | None = None) -> frozenset[str]:
    """Lädt die Funktionswort-Liste aus data_root oder Default-Datei (KIBUDDY-17.3).

    Reihenfolge:
      1. data_root/funktionswort-liste.txt
      2. kibuddy/data/funktionswort-liste.default.txt (Code-seitig mitgeliefert)

    Ergebnis wird im Modul-Level-Cache gehalten (kein Reload pro Request).
    """
    global _stop_words_cache
    if _stop_words_cache is not None:
        return _stop_words_cache

    words: frozenset[str] | None = None

    # Versuch 1: Override-Datei in data_root.
    if data_root is not None:
        override = Path(data_root) / "funktionswort-liste.txt"
        try:
            text = override.read_text(encoding="utf-8")
            parsed = frozenset(w.strip().lower() for w in text.splitlines() if w.strip())
            if parsed:
                words = parsed
                logger.info("funktionswort-liste: %d Wörter aus %s", len(parsed), override)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("funktionswort-liste: Lese-Fehler %s: %s", override, e)

    # Versuch 2: Default-Datei aus dem Modul-Verzeichnis.
    if words is None:
        default = _HERE / "data" / "funktionswort-liste.default.txt"
        try:
            text = default.read_text(encoding="utf-8")
            parsed = frozenset(w.strip().lower() for w in text.splitlines() if w.strip())
            if parsed:
                words = parsed
                logger.info("funktionswort-liste: %d Wörter aus Default-Datei", len(parsed))
        except OSError as e:
            logger.warning("funktionswort-liste: Default-Datei nicht lesbar (%s): %s", default, e)

    if words is None:
        logger.warning("funktionswort-liste: leer — alle Wörter werden als Inhaltswort behandelt")
        words = frozenset()

    _stop_words_cache = words
    return _stop_words_cache


def _reset_stop_words_cache() -> None:
    """Setzt den Cache zurück — nur für Tests."""
    global _stop_words_cache
    _stop_words_cache = None


# Rückwärtskompatibles Symbol für Tests, die STOP_WORDS_DE direkt importieren.
# Wird beim ersten Zugriff aus der Default-Datei befüllt.
class _LazyStopWords:
    """Lazy-Proxy für STOP_WORDS_DE — kompatibel mit `in`-Operator und `len()`."""

    def __contains__(self, item: str) -> bool:
        return item in load_stop_words()

    def __len__(self) -> int:
        return len(load_stop_words())

    def __iter__(self):
        return iter(load_stop_words())


STOP_WORDS_DE: _LazyStopWords = _LazyStopWords()


def tokenisiere(text: str) -> list[dict]:
    """Tokenisiert text in Wort-Token-Liste (KIBUDDY-17 Schritte 1–6a).

    Gibt eine Liste von Dicts zurück:
      {"token": str, "typ": "inhaltswort"|"funktionswort"|"satzzeichen"}
    """
    if not text:
        return []

    stop_words = load_stop_words()
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
            if normalisiert in stop_words:
                tokens.append({"token": wort_teil, "typ": "funktionswort"})
            else:
                tokens.append({"token": wort_teil, "typ": "inhaltswort", "normalisiert": normalisiert})
        if sz_teil:
            tokens.append({"token": sz_teil, "typ": "satzzeichen"})
    return tokens


def worte_zu_words_api(text: str) -> list[dict]:
    """Tokenisiert text und gibt die API-words-Liste zurück (KIBUDDY-17, KIBUDDY-24).

    Response-Format: [{"text": str, "is_inhaltswort": bool}].
    Satzzeichen werden mitgeliefert (is_inhaltswort=false).
    Icon-Lookup findet clientseitig statt (KIBUDDY-17 letzter Absatz).
    """
    tokens = tokenisiere(text)
    result = []
    for tok in tokens:
        is_inhaltswort = tok["typ"] == "inhaltswort"
        result.append({"text": tok["token"], "is_inhaltswort": is_inhaltswort})
    return result
