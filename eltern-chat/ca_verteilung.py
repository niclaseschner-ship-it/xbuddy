"""CA-Verteilung — siehe specs/platform/ca-verteilung.md (CAV-1 … CAV-7, Refs #39).

Die CA-Verteilung ist eine **aufrufbare, trigger-agnostische Funktion** (CAV-1,
E-CAV-1): Aufgerufen, liefert sie einem Familienmitglied das öffentliche
Root-CA-Zertifikat als Telegram-Dokument plus eine OS-spezifische
Installations-Anleitung über den Eltern-Chat-Bot aus.

Die Funktion kennt ihren Aufrufer NICHT. Wer sie aufruft — die
Eltern-Chat-Aufgabe aus CAV-6 (ca_task.py) oder ein künftiger
Geräte-Onboarding-Flow (OPEN-CAV-A) — ist nicht Teil ihres Vertrags. Sie nimmt
nur die für die Auslieferung nötigen Dinge entgegen: den Kanal, den Zielchat,
den Pfad zum Zertifikat.

Die Berechtigungsprüfung (CAV-4, analog EC-2) liegt — wie bei agent.py — beim
Aufrufer/der Orchestrierung, nicht in dieser Funktion. So bleibt die Funktion
ein reiner Auslieferungs-Baustein.
"""

import logging
from dataclasses import dataclass

from telegram import TelegramError


# CAV-5: OS-spezifische Installations-Anleitung — hart-codiert, kein KI-Anbieter.
# Für die gängigen Plattformen, adressatengerecht für eine Familie formuliert.
_INSTALL_GUIDE = """\
So machst du das Zertifikat auf deinem Gerät vertrauenswürdig:

📱 Android
1. Öffne die heruntergeladene Datei rootCA.pem (oder Einstellungen →
   Sicherheit → Verschlüsselung → Zertifikat installieren).
2. Wähle als Verwendung „CA-Zertifikat" bzw. „VPN und Apps".
3. Bestätige die Sicherheitsabfrage. Fertig.

 iOS / iPadOS
1. Öffne die Datei rootCA.pem — iOS lädt sie als Konfigurationsprofil.
2. Einstellungen → Allgemein → VPN & Geräteverwaltung → Profil installieren.
3. Zusätzlich: Einstellungen → Allgemein → Info → Zertifikatsvertrauens-
   einstellungen — und das XBuddy-Zertifikat dort aktivieren. Dieser zweite
   Schritt ist nötig, sonst bleibt das Zertifikat ohne Wirkung.

🪟 Windows
1. Doppelklicke auf rootCA.pem.
2. „Zertifikat installieren" → Speicherort „Lokaler Computer".
3. „Alle Zertifikate in folgendem Speicher speichern" →
   „Vertrauenswürdige Stammzertifizierungsstellen" wählen → Fertig stellen.

🍎 macOS
1. Doppelklicke auf rootCA.pem — die Schlüsselbundverwaltung öffnet sich.
2. Lege das Zertifikat im Schlüsselbund „System" ab.
3. Doppelklicke auf den neuen Eintrag → „Vertrauen" aufklappen →
   „Bei Verwendung dieses Zertifikats" auf „Immer vertrauen" setzen.

Danach öffnen die XBuddy-Seiten ohne Sicherheitswarnung."""

_CAPTION = ("XBuddy Root-Zertifikat. Installiere es auf diesem Gerät, damit "
            "die XBuddy-Seiten ohne Browser-Warnung öffnen — Anleitung folgt "
            "in der nächsten Nachricht.")

# CAV-3: Ein PEM-Privatschlüssel trägt diese Markierung. Wird der konfigurierte
# Pfad versehentlich auf eine Schlüsseldatei gesetzt, bricht die Funktion ab,
# statt ein Geheimnis auszuliefern.
_PRIVATE_KEY_MARKER = b"PRIVATE KEY"


class CaVerteilungError(Exception):
    """Die CA-Verteilung konnte nicht ausgeliefert werden."""


@dataclass
class CaVerteilungResult:
    """Ergebnis eines Funktions-Aufrufs — was wurde an wen ausgeliefert."""
    chat_id: object
    document_message_id: object
    guide_message_id: object


def verteile_ca(tg, chat_id, ca_pem_path):
    """Liefert das öffentliche Root-CA-Zertifikat samt Installations-Anleitung
    an `chat_id` aus (CAV-1).

    `tg`           — Kanal mit `send_document` und `send_message` (TelegramClient
                     oder Doppelung). Auslieferung läuft über diesen bestehenden
                     Bot-Kanal (CAV-4).
    `chat_id`      — Zielchat eines Familien-Gruppen-Mitglieds.
    `ca_pem_path`  — Pfad zum öffentlichen `rootCA.pem` (CAV-3, Per-Instanz-
                     Konfiguration).

    Liefert ein `CaVerteilungResult`. Wirft `CaVerteilungError`, wenn das
    Zertifikat nicht gelesen oder nicht gesendet werden konnte — der Aufrufer
    entscheidet, wie er darauf reagiert.
    """
    pem = _load_public_ca(ca_pem_path)

    try:
        # CAV-3/CAV-4: nur das öffentliche Zertifikat, als Telegram-Dokument.
        sent_doc = tg.send_document(chat_id, "rootCA.pem", pem, caption=_CAPTION)
        # CAV-5: OS-spezifische Installations-Anleitung hinterher.
        sent_guide = tg.send_message(chat_id, _INSTALL_GUIDE)
    except TelegramError as e:
        raise CaVerteilungError("CA-Zertifikat konnte nicht gesendet werden: %s" % e)

    logging.info("CA-Verteilung: Root-CA an Chat %s ausgeliefert (CAV-1)", chat_id)
    return CaVerteilungResult(
        chat_id=chat_id,
        document_message_id=(sent_doc or {}).get("message_id"),
        guide_message_id=(sent_guide or {}).get("message_id"))


def _load_public_ca(ca_pem_path):
    """Liest das öffentliche Root-CA-Zertifikat von der Platte (CAV-3).

    Verweigert die Auslieferung, wenn die Datei fehlt oder — als Schutz gegen
    eine fehlkonfigurierte `ca_pem_path` — einen Privatschlüssel enthält. Der
    CA-Privatschlüssel verlässt den Hub nie (CAV-3, CLAUDE.md §8).
    """
    try:
        with open(ca_pem_path, "rb") as f:
            pem = f.read()
    except FileNotFoundError:
        raise CaVerteilungError(
            "CA-Zertifikat nicht gefunden: %s — erst tools/ca/make-ca.sh "
            "ausführen oder ca_pem_path in der Konfiguration setzen (CAV-3)."
            % ca_pem_path)
    except OSError as e:
        raise CaVerteilungError("CA-Zertifikat nicht lesbar: %s" % e)

    if _PRIVATE_KEY_MARKER in pem:
        raise CaVerteilungError(
            "Die unter ca_pem_path konfigurierte Datei (%s) enthält einen "
            "Privatschlüssel — verteilt wird ausschließlich das öffentliche "
            "rootCA.pem (CAV-3)." % ca_pem_path)
    return pem
