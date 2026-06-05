"""Panel anlegen — siehe specs/platform/panel-anlegen.md (PAA-1…PAA-8,
Refs #183/#138/#141).

»Panel anlegen« ist eine aufrufbare, **trigger-agnostische** Funktion
(E-PAA-1) — das exakte Geschwister von `geraet_anlegen.geraet_anlegen`
(GAA-Pattern), nur mit der **Panel-Registry** statt der Geräte-Registry als
Schreibziel. Aufgerufen, führt sie ein Familienmitglied im Privatchat durch
die Anlage **einer** Panel-Instanz (PAA: V1 = eine Instanz je Aufruf, anders
als GAA-4) und ergänzt sie nach Bestätigungswort (PAA-3.4, `eltern-chat.md`
E-EC-7) über die HTTP-Schreib-Schnittstelle der Panel-Registry (PAA-3.5,
`panel-registry.md` PREG-15).

Die Funktion kennt ihren Aufrufer NICHT (E-PAA-1). Sie nimmt nur die für die
Anlage nötigen Dinge entgegen: den Telegram-Kanal, den Privatchat (Chat-ID +
User-ID), die ID der gebundenen Familien-Gruppe (für die Live-Prüfung der
Mitgliedschaft, PAA-2 analog EC-2), den `PanelClient` (HTTP-Schreib-Naht zur
Panel-Registry, PREG-15), den `GeraeteDisplayClient` (HTTP-Lese-Naht für die
Display-Auswahl, GER-13) und eine `next_message()`-Funktion, über die sie die
nächste eingehende Privatchat-Nachricht des Aufrufers abholt.

PAA-4: Der Skill sendet **keine** `config`-Identität — der Server leitet
`source_id`/`display_id`/`router_url` beim POST ab (PREG-15). Der Skill liefert
nur `{slug, display_id, tiles}`.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

import authz
import confirm
from telegram import TelegramError

from skills.panel_client import GeraeteReadError, PanelClientError
from skills.typing_indicator import fire_typing

# ============================================================
#  Feste App-Kandidatenliste (PAA-3.3, OPEN-PAA-B → feste Liste)
# ============================================================

# V1: hart-codierte, kuratierte Liste verfügbarer Apps zur nummerierten Auswahl
# (OPEN-PAA-B-Entscheid Nic 2026-06-03 — keine freie Slug-Nennung, Tippfehler →
# tote Kachel ausgeschlossen). Je Eintrag die PANEL-3-Pflichtfelder einer
# Kachel (`app`, `view`, `label`, `icons`, `sichtbar`; `key` wird beim Bau aus
# `app` abgeleitet; `query` wird gesetzt, wo eine Ansicht/Stufe nötig ist,
# z. B. die Kleinkind-Stufe des Plans über `?ansicht=klein`, PLAN-3). Der echte
# App-Discovery-Mechanismus, der diese Liste später ablöst, ist als #325
# erfasst (gekoppelt an #296). Datenstruktur, kein Vorrat-Discovery (CLAUDE.md
# §6): nur die heute existierenden Apps (Wetter; Plan in zwei Stufen).
@dataclass(frozen=True)
class _AppKandidat:
    """Ein wählbarer App-Kandidat für die PAA-3.3-Kachel-Auswahl."""
    app: str
    view: str
    label: str
    icons: tuple
    name: str   # Anzeigename in der Auswahl-Liste
    query: dict = None   # optionale flache Query-Parameter (PANEL-7), z. B. {"ansicht": "klein"}


# Reihenfolge = Anzeige-Reihenfolge der nummerierten Auswahl.
# ARASAAC-IDs: 24721=Wetter/Klima, 32488=Kalender (#135-Seed), 2484=Kind-Marker.
APP_KANDIDATEN = (
    _AppKandidat(app="wetter", view="heute", label="Wetter",
                 icons=("arasaac/24721.png",), name="Wetter (heute)"),
    _AppKandidat(app="plan", view="woche", label="Wochenplan",
                 icons=("arasaac/32488.png",), name="Plan (Woche) — Lese-Kind"),
    _AppKandidat(app="plan", view="woche", label="Wochenplan (klein)",
                 icons=("arasaac/32488.png", "arasaac/2484.png"),
                 name="Plan (Woche) — Kleinkind", query={"ansicht": "klein"}),
)


def _tile_aus_kandidat(kandidat, index):
    """Baut aus einem `_AppKandidat` ein PANEL-3-Kachel-Dict (PAA-3.3).

    `key` ist stabil und eindeutig innerhalb der `tiles.json` (PANEL-3) —
    wir leiten ihn aus `app` + laufendem Index ab, damit dieselbe App
    mehrfach (verschiedene Views) kollisionsfrei bliebe.
    """
    return {
        "key": "%s-%d" % (kandidat.app, index),
        "app": kandidat.app,
        "view": kandidat.view,
        "label": kandidat.label,
        "icons": list(kandidat.icons),
        "sichtbar": True,
        **({"query": dict(kandidat.query)} if kandidat.query else {}),
    }


# ============================================================
#  Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail
#  (PAA-3 / PAA-7 lassen den Wortlaut offen).
# ============================================================

ASK_SLUG = ("Wie soll die Panel-Instanz heißen? Schreib einen kurzen Namen "
            "(z. B. »Küche« oder »Flur-Tablet«) — daraus baue ich die "
            "Panel-Kennung.")
ASK_APPS = ("Welche Apps sollen als Kacheln auf dem Panel erscheinen? "
            "Schreib die Nummern (mehrere mit Komma, z. B. »1,2«):")
ASK_NOCH_KACHEL = ("Noch eine App hinzufügen? Schreib die Nummer — oder "
                   "»fertig«, wenn die Auswahl reicht.")

REJECT_DISPLAY = ("Das verstehe ich nicht. Bitte die Nummer eines gelisteten "
                  "Displays schreiben (oder die display_id).")
REJECT_SLUG = ("Der Name ergibt keine gültige Kennung — bitte mit Buchstaben "
               "oder Ziffern schreiben (z. B. »Küche«).")
REJECT_APPS = ("Das verstehe ich nicht. Bitte mindestens eine Nummer aus der "
               "Liste schreiben (mehrere mit Komma).")

KEINE_DISPLAYS = ("Es ist noch kein Display-Gerät angelegt. Ein Panel steuert "
                  "ein Display — leg erst ein Gerät mit Verwendung »display« "
                  "an (Geräte-Anlage), dann können wir das Panel bauen.")
GERAETE_FEHLER = ("Ich komme gerade nicht an die Geräte-Liste — ohne sie kann "
                  "ich kein Panel anlegen. Bitte später noch einmal.")
NOT_AUTHORIZED = ("Panels anlegen geht nur für Mitglieder der Familien-Gruppe. "
                  "Wende dich bitte an jemanden aus der Gruppe.")
WRITE_FAILED = ("Konnte das Panel nicht speichern — bitte später noch einmal. "
                "Es wurde nichts in der Registry verändert.")
CANCELLED = "Ok, abgebrochen — das Panel wurde nicht gespeichert."
DONE_FMT = "Geschafft, das Panel »%s« ist angelegt. Controller-URL: %s"

# PAA-3.1: Vorspann der Display-Auswahl-Liste.
DISPLAY_LISTE_KOPF = ("Welches Display soll dieses Panel steuern? "
                      "Schreib die Nummer:")


# PAA-3.2: Slug-Normalisierung (PREG-6 sinngemäß, URL-6). Umlaute aufgelöst,
# alles kleingeschrieben, Nicht-[a-z0-9] zu Bindestrich, Ränder getrimmt. Der
# Server normalisiert noch einmal autoritativ (PREG-6) — diese Prüfung dient
# nur dazu, eine nach Normalisierung leere Eingabe früh abzuweisen (PAA-7).
_UMLAUT_MAP = str.maketrans({
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "ae", "Ö": "oe", "Ü": "ue",
})


def normalisiere_slug(text):
    """Normalisiert freien Text zu einem PREG-6-tauglichen Slug.

    Liefert den Slug oder einen leeren String, wenn nach Normalisierung
    nichts Gültiges übrig bleibt (PAA-7: Eingabe abweisen). Die laufende
    Nummer (`-01`) hängt der Server an (PREG-6) — hier nur die Basis.
    """
    s = (text or "").translate(_UMLAUT_MAP).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# ============================================================
#  Eingabe-Protokoll (Test-Doppelung & Live-Adapter haben dieselbe Form,
#  analog GAA-1)
# ============================================================

@dataclass
class PaaInput:
    """Eine eingehende Privatchat-Nachricht des Aufrufers, PAA-spezifisch
    aufbereitet — schmaler als IncomingMessage."""
    text: str = ""


# ============================================================
#  Ergebnis
# ============================================================

class PanelAnlegenError(Exception):
    """Anlegen konnte nicht abgeschlossen werden (Aufrufer entscheidet)."""


@dataclass
class PanelAnlegenResult:
    """Ergebnis-Signal an den Aufrufer (PAA-1).

    `panel_id` ist die server-vergebene `panel_id` der angelegten Instanz —
    None, wenn der Aufrufer abgebrochen hat (PAA-3.4), ein Fehler auftrat
    (PAA-7) oder das Mitglied nicht berechtigt war (PAA-2). `controller_url`
    ist `/controller/app-panel/<panel_id>` (mit Origin, falls einer mitgegeben
    ist). `authorized` unterscheidet den Nicht-Mitglied-Fall.
    """
    panel_id: object = None
    controller_url: object = None
    authorized: bool = True


# ============================================================
#  Die Funktion
# ============================================================

def panel_anlegen(tg, chat_id, user_id, family_group_chat_id,
                  panel_client, geraete_client, next_message,
                  controller_url_origin=None,
                  typing_fn: Callable[[], None] | None = None):
    """Legt **eine** Panel-Instanz an (PAA-1).

    `tg`                     — Telegram-Kanal (`send_message`, `get_chat_member`).
    `chat_id`                — Privatchat des Aufrufers (PAA-3).
    `user_id`                — Telegram-User-ID des Aufrufers (PAA-2).
    `family_group_chat_id`   — ID der gebundenen Familien-Gruppe (PAA-2).
    `panel_client`           — `PanelClient` (HTTP-Schreib-Naht, PREG-15).
    `geraete_client`         — `GeraeteDisplayClient` (HTTP-Lese-Naht, GER-13)
                               für die Display-Auswahl (PAA-3.1).
    `next_message`           — Callable, das die nächste eingehende
                               Privatchat-Nachricht des Aufrufers liefert
                               (PaaInput). Liefert `None`, gilt der Vorgang als
                               abgebrochen.
    `controller_url_origin`  — optional, Origin-URL (z. B. „https://hub.local")
                               für die Controller-URL-Rückgabe (PAA-3.5). Ohne
                               Wert liefert die Funktion nur den Pfad
                               `/controller/app-panel/<panel_id>`.
    `typing_fn`              — optionaler Callable ohne Argumente; vor jeder
                               send_message-Phase aufgerufen (EC-25, Best-Effort,
                               Fehler geschluckt). Default None → No-op.

    Liefert ein `PanelAnlegenResult`. Schreibt ausschließlich über PREG-15.
    """
    # PAA-2: Berechtigung live über die Familien-Gruppen-Mitgliedschaft.
    if not authz.is_authorized(tg, family_group_chat_id, user_id):
        logging.info("panel_anlegen: %s nicht in Familien-Gruppe — abgewiesen",
                     user_id)
        fire_typing(typing_fn)
        _send(tg, chat_id, NOT_AUTHORIZED)
        return PanelAnlegenResult(authorized=False)

    # PAA-3.1: Display-Auswahl aus der Geräte-Registry (GER-13), gefiltert auf
    # verwendung:display. Lesefehler / keine Displays beenden den Vorgang
    # ohne Wirkung (PAA-7).
    try:
        displays = geraete_client.displays()
    except GeraeteReadError as e:
        logging.warning("panel_anlegen: GER-13-Lesen fehlgeschlagen: %s", e)
        fire_typing(typing_fn)
        _send(tg, chat_id, GERAETE_FEHLER)
        return PanelAnlegenResult()
    if not displays:
        fire_typing(typing_fn)
        _send(tg, chat_id, KEINE_DISPLAYS)
        return PanelAnlegenResult()

    display_id = _frage_display(tg, chat_id, displays, next_message, typing_fn)
    if display_id is None:
        return PanelAnlegenResult()

    # PAA-3.2: Slug (Freitext → normalisiert).
    slug = _frage_slug(tg, chat_id, next_message, typing_fn)
    if slug is None:
        return PanelAnlegenResult()

    # PAA-3.3: Apps/Kacheln aus der festen Kandidatenliste.
    tiles = _frage_apps(tg, chat_id, next_message, typing_fn)
    if tiles is None:
        return PanelAnlegenResult()

    # PAA-3.4: Zusammenfassung + Bestätigungswort (E-EC-7).
    fire_typing(typing_fn)
    _send(tg, chat_id, _zusammenfassung(display_id, slug, tiles, displays))
    bestaetigung = next_message()
    if bestaetigung is None or not confirm.is_confirmation(
            (bestaetigung.text or "").strip()):
        fire_typing(typing_fn)
        _send(tg, chat_id, CANCELLED)
        return PanelAnlegenResult()

    # PAA-3.5: Anlage über PREG-15. Der Skill sendet KEINE config-Identität
    # (PAA-4) — nur {slug, display_id, tiles}. Der Server vergibt die panel_id
    # und leitet source_id/display_id/router_url ab.
    try:
        angelegt = panel_client.panel_anlegen(
            slug=slug, display_id=display_id, tiles={"tiles": tiles})
    except PanelClientError as e:
        logging.warning("panel_anlegen: Anlage fehlgeschlagen: %s", e)
        fire_typing(typing_fn)
        _send(tg, chat_id, WRITE_FAILED)
        return PanelAnlegenResult()

    panel_id = angelegt.get("panel_id")
    if not panel_id:
        logging.warning("panel_anlegen: PREG-15-Antwort ohne panel_id: %r",
                        angelegt)
        fire_typing(typing_fn)
        _send(tg, chat_id, WRITE_FAILED)
        return PanelAnlegenResult()

    controller_url = _controller_url(panel_id, controller_url_origin)
    fire_typing(typing_fn)
    _send(tg, chat_id, DONE_FMT % (slug, controller_url))
    logging.info("PAA-Session in Chat %s beendet — panel_id=%s",
                 chat_id, panel_id)
    return PanelAnlegenResult(panel_id=panel_id, controller_url=controller_url)


# ============================================================
#  Einzel-Schritte (PAA-3.1..3.3)
# ============================================================

def _frage_display(tg, chat_id, displays, next_message, typing_fn=None):
    """PAA-3.1: nummerierte Display-Auswahl. Liefert die gewählte `display_id`
    oder None (Abbruch). Eine Antwort außerhalb der Liste wiederholt die Frage
    (PAA-7)."""
    zeilen = [DISPLAY_LISTE_KOPF]
    for i, d in enumerate(displays, start=1):
        zeilen.append("%d. %s (%s)" % (i, d.get("name", "?"), d.get("id", "?")))
    prompt = "\n".join(zeilen)
    gueltige_ids = {d.get("id") for d in displays}
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, prompt)
        msg = next_message()
        if msg is None:
            return None
        text = (msg.text or "").strip()
        # Nummer?
        if text.isdigit():
            idx = int(text)
            if 1 <= idx <= len(displays):
                return displays[idx - 1].get("id")
        # Oder die display_id direkt?
        if text in gueltige_ids:
            return text
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_DISPLAY)


def _frage_slug(tg, chat_id, next_message, typing_fn=None):
    """PAA-3.2: Slug als Freitext, normalisiert. Eine nach Normalisierung
    leere Eingabe wird abgewiesen (PAA-7)."""
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, ASK_SLUG)
        msg = next_message()
        if msg is None:
            return None
        slug = normalisiere_slug(msg.text)
        if slug:
            return slug
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_SLUG)


def _frage_apps(tg, chat_id, next_message, typing_fn=None):
    """PAA-3.3: Apps aus der festen Kandidatenliste (≥1). Liefert die
    Kachel-Liste in PANEL-3-Form (Reihenfolge = Anzeige-Reihenfolge) oder
    None (Abbruch). Eine Eingabe ohne gültige Nummer wiederholt die Frage
    (PAA-7)."""
    katalog = "\n".join(
        "%d. %s" % (i, k.name)
        for i, k in enumerate(APP_KANDIDATEN, start=1))
    while True:
        fire_typing(typing_fn)
        _send(tg, chat_id, "%s\n%s" % (ASK_APPS, katalog))
        msg = next_message()
        if msg is None:
            return None
        gewaehlt = _parse_app_auswahl(msg.text)
        if gewaehlt:
            return [_tile_aus_kandidat(APP_KANDIDATEN[i], pos)
                    for pos, i in enumerate(gewaehlt)]
        fire_typing(typing_fn)
        _send(tg, chat_id, REJECT_APPS)


def _parse_app_auswahl(text):
    """Parst »1,2« / »1 2« zu einer Liste von Kandidaten-Indizes (0-basiert),
    in Eingabe-Reihenfolge, ohne Duplikate. Liefert [] bei keiner gültigen
    Nummer."""
    roh = re.split(r"[,\s]+", (text or "").strip())
    indizes = []
    for token in roh:
        if not token.isdigit():
            continue
        n = int(token)
        if 1 <= n <= len(APP_KANDIDATEN) and (n - 1) not in indizes:
            indizes.append(n - 1)
    return indizes


# ============================================================
#  Helpers
# ============================================================

def _controller_url(panel_id, origin):
    """PAA-3.5: Controller-URL `/controller/app-panel/<panel_id>` (PANEL-2)."""
    pfad = "/controller/app-panel/%s" % panel_id
    if origin:
        return "%s%s" % (origin.rstrip("/"), pfad)
    return pfad


def _zusammenfassung(display_id, slug, tiles, displays):
    """PAA-3.4: Zusammenfassung vor dem Bestätigungswort."""
    name = next((d.get("name") for d in displays if d.get("id") == display_id),
                display_id)
    kachel_namen = ", ".join(t["label"] for t in tiles)
    teile = [
        "Bitte bestätigen (»ok« / »ja«):",
        "• Display: %s (%s)" % (name, display_id),
        "• Name/Slug: %s" % slug,
        "• Kacheln: %s" % kachel_namen,
    ]
    return "\n".join(teile)


def _send(tg, chat_id, text):
    """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt, aber
    brechen die Funktion nicht ab — analog `geraet_anlegen._send`."""
    try:
        tg.send_message(chat_id, text)
    except TelegramError as e:
        logging.warning("panel_anlegen: Senden an %s fehlgeschlagen: %s",
                        chat_id, e)
