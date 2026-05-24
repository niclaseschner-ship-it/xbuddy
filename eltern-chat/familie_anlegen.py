"""Familie anlegen — siehe specs/platform/familie-anlegen.md (FAA-1…FAA-11,
Refs #60).

»Familie anlegen« ist eine aufrufbare, **trigger-agnostische** Funktion
(E-FAA-1) — analog `ca_verteilung.verteile_ca` (E-CAV-1). Aufgerufen, führt
sie ein Familienmitglied im Privatchat durch die Anlage einer oder mehrerer
Personen und ergänzt sie nach Bestätigungswort (FAA-7, `eltern-chat.md`
E-EC-7) atomar über die Schreib-Schnittstelle der Familien-Registry
(FAA-8, `familie.md` FAM-11).

Die Funktion kennt ihren Aufrufer nicht. Wer sie aufruft — Onboarding-Flow,
konversationeller Aufruf, Slash-Aufruf — ist nicht Teil ihres Vertrags
(E-FAA-1). Sie nimmt nur die für die Anlage nötigen Dinge entgegen: den
Telegram-Kanal, den Privatchat (Chat-ID + User-ID), die ID der gebundenen
Familien-Gruppe (für die Live-Prüfung der Mitgliedschaft, FAA-2 analog
EC-2), den Pfad zur Registry-Datei und eine `next_message()`-Funktion,
über die sie die nächste eingehende Privatchat-Nachricht des Aufrufers
abholt. Letzteres macht den Konversations-Schritt **synchron** und
testbar, ohne dass die Funktion an die Update-Schleife der Eltern-Chat-
Orchestrierung gebunden wäre — die Anbindung an die Orchestrierung ist
nach FAA-1 nicht Teil dieser Spec.
"""

import logging
import os
import re
import struct
from dataclasses import dataclass, field

import authz
import confirm
from telegram import TelegramError

# Pakete der Familien-Registry: das schreibende und lesende Modul.
import sys
_ELTERN_CHAT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_ELTERN_CHAT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from familie import registry as registry_mod  # noqa: E402


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

# Umlaut-Auflösung für FAA-5 (Slug).
_UMLAUTE = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
            "Ä": "ae", "Ö": "oe", "Ü": "ue"}


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
    vergebene_ids: list = field(default_factory=list)
    authorized: bool = True


# ============================================================
#  Die Funktion
# ============================================================

def familie_anlegen(tg, chat_id, user_id, family_group_chat_id,
                    registry_path, next_message):
    """Legt eine oder mehrere Familienmitglieder an (FAA-1).

    `tg`                    — Telegram-Kanal (mit `send_message`, `download_file`,
                              `get_chat_member`).
    `chat_id`               — Privatchat des Aufrufers (FAA-3).
    `user_id`               — Telegram-User-ID des Aufrufers (FAA-2/FAA-3 Schritt 6).
    `family_group_chat_id`  — ID der gebundenen Familien-Gruppe (FAA-2).
    `registry_path`         — Pfad zur familie.json (Schreiben über FAM-11).
    `next_message`          — Callable, das die nächste eingehende
                              Privatchat-Nachricht des Aufrufers liefert
                              (FaaInput). Liefert `None`, gilt die Anlage als
                              abgebrochen.

    Liefert ein `FamilieAnlegenResult` mit `vergebene_ids`. Schreibt
    ausschliesslich über die Registry-Schreib-Schnittstelle (FAA-8, FAM-11).
    Familienspezifische Werte (Foto-Verzeichnis, Profilbild-Max-Kante) holt
    die Funktion über die Registry-Settings + ENV/Default (FAM-9) —
    **nicht** als Aufruf-Parameter (FAA-1).
    """
    # FAA-2: Berechtigung live über die Familien-Gruppen-Mitgliedschaft.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("familie_anlegen: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
        _send(tg, chat_id, NOT_AUTHORIZED)
        return FamilieAnlegenResult(vergebene_ids=[], authorized=False)

    vergebene_ids = []

    while True:
        person_id = _eine_person_anlegen(
            tg, chat_id, user_id, registry_path, next_message)
        if person_id is None:
            # Abbruch (FAA-7) oder Eingabe-Strom zu Ende — wir beenden den Aufruf.
            break
        vergebene_ids.append(person_id)

        # FAA-9: »Noch jemand?« — bei nicht-bestätigender Antwort beenden.
        _send(tg, chat_id, ASK_NOCH_JEMAND)
        msg = next_message()
        if msg is None or not confirm.is_confirmation((msg.text or "").strip()):
            break

    if vergebene_ids:
        if len(vergebene_ids) == 1:
            _send(tg, chat_id, DONE_SINGLE % vergebene_ids[0])
        else:
            _send(tg, chat_id, DONE_MULTI % ", ".join(vergebene_ids))
    return FamilieAnlegenResult(vergebene_ids=vergebene_ids, authorized=True)


# ============================================================
#  Anlage genau einer Person — FAA-3 in fester Reihenfolge
# ============================================================

def _eine_person_anlegen(tg, chat_id, user_id, registry_path, next_message):
    """Legt EINE Person an. Liefert die vergebene `id` oder None (Abbruch)."""
    # Bei jedem Personen-Start die Registry frisch lesen — sonst sehen wir die
    # in derselben Schleife frisch angelegte Person nicht für Slug-Kollision
    # (FAA-5) oder Telegram-ID-Duplikat (FAA-10).
    current = registry_mod.load(registry_path)
    settings = _effective_settings(current.settings, registry_path)

    # FAA-3 Schritt 1: Art.
    art = _frage_art(tg, chat_id, next_message)
    if art is None:
        return None

    # Schritt 2: Name.
    name = _frage_name(tg, chat_id, next_message)
    if name is None:
        return None

    # Schritt 3: Foto (optional).
    foto_filename, foto_bytes = _frage_foto(
        tg, chat_id, next_message, settings)
    if foto_filename is False:
        # Abbruch im Foto-Schritt.
        return None

    # FAA-5: Slug aus dem Namen, kollisionsfrei machen.
    person_id = _slug(name, taken=set(p.id for p in current.alle()))
    if foto_filename is not None:
        # FAA-6: Dateiname = <id>.<ext>; die Endung kennt _frage_foto schon.
        foto_filename = "%s.%s" % (person_id, foto_filename)

    # Schritt 4: Ring-Farbe.
    ring = _frage_ring(tg, chat_id, next_message, current)
    if ring is None:
        return None

    # Schritt 5: E-Mail (nur Erwachsene).
    email = None
    if art == registry_mod.KIND_ERWACHSENE:
        email = _frage_email(tg, chat_id, next_message)
        if email is False:
            return None

    # Schritt 6: Telegram-ID (optional, beide Arten).
    telegram_id = _frage_telegram(
        tg, chat_id, user_id, next_message, current, name)
    if telegram_id is False:
        return None

    # FAA-7: Zusammenfassung + Bestätigungswort.
    summary = _zusammenfassung(person_id, name, art, ring, foto_filename,
                                email, telegram_id)
    _send(tg, chat_id, summary)
    bestaetigung = next_message()
    if bestaetigung is None or not confirm.is_confirmation(
            (bestaetigung.text or "").strip()):
        _send(tg, chat_id, CANCELLED)
        return None

    # FAA-6 fortsetzen: das Foto-Binär an den Zielpfad schreiben, BEVOR die
    # Schreib-Schnittstelle aufgerufen wird (FAA-8 letzter Satz: Foto liegt
    # bei FAM-11-Aufruf bereits am Zielpfad).
    if foto_filename is not None and foto_bytes is not None:
        try:
            os.makedirs(settings["foto_verzeichnis"], exist_ok=True)
            foto_zielpfad = os.path.join(
                settings["foto_verzeichnis"], foto_filename)
            with open(foto_zielpfad, "wb") as f:
                f.write(foto_bytes)
        except OSError as e:
            logging.warning("familie_anlegen: Foto konnte nicht abgelegt werden: %s", e)
            _send(tg, chat_id, WRITE_FAILED)
            return None

    # FAA-8: Schreiben ausschliesslich über die Registry-Schreib-Schnittstelle.
    neue_person = registry_mod.Person(
        id=person_id, name=name, ring=ring, art=art,
        foto=foto_filename, email=email, telegram_id=telegram_id)
    current.add_person(neue_person)
    try:
        registry_mod.save(current, registry_path)
    except registry_mod.RegistryError as e:
        logging.warning("familie_anlegen: Schreiben fehlgeschlagen: %s", e)
        # FAA-8: weder Person noch Foto-Datei bleiben zurück.
        if foto_filename is not None:
            try:
                os.remove(os.path.join(settings["foto_verzeichnis"], foto_filename))
            except OSError:
                pass
        _send(tg, chat_id, WRITE_FAILED)
        return None

    return person_id


# ============================================================
#  Einzel-Schritte (FAA-3)
# ============================================================

def _frage_art(tg, chat_id, next_message):
    """FAA-3 Schritt 1: Art — Erwachsene oder Kind."""
    while True:
        _send(tg, chat_id, ASK_ART)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip().lower()
        if text in _ART_ERWACHSEN:
            return registry_mod.KIND_ERWACHSENE
        if text in _ART_KIND:
            return registry_mod.KIND_KINDER
        _send(tg, chat_id, REJECT_KIND)


def _frage_name(tg, chat_id, next_message):
    """FAA-3 Schritt 2: Name — Pflicht, nicht leer."""
    while True:
        _send(tg, chat_id, ASK_NAME)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip()
        if text:
            return text
        _send(tg, chat_id, REJECT_NAME)


def _frage_foto(tg, chat_id, next_message, settings):
    """FAA-3 Schritt 3: Profilfoto — optional.

    Liefert `(ext_or_None, bytes_or_None)`:
      - `(None, None)`  : Aufrufer hat übersprungen.
      - `("jpg"/"png", b"…")` : Foto-Bytes liegen vor, Endung steht fest.
      - `(False, None)` : Aufrufer hat die ganze Anlage abgebrochen.
    """
    max_kante = _as_int(settings["profilbild_max_kante"])
    while True:
        _send(tg, chat_id, ASK_FOTO)
        msg = next_message()
        if msg is None:
            return False, None
        text = (msg.text or "").strip().lower()
        if text in _SKIP_WORDS:
            return None, None

        # Telegram-Foto-Nachricht (FAA-6: immer JPEG).
        if msg.photo_file_id is not None:
            try:
                raw = tg.download_file(msg.photo_file_id)
            except TelegramError as e:
                logging.warning("familie_anlegen: Foto-Download fehlgeschlagen: %s", e)
                _send(tg, chat_id, REJECT_FOTO_GROSS)
                continue
            return "jpg", raw
        if msg.photo_oversize:
            _send(tg, chat_id, REJECT_FOTO_GROSS)
            continue

        # Datei-Anhang.
        if msg.document_file_id is not None:
            mime = (msg.document_mime_type or "").lower()
            if mime not in _EXT_BY_MIME:
                _send(tg, chat_id, REJECT_FOTO_MIME)
                continue
            # FAA-10: Kantenlänge prüfen, wenn der Anhang die Maße mitliefert.
            if msg.document_size_hint is not None and max_kante is not None:
                w, h = msg.document_size_hint
                if max(w, h) > max_kante:
                    _send(tg, chat_id, REJECT_FOTO_GROSS)
                    continue
            try:
                raw = tg.download_file(msg.document_file_id)
            except TelegramError as e:
                logging.warning("familie_anlegen: Anhang-Download fehlgeschlagen: %s", e)
                _send(tg, chat_id, REJECT_FOTO_GROSS)
                continue
            # PNG: Kantenlänge aus dem PNG-Header lesen, falls die Eingabe keine
            # Maße mitlieferte (FAA-10: „längste Kante überschreitet Wert").
            if mime == _MIME_PNG and max_kante is not None:
                masse = _png_dimensions(raw)
                if masse is not None and max(masse) > max_kante:
                    _send(tg, chat_id, REJECT_FOTO_GROSS)
                    continue
            return _EXT_BY_MIME[mime], raw

        # Keine Foto-Form erkannt — Frage wiederholen.
        _send(tg, chat_id, REJECT_FOTO_MIME)


def _frage_ring(tg, chat_id, next_message, current):
    """FAA-3 Schritt 4 / FAA-4: Ring-Farbe mit Vorschlag."""
    vorschlag = _ring_vorschlag(current)
    while True:
        _send(tg, chat_id, ASK_RING % vorschlag)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip().lower()
        if text in _RING_OK or text == vorschlag:
            return vorschlag
        if text in registry_mod.RING_PALETTE:
            return text
        _send(tg, chat_id, REJECT_RING)


def _frage_email(tg, chat_id, next_message):
    """FAA-3 Schritt 5: E-Mail (nur Erwachsene), optional.

    Liefert die E-Mail-Adresse, None (übersprungen) oder False (Abbruch).
    """
    while True:
        _send(tg, chat_id, ASK_EMAIL)
        msg = next_message()
        if msg is None:
            return False
        text = (msg.text or "").strip()
        if text.lower() in _SKIP_WORDS:
            return None
        if _looks_like_email(text):
            return text
        _send(tg, chat_id, REJECT_EMAIL)


def _frage_telegram(tg, chat_id, user_id, next_message, current, name):
    """FAA-3 Schritt 6: Telegram-ID (optional, beide Arten).

    Bietet die eigene User-ID als Default an, wenn der Aufrufer signalisiert,
    dass die anzulegende Person er selbst ist (»ich«). FAA-10: eine bereits
    vergebene Telegram-ID wird abgelehnt.
    """
    # »Ich«-Signal: heuristisch, wenn der erfasste Name mit »ich« oder dem
    # Default-Bot-Setup matched — die Spec ist hier explizit „Implementierungs-
    # Detail". Wir bieten die self-id einfach IMMER als Default an: der
    # Aufrufer kann sie mit »ich« übernehmen oder eine andere Zahl schicken.
    # Falls eine andere Person diese Person über »ich« anlegt, ist das ein
    # gewolltes Komfort-Verhalten.
    while True:
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
                _send(tg, chat_id, REJECT_TELEGRAM)
                continue
        # FAA-10: Doppelung verhindern — eine Telegram-ID = eine Person.
        if any(p.telegram_id == kandidat for p in current.alle()):
            _send(tg, chat_id, REJECT_TELEGRAM_DUP)
            continue
        return kandidat


# ============================================================
#  Helpers
# ============================================================

def _effective_settings(settings, registry_path):
    """FAM-9-Werte aus den Registry-Settings + ENV-Override + Default —
    identisch zum Settings-Lader in `familie/main.py` (geteilte Helper-
    Funktion `effective_setting`).

    Das `foto_verzeichnis` wird über `resolved_foto_verzeichnis` ausgewertet,
    damit ein relativer Wert (Default `fotos`, Settings-Wert, ENV-Override)
    immer **neben der Registry-Datei** landet (FAM-9) — und nicht im CWD
    des Eltern-Chat-Bots, wo der Pi-Live-Test die Fotos versehentlich
    abgelegt hatte."""
    return {
        "foto_verzeichnis": registry_mod.resolved_foto_verzeichnis(
            settings, registry_path),
        "profilbild_max_kante": registry_mod.effective_setting(
            settings.profilbild_max_kante,
            "FAMILIE_PROFILBILD_MAX_KANTE",
            registry_mod.FAM9_DEFAULTS["profilbild_max_kante"]),
    }


def _as_int(value):
    """Wandelt die Max-Kante aus Settings/ENV/Default in int — None bleibt None."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _slug(name, taken):
    """FAA-5: Slug aus dem Namen; kollidierende ids bekommen `-2`, `-3`, …"""
    s = "".join(_UMLAUTE.get(ch, ch) for ch in name).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = s or "person"
    if s not in taken:
        return s
    n = 2
    while True:
        kand = "%s-%d" % (s, n)
        if kand not in taken:
            return kand
        n += 1


def _ring_vorschlag(current):
    """FAA-4: erste freie Palette-Farbe, gray bleibt zuletzt."""
    belegt = set(p.ring for p in current.alle())
    for farbe in registry_mod.RING_PALETTE:  # FAM-4: Reihenfolge der Palette
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


def _zusammenfassung(person_id, name, art, ring, foto, email, telegram_id):
    """FAA-7: Zusammenfassung vor dem Bestätigungswort."""
    art_label = "Erwachsene" if art == registry_mod.KIND_ERWACHSENE else "Kind"
    teile = [
        "Bitte bestätigen (»ok« / »ja«):",
        "• Art: %s" % art_label,
        "• Name: %s" % name,
        "• id: %s" % person_id,
        "• Ring: %s" % ring,
    ]
    if foto:
        teile.append("• Foto: %s" % foto)
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
