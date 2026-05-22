"""Familien-Registry — Personen-Modell + Datenhaltung.

Siehe specs/platform/familie.md (Refs #38). Dieses Modul besitzt die
Personen-Daten der Familie (FAM-1) und stellt sie über eine Schnittstelle
bereit (FAM-7). Es kennt zwei Arten von Personen — Erwachsene und Kinder
(FAM-2) — und lädt sie aus einer Per-Instanz-Datei (FAM-6).

Die Personen sind Daten, nicht Code (CLAUDE.md §6): dieses Modul enthält
keine fest verdrahtete Personen-Liste, nur das Laden und die Schnittstelle.
"""

import json
import logging
import os


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


class Registry:
    """Die geladene Familien-Registry — eine Instanz, eine Familie (FAM-1).

    Hält die Personen in-memory und stellt die Schnittstelle bereit:
    alle Personen, eine Person je `id` (FAM-7).
    """

    def __init__(self, personen=None):
        # id -> Person; dict bewahrt die Datei-Reihenfolge.
        self._by_id = {}
        for p in (personen or []):
            self._by_id[p.id] = p

    def alle(self):
        """Alle Personen der Familie (FAM-7) — Datei-Reihenfolge."""
        return list(self._by_id.values())

    def get(self, person_id):
        """Eine Person je `id` (FAM-7). Unbekannte `id`: None."""
        return self._by_id.get(person_id)


class RegistryError(Exception):
    """Die Registry-Datei ist inhaltlich ungültig (z. B. Ring außerhalb der Palette)."""


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


def load(path):
    """Lädt die Registry-Datei (FAM-6).

    Fehlt die Datei oder ist sie nicht parsebar, protokolliert das System eine
    Warnung und liefert eine leere Familie — kein Crash (FAM-6). Inhaltlich
    ungültige Daten (fehlende Pflichtfelder, Ring außerhalb der Palette) sind
    dagegen ein echter Fehler und werfen RegistryError.
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

    logging.info(
        "familie geladen: %d Personen (%d Erwachsene, %d Kinder)",
        len(personen),
        sum(1 for p in personen if p.is_erwachsene()),
        sum(1 for p in personen if p.is_kind()))
    return Registry(personen)


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
