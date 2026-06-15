"""Einkauf hinzufügen als Aufgaben-Katalog-Aufgabe — specs/platform/einkauf-hinzufuegen.md
EIN-1 … EIN-8 und eltern-chat.md EC-8/EC-9/EC-10/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`einkauf_hinzufuegen` (EIN-1): versteht der Agent eine Bitte, Items zur
Einkaufsliste hinzuzufügen, ruft er sie auf.

Eine **schreibende** Aufgabe im Direkt-Modus (E-EIN-1): kein propose→confirm.
Der Skill schreibt sofort und bestätigt kompakt.

RAT-16: Adapter-Disziplin — diese Datei kennt IncomingMessage (vendor-neutrales
DTO, telegram.py) und TelegramClient.send_message, enthält aber kein
Telegram-Vokabular (kein callback_query, kein reply_markup, kein inline_keyboard).

EC-29 / TASK-10: run() gibt den von einkauf_hinzufuegen() returnierten
Tool-Result-String direkt weiter — kein eigenes Senden, keine
Quittungs-Konstanten. Das LLM postet.
"""

import logging

from tasks import Proposal, WriteTask

from skills import einkauf_hinzufuegen as ein_mod

logger = logging.getLogger(__name__)


class EinkaufHinzufuegenTask(WriteTask):
    # E-EIN-1: Skill schreibt direkt, kein propose→confirm-Gate.
    # Framework liest das Klassen-Attribut in agent.py vor dem propose-Pfad
    # und ruft execute() direkt auf (Catalog.execute_write_task).
    auto_confirm = True

    """Schreibende Katalog-Aufgabe im Direkt-Modus (E-EIN-1, EIN-8).

    Im Unterschied zu anderen WriteTask-Subklassen (z. B. GerichtAnlegenTask)
    gibt es kein Bestätigungs-Gate — die Funktion schreibt im execute()-Pfad
    direkt (E-EIN-1: Einkaufs-Items sind schmerzlos rückgängig zu machen).

    Die instanz-festen Abhängigkeiten — EssenClient, IconClient, Katalog-Getter
    und is_member_fn — werden im Konstruktor injiziert. Der Eltern-Text und die
    User-ID kommen aus den Modell-arguments bzw. dem TurnContext (EC-12-Geist:
    User-ID NIE aus dem Modell, immer aus TurnContext).

    EC-29: execute() gibt den Tool-Result-String direkt zurück; kein eigenes
    Telegram-Senden.
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, essen_client, icon_client, is_member_fn,
                 katalog_getter=None, receipt_store=None):
        super().__init__(
            name="einkauf_hinzufuegen",
            description=(
                "Fügt ein oder mehrere Items zur Familien-Einkaufsliste hinzu. "
                "Aufrufen, wenn jemand sagt: \"kauf bitte Brot und Milch\", "
                "\"füg Erdbeeren auf die Liste\", \"wir brauchen noch Joghurt, "
                "Käse und Äpfel\", \"auch noch Wurst\" oder Ähnliches. "
                "Der `text`-Parameter trägt die rohe Eltern-Eingabe mit allen "
                "Items — der Skill zerlegt sie selbst (Komma, 'und', Newline)."),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "Die Eltern-Eingabe mit den gewünschten Items, "
                            "z. B. 'Brot, Milch und Joghurt' oder "
                            "'Auch noch Erdbeeren'."),
                    },
                },
                "required": ["text"],
            })
        self._essen_client = essen_client
        self._icon_client = icon_client
        self._is_member_fn = is_member_fn
        # katalog_getter: Callable () -> list[dict] oder None.
        # Wenn gesetzt, wird der Katalog pro Aufruf frisch gelesen
        # (Test-Naht + Laufzeit-Nutzung).
        self._katalog_getter = katalog_getter
        # receipt_store: A2ReceiptStore-Instanz (EC-10 A2-Receipt, #841).
        # None in Tests ohne Receipt-Probe; build_catalog injiziert immer
        # die laufende Store-Instanz (main.py build_context).
        self._receipt_store = receipt_store

    def propose(self, arguments, turn_context):
        """EIN-5 Direkt-Modus: propose liefert einen allgemeinen Hinweis.

        Weil der Skill direkt schreibt (E-EIN-1, kein Bestätigungs-Gate),
        ist der propose-Schritt ein kurzer Preview — der Agent kann ihn für
        das Bestätigungs-Wording nutzen, bevor execute() aufgerufen wird.
        (Das EC-10-Framework ruft propose() auf, bevor es execute() aufruft,
        wenn der Agent-Loop das propose→confirm-Pattern nutzt.)
        """
        args = arguments or {}
        text = (args.get("text") or "").strip()
        if text:
            return Proposal(
                "Items zur Einkaufsliste hinzufügen: %s" % text)
        return Proposal("Items zur Einkaufsliste hinzufügen.")

    def execute(self, arguments, turn_context):
        """Führt die EIN-Funktion synchron aus (EIN-5, is_async=False).

        `from_user_id` kommt aus dem TurnContext — nie aus den Modell-arguments
        (EC-12-Geist).

        Returnt den Tool-Result-String direkt (EC-29).
        """
        args = arguments or {}
        text = args.get("text") or ""
        from_user_id = getattr(turn_context, "from_user_id", None)

        katalog = None
        if self._katalog_getter is not None:
            try:
                katalog = self._katalog_getter()
            except Exception as e:
                logger.warning(
                    "EinkaufHinzufuegenTask: Katalog-Getter fehlgeschlagen "
                    "— %s (kein Katalog-Match)", e)

        result = ein_mod.einkauf_hinzufuegen(
            text=text,
            from_user_id=from_user_id,
            essen_client=self._essen_client,
            icon_client=self._icon_client,
            is_member_fn=self._is_member_fn,
            katalog=katalog,
            # EC-10 A2-Receipt (#841): Store + chat_id durchreichen, damit die
            # trigger-agnostische Funktion einen Bon pro Item schreiben kann
            # (insert_many in einer Transaktion). chat_id=None → kein Receipt
            # (Sicherheits-Fallback in einkauf_hinzufuegen.py).
            receipt_store=self._receipt_store,
            chat_id=getattr(turn_context, "chat_id", None),
        )

        logger.info("EinkaufHinzufuegenTask: chat=%s, result_len=%d",
                    getattr(turn_context, "chat_id", None),
                    len(result) if result else 0)
        return result
