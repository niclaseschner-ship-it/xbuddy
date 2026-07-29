"""Gerät anlegen — siehe specs/platform/geraet-anlegen.md (GAA-1…, Refs #106).

»Gerät anlegen« ist eine aufrufbare, **trigger-agnostische** Funktion
(E-GAA-1). Aufgerufen, gibt sie einem berechtigten Familienmitglied im
Privatchat einen frischen **Pairing-Link** — mehr nicht.

RAT-31 E6c (Nic-Setzung 2026-07-29): das Modell ist radikal vereinfacht.
Es gibt **keine geraete-Registry mehr** — kein Geräte-Anlege-Formular
(Typ/Name/Auflösung/OS/Verwendung), kein Registry-Schreiben (GeraeteClient),
keine gespeicherte Geräte-Rollen-Zuordnung. Der Skill mintet nur einen
Pairing-Link (`<origin>/auth/pair?token=<X>`, 15 Minuten, HMAC mit dem
Bot-Token). Die Familie öffnet den Link auf dem Zielgerät, bekommt den
Session-Cookie und **wählt die Rolle** (Kinder-Display vs. Elterngerät)
selbst beim PWA-Installieren — nicht der Server.

RAT-31 E1 (#1470): Der CA-Verteilungs-Schritt (GAA-6) ist unter
Cookie-only-hart (RAT-32) bereits entfallen. Mit E6c entfällt auch der
Registry-Schreib-Schritt (GAA-3.7) — der Pairing-Link ist der einzige
Nach-Trigger-Schritt.

Die Funktion kennt ihren Aufrufer NICHT. Sie nimmt nur die für die
Berechtigung (GAA-2) und die Link-Zustellung nötigen Dinge entgegen: den
Telegram-Kanal, den Privatchat (Chat-ID + User-ID), die ID der gebundenen
Familien-Gruppe (Live-Mitgliedschaftsprüfung, GAA-2) sowie den Bot-Token
und die Origin für den Pairing-Link.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import authz
from telegram import TelegramError

from skills.typing_indicator import fire_typing
from tools.initdata import session_cookie

# ============================================================
#  Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail.
# ============================================================

NOT_AUTHORIZED = ("Geräte koppeln geht nur für Mitglieder der Familien-Gruppe. "
                  "Wende dich bitte an jemanden aus der Gruppe.")
PAIRING_SETUP_FEHLT = (
    "Ich kann gerade keinen Pairing-Link erzeugen — die Pairing-Konfiguration "
    "fehlt. Bitte später noch einmal versuchen.")

# GAA-3.8: Pairing-Anweisung. Zwei Zeilen (Anweisung + Hinweis).
PAIRING_ANWEISUNG_FMT = (
    "Öffne diesen Link **auf dem Gerät, das du koppeln willst**:\n"
    "%s\n(gilt 15 Minuten)\n"
    "Nach dem Öffnen kannst du beim Installieren wählen, ob das Gerät ein "
    "Kinder-Display oder ein Elterngerät wird.")


# ============================================================
#  Ergebnis
# ============================================================

class GeraetAnlegenError(Exception):
    """Anlegen konnte nicht abgeschlossen werden (Aufrufer entscheidet)."""


@dataclass
class GeraetAnlegenResult:
    """Ergebnis-Signal an den Aufrufer (GAA-1).

    `pairing_links` ist die Liste der in diesem Aufruf geminteten Pairing-Links
    — leer, wenn das Mitglied nicht berechtigt war (`authorized=False`) oder
    kein Pairing-Setup vorlag.
    """
    pairing_links: list = field(default_factory=list)
    authorized: bool = True


# ============================================================
#  Die Funktion
# ============================================================

def geraet_anlegen(tg, chat_id, user_id, family_group_chat_id,
                   next_message=None,
                   typing_fn: Callable[[], None] | None = None,
                   pairing_bot_token=None, pairing_origin=None):
    """Mintet einen Pairing-Link und postet ihn im Privatchat (GAA-1).

    `tg`                    — Telegram-Kanal (mit `send_message`,
                              `get_chat_member`).
    `chat_id`               — Privatchat des Aufrufers (GAA-3).
    `user_id`               — Telegram-User-ID des Aufrufers (GAA-2).
    `family_group_chat_id`  — ID der gebundenen Familien-Gruppe (GAA-2).
    `next_message`          — vestigial (RAT-31 E6c: keine Konversation mehr).
                              Bleibt in der Signatur, damit bestehende Aufrufer
                              unberührt bleiben; wird nicht mehr gelesen.
    `typing_fn`             — Optionaler Callable ohne Argumente; wird vor der
                              send_message-Phase aufgerufen (EC-25). Default None
                              → No-op.
    `pairing_bot_token`     — Bot-Token als HMAC-Sign-Key für den Pairing-Token.
                              Fehlt er (oder `pairing_origin`), entfällt der
                              Link-Schritt mit einer Hinweis-Nachricht.
    `pairing_origin`        — Funnel-FQDN-Origin für den Pairing-Link
                              (`<origin>/auth/pair?token=…`).

    Liefert ein `GeraetAnlegenResult`. Schreibt nichts (keine Registry mehr).
    """
    # GAA-2: Berechtigung live über die Familien-Gruppen-Mitgliedschaft.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("geraet_anlegen: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
        fire_typing(typing_fn)
        _send(tg, chat_id, NOT_AUTHORIZED)
        return GeraetAnlegenResult(pairing_links=[], authorized=False)

    # RAT-31 E6c: reines Link-Minten — kein Formular, kein Registry-Write.
    if not pairing_bot_token or not pairing_origin:
        logging.warning(
            "geraet_anlegen: pairing_bot_token/origin fehlt — kein Link geminted")
        fire_typing(typing_fn)
        _send(tg, chat_id, PAIRING_SETUP_FEHLT)
        return GeraetAnlegenResult(pairing_links=[], authorized=True)

    link = baue_pairing_link(pairing_bot_token, pairing_origin)
    fire_typing(typing_fn)
    _send(tg, chat_id, PAIRING_ANWEISUNG_FMT % link)
    return GeraetAnlegenResult(pairing_links=[link], authorized=True)


# ============================================================
#  Helpers
# ============================================================

def baue_pairing_link(bot_token, origin):
    """Signiert einen 15-Minuten-Pairing-Token und baut den Pairing-Link.

    RAT-31 E6c: das Token-Subjekt ist ein frisch generierter, opaquer
    Geräte-Bezeichner (kein Registry-Eintrag, keine Rolle) — es dient nur
    als Session-Subjekt für den Cookie, den `/auth/pair` setzt (auth.md
    AUTH-2.a; das Subjekt wird downstream nur auf Gültigkeit geprüft, nie auf
    eine Rolle). `origin` ist die Funnel-FQDN (PWA + `/auth/pair` auf derselben
    Origin, LE-Cert). Ergebnis: `<origin>/auth/pair?token=<X>`.
    """
    subjekt = "geraet-%s" % uuid.uuid4().hex[:12]
    token = session_cookie.sign_pairing(subjekt, bot_token)
    return "%s/auth/pair?token=%s" % (origin.rstrip("/"), token)


def _send(tg, chat_id, text):
    """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt, aber
    brechen die Funktion nicht ab — analog `familie_anlegen._send`."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logging.warning("geraet_anlegen: Senden an %s fehlgeschlagen: %s",
                        chat_id, e)
