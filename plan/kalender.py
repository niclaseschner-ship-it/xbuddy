"""Plan-Buddy — Kalender-Anbindung (PLAN-15 … PLAN-20).

Siehe specs/buddies/plan.md §6. Die Anbindung an den Google-Familien-Kalender
ist eine Funktion **dieser App** (E-PLAN-6). Sie liest Events eines Zeitraums
und legt sie an / ändert / löscht sie — alles auf genau einen konfigurierten
Kalender (PLAN-15).

Aufbau — Test-Naht (PLAN-29):

  GoogleTransport   spricht HTTP mit Google (OAuth + Calendar v3). Das ist die
                    EINZIGE Stelle mit Netz-Zugriff.
  Kalender          die App-Funktion: nimmt einen `transport`, normalisiert
                    die Rohantwort (PLAN-17) und löst Personen auf (PLAN-19).

Für Tests wird `GoogleTransport` durch ein FakeTransport ersetzt, das
kontrollierte Rohantworten liefert (PLAN-29) — kein Netz nötig. `Kalender`
selbst (Normalisierung, Personen-Match, Multi-Day) wird so vollständig ohne
Google geprüft.

Die OAuth-Daten (Client + Refresh-Token) kommen aus dem zentralen
Zugangsdaten-Speicher (PLAN-16, `zugangsdaten.md`) — die App legt KEINE eigene
Token-Datei an.
"""

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta

logger = logging.getLogger(__name__)

# PLAN-16: Namen, unter denen OAuth-Client und Refresh-Token im
# Zugangsdaten-Speicher liegen (ZD-2: stabile Namen).
ZD_NAME_OAUTH_CLIENT = "plan-google-oauth-client"
ZD_NAME_OAUTH_TOKEN = "plan-google-oauth-refresh-token"

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_CAL_BASE = "https://www.googleapis.com/calendar/v3/calendars"


class CalendarUnavailable(Exception):
    """Der Kalender ist nicht erreichbar oder es fehlen Credentials (PLAN-20).

    Eine Schreib-Anfrage wirft das als klar erkennbaren Misserfolg; eine
    Lese-Anfrage fängt es ab und liefert ein leeres Ergebnis (PLAN-20).
    """


class CalendarRateLimited(CalendarUnavailable):
    """Google hat 429 oder 403 (Rate-Limit) geliefert (PLAN-33.6).

    Ist eine Unterklasse von CalendarUnavailable, damit bestehende
    `except CalendarUnavailable`-Blöcke (PLAN-20/PLAN-22) sich nicht ändern.
    Erweiterter Kontext: `retry_after` trägt den Wert des Retry-After-Headers
    in Sekunden (float) oder None wenn kein Header gesetzt war.
    """

    def __init__(self, msg, retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after  # float | None


class CalendarAuthFailed(CalendarUnavailable):
    """OAuth-Token-Refresh oder Calendar-Auth ist fehlgeschlagen (PLAN-33.2,
    error_code: calendar_auth).

    Ist eine Unterklasse von CalendarUnavailable — bestehende Handler
    fangen sie automatisch mit.
    """


# ============================================================
#  Normalisiertes Event-Modell (PLAN-17)
# ============================================================

class Event:
    """Ein anbieter-neutrales Kalender-Event (PLAN-17 V1.1).

    Felder: stabile `id` (trägt die Multi-Day-Gruppierung, PLAN-14), `titel`,
    `beginn` und `ende` (date oder datetime), `ganztags` (bool), `personen`
    (Liste aufgelöster Personen-`id`, PLAN-19 V1.1 Multi-Person — immer eine
    Liste, max 2 Einträge, leer wenn keine Zuordnung). Google-Rohfelder, die V1
    nicht braucht, werden nicht durchgereicht (CLAUDE.md §6).

    Backward-Compat: `person`-Property liefert `personen[0]` oder None —
    bestehende Konsumenten, die nur eine Person brauchen, bleiben kompatibel.
    """

    def __init__(self, id, titel, beginn, ende, ganztags, personen=None):
        self.id = id
        self.titel = titel
        self.beginn = beginn
        self.ende = ende
        self.ganztags = ganztags
        # PLAN-17 V1.1: personen ist immer eine Liste.
        # Befund 4 (T473-S2): person-Kwarg entfernt — kein Aufrufer nutzte ihn;
        # personen ist der einzige Eingang.
        self.personen = list(personen) if personen is not None else []

    @property
    def person(self):
        """Backward-Compat: erste Person oder None (PLAN-19 V1.1)."""
        return self.personen[0] if self.personen else None

    def to_dict(self):
        """Serialisierbare Form — für die Termin-Schnittstelle (PLAN-22)."""
        return {
            "id": self.id,
            "titel": self.titel,
            "beginn": self.beginn.isoformat() if self.beginn else None,
            "ende": self.ende.isoformat() if self.ende else None,
            "ganztags": self.ganztags,
            "personen": self.personen,
            "person": self.person,  # Backward-Compat für bestehende Konsumenten
        }


# ============================================================
#  Transport — die Netz-Naht (PLAN-29)
# ============================================================

class GoogleTransport:
    """Spricht HTTP mit Google: OAuth-Refresh + Calendar v3 (PLAN-16/17/18).

    Dies ist die einzige Klasse mit Netz-Zugriff. In Tests wird sie durch ein
    Fake ersetzt (PLAN-29). Die OAuth-Daten holt sie aus dem
    Zugangsdaten-Speicher (PLAN-16).

    `store` ist eine Zugangsdaten-Instanz (zugangsdaten.Zugangsdaten),
    `kalender_id` die konfigurierte Google-Kalender-ID (PLAN-15).
    """

    def __init__(self, store, kalender_id, timeout=12):
        self._store = store
        self._kalender_id = kalender_id
        self._timeout = timeout

    def credentials_available(self):
        """True, wenn OAuth-Client UND Refresh-Token im Speicher liegen (PLAN-20)."""
        return (self._store.get(ZD_NAME_OAUTH_CLIENT) is not None
                and self._store.get(ZD_NAME_OAUTH_TOKEN) is not None)

    def _access_token(self):
        """Holt einen frischen Access-Token aus dem Refresh-Token (PLAN-16).

        Client und Token liegen im Zugangsdaten-Speicher. Wirft
        CalendarUnavailable, wenn etwas fehlt oder Google nicht antwortet.
        """
        client = self._store.get(ZD_NAME_OAUTH_CLIENT)
        token = self._store.get(ZD_NAME_OAUTH_TOKEN)
        if client is None or token is None:
            raise CalendarUnavailable("OAuth-Client oder -Token fehlt im Speicher")
        # Der Client-Eintrag folgt dem Google-Format ({"installed"|"web": {...}}).
        if isinstance(client, dict):
            client = client.get("installed", client.get("web", client))
        try:
            client_id = client["client_id"]
            client_secret = client["client_secret"]
            refresh_token = token["refresh_token"] if isinstance(token, dict) else token
        except (KeyError, TypeError) as e:
            raise CalendarUnavailable("OAuth-Daten unvollständig: %s" % e)
        data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode()
        try:
            req = urllib.request.Request(
                _GOOGLE_TOKEN_URL, data=data, method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read())
        except Exception as e:  # jeder Netzfehler → PLAN-20
            raise CalendarUnavailable("OAuth-Token-Refresh fehlgeschlagen: %s" % e)
        if "access_token" not in body:
            raise CalendarUnavailable("OAuth-Antwort ohne access_token")
        return body["access_token"]

    def _request(self, method, path, query=None, body=None, bearer=None):
        """Authentifizierter Calendar-v3-Request gegen den konfigurierten Kalender.

        `bearer` ist ein vorher geholter Access-Token — wird er übergeben,
        wird kein neues OAuth-Refresh gemacht (Token-Cache, PLAN-33.4).
        """
        token = bearer if bearer is not None else self._access_token()
        url = "%s/%s%s" % (_GOOGLE_CAL_BASE,
                           urllib.parse.quote(self._kalender_id), path)
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + token}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            # 429 und 403 (Rate-Limit) → CalendarRateLimited (PLAN-33.6)
            if e.code in (429, 403):
                retry_after = None
                try:
                    ra = e.headers.get("Retry-After")
                    if ra is not None:
                        retry_after = float(ra)
                except (TypeError, ValueError):
                    pass
                raise CalendarRateLimited(
                    "Calendar-Request %s %s: HTTP %s" % (method, path, e.code),
                    retry_after=retry_after)
            # 401 → CalendarAuthFailed (PLAN-33.2, error_code: calendar_auth)
            if e.code == 401:
                raise CalendarAuthFailed(
                    "Calendar-Request %s %s: HTTP 401 Unauthorized" % (method, path))
            raise CalendarUnavailable(
                "Calendar-Request %s %s: HTTP %s" % (method, path, e.code))
        except Exception as e:  # jeder Netzfehler → PLAN-20
            raise CalendarUnavailable("Calendar-Request %s %s: %s" % (method, path, e))

    def list_events(self, time_min, time_max):
        """Roh-Events des Kalenders im Zeitfenster [time_min, time_max) (PLAN-17).

        `time_min`/`time_max` sind ISO-Datetime-Strings. Wiederkehrende Events
        werden von Google in Einzel-Vorkommen aufgelöst (`singleEvents=true`).
        Liefert die Liste der Google-Roh-Items.
        """
        body = self._request("GET", "/events", query={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 250,
        })
        return body.get("items", [])

    def insert_event(self, raw_event):
        """Legt ein Event an (PLAN-18). Liefert das Google-Roh-Item."""
        return self._request("POST", "/events", body=raw_event)

    def insert_event_with_bearer(self, raw_event, bearer):
        """Legt ein Event an mit einem vorher geholten Bearer-Token (PLAN-33.4
        Token-Cache: ein Refresh für alle N Bulk-Inserts).

        Wirft CalendarRateLimited, CalendarAuthFailed oder CalendarUnavailable.
        """
        return self._request("POST", "/events", body=raw_event, bearer=bearer)

    def access_token(self):
        """Öffentliche Schnittstelle zum OAuth-Token-Refresh (PLAN-33.4).

        Der Bulk-Endpoint holt einmal einen Token und reicht ihn an alle
        Inserts weiter — `2N → N+1` Google-Requests.
        Wirft CalendarUnavailable (oder CalendarAuthFailed) bei Fehler.
        """
        return self._access_token()

    def patch_event(self, event_id, raw_patch):
        """Ändert ein Event über seine `id` (PLAN-18). Liefert das Roh-Item."""
        return self._request(
            "PATCH", "/events/" + urllib.parse.quote(event_id), body=raw_patch)

    def delete_event(self, event_id):
        """Löscht ein Event über seine `id` (PLAN-18)."""
        self._request("DELETE", "/events/" + urllib.parse.quote(event_id))


class DateiTransport:
    """Datei-basierter Kalender-Transport für den **Demo-Modus** (#1761).

    Liest Google-Roh-kompatible Event-Items aus einer lokalen JSON-Datei
    (``{"items": [ {id, summary, start, end, creator}, … ]}``) statt aus Google.
    Live bleibt ``GoogleTransport`` — diese Klasse greift NUR, wenn der
    Entrypoint ``PLAN_KALENDER_DEMO_FILE`` gesetzt sieht, und macht das Demo-
    Board ohne OAuth screenshot-tauglich (Familie Sonntag). Read-only: die
    Schreib-Ops sind No-Ops bzw. werfen ``CalendarUnavailable`` (die Demo legt
    keine Termine an).

    Gleiche Schnittstelle wie ``GoogleTransport`` (PLAN-29-Naht), damit
    ``Kalender`` und ``main`` nichts über die Quelle wissen müssen.
    """

    def __init__(self, pfad, kalender_id="demo"):
        self._pfad = pfad
        self.kalender_id = kalender_id

    def credentials_available(self):
        """„Verfügbar", sobald die Demo-Datei existiert (analog OAuth-Check)."""
        return bool(self._pfad) and os.path.isfile(self._pfad)

    def _load_items(self):
        try:
            with open(self._pfad, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise CalendarUnavailable(
                "Demo-Kalender-Datei nicht lesbar: %s" % exc) from exc
        items = data.get("items", []) if isinstance(data, dict) else data
        return [it for it in items if isinstance(it, dict)]

    @staticmethod
    def _bound_to_dt(iso):
        """ISO-String (Z/Offset/naiv) → aware datetime in UTC für Vergleiche."""
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    def _item_start_dt(self, item):
        wert, _ganztags = _parse_when(item.get("start"))
        if wert is None:
            return None
        if isinstance(wert, datetime):
            base = wert if wert.tzinfo else wert.replace(tzinfo=UTC)
            return base.astimezone(UTC)
        # date (ganztägig) → Mitternacht UTC
        return datetime(wert.year, wert.month, wert.day, tzinfo=UTC)

    def list_events(self, time_min, time_max):
        """Roh-Items im Fenster [time_min, time_max) — gleiche Semantik wie
        ``GoogleTransport.list_events`` (PLAN-17). Unparsebare Grenzen → alle
        Items (die Demo-Datei trägt ohnehin nur die aktuelle Woche)."""
        lo = self._bound_to_dt(time_min)
        hi = self._bound_to_dt(time_max)
        items = self._load_items()
        if lo is None or hi is None:
            return items
        out = []
        for it in items:
            start = self._item_start_dt(it)
            if start is None or lo <= start < hi:
                out.append(it)
        return out

    def insert_event(self, raw_event):
        raise CalendarUnavailable("Demo-Kalender ist read-only (#1761)")

    def insert_event_with_bearer(self, raw_event, bearer):
        raise CalendarUnavailable("Demo-Kalender ist read-only (#1761)")

    def patch_event(self, event_id, raw_patch):
        raise CalendarUnavailable("Demo-Kalender ist read-only (#1761)")

    def delete_event(self, event_id):
        raise CalendarUnavailable("Demo-Kalender ist read-only (#1761)")


# ============================================================
#  Personen-Auflösung (PLAN-19)
# ============================================================

def resolve_personen(titel, creator_email, personen):
    """Ordnet ein Event maximal zwei Personen zu (PLAN-19 V1.1 Multi-Person).

    `personen` ist eine Liste von familie.Person. Reihenfolge:
      1. Titel-Treffer — alle Namen, die im Titel vorkommen, werden gesammelt
         und nach Position der ersten Erwähnung sortiert; maximal zwei gewinnen.
      2. Creator-E-Mail — sonst, ist die Creator-Adresse die E-Mail eines
         Erwachsenen, ist das die einzige Person (1-Element-Liste).
      3. sonst leere Liste.

    Liefert eine Liste mit 0, 1 oder 2 Personen-`id`-Strings, in
    Erwähnungs-Reihenfolge.
    """
    titel_lo = (titel or "").lower()
    treffer = []  # (fundindex, person_id)
    for p in personen:
        if not p.name:
            continue
        pos = titel_lo.find(p.name.lower())
        if pos >= 0:
            treffer.append((pos, p.id))
    if treffer:
        # Sortieren nach Fundindex (Erwähnungs-Reihenfolge), dann auf 2 kappen.
        treffer.sort(key=lambda t: t[0])
        return [pid for _, pid in treffer[:2]]
    # 2. Creator-E-Mail.
    if creator_email:
        ce = creator_email.lower()
        for p in personen:
            if p.email and p.email.lower() == ce:
                return [p.id]
    return []


def resolve_person(titel, creator_email, personen):
    """Backward-Compat-Wrapper: liefert die erste aufgelöste Person oder None.

    Delegiert an resolve_personen (PLAN-19 V1.1). Bestehende Aufrufer, die
    nur eine Person brauchen, bleiben ohne Änderung kompatibel.
    """
    result = resolve_personen(titel, creator_email, personen)
    return result[0] if result else None


# ============================================================
#  Kalender — die App-Funktion (PLAN-17 … PLAN-20)
# ============================================================

def _parse_when(when):
    """Übersetzt einen Google-{date|dateTime}-Block in (wert, ganztags).

    Ganztags-Events tragen `date` (ein date), zeitgebundene `dateTime` (ein
    datetime). Liefert (None, False), wenn der Block leer ist.
    """
    if not when:
        return None, False
    if "dateTime" in when:
        raw = when["dateTime"]
        # Google liefert mit Offset (…+02:00) oder Z; fromisoformat versteht
        # beides ab Python 3.11.
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")), False
        except ValueError:
            return None, False
    if "date" in when:
        try:
            return date.fromisoformat(when["date"]), True
        except ValueError:
            return None, True
    return None, False


class Kalender:
    """Die Kalender-Anbindung des Plan-Buddys (PLAN-15 … PLAN-20).

    Nimmt einen `transport` (GoogleTransport in Produktion, ein Fake in Tests —
    PLAN-29) und eine Personen-Liste der Familien-Registry (PLAN-19).
    """

    def __init__(self, transport, personen):
        self._transport = transport
        self._personen = list(personen)

    def credentials_available(self):
        """True, wenn der Transport Credentials hat (PLAN-20)."""
        return self._transport.credentials_available()

    def events(self, start_tag, anzahl_tage):
        """Liefert die normalisierten Events des Fensters (PLAN-17).

        `start_tag` ist ein date, `anzahl_tage` die Fenster-Größe. Fehlen die
        Credentials oder ist Google nicht erreichbar, kommt eine leere Liste
        zurück — kein unbehandelter Fehler (PLAN-20).
        """
        if not self._transport.credentials_available():
            logger.info("Kalender: keine Credentials — leeres Lese-Ergebnis (PLAN-20)")
            return []
        end_tag = start_tag + timedelta(days=anzahl_tage)
        time_min = start_tag.isoformat() + "T00:00:00Z"
        time_max = end_tag.isoformat() + "T00:00:00Z"
        try:
            raw_items = self._transport.list_events(time_min, time_max)
        except CalendarUnavailable as e:
            logger.warning("Kalender nicht erreichbar (%s) — leeres Lese-Ergebnis", e)
            return []
        events = []
        for raw in raw_items:
            ev = self._normalise(raw)
            if ev is not None:
                events.append(ev)
        return events

    def _normalise(self, raw):
        """Übersetzt ein Google-Roh-Item in das neutrale Modell (PLAN-17/PLAN-19 V1.1)."""
        beginn, ganztags = _parse_when(raw.get("start"))
        if beginn is None:
            return None
        ende, _ = _parse_when(raw.get("end"))
        titel = raw.get("summary") or "(ohne Titel)"
        creator_email = (raw.get("creator") or {}).get("email")
        personen = resolve_personen(titel, creator_email, self._personen)
        return Event(
            id=raw.get("id"),
            titel=titel,
            beginn=beginn,
            ende=ende,
            ganztags=ganztags,
            personen=personen,
        )

    # -- Schreiben (PLAN-18) ---------------------------------------------

    def event_anlegen(self, titel, beginn, ende=None):
        """Legt einen Termin an (PLAN-18, #256). Liefert die `id` des neuen Events.

        `beginn` ist ein `date` (ganztägig) oder `datetime` (zeitgebunden, aware).
        `ende` ist optional für ganztägige Termine (fehlt → eintägig, exklusiv-Ende
        +1 Tag) und Pflicht für zeitgebundene Termine.

        Semantik (PLAN-22 PUT-Vertrag):
        - datetime-Erkennung kommt zuerst, weil datetime Subklasse von date ist.
        - Ganztägig: start.date=beginn, end.date=(ende or beginn)+1 Tag (exklusiv).
        - Zeitgebunden: start.dateTime/end.dateTime als ISO-String mit UTC-Offset.

        Wirft ValueError bei ungültigen Kombinationen (AC4) und CalendarUnavailable
        bei fehlenden Credentials oder Netzfehler (PLAN-20).
        """
        # isinstance(datetime) muss VOR isinstance(date) kommen, weil datetime
        # eine Subklasse von date ist.
        if isinstance(beginn, datetime):
            if ende is None:
                raise ValueError(
                    "zeitgebundener Termin: ende ist Pflicht wenn beginn ein datetime ist")
            if not isinstance(ende, datetime):
                raise ValueError(
                    "Typ-Mismatch: beginn ist datetime, ende muss datetime sein (nicht date)")
            if ende <= beginn:
                raise ValueError(
                    "zeitgebundener Termin: ende muss nach beginn liegen")
            raw = {
                "summary": titel,
                "start": {"dateTime": beginn.isoformat()},
                "end": {"dateTime": ende.isoformat()},
            }
        else:
            # Ganztägig — beginn ist ein date.
            if ende is not None:
                if isinstance(ende, datetime):
                    raise ValueError(
                        "Typ-Mismatch: beginn ist date (ganztägig), ende muss date sein (nicht datetime)")
                if ende < beginn:
                    raise ValueError(
                        "ganztägiger Termin: ende darf nicht vor beginn liegen")
            end_exklusiv = (ende if ende is not None else beginn) + timedelta(days=1)
            raw = {
                "summary": titel,
                "start": {"date": beginn.isoformat()},
                "end": {"date": end_exklusiv.isoformat()},
            }
        res = self._transport.insert_event(raw)
        return res.get("id")

    def event_aendern(self, event_id, titel):
        """Ändert den Titel eines Events über seine `id` (PLAN-18)."""
        res = self._transport.patch_event(event_id, {"summary": titel})
        return res.get("id")

    def event_loeschen(self, event_id):
        """Löscht ein Event über seine `id` (PLAN-18)."""
        self._transport.delete_event(event_id)
