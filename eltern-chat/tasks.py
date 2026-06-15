"""Aufgaben-Katalog — siehe specs/platform/eltern-chat.md EC-8/EC-9/EC-10
(Refs #27).

Dieses Modul ist der RAHMEN: ein Registrierungs-Mechanismus, die Unterscheidung
lesend/schreibend und der deterministische Ausführungs-Kontext (`TurnContext`).
Die einzelnen Aufgaben kommen je aus einer eigenen, reviewten Spec mit eigenem
Ticket (EC-8) und leben in eigenen Modulen; `build_catalog` registriert sie.

Lesende Aufgaben (EC-9) laufen direkt: `ReadTask.run()`. Schreibende Aufgaben
(EC-10) sind zweiphasig: `WriteTask.propose()` legt einen strukturierten
Vorschlag vor, `WriteTask.execute()` führt ihn erst nach Bestätigung aus. Die
Bestätigung selbst liegt außerhalb dieses Moduls und außerhalb des Agent-Loops
(confirm.py, E-EC-4).

**Direkt-Modus (E-EIN-1, #714):** Schreibende Aufgaben mit `auto_confirm = True`
übergehen das EC-10-Bestätigungs-Gate — agent.py erkennt das Attribut und ruft
`execute()` direkt via `Catalog.execute_write_task` auf (Hooks + Async-Pfad bleiben
intakt). Anwendung: Aufgaben, deren Wirkung **schmerzlos rückgängig** ist
(z. B. Einkauf-Item hinzufügen — per Mini-App-Geste entfernbar). Standard ist
`auto_confirm = False` — Verlust-Risiko-Aufgaben (Familie anlegen, Plan-Punkte
setzen, Routine ändern) bleiben beim propose→confirm. Entscheidungsfrage beim
Bauen eines neuen schreibenden Skills: „Wirkung schmerzlos rückgängig?" → ja:
`auto_confirm = True`. Nein: Standard EC-10. Spec-Anker: E-EIN-1, EIN-5.
"""

import os
from dataclasses import dataclass

from authz import MEMBER_STATUSES
from hooks import HookContext, HookFailure, summarize_failures
from model import READ, WRITE, TaskDef


def _make_is_member_fn(tg, fgcid_getter):
    """Factory für is_member_fn-Closures — prüft Live-Telegram-Mitgliedschaft.

    Args:
        tg: Telegram-Interface (mit get_chat_member).
        fgcid_getter: Funktion, die die Familien-Gruppen-Chat-ID zurückgibt
            (z.B. lambda: cfg.get("fgcid")). MUSS eine Funktion sein, nicht
            der Wert selbst — sonst wird der Wert beim Bau dieser Factory
            eingefroren und Reload-Operationen haben keine Wirkung (TASK-7).

    Returns:
        Eine Closure is_member(user_id), die gegen die Familien-Gruppe
        (via fgcid_getter) live prüft. Gibt False zurück, wenn fgcid None ist.
    """
    def _is_member(user_id):
        fgcid = fgcid_getter()
        if not fgcid:
            return False
        member = tg.get_chat_member(fgcid, user_id)
        return member is not None and member.get("status") in MEMBER_STATUSES
    return _is_member


@dataclass
class TurnContext:
    """Deterministischer Ausführungs-Kontext einer Anfrage, getrennt vom Modell.

    Diese Daten reicht die Orchestrierung an eine Aufgabe durch, OHNE dass das
    Sprachmodell sie sieht oder beeinflusst (EC-12-Geist): der Modell-Kanal ist
    allein `arguments`. So kann eine Aufgabe z. B. ihren Zielchat verlässlich
    aus dem Kontext nehmen, statt einer vom Modell gelieferten ID zu vertrauen.

    `chat_id` ist der Chat der eingehenden Anfrage (Familien-Gruppe oder
    Privatchat). `private_chat_id` ist der Privatchat des Aufrufers — bei
    einer Privatchat-Anfrage identisch zu `chat_id`, bei einer Gruppen-Anfrage
    die User-ID des Aufrufers (Telegram-Privatchat-ID == User-ID). `from_user_id`
    ist die Telegram-User-ID des Aufrufers. Die Aufnahme dieser Felder ist load-
    bearing für FAA-12 (`familie_anlegen_task`): der Anlage-Dialog läuft im
    Privatchat, nicht in der Gruppe (analog ONB-3).

    `media_telegram_file_id` und `medium_typ` sind FSE-3-Felder (Refs #393):
    bei einem kommentarlos gesendeten Medium reicht die Orchestrierung die
    Telegram-`file_id` deterministisch durch — der `FotoSendenTask` lädt das
    Medium darüber, nie aus den Modell-`arguments` (EC-12-Geist). `medium_typ`
    ist `"foto"` oder `"video"`. Beide leer ⇒ kein Medium im Turn (Modell hat
    den Skill auf falscher Spur gerufen, EC-7).
    """
    chat_id: object
    from_user_id: object = None
    private_chat_id: object = None
    media_telegram_file_id: object = None    # FSE-3 / D4 (Refs #393)
    medium_typ: object = None                # FSE-5 / D4 — "foto" | "video"


def is_from_private_chat(turn_context):
    """True, wenn die Anfrage IM Privatchat des Aufrufers gestellt wurde
    (Refs #157).

    Konvention aus `TurnContext` (s.o.): bei einer Privatchat-Anfrage sind
    `chat_id` und `private_chat_id` identisch (`main._user_message_from`
    bzw. der Bau in `handle_update`/`_execute_confirmed` setzt
    `private_chat_id = chat_id` für `chat_type == "private"`). Bei einer
    Gruppen-Anfrage steht in `chat_id` die Gruppe und in `private_chat_id`
    die User-ID — sie unterscheiden sich.

    Helfer hier in `tasks.py`, weil die drei Privatchat-Sessions (FAA/GAA/KAV)
    dieselbe Logik brauchen und `tasks.py` schon Heimat des `TurnContext`
    ist — kein zusaetzliches Modul noetig, kein Import-Zyklus.
    """
    if turn_context is None:
        return False
    pid = turn_context.private_chat_id
    if pid is None:
        return False
    return turn_context.chat_id == pid


@dataclass
class WriteTaskResult:
    """Ergebnis einer ueber das Framework ausgefuehrten Schreib-Aufgabe
    (EC-21, #140).

    `reply` ist die Quittung der Aufgabe (das, was `execute()` zurueckgegeben
    hat). `warning` ist eine optionale Familien-Warnung, die das Framework
    aus den fehlgeschlagenen Hooks zusammensetzt — leer, wenn alle Hooks
    durchgelaufen sind oder gar keine deklariert waren.

    Aufrufer bauen aus beiden Feldern die Antwort an die Familie: typisch
    `reply + "\\n\\n" + warning` (siehe `combined_text`). Die Trennung gibt
    main.py Spielraum, die Warnung anders zu formatieren, falls noetig.
    """
    reply: str
    warning: str = ""
    hook_failures: tuple = ()

    def combined_text(self):
        """Antwort + Warnung als ein Stueck Text — was an die Familie geht."""
        if not self.warning:
            return self.reply
        return "%s\n\n%s" % (self.reply, self.warning)


@dataclass
class Proposal:
    """EC-10: ein strukturierter Vorschlag — was genau geschehen würde.

    `summary` ist die menschenlesbare Beschreibung der geplanten Änderung. Die
    gebundenen Argumente werden separat geführt (confirm.py), damit die
    Ausführung exakt den vorgeschlagenen Eingaben folgt.
    """
    summary: str


class Task:
    """Basis einer Katalog-Aufgabe. Nicht direkt registrieren — `ReadTask`
    oder `WriteTask` verwenden."""

    kind = None   # von der Unterklasse gesetzt

    def __init__(self, name, description, parameters):
        self.name = name
        self.description = description
        self.parameters = parameters   # JSON-Schema der Eingaben

    def to_def(self):
        """Anbieter-neutrale Definition für den Agenten/Anbieter."""
        return TaskDef(name=self.name, description=self.description,
                       kind=self.kind, parameters=self.parameters)


class ReadTask(Task):
    """Eine lesende Aufgabe (EC-9): liefert nur Information, ändert keine Daten."""

    kind = READ

    def run(self, arguments, turn_context):
        """Führt die Aufgabe aus und liefert das Ergebnis als Text.

        `arguments` ist der Modell-Kanal; `turn_context` ist der deterministische
        Ausführungs-Kontext (`TurnContext`), den das Modell nicht beeinflusst.
        """
        raise NotImplementedError


class WriteTask(Task):
    """Eine schreibende Aufgabe (EC-10): verändert Familien-Daten.

    Eine Unterklasse darf `post_execute_hooks` setzen (EC-21, #140) — eine
    Liste zustandsloser Hooks, die nach erfolgreichem `execute()` laufen
    und typisch einen konsumierenden Buddy auffordern, seinen In-Memory-
    Cache neu zu laden. Default ist leer: ohne explizite Deklaration
    aendert sich am Verhalten nichts.

    `is_async` (Refs #159): wenn True, kehrt `execute()` mit einer
    Kurzquittung zurueck und ein Worker-Thread macht die eigentliche
    Schreib-Operation (Privatchat-Flow, FAA/GAA/KAV). In diesem Fall
    SKIPT `Catalog.execute_write_task` die inline-Hook-Iteration — die
    Hooks sind dann Selbstaufgabe des Workers (er feuert sie nach
    erfolgreichem Abschluss am Thread-Ende, siehe `PrivateChatSession`).
    Default ist False: sync-Tasks verhalten sich wie vor #159."""

    kind = WRITE

    # Klassenattribut — Unterklassen ueberschreiben es mit ihrer eigenen
    # Hook-Liste. Wird vom Framework gelesen, nicht von der Aufgabe selbst.
    post_execute_hooks = ()

    # Klassenattribut — Unterklassen mit Worker-Thread-Pattern (FAA/GAA/KAV)
    # setzen es auf True. Wird vom Framework (`execute_write_task`) gelesen,
    # um zu entscheiden, ob die Hooks inline laufen (sync) oder am
    # Worker-Thread-Ende (async).
    is_async = False

    # Klassenattribut — Direkt-Modus (E-EIN-1): Skill schreibt sofort,
    # ohne EC-10-propose→confirm-Gate. Default False (Standard EC-10).
    # Wenn True, ruft `agent.py` die Aufgabe wie eine ReadTask direkt
    # via `Catalog.execute_write_task` auf — `propose()` wird übersprungen.
    # Anwendung: Aufgaben, deren Wirkung "schmerzlos rückgängig" ist
    # (E-EIN-1 Begründung: Einkaufsliste-Items per Mini-App-Geste
    # entfernbar; Bestätigungs-Reibung ohne Sicherheits-Gewinn).
    auto_confirm = False

    def propose(self, arguments, turn_context):
        """Legt einen `Proposal` vor — führt NICHTS aus."""
        raise NotImplementedError

    def execute(self, arguments, turn_context):
        """Führt die Aufgabe aus (erst nach Bestätigung aufzurufen)."""
        raise NotImplementedError


class Catalog:
    """Registry der verfügbaren Aufgaben (EC-8).

    Aufgaben werden additiv ergänzt; der bestehende Katalog bleibt unberührt.
    Ist der Katalog leer, kann der Agent keine Aufgabe ausführen — jede
    aufgaben-artige Anfrage führt dann zur ehrlichen Grenze (EC-7).
    """

    def __init__(self):
        self._tasks = {}

    def register(self, task):
        """Registriert eine Aufgabe. Doppelte Namen sind ein Fehler."""
        if not isinstance(task, (ReadTask, WriteTask)):
            raise TypeError("Aufgabe muss ReadTask oder WriteTask sein")
        if task.name in self._tasks:
            raise ValueError("Aufgabe '%s' ist bereits registriert" % task.name)
        self._tasks[task.name] = task

    def get(self, name):
        """Liefert die Aufgabe oder None, wenn sie nicht im Katalog ist."""
        return self._tasks.get(name)

    def task_defs(self):
        """Anbieter-neutrale Definitionen aller registrierten Aufgaben."""
        return [t.to_def() for t in self._tasks.values()]

    def execute_write_task(self, task, arguments, turn_context):
        """Fuehrt eine schreibende Aufgabe inkl. Post-Execute-Hooks aus
        (EC-21, #140).

        Lifecycle:
        1. `task.execute(arguments, turn_context)` — die eigentliche Aufgabe.
           Wirft sie eine Exception, propagiert die nach aussen (das
           Framework rollt nicht zurueck — der Aufrufer entscheidet, ob
           er das als Aufgaben-Fehlschlag meldet).
        2. Nach erfolgreichem `execute()`: ueber `task.post_execute_hooks`
           iterieren, jeden synchron aufrufen, Ergebnisse sammeln.
        3. Hook-Fehler **rollen die Schreib-Aufgabe nicht zurueck** (EC-21):
           die Aenderung ist durch. Mehrere fehlgeschlagene Hooks landen
           in EINER zusammengefassten Warnung an die Familie.

        Hook-Aufrufe sind isoliert: wirft ein Hook (gegen die Konvention!)
        doch eine Exception, faengt das Framework sie als HookFailure ab —
        sonst koennten weitere Hooks oder die Quittung verloren gehen.

        Async-Tasks (Refs #159): wenn `task.is_async` True ist, kehrt
        `execute()` nur mit einer Privatchat-Kurzquittung zurueck — die
        eigentliche Schreib-Operation laeuft in einem Worker-Thread, der
        erst Minuten spaeter abschliesst. In diesem Fall SKIPT das
        Framework die inline-Hook-Iteration: die Hooks sind dann
        Selbstaufgabe des Workers (`PrivateChatSession` feuert sie nach
        erfolgreichem Worker-Ende). Der Task verkabelt das in seinem
        `execute()` — wir lesen hier nur das Klassenattribut.
        """
        reply = task.execute(arguments, turn_context)
        if getattr(task, "is_async", False):
            # Async-Task: Hooks laufen am Worker-Ende, nicht hier. Der
            # Aufrufer bekommt nur die Kurzquittung; eine etwaige Warnung
            # geht direkt aus dem Worker in den Privatchat (`on_warning`).
            return WriteTaskResult(reply=reply)
        hooks = getattr(task, "post_execute_hooks", ()) or ()
        if not hooks:
            return WriteTaskResult(reply=reply)
        context = HookContext(task_name=task.name, turn_context=turn_context)
        failures = []
        for hook in hooks:
            try:
                result = hook(context)
            except Exception as e:  # siehe EC-21-Notiz oben
                failures.append(HookFailure(
                    consumer=getattr(hook, "consumer", task.name),
                    error="unerwarteter Fehler (%s)" % e))
                continue
            if isinstance(result, HookFailure):
                failures.append(result)
        warning = summarize_failures(failures)
        return WriteTaskResult(reply=reply, warning=warning,
                               hook_failures=tuple(failures))


# ---------------------------------------------------------------------------
# TASK-10c Form (b) — Übersetzer
# ---------------------------------------------------------------------------

#: Vokabular-Schlüssel für Präsentations-Hinweise (TASK-10c Form (b)).
PRESENTATION_INLINE_BUTTON = "inline_button"
PRESENTATION_WEBAPP_LINK = "webapp_link"


def render_form_b(result, tg, chat_id):
    """TASK-10c Form (b): {text, presentation} → eine Telegram-Nachricht.

    Nimmt ein Form-(b)-Dict entgegen (`{"text": ..., "presentation": ...}`),
    übersetzt den `presentation`-Hinweis in einen passenden Telegram-Aufruf
    und gibt eine Quittungs-Zeichenkette zurück.

    Bekannte Schlüssel in `presentation`:
      * ``inline_button`` → `tg.send_inline_keyboard` mit web_app_url-Button.
      * ``webapp_link``   → ebenso (web_app_url als Alias).
      * Unbekannter / leerer Schlüssel → Fallback auf `tg.send_message`.

    Der Skill sendet NICHTS selbst — das Framework (agent.py) ruft diesen
    Übersetzer auf (EC-29 „Eine Stimme im Agent-Turn").
    """
    text = result.get("text", "")
    presentation = result.get("presentation") or {}

    if PRESENTATION_INLINE_BUTTON in presentation:
        ib = presentation[PRESENTATION_INLINE_BUTTON]
        buttons = [{"label": ib["label"], "web_app_url": ib.get("web_app_url")}]
        tg.send_inline_keyboard(chat_id, text, buttons)
        return "Nachricht mit Inline-Button gesendet."

    if PRESENTATION_WEBAPP_LINK in presentation:
        wl = presentation[PRESENTATION_WEBAPP_LINK]
        buttons = [{"label": wl["label"], "web_app_url": wl["url"]}]
        tg.send_inline_keyboard(chat_id, text, buttons)
        return "Nachricht mit WebApp-Link gesendet."

    # Unbekannter Schlüssel oder leeres presentation → nur Text
    tg.send_message(chat_id, text)
    return "Nachricht gesendet."


# ---------------------------------------------------------------------------

def build_catalog(tg, ca_pem_path, familie_origin_url=None,
                  faa_sessions=None, family_group_chat_id_getter=None,
                  geraete_origin_url=None, gaa_sessions=None,
                  cav_call_hook=None, display_url_origin=None,
                  zd_store_getter=None, kav_sessions=None,
                  plan_origin_url=None,
                  tes_sessions=None, panel_origin_url=None,
                  paa_sessions=None, controller_url_origin=None,
                  routine_origin_url=None, photo_origin_url=None,
                  icon_origin_url=None, seiten_origin_url=None,
                  display_url_origin_heim=None,
                  tab_sessions=None,
                  provider_name=None, provider_api_key=None,
                  provider_model=None,
                  multimodal_provider=None, multimodal_api_key=None,
                  multimodal_model=None,
                  essen_origin_url=None,
                  avb_sessions=None,
                  current_provider_getter=None,
                  mini_app_einkauf_url=None,
                  mini_app_base_url=None,
                  hoerspiel_url_origin=None,
                  kibuddy_origin_url=None):
    """Baut den Katalog für eine laufende Instanz.

    Registriert die CA-Verteilungs-Aufgabe (`ca_verteilung.md` CAV-6, lesend),
    — wenn die FAA-Abhängigkeiten vorliegen — die »Familie anlegen«-Aufgabe
    (`familie-anlegen.md` FAA-12, schreibend), — wenn die GAA-Abhängigkeiten
    vorliegen — die »Gerät anlegen«-Aufgabe (`geraet-anlegen.md` GAA-5,
    schreibend), — wenn die KAV-Abhängigkeiten vorliegen — die »Kalender
    verbinden«-Aufgabe (`kalender-verbinden.md` KAV-3, schreibend) und —
    wenn `plan_origin_url` gesetzt ist — die »Termine erfragen«-Aufgabe
    (`termine-erfragen.md` TER-10, lesend). Die instanz-festen Abhängigkeiten
    reicht die Orchestrierung hier herein; das ermöglicht einer Test-Umgebung,
    den Katalog ohne FAA-/GAA-/KAV-Setup zu bauen (`build_catalog(tg, ca_path)`
    bleibt unverändert kompatibel zu den CAV-Tests). Weitere Aufgaben werden
    additiv ergänzt (EC-8).

    FSE-8 / #393: Setzt der Aufrufer `photo_origin_url`, registriert
    build_catalog zusätzlich die »Foto/Video senden«-Aufgabe (TASK-9,
    Sofort-Schreib-Aufgabe) — wieder hinter dem AND-Guard auf
    `family_group_chat_id_getter` (FSE-2-Berechtigung).

    SREG-6 / #476: Setzt der Aufrufer `seiten_origin_url`, registriert
    build_catalog zusätzlich die lesende »Seiten-Übersicht«-Aufgabe (EC-9,
    SREG-5/5b) — hinter dem AND-Guard auf `seiten_origin_url` +
    `family_group_chat_id_getter` (SREG-6-Berechtigung via EC-2-Mitgliedschaft).
    `display_url_origin_heim` ist die Heim-Origin (SREG-7) für den Übersichts-Link.

    KAQS-6 / #825: Setzt der Aufrufer `kibuddy_origin_url`, registriert
    build_catalog zusätzlich die schreibende »KIBuddy-Aufnahme-Quelle setzen«-
    Aufgabe (EC-10, KAQS-4 propose→confirm) — hinter dem AND-Guard auf
    `kibuddy_origin_url` + `family_group_chat_id_getter` (KAQS-3-Berechtigung).
    """
    # Lokale Imports: brechen den Import-Zyklus tasks <-> ca_task/faa_task/
    # gaa_task/kav_task — nicht hochziehen.
    from skills.ca_task import CaVerteilungTask

    catalog = Catalog()
    catalog.register(CaVerteilungTask(tg, ca_pem_path))

    if familie_origin_url is not None and faa_sessions is not None \
            and family_group_chat_id_getter is not None:
        from skills.familie_anlegen_task import FamilieAnlegenTask
        catalog.register(FamilieAnlegenTask(
            tg, familie_origin_url, faa_sessions,
            family_group_chat_id_getter))

    if geraete_origin_url is not None and gaa_sessions is not None \
            and family_group_chat_id_getter is not None:
        from skills.geraet_anlegen_task import GeraetAnlegenTask
        catalog.register(GeraetAnlegenTask(
            tg, geraete_origin_url, gaa_sessions,
            family_group_chat_id_getter,
            cav_call_hook=cav_call_hook,
            display_url_origin=display_url_origin))

    if zd_store_getter is not None and kav_sessions is not None \
            and family_group_chat_id_getter is not None:
        from skills.kalender_verbinden_task import KalenderVerbindenTask
        catalog.register(KalenderVerbindenTask(
            tg, zd_store_getter, kav_sessions,
            family_group_chat_id_getter,
            plan_origin_url=plan_origin_url))

    if plan_origin_url is not None:
        # TER-10: »Termine erfragen« als lesende Aufgabe (EC-9). Die
        # is_member_fn prüft live die Telegram-Gruppen-Mitgliedschaft (TER-2)
        # — hier als reines tg.get_chat_member-Proxy, damit build_catalog
        # keinen family_group_chat_id-Getter separat braucht. In der
        # Laufzeit-Instanz ist family_group_chat_id_getter gesetzt; fehlt es,
        # läuft die Berechtigung über die is_member_fn im Task, die das
        # authz-Gate in main.py bereits abbildet — die Aufgabe bekommt hier
        # eine Immer-true-Funktion (Sicherheits-Gate liegt außen, EC-2, E-EC-4).
        # Die echte Berechtigungs-Prüfung (TER-2) nutzt die family_group_chat_id;
        # da diese aber im normalen Betrieb durch authz.py geprüft wurde, bevor
        # der Catalog-Aufruf erreicht wird, ist die Task-interne Prüfung eine
        # zweite Sicherheitslinie — nützlich bei direktem Task-Aufruf.
        from skills.plan_client import PlanClient
        from skills.termine_erfragen_task import TermineErfragenTask
        plan_client = PlanClient(origin_url=plan_origin_url)
        # TER-2: is_member_fn nutzt family_group_chat_id_getter, wenn vorhanden;
        # sonst wird die Prüfung ans Task-run delegiert (authz.py vor dem Loop).
        if family_group_chat_id_getter is not None:
            _is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        else:
            # Kein Getter → Immer-true (authz.py hat die Prüfung bereits gemacht)
            _is_member = lambda uid: True
        catalog.register(TermineErfragenTask(
            plan_client=plan_client,
            is_member_fn=_is_member))

    # TES-10: »Termin eintragen« als schreibende Aufgabe (EC-10). AND-Guard:
    # plan_origin_url UND family_group_chat_id_getter müssen gesetzt sein —
    # analog der KAV-Guard-Linie oben. Der TES-Task braucht beide, um:
    # (a) den Plan-Buddy über die PUT-Schnittstelle anzusprechen (plan_origin_url),
    # (b) die Live-Berechtigung gegen die Familien-Gruppe zu prüfen (TES-2).
    # `tes_sessions` ist die externe Session-Registry aus main.build_context —
    # dieselbe Map, die handle_update für das Routing liest (TES-3, AC2+AC3).
    # Wenn plan_origin_url bereits oben gesetzt war, ist plan_client schon
    # gebaut — wir bauen ihn hier separat (oder teilen ihn), beide Wege sind
    # korrekt; separater Bau hält die Guards unabhängig lesbar.
    if plan_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.plan_client import PlanClient as _PlanClient
        from skills.termin_eintragen_task import TermineEintragenTask
        _tes_plan_client = _PlanClient(origin_url=plan_origin_url)
        _tes_sessions = tes_sessions if tes_sessions is not None else {}
        _tes_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(TermineEintragenTask(
            tg=tg,
            plan_client=_tes_plan_client,
            sessions=_tes_sessions,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_tes_is_member))

    # TAB-12 / #475: »Termine aus Bild« als async-schreibende Aufgabe (EC-10,
    # TASK-4 propose+execute, TASK-5 is_async=True). AND-Guard analog TES:
    # plan_origin_url (PLAN-33 Bulk-PUT), family_group_chat_id_getter (TAB-2
    # Live-Berechtigung), tab_sessions (Lego-Falle TASK-7 — geteilte Map)
    # UND provider_api_key (TAB-5 multimodaler Anbieter; ohne Key kein
    # Adapter → Aufgabe NICHT im Katalog, EC-15-Schema). Im Onboarding-Modus
    # (kein API-Key) ist der Skill abgeschaltet, der bestehende Katalog bleibt
    # unberührt.
    if plan_origin_url is not None \
            and family_group_chat_id_getter is not None \
            and tab_sessions is not None \
            and provider_api_key:
        from skills._multimodal import get_multimodal_provider
        from skills.plan_client import PlanClient as _TabPlanClient
        from skills.termine_aus_bild_task import TermineAusBildTask
        _tab_plan_client = _TabPlanClient(origin_url=plan_origin_url)
        _tab_multimodal = get_multimodal_provider(
            multimodal_provider or provider_name or "claude",
            multimodal_api_key or provider_api_key,
            multimodal_model or "")
        _tab_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(TermineAusBildTask(
            tg=tg,
            multimodal_provider=_tab_multimodal,
            plan_client=_tab_plan_client,
            sessions=tab_sessions,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_tab_is_member))

    # PAA-5/PAA-6: »Panel anlegen« als async-schreibende Aufgabe (EC-10).
    # Guard analog der SUE-Linie: panel_origin_url (PREG-15-Schreiben),
    # geraete_origin_url (GER-13-Display-Lese), seiten_origin_url (SREG-3-Lesen,
    # PAA-3.3-Kandidaten-Liste), paa_sessions (die Map, die handle_update für
    # das Routing liest, PAA-6) UND family_group_chat_id_getter (Live-Berechtigung,
    # PAA-2) müssen gesetzt sein. `paa_sessions` ist die externe Session-Registry
    # aus main.build_context — DIESELBE Map, die der PAA-Worker füllt und
    # handle_update für das Routing liest (PAA-6/TASK-7; die stille Lego-Falle,
    # wenn hier eine andere Map landete).
    # seiten_origin_url ist Pflicht im Guard (nicht optional): ohne sie liefert
    # get_kandidaten() eine leere Liste → Dialog-Falle (AC4 nennt es, aber das
    # Scheitern käme zu spät, erst im Dialog — besser nicht im Katalog erscheinen).
    if panel_origin_url is not None and geraete_origin_url is not None \
            and seiten_origin_url is not None \
            and paa_sessions is not None \
            and family_group_chat_id_getter is not None:
        from skills.panel_anlegen_task import PanelAnlegenTask
        catalog.register(PanelAnlegenTask(
            tg, panel_origin_url, geraete_origin_url, paa_sessions,
            family_group_chat_id_getter,
            controller_url_origin=controller_url_origin,
            seiten_origin_url=seiten_origin_url))

    # RZS-7: »Routine-Zeiten setzen« als synchrone schreibende Aufgabe (EC-10).
    # AND-Guard: routine_origin_url UND family_group_chat_id_getter müssen gesetzt
    # sein — analog der TES-Linie. Fehlt eine → Aufgabe nicht im Katalog (RZS-7).
    # routine_origin_url: Routine-Buddy-Schnittstelle (ROUTINE-14, PUT /api/v1/routine/config).
    # family_group_chat_id_getter: Live-Berechtigung gegen die Familien-Gruppe (RZS-2).
    if routine_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.routine_client import RoutineClient
        from skills.routine_zeiten_setzen_task import RoutineZeitenSetzenTask
        _rzs_client = RoutineClient(origin_url=routine_origin_url)
        _rzs_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(RoutineZeitenSetzenTask(
            tg=tg,
            routine_client=_rzs_client,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_rzs_is_member))

    # FSE-8: »Foto/Video senden« als Sofort-Schreib-Aufgabe (TASK-9,
    # conventions/tasks.md). AND-Guard: photo_origin_url UND
    # family_group_chat_id_getter müssen gesetzt sein — fehlt eine, erscheint
    # die Aufgabe NICHT im Katalog. is_member_fn baut den Live-Check gegen die
    # Familien-Gruppe analog der RZS-/TES-Linie (FSE-2).
    if photo_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.foto_senden_task import FotoSendenTask
        from skills.photo_client import PhotoClient
        _fse_client = PhotoClient(origin_url=photo_origin_url)
        _fse_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(FotoSendenTask(
            tg=tg,
            photo_client=_fse_client,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_fse_is_member))

    # RPS-3 V1.2 / EC-9: »Routine-Punkte lesen« als lesende Aufgabe (ReadTask).
    # Guard: routine_origin_url UND family_group_chat_id_getter müssen gesetzt sein.
    # Lego-Trennung nach Genre (ReadTask): läuft direkt EC-9-konform, kein
    # propose→confirm-Gate (im Gegensatz zu RoutinePunkteSetzenTask/WriteTask).
    if routine_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.routine_client import RoutineClient as _RplRoutineClient
        from skills.routine_punkte_lesen_task import RoutinePunkteLesenTask
        _rpl_routine_client = _RplRoutineClient(origin_url=routine_origin_url)
        _rpl_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(RoutinePunkteLesenTask(
            routine_client=_rpl_routine_client,
            is_member_fn=_rpl_is_member))

    # RPS-7: »Routine-Punkte setzen« als synchrone schreibende Aufgabe (EC-10,
    # E-RPS-1 propose→confirm). AND-Guard: routine_origin_url UND icon_origin_url
    # UND family_group_chat_id_getter müssen ALLE gesetzt sein — fehlt eine,
    # erscheint die Aufgabe NICHT im Katalog (RPS-7 Spec Z. 99-105). Hintergrund:
    # - routine_origin_url: Schreib-Naht für die Items-API (RPS-6, ROUTINE-14).
    # - icon_origin_url: Lese-Naht für die ICONS-7-Stichwort-Suche (RPS-4).
    #   Konsumenten-Origin ist der Router (z. B. http://127.0.0.1:5000); RPS hat
    #   per E-RPS-2 KEINEN eigenen ARASAAC-Bezug — die Suche läuft zentral.
    # - family_group_chat_id_getter: Live-Berechtigung gegen die Familien-Gruppe
    #   (RPS-2). is_member_fn baut den Live-Check analog zur RZS-/TES-/FSE-Linie.
    if routine_origin_url is not None and icon_origin_url is not None \
            and family_group_chat_id_getter is not None:
        from skills.icon_client import IconClient
        from skills.routine_client import RoutineClient as _RpsRoutineClient
        from skills.routine_punkte_setzen_task import RoutinePunkteSetzenTask
        _rps_routine_client = _RpsRoutineClient(origin_url=routine_origin_url)
        _rps_icon_client = IconClient(origin_url=icon_origin_url)
        _rps_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(RoutinePunkteSetzenTask(
            tg=tg,
            routine_client=_rps_routine_client,
            icon_client=_rps_icon_client,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_rps_is_member,
            icon_origin_url=icon_origin_url))

    # SREG-5/SREG-6 / #476: »Seiten-Übersicht« als lesende Aufgabe (EC-9).
    # AND-Guard: seiten_origin_url UND family_group_chat_id_getter müssen
    # gesetzt sein — analog der TER-Linie. Fehlt eine → Aufgabe nicht im
    # Katalog (SREG-6). seiten_origin_url: Seiten-Registry-Schnittstelle
    # (GET /api/v1/seiten, SREG-3, nur im Opt-in-Pfad genutzt).
    # display_url_origin_heim: Heim-Origin für den Übersichts-Link (SREG-7).
    if seiten_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.seiten_client import SeitenClient
        from skills.seiten_uebersicht_task import SeitenUebersichtTask
        _su_client = SeitenClient(origin_url=seiten_origin_url)
        _su_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(SeitenUebersichtTask(
            seiten_client=_su_client,
            is_member_fn=_su_is_member,
            display_url_origin_heim=display_url_origin_heim))

    # PAS-8 / #578: »Plan-Aktivitäten setzen« als synchrone schreibende Aufgabe
    # (EC-10, E-PAS-1 propose→confirm). AND-Guard: plan_origin_url UND
    # icon_origin_url UND family_group_chat_id_getter müssen ALLE gesetzt sein —
    # fehlt eine, erscheint die Aufgabe NICHT im Katalog (PAS-8). Hintergrund:
    # - plan_origin_url:              Schreib-Naht für die Admin-API (PAS-7,
    #                                 PLAN-34 POST/DELETE).
    # - icon_origin_url:              Lese-Naht für die ICONS-7-Stichwort-Suche
    #                                 (PAS-4). Kein eigener ARASAAC-Bezug (E-PAS-2).
    # - family_group_chat_id_getter:  Live-Berechtigung gegen die Familien-Gruppe
    #                                 (PAS-2). is_member_fn baut den Live-Check
    #                                 analog zur RPS-/GAN-Linie.
    if plan_origin_url is not None and icon_origin_url is not None \
            and family_group_chat_id_getter is not None:
        from skills.icon_client import IconClient as _PasIconClient
        from skills.plan_aktivitaeten_setzen_task import PlanAktivitaetenSetzenTask
        from skills.plan_client import PlanClient as _PasPlanClient
        _pas_plan_client = _PasPlanClient(origin_url=plan_origin_url)
        _pas_icon_client = _PasIconClient(origin_url=icon_origin_url)
        _pas_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(PlanAktivitaetenSetzenTask(
            tg=tg,
            plan_client=_pas_plan_client,
            icon_client=_pas_icon_client,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_pas_is_member,
            icon_origin_url=icon_origin_url))

    # WZE-8 / #503: »Wünsche zeigen« als lesende Aufgabe (EC-9).
    # AND-Guard: essen_origin_url UND family_group_chat_id_getter müssen
    # gesetzt sein — fehlt eine, erscheint die Aufgabe NICHT im Katalog
    # (WZE-8). essen_origin_url: Essens-Buddy-Schnittstelle für die
    # Wunschliste (GET /api/v1/essen/wuensche, ESSEN-15).
    if essen_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.essen_client import EssenClient
        from skills.wuensche_zeigen_task import WuenscheZeigenTask
        _wze_essen_client = EssenClient(origin_url=essen_origin_url)
        _wze_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(WuenscheZeigenTask(
            essen_client=_wze_essen_client,
            is_member_fn=_wze_is_member))

    # GAN-7 / #503 / ESSEN-22 V1.2 Pfad 1: »Gericht anlegen« als synchrone
    # schreibende Aufgabe (EC-10, E-GAN-2 propose→confirm). AND-Guard:
    # essen_origin_url UND icon_origin_url UND family_group_chat_id_getter
    # müssen ALLE gesetzt sein — fehlt eine, erscheint die Aufgabe NICHT im
    # Katalog (GAN-7):
    # - essen_origin_url:  Schreib-Naht für Gerichte-API (ESSEN-19) UND
    #                      Foto-Upload (POST /api/v1/essen/fotos, ESSEN-22 V1.2).
    # - icon_origin_url:   Lese-Naht für ICONS-7-Stichwort-Suche (GAN-4).
    #   Kein eigener ARASAAC-Bezug (E-GAN-3) — die Suche läuft zentral.
    # - family_group_chat_id_getter: Live-Berechtigung (GAN-2, EC-2).
    # Welle 2 von #804: photo_origin_url nicht mehr im Guard — Foto-Upload
    # läuft über essen_client.post_foto (MEDIEN-1), kein Photo-Buddy-Inject.
    if essen_origin_url is not None and icon_origin_url is not None \
            and family_group_chat_id_getter is not None:
        from skills.essen_client import EssenClient as _GanEssenClient
        from skills.gericht_anlegen_task import GerichtAnlegenTask
        from skills.icon_client import IconClient as _GanIconClient
        _gan_essen_client = _GanEssenClient(origin_url=essen_origin_url)
        _gan_icon_client = _GanIconClient(origin_url=icon_origin_url)
        _gan_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(GerichtAnlegenTask(
            tg=tg,
            essen_client=_gan_essen_client,
            icon_client=_gan_icon_client,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_gan_is_member,
            icon_origin_url=icon_origin_url))

    # EIN-8 / #653: »Einkauf hinzufügen« als schreibende Sofort-Aufgabe
    # (Direkt-Modus, E-EIN-1 — kein propose→confirm).
    # AND-Guard: essen_origin_url UND icon_origin_url UND
    # family_group_chat_id_getter müssen ALLE gesetzt sein — fehlt eine,
    # erscheint die Aufgabe NICHT im Katalog:
    # - essen_origin_url: Schreib-Naht für die Einkaufsliste (ESSEN-30).
    # - icon_origin_url:  ICONS-7-Stichwort-Suche für Item-Icons (EIN-4).
    # - family_group_chat_id_getter: Live-Berechtigung (EIN-2, EC-2).
    if essen_origin_url is not None and icon_origin_url is not None \
            and family_group_chat_id_getter is not None:
        from skills.einkauf_hinzufuegen_task import EinkaufHinzufuegenTask
        from skills.essen_client import EssenClient as _EinEssenClient
        from skills.icon_client import IconClient as _EinIconClient
        _ein_essen_client = _EinEssenClient(origin_url=essen_origin_url)
        _ein_icon_client = _EinIconClient(origin_url=icon_origin_url)
        _ein_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        # katalog_getter: Closure, die den Essen-Buddy-Katalog frisch abruft
        # (EIN-4 Schritt 1: Katalog-Match vor Icon-Suche). Analoges Muster wie
        # WZE-8 (_wze_essen_client.get_wuensche für den Lese-Pfad). Bei Ausfall
        # des Buddys fällt der Skill auf ICONS-7 / Icon-Suche zurück (EIN-4).
        def _ein_katalog_getter(_client=_ein_essen_client):
            return _client.lese_katalog()
        catalog.register(EinkaufHinzufuegenTask(
            essen_client=_ein_essen_client,
            icon_client=_ein_icon_client,
            is_member_fn=_ein_is_member,
            katalog_getter=_ein_katalog_getter))

    # EZG-8 / #653: »Einkauf zeigen« als lesende Aufgabe (EC-9).
    # AND-Guard: essen_origin_url UND family_group_chat_id_getter müssen
    # gesetzt sein — fehlt eine, erscheint die Aufgabe NICHT im Katalog
    # (EZG-8). mini_app_einkauf_url ist optional — Skill kennt ENV-Fallback
    # (EZG-6: MINI_APP_EINKAUF_URL). Leer/None → Skill zeigt Fehler-Text
    # ohne Button (EZG-7).
    if essen_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.einkauf_zeigen_task import EinkaufZeigenTask
        from skills.essen_client import EssenClient as _EzgEssenClient
        _ezg_essen_client = _EzgEssenClient(origin_url=essen_origin_url)
        _ezg_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(EinkaufZeigenTask(
            tg=tg,
            essen_client=_ezg_essen_client,
            is_member_fn=_ezg_is_member,
            mini_app_url=mini_app_einkauf_url or ""))

    # RAO-8 / T728-C: »Routine-Anpassen öffnen« als lesende Aufgabe (EC-9).
    # Dreifacher AND-Guard: routine_origin_url UND mini_app_base_url UND
    # family_group_chat_id_getter müssen ALLE gesetzt sein — fehlt eine,
    # erscheint die Aufgabe NICHT im Katalog (RAO-8).
    # - routine_origin_url: Lese-Naht für GET /api/v1/routine/items (RAO-4).
    # - mini_app_base_url: Funnel-Domain für web_app.url (RAO-6, EZG-6-Naht).
    # - family_group_chat_id_getter: Live-Berechtigung gegen die Familien-Gruppe
    #   (RAO-2). is_member_fn analog der RZS-/EZG-Linie.
    if routine_origin_url is not None and mini_app_base_url is not None \
            and family_group_chat_id_getter is not None:
        from skills.routine_anpassen_oeffnen_task import RoutineAnpassenOeffnenTask
        from skills.routine_client import RoutineClient as _RaoRoutineClient
        _rao_routine_client = _RaoRoutineClient(origin_url=routine_origin_url)
        _rao_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(RoutineAnpassenOeffnenTask(
            tg=tg,
            routine_client=_rao_routine_client,
            is_member_fn=_rao_is_member,
            mini_app_url=mini_app_base_url))

    # ONB-11 / #639: »Anbieter wechseln« als async-schreibende Aufgabe.
    # AND-Guard: zd_store_getter UND family_group_chat_id_getter UND
    # avb_sessions UND current_provider_getter müssen gesetzt sein — fehlt
    # eine, erscheint die Aufgabe NICHT im Katalog. Im Onboarding-Modus
    # (kein ZD-Getter, kein Getter für den aktuellen Provider) ist der
    # Skill abgeschaltet — das Onboarding selbst richtet den Anbieter ein.
    # `avb_sessions` ist die externe Session-Registry aus main.build_context
    # (TASK-7-Lego-Falle: dieselbe Map, die handle_update für das Routing
    # liest).
    if zd_store_getter is not None and family_group_chat_id_getter is not None \
            and avb_sessions is not None and current_provider_getter is not None:
        from skills.anbieter_wechseln_task import AnbieterWechselnTask
        catalog.register(AnbieterWechselnTask(
            tg=tg,
            zd_store_getter=zd_store_getter,
            sessions=avb_sessions,
            family_group_chat_id_getter=family_group_chat_id_getter,
            current_provider_getter=current_provider_getter))

    # HFE-9 / #729: »Hörspiel-Folge erzeugen« als schreibende Aufgabe (EC-10,
    # E-HFE-5 propose→confirm). AND-Guard: hoerspiel_url_origin UND
    # family_group_chat_id_getter müssen gesetzt sein — fehlt eine, erscheint
    # die Aufgabe NICHT im Katalog.
    # hoerspiel_url_origin: Hörspiel-Buddy-Schnittstelle (HSP-17,
    #   POST /api/v1/hoerspiel/folgen-vorschlag HFE-3,
    #   POST /api/v1/hoerspiel/alben HFE-5).
    # family_group_chat_id_getter: Live-Berechtigung (HFE-2, EC-2).
    # display_url_origin: Heim-Origin für den Album-Display-Link (HFE-5-Bubble);
    #   analog display_url_origin in GeraetAnlegenTask (GAA-3.7). Leer → kein Link.
    if hoerspiel_url_origin is not None and family_group_chat_id_getter is not None:
        from skills.hoerspiel_client import HoerspielClient
        from skills.hoerspiel_folge_erzeugen_task import HoerspielFolgeErzeugenTask
        _hfe_client = HoerspielClient(origin_url=hoerspiel_url_origin)
        _hfe_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(HoerspielFolgeErzeugenTask(
            tg=tg,
            hoerspiel_client=_hfe_client,
            display_url_origin=display_url_origin or "",
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_hfe_is_member))

    # T531 / ESSEN-22 V1.2 Pfad 2: »Foto für Essens-Item setzen« als
    # Klasse-C-Skill (propose→confirm, EC-10 zweistufige Variante).
    # AND-Guard: essen_origin_url UND family_group_chat_id_getter müssen
    # gesetzt sein — fehlt eine, erscheint die Aufgabe NICHT im Katalog.
    # - essen_origin_url:             POST /api/v1/essen/fotos (ESSEN-22 V1.2)
    #                                 + PATCH /api/v1/essen/katalog/gerichte/<id>
    #                                 (ESSEN-19a) für Gericht-Ziel.
    # - family_group_chat_id_getter:  Live-Berechtigung (EC-2).
    # Welle 2 von #804: photo_origin_url nicht mehr im Guard — Foto-Upload
    # läuft über essen_client.post_foto (MEDIEN-1), kein Photo-Buddy-Inject.
    if essen_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.essen_client import EssenClient as _EfsEssenClient
        from skills.essen_foto_setzen_task import EssenFotoSetzenTask
        _efs_essen_client = _EfsEssenClient(origin_url=essen_origin_url)
        _efs_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        # SVC-5: foto_overrides.json lebt per-Instanz unter xbuddy-data/essen/.
        # ESSEN_FOTO_OVERRIDES_FILE teilt den gleichen Wert wie das Essen-Buddy-Service-Template;
        # Default ist der SVC-5-Pfad, falls die ENV nicht gesetzt ist.
        _efs_overrides_pfad = os.environ.get(
            "ESSEN_FOTO_OVERRIDES_FILE",
            "/home/buddy/xbuddy-data/essen/foto_overrides.json")
        catalog.register(EssenFotoSetzenTask(
            tg=tg,
            essen_client=_efs_essen_client,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_efs_is_member,
            overrides_pfad=_efs_overrides_pfad))

    # T777 / ESSEN-22 V1.1 Vor-Routing: »Essens-Katalog lesen« als
    # Item-Lookup-ReadTask (EC-9). LLM ruft ihn VOR essen_foto_setzen,
    # um gericht_id/item_id aus der Caption zu bestimmen.
    # AND-Guard: essen_origin_url UND family_group_chat_id_getter müssen
    # gesetzt sein — fehlt eine, erscheint die Aufgabe NICHT im Katalog.
    if essen_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.essen_client import EssenClient as _EklEssenClient
        from skills.essen_katalog_lesen_task import EssenKatalogLesenTask
        _ekl_essen_client = _EklEssenClient(origin_url=essen_origin_url)
        _ekl_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(EssenKatalogLesenTask(
            essen_client=_ekl_essen_client,
            is_member_fn=_ekl_is_member))

    # KAQS-6 / #825: »KIBuddy-Aufnahme-Quelle setzen« als synchrone schreibende
    # Aufgabe (EC-10, KAQS-4 propose→confirm). AND-Guard: kibuddy_origin_url UND
    # family_group_chat_id_getter müssen gesetzt sein — fehlt eine, erscheint die
    # Aufgabe NICHT im Katalog (KAQS-6):
    # - kibuddy_origin_url:            KIBuddy-Config-Schnittstelle (KIBUDDY-24,
    #                                  PUT /api/v1/kibuddy/config, KAQS-5).
    # - family_group_chat_id_getter:   Live-Berechtigung (KAQS-3, EC-2).
    #   is_member_fn baut den Live-Check analog der RZS-/TES-/FSE-Linie.
    if kibuddy_origin_url is not None and family_group_chat_id_getter is not None:
        from skills.kibuddy_aufnahme_quelle_setzen_client import KibuddyConfigClient
        from skills.kibuddy_aufnahme_quelle_setzen_task import (
            KibuddyAufnahmeQuelleSetzenTask,
        )
        _kaqs_client = KibuddyConfigClient(origin_url=kibuddy_origin_url)
        _kaqs_is_member = _make_is_member_fn(tg, family_group_chat_id_getter)
        catalog.register(KibuddyAufnahmeQuelleSetzenTask(
            kibuddy_config_client=_kaqs_client,
            family_group_chat_id_getter=family_group_chat_id_getter,
            is_member_fn=_kaqs_is_member))

    return catalog
