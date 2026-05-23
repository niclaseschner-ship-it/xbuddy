"""Familien-Registry — Personen-Modell + Datenhaltung.

Siehe specs/platform/familie.md (Refs #38, #60). Dieses Modul besitzt die
Personen-Daten **und die familienspezifischen Settings** der Familie (FAM-1)
und stellt beides über eine Schnittstelle bereit (FAM-7, FAM-11). Es kennt
zwei Arten von Personen — Erwachsene und Kinder (FAM-2) — und lädt sie
zusammen mit den Settings aus einer Per-Instanz-Datei (FAM-6).

Die Personen und Settings sind Daten, nicht Code (CLAUDE.md §6): dieses
Modul enthält keine fest verdrahtete Personen-Liste und keine Familien-
Default-Werte im Code, nur das Laden, das atomare Schreiben und die
Schnittstelle.
"""

import json
import logging
import os
import tempfile


# FAM-4: feste Ring-Farb-Palette. Endlich; mehr Personen als Farben ist eine
# Spec-Änderung, kein Config-Wert. `gray` ist die Farbe für Personen ohne
# feste Zuordnung.
RING_PALETTE = ("blue", "orange", "green", "red", "purple", "teal", "gray")

# FAM-2: die zwei Arten von Personen.
KIND_ERWACHSENE = "erwachsene"
KIND_KINDER = "kinder"


class Person:
    """Eine Person der Familie (FAM-3).

    Pflichtfelder: id, name, ring, art. Optionale Kontakt-/Anzeige-Merkmale:
    foto, email, telegram_id. `email` ist Erwachsenen vorbehalten (FAM-3);
    `telegram_id` kann jede Person tragen. Ein fehlendes optionales Feld ist
    kein Fehler — nur die darauf gestützte Auflösung entfällt.
    """

    def __init__(self, id, name, ring, art, foto=None, email=None, telegram_id=None):
        self.id = id
        self.name = name
        self.ring = ring
        self.art = art
        self.foto = foto
        self.email = email
        self.telegram_id = telegram_id

    def is_erwachsene(self):
        return self.art == KIND_ERWACHSENE

    def is_kind(self):
        return self.art == KIND_KINDER

    def to_dict(self):
        """Personen-Daten für die Schnittstelle (FAM-7) — ohne Foto-Binär.

        `foto` ist nur der Dateiname; das Bild selbst liefert der HTTP-Endpunkt
        (FAM-8). Optionale Felder erscheinen nur, wenn gesetzt.
        """
        d = {
            "id": self.id,
            "name": self.name,
            "ring": self.ring,
            "art": self.art,
        }
        if self.foto is not None:
            d["foto"] = self.foto
        if self.email is not None:
            d["email"] = self.email
        if self.telegram_id is not None:
            d["telegram_id"] = self.telegram_id
        return d


class Settings:
    """Familienspezifische Settings (FAM-6/FAM-9).

    Werte aus dem `settings`-Abschnitt der Registry-Datei. Alle Felder
    sind optional — `None` heißt „dieses Setting ist in `familie.json`
    nicht gesetzt, ein Konsument soll den Default verwenden" (FAM-9
    Tabelle). Die Defaults selbst stehen NICHT hier (sondern beim
    Konsumenten), damit die Settings-Klasse nicht die Doppelt-Quelle
    der Wahrheit für die Defaults wird.
    """

    def __init__(self, foto_verzeichnis=None, profilbild_max_kante=None):
        self.foto_verzeichnis = foto_verzeichnis
        self.profilbild_max_kante = profilbild_max_kante

    def to_dict(self):
        """Settings für die Schnittstelle/Datei — analog `Person.to_dict()`:
        nur explizit gesetzte Werte schreiben, fehlende Felder erscheinen
        gar nicht. Eine leere Settings-Instanz wird zu `{}`."""
        d = {}
        if self.foto_verzeichnis is not None:
            d["foto_verzeichnis"] = self.foto_verzeichnis
        if self.profilbild_max_kante is not None:
            d["profilbild_max_kante"] = self.profilbild_max_kante
        return d


def effective_setting(value, env_var, default):
    """FAM-9-Auflösung eines Settings-Werts.

    Reihenfolge: expliziter Settings-Wert (aus `familie.json`) > Env-Variable
    (Ops-Notfall) > hartkodierter Default. Genau das Muster aus FAM-9 — eine
    Funktion, weil sowohl `familie/main.py` als auch
    `eltern-chat/familie_anlegen.py` dieselbe Auflösung brauchen.
    """
    if value is not None:
        return value
    if env_var and env_var in os.environ:
        return os.environ[env_var]
    return default


class Registry:
    """Die geladene Familien-Registry — eine Instanz, eine Familie (FAM-1).

    Hält die Personen und die Settings in-memory und stellt die Schnittstelle
    bereit: alle Personen, eine Person je `id`, die Settings als
    zusammenhängende Werte (FAM-7).
    """

    def __init__(self, personen=None, settings=None):
        # id -> Person; dict bewahrt die Datei-Reihenfolge.
        self._by_id = {}
        for p in (personen or []):
            self._by_id[p.id] = p
        # FAM-6/FAM-7: Settings sind Teil der Registry.
        self.settings = settings if settings is not None else Settings()

    def alle(self):
        """Alle Personen der Familie (FAM-7) — Datei-Reihenfolge."""
        return list(self._by_id.values())

    def get(self, person_id):
        """Eine Person je `id` (FAM-7). Unbekannte `id`: None."""
        return self._by_id.get(person_id)

    def add_person(self, person):
        """Ergänzt eine Person in der In-Memory-Registry (FAM-11-Helfer).

        Hebt RegistryError, wenn die `id` bereits vergeben ist — Aufrufer
        (FAA-5) vergeben einen kollisionsfreien Slug, eine Kollision an
        dieser Stelle wäre also ein echter Programmierfehler. Bestehende
        Personen bleiben unberührt (FAM-11).
        """
        if person.id in self._by_id:
            raise RegistryError("Person mit id %r existiert bereits" % person.id)
        self._by_id[person.id] = person


class RegistryError(Exception):
    """Die Registry-Datei ist inhaltlich ungültig (z. B. Ring außerhalb der
    Palette) ODER der Schreib-Aufruf ist fehlgeschlagen (FAM-11)."""


def _parse_person(raw, art):
    """Baut eine Person aus einem Rohdaten-Eintrag der Registry-Datei.

    Wirft RegistryError, wenn ein Pflichtfeld fehlt oder der Ring nicht aus der
    Palette stammt (FAM-3/FAM-4) — die Datei ist Daten, falsche Daten sind ein
    Datei-Fehler, kein stiller Default.
    """
    for feld in ("id", "name", "ring"):
        if feld not in raw or raw[feld] in (None, ""):
            raise RegistryError("Person ohne Pflichtfeld %r: %r" % (feld, raw))
    ring = raw["ring"]
    if ring not in RING_PALETTE:
        raise RegistryError(
            "Person %r: Ring %r nicht in der Palette %r (FAM-4)"
            % (raw.get("id"), ring, list(RING_PALETTE)))
    email = raw.get("email")
    if email is not None and art == KIND_KINDER:
        # FAM-3: Kinder tragen keine E-Mail.
        raise RegistryError("Kind %r darf kein email-Feld tragen (FAM-3)" % raw.get("id"))
    return Person(
        id=raw["id"],
        name=raw["name"],
        ring=ring,
        art=art,
        foto=raw.get("foto") or None,
        email=email,
        telegram_id=raw.get("telegram_id"),
    )


def _parse_settings(raw):
    """Baut Settings aus dem `settings`-Abschnitt der Registry-Datei.

    Fehlt der Abschnitt oder einzelne Felder, bleibt das Feld `None`
    (Konsument verwendet den Default — FAM-9). Keine Warnung: ein fehlender
    `settings`-Block ist der Normalfall einer minimalen `familie.json`.
    """
    raw = raw or {}
    return Settings(
        foto_verzeichnis=raw.get("foto_verzeichnis"),
        profilbild_max_kante=raw.get("profilbild_max_kante"),
    )


def load(path):
    """Lädt die Registry-Datei — Personen + Settings (FAM-6).

    Fehlt die Datei oder ist sie nicht parsebar, protokolliert das System eine
    EINE Warnung und liefert eine leere Familie mit Default-Settings — kein
    Crash (FAM-6). Inhaltlich ungültige Daten (fehlende Pflichtfelder, Ring
    außerhalb der Palette) sind dagegen ein echter Fehler und werfen
    RegistryError.
    """
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.warning(
            "familie.json nicht gefunden: %s — starte mit leerer Familie", path)
        return Registry()
    except json.JSONDecodeError as e:
        logging.warning(
            "familie.json nicht parsebar (%s): %s — starte mit leerer Familie",
            path, e)
        return Registry()

    personen = []
    seen = set()
    for art, schluessel in ((KIND_ERWACHSENE, "erwachsene"), (KIND_KINDER, "kinder")):
        for raw in (data.get(schluessel) or []):
            p = _parse_person(raw, art)
            if p.id in seen:
                raise RegistryError("doppelte id %r in der Registry-Datei" % p.id)
            seen.add(p.id)
            personen.append(p)

    settings = _parse_settings(data.get("settings"))

    logging.info(
        "familie geladen: %d Personen (%d Erwachsene, %d Kinder)",
        len(personen),
        sum(1 for p in personen if p.is_erwachsene()),
        sum(1 for p in personen if p.is_kind()))
    return Registry(personen, settings=settings)


def save(registry, path):
    """Schreibt die Registry — Personen + Settings — atomar in die Datei (FAM-11).

    Schreibt zuerst in eine Temp-Datei im **Zielverzeichnis** (damit
    `os.replace` ein In-Filesystem-Rename ist und tatsächlich atomar
    funktioniert) und ersetzt dann die Zieldatei. Bei einem Fehlschlag
    (z. B. kein Schreibrecht, Disk voll) wird die Temp-Datei aufgeräumt
    und ein `RegistryError` geworfen — die alte Datei bleibt unverändert,
    und es bleibt keine verwaiste Temp-Datei zurück.

    Bestehende Personen bleiben byte-gleich, solange der Aufrufer sie nicht
    explizit ändert (FAM-11): die Datei-Reihenfolge der Personen wird aus
    der Registry übernommen, optionale Felder erscheinen nur wenn gesetzt
    (analog Person.to_dict / Settings.to_dict).
    """
    erwachsene = [p.to_dict() for p in registry.alle() if p.is_erwachsene()]
    kinder = [p.to_dict() for p in registry.alle() if p.is_kind()]
    payload = {
        "erwachsene": erwachsene,
        "kinder": kinder,
        "settings": registry.settings.to_dict(),
    }

    target_dir = os.path.dirname(os.path.abspath(path))
    # Temp-Datei im Zielverzeichnis → os.replace ist ein Filesystem-internes
    # atomares Rename.
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".familie.", suffix=".json.tmp", dir=target_dir)
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except OSError as e:
        # Aufräumen: Temp darf nicht zurückbleiben (FAM-11 „kein verwaistes Temp").
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise RegistryError("familie.json konnte nicht geschrieben werden: %s" % e)


def foto_pfad(registry, foto_verzeichnis, person_id):
    """Pfad zur Profilfoto-Datei einer Person — oder None (FAM-5/FAM-8).

    None, wenn die `id` unbekannt ist, die Person kein Foto trägt oder die
    Foto-Datei im Verzeichnis fehlt. Genau die Fälle, die FAM-8 als 404
    behandelt.
    """
    person = registry.get(person_id)
    if person is None or not person.foto:
        return None
    # FAM-5: `foto` ist ein Dateiname — basename schließt Pfad-Anteile aus.
    pfad = os.path.join(foto_verzeichnis, os.path.basename(person.foto))
    if not os.path.isfile(pfad):
        return None
    return pfad
