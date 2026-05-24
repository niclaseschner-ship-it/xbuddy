"""Gerät anlegen — siehe specs/platform/geraet-anlegen.md (GAA-1…GAA-8,
Refs #106).

»Gerät anlegen« ist eine aufrufbare, **trigger-agnostische** Funktion
(E-GAA-1) — analog `familie_anlegen.familie_anlegen` (E-FAA-1) und
`ca_verteilung.verteile_ca` (E-CAV-1). Aufgerufen, führt sie ein
Familienmitglied im Privatchat durch die Anlage **eines oder mehrerer**
Geräte und ergänzt sie nach Bestätigungswort (GAA-3.6, `eltern-chat.md`
E-EC-7) atomar über die Schreib-Schnittstelle der Geräte-Registry
(GAA-3.7, `geraete.md` GER-6).

Die Funktion kennt ihren Aufrufer NICHT. Wer sie aufruft — eine
EC-8-Aufgabe (GAA-5), ein späterer Geräte-Onboarding-Flow (OPEN-GAA-C)
oder ein anderer Aufrufer — ist nicht Teil ihres Vertrags. Sie nimmt nur
die für die Anlage nötigen Dinge entgegen: den Telegram-Kanal, den
Privatchat (Chat-ID + User-ID), die ID der gebundenen Familien-Gruppe
(für die Live-Prüfung der Mitgliedschaft, GAA-2 analog EC-2), den Pfad
zur Registry-Datei und eine `next_message()`-Funktion, über die sie die
nächste eingehende Privatchat-Nachricht des Aufrufers abholt. Optional
ein `cav_call_hook` (GAA-6, E-GAA-5) — wenn gesetzt, ruft die Funktion
ihn nach jeder erfolgreich angelegten Geräte-Anlage auf (bei Bestätigung
durch den Aufrufer); ohne Hook entfällt der CA-Verteilungs-Schritt
stillschweigend, damit die Funktion auch ohne CAV-Setup testbar bleibt.
"""

import logging
import os
import re
import sys
from dataclasses import dataclass

import authz
import confirm
from telegram import TelegramError

# Geräte-Registry — Public-API über das Paket geraete/ (GAA-3.7 / GER-6).
_ELTERN_CHAT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_ELTERN_CHAT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
import geraete as geraete_pkg  # noqa: E402


# ============================================================
#  Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail
#  (GAA-3 / GAA-6 / GAA-7 lassen den Wortlaut offen).
# ============================================================

ASK_TYP = ("Was für ein Gerät willst du anlegen? "
           "Schreib einen der Typen: tablet / handy / monitor / pi-display.")
ASK_NAME = ("Wie soll das Gerät heißen? (Anzeigename — z. B. »Tablet Elias«)")
ASK_AUFLOESUNG = ("Welche Auflösung hat der Bildschirm? "
                  "Format: <breite>x<höhe>, z. B. »1280x800«. "
                  "Die Werte findest du in den Anzeige-Einstellungen "
                  "des Geräts.")
ASK_OS = ("Welches Betriebssystem läuft auf dem Gerät? "
          "Schreib eins davon: android / ios / windows / macos / linux.")
ASK_VERWENDUNG = ("Wofür wird das Gerät genutzt? "
                  "V1 legt nur Display-Geräte an — schreib »display« zum "
                  "Bestätigen.")
ASK_NOCH_EIN = "Noch ein Gerät anlegen? Schreib »ja« oder »nein«."
ASK_CA = ("Soll ich dir das XBuddy-Zertifikat fürs neue Gerät jetzt schicken? "
          "Schreib »ja« zum Bestätigen oder »nein«, um es später nachzuholen.")

REJECT_TYP = ("Diesen Typ kenne ich nicht. Bitte einer aus: "
              "tablet / handy / monitor / pi-display.")
REJECT_NAME = "Der Name darf nicht leer sein."
REJECT_AUFLOESUNG = ("Das verstehe ich nicht. Bitte im Format <breite>x<höhe>, "
                     "z. B. »1280x800« (beide Zahlen größer als 0).")
REJECT_OS = ("Dieses Betriebssystem kenne ich nicht. Bitte eins aus: "
             "android / ios / windows / macos / linux.")
REJECT_VERWENDUNG = ("V1 legt nur Display-Geräte an. Bitte »display« "
                     "schreiben (controller folgt später).")
NOT_AUTHORIZED = ("Geräte anlegen geht nur für Mitglieder der Familien-Gruppe. "
                  "Wende dich bitte an jemanden aus der Gruppe.")
WRITE_FAILED = ("Konnte das Gerät nicht speichern — bitte später noch einmal. "
                "Es wurde nichts in der Registry verändert.")
CAV_FAILED = ("Das Gerät ist angelegt, aber das Zertifikat konnte ich gerade "
              "nicht schicken — du kannst es jederzeit über die "
              "Eltern-Chat-Aufgabe nachholen.")
CANCELLED = "Ok, abgebrochen — das Gerät wurde nicht gespeichert."
DONE_SINGLE_FMT = ("Geschafft, %s ist angelegt. Display-URL: %s")
DONE_MULTI_FMT = ("Geschafft — angelegt: %s.")

# V1: einzig zulässiger Verwendungs-Wert (Spec-Schnitt GAA-3.5 / OPEN-GAA-D).
# Wir fragen trotzdem (Quick-Reply mit nur dieser einen Option) — so bleibt
# die Stelle in der Konversation sichtbar, an der später `controller`/`beides`
# dazukommen werden (OPEN-GAA-D), und der Aufrufer erfährt explizit, dass V1
# bewusst nur Display-Geräte anlegt.
_VERWENDUNG_V1 = "display"

# GAA-3.7: V1-Status für ein neu angelegtes Gerät — laut Spec hart „aktiv"
# (OPEN-GER-B führt das manuelle Setzen von `status` ohnehin noch).
_STATUS_V1 = "aktiv"

# GAA-3.3 / GAA-7: erlaubte Trenner zwischen Breite und Höhe. „x", „X" und
# das mathematische „×" — Auflösungs-Schreibweisen kommen aus unterschiedlichen
# Quellen, der Aufrufer soll daran nicht scheitern.
_AUFLOESUNG_RE = re.compile(r"^\s*(\d+)\s*[xX×]\s*(\d+)\s*$")


# ============================================================
#  Eingabe-Protokoll (Test-Doppelung & Live-Adapter haben dieselbe Form,
#  analog FAA-1 / FAA-12)
# ============================================================

@dataclass
class GaaInput:
    """Eine eingehende Privatchat-Nachricht des Aufrufers, GAA-spezifisch
    aufbereitet — schmaler als IncomingMessage (GAA muss z. B. nicht wissen,
    ob die Nachricht den Bot @-erwähnt).
    """
    text: str = ""


# ============================================================
#  Ergebnis
# ============================================================

class GeraetAnlegenError(Exception):
    """Anlegen konnte nicht abgeschlossen werden (Aufrufer entscheidet)."""


@dataclass
class GeraetAnlegenResult:
    """Ergebnis-Signal an den Aufrufer (GAA-1).

    `vergebene_display_ids` ist die Liste der `display_id`s der in diesem
    Aufruf angelegten Geräte — leere Liste, wenn der Aufrufer schon die erste
    Anlage abgebrochen hat (GAA-3.6) oder das Mitglied nicht berechtigt war
    (GAA-2). `authorized` unterscheidet diesen letzteren Fall.
    """
    vergebene_display_ids: list
    authorized: bool = True


# ============================================================
#  Die Funktion
# ============================================================

def geraet_anlegen(tg, chat_id, user_id, family_group_chat_id,
                   registry_path, next_message,
                   cav_call_hook=None, display_url_origin=None):
    """Legt ein oder mehrere Geräte an (GAA-1).

    `tg`                    — Telegram-Kanal (mit `send_message`,
                              `get_chat_member`).
    `chat_id`               — Privatchat des Aufrufers (GAA-3).
    `user_id`               — Telegram-User-ID des Aufrufers (GAA-2).
    `family_group_chat_id`  — ID der gebundenen Familien-Gruppe (GAA-2).
    `registry_path`         — Pfad zur geraete.json (Schreiben über GER-6).
    `next_message`          — Callable, das die nächste eingehende
                              Privatchat-Nachricht des Aufrufers liefert
                              (GaaInput). Liefert `None`, gilt die Anlage als
                              abgebrochen.
    `cav_call_hook`         — optional, Callable für GAA-6. Wird nach jeder
                              erfolgreich angelegten Geräte-Anlage und einer
                              Bestätigung durch den Aufrufer aufgerufen mit
                              `cav_call_hook(os, private_chat_id, user_id)`.
                              Ohne Hook entfällt der CA-Schritt stillschweigend
                              (z. B. in Tests ohne CAV-Setup) — die Funktion
                              bleibt trigger- und CAV-agnostisch (E-GAA-5).
    `display_url_origin`    — optional, Origin-URL (z. B. „https://hub.local")
                              für die Display-URL-Rückgabe (GAA-3.7). Ohne
                              Wert liefert die Funktion nur den Pfad
                              `/display/<display_id>` (DC-1) — der Aufrufer
                              erfährt die `display_id`, kann sie aber selbst
                              an seinen Origin hängen.

    Liefert ein `GeraetAnlegenResult`. Schreibt ausschließlich über die
    Registry-Schreib-Schnittstelle (GAA-3.7, GER-6).
    """
    # GAA-2: Berechtigung live über die Familien-Gruppen-Mitgliedschaft.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("geraet_anlegen: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
        _send(tg, chat_id, NOT_AUTHORIZED)
        return GeraetAnlegenResult(vergebene_display_ids=[], authorized=False)

    vergebene = []

    while True:
        outcome = _ein_geraet_anlegen(
            tg, chat_id, registry_path, next_message)
        if outcome.display_id is not None:
            vergebene.append(outcome.display_id)
            _antworte_display_url(tg, chat_id, outcome.display_id,
                                  display_url_origin)
            # GAA-6: optional CA-Verteilung anstoßen — erst nach erfolgreicher
            # Anlage, vor der Schleifen-Frage. Ablehnung oder CAV-Fehler bricht
            # die Schleife nicht ab.
            _frage_und_rufe_cav(tg, chat_id, user_id, outcome.os_wert,
                                next_message, cav_call_hook)
        elif not outcome.should_loop:
            # Konversations-Abbruch (GAA-3.6 ohne Bestätigung) oder
            # Eingabe-Strom zu Ende — die Funktion endet ohne Schleifen-Frage.
            break
        # outcome.display_id is None und should_loop=True: Disk-Fehler
        # (GAA-7 letzter Punkt) — Schleifen-Frage trotzdem stellen.

        # GAA-4: »Noch ein Gerät?« — bei nicht-bestätigender Antwort beenden.
        _send(tg, chat_id, ASK_NOCH_EIN)
        msg = next_message()
        if msg is None or not confirm.is_confirmation((msg.text or "").strip()):
            break

    if vergebene:
        if len(vergebene) > 1:
            _send(tg, chat_id, DONE_MULTI_FMT % ", ".join(vergebene))
    return GeraetAnlegenResult(vergebene_display_ids=vergebene, authorized=True)


# ============================================================
#  Anlage genau eines Geräts — GAA-3 in fester Reihenfolge
# ============================================================

@dataclass
class _Outcome:
    """Ausgang eines Einzel-Geräte-Versuchs.

    `display_id`/`os_wert` gesetzt → Erfolg (GAA-3.7).
    `display_id` None und `should_loop` True → Disk-Schreibfehler (GAA-7
      letzter Punkt) — Schleife (GAA-4) fragt trotzdem „noch ein Gerät?".
    `display_id` None und `should_loop` False → Konversations-Abbruch
      (GAA-3.6 ohne Bestätigung oder Eingabe-Strom zu Ende) — die Funktion
      endet ohne Schleifen-Frage.
    """
    display_id: object = None
    os_wert: object = None
    should_loop: bool = False


def _ein_geraet_anlegen(tg, chat_id, registry_path, next_message):
    """Legt EIN Gerät an. Liefert ein `_Outcome`."""
    # Bei jedem Geräte-Start die Registry frisch lesen — sonst sehen wir das
    # in derselben Schleife frisch angelegte Gerät nicht für die laufende
    # `display_id`-Vergabe (GER-7) oder Schreib-Konflikte.
    try:
        registry = geraete_pkg.load(registry_path)
    except geraete_pkg.RegistryError as e:
        # Registry-Datei selbst ist kaputt — kein guter Ausgangspunkt für
        # weitere Anlagen. Schleife nicht fortsetzen.
        logging.warning("geraet_anlegen: Registry-Datei nicht lesbar: %s", e)
        _send(tg, chat_id, WRITE_FAILED)
        return _Outcome(should_loop=False)

    # GAA-3.1: Typ.
    typ = _frage_typ(tg, chat_id, next_message)
    if typ is None:
        return _Outcome(should_loop=False)

    # GAA-3.2: Anzeigename.
    name = _frage_name(tg, chat_id, next_message)
    if name is None:
        return _Outcome(should_loop=False)

    # GAA-3.3: Auflösung.
    aufloesung = _frage_aufloesung(tg, chat_id, next_message)
    if aufloesung is None:
        return _Outcome(should_loop=False)

    # GAA-3.4: OS.
    os_wert = _frage_os(tg, chat_id, next_message)
    if os_wert is None:
        return _Outcome(should_loop=False)

    # GAA-3.5: Verwendung — V1 hart `display`, aber wir holen die Bestätigung
    # über einen Quick-Reply-Schritt mit dieser einzigen Option.
    verwendung = _frage_verwendung(tg, chat_id, next_message)
    if verwendung is None:
        return _Outcome(should_loop=False)

    # GAA-3.6: Zusammenfassung + Bestätigungswort.
    summary = _zusammenfassung(typ, name, aufloesung, os_wert, verwendung)
    _send(tg, chat_id, summary)
    bestaetigung = next_message()
    if bestaetigung is None or not confirm.is_confirmation(
            (bestaetigung.text or "").strip()):
        _send(tg, chat_id, CANCELLED)
        return _Outcome(should_loop=False)

    # GAA-3.7: kollisionsfreie `display_id` (GER-7) + atomares Schreiben
    # ausschließlich über die Registry-Schreib-Schnittstelle (GER-6).
    try:
        display_id = geraete_pkg.neue_id(registry, typ, name)
    except (geraete_pkg.RegistryError, ValueError) as e:
        # Disk-/Schema-Fehler bei der ID-Vergabe — gemäß GAA-7 letzter Punkt
        # ist das ein Disk-Schreibfehler-äquivalenter Misserfolg: die Schleife
        # darf weitergehen.
        logging.warning("geraet_anlegen: id-Vergabe abgelehnt: %s", e)
        _send(tg, chat_id, WRITE_FAILED)
        return _Outcome(should_loop=True)

    geraet = geraete_pkg.Geraet(
        id=display_id, typ=typ, name=name,
        aufloesung=aufloesung, os=os_wert,
        verwendung=verwendung, status=_STATUS_V1)
    registry.add(geraet)
    try:
        geraete_pkg.save(registry, registry_path)
    except geraete_pkg.RegistryError as e:
        # GAA-7 letzter Punkt: Disk-Schreibfehler — Misserfolg signalisieren,
        # nichts in geraete.json mutieren (save ist atomar, GER-6), aber
        # die Schleife (GAA-4) fragt trotzdem „noch ein Gerät?".
        logging.warning("geraet_anlegen: Schreiben fehlgeschlagen: %s", e)
        _send(tg, chat_id, WRITE_FAILED)
        return _Outcome(should_loop=True)

    return _Outcome(display_id=display_id, os_wert=os_wert, should_loop=True)


# ============================================================
#  Einzel-Schritte (GAA-3.1..3.5)
# ============================================================

def _frage_typ(tg, chat_id, next_message):
    """GAA-3.1: Typ — einer aus GER-2."""
    while True:
        _send(tg, chat_id, ASK_TYP)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip().lower()
        if text in geraete_pkg.TYPEN:
            return text
        _send(tg, chat_id, REJECT_TYP)


def _frage_name(tg, chat_id, next_message):
    """GAA-3.2: Anzeigename — Pflicht, nicht leer."""
    while True:
        _send(tg, chat_id, ASK_NAME)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip()
        if text:
            return text
        _send(tg, chat_id, REJECT_NAME)


def _frage_aufloesung(tg, chat_id, next_message):
    """GAA-3.3: Auflösung als Freitext <int>x<int>."""
    while True:
        _send(tg, chat_id, ASK_AUFLOESUNG)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip()
        m = _AUFLOESUNG_RE.match(text)
        if m is not None:
            w = int(m.group(1))
            h = int(m.group(2))
            if w > 0 and h > 0:
                return {"w": w, "h": h}
        _send(tg, chat_id, REJECT_AUFLOESUNG)


def _frage_os(tg, chat_id, next_message):
    """GAA-3.4: OS — einer aus android/ios/windows/macos/linux.

    `unbekannt` aus GER-3 ist V1 kein Konversations-Ergebnis (GAA-3.4) —
    wir akzeptieren nur die fünf bekannten Werte.
    """
    # OS_WERTE aus der Registry enthält auch `unbekannt`; wir filtern ihn raus.
    erlaubt = tuple(w for w in geraete_pkg.OS_WERTE if w != "unbekannt")
    while True:
        _send(tg, chat_id, ASK_OS)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip().lower()
        if text in erlaubt:
            return text
        _send(tg, chat_id, REJECT_OS)


def _frage_verwendung(tg, chat_id, next_message):
    """GAA-3.5: Verwendung — V1 nur `display` (Spec-Schnitt / OPEN-GAA-D).

    Quick-Reply mit nur einer Option: nur „display" wird akzeptiert.
    `controller` / `beides` werden abgelehnt — bewusst, V1-Schnitt.
    """
    while True:
        _send(tg, chat_id, ASK_VERWENDUNG)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip().lower()
        if text == _VERWENDUNG_V1:
            return _VERWENDUNG_V1
        _send(tg, chat_id, REJECT_VERWENDUNG)


# ============================================================
#  GAA-6 — CA-Verteilung optional anstoßen
# ============================================================

def _frage_und_rufe_cav(tg, chat_id, user_id, os_wert,
                        next_message, cav_call_hook):
    """GAA-6: bietet die CA-Verteilung an und ruft den Hook bei Bestätigung.

    Ohne Hook (Tests ohne CAV-Setup) entfällt der ganze Schritt stillschweigend
    — keine Frage, keine Aktion. Die Funktion bleibt CAV-agnostisch (E-GAA-5).

    Lehnt der Aufrufer ab oder wirft der Hook, schreibt die Funktion das in
    den Privatchat und kehrt zurück; das angelegte Gerät bleibt unberührt
    (GAA-6 letzter Absatz / GAA-7: CAV-Fehler bricht die Schleife nicht ab).
    """
    if cav_call_hook is None:
        return
    _send(tg, chat_id, ASK_CA)
    msg = next_message()
    if msg is None or not confirm.is_confirmation((msg.text or "").strip()):
        return
    try:
        cav_call_hook(os_wert, chat_id, user_id)
    except Exception as e:  # noqa: BLE001 — CAV-Fehler isoliert melden
        logging.warning("geraet_anlegen: CAV-Aufruf fehlgeschlagen: %s", e)
        _send(tg, chat_id, CAV_FAILED)


# ============================================================
#  Helpers
# ============================================================

def _antworte_display_url(tg, chat_id, display_id, origin):
    """GAA-3.7 zweiter Teil: Display-URL zurück an den Aufrufer."""
    if origin:
        url = "%s/display/%s" % (origin.rstrip("/"), display_id)
    else:
        url = "/display/%s" % display_id
    _send(tg, chat_id, DONE_SINGLE_FMT % (display_id, url))


def _zusammenfassung(typ, name, aufloesung, os_wert, verwendung):
    """GAA-3.6: Zusammenfassung vor dem Bestätigungswort."""
    teile = [
        "Bitte bestätigen (»ok« / »ja«):",
        "• Typ: %s" % typ,
        "• Name: %s" % name,
        "• Auflösung: %dx%d" % (aufloesung["w"], aufloesung["h"]),
        "• OS: %s" % os_wert,
        "• Verwendung: %s (V1)" % verwendung,
        "• Status: %s" % _STATUS_V1,
    ]
    return "\n".join(teile)


def _send(tg, chat_id, text):
    """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt, aber
    brechen die Funktion nicht ab — analog `familie_anlegen._send`."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logging.warning("geraet_anlegen: Senden an %s fehlgeschlagen: %s",
                        chat_id, e)
