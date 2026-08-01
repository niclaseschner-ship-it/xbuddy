"""Hörspiel-Folge erzeugen — specs/platform/hoerspiel-folge-erzeugen.md
(HFE-1 … HFE-10, E-HFE-1 … E-HFE-6).

Aufrufbare, trigger-agnostische Funktion (HFE-1, E-HFE-1): nimmt eine
Folgen-Idee und die `kind_id` der Ziel-Instanz entgegen, holt vom
Hörspiel-Buddy einen Folgen-Vorschlag
(POST /api/v1/hoerspiel/<kind_id>/folgen-vorschlag) und löst den Album-Bau
aus (POST /api/v1/hoerspiel/<kind_id>/alben). Der LLM-Aufruf lebt im
Hörspiel-Buddy — dieser Skill ist ein dünner Konsument (E-HFE-2).

`kind_id` ist Pflicht-Argument seit RAT-17 / E-HFE-6 (#910). Die
Modul-Konstante MIA_ALTER wurde damit ersetzt: Alter lebt in der
instance.json des Buddys, nicht im Skill (E-HFE-6, HSP-27).

Pattern (E-HFE-5 / E-HFE-3): **propose → confirm**, NICHT Sofort-Wirkung.
Ein Album-Bau kostet 1–5 min TTS-Zeit; die Voice-Wahl verlangt einen
vorab sichtbaren Vorschlag. EC-10-Gate sitzt eine Ebene höher im Task.

Berechtigung (HFE-2): nur Familien-Mitglieder (is_member_fn). Im
Agent-Loop wirft die Funktion `BerechtigungError` — kein Buddy-Aufruf.

Eingang propose(): hoerspiel_client, is_member_fn, from_user_id, idee,
  kind_id (Pflicht, RAT-17 / E-HFE-6),
  mini_app_base_url (für HFE-10 Settings-Beifang, optional),
  is_first_propose (HFE-10: True für erste propose()-Antwort im Turn).
Eingang execute(): hoerspiel_client, tg, chat_id, display_url_origin,
  titel, text, voice, idee.

Ausgang propose(): strukturierter Tool-Result-Text (HFE-4) bei Erfolg,
  oder EC-22-Rückfrage-Text via ValueError (Sub-Case 1/2),
  oder HoerspielClientError bei Fehler.
Ausgang execute(): sendet Erfolgs- oder Fehler-Bubble über tg (HFE-5).

HFE-3 Diskussions-Schleife (Werft-Lauf 2026-06-15, Refs #848):
  Sub-Case 1: leere/mehrdeutige Idee → themen_lesen(kind_id) + EC-22-Rückfrage.
  Sub-Case 2: konkret-aber-unvollständig (vom Agent markiert via
              idee_diskussion=True) → Diskussions-Marker zurückgeben.
  Sub-Case 3: konkrete vollständige Idee → Standard-Pfad.

HFE-10 Settings-Beifang: In der ersten propose()-Antwort eines Turns
trägt die Antwort einen Button (⚙️ Einstellungen) via tg.send_inline_keyboard,
der auf die Player-PWA zeigt (HSP-53). Wenn mini_app_base_url leer: still
ausgelassen.
"""

import json
import logging

from skills._errors import BerechtigungError
from skills.hoerspiel_client import HoerspielClientError

logger = logging.getLogger(__name__)

# HFE-4: erlaubte Voice-Werte (shimmer/onyx, HSP-23).
VOICE_SHIMMER = "shimmer"
VOICE_ONYX    = "onyx"
VOICE_DEFAULT = VOICE_ONYX   # HSP-26-Default, Fallback wenn config nicht erreichbar (#995)

# E-HFE-6 / RAT-17: MIA_ALTER wurde entfernt. kind_id ist Pflicht-Argument
# von propose(); Alter zieht der Buddy aus seiner instance.json (HSP-27).

# HFE-3 Sub-Case 2: JSON-Marker-Präfix für den Diskussions-Pattern.
# Der Agent erkennt diesen Marker im Tool-Result und stellt Rückfragen.
_DISKUSSION_MARKER_KEY = "diskussion"

# HFE-3 Sub-Case 1: Mindest-Länge in Zeichen für eine nicht-leere Idee.
# Ideen unter diesem Wert gelten als leer/mehrdeutig → Themen-Rückfrage.
_IDEE_MIN_ZEICHEN = 5


def propose(*, hoerspiel_client, is_member_fn, from_user_id,
            idee: str, kind_id: str,
            tg=None, chat_id=None,
            mini_app_base_url: str | None = None,
            is_first_propose: bool = True,
            idee_diskussion: bool = False) -> tuple[str, dict]:
    """Folgen-Vorschlag holen und als strukturierten Text zurückgeben (HFE-3/4).

    Trigger-agnostisch (E-HFE-1): wer diese Funktion aufruft, ist nicht
    Teil ihres Vertrags. Im Agent-Loop ruft HoerspielFolgeErzeugenTask.propose()
    sie auf (HFE-1).

    `hoerspiel_client` — HoerspielClient-Instanz (hoerspiel_client.py).
    `is_member_fn`     — Callable `(user_id) -> bool` (HFE-2).
    `from_user_id`     — Telegram-User-ID des Aufrufers (HFE-2).
    `idee`             — Folgen-Idee aus dem Aufrufer-Text (HFE-3).
    `kind_id`          — Pflicht-Arg: Instanz-Identität des Hörspiel-Buddys
                         (E-HFE-6, RAT-17). Kommt aus Face-Pille-State der
                         Mini-App oder LLM-Entscheidung im Agent-Prompt (HFE-3).
    `tg`               — optionaler Telegram-Client (für Start-Bubble + HFE-10).
    `chat_id`          — Ziel-Chat (für Start-Bubble + HFE-10).
    `mini_app_base_url`— Basis-URL der Eltern-Mini-App (HFE-10, optional).
    `is_first_propose` — True wenn dies die erste propose()-Antwort des Turns
                         ist (HFE-10 Settings-Beifang); False für Folge-Antworten.
    `idee_diskussion`  — True wenn der Agent eine konkret-aber-unvollständige
                         Idee erkannt hat (HFE-3 Sub-Case 2). Default: False.

    HFE-4 (#995): Voice-Wechsel lebt **nur** in der Mini-App (HSP-34 PATCH /config).
    Kein voice_hint mehr — der Skill liest die Default-Voice aus GET /config
    NACH dem Folgen-Vorschlag-LLM-Call, damit eine Mini-App-Änderung während
    der 90s-Wartezeit (HFE-10-Settings-Beifang-Button) noch einfließt.

    Rückgabe: Tuple (result_text, fields_dict) bei Erfolg (Sub-Case 3).

    Wirft:
      BerechtigungError — Aufrufer nicht berechtigt (HFE-2).
      ValueError        — leere/mehrdeutige Idee (Sub-Case 1) oder
                          Diskussions-Marker (Sub-Case 2); Nachricht ist der
                          Tool-Result-Text den das LLM als Antwort nutzt.
      HoerspielClientError(status=503)  — LLM-Provider nicht eingerichtet.
      HoerspielClientError(status!=503) — Buddy nicht erreichbar.

    HFE-7: keine tg.send_*-Aufrufe außer Start-Bubble (1-2 min Stille)
    und HFE-10 Beifang-Button (erster Turn) in dieser Funktion.
    """
    # HFE-2: Berechtigung prüfen — kein Buddy-Aufruf bei Nicht-Mitglied.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info(
            "hoerspiel_folge_erzeugen.propose: User %s nicht berechtigt (HFE-2)",
            from_user_id)
        raise BerechtigungError("Das geht nur für Eltern.")

    idee_bereinigt = (idee or "").strip()

    # HFE-3 Sub-Case 2: Agent hat die Idee als "konkret-aber-unvollständig"
    # markiert. Der Skill gibt einen Diskussions-Marker zurück.
    # Der Agent (Agent-Prompt, EC-30-Trennlinie) stellt die Rückfragen.
    if idee_diskussion and idee_bereinigt:
        logger.info(
            "hoerspiel_folge_erzeugen.propose: Sub-Case 2 — Diskussions-Marker "
            "(idee=%r)", idee_bereinigt)
        # HFE-10: Settings-Beifang-Button in erster propose()-Antwort.
        if is_first_propose and tg is not None and chat_id is not None:
            _sende_beifang_button(tg, chat_id, mini_app_base_url)
        marker = json.dumps(
            {_DISKUSSION_MARKER_KEY: True, "idee_bisher": idee_bereinigt},
            ensure_ascii=False)
        raise ValueError(marker)

    # HFE-3 Sub-Case 1: leere oder mehrdeutige Idee → Themen-Liste + Rückfrage.
    if len(idee_bereinigt) < _IDEE_MIN_ZEICHEN:
        logger.info(
            "hoerspiel_folge_erzeugen.propose: Sub-Case 1 — leere/mehrdeutige "
            "Idee — rufe GET /api/v1/hoerspiel/%s/themen (HFE-3, RAT-17)", kind_id)
        rueckfrage = _baue_themen_rueckfrage(hoerspiel_client, kind_id)
        # HFE-10: Settings-Beifang-Button in erster propose()-Antwort.
        if is_first_propose and tg is not None and chat_id is not None:
            _sende_beifang_button(tg, chat_id, mini_app_base_url)
        raise ValueError(rueckfrage)

    # HFE-3: kind_id-Validierung via Buddy-Aufruf entfällt hier — der Buddy
    # selbst gibt 404 zurück wenn die kind_id unbekannt ist. Das wird weiter
    # unten in HoerspielClientError(status=404) übersetzt.

    # HFE-3 Sub-Case 3: Folgen-Vorschlag vom Hörspiel-Buddy holen.
    # Live-UX: der LLM-Call dauert 1-2 min, propose() bleibt sonst stumm.
    # Nic-Befund 2026-06-12: Eltern denken in der Stille, der Bot sei
    # eingefroren. Start-Bubble vor dem Aufruf — analog execute().
    if tg is not None and chat_id is not None:
        _sende(tg, chat_id,
               "Klar, ich überlege mir gerade eine Folge. "
               "Das dauert 1–2 Minuten — bitte solange nicht stören, "
               "ich melde mich, sobald der Vorschlag steht.")
    # HFE-10 (Live-Fix 2026-06-16): Settings-Beifang-Button gehört VOR den
    # LLM-Call (= zur ERSTEN propose()-Antwort). Wenn er erst nach dem 1-2-min
    # Vorschlag käme, hätte Eltern keine Chance mehr, Voice/Provider vorher zu
    # tunen — Spec-Sinn verfehlt. Sende ihn jetzt direkt nach "Klar, ich überlege".
    if is_first_propose and tg is not None and chat_id is not None:
        _sende_beifang_button(tg, chat_id, mini_app_base_url)
    logger.info(
        "hoerspiel_folge_erzeugen.propose: rufe POST /api/v1/hoerspiel/%s/"
        "folgen-vorschlag (HFE-3 Sub-Case 3, RAT-17)", kind_id)
    try:
        data = hoerspiel_client.folgen_vorschlag(idee_bereinigt)
    except HoerspielClientError as exc:
        if exc.status == 404:
            # kind_id unbekannt — Fehler-Tool-Result-Text (HFE-3, kein Vorschlag).
            raise ValueError("Für %s gibt es keinen Hörspiel-Buddy." % kind_id) from exc
        raise  # 503 / 5xx / None → propagiert weiter (Task-Layer übernimmt)

    # HFE-4 (#995): Voice-Default NACH dem 90s-LLM-Call lesen, damit eine
    # Mini-App-Änderung während des HFE-10-Tune-Fensters (Settings-Beifang)
    # noch in den Bestätigungs-Block einfließt. Vorher lag das vor dem Call —
    # Race: User stellte in der Mini-App auf onyx um, Vorschlag kam aber
    # mit dem alten shimmer-Stand zurück.
    voice = _voice_default_lesen(hoerspiel_client)

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
        # HFE-4 (#995): kein on-the-fly Voice-Override mehr — Voice-Wechsel
        # lebt in der Mini-App-Settings (HSP-34). Result-Text trägt nur den
        # aktuellen Stand zur Information.
        result = (
            "Vollständiger Vorschlag oben in %d Nachrichten.\n\n"
            "Voice: %s\n"
            "Vertonen? Antworte nur mit »ja« (oder 👍). Das dauert 1–5 Minuten."
        ) % (len(splits), voice)
    else:
        # Kurze Folge (≤ 1 Split) oder kein tg verfügbar: alles in den
        # Tool-Result-Block, das LLM postet eine Bot-Nachricht.
        result = (
            "**Folge %s: %s**\n\n"
            "%s\n\n"
            "Voice: %s\n"
            "Vertonen? Antworte nur mit »ja« (oder 👍). Das dauert 1–5 Minuten."
        ) % (folge_nr, titel, splits[0] if splits else text, voice)

    # HFE-10 wurde oben schon vor dem LLM-Call ausgelöst (Live-Fix 2026-06-16).
    logger.info(
        "hoerspiel_folge_erzeugen.propose: Vorschlag bereit "
        "(folge_nr=%s, voice=%s)", folge_nr, voice)
    return result, {
        "titel": titel,
        "text": text,
        "voice": voice,
        "folge_nr": folge_nr,
    }


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
           "Das dauert etwa 1–3 Minuten — bitte solange nicht stören, "
           "ich melde mich, sobald die Folge in der App ist.")
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
    # HSP-53: Fertig-Link zeigt auf die Player-PWA (nicht mehr /display/hoerspiel/alben)
    url = "%s/seiten/hoerspiel/player" % origin if origin else "/seiten/hoerspiel/player"
    bubble = "✅ Folge %s ist in der App.\n%s" % (nr, url)
    logger.info(
        "hoerspiel_folge_erzeugen.execute: Album gebaut album-id=%s", nr)
    _sende(tg, chat_id, bubble)


# ============================================================
#  Helpers
# ============================================================

def _baue_themen_rueckfrage(hoerspiel_client, kind_id: str) -> str:
    """HFE-3 Sub-Case 1: GET /api/v1/hoerspiel/<kind_id>/themen + EC-22-Rückfrage-Text.

    Response-Body trägt {kind_id, name, alter, themen} (HFE-3, HSP-38, RAT-17).
    Der Kindername wird in der personalisierten Rückfrage genutzt.

    Bei 404 (kind_id unbekannt): Fehler-Tool-Result-Text (kein Vorschlag).
    Bei 422 (Alter nicht gepflegt): nur EC-22-Rückfrage ohne Themen (HFE-3).
    Bei anderen Fehlern: nur EC-22-Rückfrage (degrades gracefully).
    """
    try:
        data = hoerspiel_client.themen_lesen()
    except HoerspielClientError as exc:
        if exc.status == 404:
            # kind_id unbekannt — Fehler-Tool-Result-Text (HFE-3, keine Themen möglich)
            logger.warning(
                "hoerspiel_folge_erzeugen: themen_lesen kind_id=%r → 404 "
                "(unbekannte Instanz, HFE-3)", kind_id)
            return "Für %s gibt es keinen Hörspiel-Buddy." % kind_id
        # 422 (Alter nicht gepflegt) oder Netzfehler → EC-22-Rückfrage ohne Themen
        logger.warning(
            "hoerspiel_folge_erzeugen: themen_lesen fehlgeschlagen "
            "(status=%s) — Rückfrage ohne Themen", exc.status)
        return (
            "Worum soll die Folge gehen? "
            "Beschreib die Idee kurz (ein Satz reicht), "
            "dann erstelle ich einen Vorschlag."
        )

    themen = data.get("themen") or []
    name = data.get("name") or ""
    alter = data.get("alter")

    if themen:
        themen_str = ", ".join(themen)
        if name and alter is not None:
            return (
                "Worum soll die Folge gehen? "
                "Hier ein paar Vorschläge für %s (%d Jahre): %s"
            ) % (name, alter, themen_str)
        return (
            "Worum soll die Folge gehen? "
            "Hier ein paar Vorschläge: %s"
        ) % themen_str
    return (
        "Worum soll die Folge gehen? "
        "Beschreib die Idee kurz (ein Satz reicht), "
        "dann erstelle ich einen Vorschlag."
    )


def _sende_beifang_button(tg, chat_id, mini_app_base_url: str | None) -> None:
    """HFE-10: Settings-Beifang-Button senden (einmal pro Turn, erste Antwort).

    HSP-53: öffnet die Player-PWA (/seiten/hoerspiel/player, AUTH-6) —
    kein Tab-Hash (#einstellungen) mehr. Eltern erreicht Settings über
    das Zahnrad im Player.

    Wenn mini_app_base_url leer: still ausgelassen, kein Fehler, kein Text.
    Button-Label: ⚙️ Einstellungen;
    URL: <mini_app_base_url>/seiten/hoerspiel/player (HSP-47 / HSP-53).
    """
    if not mini_app_base_url:
        logger.debug(
            "hoerspiel_folge_erzeugen: mini_app_base_url leer — "
            "Settings-Beifang-Button entfällt (HFE-10)")
        return
    base = mini_app_base_url.rstrip("/")
    player_url = "%s/seiten/hoerspiel/player" % base
    try:
        tg.send_inline_keyboard(
            chat_id,
            "⚙️ Voice oder Anbieter ändern?",
            [{"label": "⚙️ Einstellungen", "url": player_url}],
        )
        logger.debug(
            "hoerspiel_folge_erzeugen: Settings-Beifang-Button gesendet "
            "(HFE-10) chat_id=%s", chat_id)
    except Exception as exc:  # Beifang darf HFE-Fluss nicht brechen
        logger.warning(
            "hoerspiel_folge_erzeugen: send_inline_keyboard fehlgeschlagen "
            "(HFE-10, verschluckt): %s", exc)


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
