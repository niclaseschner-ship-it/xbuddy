"""Familie anlegen — siehe specs/platform/familie-anlegen.md (FAA-1…FAA-11,
Refs #60).

»Familie anlegen« ist eine aufrufbare, **trigger-agnostische** Funktion
(E-FAA-1) — analog `ca_verteilung.verteile_ca` (E-CAV-1). Aufgerufen, führt
sie ein Familienmitglied im Privatchat durch die Anlage einer oder mehrerer
Personen und ergänzt sie nach Bestätigungswort (FAA-7, `eltern-chat.md`
E-EC-7) atomar über die HTTP-Schreib-Schnittstelle der Familien-Komponente
(FAA-8, `familie.md` FAM-12/FAM-13).

Die Funktion kennt ihren Aufrufer nicht. Wer sie aufruft — Onboarding-Flow,
konversationeller Aufruf, Slash-Aufruf — ist nicht Teil ihres Vertrags
(E-FAA-1). Sie nimmt nur die für die Anlage nötigen Dinge entgegen: den
Telegram-Kanal, den Privatchat (Chat-ID + User-ID), die ID der gebundenen
Familien-Gruppe (für die Live-Prüfung der Mitgliedschaft, FAA-2 analog
EC-2), den `FamilieClient` (HTTP-Naht zur Familien-Komponente, Auftrag #215)
und eine `next_message()`-Funktion, über die sie die nächste eingehende
Privatchat-Nachricht des Aufrufers abholt. Letzteres macht den Konversations-
Schritt **synchron** und testbar, ohne dass die Funktion an die Update-
Schleife der Eltern-Chat-Orchestrierung gebunden wäre — die Anbindung an
die Orchestrierung ist nach FAA-1 nicht Teil dieser Spec.

Seit Auftrag #215 (`familie_client.FamilieClient`) spricht die Skill nur
noch über HTTP (DCOMP-1): IDENT-1-`id` und Slug-Vergabe leistet FAM-12
serverseitig (Skill liest die zurueckgegebene `id`); Foto laeuft per
`POST /api/v1/familie/personen/<id>/foto` (FAM-13). Die fruehere
Eigenleistung (slug-collision `-2`/`-3`-Suffix, direkter Datei-Write) ist
entfallen.
"""

import logging
import struct
from dataclasses import dataclass
from typing import Callable

import authz
import confirm
from telegram import TelegramError

from skills.familie_client import FamilieClientError
from skills.typing_indicator import fire_typing


# ============================================================
#  Konstanten (FAM-3/FAM-4 spiegelnde Werte fuer die Konversation)
# ============================================================

# FAM-2: Werte fuer das `art`-Feld. Spiegeln familie/registry.KIND_ERWACHSENE
# / KIND_KINDER — die Skill spricht ueber HTTP (DCOMP-1) und ueberlaesst die
# Validierung der Familie. Die Konversation braucht aber die String-Konstanten
# selbst, weil sie die Eingabe direkt prueft (»erwachsene« / »kind«).
KIND_ERWACHSENE = "erwachsene"
KIND_KINDER = "kinder"

# FAM-4: feste Ring-Farb-Palette (Reihenfolge wichtig fuer den FAA-4-
# Vorschlag). `gray` bleibt zuletzt. Spiegel der Palette in
# familie/registry.RING_PALETTE — die Skill braucht die Liste lokal, weil
# der Vorschlag aus dem Snapshot der bereits belegten Ringe abgeleitet wird.
RING_PALETTE = ("blue", "orange", "green", "red", "purple", "teal", "gray")

# FAM-9 / FAA-10: zulaessige Profilbild-Kantenlaenge (Default in Pixel).
# Die Skill prueft das nur lokal als UX-Filter, bevor sie den Anhang
# hochlaedt — Wahrheit ueber den effektiven Wert liegt nach FAM-9 in der
# Familie-Komponente. 1280 ist der hartkodierte Default aus
# `familie/registry.FAM9_DEFAULTS`. Per-Familie-Override leistet die
# Familie selbst; ein eigener HTTP-Settings-Endpunkt waere Wildwuchs
# fuer V1 (Skill schickt das Foto im Zweifel weiter, der Server hat das
# letzte Wort).
PROFILBILD_MAX_KANTE_DEFAULT = 1280


# ============================================================
#  Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail (FAA-3/7/10)
# ============================================================

ASK_ART = ("Wer wird angelegt — ein **Erwachsener** oder ein **Kind**? "
           "Schreib »erwachsene« oder »kind«.")
ASK_NAME = "Wie heißt die Person? (Anzeigename)"
ASK_FOTO = ("Schick mir ein Profilfoto — als Foto oder als Bild-Anhang (JPEG/PNG). "
            "Wenn du keins willst, schreib »überspringen«.")
ASK_RING = ("Welche Ring-Farbe? Vorschlag: **%s**. "
            "Schick eine Farbe aus der Palette (blue, orange, green, red, "
            "purple, teal, gray) oder übernimm den Vorschlag mit »ok«.")
ASK_EMAIL = ("E-Mail-Adresse (optional, hilft bei der Auflösung von "
             "Kalender-Eintragenden). »überspringen«, wenn nicht gewünscht.")
ASK_TELEGRAM = ("Telegram-Benutzer-ID (Zahl, optional). "
                "»überspringen«, wenn nicht gewünscht.")
ASK_TELEGRAM_SELF = ("Telegram-Benutzer-ID (Zahl, optional). Schreib »ich«, "
                     "um deine eigene ID (%s) zu übernehmen, oder "
                     "»überspringen«.")
ASK_NOCH_JEMAND = "Noch jemand anlegen? Schreib »ja« oder »nein«."

REJECT_KIND = "Bitte »erwachsene« oder »kind«."
REJECT_NAME = "Der Name darf nicht leer sein."
REJECT_RING = "Diese Farbe gehört nicht zur Palette."
REJECT_EMAIL = "Das sieht nicht wie eine E-Mail-Adresse aus."
REJECT_TELEGRAM = "Bitte eine Zahl als Telegram-ID."
REJECT_TELEGRAM_DUP = ("Diese Telegram-ID ist bereits einer anderen Person "
                       "zugeordnet. Bitte eine andere Zahl oder "
                       "»überspringen«.")
REJECT_FOTO_MIME = "Anhang ist kein Bild (akzeptiert: JPEG, PNG)."
REJECT_FOTO_GROSS = "Foto ist zu groß. Bitte ein kleineres Bild."
NOT_AUTHORIZED = ("Anlegen geht nur für Mitglieder der Familien-Gruppe. "
                  "Wende dich bitte an jemanden aus der Gruppe.")
WRITE_FAILED = ("Konnte die Person nicht speichern — bitte später noch einmal. "
                "Es wurde nichts in der Registry verändert.")
CANCELLED = "Ok, abgebrochen — nichts gespeichert."
DONE_SINGLE = "Geschafft, %s ist angelegt. 🎉"
DONE_MULTI = "Geschafft — angelegt: %s. 🎉"

# Skip-Wörter (Wortlaut ist Implementierungs-Detail).
_SKIP_WORDS = frozenset({"überspringen", "skip", "-", "weiter"})
_SELF_WORDS = frozenset({"ich", "mich", "meine", "ich selbst"})
_ART_ERWACHSEN = frozenset({"erwachsene", "erwachsener", "erwachsen"})
_ART_KIND = frozenset({"kind", "kinder"})
_RING_OK = frozenset({"ok", "okay", "passt", "übernehmen", "übernimm"})

# FAA-6: akzeptierte Bild-MIMEs.
_MIME_JPEG = "image/jpeg"
_MIME_PNG = "image/png"
_EXT_BY_MIME = {_MIME_JPEG: "jpg", _MIME_PNG: "png"}


# ============================================================
#  Eingabe-Protokoll (Test-Doppelung & Live-Adapter haben dieselbe Form)
# ============================================================

@dataclass
class FaaInput:
    """Eine eingehende Privatchat-Nachricht des Aufrufers, FAA-spezifisch
    aufbereitet — schmaler als IncomingMessage (FAA muss z. B. nicht wissen,
    ob die Nachricht den Bot @-erwähnt).

    `photo_file_id`   — Telegram-Foto-Nachricht: file_id der GRÖSSTEN Auflösung,
                        die die Max-Kante (FAM-9) nicht überschreitet, oder None
                        wenn alle Auflösungen sie überschreiten.
    `photo_oversize`  — True, wenn der Aufrufer ein Foto schickte, aber alle
                        Auflösungen die Max-Kante überschreiten → Ablehnung
                        nach FAA-10.
    `document_file_id`/`document_mime_type`/`document_size_hint` — Datei-Anhang.
    """
    text: str = ""
    photo_file_id: object = None
    photo_oversize: bool = False
    document_file_id: object = None
    document_mime_type: str = ""
    document_size_hint: tuple = None  # (breite, höhe) wenn bekannt, sonst None


# ============================================================
#  Ergebnis
# ============================================================

class FamilieAnlegenError(Exception):
    """Anlegen konnte nicht abgeschlossen werden (Aufrufer entscheidet)."""


@dataclass
class FamilieAnlegenResult:
    """Ergebnis-Signal an den Aufrufer (FAA-1).

    `vergebene_ids` ist die Liste der `id`s der in diesem Aufruf angelegten
    Personen — leere Liste, wenn der Aufrufer schon die erste Anlage
    abgebrochen hat (FAA-7) oder das Mitglied nicht berechtigt war (FAA-2).
    `authorized` unterscheidet diesen letzteren Fall.
    """
    vergebene_ids: list = None
    authorized: bool = True

    def __post_init__(self):
        if self.vergebene_ids is None:
            self.vergebene_ids = []


# ============================================================
#  Die Funktion
# ============================================================

def familie_anlegen(tg, chat_id, user_id, family_group_chat_id,
                    client, next_message,
                    profilbild_max_kante=PROFILBILD_MAX_KANTE_DEFAULT,
                    typing_fn: Callable[[], None] | None = None):
    """Legt eine oder mehrere Familienmitglieder an (FAA-1).

    `tg`                    — Telegram-Kanal (mit `send_message`, `download_file`,
                              `get_chat_member`).
    `chat_id`               — Privatchat des Aufrufers (FAA-3).
    `user_id`               — Telegram-User-ID des Aufrufers (FAA-2/FAA-3 Schritt 6).
    `family_group_chat_id`  — ID der gebundenen Familien-Gruppe (FAA-2).
    `client`                — `FamilieClient` (HTTP-Naht, DCOMP-1). Wird fuer
                              den Snapshot (Ring-Vorschlag, Dup-Check),
                              die Anlage (FAM-12) und den Foto-Upload
                              (FAM-13) verwendet.
    `next_message`          — Callable, das die nächste eingehende
                              Privatchat-Nachricht des Aufrufers liefert
                              (FaaInput). Liefert `None`, gilt die Anlage als
                              abgebrochen.
    `profilbild_max_kante`  — UX-Filter fuer den Foto-Upload (FAA-10). Default
                              `PROFILBILD_MAX_KANTE_DEFAULT` (1280). Wert
                              `None` schaltet den Filter aus — der Server hat
                              das letzte Wort (FAM-9).
    `typing_fn`             — Optionaler Callable ohne Argumente; wird vor jeder
                              send_message-Phase aufgerufen (EC-25: Typing-Indikator,
                              Best-Effort, Fehler werden geschluckt). Default None →
                              No-op (Backward-Compat). Vgl. skills/typing_indicator.py.

    Liefert ein `FamilieAnlegenResult` mit `vergebene_ids`. Schreibt
    ausschliesslich über die HTTP-Schreib-Schnittstelle der Familien-
    Komponente (FAA-8, FAM-12/FAM-13).
    """
    # FAA-2: Berechtigung live über die Familien-Gruppen-Mitgliedschaft.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("familie_anlegen: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
        fire_typing(typing_fn)
        _send(tg, chat_id, NOT_AUTHORIZED)
        return FamilieAnlegenResult(vergebene_ids=[], authorized=False)

    vergebene_ids = []

    while True:
        person_id = _eine_person_anlegen(
            tg, chat_id, user_id, client, next_message, profilbild_max_kante,
            typing_fn)
        if person_id is None:
            # Abbruch (FAA-7) oder Eingabe-Strom zu Ende — wir beenden den Aufruf.
            break
        vergebene_ids.append(person_id)

        # FAA-9: »Noch jemand?« — bei nicht-bestätigender Antwort beenden.
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_NOCH_JEMAND)
        msg = next_message()
        if msg is None or not confirm.is_confirmation((msg.text or "").strip()):
            break

    if vergebene_ids:
        fire_typing(typing_fn)
        if len(vergebene_ids) == 1:
            _send(tg, chat_id, DONE_SINGLE % vergebene_ids[0])
        else:
            _send(tg, chat_id, DONE_MULTI % ", ".join(vergebene_ids))
    return FamilieAnlegenResult(vergebene_ids=vergebene_ids, authorized=True)


# ============================================================
#  Anlage genau einer Person — FAA-3 in fester Reihenfolge
# ============================================================

def _eine_person_anlegen(tg, chat_id, user_id, client, next_message,
                          profilbild_max_kante, typing_fn=None):
    """Legt EINE Person an. Liefert die vergebene `id` oder None (Abbruch)."""
    # Bei jedem Personen-Start den aktuellen Personen-Stand frisch holen —
    # sonst sehen wir die in derselben Schleife frisch angelegte Person nicht
    # fuer Ring-Vorschlag (FAA-4) oder Telegram-ID-Duplikat (FAA-10).
    # FAM-12 ueberprueft selbst (Dup-Check serverseitig), aber die Skill
    # liefert dem Aufrufer schon vorher einen REJECT_TELEGRAM_DUP.
    try:
        current = client.alle_personen()
    except FamilieClientError as e:
        logging.warning("familie_anlegen: Familie-Service nicht erreichbar: %s", e)
        fire_typing(typing_fn)
        _send(tg, chat_id, WRITE_FAILED)
        return None

    # FAA-3 Schritt 1: Art.
    art = _frage_art(tg, chat_id, next_message, typing_fn)
    if art is None:
        return None

    # Schritt 2: Name.
    name = _frage_name(tg, chat_id, next_message, typing_fn)
    if name is None:
        return None

    # Schritt 3: Foto (optional).
    foto_ext, foto_bytes, foto_content_type = _frage_foto(
        tg, chat_id, next_message, profilbild_max_kante, typing_fn)
    if foto_ext is False:
        # Abbruch im Foto-Schritt.
        return None

    # Schritt 4: Ring-Farbe.
    ring = _frage_ring(tg, chat_id, next_message, current, typing_fn)
    if ring is None:
        return None

    # Schritt 5: E-Mail (nur Erwachsene).
    email = None
    if art == KIND_ERWACHSENE:
        email = _frage_email(tg, chat_id, next_message, typing_fn)
        if email is False:
            return None

    # Schritt 6: Telegram-ID (optional, beide Arten).
    telegram_id = _frage_telegram(
        tg, chat_id, user_id, next_message, current, name, typing_fn)
    if telegram_id is False:
        return None

    # FAA-7 / EC-10: Zusammenfassung + Bestätigungswort in EINER Nachricht.
    # FAA hat immer Pflicht-Felder (Art, Name, Foto, Ring) → zweistufige Variante
    # ist der einzige Pfad (vollständiger Anstoß ist strukturell nicht möglich).
    # Die _zusammenfassung enthält bereits die Bestätigungsfrage als ersten Satz
    # — das ist die EC-10-konforme kombinierte Nachricht nach Abschluss aller
    # Rückfragen. Die `id` vergibt FAM-12 erst nach dem Bestaetigungswort;
    # in der Zusammenfassung zeigen wir nur die vom Aufrufer erfassten Werte.
    summary = _zusammenfassung(name, art, ring, foto_ext, email, telegram_id)
    fire_typing(typing_fn)
    _send(tg, chat_id, summary)
    bestaetigung = next_message()
    if bestaetigung is None or not confirm.is_confirmation(
            (bestaetigung.text or "").strip()):
        fire_typing(typing_fn)
        _send(tg, chat_id, CANCELLED)
        return None

    # FAA-8: Schreiben ausschliesslich ueber FAM-12 (HTTP). Server vergibt
    # die IDENT-1-`id` (`person-<slug>-<nn>`).
    try:
        angelegt = client.person_anlegen(
            name=name, art=art, ring=ring,
            email=email, telegram_id=telegram_id)
    except FamilieClientError as e:
        logging.warning("familie_anlegen: Anlage fehlgeschlagen: %s", e)
        fire_typing(typing_fn)
        _send(tg, chat_id, WRITE_FAILED)
        return None

    person_id = angelegt.get("id")
    if not person_id:
        logging.warning(
            "familie_anlegen: FAM-12-Antwort ohne id: %r", angelegt)
        fire_typing(typing_fn)
        _send(tg, chat_id, WRITE_FAILED)
        return None

    # FAA-6: Foto haengt am `<id>/<dateiname>`-Schema der Schreib-API
    # (FAM-13). Wir wissen die `id` erst nach FAM-12, also haengt der
    # Foto-Upload hinten dran — bei Fehlschlag bleibt die Person aber
    # angelegt (kein Rollback, FAM-13 ist eigenstaendig).
    if foto_bytes is not None and foto_ext is not None:
        dateiname = "%s.%s" % (person_id, foto_ext)
        try:
            client.foto_hochladen(
                person_id=person_id, dateiname=dateiname,
                daten=foto_bytes, content_type=foto_content_type)
        except FamilieClientError as e:
            # Foto-Upload-Fehlschlag waere unschoen, aber die Person ist
            # bereits angelegt — wir loggen und melden den Teilerfolg an
            # die Familie, statt die ganze Anlage zu kippen.
            logging.warning(
                "familie_anlegen: Foto-Upload fehlgeschlagen (Person %s bleibt "
                "angelegt): %s", person_id, e)

    return person_id


# ============================================================
#  Einzel-Schritte (FAA-3)
# ============================================================

def _frage_art(tg, chat_id, next_message, typing_fn=None):
    """FAA-3 Schritt 1: Art — Erwachsene oder Kind."""
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_ART)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip().lower()
        if text in _ART_ERWACHSEN:
            return KIND_ERWACHSENE
        if text in _ART_KIND:
            return KIND_KINDER
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_KIND)


def _frage_name(tg, chat_id, next_message, typing_fn=None):
    """FAA-3 Schritt 2: Name — Pflicht, nicht leer."""
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_NAME)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip()
        if text:
            return text
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_NAME)


def _frage_foto(tg, chat_id, next_message, max_kante, typing_fn=None):
    """FAA-3 Schritt 3: Profilfoto — optional.

    Liefert `(ext_or_None, bytes_or_None, content_type_or_None)`:
      - `(None, None, None)`               : Aufrufer hat übersprungen.
      - `("jpg"/"png", b"…", "image/...")` : Foto-Bytes liegen vor, Endung steht fest.
      - `(False, None, None)`              : Aufrufer hat die ganze Anlage abgebrochen.
    """
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_FOTO)
        msg = next_message()
        if msg is None:
            return False, None, None
        text = (msg.text or "").strip().lower()
        if text in _SKIP_WORDS:
            return None, None, None

        # Telegram-Foto-Nachricht (FAA-6: immer JPEG).
        if msg.photo_file_id is not None:
            try:
                raw = tg.download_file(msg.photo_file_id)
            except TelegramError as e:
                logging.warning("familie_anlegen: Foto-Download fehlgeschlagen: %s", e)
                fire_typing(typing_fn)
                _send(tg, chat_id, REJECT_FOTO_GROSS)
                continue
            return "jpg", raw, _MIME_JPEG
        if msg.photo_oversize:
            fire_typing(typing_fn)
            _send(tg, chat_id, REJECT_FOTO_GROSS)
            continue

        # Datei-Anhang.
        if msg.document_file_id is not None:
            mime = (msg.document_mime_type or "").lower()
            if mime not in _EXT_BY_MIME:
                fire_typing(typing_fn)
                _send(tg, chat_id, REJECT_FOTO_MIME)
                continue
            # FAA-10: Kantenlänge prüfen, wenn der Anhang die Maße mitliefert.
            if msg.document_size_hint is not None and max_kante is not None:
                w, h = msg.document_size_hint
                if max(w, h) > max_kante:
                    fire_typing(typing_fn)
                    _send(tg, chat_id, REJECT_FOTO_GROSS)
                    continue
            try:
                raw = tg.download_file(msg.document_file_id)
            except TelegramError as e:
                logging.warning("familie_anlegen: Anhang-Download fehlgeschlagen: %s", e)
                fire_typing(typing_fn)
                _send(tg, chat_id, REJECT_FOTO_GROSS)
                continue
            # PNG: Kantenlänge aus dem PNG-Header lesen, falls die Eingabe keine
            # Maße mitlieferte (FAA-10: „längste Kante überschreitet Wert").
            if mime == _MIME_PNG and max_kante is not None:
                masse = _png_dimensions(raw)
                if masse is not None and max(masse) > max_kante:
                    fire_typing(typing_fn)
                    _send(tg, chat_id, REJECT_FOTO_GROSS)
                    continue
            return _EXT_BY_MIME[mime], raw, mime

        # Keine Foto-Form erkannt — Frage wiederholen.
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_FOTO_MIME)


def _frage_ring(tg, chat_id, next_message, current, typing_fn=None):
    """FAA-3 Schritt 4 / FAA-4: Ring-Farbe mit Vorschlag."""
    vorschlag = _ring_vorschlag(current)
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_RING % vorschlag)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip().lower()
        if text in _RING_OK or text == vorschlag:
            return vorschlag
        if text in RING_PALETTE:
            return text
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_RING)


def _frage_email(tg, chat_id, next_message, typing_fn=None):
    """FAA-3 Schritt 5: E-Mail (nur Erwachsene), optional.

    Liefert die E-Mail-Adresse, None (übersprungen) oder False (Abbruch).
    """
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_EMAIL)
        msg = next_message()
        if msg is None:
            return False
        text = (msg.text or "").strip()
        if text.lower() in _SKIP_WORDS:
            return None
        if _looks_like_email(text):
            return text
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_EMAIL)


def _frage_telegram(tg, chat_id, user_id, next_message, current, name,
                    typing_fn=None):
    """FAA-3 Schritt 6: Telegram-ID (optional, beide Arten).

    Bietet die eigene User-ID als Default an, wenn der Aufrufer signalisiert,
    dass die anzulegende Person er selbst ist (»ich«). FAA-10: eine bereits
    vergebene Telegram-ID wird abgelehnt — der Pre-Check basiert auf dem
    Snapshot; FAM-12 weist Dup zusaetzlich serverseitig ab.
    """
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_TELEGRAM_SELF % user_id)
        msg = next_message()
        if msg is None:
            return False
        text = (msg.text or "").strip().lower()
        if text in _SKIP_WORDS:
            return None
        if text in _SELF_WORDS:
            kandidat = user_id
        else:
            try:
                kandidat = int(text)
            except (TypeError, ValueError):
                fire_typing(typing_fn)
                _send(tg, chat_id, REJECT_TELEGRAM)
                continue
        # FAA-10: Doppelung verhindern — eine Telegram-ID = eine Person.
        if any(p.get("telegram_id") == kandidat for p in current):
            fire_typing(typing_fn)
            _send(tg, chat_id, REJECT_TELEGRAM_DUP)
            continue
        return kandidat


# ============================================================
#  Helpers
# ============================================================

def _ring_vorschlag(current):
    """FAA-4: erste freie Palette-Farbe, gray bleibt zuletzt.

    `current` ist die Liste der Personen-Dicts aus FAM-7.
    """
    belegt = set(p.get("ring") for p in current)
    for farbe in RING_PALETTE:  # FAM-4: Reihenfolge der Palette
        if farbe == "gray":
            continue
        if farbe not in belegt:
            return farbe
    return "gray"


def _looks_like_email(text):
    """Syntaktische E-Mail-Prüfung — eine Adresse mit genau einem @ und Punkt
    in der Domain. Bewusst pragmatisch (RFC-vollständig ist V1 nicht)."""
    if "@" not in text:
        return False
    local, _, domain = text.rpartition("@")
    return bool(local) and "." in domain and not domain.startswith(".")


def _zusammenfassung(name, art, ring, foto_ext, email, telegram_id):
    """FAA-7: Zusammenfassung vor dem Bestätigungswort.

    Die `id` ist hier noch nicht bekannt — FAM-12 vergibt sie erst beim
    POST-Aufruf (`person-<slug>-<nn>`). Die Zusammenfassung zeigt deshalb
    nur die vom Aufrufer erfassten Werte.
    """
    art_label = "Erwachsene" if art == KIND_ERWACHSENE else "Kind"
    teile = [
        "Bitte bestätigen (»ok« / »ja«):",
        "• Art: %s" % art_label,
        "• Name: %s" % name,
        "• Ring: %s" % ring,
    ]
    if foto_ext:
        teile.append("• Foto: ja (.%s)" % foto_ext)
    if email:
        teile.append("• E-Mail: %s" % email)
    if telegram_id is not None:
        teile.append("• Telegram-ID: %s" % telegram_id)
    return "\n".join(teile)


def _png_dimensions(data):
    """Liest Breite/Höhe aus dem PNG-Header. Liefert (w, h) oder None."""
    # PNG-Signatur + IHDR-Chunk: w/h stehen als big-endian uint32 ab Offset 16.
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        w, h = struct.unpack(">II", data[16:24])
    except struct.error:
        return None
    return (w, h)


def _send(tg, chat_id, text):
    """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt, aber
    brechen die Funktion nicht ab — analog `onboarding._send`."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logging.warning("familie_anlegen: Senden an %s fehlgeschlagen: %s",
                        chat_id, e)
