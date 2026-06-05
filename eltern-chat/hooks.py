"""Post-Execute-Hooks fuer das WriteTask-Framework — siehe specs/platform/
eltern-chat.md EC-21 (Refs #140).

Eine WriteTask kann nach erfolgreichem `execute()` zustandslose Hooks
anstossen — typisch ein HTTP-Reload-Aufruf an einen konsumierenden Buddy,
damit dort der In-Memory-Cache neu aus den geaenderten Daten gelesen wird
(memory/feedback_api_vs_direct_fs.md: API vor direktem FS).

Die Hooks laufen synchron, im selben Prozess, mit kurzem Timeout. Ein
Hook-Fehler **rollt die Schreib-Aufgabe nicht zurueck** (EC-21): die
Aenderung ist durch, die Familie bekommt nur eine zusaetzliche Warnung
mit den Buddies, die noch nicht nachgezogen haben. Mehrere Fehler einer
Aufgabe werden in EINER zusammengefassten Warnung gemeldet, nicht je Hook.

Ein Hook ist eine Callable mit Signatur::

    hook(context: HookContext) -> HookSuccess | HookFailure

`context` reicht der Framework-Lifecycle (`Catalog.execute_write_task`) an
den Hook — der Hook selbst haelt keinen Zustand. So bleibt die
Hook-Liste am `WriteTask` eine reine Deklaration (Klassenattribut), nicht
eine Bindung an Instanz-State.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

# Timeout fuer einen einzelnen Hook-Aufruf. Kurz halten — der Aufrufer wartet
# synchron, bevor die Quittung an die Familie geht. Passend zum
# Router-/Plan-Reload-Vertrag aus #149/#151.
HOOK_HTTP_TIMEOUT_SECONDS = 5


@dataclass
class HookContext:
    """Was ein Hook beim Aufruf vorfindet.

    `task_name` ist nur fuer Logging gedacht (der Hook selbst kennt den
    auslosenden Task nicht). Weitere Felder kommen additiv hinzu, sobald
    konkrete Hooks sie brauchen — heute reichen Name + Hinweis auf den
    deterministischen Ausfuehrungs-Kontext.
    """
    task_name: str
    turn_context: object = None


@dataclass
class HookSuccess:
    """Hook lief sauber durch — typsicheres Erfolgs-Ergebnis."""
    details: str = ""


@dataclass
class HookFailure:
    """Hook konnte den Konsumenten nicht erreichen oder hat eine schlechte
    Antwort bekommen — typsicheres Fehl-Ergebnis. `consumer` ist die kurze
    Bezeichnung des Konsumenten fuer die Familien-Warnung (z. B.
    'Plan-Buddy'); `error` ist die technische Detail-Beschreibung."""
    consumer: str
    error: str


HookResult = object   # HookSuccess | HookFailure — Union-Typ ohne typing.Union


class ReloadHook:
    """Generischer Reload-Hook: HTTP POST an einen Konsumenten, der seinen
    In-Memory-State neu aus den geaenderten Daten lesen soll.

    HTTP-Vertrag (analog #149/#151):
    - POST `url`, leerer Body.
    - 200 + JSON-Body `{"reloaded": true, ...}` ⇒ Erfolg.
    - Alles andere (Non-200, kein JSON, `reloaded` nicht True, Timeout,
      Connection-Refused, irgendeine Exception) ⇒ Fehler.

    Der Hook ist zustandslos: `__call__` enthaelt keinen Hook-internen
    State; die URL und das Consumer-Label sind Konstruktor-Argumente, der
    `HookContext` kommt vom Framework. Mehrere Tasks koennen dieselbe
    `ReloadHook`-Instanz teilen.
    """

    def __init__(self, url, consumer):
        """`url` ist der vollstaendige Reload-Endpunkt; `consumer` ist die
        kurze Bezeichnung fuer die Familien-Warnung (z. B. 'Plan-Buddy')."""
        self._url = url
        self._consumer = consumer

    @property
    def url(self):
        return self._url

    @property
    def consumer(self):
        return self._consumer

    def __call__(self, context):
        """Fuehrt den Reload synchron aus; gibt HookSuccess/HookFailure
        zurueck. Eine Exception kommt **nie** heraus — alle Fehler werden
        als HookFailure verpackt (EC-21: die Schreib-Aufgabe darf nicht
        durch den Reload zurueckgerollt werden)."""
        request = urllib.request.Request(
            self._url, data=b"", method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(
                    request, timeout=HOOK_HTTP_TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", None) or response.getcode()
                body = response.read()
        except urllib.error.HTTPError as e:
            logging.warning("ReloadHook %s: HTTP %s vom Konsumenten %s",
                            self._url, e.code, self._consumer)
            return HookFailure(consumer=self._consumer,
                               error="HTTP %s" % e.code)
        except urllib.error.URLError as e:
            # Connection-Refused, Timeout, DNS-Fehler — fuer den Aufrufer
            # alles dasselbe Symptom: der Konsument antwortet gerade nicht.
            logging.warning("ReloadHook %s: Konsument %s nicht erreichbar: %s",
                            self._url, self._consumer, e.reason)
            return HookFailure(consumer=self._consumer,
                               error="nicht erreichbar (%s)" % e.reason)
        except Exception as e:  # Hook-Fehler isoliert melden
            logging.warning("ReloadHook %s: unerwarteter Fehler: %s",
                            self._url, e)
            return HookFailure(consumer=self._consumer,
                               error="unerwarteter Fehler (%s)" % e)

        if status != 200:
            return HookFailure(consumer=self._consumer,
                               error="HTTP %s" % status)

        # Body pruefen — `reloaded: true` ist Pflicht (HTTP-200 allein
        # garantiert beim generischen Vertrag nicht, dass der Konsument
        # auch wirklich neu geladen hat).
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            return HookFailure(consumer=self._consumer,
                               error="falsches Body-Format (%s)" % e)
        if not isinstance(parsed, dict) or parsed.get("reloaded") is not True:
            return HookFailure(consumer=self._consumer,
                               error="falsches Body-Format")
        return HookSuccess(details="reloaded")


def summarize_failures(failures):
    """Fasst eine Liste von HookFailures zu EINER Warnzeile zusammen
    (EC-21: nicht je Hook eine Warnung, sondern eine pro Aufgabe).

    Leere Liste ⇒ leerer String.
    """
    if not failures:
        return ""
    consumers = ", ".join(sorted({f.consumer for f in failures}))
    return ("Hinweis: %s hat die Aenderung evtl. noch nicht geladen — "
            "bitte einmal manuell neu oeffnen." % consumers)
