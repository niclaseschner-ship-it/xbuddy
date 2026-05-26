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
import sys
import time
from dataclasses import dataclass

# eltern-chat/ liegt auf sys.path, wenn main.py direkt gestartet wird; für den
# Import-aus-Tests-Fall sorgt tests/conftest.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Repo-Wurzel auf den Importpfad — der Bot konsumiert die Public-API der
# zentralen Komponente `zugangsdaten` (für die Kalender-Verbinden-Skill,
# analog plan/main.py). Im systemd-Setup ist WorkingDirectory=eltern-chat/,
# damit `from zugangsdaten import …` ohne PYTHONPATH funktioniert.
_REPO_ROOT_FOR_IMPORTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT_FOR_IMPORTS not in sys.path:
    sys.path.insert(0, _REPO_ROOT_FOR_IMPORTS)

import agent
import authz
import config as config_mod
import confirm
import onboarding
from confirm import PendingProposal, PendingStore
from history import History
from model import ImageBlock, Message, ProviderError, TextBlock
from onboarding import OnboardingState
from onboarding_store import OnboardingStore
from providers import get_provider
from tasks import TurnContext, build_catalog
from telegram import ChatMigratedError, TelegramClient, TelegramError


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
    provider: object           # KI-Anbieter-Adapter (oder Doppelung); None im Onboarding-Modus
    catalog: object            # tasks.Catalog
    history: object            # history.History
    pending: object            # confirm.PendingStore
    store: object = None               # onboarding_store.OnboardingStore — Persistenz der Familien-Gruppe (ONB-5, EC-18)
    family_group_locked: bool = False  # True ⇒ Familien-Gruppe per Env/Config gesetzt, Vorrang (ONB-6, EC-18)
    onboarding: object = None  # onboarding.OnboardingState — None ⇒ KI-Modus (ONB-1)
    faa_sessions: dict = None  # FAA-12: laufende »Familie anlegen«-Sessions (chat_id → FaaSession)
    gaa_sessions: dict = None  # GAA-5: laufende »Gerät anlegen«-Sessions (chat_id → GaaSession)
    kav_sessions: dict = None  # KAV-3: laufende »Kalender verbinden«-Sessions (chat_id → KavSession)


# ============================================================
#  Orchestrierung
# ============================================================

def handle_update(update, ctx):
    """Petrarbeitet ein einzelnes Telegram-Update."""
    msg = ctx.tg.extract_message(update, ctx.bot_username)
    if msg is None:
        return

    # FAA-12: läuft eine »Familie anlegen«-Session in diesem Privatchat,
    # gehen Privatchat-Nachrichten an die Session statt zum Agenten —
    # die Konversation gehört der Funktion, bis sie endet.
    if ctx.faa_sessions is not None and msg.chat_type == "private":
        session = ctx.faa_sessions.get(msg.chat_id)
        if session is not None and not session.is_finished():
            from skills.familie_anlegen_task import make_faa_input
            session.deliver(make_faa_input(msg))
            return

    # GAA-5: analog FAA-12 für »Gerät anlegen«-Sessions — eine laufende
    # GAA-Session beansprucht den Privatchat bis zum Ende.
    if ctx.gaa_sessions is not None and msg.chat_type == "private":
        session = ctx.gaa_sessions.get(msg.chat_id)
        if session is not None and not session.is_finished():
            from skills.geraet_anlegen_task import make_gaa_input
            session.deliver(make_gaa_input(msg))
            return

    # KAV-3 / KAV-6: analog FAA-12 / GAA-5 für »Kalender verbinden«-Sessions
    # — eine laufende KAV-Session beansprucht den Privatchat bis zum Ende
    # (Aufklärungstext + Login-Link + Code-Empfang).
    if ctx.kav_sessions is not None and msg.chat_type == "private":
        session = ctx.kav_sessions.get(msg.chat_id)
        if session is not None and not session.is_finished():
            from skills.kalender_verbinden_task import make_kav_input
            session.deliver(make_kav_input(msg))
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

    # F2: deterministischer Ausführungs-Kontext, getrennt vom Modell. Der
    # Agent-Loop reicht ihn unverändert an die Aufgaben durch (#63).
    turn_context = TurnContext(
        chat_id=msg.chat_id,
        from_user_id=msg.from_user_id,
        private_chat_id=(msg.chat_id if msg.chat_type == "private"
                         else msg.from_user_id))

    # Issue #93: Typing-Indikator vor dem Provider-Aufruf — bei mehreren
    # Sekunden Provider-Latenz wirkt der Bot sonst eingefroren. Der Wrapper
    # `TelegramClient.send_chat_action` schluckt Telegram-Fehler bereits
    # (Komfort, kein Gate). Der zusätzliche try/except hier ist eine doppelte
    # Sicherung — der Indikator darf den Turn unter keinen Umständen blockieren.
    try:
        ctx.tg.send_chat_action(msg.chat_id, "typing")
    except TelegramError as e:
        logging.warning("Typing-Indikator-Aufruf hat trotz Wrapper-Schluck "
                        "geworfen: %s", e)

    try:
        result = agent.run_turn(history, user_message, ctx.provider,
                                ctx.catalog, turn_context)
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
    turn_context = TurnContext(
        chat_id=msg.chat_id,
        from_user_id=msg.from_user_id,
        private_chat_id=(msg.chat_id if msg.chat_type == "private"
                         else msg.from_user_id))
    try:
        result = task.execute(pending.arguments, turn_context)
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
                dispatch(update, ctx)
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
    p.add_argument("--store", default="onboarding-store.json",
                   help="Pfad zum Onboarding-Speicher (ONB-5)")
    p.add_argument("--log-level", dest="log_level", default="INFO",
                   help="DEBUG | INFO | WARNING | ERROR")
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


def build_context(cfg, db_path, store_path):
    """Verdrahtet aus der Konfiguration einen lauffähigen Context.

    Liegt kein Anbieter-Key vor, startet die Instanz im Onboarding-Modus
    (ONB-1): `provider` bleibt None, `onboarding` trägt den Onboarding-Zustand.
    """
    tg = TelegramClient(cfg.bot_token)
    me = tg.get_me()

    # FAA-12: in-memory Session-Registry je Privatchat. Wird vom
    # FamilieAnlegenTask gefüllt und von `handle_update` ausgelesen.
    faa_sessions = {}
    # GAA-5: analog FAA, eigene Session-Map für die »Gerät anlegen«-Aufgabe.
    gaa_sessions = {}
    # KAV-3: analog FAA/GAA, eigene Session-Map für »Kalender verbinden«.
    kav_sessions = {}

    # KAV-7: Zugangsdaten-Speicher als Per-Instanz-Datei (ZD-1/ZD-8). Lazy-
    # importiert, damit Tests, die `build_context` nicht aufrufen, keine
    # zugangsdaten-Abhängigkeit aufbauen müssen.
    from zugangsdaten import Zugangsdaten, resolve_store_path
    zd_store = Zugangsdaten(resolve_store_path())

    ctx = Context(
        tg=tg,
        bot_username=me.get("username", ""),
        family_group_chat_id=cfg.family_group_chat_id,
        context_depth=cfg.context_depth,
        provider=None,
        catalog=None,                # gleich gesetzt — braucht ctx-Verweis
        history=History(db_path),
        pending=PendingStore(),
        store=OnboardingStore(store_path),
        family_group_locked=cfg.family_group_locked,
        faa_sessions=faa_sessions,
        gaa_sessions=gaa_sessions,
        kav_sessions=kav_sessions,
    )
    # FAA-12 / GAA-5 / KAV-3: Familien-Gruppen-ID darf nach einer Migration
    # (EC-18) wechseln — der Getter liest sie zur Laufzeit aus dem Context,
    # statt sie einmal beim Bootstrap zu kopieren.
    # GAA-6: CAV-Hook — bindet die CA-Verteilung an den Privatchat des
    # Aufrufers. GAA bleibt CAV-agnostisch (E-GAA-5), die Orchestrierung
    # verdrahtet die beiden Funktionen.
    import skills.ca_verteilung as _cav

    def _cav_hook(os_wert, private_chat_id, _user_id):
        # GAA-6/CAV-5 (#95): das von der GAA erfragte Betriebssystem reicht
        # die Orchestrierung an die CA-Verteilung weiter — sie liefert dann
        # nur den passenden Anleitungs-Abschnitt aus. Wirft die CAV bei einem
        # unbekannten Wert (z. B. `linux`, das die CA-Anleitung in V1 nicht
        # abdeckt), fängt sie der GAA-Hook-Wrapper auf (geraet_anlegen.py).
        _cav.verteile_ca(tg, private_chat_id, cfg.ca_pem_path, geraet=os_wert)

    ctx.catalog = build_catalog(
        tg, cfg.ca_pem_path,
        family_registry_path=cfg.family_registry_path,
        faa_sessions=faa_sessions,
        family_group_chat_id_getter=lambda: ctx.family_group_chat_id,
        geraete_registry_path=cfg.geraete_registry_path,
        gaa_sessions=gaa_sessions,
        cav_call_hook=_cav_hook,
        display_url_origin=cfg.display_url_origin,
        zd_store_getter=lambda: zd_store,
        kav_sessions=kav_sessions,
        plan_json_path=cfg.plan_json_path)

    if cfg.provider_api_key:
        # KI-Modus — Anbieter steht; die Familien-Gruppe muss gesetzt sein (EC-2).
        if not cfg.family_group_chat_id:
            raise config_mod.ConfigError(
                "Anbieter-Key vorhanden, aber keine Familien-Gruppe — "
                "Onboarding unvollständig?")
        ctx.provider = get_provider(cfg.provider, cfg.provider_api_key,
                                    cfg.provider_model)
        # EC-19: kann der Bot die Nachrichten der Familien-Gruppe empfangen?
        _check_group_reception(tg, cfg.family_group_chat_id, me)
    else:
        # Onboarding-Modus (ONB-1) — der Bot richtet sich per Chat selbst ein.
        ctx.onboarding = OnboardingState(
            provider_name=cfg.provider,
            provider_model=cfg.provider_model)
    return ctx


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = config_mod.resolve(args.config, args.store)
        ctx = build_context(cfg, args.db, args.store)
    except config_mod.ConfigError as e:
        logging.error("Konfigurationsfehler: %s", e)
        return 2
    if ctx.onboarding is not None:
        logging.info("Bot @%s — Onboarding-Modus: warte auf KI-Anbieter-Key (ONB-1).",
                     ctx.bot_username)
    else:
        logging.info("Bot @%s, Anbieter '%s', Familien-Gruppe %s",
                     ctx.bot_username, cfg.provider, ctx.family_group_chat_id)
    poll_loop(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
