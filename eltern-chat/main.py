#!/usr/bin/env python3
"""XBuddy Eltern-Chat V1 — siehe specs/platform/eltern-chat.md und
eltern-chat-onboarding.md (Refs #27, #33).

Eigener Prozess, eigener Telegram-Kanal per Polling. Diese Datei ist die
ORCHESTRIERUNG: sie nimmt Nachrichten entgegen und verdrahtet die Bausteine.
Die Sicherheits-Gates liegen hier — außerhalb des Agent-Loops (E-EC-4):

  eingehende Nachricht
    → EC-5  Ansprache-Prüfung (Gruppe: nur bei Mention/Antwort an den Bot)
    → EC-2  Berechtigung (authz, Live-Mitgliedschaftsprüfung)
    → EC-10 Bestätigung (confirm) — ist es ein Bestätigungswort?
    → sonst: Agent-Loop (agent), Antwort/Vorschlag, Verlauf persistieren

agent.py kennt weder authz noch confirm — der LLM kann die Gates nicht umgehen.

Liegt beim Start kein Anbieter-Key vor, läuft die Instanz zunächst im
Onboarding-Modus (onboarding.py, ONB-1) — der Polling-Loop reicht Updates dann
an onboarding.handle_update, bis der Key per Chat eingerichtet ist.
"""

import argparse
import logging
import os
import queue
import sys
import threading
import time
import uuid
from dataclasses import dataclass

# eltern-chat/ liegt auf sys.path, wenn main.py direkt gestartet wird; für den
# Import-aus-Tests-Fall sorgt tests/conftest.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Repo-Wurzel auf den Importpfad — der Bot konsumiert die Library
# `tools.zugangsdaten` (für die Kalender-Verbinden-Skill, analog plan/main.py)
# und die gemeinsamen Tools (`tools.logsetup`, …). Im systemd-Setup ist
# WorkingDirectory=eltern-chat/, damit `from tools.zugangsdaten import …`
# ohne PYTHONPATH funktioniert.
_REPO_ROOT_FOR_IMPORTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT_FOR_IMPORTS not in sys.path:
    sys.path.insert(0, _REPO_ROOT_FOR_IMPORTS)

import agent
import authz
import config as config_mod
import confirm
import onboarding
from a2_receipt_store import A2ReceiptStore
from confirm import PendingProposal, PendingStore
from history import History
from model import ImageBlock, Message, ProviderError, TextBlock
from onboarding import OnboardingState
from onboarding_store import ZD_NAME_PROVIDER_NAME, OnboardingStore
from private_chat_session import SessionSortEntry
from providers import get_lib_agent_provider

# EC-39: Renewer-Intervall — gemeinsame Wahrheit mit EC-28 / skills/typing_indicator.py.
# Re-Export, damit eine spätere conventions/typing-renewal.md (n=3-Aufschub)
# den Wert nicht an zwei Orten pflegt.
from skills.typing_indicator import _DEFAULT_RENEWAL_INTERVAL as _RENEWER_INTERVAL_S
from tasks import TurnContext, build_catalog
from telegram import ChatMigratedError, TelegramClient, TelegramError
from telemetry import TelemetryStore

from tools import logsetup  # LOG-4 (#166), Repo-Root liegt schon auf sys.path

# Klartext-Antworten.
_PROVIDER_DOWN = ("Ich kann deine Anfrage gerade nicht bearbeiten — der "
                  "KI-Dienst ist nicht erreichbar. Bitte versuch es gleich "
                  "noch einmal.")   # EC-14
_TASK_GONE = "Diese Aufgabe ist nicht mehr verfügbar."
_TASK_FAILED = "Die Aufgabe konnte nicht ausgeführt werden: %s"

# FSE-3 / EC-12-Geist (#393): Marker statt Pixel für das kommentarlose Foto.
# Ein Foto OHNE Begleittext ist das Intent-Signal für `foto_senden` (Bilderrahmen).
# Der Haupt-Agent-LLM braucht dafür die Pixel NICHT — er routet allein aus diesem
# Marker zu `foto_senden`; die Bytes fließen deterministisch über die TurnContext-
# file_id-Naht zur Photo-API (foto_senden_task.py:160). Das Bild als base64 an den
# Provider (Mistral `image_url`) zu hängen war redundant: es kostete bei JEDEM
# Schnappschuss Tokens/Latenz und blähte die persistierte History (Re-Send pro
# Folge-Turn). Foto MIT Begleittext bleibt unangetastet (EC-4 / Skill-Routing).
_FOTO_OHNE_BEGLEITTEXT_MARKER = "[Ein Foto ohne Begleittext wurde gesendet.]"

# EC-36 Korrektur-Hook (#844): das deterministische `falsch`-Wort vor dem
# Agenten — case-insensitiv, getrimmt, ganzes Wort. Nur diese Form triggert
# den Hook; »falsch eingeschätzt«, »ist falsch gelaufen« etc. sind Gesprächs-
# text und gehen an den Agenten. Subsumiert #721 (deterministischer Vor-Agent-
# Hook): das Match HIER ist der erste Schritt, danach folgt A2-Inverse oder
# Klasse-C-Verwerfung.
_FALSCH_WORT = "falsch"

# EC-36 (#844): Quittungs-Wortlaute pro Pfad-Sorte (spec Z. 1162-1168).
# Beide Pfade fragen anschließend mit derselben Folge-Frage nach der Korrektur.
_QUITTUNG_A2_POSITIV = "Ok, rückgängig."
# EC-7 / EC-10-Spec Z. 586-597: Ambiguitäts-Form für 4xx/5xx oder Connection-
# Fehler — der Bot bleibt ehrlich, behauptet keinen sauberen Rollback.
_QUITTUNG_A2_AMBIVALENT = (
    "Konnte den Eintrag nicht zweifelsfrei zurücknehmen — bitte selbst an "
    "der Quelle prüfen.")
_QUITTUNG_C_VERWORFEN = "Ok, Vorschlag verworfen."
# Folge-Frage des Bots NACH der Quittung — identisch für A2 und Klasse-C
# (spec Z. 1162-1168).
_QUITTUNG_KORREKTUR_FRAGE = "Was war falsch, wie soll ich es machen?"

# EC-36 / EC-10 spec Z. 533-535: inverse_call ist HTTP-Form
# "<buddy-key> <method> <api-path>". Buddy-Key → Origin-URL-Resolver:
# der Hook nutzt einen reinen Getter, damit der Skill-Client unangetastet
# bleibt (T844-stop_rule client_pollution). Neue Buddies werden hier
# ergänzt, sobald sie A2-Receipts schreiben.
def _resolve_origin(buddy_key, ctx):
    """Liefert die Origin-URL für einen Buddy-Key des inverse_call (#844)."""
    if buddy_key == "photo":
        return ctx.photo_origin_url
    if buddy_key == "essen":
        return ctx.essen_origin_url
    return ""


@dataclass
class Context:
    """Verdrahtete Abhängigkeiten einer laufenden Instanz.

    Tests bauen einen Context mit Doppelungen für `tg` und `provider` und können
    so `handle_update` ohne Netz prüfen (EC-17).
    """
    tg: object                 # TelegramClient (oder Doppelung)
    bot_username: str
    family_group_chat_id: object
    context_depth: int
    provider: object           # KI-Anbieter-Adapter (oder Doppelung); None im Onboarding-Modus
    catalog: object            # tasks.Catalog
    history: object            # history.History
    pending: object            # confirm.PendingStore
    telemetry_store: object = None     # telemetry.TelemetryStore — None ⇒ Persistenz aus (Test-Default, EC-23/#268)
    store: object = None               # onboarding_store.OnboardingStore — Persistenz der Familien-Gruppe (ONB-5, EC-18)
    family_group_locked: bool = False  # True ⇒ Familien-Gruppe per Env/Config gesetzt, Vorrang (ONB-6, EC-18)
    onboarding: object = None  # onboarding.OnboardingState — None ⇒ KI-Modus (ONB-1)
    faa_sessions: dict = None  # FAA-12: laufende »Familie anlegen«-Sessions (chat_id → FaaSession)
    kav_sessions: dict = None  # KAV-3: laufende »Kalender verbinden«-Sessions (chat_id → KavSession)
    tes_sessions: dict = None  # TES-3: laufende »Termin eintragen«-Sessions (chat_id → TesSession)
    tab_sessions: dict = None  # TAB-12: laufende »Termine aus Bild«-Sessions (chat_id → TabSession)
    avb_sessions: dict = None  # AVB/ONB-11: laufende »Anbieter wechseln«-Sessions (chat_id → AvbSession)
    # EC-36 Korrektur-Hook (#844): der Vor-Agent-Hook liest unversiegelte
    # A2-Receipts aus dem Store und ruft je inverse_call den passenden Buddy-
    # Endpunkt deterministisch (HTTP DELETE) — Origin-URLs werden im build_context
    # aus cfg.* eingespeist, der Hook braucht keinen Skill-Client-Wrapper
    # (RAT-12 / T844-stop_rule client_pollution).
    a2_receipt_store: object = None   # A2ReceiptStore | None — None ⇒ Hook ist no-op
    photo_origin_url: str = ""        # Origin des Photo-Buddys (cfg.photo_origin_url)
    essen_origin_url: str = ""        # Origin des Essens-Buddys (cfg.essen_origin_url)


# SESS-5: Session-Sorten-Registry — modul-weit, einmal definiert.
# Jede Sorte benennt ihren Context-Slot und ihren make_input-Helfer.
# handle_update iteriert darüber, statt pro Sorte einen eigenen if-Block
# zu tragen. Reihenfolge entspricht der früheren if-Kette und darf nicht
# ohne Routing-Check geändert werden (alle in _SESSION_SORTS registrierten
# Sorten — aktuell FAA→KAV→TES→TAB→AVB). RAT-31 E6c: GAA hat keine
# PrivateChatSession mehr (nur noch Link-Minten, synchron) — kein gaa_sessions-Slot.
#
# Die make_input-Callables werden einmal beim Modul-Load gebunden —
# die skills-Module liegen zu diesem Zeitpunkt bereits auf sys.path
# (conftest.py / systemd-WorkingDirectory).
#
# Invariante (Lego-Sanity, Befund 5): jeder Context-Slot der Form `*_sessions`
# MUSS hier eingetragen sein — test_main_bootstrap.py prüft das mechanisch.
def _build_session_sorts():
    from skills.anbieter_wechseln_task import make_avb_input
    from skills.familie_anlegen_task import make_faa_input
    from skills.kalender_verbinden_task import make_kav_input
    from skills.termin_eintragen_task import make_tes_input
    from skills.termine_aus_bild_task import make_tab_input
    return (
        SessionSortEntry("faa_sessions", make_faa_input),   # FAA-12
        SessionSortEntry("kav_sessions", make_kav_input),   # KAV-3
        SessionSortEntry("tes_sessions", make_tes_input),   # TES-3
        SessionSortEntry("tab_sessions", make_tab_input),   # TAB-12
        SessionSortEntry("avb_sessions", make_avb_input),   # AVB/ONB-11
    )

_SESSION_SORTS = _build_session_sorts()


# ============================================================
#  Orchestrierung
# ============================================================

def handle_update(update, ctx):
    """Petrarbeitet ein einzelnes Telegram-Update."""
    msg = ctx.tg.extract_message(update, ctx.bot_username)
    if msg is None:
        return

    # SESS-5: Privatchat-Session-Routing — generische Iteration über _SESSION_SORTS.
    # Alle in _SESSION_SORTS registrierten Sorten beanspruchen den Privatchat
    # ihres Inhabers, solange sie laufen. handle_update liest die Session-Map
    # per getattr(ctx, entry.ctx_attr) — dieselbe Map-Referenz, die der Worker
    # befüllt (Lego-Falle-Sicherung, TASK-7). Reihenfolge: wie bisher.
    if msg.chat_type == "private":
        for entry in _SESSION_SORTS:
            sessions = getattr(ctx, entry.ctx_attr, None)
            if sessions is None:
                continue
            session = sessions.get(msg.chat_id)
            if session is not None and not session.is_finished():
                session.deliver(entry.make_input_fn(msg))
                return

    # EC-5: In einer Gruppe reagiert das System nur, wenn es ausdrücklich
    # angesprochen wird. Im Privatchat bezieht sich jede Nachricht auf den Bot.
    # Das Verwerfen wird protokolliert — sonst ist ein „Bot schweigt in der
    # Gruppe" nicht von „Nachricht nie angekommen" zu unterscheiden.
    if msg.chat_type in ("group", "supergroup"):
        if not (msg.mentions_bot or msg.reply_to_from_bot):
            logging.debug("Gruppe %s: Nachricht ohne Ansprache — ignoriert (EC-5)",
                          msg.chat_id)
            return
        logging.info("Gruppe %s: ausdrücklich angesprochen — Anfrage wird "
                     "bearbeitet (EC-5)", msg.chat_id)

    # EC-25 / AC2 (Ticket #287): Typing-Indikator VOR dem Auth-Check im Privatchat.
    # Der Nutzer sieht „tippt gerade" während des getChatMember-Aufrufs (bis zu 35 s
    # Stille bisher). Best-Effort: Fehler dürfen den Turn nicht abbrechen.
    # Nur im Privatchat: in der Familien-Gruppe ist Typing nicht sinnvoll (EC-25
    # spricht explizit von „Privatchat" für mehrstufige Schreib-Aufgaben).
    if msg.chat_type == "private":
        try:
            ctx.tg.send_chat_action(msg.chat_id, "typing")
        except TelegramError as e:
            logging.warning("Typing vor Auth-Check fehlgeschlagen "
                            "chat_id=%s fehler=%s", msg.chat_id, e)

    # EC-2/EC-3: Berechtigung — Live-Mitgliedschaftsprüfung. Nicht-Mitglieder
    # werden ohne Antwort ignoriert. Dieses Gate liegt außerhalb des Agenten.
    try:
        authorized = authz.is_authorized(ctx.tg, ctx.family_group_chat_id,
                                         msg.from_user_id)
    except ChatMigratedError as e:
        # EC-18 (Weg 2): die Familien-Gruppe ist zu einer Supergruppe migriert.
        # Bindung nachziehen und die Berechtigung gegen die neue ID erneut
        # prüfen — die Nachricht nicht fälschlich als unberechtigt verwerfen.
        rebind_family_group(ctx, e.new_chat_id)
        authorized = authz.is_authorized(ctx.tg, ctx.family_group_chat_id,
                                         msg.from_user_id)
    if not authorized:
        logging.info("Nachricht von nicht-berechtigtem Absender %s ignoriert",
                     msg.from_user_id)
        return

    # EC-36 Korrektur-Hook (#844): vor dem Bestätigungs-Gate UND vor dem Agenten.
    # Der `falsch`-Vor-Agent-Hook ist deterministisch, außerhalb des Agenten
    # (E-EC-4-Linie wie is_confirmation): das LLM entscheidet nie über das
    # Rückgängigmachen. Subsumiert #721. Liegt ein unversiegelter A2-Receipt vor,
    # läuft der Inverse-Call; sonst wird ein offener Klasse-C-Vorschlag verworfen.
    # Im trivialen Fall (kein Receipt, kein Pending) ist `falsch` Gesprächstext
    # und der Hook gibt False zurück — der Agent kann antworten.
    if _is_falsch_wort(msg.text) and _falsch_hook(msg, ctx):
        return

    # EC-10: Bestätigung schreibender Aufgaben — deterministisch (E-EC-7),
    # außerhalb des Agenten. Nur wenn der Text ein Bestätigungswort ist UND ein
    # passender offener Vorschlag existiert, wird ausgeführt.
    if confirm.is_confirmation(msg.text):
        pending = ctx.pending.take(msg.chat_id, msg.reply_to_message_id)
        if pending is not None:
            _execute_confirmed(pending, msg, ctx)
            return
        # Kein passender Vorschlag → „ok" ist hier nur Gesprächstext, weiter
        # an den Agenten.

    _run_agent(msg, ctx)


def _is_falsch_wort(text):
    """True, wenn `text` GENAU dem Korrektur-Wort `falsch` entspricht (EC-36,
    case-insensitiv, getrimmt; analog confirm.is_confirmation für »ok«)."""
    if not text:
        return False
    return text.strip().lower() == _FALSCH_WORT


def _http_delete(origin_url, api_path, timeout=2.0, transport=None):
    """Setzt einen HTTP DELETE auf `origin_url + api_path` ab (EC-36 Inverse).

    Liefert `(status_code, body_bytes)`. Connection-Fehler werden als
    `(0, b"")` zurückgegeben — der Hook wertet status < 200 oder >= 300 als
    Ambiguität (EC-7/EC-10 spec Z. 586-597) und siegelt den Bon trotzdem.

    Test-Naht analog `conventions/http-client.md` CLIENT-1: optionaler
    `transport=`-Callable, Default ist der echte HTTP-Aufruf über urllib.
    Tests übergeben einen In-Process-Stub statt monkeypatch — die
    Signatur des Stubs ist identisch mit dem Default-Transport:
    `(url, timeout) -> (status_code, bytes)`.

    Hinweis zur Lego-Form: _http_delete ist KEIN voller Komponenten-Client
    nach CLIENT-1..CLIENT-4. Der Pfad kommt aus dem persistierten
    `inverse_call` (EC-36 spec Z. 543-561, `a2_receipts.inverse_call`),
    nicht aus dem Skill-Code — CLIENT-4 (Pfad-Konstanten aus urls.md)
    trifft für inverse_call deshalb nicht. Eine eigene Komponenten-Error-
    Klasse (CLIENT-3) ist hier ebenfalls offen — Halt-zu-Nic-Sonderfall,
    weil der Hook ausdrücklich auf Ambiguitäts-Quittung statt Exception
    setzt (EC-7/EC-10 spec Z. 586-597).

    Bewusst urllib (kein requests-Dependency); konsistent mit
    `skills/photo_client.py:152-186`.
    """
    import urllib.error
    import urllib.request

    url = (origin_url or "").rstrip("/") + api_path
    if transport is not None:
        # CLIENT-1 Test-Naht — Stub erhält dieselbe Signatur wie der echte
        # Default-Transport unten (URL + timeout).
        return transport(url, timeout)
    request = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        # 4xx/5xx kommen als HTTPError — der Hook liest sie als Ambiguität.
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        logging.warning("EC-36-Hook: DELETE %s nicht erreichbar (%s)", url, e)
        return 0, b""


def _falsch_hook(msg, ctx, http_delete=None):
    """Vor-Agent-Hook für das Korrektur-Wort `falsch` (EC-36, #844).

    Reihenfolge der Pfade (spec Z. 1145-1168):
      1. **A2-Pfad** — wenn unversiegelte A2-Receipts der `chat_id` existieren,
         pro Receipt den `inverse_call` parsen und HTTP-DELETE absetzen,
         danach **alle** Receipts des Chats versiegeln (auch im Ambiguitäts-
         Fall, spec Z. 593-597). Quittung positiv bei sauberen 2xx auf allen
         Receipts, sonst Ambiguitäts-Quittung (EC-7/EC-10 spec Z. 586-597).
         Korrektur-State wird gesetzt — die Folge-Frage „Was war falsch?"
         wird angehängt; der nächste User-Turn läuft mit erweitertem System-
         Prompt durch den Agenten (Re-Propose ⇒ Confirm-Gate, spec Z. 1193-1201).
      2. **Klasse-C-Pfad** — kein A2-Receipt, aber ein offener Pending-Vorschlag:
         der Vorschlag wird verworfen (`take()` ohne Reply-ID nutzt den Single-
         Slot), Quittung „Vorschlag verworfen", Korrektur-State gesetzt.
      3. **Trivialer Fall** — weder Receipt noch Pending: der Hook gibt False
         zurück, `falsch` ist Gesprächstext und geht an den Agenten.

    Rückgabe: True ⇒ Hook hat petrarbeitet, Orchestrierung beendet den Turn.
              False ⇒ Hook hat nichts gefunden, weiterreichen.

    `http_delete` (Test-Naht, CLIENT-1-Pattern): optionaler Callable mit
    derselben Signatur wie `_http_delete(origin, api_path) -> (status, bytes)`.
    Default `None` → das Modul-Level `_http_delete` (echter HTTP-Aufruf).
    Tests injizieren einen In-Process-Stub statt monkeypatch.

    Cross-Skill-Exit (spec Z. 1184-1191) ist implizit: der Korrektur-State lebt
    nur einen Folge-Turn — schickt der User dort eine Anfrage zu einem anderen
    Skill, läuft der Agent durch seinen normalen Pfad (neuer Vorschlag in
    `pending.add()` verdrängt nichts, weil der alte Pending bereits beim
    `falsch` verworfen wurde). `_run_agent` löscht den State nach jedem Turn.
    """
    chat_id = msg.chat_id
    if http_delete is None:
        http_delete = _http_delete

    # Pfad 1: A2-Receipts.
    receipts = []
    if ctx.a2_receipt_store is not None:
        try:
            receipts = ctx.a2_receipt_store.fetch_unsealed_for_chat(chat_id)
        except Exception as e:
            # Receipt-Lese-Fehler darf den Hook nicht sprengen — er fällt auf
            # den Klasse-C-Pfad zurück. Ehrliche Grenze (EC-7).
            logging.warning("EC-36-Hook: fetch_unsealed_for_chat fehlgeschlagen "
                            "chat_id=%s: %s", chat_id, e)

    if receipts:
        alle_ok = True
        last_skill = receipts[-1]["task_name"]
        for receipt in receipts:
            inverse = receipt.get("inverse_call") or ""
            parts = inverse.split(None, 2)
            if len(parts) != 3:
                logging.warning("EC-36-Hook: ungültige inverse_call-Form %r "
                                "(receipt id=%s)", inverse, receipt.get("id"))
                alle_ok = False
                continue
            buddy_key, method, api_path = parts
            origin = _resolve_origin(buddy_key, ctx)
            if not origin or method.upper() != "DELETE":
                logging.warning("EC-36-Hook: keine Origin/Method-Form für "
                                "buddy_key=%r method=%r", buddy_key, method)
                alle_ok = False
                continue
            status, _body = http_delete(origin, api_path)
            if not (200 <= status < 300):
                # EC-10 spec Z. 586-597: Ambiguitäts-Pfad — Quittung wird
                # ehrlich, Bon trotzdem gesiegelt (kein zweiter Versuch).
                logging.info("EC-36-Hook: inverse DELETE %s%s -> %s (ambivalent)",
                             origin, api_path, status)
                alle_ok = False
            else:
                logging.info("EC-36-Hook: inverse DELETE %s%s -> %s (ok)",
                             origin, api_path, status)

        # Versiegelung läuft IMMER nach den Inverse-Versuchen (spec Z. 593-597):
        # auch im Ambiguitäts-Fall ist der Bon „verbraucht", ein zweiter
        # `falsch` greift nicht mehr auf dieselbe Zeile.
        try:
            ctx.a2_receipt_store.seal_all_for_chat(chat_id)
        except Exception as e:
            logging.warning("EC-36-Hook: seal_all_for_chat fehlgeschlagen "
                            "chat_id=%s: %s", chat_id, e)

        quittung = (_QUITTUNG_A2_POSITIV if alle_ok
                    else _QUITTUNG_A2_AMBIVALENT)
        _send(ctx, chat_id, quittung + "\n" + _QUITTUNG_KORREKTUR_FRAGE,
              reply_to_message_id=msg.message_id)
        ctx.pending.set_correction(chat_id, confirm.CorrectionState(
            last_skill=last_skill, last_args={}, quelle="a2"))
        return True

    # Pfad 2: offener Klasse-C-Pending-Vorschlag.
    # take() ohne Reply-ID nutzt den Single-Slot (confirm.py Z. 95-107).
    pending = ctx.pending.take(chat_id, msg.reply_to_message_id)
    if pending is None and msg.reply_to_message_id is not None:
        # Fallback: Reply-Bezug passt nicht (z. B. Antwort auf alte Nachricht) —
        # trotzdem den Single-Slot ziehen, weil `falsch` der eindeutige Korrektur-
        # Trigger ist und keine ID-Sortierung braucht (EC-36 Wortmatch ist
        # deterministisch, kein LLM).
        pending = ctx.pending.take(chat_id, None)
    if pending is not None:
        _send(ctx, chat_id,
              _QUITTUNG_C_VERWORFEN + "\n" + _QUITTUNG_KORREKTUR_FRAGE,
              reply_to_message_id=msg.message_id)
        ctx.pending.set_correction(chat_id, confirm.CorrectionState(
            last_skill=pending.task_name,
            last_args=dict(pending.arguments or {}),
            quelle="klasse_c"))
        return True

    # Pfad 3: trivial — kein Receipt, kein Pending. `falsch` ist Gesprächstext
    # und geht an den Agenten (ohne Hook-Markierung).
    return False


def _maybe_append_telemetry(text, telemetry):
    """Hängt den EC-23-Suffix an `text`, wenn der Turn mindestens einen
    Provider-Call hatte (AC2). Bei AC3 (keine Calls) bleibt `text` unverändert.

    Der Suffix kommt NUR an die Telegram-Sendung (R7) — die History speichert
    den Originaltext. So bleibt der Verlauf neutral und Folge-Turns sehen
    keine Telemetrie als »Bot-Wortlaut«.
    """
    if telemetry is None or not telemetry.has_calls():
        return text
    suffix = telemetry.format_suffix()
    if not suffix:
        return text
    return "%s\n\n%s" % (text, suffix)


def _persist_telemetry(ctx, turn_id, chat_id, telemetry):
    """Persistiert die Turn-Telemetrie in `conversations.db` (EC-23/AC4).

    Komfort, kein Gate (R1): ein Persistenz-Fehler darf den Turn nicht
    sprengen. Ohne `ctx.telemetry_store` (Test-Default) passiert nichts.
    """
    if ctx.telemetry_store is None or telemetry is None:
        return
    try:
        ctx.telemetry_store.persist_turn(turn_id, chat_id, telemetry)
    except Exception as e:  # Persistenz ist Komfort, nicht Gate
        logging.warning("Telemetrie-Persistenz fehlgeschlagen (turn=%s): %s",
                        turn_id, e)


def _run_agent(msg, ctx):
    """Lässt den Agenten eine Anfrage bearbeiten und sendet das Ergebnis."""
    history = ctx.history.load(msg.chat_id, ctx.context_depth)
    user_message = _user_message_from(msg)
    # EC-23 (#268): turn_id verknüpft die Provider-Calls eines Turns in
    # `provider_calls`. UUID statt Sequenz: ohne Lock, ohne DB-Roundtrip,
    # ohne Kollisionen über Restarts.
    turn_id = uuid.uuid4().hex

    # F2: deterministischer Ausführungs-Kontext, getrennt vom Modell. Der
    # Agent-Loop reicht ihn unverändert an die Aufgaben durch (#63).
    # FSE-3 / D4 (#393): bei einem mitgesendeten Medium reicht main hier die
    # Telegram-`file_id` und den `medium_typ` durch — der FotoSendenTask lädt
    # das Medium über die deterministische Naht, nie aus den Modell-`arguments`
    # (EC-12-Geist). Video als Dokument (mime startend mit `video/`) gilt als
    # Video (FSE-5: gleicher Pfad). Foto > Video > Dokument-Video — die erste
    # Quelle gewinnt; das LLM disambiguiert den eigentlichen Skill-Aufruf
    # (FSE-3: kommentarloses Medium = foto_senden; mit Prompt = anderer Skill).
    media_file_id, medium_typ = _media_naht(msg)
    turn_context = TurnContext(
        chat_id=msg.chat_id,
        from_user_id=msg.from_user_id,
        private_chat_id=(msg.chat_id if msg.chat_type == "private"
                         else msg.from_user_id),
        media_telegram_file_id=media_file_id,
        medium_typ=medium_typ,
        # T1085: dieselbe turn_id (Z.489) als correlation_id durch run_turn an
        # den GenerationRequest → JSONL-Telemetrie der Lib (EC-23-Spiegel). KEIN
        # zweiter UUID — die SQLite-Doppelschreibung nutzt dieselbe turn_id.
        turn_id=turn_id)

    # Issue #93 / #156: Typing-Indikator vor JEDEM Provider-Aufruf — auch in
    # Tool-Loops, in denen der Loop nach einem Tool-Ergebnis erneut den
    # Anbieter ruft. Telegram löscht den Indikator nach rund 5 s, lange
    # Provider-Calls hinterlassen sonst einen toten Indikator. Der Callback
    # läuft pro Iteration; der Wrapper `TelegramClient.send_chat_action`
    # schluckt Telegram-Fehler bereits (Komfort, kein Gate). Das zusätzliche
    # try/except ist doppelte Sicherung — der Indikator darf den Turn unter
    # keinen Umständen blockieren.
    def _typing():
        try:
            ctx.tg.send_chat_action(msg.chat_id, "typing")
        except TelegramError as e:
            logging.warning("Typing-Indikator-Aufruf hat trotz Wrapper-Schluck "
                            "geworfen: %s", e)

    # EC-36 Korrektur-Hook (#844): liegt ein Korrektur-State für diesen Chat
    # vor, reicht die Orchestrierung ihn an den Agenten — der erweitert seinen
    # System-Prompt um den Original-Kontext (last_skill, last_args, quelle),
    # damit das LLM einen gezielten Patch baut statt blank von vorn zu starten.
    # Lebensdauer: genau-ein-Turn — nach dem Agent-Lauf (unten) wird der State
    # gelöscht, egal ob ein Re-Propose oder eine LLM-Rückfrage entstand.
    correction_state = ctx.pending.get_correction(msg.chat_id)

    try:
        result = agent.run_turn(history, user_message, ctx.provider,
                                ctx.catalog, turn_context,
                                before_provider_call=_typing,
                                chat_action_renewer=_typing,  # Issue #165
                                tg=ctx.tg,  # T722: Form-(b)-Übersetzer braucht tg für send
                                correction_state=correction_state)
    except ProviderError as err:
        # EC-14: klarer Hinweis, sauberer Abbruch — keine halbfertige Aufgabe.
        # EC-23 (#268): der Wrapper im Agenten hat einen Stub-Call angehängt
        # und ihn an `err.telemetry` gepinnt. Wir persistieren ihn (R3) und
        # senden den Provider-Down-Hinweis OHNE Suffix — kein Provider-Call
        # ist erfolgreich durchgekommen, also wäre ein Suffix irreführend.
        _persist_telemetry(ctx, turn_id, msg.chat_id,
                           getattr(err, "telemetry", None))
        # EC-36 (#844): Korrektur-State auch im Provider-Down-Fall verbrauchen
        # — sonst würde der nächste Turn ihn doppelt zugespielt bekommen.
        if correction_state is not None:
            ctx.pending.clear_correction(msg.chat_id)
        _send(ctx, msg.chat_id, _PROVIDER_DOWN)
        return

    # EC-36 (#844): Korrektur-State gilt genau einen Folge-Turn — egal ob ein
    # Re-Propose entstand, eine LLM-Rückfrage kam, ein Cross-Skill-Aufruf lief
    # oder eine reine Text-Antwort. Beim Re-Propose liegt der neue Vorschlag
    # bereits im Pending-Slot, der Confirm-Gate-Pfad läuft danach normal.
    if correction_state is not None:
        ctx.pending.clear_correction(msg.chat_id)

    # #310: das VOLLE Turn-Transkript in Loop-Reihenfolge persistieren — nicht
    # nur die finale Text-Quittung. Das Modell muss in Folge-Turns seine eigenen
    # Tool-Aufrufe sehen (EC-6, Modell-Kohärenz), sonst hält es den Tool-Aufruf
    # für überflüssig und hört auf, Werkzeuge zu rufen. `transcript` beginnt mit
    # user_message (Element 0) → kein doppeltes append.
    # R7 (#268): der Telemetrie-Suffix hängt NUR an der Telegram-Sendung, NIE an
    # den persistierten Messages — das gilt hier unverändert weiter.
    for message in result.transcript:
        ctx.history.append(msg.chat_id, message)

    if result.proposal is not None:
        # EC-10: schreibende Aufgabe — Vorschlag vorlegen, auf Bestätigung warten.
        # EC-23/AC2 (#268): der Vorschlag entsteht aus mind. einem Provider-Call;
        # der Suffix kommt an die Telegram-Sendung. R7: History bekommt den
        # Originaltext OHNE Suffix — Folge-Turns sehen die Telemetrie nicht.
        text = _format_proposal(result.proposal)
        sent = _send(ctx, msg.chat_id,
                     _maybe_append_telemetry(text, result.telemetry),
                     reply_to_message_id=msg.message_id)
        if sent is not None:
            # #514 (TAB-12): die deterministische Medien-Naht (FSE-3 / D4) des
            # propose-Turns mit am PendingProposal festhalten — der confirm-Turn
            # trägt nur das Bestätigungs-Wort, nicht das Foto. Ohne diese
            # Persistenz sähe `execute()` einen leeren TurnContext und müsste
            # fälschlich »kein Bild«-Quittung schicken (Live-Bug 2026-06-09).
            ctx.pending.add(PendingProposal(
                chat_id=msg.chat_id,
                proposal_message_id=sent.get("message_id"),
                task_name=result.pending_call.task,
                arguments=result.pending_call.arguments,
                media_telegram_file_id=turn_context.media_telegram_file_id,
                medium_typ=turn_context.medium_typ))
        # #310: das Transkript endet auf dem proposal-Pfad mit dem letzten
        # Tool-Turn; der reine Vorschlagstext (OHNE Suffix, R7) kommt als
        # finaler Assistant-TextBlock zusätzlich in die History.
        ctx.history.append(msg.chat_id, Message("assistant", [TextBlock(text)]))
        _persist_telemetry(ctx, turn_id, msg.chat_id, result.telemetry)
        return

    # EC-23/AC2 (#268): Erfolgs-Pfad ohne schreibende Aufgabe — Suffix an die
    # Sendung. Der finale Assistant-Text steckt bereits im Transkript (oben
    # persistiert, OHNE Suffix — R7); hier wird nur noch gesendet.
    _send(ctx, msg.chat_id,
          _maybe_append_telemetry(result.reply_text, result.telemetry))
    _persist_telemetry(ctx, turn_id, msg.chat_id, result.telemetry)


def _execute_confirmed(pending, msg, ctx):
    """Führt eine bestätigte schreibende Aufgabe aus (nach EC-10-Bestätigung).

    Nach erfolgreicher Ausfuehrung laufen die deklarierten post_execute_hooks
    der Aufgabe (EC-21, #140). Hook-Fehler rollen die Schreib-Aufgabe NICHT
    zurueck — sie werden als zusammengefasste Warnung an die Quittung
    angehaengt."""
    task = ctx.catalog.get(pending.task_name)
    if task is None:
        _send(ctx, msg.chat_id, _TASK_GONE, reply_to_message_id=msg.message_id)
        return
    # #514 (TAB-12): die im propose-Turn festgehaltene Medien-Naht (FSE-3 / D4)
    # in den TurnContext des execute-Turns zurückspielen — der confirm-Turn
    # selbst trägt nur das Bestätigungs-Wort, kein Medium. Bei Schreib-Aufgaben
    # ohne Medium (TES/FAA/…) bleiben beide Felder None — alter Code-Pfad.
    turn_context = TurnContext(
        chat_id=msg.chat_id,
        from_user_id=msg.from_user_id,
        private_chat_id=(msg.chat_id if msg.chat_type == "private"
                         else msg.from_user_id),
        media_telegram_file_id=pending.media_telegram_file_id,
        medium_typ=pending.medium_typ)
    try:
        outcome = ctx.catalog.execute_write_task(
            task, pending.arguments, turn_context)
    except Exception as e:  # Aufgabe isoliert melden
        logging.warning("Ausführung von '%s' fehlgeschlagen: %s", pending.task_name, e)
        _send(ctx, msg.chat_id, _TASK_FAILED % e, reply_to_message_id=msg.message_id)
        return
    text = outcome.combined_text()
    _send(ctx, msg.chat_id, text, reply_to_message_id=msg.message_id)
    ctx.history.append(msg.chat_id, Message("assistant", [TextBlock(text)]))


def _media_naht(msg):
    """FSE-3 / D4 (#393): bestimmt die deterministische Medien-Naht für den
    TurnContext aus einer eingehenden Telegram-Nachricht.

    Liefert `(file_id, typ)` mit `typ in ("foto", "video")` oder `(None, None)`,
    wenn kein Medium anhängt. Reihenfolge: natives Foto > natives Video >
    Video-als-Dokument (`document_mime_type` startend mit `video/`). Andere
    Dokument-Typen (PDFs etc.) sind hier kein FSE-Medium und bleiben für
    foto-fremde Skills (FAA/Schulplan/…) sichtbar — die Disambiguierung
    übernimmt das LLM beim Tool-Wahl-Schritt (FSE-3).
    """
    if msg.photo_file_id:
        return msg.photo_file_id, "foto"
    if msg.video_file_id:
        return msg.video_file_id, "video"
    mime = (msg.document_mime_type or "").lower()
    if msg.document_file_id and mime.startswith("video/"):
        return msg.document_file_id, "video"
    return None, None


def _user_message_from(msg):
    """Baut aus einer eingehenden Nachricht die kanonische Nutzer-Nachricht."""
    blocks = []
    if msg.text:
        blocks.append(TextBlock(msg.text))
    if msg.images and not msg.text:
        # Kommentarloses Foto (FSE-3): nur der Marker geht an den Provider, nicht
        # die base64-Pixel. Das routet zu `foto_senden` (Bilderrahmen); die Bytes
        # holt der Task deterministisch über die TurnContext-file_id-Naht.
        blocks.append(TextBlock(_FOTO_OHNE_BEGLEITTEXT_MARKER))
    else:
        # Foto MIT Begleittext: unverändert — ein konkreter Skill liest das Bild
        # (TAB/Gericht/Essen) bzw. EC-4 greift. Verhalten wie bisher.
        for media_type, data_b64 in msg.images:
            blocks.append(ImageBlock(media_type=media_type, data_b64=data_b64))
    if not blocks:
        # Reine Nicht-Text/Nicht-Bild-Nachricht — leerer Text, der Agent fragt nach.
        blocks.append(TextBlock(""))
    return Message(role="user", blocks=blocks)


def _format_proposal(proposal):
    """Formatiert einen schreibenden Vorschlag als Nachrichtentext (EC-10)."""
    return ("Vorschlag — soll ich das tun?\n\n%s\n\n"
            "Zum Bestätigen antworte mit einem 👍 (zum Beispiel ok oder ja)."
            % proposal.summary)


def _send(ctx, chat_id, text, reply_to_message_id=None):
    """Sendet eine Nachricht; ein Sendefehler bricht die Petrarbeitung nicht ab."""
    try:
        return ctx.tg.send_message(chat_id, text, reply_to_message_id=reply_to_message_id)
    except TelegramError as e:
        logging.warning("Senden an %s fehlgeschlagen: %s", chat_id, e)
        return None


# ============================================================
#  Polling-Loop
# ============================================================

def rebind_family_group(ctx, new_chat_id):
    """EC-18: zieht die Bindung der Familien-Gruppe auf eine neue Chat-ID nach
    (Supergruppen-Migration) und persistiert sie (ONB-5).

    Ist die Gruppe per Env/Config fest gebunden, bleibt der gesetzte Wert
    unangetastet — nur eine Warnung wird protokolliert (Vorrang analog ONB-6).
    """
    new_chat_id = str(new_chat_id)
    if str(ctx.family_group_chat_id) == new_chat_id:
        return
    if ctx.family_group_locked:
        logging.warning(
            "Familien-Gruppe zu %s migriert, ist aber per Env/Config fest "
            "gebunden (%s) — bitte dort manuell nachziehen (EC-18)",
            new_chat_id, ctx.family_group_chat_id)
        return
    old = ctx.family_group_chat_id
    ctx.family_group_chat_id = new_chat_id
    if ctx.store is not None:
        ctx.store.save(family_group_chat_id=new_chat_id)
    logging.info("Familien-Gruppe migriert: %s → %s — Bindung nachgezogen (EC-18)",
                 old, new_chat_id)


def _apply_migration(ctx, old_chat_id, new_chat_id):
    """EC-18: behandelt eine gemeldete Gruppen-Migration. Betrifft sie die
    gebundene Familien-Gruppe (KI-Modus) oder die Onboarding-Gruppe
    (Onboarding-Modus), wird die jeweilige Bindung nachgezogen."""
    old_chat_id = str(old_chat_id)
    if ctx.onboarding is not None:
        st = ctx.onboarding
        if st.pending_group_chat_id is not None and \
                str(st.pending_group_chat_id) == old_chat_id:
            st.pending_group_chat_id = new_chat_id
            logging.info("Onboarding-Gruppe migriert: %s → %s (EC-18)",
                         old_chat_id, new_chat_id)
        return
    if str(ctx.family_group_chat_id) == old_chat_id:
        rebind_family_group(ctx, new_chat_id)


def dispatch(update, ctx):
    """Reicht ein Update an den passenden Handler: den Onboarding-Flow (ONB-1),
    solange kein Anbieter-Key vorliegt — sonst die reguläre Orchestrierung.

    Eine gemeldete Supergruppen-Migration (EC-18) wird vorab abgefangen — sie
    betrifft die Gruppen-Bindung in beiden Modi."""
    migration = ctx.tg.extract_migration(update)
    if migration is not None:
        _apply_migration(ctx, migration[0], migration[1])
        return
    if ctx.onboarding is not None:
        onboarding.handle_update(update, ctx)
    else:
        handle_update(update, ctx)


_BACKOFF_START = 1      # Sekunden — Startverzögerung bei leerem Poll
_BACKOFF_FACTOR = 2     # Multiplikator je aufeinanderfolgendem leeren Poll
_BACKOFF_CAP = 5        # Sekunden — maximale Backoff-Pause

# T1666 / SVC-6-Ergänzung: Heartbeat-Pfad für eltern-chat (Polling-Bot ohne HTTP).
# Priorität: ENV XBUDDY_DATA_DIR > Default. Analoges Muster wie tools/llm/telemetry.py.
_HEARTBEAT_SUBDIR = "eltern-chat"
_HEARTBEAT_FILENAME = "heartbeat"


def _resolve_heartbeat_path() -> str:
    """Löst den Heartbeat-Pfad nach SVC-6 auf.

    Format: `<XBUDDY_DATA_DIR>/eltern-chat/heartbeat`
    Priorität: ENV `XBUDDY_DATA_DIR` > Default `/home/buddy/xbuddy-data`.
    Test-Naht: ENV kann auf tmp_path zeigen.
    """
    base = os.environ.get("XBUDDY_DATA_DIR") or "/home/buddy/xbuddy-data"
    return os.path.join(base, _HEARTBEAT_SUBDIR, _HEARTBEAT_FILENAME)


def _write_heartbeat(heartbeat_path: str) -> None:
    """Schreibt den aktuellen Unix-Timestamp atomar in `heartbeat_path`.

    Format: eine Zeile mit dem Unix-Epoch-Integer (maschinenlesbar für #1646-Poller).
    Atomar via .tmp-Datei + os.replace (POSIX-Garantie — Leser sehen nie halb
    geschriebene Datei). Schreibfehler werden geloggt und geschluckt — der
    Heartbeat ist Observability, kein kritischer Pfad; ein Schreibfehler darf
    den Poll-Loop NICHT unterbrechen (SVC-6-Ergänzung T1666).
    """
    try:
        directory = os.path.dirname(heartbeat_path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        tmp_path = heartbeat_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())) + "\n")
        os.replace(tmp_path, heartbeat_path)
    except OSError as e:
        logging.warning(
            "eltern-chat: Heartbeat konnte nicht geschrieben werden (%s): %s",
            heartbeat_path, e)


def _is_private_message_update(update):
    """True, wenn das Update ein `message` mit `chat.type == "private"` trägt
    (Reader-Filter für Sofort-Typing, EC-39). `my_chat_member` und Gruppen
    fallen raus — EC-25 verriegelt das Bestand-Verhalten.
    """
    if not isinstance(update, dict):
        return False
    msg = update.get("message")
    if not isinstance(msg, dict):
        return False
    chat = msg.get("chat") or {}
    return chat.get("type") == "private"


def _safe_send_chat_action(tg, chat_id, action="typing"):
    """Sendet einen Typing-Indikator und schluckt jede Exception (EC-39:
    Best-Effort; sendChatAction-Fehler dürfen den Reader-Pfad nicht
    unterbrechen). Der echte TelegramClient.send_chat_action schluckt bereits
    TelegramError; dieser Wrapper schließt auch alles weitere ein (Rate-Limit,
    Test-Doppelungen, die andere Exceptions werfen).
    """
    try:
        tg.send_chat_action(chat_id, action)
    except Exception as e:  # EC-39 Best-Effort
        logging.warning("send_chat_action chat_id=%s fehler=%s (geschluckt)",
                        chat_id, e)


def _reader_loop(ctx, tg_reader, handoff, ack, open_chat_ids, chat_ids_lock,
                 stop_event, get_updates_timeout, heartbeat_path=None):
    """Reader-Daemon (EC-37): Long-Poll, Sofort-Typing (EC-39), Hand-off, ACK.

    Backoff (E-EC-2, #294) liegt jetzt hier: Reader pausiert bei leerem oder
    fehlgeschlagenem Poll mit exponentiellem Backoff. Pro Update wird **vor**
    dem `handoff.put` ein Sofort-Typing-Indikator gefeuert (EC-39, nur
    Privatchat), die `chat_id` in `open_chat_ids` aufgenommen und dann auf
    das ACK des Processors gewartet (EC-38: At-least-once).

    `heartbeat_path` — wenn gesetzt, wird nach jedem erfolgreichen
    `get_updates`-Rückgabe (auch leere Liste) der Unix-Timestamp atomar in
    diese Datei geschrieben (SVC-6-Ergänzung T1666). Schreibfehler werden
    geloggt und geschluckt — sie unterbrechen den Poll-Loop nicht.
    """
    offset = None
    backoff = 0.0
    while not stop_event.is_set():
        try:
            updates = tg_reader.get_updates(offset, timeout=get_updates_timeout)
        except TelegramError as e:
            if backoff == 0.0:
                backoff = _BACKOFF_START
            logging.warning(
                "getUpdates fehlgeschlagen: %s — neuer Versuch in %.0f s",
                e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_CAP)
            continue
        except Exception:
            # Reader-Daemon darf nicht still sterben — sonst sitzt der
            # Processor fuer immer in `handoff.get(...)`. stop_event wird
            # gesetzt, damit der Processor aus dem handoff.get-Loop austritt.
            # Test-Doppelungen werfen bewusst untypisierte Exceptions, um den
            # Reader zu beenden; im Live-Betrieb stoppt der Stop-Event den
            # Loop sowieso.
            logging.warning(
                "Reader-Loop: unerwartete Exception aus get_updates — "
                "Reader beendet sich, stop_event wird gesetzt",
                exc_info=True)
            stop_event.set()
            return

        # SVC-6-Ergänzung T1666: Heartbeat nach jedem erfolgreichen Poll
        # (auch leere Update-Liste = Bot lebt). Schreibfehler schlucken.
        if heartbeat_path:
            _write_heartbeat(heartbeat_path)

        if not updates:
            if backoff == 0.0:
                backoff = _BACKOFF_START
            else:
                backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_CAP)
            if backoff > 0:
                time.sleep(backoff)
            continue

        # Update(s) eingetroffen — Backoff zurücksetzen.
        backoff = 0.0
        for update in updates:
            if stop_event.is_set():
                return
            update_id = update.get("update_id", 0)
            t0 = time.monotonic()

            # EC-39: Sofort-Typing für Privatchat-Updates, VOR Hand-off.
            # Privacy-Trade-off bewusst akzeptiert (vor Auth, spec Z. 1357-1370).
            chat_id_for_typing = None
            if _is_private_message_update(update):
                chat_id_for_typing = (update["message"]["chat"] or {}).get("id")
                if chat_id_for_typing is not None:
                    _safe_send_chat_action(tg_reader, chat_id_for_typing)
                    with chat_ids_lock:
                        open_chat_ids.add(chat_id_for_typing)

            # EC-37 Hand-off: bounded Queue(maxsize=1), blockiert bis Processor
            # entnimmt. Tupel (t0, update_id, update) trägt die Pickup-Latenz
            # bis zum Processor weiter (E-EC-2).
            handoff.put((t0, update_id, update))

            # EC-38: ACK abwarten — erst nach Done-Signal Offset erhöhen.
            # At-least-once: Crash zwischen Hand-off und ACK ⇒ Telegram liefert
            # das Update beim Restart erneut.
            try:
                acked_id = ack.get()
            except Exception:  # pragma: no cover — Queue.get blockiert sonst nie
                acked_id = None
            if acked_id != update_id:
                # Schreibender Watch-Punkt — sollte nie passieren, weil Queue
                # serialisiert. Defensiv geloggt.
                logging.error(
                    "ACK-ID-Mismatch: erwartet %s, erhalten %s — "
                    "Offset wird trotzdem auf %s gesetzt",
                    update_id, acked_id, update_id + 1)
            offset = update_id + 1


def _processor_loop(ctx, handoff, ack, open_chat_ids, chat_ids_lock,
                    stop_event):
    """Processor (Hauptthread, EC-37): konsumiert die Hand-off-Queue,
    läuft `dispatch(update, ctx)` und meldet das Done-Signal über die
    ACK-Queue. `open_chat_ids` wird nach `dispatch` wieder frei — der
    Renewer hört für diesen Chat auf, weitere Typing-Indikatoren zu schicken.
    Pickup-Latenz wird hier geloggt (E-EC-2): t0 stammt aus dem Reader,
    t1 ist der Zeitpunkt nach `dispatch`.
    """
    while not stop_event.is_set():
        try:
            t0, update_id, update = handoff.get(timeout=0.5)
        except queue.Empty:
            continue
        chat_id_open = None
        if _is_private_message_update(update):
            chat_id_open = (update["message"]["chat"] or {}).get("id")
        try:
            dispatch(update, ctx)
        except Exception:  # ein Update darf den Loop nie killen
            logging.exception("Petrarbeitung eines Updates fehlgeschlagen")
        finally:
            if chat_id_open is not None:
                with chat_ids_lock:
                    open_chat_ids.discard(chat_id_open)
            latency_ms = int((time.monotonic() - t0) * 1000)
            logging.info(
                "poll event=pickup_latency count=%d latency_ms=%d",
                1, latency_ms)
            ack.put(update_id)


def _renewer_loop(tg_main, open_chat_ids, chat_ids_lock, stop_event,
                  interval=_RENEWER_INTERVAL_S):
    """Renewer-Daemon (EC-39): erneuert den Typing-Indikator alle `interval`
    Sekunden für jede `chat_id` in `open_chat_ids`. Telegram löscht das
    Signal nach ~5 s — 4-s-Tick (EC-28-Konstante) hält es lebendig, solange
    das Update in der Hand-off-Queue steht oder der Processor arbeitet.
    Tolerante Race (spec Z. 1271-1273): worst case ein Typing zuviel — der
    Telegram-Client überschreibt das mit der nächsten Bot-Antwort.
    """
    while not stop_event.wait(interval):
        with chat_ids_lock:
            chats = list(open_chat_ids)
        for chat_id in chats:
            _safe_send_chat_action(tg_main, chat_id)


def poll_loop(ctx, get_updates_timeout=30, tg_reader=None):
    """Reader/Processor/Renewer-Topologie (E-EC-2 / EC-37 / EC-38 / EC-39).

    Drei Threads:
      * **Reader** (Daemon) — Long-Poll auf `tg_reader.get_updates`, Sofort-
        Typing für Privatchat-Updates (EC-39), Hand-off pro Update, blockiert
        bis ACK vor Offset-Erhöhung (EC-38: At-least-once).
      * **Processor** (Hauptthread) — konsumiert Hand-off, ruft
        `dispatch(update, ctx)`, meldet ACK.
      * **Renewer** (Daemon) — erneuert alle 4 s den Typing-Indikator für
        jede `chat_id` in `open_chat_ids` (EC-39, EC-28-Intervall).

    `tg_reader` ist ein separater `TelegramClient` mit gleichem Token aber
    eigenem `_opener` (EC-37 spec Z. 1265-1268). `ctx.tg` (= `tg_main`)
    bleibt für Renewer, Bot-Antworten und Skill-Sends. Fehlt `tg_reader`
    (Test-Setup ohne expliziten zweiten Client), nutzt der Reader `ctx.tg`
    — das ist ausreichend, solange der Test nicht parallel auf demselben
    Opener Bot-Antworten sendet.

    Backoff (E-EC-2 / #294): Reader hält Start 1 s, Faktor 2, Cap 5 s.
    Pickup-Latenz (E-EC-2 / LOG-4): pro Update vom Reader bis Processor-
    Ende, identisches Logformat `event=pickup_latency count=N latency_ms=X`.
    """
    if tg_reader is None:
        tg_reader = ctx.tg

    # SVC-6-Ergänzung T1666: Heartbeat-Pfad einmalig auflösen; Reader schreibt
    # ihn nach jedem erfolgreichen get_updates-Poll.
    heartbeat_path = _resolve_heartbeat_path()

    handoff = queue.Queue(maxsize=1)   # (t0, update_id, update) — EC-37
    ack = queue.Queue(maxsize=1)       # update_id — Done-Signal (EC-37/EC-38)
    open_chat_ids = set()              # set[int] — EC-37/EC-39
    chat_ids_lock = threading.RLock()  # einzige RLock-Instanz, spec Z. 1269-1271
    stop_event = threading.Event()

    reader = threading.Thread(
        target=_reader_loop,
        name="poll-reader",
        args=(ctx, tg_reader, handoff, ack, open_chat_ids, chat_ids_lock,
              stop_event, get_updates_timeout, heartbeat_path),
        daemon=True)
    renewer = threading.Thread(
        target=_renewer_loop,
        name="poll-renewer",
        args=(ctx.tg, open_chat_ids, chat_ids_lock, stop_event),
        daemon=True)

    logging.info("Eltern-Chat läuft — warte auf Nachrichten.")
    reader.start()
    renewer.start()
    try:
        _processor_loop(ctx, handoff, ack, open_chat_ids, chat_ids_lock,
                        stop_event)
    finally:
        stop_event.set()


# ============================================================
#  Entrypoint
# ============================================================

def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Eltern-Chat V1")
    p.add_argument("--config", default="config.json",
                   help="Pfad zur Konfigurationsdatei (EC-15)")
    p.add_argument("--db", default="conversations.db",
                   help="Pfad zur Gesprächs-Datenbank (EC-16)")
    p.add_argument("--log-level", dest="log_level", default=None,
                   help="DEBUG | INFO | WARNING | ERROR "
                        "(überschreibt den Config-Wert, CONFIG-1)")
    # ZD-8: einheitliches Flag aus der Zugangsdaten-Komponente, damit der Bot
    # genauso wie andere Komponenten eine alternative ZD-Datei akzeptiert
    # (Test-/Debug-Workflow, Refs #131).
    from tools.zugangsdaten import add_cli_argument as _add_zd_cli_argument
    _add_zd_cli_argument(p)
    return p.parse_args(argv)


def _check_group_reception(tg, family_group_chat_id, me):
    """EC-19: warnt beim Start, wenn der Bot die Nachrichten der Familien-Gruppe
    nicht empfangen kann — er ist dort weder Administrator, noch ist sein
    Telegram-Privacy-Modus deaktiviert. Dann stellt Telegram ihm nur Kommandos
    und Antworten zu, keine bloße Erwähnung (vgl. EC-5)."""
    if me.get("can_read_all_group_messages"):
        return  # Privacy-Modus deaktiviert — der Bot empfängt alle Nachrichten.
    try:
        member = tg.get_chat_member(family_group_chat_id, me.get("id"))
    except TelegramError as e:
        logging.warning("EC-19: Empfangs-Voraussetzung nicht prüfbar: %s", e)
        return
    status = member.get("status") if isinstance(member, dict) else None
    if status not in ("administrator", "creator"):
        logging.warning(
            "EC-19: Der Bot ist in der Familien-Gruppe %s weder Administrator, "
            "noch ist sein Privacy-Modus deaktiviert — eine bloße Erwähnung "
            "erreicht ihn dort nicht. Bot zum Admin der Gruppe machen.",
            family_group_chat_id)


def build_context(cfg, db_path, zd_cli_path=None):
    """Verdrahtet aus der Konfiguration einen lauffähigen Context.

    Liegt kein Anbieter-Key vor, startet die Instanz im Onboarding-Modus
    (ONB-1): `provider` bleibt None, `onboarding` trägt den Onboarding-Zustand.

    `zd_cli_path` ist der Wert eines CLI-Flags (ZD-8, Refs #131): liegt er vor,
    überschreibt er Umgebungsvariable und Default bei der Auflösung des
    Zugangsdaten-Speicher-Pfads.
    """
    # EC-37: zwei TelegramClient-Instanzen — gleicher Token, getrennte _opener.
    # `tg` (= tg_main) trägt alle Bot-Antworten, Renewer und Skill-Sends; der
    # separate Reader-Client wird in `main()` instanziiert und durch `poll_loop`
    # gereicht. Hier reicht der eine Client für Onboarding/get_me und alle
    # Schreibwege.
    tg = TelegramClient(cfg.bot_token)
    me = tg.get_me()

    # FAA-12: in-memory Session-Registry je Privatchat. Wird vom
    # FamilieAnlegenTask gefüllt und von `handle_update` ausgelesen.
    faa_sessions = {}
    # KAV-3: analog FAA, eigene Session-Map für »Kalender verbinden«.
    kav_sessions = {}
    # TES-3: analog FAA/GAA/KAV, eigene Session-Map für »Termin eintragen«.
    tes_sessions = {}
    # TAB-12: analog TES, eigene Session-Map für »Termine aus Bild«.
    tab_sessions = {}
    # AVB/ONB-11: analog den anderen Sorten, eigene Session-Map für »Anbieter wechseln«.
    avb_sessions = {}

    # KAV-7: Zugangsdaten-Speicher als Per-Instanz-Datei (ZD-1/ZD-8). Lazy-
    # importiert, damit Tests, die `build_context` nicht aufrufen, keine
    # zugangsdaten-Abhängigkeit aufbauen müssen.
    from tools.zugangsdaten import Zugangsdaten, resolve_store_path
    zd_store = Zugangsdaten(resolve_store_path(cli_path=zd_cli_path))

    # EC-10 A2-Receipt (#841): einmalige Store-Instanz pro laufender Instanz.
    # Selbe db_path wie TelemetryStore — `a2_receipts`-Tabelle lebt in
    # `conversations.db`. Wird gleich an build_catalog weitergereicht, damit
    # FotoSendenTask und EinkaufHinzufuegenTask Bons schreiben können.
    a2_receipt_store = A2ReceiptStore(db_path)

    ctx = Context(
        tg=tg,
        bot_username=me.get("username", ""),
        family_group_chat_id=cfg.family_group_chat_id,
        context_depth=cfg.context_depth,
        provider=None,
        catalog=None,                # gleich gesetzt — braucht ctx-Verweis
        history=History(db_path),
        pending=PendingStore(),
        # EC-23/AC4 (#268): Telemetrie liegt in derselben SQLite-Datei wie der
        # Verlauf — kein zweiter SSoT, kein zweites Backup-Ziel.
        telemetry_store=TelemetryStore(db_path),
        # EC-10 A2-Receipt (#841): A2-Kassenbons liegen in derselben SQLite-Datei
        # wie task_events/provider_calls — `a2_receipts`-Tabelle wird beim ersten
        # Init via CREATE TABLE IF NOT EXISTS angelegt (a2_receipt_store.py).
        # Wird direkt an build_catalog gereicht (FotoSendenTask /
        # EinkaufHinzufuegenTask), nicht über den Context — analog der
        # Skill-Client-Instanziierung in build_catalog.
        store=OnboardingStore(zd=zd_store),
        family_group_locked=cfg.family_group_locked,
        faa_sessions=faa_sessions,
        kav_sessions=kav_sessions,
        tes_sessions=tes_sessions,
        tab_sessions=tab_sessions,
        avb_sessions=avb_sessions,
        # EC-36 Korrektur-Hook (#844): der Vor-Agent-Hook braucht denselben
        # A2ReceiptStore wie die A2-Skills (foto_senden, einkauf_hinzufuegen),
        # damit `falsch` die zuletzt geschriebenen Bons unversiegelt findet und
        # die inverse_calls deterministisch ausführen kann. Origin-URLs werden
        # für den HTTP-DELETE-Aufruf gebraucht (Buddy-Key → Origin-URL-Map im
        # Hook, siehe _BUDDY_ORIGIN_GETTERS).
        a2_receipt_store=a2_receipt_store,
        photo_origin_url=cfg.photo_origin_url or "",
        essen_origin_url=cfg.essen_origin_url or "",
    )
    # FAA-12 / GAA-5 / KAV-3: Familien-Gruppen-ID darf nach einer Migration
    # (EC-18) wechseln — der Getter liest sie zur Laufzeit aus dem Context,
    # statt sie einmal beim Bootstrap zu kopieren.
    # RAT-31 E1 (#1470): der frühere GAA-6-CAV-Hook (skills.ca_verteilung) ist
    # unter Cookie-only-hart (RAT-32) entfallen — das Onboarding stellt keine
    # CA mehr zu.
    ctx.catalog = build_catalog(
        tg, cfg.ca_pem_path,
        familie_origin_url=cfg.familie_origin_url,
        faa_sessions=faa_sessions,
        family_group_chat_id_getter=lambda: ctx.family_group_chat_id,
        # RAT-31 E6c (#1565): geraete_origin_url/gaa_sessions entfallen — die
        # geraete-Registry stirbt, »Gerät koppeln« mintet nur einen Pairing-Link.
        display_url_origin=cfg.display_url_origin,
        # GAA-3.8 / auth.md AUTH-2.a (T948): Pairing-Link-Zustellweg live.
        # pairing_bot_token = per-Instanz-Bot-Token (HMAC-Sign-Key, cfg.bot_token).
        # pairing_origin = Funnel-FQDN, unter der /auth/pair (seiten) + PWA liegen
        # (cfg.mini_app_base_url, AUTH-2 First-Party-Cookie-Origin). Leer/None →
        # GAA postet keinen Pairing-Link (E-GAA-5-Agnostik).
        pairing_bot_token=cfg.bot_token,
        pairing_origin=cfg.mini_app_base_url or None,
        zd_store_getter=lambda: zd_store,
        kav_sessions=kav_sessions,
        plan_origin_url=cfg.plan_origin_url,
        tes_sessions=tes_sessions,
        # RAT-31 E1 (#1470): panel_origin_url bleibt vestigial in der Signatur
        # (PanelAnlegenTask entfallen); paa_sessions wird nicht mehr gereicht.
        panel_origin_url=cfg.panel_origin_url,
        # PAA-3.5: Controller-URL nutzt dieselbe Hub-Origin wie die Display-URL
        # (GAA-3.7) — beide werden auf demselben Origin ausgeliefert.
        controller_url_origin=cfg.display_url_origin,
        # RZS-6 / #343: Origin des Routine-Buddys (ROUTINE-14).
        routine_origin_url=cfg.routine_origin_url,
        # EC-15 / #443: Origin des Icon-Routers (ICONS-7). Leer ⇒
        # RoutinePunkteSetzenTask wird NICHT registriert (RPS-7 AND-Guard).
        icon_origin_url=cfg.icon_origin_url,
        # FSE-7 / #393: Origin des Photo-Buddys (PHOTO-13/PHOTO-16). Leer ⇒
        # FotoSendenTask wird NICHT registriert (FSE-8 AND-Guard).
        photo_origin_url=cfg.photo_origin_url,
        # SREG-6 / #453: Origin der Seiten-Registry (SREG-3). Leer ⇒
        # SeitenUebersichtTask wird NICHT registriert (SREG-6 AND-Guard).
        seiten_origin_url=cfg.seiten_origin_url,
        # WZE-8 / GAN-7 / #503: Origin des Essens-Buddys (ESSEN-15/ESSEN-19). Leer ⇒
        # WuenscheZeigenTask + GerichtAnlegenTask werden NICHT registriert.
        essen_origin_url=cfg.essen_origin_url,
        # EZG-6 / EIN-8 / #653: Mini-App-URL für die Einkaufsliste (EZG-6).
        # Leer/None → EinkaufZeigenTask nutzt ENV-Fallback MINI_APP_EINKAUF_URL.
        mini_app_einkauf_url=cfg.mini_app_einkauf_url or None,
        # RAO-6 / T728-C: Basis-URL aller Mini-Apps (Funnel-Domain).
        # Leer/None → RoutineAnpassenOeffnenTask NICHT im Katalog (RAO-8 Guard).
        mini_app_base_url=cfg.mini_app_base_url or None,
        # SREG-7 / #476: Heim-Origin für den Übersichts-Link (SREG-5/SREG-5b).
        display_url_origin_heim=cfg.display_url_origin_heim,
        # TAB-12 / #475: Session-Map für »Termine aus Bild«.
        tab_sessions=tab_sessions,
        # AVB / ONB-11 / #639: Session-Map + Getter für den aktuellen Anbieter.
        # Ohne beide erscheint »Anbieter wechseln« nicht im Katalog (AND-Guard
        # in tasks.py). `current_provider_getter` liest den persistierten
        # Vendor-Namen aus dem ZD-Slot (`eltern-chat-provider-name`, T663
        # Welle A) — Fallback auf `cfg.provider` (Start-Wert), wenn der Slot
        # leer/fehlend ist. Damit greift die Same-Provider-Logik im Skill auch
        # nach einem Wechsel-Akt ohne Neustart (Watchdog-Folge #1021).
        avb_sessions=avb_sessions,
        current_provider_getter=lambda: (
            zd_store.get(ZD_NAME_PROVIDER_NAME) or cfg.provider),
        # TAB-5 / E-TAB-6: V1 nutzt denselben Anbieter wie der Text-Pfad
        # (cfg.provider). V2 (E-TAB-6): multimodal_* können unabhängig
        # gesetzt werden — leere Werte fallen auf den Text-Pfad zurück.
        # T1262 PR1: build_catalog baut FotoAnalyseProvider intern über den
        # Foto-Slot (`eltern-chat-anthropic-foto-analyse-api-key`, ZD-5);
        # multimodal_provider/multimodal_api_key wurden als tote Felder entfernt
        # (#1334 Rückbau).
        provider_name=cfg.provider,
        provider_api_key=cfg.provider_api_key,
        provider_model=cfg.provider_model,
        multimodal_model=getattr(cfg, "multimodal_model", "") or "",
        # HFE-9 / #729: Origin des Hörspiel-Buddys. Leer/None → HFE NICHT im
        # Katalog (AND-Guard in tasks.py).
        hoerspiel_url_origin=cfg.hoerspiel_url_origin or None,
        # RAT-17 / #910 / T954: Finn-Origin an build_catalog durchreichen,
        # damit HoerspielFolgeErzeugenTask die Mini-Map mit echtem Finn-Client
        # befüllt (kind_id="finn" → hoerspiel_url_origin_finn, AC-1).
        hoerspiel_url_origin_finn=cfg.hoerspiel_url_origin_finn or "",
        # HSP-43 / #1263: Niclas-Origin an build_catalog durchreichen, damit
        # HoerspielFolgeErzeugenTask die Mini-Map mit echtem Niclas-Client befüllt
        # (kind_id="emil" → hoerspiel_url_origin_emil, AC3).
        hoerspiel_url_origin_emil=cfg.hoerspiel_url_origin_emil or "",
        # KAQS-6 / #825: Origin des KIBuddy-Config-Endpunkts. Leer/None →
        # KibuddyAufnahmeQuelleSetzenTask NICHT im Katalog (AND-Guard KAQS-6).
        kibuddy_origin_url=cfg.kibuddy_origin_url or None,
        # EC-10 A2-Receipt (#841): Store-Instanz für FotoSendenTask /
        # EinkaufHinzufuegenTask. None → Skills laufen ohne Receipt-Schreibung
        # (Backward-Compat für Test-Kataloge).
        a2_receipt_store=a2_receipt_store,
        # WRO-8 / #1094: Origin des Wetter-Buddys (Mini-App-URL = Origin +
        # /display/wetter/regeln, WRO-5). Leer/None → WetterRegelnOeffnenTask
        # NICHT im Katalog (AND-Guard in tasks.py).
        wetter_origin_url=cfg.wetter_origin_url or None,
    )

    if cfg.provider_api_key:
        # KI-Modus — Anbieter steht; die Familien-Gruppe muss gesetzt sein (EC-2).
        if not cfg.family_group_chat_id:
            raise config_mod.ConfigError(
                "Anbieter-Key vorhanden, aber keine Familien-Gruppe — "
                "Onboarding unvollständig?")
        # T1085 PR2: Chat-Agent-Pfad über tools/llm (LibAgentAdapter). Der
        # Adapter bildet den Brand-Vendor-Slot selbst und die Lib holt den Key
        # aus dem Zugangsdaten-Speicher — der KI-Modus-Guard (cfg.provider_api_key)
        # oben bleibt das Schaltkriterium (Onboarding-Modus ⇒ kein Adapter).
        # Effektives Modell unverändert (provider_model bzw. Anbieter-Default).
        ctx.provider = get_lib_agent_provider(cfg.provider, cfg.provider_model)
        # EC-19: kann der Bot die Nachrichten der Familien-Gruppe empfangen?
        _check_group_reception(tg, cfg.family_group_chat_id, me)
    else:
        # Onboarding-Modus (ONB-1) — der Bot richtet sich per Chat selbst ein.
        ctx.onboarding = OnboardingState(
            provider_name=cfg.provider,
            provider_model=cfg.provider_model)
    return ctx


def _secret_preflight(cfg):
    """SVC-7 — Startup-Secret-Preflight für die LLM-Pflicht-Slots (#1493).

    Prüft VOR `build_context` (das den Chat-Agent-Adapter eager baut), ob die
    beim Boot boot-kritischen Slots im Zugangsdaten-Speicher PRÄSENT sind. Fehlt
    ein Pflicht-Slot: Log-Zeile 'FEHLT: <slot>' + `sys.exit(1)` — statt eines
    rohen `LLMCapabilityError` mitten im Boot (die #1509-Crash-Klasse:
    `LibAgentAdapter.__init__` → `get_agent(slot=…)` → `_build_vendor` →
    `resolve_api_key` None → Raise).

    Nur PRÄSENZ (SVC-7) — kein Anbieter-Call, keine Capability-Prüfung.

    Config-gated: geprüft wird ausschließlich der Slot, den `build_context` beim
    aktuellen Boot auch wirklich eager braucht:
      - Der Chat-Agent-Slot (`litellm_slot_for_provider("eltern-chat", cfg.provider)`) NUR im
        KI-Modus (`cfg.provider_api_key` gesetzt). Im Onboarding-Modus baut
        `build_context` KEINEN Adapter → kein Slot nötig.
    Der Foto-Analyse-Slot (`FOTO_ANALYSE_SLOT`) ist bewusst NICHT boot-kritisch:
    `build_catalog` fängt seinen `LLMCapabilityError` bereits ab und schaltet nur
    »Termine aus Bild« ab (tasks.py:604) — ein fehlender Foto-Slot bootet weiter
    (graceful degradation), darum darf der Preflight ihn nicht boot-fatal machen.

    Das Bot-Token ist bereits in `config.resolve` Pflicht (ConfigError EC-15,
    config.py:322) — hier nicht doppelt geprüft; der Boot kommt ohne Token gar
    nicht bis zum Preflight.
    """
    from tools.llm import litellm_slot_for_provider, slot_present

    if cfg.provider_api_key:
        # KI-Modus: build_context baut den LibAgentAdapter eager (main:1217) —
        # der Slot MUSS präsent sein, sonst Boot-Crash. Unbekannter Provider ist
        # ein Konfig-Fehler (spiegelt den KeyError aus litellm_slot_for_provider,
        # aber sichtbar hier als FEHLT-Zeile statt rohem KeyError). T1492: Naht.
        try:
            slot = litellm_slot_for_provider("eltern-chat", cfg.provider)
        except KeyError:
            slot = None
        if slot is None:
            logging.critical(
                "FEHLT: gültiger Anbieter — provider=%r hat keinen LLM-Slot "
                "(SVC-7/#1493)", cfg.provider)
            sys.exit(1)
        # `slot_present` = bool(resolve_api_key): ein LEERER Slot-Wert zählt als
        # nicht präsent. #1510-Härtung des Probe-Crash-Fensters: bricht das
        # Onboarding/der Wechsel zwischen Probe-Schreib und Ping ab, räumt
        # `litellm_probe_delete` den Slot auf den leeren String — dieser Boot-
        # Check fängt genau diesen present-but-invalid-Rest (leerer Slot → FEHLT
        # → Exit → nächster Start läuft ins Onboarding, statt mit kaputtem Key
        # in den KI-Modus zu booten). Ein nicht-leerer, aber inhaltlich falscher
        # Key bleibt SVC-7-konform ungeprüft (kein Anbieter-Call am Boot) und
        # fällt erst im ersten Turn — bewusst (RATIFIZIERT 20260728-1510).
        if not slot_present(slot):
            logging.critical(
                "FEHLT: %s — Chat-Agent-Slot fehlt/leer im Zugangsdaten-Speicher "
                "(provider=%s, KI-Modus) (SVC-7/#1493, #1510-Probe-Rest)",
                slot, cfg.provider)
            sys.exit(1)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    # LOG-4 (#166): zentraler Setup statt eigenem basicConfig. Bootstrap-Level
    # ist der CLI-Wert oder INFO — damit Config-Fehler unten bereits mit dem
    # LOG-1-Format protokolliert werden. Nach erfolgreichem Resolve setzen
    # wir auf den Config-Wert um (CLI-Flag > Config > Default; CONFIG-1,
    # EC-15-Schema).
    logsetup.setup(args.log_level or "INFO")
    try:
        cfg = config_mod.resolve(args.config)
        # SVC-7 (#1493): LLM-Pflicht-Slots auf Präsenz prüfen, BEVOR build_context
        # den Chat-Agent-Adapter eager baut — fehlender Slot bricht hier sichtbar
        # (FEHLT: <slot> + exit) statt als roher LLMCapabilityError im Boot.
        _secret_preflight(cfg)
        ctx = build_context(cfg, args.db,
                            zd_cli_path=args.zugangsdaten_file)
    except config_mod.ConfigError as e:
        logging.error("Konfigurationsfehler: %s", e)
        return 2
    # CLI-Flag (Test-Werkzeug, CONFIG-1) überschreibt den Config-Wert.
    logsetup.setup(args.log_level or cfg.log_level)
    if ctx.onboarding is not None:
        logging.info("Bot @%s — Onboarding-Modus: warte auf KI-Anbieter-Key (ONB-1).",
                     ctx.bot_username)
    else:
        logging.info("Bot @%s, Anbieter '%s', Familien-Gruppe %s",
                     ctx.bot_username, cfg.provider, ctx.family_group_chat_id)
    # EC-37: zweiter TelegramClient für Reader/Long-Poll (eigener _opener).
    # Selber Token wie ctx.tg, aber unabhängige HTTP-Verbindung — der lange
    # getUpdates-Aufruf blockiert die Bot-Sende-Pfade nicht.
    tg_reader = TelegramClient(cfg.bot_token)
    poll_loop(ctx, tg_reader=tg_reader)
    return 0


if __name__ == "__main__":
    sys.exit(main())
