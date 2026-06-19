"""Anbieter wechseln — siehe specs/platform/eltern-chat-onboarding.md
(ONB-11, ONB-12, ONB-13, E-ONB-7, Refs #639, #663).

»Anbieter wechseln« ist eine aufrufbare, **trigger-agnostische** Funktion
(analog `familie_anlegen.familie_anlegen` E-FAA-1). Aufgerufen, führt sie ein
Familienmitglied im Telegram-Privatchat durch den KI-Anbieter-Wechsel:
Anbieter-Wahl → ggf. Key-Eingabe → ggf. Validierungs-Ping → atomares
Schreiben im Zugangsdaten-Speicher → Bestätigung in der Familien-Gruppe.

Die Funktion kennt ihren Aufrufer nicht. Sie nimmt nur die nötigen Dinge
entgegen: Telegram-Kanal, Privatchat-ID, User-ID, Familien-Gruppen-ID,
Zugangsdaten-Speicher, eine `next_message()`-Callable und Getter für den
aktuell konfigurierten Anbieter.

**Kein LLM im Wechsel-Akt (E-ONB-7):** der Wechsel-Flow läuft vollständig
deterministisch — hart-codierte Nachrichten, Validierungs-Ping als
Abschluss-Gate, kein propose→confirm-Pattern (ONB-11-Spec).

**ONB-11 V2 — Pfad A / Pfad B (T663 Welle A):** der ZD-Speicher hält pro
Vendor einen eigenen Slot (`eltern-chat-claude-api-key`,
`eltern-chat-mistral-api-key`). Beim Wechsel entscheidet die Funktion nach der
Anbieter-Wahl per truthy-Check auf den vendor-spezifischen Slot:

  * **Pfad A — vorbefüllter vendor-Slot:** liegt für den gewählten Vendor
    bereits ein Key, wird KEIN Re-Key abgefragt und KEIN Validierungs-Ping
    geschickt. Nur der `provider_name`-Slot wird umgeschaltet — der alte
    vendor-Slot bleibt unverändert (Lookup-Modell, ONB-11 V2).
  * **Pfad B — neuer Vendor:** kein truthy Wert im vendor-Slot → Key-Eingabe,
    Validierungs-Ping, anschließend atomares `set_multi({vendor-Slot: key,
    provider_name: vendor})`. Beide Werte landen in genau einem
    Schreibvorgang (DCOMP-4) — Race-Fenster aus #639 ist geschlossen.

**Atomares Ersetzen (ONB-12) — V2:** Pfad B nutzt `zd.set_multi(...)` mit
beiden Slots als einzelnen atomaren `_write`-Vorgang. Scheitert er, bleibt
der Speicher byte-gleich (DCOMP-4). Das ist der Fix der ONB-12-V1-Race-Lücke,
die in #639 als bekannter Schwachpunkt markiert war.

**ONB-8-Schutz:** Keys werden zu keinem Zeitpunkt im Klartext in
Bestätigungen, Fehlermeldungen oder Logs gespiegelt (ZD-6).
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

import authz
from model import GenerationRequest, Message, ProviderError, TextBlock
from onboarding_store import (
    ZD_NAME_PROVIDER_NAME,
    zd_name_provider_api_key,
)
from providers import get_provider
from telegram import TelegramError

from skills.typing_indicator import fire_typing
from tools.zugangsdaten import StoreError

# ============================================================
#  ZD-Schlüssel-Namen (ONB-12 / ZD-2)
# ============================================================
#
# `ZD_NAME_PROVIDER_API_KEY` (Single-Slot, Welle-A-Fallback) und
# `ZD_NAME_PROVIDER_NAME` (persistenter Anbieter-Name nach Wechsel) leben
# zentral in `onboarding_store` — Watchdog B4 / CLAUDE.md §6. Der Skill
# importiert sie hier nur, statt sie als String-Literale zu wiederholen.
#
# T663 Welle A: der Single-Slot bleibt als Fallback (read-both in
# `OnboardingStore.load`), wird beim Wechsel aber NICHT mehr beschrieben —
# der Skill schreibt in vendor-spezifische Slots
# (`eltern-chat-<vendor>-api-key`, Brand-Vendor via `vendor_slug_for_adapter`),
# zusammen mit `ZD_NAME_PROVIDER_NAME` in einem atomaren `set_multi`-Aufruf.
# Welle B entfernt den Single-Slot.

# ============================================================
#  Verfügbare Anbieter (ONB-10 / ONB-11)
# ============================================================

# Zentrale Liste der verfügbaren Anbieter — analog der Provider-Factory in
# `providers/__init__.py`. Je Eintrag: interner Name (wie `get_provider` ihn
# kennt) und Anzeige-Name für den Dialog.
ANBIETER_LISTE = [
    {"name": "claude",  "anzeige": "Claude (Anthropic)"},
    {"name": "mistral", "anzeige": "Mistral"},
]

# Interne Namen (für schnelle Lookup-Prüfung).
_ANBIETER_NAMEN = {a["name"] for a in ANBIETER_LISTE}


# ============================================================
#  Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail (E-ONB-7)
# ============================================================

# ONB-11 Schritt 1: Anbieter-Wahl.
ASK_ANBIETER = (
    "Welchen KI-Anbieter möchtest du verwenden? Verfügbar sind:\n\n"
    "%s\n\n"
    "Schreib den Namen (z. B. »claude« oder »mistral«).")

REJECT_ANBIETER = (
    "Das habe ich nicht erkannt. Bitte schreib einen der Anbieter-Namen "
    "aus der Liste oben.")

# ONB-11: Same-Provider-Quittung — wenn der gewählte Anbieter bereits der
# aktive ist. KEIN Re-Key, KEIN Schreiben (ONB-11-Spec).
SAME_PROVIDER = (
    "Du nutzt diesen Anbieter bereits — nichts geändert.")

# ONB-11 Schritt 2: Key-Eingabe.
ASK_KEY = (
    "Schick mir bitte den API-Key für %s als Nachricht — nur im Privatchat, "
    "nie in der Gruppe. Ich prüfe ihn sofort.")

# ONB-12: Validierungs-Ping fehlgeschlagen.
KEY_INVALID = (
    "Hm — mit diesem Key komme ich bei %s nicht durch (ungültig oder der "
    "Anbieter ist gerade nicht erreichbar). Bitte prüf ihn und schick ihn "
    "mir noch einmal. (Dein bisheriger Anbieter läuft unverändert weiter.)")

# ONB-12: Schreib-Fehler.
WRITE_FAILED = (
    "Der Key wurde validiert, aber ich konnte den Speicher nicht "
    "aktualisieren — bitte später noch einmal versuchen. "
    "Dein bisheriger Anbieter läuft unverändert weiter.")

# ONB-11 Schritt 5: Privatchat-Abschluss.
DONE_PRIVAT = (
    "Anbieter-Wechsel abgeschlossen — der neue Key ist gespeichert. "
    "Die Familie bekommt gleich eine Benachrichtigung.")

# ONB-11 Schritt 5: Bestätigung in der Familien-Gruppe (kein Key im Text).
DONE_GRUPPE = "KI-Anbieter ist jetzt %s."

# EC-2 / ONB-11: nicht berechtigt.
NOT_AUTHORIZED = (
    "Anbieter wechseln geht nur für Mitglieder der Familien-Gruppe. "
    "Wende dich bitte an jemanden aus der Gruppe.")

# ONB-3: Heuristik für eine Key-Eingabe — lang, keine Leerzeichen.
_MIN_KEY_LENGTH = 20

# Minimal-Ping für den Validierungs-Aufruf (ONB-4).
_VALIDATION_SYSTEM = "Antworte mit einem einzigen Wort."
_VALIDATION_PING = "ping"


# ============================================================
#  Eingabe-Protokoll
# ============================================================

@dataclass
class AvbInput:
    """Eine eingehende Privatchat-Nachricht — AVB-spezifisch aufbereitet.

    Schlanker als IncomingMessage (nur Text wird benötigt).
    """
    text: str = ""


# ============================================================
#  Ergebnis-Signal
# ============================================================

ERGEBNIS_GEWECHSELT = "gewechselt"
ERGEBNIS_UNPETRAENDERT = "unpetraendert"   # same-provider oder Abbruch
ERGEBNIS_ABGELEHNT = "abgelehnt"


@dataclass
class AnbieterWechselnResult:
    """Ergebnis-Signal an den Aufrufer (ONB-11).

    `ergebnis` ist einer der ERGEBNIS_*-Werte. `neuer_anbieter` ist der
    Name des neuen Anbieters (nur wenn `ergebnis == ERGEBNIS_GEWECHSELT`).
    """
    ergebnis: str = ERGEBNIS_UNPETRAENDERT
    neuer_anbieter: str = ""


# ============================================================
#  Die Funktion (ONB-11)
# ============================================================

def anbieter_wechseln(tg, chat_id, user_id, family_group_chat_id,
                      zd, next_message,
                      current_provider_name,
                      typing_fn: Callable[[], None] | None = None,
                      _validate=None):
    """Wechselt den KI-Anbieter der Instanz im Privatchat (ONB-11).

    `tg`                    — Telegram-Kanal (mit `send_message`,
                              `get_chat_member`).
    `chat_id`               — Privatchat des Aufrufers.
    `user_id`               — Telegram-User-ID des Aufrufers (EC-2).
    `family_group_chat_id`  — ID der Familien-Gruppe (EC-2 Live-Berechtigung
                              und Schritt-5-Bestätigung).
    `zd`                    — Zugangsdaten-Speicher (`Zugangsdaten`-Instanz,
                              ZD-5). Wird atomar geschrieben (ONB-12).
    `next_message`          — Callable, das den nächsten `AvbInput` liefert.
                              Liefert `None` → Abbruch (Timeout).
    `current_provider_name` — Name des aktuell aktiven Anbieters (für die
                              Same-Provider-Quittung, ONB-11).
    `typing_fn`             — Optionaler Callable (EC-25, Best-Effort).
    `_validate`             — Test-Naht: Callable `(name, key) -> True/False`.
                              Default None → echter Validierungs-Ping.

    Liefert ein `AnbieterWechselnResult`.
    """
    if _validate is None:
        _validate = _do_validate

    # EC-2: Live-Berechtigung gegen die Familien-Gruppe.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("anbieter_wechseln: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
        fire_typing(typing_fn)
        _send(tg, chat_id, NOT_AUTHORIZED)
        return AnbieterWechselnResult(ergebnis=ERGEBNIS_ABGELEHNT)

    # ONB-11 Schritt 1: Anbieter-Wahl.
    anbieter_zeilen = "\n".join(
        "• %s (%s)" % (a["anzeige"], a["name"]) for a in ANBIETER_LISTE)
    neuer_name = None
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_ANBIETER % anbieter_zeilen)
        msg = next_message()
        if msg is None:
            return AnbieterWechselnResult(ergebnis=ERGEBNIS_UNPETRAENDERT)
        text = (msg.text or "").strip().lower()
        if text in _ANBIETER_NAMEN:
            neuer_name = text
            break
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_ANBIETER)

    # ONB-11: Same-Provider-Quittung — kein Re-Key, kein Schreiben.
    if neuer_name == current_provider_name:
        fire_typing(typing_fn)
        _send(tg, chat_id, SAME_PROVIDER)
        return AnbieterWechselnResult(ergebnis=ERGEBNIS_UNPETRAENDERT)

    anzeige = _anzeige(neuer_name)
    vendor_slot = zd_name_provider_api_key(neuer_name)

    # ONB-11 V2 Pfad-A-Wahl (T663 Welle A): liegt für den gewählten Vendor
    # bereits ein truthy Key im vendor-Slot, springen wir die Re-Key-Schleife.
    # Nur der provider_name wird umgeschaltet — der alte vendor-Slot bleibt
    # unverändert (Lookup-Modell). Truthy-Check (R8): leere Strings zählen
    # als nicht gesetzt und triggern Pfad B.
    if zd.get(vendor_slot):
        # Pfad A: kein Validierungs-Ping (SD5), kein Re-Key.
        try:
            zd.set_multi({ZD_NAME_PROVIDER_NAME: neuer_name})
        except StoreError as e:
            logging.error(
                "anbieter_wechseln: ZD-Schreibvorgang (Pfad A) fehlgeschlagen "
                "(%s) — alter Eintrag bleibt", e)
            fire_typing(typing_fn)
            _send(tg, chat_id, WRITE_FAILED)
            return AnbieterWechselnResult(ergebnis=ERGEBNIS_UNPETRAENDERT)

        # ONB-11 Schritt 5a: Privatchat-Quittung.
        fire_typing(typing_fn)
        _send(tg, chat_id, DONE_PRIVAT)
        # ONB-11 Schritt 5b: Bestätigung in der Familien-Gruppe.
        _send(tg, family_group_chat_id, DONE_GRUPPE % anzeige)
        return AnbieterWechselnResult(
            ergebnis=ERGEBNIS_GEWECHSELT, neuer_anbieter=neuer_name)

    # ONB-11 Pfad B Schritt 2 + 3: Key-Eingabe + Validierungs-Ping.
    # Schleife: bei ungültigem Key erneut fragen.
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_KEY % anzeige)
        msg = next_message()
        if msg is None:
            return AnbieterWechselnResult(ergebnis=ERGEBNIS_UNPETRAENDERT)
        key = (msg.text or "").strip()
        if len(key) < _MIN_KEY_LENGTH or " " in key:
            # Heuristik: zu kurz oder enthält Leerzeichen → kein Key.
            fire_typing(typing_fn)
            _send(tg, chat_id, KEY_INVALID % anzeige)
            continue

        # ONB-11 Schritt 3: Validierungs-Ping gegen den NEUEN Anbieter (AC5).
        # Nur bei Erfolg → Schritt 4 (atomares Ersetzen).
        if not _validate(neuer_name, key):
            # ZD-6: Key nie im Log.
            logging.info("anbieter_wechseln: Validierungs-Ping fuer %s fehlgeschlagen "
                         "— Key nicht gespeichert", neuer_name)
            fire_typing(typing_fn)
            _send(tg, chat_id, KEY_INVALID % anzeige)
            continue

        # ONB-11 Schritt 4: atomares Schreiben in den ZD-Speicher (ONB-12 V2).
        # `set_multi` schreibt beide Werte in EINEM `_write`-Vorgang
        # (DCOMP-4): vendor-Slot (eltern-chat-<vendor>-api-key) und
        # provider-name. Scheitert der Schreibvorgang, bleibt die alte Datei
        # byte-gleich — Race-Fenster aus #639/V1 ist geschlossen (T663 Welle A).
        try:
            zd.set_multi({
                vendor_slot: key,
                ZD_NAME_PROVIDER_NAME: neuer_name,
            })
        except StoreError as e:
            logging.error("anbieter_wechseln: ZD-Schreibvorgang fehlgeschlagen (%s) "
                          "— alter Eintrag bleibt", e)
            fire_typing(typing_fn)
            _send(tg, chat_id, WRITE_FAILED)
            return AnbieterWechselnResult(ergebnis=ERGEBNIS_UNPETRAENDERT)

        break   # Erfolg — Schleife verlassen

    # ONB-11 Schritt 5a: Privatchat-Quittung.
    fire_typing(typing_fn)
    _send(tg, chat_id, DONE_PRIVAT)

    # ONB-11 Schritt 5b: Bestätigung in der Familien-Gruppe (EC-2-Kreis).
    # Kein Key im Text (ONB-8).
    _send(tg, family_group_chat_id, DONE_GRUPPE % anzeige)

    return AnbieterWechselnResult(
        ergebnis=ERGEBNIS_GEWECHSELT, neuer_anbieter=neuer_name)


# ============================================================
#  Validierungs-Ping (ONB-11 Schritt 3 / ONB-4-Analogie)
# ============================================================

def _do_validate(provider_name, api_key):
    """Validierungs-Ping gegen den neuen Anbieter (ONB-11 Schritt 3).

    Nutzt den Adapter des NEUEN Anbieters (`providers.get_provider`, AC5).
    Gibt True zurück bei erfolgreichem Ping, False bei `ProviderError` oder
    `ValueError` (unbekannter Anbieter). Key wird nie ins Log gespiegelt
    (ZD-6 / ONB-8).
    """
    try:
        provider = get_provider(provider_name, api_key)
        provider.generate(GenerationRequest(
            system=_VALIDATION_SYSTEM,
            messages=[Message(role="user",
                              blocks=[TextBlock(text=_VALIDATION_PING)])],
            task_defs=[]))
        return True
    except ProviderError as e:
        logging.info("anbieter_wechseln: Validierungs-Ping fehlgeschlagen (%s)", e)
        return False
    except ValueError as e:
        logging.warning("anbieter_wechseln: unbekannter Anbieter (%s)", e)
        return False
    except Exception as e:
        logging.warning("anbieter_wechseln: Validierungs-Ping Ausnahme (%s)", e)
        return False


# ============================================================
#  Helpers
# ============================================================

def _anzeige(provider_name):
    """Anzeige-Name zum internen Anbieter-Namen."""
    for a in ANBIETER_LISTE:
        if a["name"] == provider_name:
            return a["anzeige"]
    return provider_name


def _send(tg, chat_id, text):
    """Sendet eine Nachricht; Telegram-Fehler werden geloggt, aber brechen
    die Funktion nicht ab — analog `familie_anlegen._send`."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logging.warning("anbieter_wechseln: Senden an %s fehlgeschlagen: %s",
                        chat_id, e)
