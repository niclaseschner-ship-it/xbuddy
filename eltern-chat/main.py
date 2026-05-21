#!/usr/bin/env python3
"""XBuddy Eltern-Chat V1 — siehe specs/platform/eltern-chat.md (Refs #27).

Eigener Prozess, eigener Telegram-Kanal per Polling. Diese Datei ist die
ORCHESTRIERUNG: sie nimmt Nachrichten entgegen und verdrahtet die Bausteine.
Die Sicherheits-Gates liegen hier — außerhalb des Agent-Loops (E-EC-4):

  eingehende Nachricht
    → EC-5  Ansprache-Prüfung (Gruppe: nur bei Mention/Antwort an den Bot)
    → EC-2  Berechtigung (authz, Live-Mitgliedschaftsprüfung)
    → EC-10 Bestätigung (confirm) — ist es ein Bestätigungswort?
    → sonst: Agent-Loop (agent), Antwort/Vorschlag, Verlauf persistieren

agent.py kennt weder authz noch confirm — der LLM kann die Gates nicht umgehen.
"""

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass

# eltern-chat/ liegt auf sys.path, wenn main.py direkt gestartet wird; für den
# Import-aus-Tests-Fall sorgt tests/conftest.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent
import authz
import config as config_mod
import confirm
from confirm import PendingProposal, PendingStore
from history import History
from model import ImageBlock, Message, ProviderError, TextBlock
from providers import get_provider
from tasks import build_catalog
from telegram import TelegramClient, TelegramError


# Klartext-Antworten.
_PROVIDER_DOWN = ("Ich kann deine Anfrage gerade nicht bearbeiten — der "
                  "KI-Dienst ist nicht erreichbar. Bitte versuch es gleich "
                  "noch einmal.")   # EC-14
_TASK_GONE = "Diese Aufgabe ist nicht mehr verfügbar."
_TASK_FAILED = "Die Aufgabe konnte nicht ausgeführt werden: %s"


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
    provider: object           # KI-Anbieter-Adapter (oder Doppelung)
    catalog: object            # tasks.Catalog
    history: object            # history.History
    pending: object            # confirm.PendingStore


# ============================================================
#  Orchestrierung
# ============================================================

def handle_update(update, ctx):
    """Petrarbeitet ein einzelnes Telegram-Update."""
    msg = ctx.tg.extract_message(update, ctx.bot_username)
    if msg is None:
        return

    # EC-5: In einer Gruppe reagiert das System nur, wenn es ausdrücklich
    # angesprochen wird. Im Privatchat bezieht sich jede Nachricht auf den Bot.
    if msg.chat_type in ("group", "supergroup"):
        if not (msg.mentions_bot or msg.reply_to_from_bot):
            return

    # EC-2/EC-3: Berechtigung — Live-Mitgliedschaftsprüfung. Nicht-Mitglieder
    # werden ohne Antwort ignoriert. Dieses Gate liegt außerhalb des Agenten.
    if not authz.is_authorized(ctx.tg, ctx.family_group_chat_id, msg.from_user_id):
        logging.info("Nachricht von nicht-berechtigtem Absender %s ignoriert",
                     msg.from_user_id)
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


def _run_agent(msg, ctx):
    """Lässt den Agenten eine Anfrage bearbeiten und sendet das Ergebnis."""
    history = ctx.history.load(msg.chat_id, ctx.context_depth)
    user_message = _user_message_from(msg)

    try:
        result = agent.run_turn(history, user_message, ctx.provider, ctx.catalog)
    except ProviderError:
        # EC-14: klarer Hinweis, sauberer Abbruch — keine halbfertige Aufgabe.
        _send(ctx, msg.chat_id, _PROVIDER_DOWN)
        return

    # Anfrage erst nach erfolgreichem Lauf in den Verlauf aufnehmen.
    ctx.history.append(msg.chat_id, user_message)

    if result.proposal is not None:
        # EC-10: schreibende Aufgabe — Vorschlag vorlegen, auf Bestätigung warten.
        text = _format_proposal(result.proposal)
        sent = _send(ctx, msg.chat_id, text, reply_to_message_id=msg.message_id)
        if sent is not None:
            ctx.pending.add(PendingProposal(
                chat_id=msg.chat_id,
                proposal_message_id=sent.get("message_id"),
                task_name=result.pending_call.task,
                arguments=result.pending_call.arguments))
        ctx.history.append(msg.chat_id, Message("assistant", [TextBlock(text)]))
        return

    _send(ctx, msg.chat_id, result.reply_text)
    ctx.history.append(msg.chat_id, Message("assistant", [TextBlock(result.reply_text)]))


def _execute_confirmed(pending, msg, ctx):
    """Führt eine bestätigte schreibende Aufgabe aus (nach EC-10-Bestätigung)."""
    task = ctx.catalog.get(pending.task_name)
    if task is None:
        _send(ctx, msg.chat_id, _TASK_GONE, reply_to_message_id=msg.message_id)
        return
    try:
        result = task.execute(pending.arguments)
    except Exception as e:  # noqa: BLE001 — Aufgabe isoliert melden
        logging.warning("Ausführung von '%s' fehlgeschlagen: %s", pending.task_name, e)
        _send(ctx, msg.chat_id, _TASK_FAILED % e, reply_to_message_id=msg.message_id)
        return
    _send(ctx, msg.chat_id, result, reply_to_message_id=msg.message_id)
    ctx.history.append(msg.chat_id, Message("assistant", [TextBlock(result)]))


def _user_message_from(msg):
    """Baut aus einer eingehenden Nachricht die kanonische Nutzer-Nachricht."""
    blocks = []
    if msg.text:
        blocks.append(TextBlock(msg.text))
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

def poll_loop(ctx, get_updates_timeout=30):
    """Liest fortlaufend Updates und petrarbeitet sie (E-EC-2: Polling)."""
    offset = None
    logging.info("Eltern-Chat läuft — warte auf Nachrichten.")
    while True:
        try:
            updates = ctx.tg.get_updates(offset, timeout=get_updates_timeout)
        except TelegramError as e:
            logging.warning("getUpdates fehlgeschlagen: %s — neuer Versuch in 3 s", e)
            time.sleep(3)
            continue
        for update in updates:
            offset = update.get("update_id", 0) + 1
            try:
                handle_update(update, ctx)
            except Exception:  # noqa: BLE001 — ein Update darf den Loop nie killen
                logging.exception("Petrarbeitung eines Updates fehlgeschlagen")


# ============================================================
#  Entrypoint
# ============================================================

def parse_args(argv):
    p = argparse.ArgumentParser(description="XBuddy Eltern-Chat V1")
    p.add_argument("--config", default="config.json",
                   help="Pfad zur Konfigurationsdatei (EC-15)")
    p.add_argument("--db", default="conversations.db",
                   help="Pfad zur Gesprächs-Datenbank (EC-16)")
    p.add_argument("--log-level", dest="log_level", default="INFO",
                   help="DEBUG | INFO | WARNING | ERROR")
    return p.parse_args(argv)


def build_context(cfg, db_path):
    """Verdrahtet aus der Konfiguration einen lauffähigen Context."""
    tg = TelegramClient(cfg.bot_token)
    me = tg.get_me()
    bot_username = me.get("username", "")
    provider = get_provider(cfg.provider, cfg.provider_api_key, cfg.provider_model)
    return Context(
        tg=tg,
        bot_username=bot_username,
        family_group_chat_id=cfg.family_group_chat_id,
        context_depth=cfg.context_depth,
        provider=provider,
        catalog=build_catalog(),
        history=History(db_path),
        pending=PendingStore(),
    )


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = config_mod.resolve(args.config)
    except config_mod.ConfigError as e:
        logging.error("Konfigurationsfehler: %s", e)
        return 2
    ctx = build_context(cfg, args.db)
    logging.info("Bot @%s, Anbieter '%s', Familien-Gruppe %s",
                 ctx.bot_username, cfg.provider, cfg.family_group_chat_id)
    poll_loop(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
