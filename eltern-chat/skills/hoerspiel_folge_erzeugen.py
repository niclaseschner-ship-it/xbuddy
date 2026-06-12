"""Hörspiel-Folge erzeugen — specs/platform/hoerspiel-folge-erzeugen.md
(HFE-1 … HFE-9, E-HFE-1 … E-HFE-5).

Aufrufbare, trigger-agnostische Funktion (HFE-1, E-HFE-1): nimmt eine
Folgen-Idee entgegen, holt vom Hörspiel-Buddy einen Folgen-Vorschlag
(POST /api/v1/hoerspiel/folgen-vorschlag) und löst den Album-Bau aus
(POST /api/v1/hoerspiel/alben). Der LLM-Aufruf lebt im Hörspiel-Buddy
— dieser Skill ist ein dünner Konsument (E-HFE-2).

Pattern (E-HFE-5 / E-HFE-3): **propose → confirm**, NICHT Sofort-Wirkung.
Ein Album-Bau kostet 1–5 min TTS-Zeit; die Voice-Wahl verlangt einen
vorab sichtbaren Vorschlag. EC-10-Gate sitzt eine Ebene höher im Task.

Berechtigung (HFE-2): nur Familien-Mitglieder (is_member_fn). Im
Agent-Loop wirft die Funktion `BerechtigungError` — kein Buddy-Aufruf.

Eingang propose(): hoerspiel_client, is_member_fn, from_user_id, idee,
  voice_hint (aus dem Aufrufer-Text, optional).
Eingang execute(): hoerspiel_client, tg, chat_id, display_url_origin,
  titel, text, voice, idee.

Ausgang propose(): strukturierter Tool-Result-Text (HFE-4) bei Erfolg,
  oder EC-22-Rückfrage-Text, oder HoerspielClientError bei Fehler.
Ausgang execute(): sendet Erfolgs- oder Fehler-Bubble über tg (HFE-5).
"""

import logging

from skills._errors import BerechtigungError
from skills.hoerspiel_client import HoerspielClientError

logger = logging.getLogger(__name__)

# HFE-4: erlaubte Voice-Werte (shimmer/onyx, HSP-23).
VOICE_SHIMMER = "shimmer"
VOICE_ONYX    = "onyx"
VOICE_DEFAULT = VOICE_SHIMMER   # HSP-26-Default, Fallback wenn config nicht erreichbar

# HFE-3: Phrases, die als "leere/mehrdeutige Idee" gelten (EC-22).
# Statt hart-gecodete Prüfung nutzt propose() eine Längen-/Inhalt-Prüfung.
_IDEE_MIN_ZEICHEN = 5


def propose(*, hoerspiel_client, is_member_fn, from_user_id,
            idee: str, voice_hint: str | None = None,
            tg=None, chat_id=None) -> str:
    """Folgen-Vorschlag holen und als strukturierten Text zurückgeben (HFE-3/4).

    Trigger-agnostisch (E-HFE-1): wer diese Funktion aufruft, ist nicht
    Teil ihres Vertrags. Im Agent-Loop ruft HoerspielFolgeErzeugenTask.propose()
    sie auf (HFE-1).

    `hoerspiel_client` — HoerspielClient-Instanz (hoerspiel_client.py).
    `is_member_fn`     — Callable `(user_id) -> bool` (HFE-2).
    `from_user_id`     — Telegram-User-ID des Aufrufers (HFE-2).
    `idee`             — Folgen-Idee aus dem Aufrufer-Text (HFE-3).
    `voice_hint`       — optionale Voice aus dem Aufrufer-Text (HFE-4).

    Rückgabe: strukturierter Tool-Result-Text (Titel + Vorschau + Voice +
    Bestätigungs-Frage) bei Erfolg.

    Wirft:
      BerechtigungError — Aufrufer nicht berechtigt (HFE-2).
      ValueError        — leere/mehrdeutige Idee; Nachricht ist EC-22-Rückfrage.
      HoerspielClientError(status=503)  — LLM-Provider nicht eingerichtet.
      HoerspielClientError(status!=503) — Buddy nicht erreichbar.

    HFE-7: keine tg.send_*-Aufrufe in dieser Funktion.
    """
    # HFE-2: Berechtigung prüfen — kein Buddy-Aufruf bei Nicht-Mitglied.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "hoerspiel_folge_erzeugen.propose: User %s nicht berechtigt (HFE-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    # EC-22: leere oder mehrdeutige Idee → Rückfrage, kein Buddy-Aufruf.
    idee_bereinigt = (idee or "").strip()
    if len(idee_bereinigt) < _IDEE_MIN_ZEICHEN:
        logger.info(
            "hoerspiel_folge_erzeugen.propose: Idee zu kurz/leer — EC-22")
        raise ValueError(
            "Worum soll die Folge gehen? Beschreib die Idee kurz "
            "(ein Satz reicht), dann erstelle ich einen Vorschlag.")

    # HFE-4: Voice auflösen.
    voice = _voice_aus_hint(voice_hint)
    if voice is None:
        # Kein Voice-Hinweis → Default aus config lesen (HFE-4).
        voice = _voice_default_lesen(hoerspiel_client)

    # HFE-3: Folgen-Vorschlag vom Hörspiel-Buddy holen.
    # Fehler werden als HoerspielClientError weitergegeben — der Task entscheidet.
    logger.info("hoerspiel_folge_erzeugen.propose: rufe POST %s (HFE-3)",
                "/api/v1/hoerspiel/folgen-vorschlag")
    data = hoerspiel_client.folgen_vorschlag(idee_bereinigt)

    titel   = data.get("titel", "")
    text    = data.get("text", "")
    folge_nr = data.get("folgen-nr-vorschlag", "?")

    # HFE-4: strukturierter Tool-Result-Text (Reihenfolge: Titel, Vorschau,
    # Bestätigungs-Block). Intro/Outro-Reime sind geteilte Serien-Assets
    # (HSP-8) und gehören NICHT in die Vorschau.
    #
    # Telegram-Limit ist 4096 Zeichen/Nachricht — eine vollständige Folge
    # liegt bei ~25 000 Zeichen. Lange Folgen werden in mehrere Direkt-
    # Nachrichten gesplittet (Eltern-Kuratierung, Nic-Entscheid 2026-06-12),
    # der Tool-Result-Text dient dann nur dem Confirm-Block.
    splits = _splitte_vorschau(text)
    if tg is not None and chat_id is not None and len(splits) > 1:
        for i, teil in enumerate(splits, start=1):
            header = "**Folge %s: %s** (%d/%d)\n\n" % (
                folge_nr, titel, i, len(splits)) if i == 1 else \
                "**Folge %s** (%d/%d)\n\n" % (folge_nr, i, len(splits))
            _sende(tg, chat_id, header + teil)
        result = (
            "Vollständiger Vorschlag oben in %d Nachrichten.\n\n"
            "Voice: %s (oder schreib »shimmer« / »onyx«)\n"
            "Soll ich vertonen? Das dauert 1–5 Minuten."
        ) % (len(splits), voice)
    else:
        # Kurze Folge (≤ 1 Split) oder kein tg verfügbar: alles in den
        # Tool-Result-Block, das LLM postet eine Bot-Nachricht.
        result = (
            "**Folge %s: %s**\n\n"
            "%s\n\n"
            "Voice: %s (oder schreib »shimmer« / »onyx«)\n"
            "Soll ich vertonen? Das dauert 1–5 Minuten."
        ) % (folge_nr, titel, splits[0] if splits else text, voice)

    logger.info(
        "hoerspiel_folge_erzeugen.propose: Vorschlag bereit "
        "(folge_nr=%s, voice=%s)", folge_nr, voice)
    return result


def execute(*, hoerspiel_client, tg, chat_id,
            display_url_origin: str,
            titel: str, text: str, voice: str, idee: str) -> None:
    """Album-Bau auslösen und Erfolgs-/Fehler-Bubble senden (HFE-5).

    Trigger-agnostisch (E-HFE-1). Im Agent-Loop ruft HoerspielFolgeErzeugenTask
    .execute() diese Funktion auf — nach EC-10-Bestätigung.

    `hoerspiel_client`  — HoerspielClient-Instanz.
    `tg`                — Telegram-Client (hat send_message).
    `chat_id`           — Ziel-Chat für die Erfolgs-/Fehler-Bubble.
    `display_url_origin`— Basis-Origin der Display-View (EC-15 / GAA-3.7).
    `titel`/`text`/`voice`/`idee` — aus dem bestätigten Vorschlag.

    Sendet bei Erfolg: ✅ Folge <nr> ist in der App. + Album-URL.
    Sendet bei Fehler: kontextabhängige Fehlermeldung (HFE-5).

    TASK-10: execute() ist außerhalb des Agent-Loops und darf selbst senden.
    """
    logger.info(
        "hoerspiel_folge_erzeugen.execute: POST /alben titel=%r voice=%s",
        titel, voice)
    # HFE-5: Start-Bubble vor dem langen Album-Bau-Aufruf — Eltern wissen,
    # dass im Hintergrund gearbeitet wird, und können in der Zwischenzeit
    # andere Fragen stellen (V1: andere Skill-Turns laufen unabhängig).
    _sende(tg, chat_id,
           "Alles klar — ich schreibe und vertone die Folge gerade. "
           "Das dauert etwa 1–3 Minuten. Bis dahin melde ich mich kurz.\n"
           "(Andere Fragen kannst du in der Zwischenzeit weiter stellen.)")
    try:
        data = hoerspiel_client.album_bauen(
            titel=titel, text=text, voice=voice, idee=idee)
    except HoerspielClientError as exc:
        bubble = _fehler_bubble_album(exc, voice)
        logger.warning(
            "hoerspiel_folge_erzeugen.execute: Album-Bau fehlgeschlagen "
            "(HTTP %s) — %s", exc.status, exc)
        _sende(tg, chat_id, bubble)
        return

    nr = data.get("album-id", "?")
    origin = (display_url_origin or "").rstrip("/")
    url = "%s/display/hoerspiel/alben" % origin if origin else "/display/hoerspiel/alben"
    bubble = "✅ Folge %s ist in der App.\n%s" % (nr, url)
    logger.info(
        "hoerspiel_folge_erzeugen.execute: Album gebaut album-id=%s", nr)
    _sende(tg, chat_id, bubble)


# ============================================================
#  Helpers
# ============================================================

def _voice_aus_hint(hint: str | None) -> str | None:
    """HFE-4: extrahiert shimmer/onyx aus einem optionalen Hinweis-Text.

    Gibt None zurück, wenn kein gültiger Voice-Hint vorhanden ist.
    """
    if not hint:
        return None
    h = hint.strip().lower()
    if VOICE_ONYX in h:
        return VOICE_ONYX
    if VOICE_SHIMMER in h:
        return VOICE_SHIMMER
    return None


def _voice_default_lesen(hoerspiel_client) -> str:
    """HFE-4: Voice-Default aus GET /config lesen, Fallback VOICE_DEFAULT.

    Fehler beim Config-Lesen werden geloggt und mit dem Default abgefangen —
    der Vorschlag wird trotzdem erstellt (degrades gracefully).
    """
    try:
        cfg = hoerspiel_client.config_lesen()
        v = cfg.get("default_voice") or ""
        if v in (VOICE_SHIMMER, VOICE_ONYX):
            return v
    except HoerspielClientError as exc:
        logger.warning(
            "hoerspiel_folge_erzeugen: config_lesen fehlgeschlagen — %s; "
            "nutze Default '%s'", exc, VOICE_DEFAULT)
    return VOICE_DEFAULT


def _fehler_bubble_album(exc: HoerspielClientError, voice: str) -> str:
    """HFE-5: übersetzt HoerspielClientError in den Fehler-Bubble-Text."""
    if exc.status == 412:
        return (
            "Die Intro/Outro-Aufnahmen für `%s` müssen erst einmalig "
            "vorsynthetisiert werden." % voice)
    if exc.status == 503:
        return "Die Vertonungs-Engine ist gerade nicht erreichbar."
    return "Beim Album-Bau ist etwas schiefgegangen."


def _sende(tg, chat_id, text: str) -> None:
    """Sendet eine Nachricht; ein Sendefehler bricht execute() nicht ab."""
    try:
        tg.send_message(chat_id, text)
    except Exception as exc:  # TelegramError u. ä.
        logger.warning(
            "hoerspiel_folge_erzeugen: send_message fehlgeschlagen: %s", exc)


# Telegram-Limit ist 4096 Zeichen/Nachricht. Wir zielen pro Split auf
# einen lockeren Puffer (Header + Markdown nimmt auch Platz).
TELEGRAM_SPLIT_BUDGET = 3200


def _splitte_vorschau(text: str) -> list[str]:
    """Teilt den Folgentext in mehrere Telegram-taugliche Stücke.

    Schnitt-Kandidaten sind Absatz-Grenzen (`\\n\\n`); Absätze werden nur
    dann zerlegt, wenn ein einzelner Absatz bereits über dem Budget liegt
    (sehr selten). Eltern lesen die Stücke nacheinander und bestätigen
    danach im Confirm-Block.
    """
    if not text:
        return [""]
    absaetze = [a for a in text.strip().split("\n\n") if a.strip()]
    if not absaetze:
        return [text.strip()]
    splits: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for absatz in absaetze:
        addl = len(absatz) + (2 if cur else 0)
        if cur and cur_len + addl > TELEGRAM_SPLIT_BUDGET:
            splits.append("\n\n".join(cur))
            cur = [absatz]
            cur_len = len(absatz)
        else:
            cur.append(absatz)
            cur_len += addl
    if cur:
        splits.append("\n\n".join(cur))
    # Sicherheits-Cap: falls ein einzelner Absatz das Budget sprengt
    out: list[str] = []
    for s in splits:
        if len(s) <= TELEGRAM_SPLIT_BUDGET:
            out.append(s)
        else:
            for j in range(0, len(s), TELEGRAM_SPLIT_BUDGET):
                out.append(s[j:j + TELEGRAM_SPLIT_BUDGET])
    return out
