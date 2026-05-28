"""Zugangsdaten-Speicher — geteiltes Lese-/Schreib-Modul (Refs #37).

Siehe specs/platform/zugangsdaten.md. Dieses Modul ist der **einzige** Zugang
zum Per-Instanz-Speicher (ZD-5): andere Komponenten holen und setzen
Zugangsdaten ausschließlich hierüber, nie über eigenen Datei-Zugriff.

Der Speicher hält benannte Zugangsdaten (ZD-2) als JSON-Datei je Instanz
(ZD-1), mit Dateirechten 0600 auf den Eigentümer beschränkt (ZD-3). Fehlt die
Datei, gilt der Speicher als leer — kein Fehler (ZD-4). Werte werden zu keinem
Zeitpunkt im Klartext protokolliert oder in Fehlermeldungen gezeigt (ZD-6).
"""

import json
import logging
import os
import stat

logger = logging.getLogger(__name__)

# ZD-3: Dateirechte auf den Eigentümer beschränkt — Lesen+Schreiben, sonst nichts.
FILE_MODE = 0o600


class Zugangsdaten:
    """Per-Instanz-Speicher für benannte Zugangsdaten (ZD-1, ZD-2).

    Die Werte leben in einer JSON-Datei `path`. Eine Instanz dieser Klasse ist
    der gekapselte Zugang aus ZD-5: `get(name)` holt eine Zugangsdate, `set(name,
    value)` setzt sie. Beim Schreiben werden die Dateirechte aus ZD-3
    durchgesetzt.
    """

    def __init__(self, path):
        self.path = str(path)

    # -- Lesen ------------------------------------------------------------

    def _load(self):
        """Liest die Speicher-Datei. Fehlt sie, gilt der Speicher als leer (ZD-4).

        Liefert ein dict Name -> Wert.
        """
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            # ZD-4: fehlende Datei ist kein Fehler — leerer Speicher.
            return {}
        except json.JSONDecodeError as e:
            # Eine kaputte Datei darf das System nicht abreißen lassen. Wir
            # behandeln sie wie einen leeren Speicher und loggen den Pfad —
            # ohne Inhalt, damit kein Geheimnis ins Log gerät (ZD-6).
            logger.warning(
                "Zugangsdaten-Datei nicht parsebar (%s): %s — leerer Speicher",
                self.path, e)
            return {}
        if not isinstance(data, dict):
            logger.warning(
                "Zugangsdaten-Datei hat kein Objekt als Inhalt (%s) — leerer Speicher",
                self.path)
            return {}
        return data

    def get(self, name, default=None):
        """Holt die Zugangsdate `name` (ZD-5). Fehlt sie, kommt `default` zurück.

        Der Speicher entscheidet nicht, was ein fehlender Wert bedeutet — das
        ist Sache der aufrufenden Komponente (ZD-4, ZD-7).
        """
        return self._load().get(name, default)

    def has(self, name):
        """True, wenn eine Zugangsdate `name` im Speicher liegt."""
        return name in self._load()

    def names(self):
        """Liste der Namen im Speicher (ZD-2) — nur Schlüssel, nie Werte."""
        return sorted(self._load().keys())

    # -- Schreiben --------------------------------------------------------

    def set(self, name, value):
        """Setzt die Zugangsdate `name` auf `value` (ZD-5).

        Schreibt die gesamte Speicher-Datei neu und setzt dabei die Dateirechte
        aus ZD-3 (0600) durch — auch wenn die Datei neu angelegt wird.
        """
        if not isinstance(name, str) or not name:
            raise ValueError("Zugangsdaten-Name muss ein nicht-leerer String sein")
        data = self._load()
        data[name] = value
        self._write(data)
        # ZD-6: bestätigt wird nur der Name, nie der Wert.
        logger.info("Zugangsdate gesetzt: %s", name)

    def _write(self, data):
        """Schreibt `data` als JSON nach `self.path` mit Rechten 0600 (ZD-3).

        Die Datei wird mit den restriktiven Rechten *angelegt*, sodass der
        Inhalt zu keinem Zeitpunkt mit offeneren Rechten auf der Platte liegt.
        Auf einer bestehenden Datei werden die Rechte zusätzlich erzwungen.
        """
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        # os.open mit explizitem Modus: die Datei entsteht direkt mit 0600,
        # nicht erst mit dem (offeneren) umask-Default.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        # Bestehende Datei kann offenere Rechte gehabt haben — erzwingen.
        os.chmod(self.path, FILE_MODE)

    # -- Diagnose ---------------------------------------------------------

    def __repr__(self):
        # ZD-6: nie Werte spiegeln. Repr zeigt nur Pfad und Anzahl.
        try:
            count = len(self._load())
        except Exception:  # noqa: BLE001 — Diagnose darf nie selbst werfen
            count = "?"
        return "Zugangsdaten(path=%r, eintraege=%s)" % (self.path, count)


def is_owner_only(path):
    """True, wenn `path` die Dateirechte aus ZD-3 (0600) trägt.

    Hilfsfunktion für Diagnose und Tests — prüft, dass weder Gruppe noch
    andere Lese-/Schreibrechte auf der Speicher-Datei haben.
    """
    mode = stat.S_IMODE(os.stat(path).st_mode)
    return mode == FILE_MODE
