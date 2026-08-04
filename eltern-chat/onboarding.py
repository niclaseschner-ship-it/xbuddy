"""Onboarding-Flow — siehe specs/platform/eltern-chat-onboarding.md (Refs #33).

Der deterministische, hart-codierte Weg einer frischen Instanz von »kein
KI-Zugang« zu »KI aktiv«. Zu diesem Zeitpunkt steht noch kein Sprachmodell zur
Verfügung — daher kein LLM, nur feste Nachrichten und feste Abläufe (E-ONB-1).

Ablauf: Bot wird einer Gruppe hinzugefügt (ONB-2) → Einstiegs-Nachricht →
Key-Eingabe im Privatchat (ONB-3) → Validierung durch probeweises Speichern im
litellm-Slot + Motor-Ping (ONB-4, #1510: der Speicherschritt ONB-5 verschmilzt
mit der Validierung) → Bindung der Familien-Gruppe (ONB-6) → Moduswechsel in den
KI-Modus (ONB-7).
"""

import logging
from dataclasses import dataclass

import authz
from model import GenerationRequest, Message, ProviderError, TextBlock
from providers import get_lib_agent_provider
from telegram import TelegramError

# ============================================================
#  Hart-codierte Nachrichten (E-ONB-1)
# ============================================================

ENTRY_MESSAGE = (
    "👋 Hallo! Ich bin euer XBuddy-Bot — aber noch nicht schlau: mir fehlt "
    "der Zugang zu einer KI. Den richtet ihr einmalig ein, dann bin ich für "
    "euch da.\n\n"
    "Ich nutze dafür Claude von Anthropic. So kommt ihr an den Schlüssel:\n\n"
    "1) Öffnet im Browser console.anthropic.com und legt ein Konto an "
    "(oder meldet euch an).\n"
    "2) Hinterlegt unter »Billing« eine Zahlungsmethode und ladet ein kleines "
    "Startguthaben auf — abgerechnet wird je Anfrage, für den Anfang genügt "
    "der Mindestbetrag.\n"
    "3) Geht auf »API Keys« und erstellt mit »Create Key« einen neuen "
    "Schlüssel (Name z. B. »XBuddy«). Kopiert ihn sofort — er beginnt mit "
    "»sk-ant-« und wird nur ein einziges Mal angezeigt.\n"
    "4) Öffnet den Privatchat mit mir (tippt meinen Namen an) und schickt mir "
    "den Schlüssel dort als Nachricht.\n\n"
    "⚠️ Den Schlüssel bitte NUR im Privatchat mit mir senden — niemals hier "
    "in der Gruppe, sonst sehen ihn alle Mitglieder. Ich prüfe ihn sofort und "
    "sage euch Bescheid."
)

NEED_GROUP_FIRST = (
    "Bevor es losgeht: Füg mich bitte zuerst zu eurer Familien-Gruppe hinzu. "
    "Dort starte ich die Einrichtung — diese Gruppe wird dann eure "
    "XBuddy-Familien-Gruppe."
)

ASK_FOR_KEY = (
    "Schick mir bitte deinen KI-Anbieter-Schlüssel als Nachricht — für Claude "
    "beginnt er mit »sk-ant-«. Ich prüfe ihn sofort."
)

KEY_INVALID = (
    "Hm — mit diesem Schlüssel komme ich nicht durch (ungültig oder der "
    "Anbieter ist gerade nicht erreichbar). Bitte prüf ihn und schick ihn mir "
    "noch einmal."
)

KEY_OK_PRIVATE = (
    "Geschafft — der Schlüssel passt. 🎉 Ich bin jetzt schlau und für euch da. "
    "Schreib mir einfach in der Familien-Gruppe."
)

DONE_GROUP = (
    "✅ Einrichtung abgeschlossen — ich bin jetzt für euch da! Sprecht mich "
    "hier in der Gruppe an (oder schreibt mir privat), wann immer ihr etwas "
    "braucht."
)

# Minimaler Inhalt für den Validierungs-Aufruf (ONB-4).
_VALIDATION_SYSTEM = "Antworte mit einem einzigen Wort."
_VALIDATION_PING = "ping"

# ONB-3: Heuristik, ob eine Privatnachricht eine Schlüssel-Eingabe ist —
# anbieter-neutral: ein langes, zusammenhängendes Token ohne Leerzeichen. Eine
# Begrüßung oder Frage ist das typischerweise nicht.
_MIN_KEY_LENGTH = 20


@dataclass
class OnboardingState:
    """Zustand des Onboardings einer Instanz.

    `pending_group_chat_id` ist die Gruppe, in der das Onboarding begann — sie
    wird beim Abschluss zur Familien-Gruppe (ONB-6). Sie wird nur im Speicher
    gehalten: nach einem Neustart genügt es, den Bot erneut anzusprechen (ONB-2).
    Der Onboarding-Speicher und die Gruppen-Sperre liegen am Context — eine
    Wahrheitsquelle für beide Modi.
    """
    provider_name: str
    provider_model: str
    pending_group_chat_id: object = None


def handle_update(update, ctx):
    """Verarbeitet ein Update im Onboarding-Modus (ONB-1).

    `ctx` ist der laufende Context; bei erfolgreichem Abschluss setzt diese
    Funktion `ctx.provider`/`ctx.family_group_chat_id` und `ctx.onboarding`
    auf den KI-Modus um.
    """
    st = ctx.onboarding

    # ONB-2: Bot wurde einer Gruppe hinzugefügt → Einstiegs-Nachricht.
    added_chat_id = ctx.tg.extract_bot_added(update)
    if added_chat_id is not None:
        st.pending_group_chat_id = added_chat_id
        logging.info("Onboarding: Bot zu Gruppe %s hinzugefügt — "
                     "Einstiegs-Nachricht (ONB-2)", added_chat_id)
        _send(ctx, added_chat_id, ENTRY_MESSAGE)
        return

    msg = ctx.tg.extract_message(update, ctx.bot_username)
    if msg is None:
        return

    # In einer Gruppe: im Onboarding-Modus bleibt der Bot nie stumm — jede
    # Gruppennachricht wird mit der Einstiegs-Nachricht beantwortet, nicht nur
    # die ausdrückliche Ansprache (ONB-2, E-ONB-6). So hängt der Erstkontakt
    # nicht an der Erwähnungs-Erkennung. Nach dem Abschluss gilt wieder EC-5.
    if msg.chat_type in ("group", "supergroup"):
        st.pending_group_chat_id = msg.chat_id
        logging.info("Onboarding: Gruppennachricht in %s — "
                     "Einstiegs-Nachricht (ONB-2)", msg.chat_id)
        _send(ctx, msg.chat_id, ENTRY_MESSAGE)
        return

    # Privatchat — hier läuft die Key-Eingabe (ONB-3).
    if st.pending_group_chat_id is None:
        # Es ist noch keine Onboarding-Gruppe bekannt — ohne sie lässt sich die
        # Familien-Gruppe nicht binden und der Absender nicht prüfen.
        _send(ctx, msg.chat_id, NEED_GROUP_FIRST)
        return

    # Berechtigung: nur Mitglieder der Onboarding-Gruppe dürfen einrichten
    # (analog EC-2, live geprüft).
    if not authz.is_authorized(ctx.tg, st.pending_group_chat_id, msg.from_user_id):
        logging.info("Onboarding: Privatnachricht von Nicht-Mitglied %s ignoriert",
                     msg.from_user_id)
        return

    key = (msg.text or "").strip()
    if not _looks_like_key(key):
        # ONB-3: keine Schlüssel-Eingabe (Begrüßung, Frage …) — der Bot bleibt
        # nie stumm und meldet nicht fälschlich »ungültig«, sondern leitet an.
        _send(ctx, msg.chat_id, ASK_FOR_KEY)
        return

    # ONB-4: Validierung — probeweise in den litellm-Slot schreiben, über den
    # Motor pingen, bei Fehler wieder abräumen (#1510, RATIFIZIERT 20260728).
    logging.info("Onboarding: Key im Privatchat empfangen — Validierung läuft (ONB-4)")
    provider = _validate_key(ctx.store, st.provider_name, st.provider_model, key)
    if provider is None:
        logging.info("Onboarding: Key-Validierung fehlgeschlagen — bleibe im Onboarding-Modus")
        _send(ctx, msg.chat_id, KEY_INVALID)
        return

    _complete(ctx, provider)
    _send(ctx, msg.chat_id, KEY_OK_PRIVATE)


def _looks_like_key(text):
    """ONB-3: True, wenn `text` wie ein API-Schlüssel aussieht — ein
    zusammenhängendes Token ohne Leerzeichen, ausreichend lang. So lässt sich
    eine Schlüssel-Eingabe von normaler Chat-Nachricht unterscheiden."""
    return (len(text) >= _MIN_KEY_LENGTH
            and not any(ch.isspace() for ch in text))


def _validate_key(store, provider_name, provider_model, key):
    """ONB-4: prüft den Key mit einem minimalen Aufruf gegen den Motor (#1510).

    Der Key wird PROBEWEISE in den litellm-Slot des Anbieters geschrieben
    (`store.litellm_probe_write`), dann feuert der reguläre Motor-Adapter
    (`get_lib_agent_provider`, der den Key selbst aus dem Slot holt, ZD-5) einen
    Minimal-Ping. Gültig → der Slot bleibt gefüllt (er IST damit der
    persistierte Key, der separate ONB-5/ONB-12-Schreibschritt verschmilzt) und
    das Adapter-Objekt kommt zurück. Ungültig → der Slot wird wieder abgeräumt
    (`litellm_probe_delete`), Rückgabe None. Der Key wird nie geloggt (ONB-8).
    """
    try:
        store.litellm_probe_write(provider_name, key)
    except Exception as e:  # z. B. unbekannter Anbieter-Name (KeyError)
        logging.warning("Key-Validierung: Probe-Schreiben fehlgeschlagen: %s", e)
        return None
    try:
        provider = get_lib_agent_provider(provider_name, provider_model)
        provider.generate(GenerationRequest(
            system=_VALIDATION_SYSTEM,
            messages=[Message("user", [TextBlock(_VALIDATION_PING)])],
            task_defs=[]))
        return provider
    except ProviderError:
        store.litellm_probe_delete(provider_name)
        return None
    except Exception as e:  # z. B. LLMCapabilityError, unbekannter Anbieter
        logging.warning("Key-Validierung fehlgeschlagen: %s", e)
        store.litellm_probe_delete(provider_name)
        return None


def _complete(ctx, provider):
    """ONB-6/7: Familien-Gruppe binden, Modus wechseln (#1510).

    Der Key ist bereits persistent im litellm-Slot (die ONB-4-Validierung ließ
    ihn dort stehen) — kein separater `store.save(provider_api_key=...)`-Schritt
    mehr (ONB-5-Schreibschritt verschmilzt mit ONB-4).
    """
    st = ctx.onboarding

    # ONB-6: Onboarding-Gruppe als Familien-Gruppe binden — außer eine
    # Env-/Config-Bindung hat Vorrang.
    if not ctx.family_group_locked:
        ctx.family_group_chat_id = str(st.pending_group_chat_id)
        ctx.store.save(family_group_chat_id=ctx.family_group_chat_id)

    # ONB-7: Moduswechsel in den KI-Modus — ab jetzt gelten EC-4 ff.
    ctx.provider = provider
    ctx.onboarding = None
    logging.info("Onboarding abgeschlossen — KI-Modus aktiv, Familien-Gruppe %s (ONB-7)",
                 ctx.family_group_chat_id)
    _send(ctx, ctx.family_group_chat_id, DONE_GROUP)


def _send(ctx, chat_id, text):
    """Sendet eine Nachricht; ein Sendefehler bricht die Verarbeitung nicht ab."""
    try:
        ctx.tg.send_message(chat_id, text)
    except TelegramError as e:
        logging.warning("Onboarding: Senden an %s fehlgeschlagen: %s", chat_id, e)
