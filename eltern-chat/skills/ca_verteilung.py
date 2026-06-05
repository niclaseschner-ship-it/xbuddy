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
# Stolpersteine je OS adressiert (Quellen siehe PR #75/#77).
#
# Die Anleitung deckt alle vier Plattformen gleichgewichtig ab — kein OS wird
# bevorzugt. Die Auslieferung ist jedoch gerätespezifisch: pro Aufruf geht nur
# der Abschnitt zum gewählten Gerät an die Familie (CAV-5, #95). Eine Familie
# bekommt nie alle vier OS auf einmal.

_GUIDE_WINDOWS = """\
So machst du das XBuddy-Zertifikat (xbuddy-rootCA.crt) auf Windows (10 / 11) vertrauenswürdig:

🪟 Windows (10 / 11)
1. Tippe doppelt auf xbuddy-rootCA.crt → „Zertifikat installieren…"
2. Erste Frage „Speicherort": wähle „Aktueller Benutzer" (reicht für dich allein) oder „Lokaler Computer" (für alle Konten auf dem PC, Admin-Passwort nötig). Weiter.
3. Zweite Frage „Zertifikatspeicher": wähle NICHT die automatische Auswahl, sondern „Alle Zertifikate in folgendem Speicher speichern" → „Durchsuchen…" → „Vertrauenswürdige Stammzertifizierungsstellen" → OK → Weiter → Fertig stellen. Sicherheitswarnung mit Ja bestätigen.
4. Prüfen: Start → certmgr.msc (oder certlm.msc bei „Lokaler Computer") → unter „Vertrauenswürdige Stammzertifizierungsstellen" muss „XBuddy" auftauchen.
5. Schließe deinen Browser komplett (alle Fenster) und öffne ihn neu.
6. Firefox? Firefox nutzt einen eigenen Zertifikatsspeicher. Dort zusätzlich: about:preferences#privacy → unten „Zertifikate" → „Zertifikate anzeigen…" → Reiter „Zertifizierungsstellen" → „Importieren…" → xbuddy-rootCA.crt → „Dieser CA vertrauen, um Websites zu identifizieren" aktivieren → OK.

Danach öffnen die XBuddy-Seiten ohne Sicherheitswarnung. Klappt etwas nicht — schreib mir hier, ich helfe."""

_GUIDE_ANDROID = """\
So machst du das XBuddy-Zertifikat (xbuddy-rootCA.crt) auf Android (12 / 13 / 14) vertrauenswürdig:

📱 Android (12 / 13 / 14)
1. Einstellungen → „Sicherheit & Datenschutz" → „Weitere Sicherheitseinstellungen" → „Verschlüsselung & Anmeldedaten" → „Zertifikat installieren" → „CA-Zertifikat". (Auf älteren Android-Versionen heißt der Pfad ähnlich, z. B. Einstellungen → Sicherheit → Verschlüsselung & Zugangsdaten.) Eine PIN/Sperre muss eingerichtet sein.
2. Die Warnung „Ihre Daten sind nicht privat" ist hier normal — mit „Trotzdem installieren" bestätigen.
3. xbuddy-rootCA.crt auswählen.
4. Wichtig zu wissen: Browser (Chrome, Firefox) und der Großteil der Apps akzeptieren dieses Zertifikat. Manche Apps trauen nur System-CAs und ignorieren von dir installierte Zertifikate — das ist eine Android-Sicherheitsmaßnahme und nicht zu umgehen. Für XBuddy im Browser/PWA reicht der Schritt aus.

Danach öffnen die XBuddy-Seiten ohne Sicherheitswarnung. Klappt etwas nicht — schreib mir hier, ich helfe."""

_GUIDE_IOS = """\
So machst du das XBuddy-Zertifikat (xbuddy-rootCA.crt) auf iOS / iPadOS (16 / 17 / 18) vertrauenswürdig:

🍏 iOS / iPadOS (16 / 17 / 18)
ZWEI Schritte — beide sind nötig, sonst bleibt das Zertifikat wirkungslos.
1. Profil installieren: Tippe in Mail/Safari/Dateien auf xbuddy-rootCA.crt. iOS lädt es als „Profil". Einstellungen öffnen → oben erscheint „Profil geladen" → antippen → „Installieren" (rechts oben) → Code eingeben → noch einmal „Installieren" → Fertig.
2. Vertrauen aktivieren: Einstellungen → Allgemein → Info → ganz unten „Zertifikatsvertrauenseinstellungen" → unter „Vollständiges Vertrauen für Stammzertifikate aktivieren" den Schalter für „XBuddy" einschalten → Warnung mit „Fortfahren" bestätigen.

Danach öffnen die XBuddy-Seiten ohne Sicherheitswarnung. Klappt etwas nicht — schreib mir hier, ich helfe."""

_GUIDE_MACOS = """\
So machst du das XBuddy-Zertifikat (xbuddy-rootCA.crt) auf macOS (Sonoma / Sequoia) vertrauenswürdig:

🍎 macOS (Sonoma / Sequoia)
1. Doppeltippe auf xbuddy-rootCA.crt → die App „Schlüsselbundverwaltung" öffnet sich (Programme → Dienstprogramme).
2. Im Fenster oben „System" als Schlüsselbund wählen (NICHT „Anmeldung"). Admin-Passwort eingeben.
3. Im Schlüsselbund „System" das neue Zertifikat „XBuddy" doppeltippen → den Abschnitt „Vertrauen" aufklappen → „Bei Verwendung dieses Zertifikats" auf „Immer vertrauen" stellen → Fenster schließen → Admin-Passwort bestätigen.
4. Browser komplett beenden und neu öffnen.

Danach öffnen die XBuddy-Seiten ohne Sicherheitswarnung. Klappt etwas nicht — schreib mir hier, ich helfe."""

# Mapping der erlaubten geraet-Werte auf den jeweiligen Anleitungs-Block.
# Die Werte sind die Enum-Schar aus CAV-5; ein anderer Wert ist ein
# Aufruf-Fehler (siehe verteile_ca).
_GUIDES_BY_GERAET = {
    "windows": _GUIDE_WINDOWS,
    "android": _GUIDE_ANDROID,
    "ios": _GUIDE_IOS,
    "macos": _GUIDE_MACOS,
}

SUPPORTED_GERAETE = tuple(_GUIDES_BY_GERAET.keys())

_CAPTION = ("XBuddy Root-Zertifikat (xbuddy-rootCA.crt). Installiere es auf "
            "diesem Gerät, damit die XBuddy-Seiten ohne Browser-Warnung "
            "öffnen — Anleitung folgt in der nächsten Nachricht.")

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


def verteile_ca(tg, chat_id, ca_pem_path, geraet):
    """Liefert das öffentliche Root-CA-Zertifikat samt Installations-Anleitung
    an `chat_id` aus (CAV-1).

    `tg`           — Kanal mit `send_document` und `send_message` (TelegramClient
                     oder Doppelung). Auslieferung läuft über diesen bestehenden
                     Bot-Kanal (CAV-4).
    `chat_id`      — Zielchat eines Familien-Gruppen-Mitglieds.
    `ca_pem_path`  — Pfad zum öffentlichen `rootCA.pem` (CAV-3, Per-Instanz-
                     Konfiguration).
    `geraet`       — Zielgerät: `windows`, `android`, `ios` oder `macos`
                     (CAV-5, #95). Pflicht-Eingabe — fehlt die Angabe, ist
                     der Aufruf ungültig. Geliefert wird nur der zu diesem
                     Gerät passende Abschnitt der Anleitung; die Familie
                     bekommt nie alle vier OS auf einmal.

    Liefert ein `CaVerteilungResult`. Wirft `CaVerteilungError`, wenn das
    Zertifikat nicht gelesen oder nicht gesendet werden konnte — der Aufrufer
    entscheidet, wie er darauf reagiert. Ein fehlendes oder ungültiges
    `geraet` ist ein Aufruf-Fehler (`ValueError`) — keine stille Auslieferung
    eines Default-Geräts.
    """
    guide = _guide_for(geraet)
    pem = _load_public_ca(ca_pem_path)

    try:
        # CAV-3/CAV-4: nur das öffentliche Zertifikat, als Telegram-Dokument.
        # Dateiname „xbuddy-rootCA.crt": Windows hat für `.pem` keinen Cert-
        # Handler — Doppelklick öffnet den Editor statt des Import-Assistenten
        # (#75). `.crt` ist der gemeinsame Nenner: Windows/Android/iOS/macOS
        # erkennen ihn alle als Zertifikat, der Inhalt bleibt PEM-kodiertes
        # X.509. Quelldatei auf der Platte (ca_pem_path) bleibt `rootCA.pem`.
        sent_doc = tg.send_document(chat_id, "xbuddy-rootCA.crt", pem, caption=_CAPTION)
        # CAV-5: gerätespezifischer Anleitungs-Abschnitt hinterher.
        sent_guide = tg.send_message(chat_id, guide)
    except TelegramError as e:
        raise CaVerteilungError("CA-Zertifikat konnte nicht gesendet werden: %s" % e)

    logging.info("CA-Verteilung: Root-CA an Chat %s ausgeliefert (CAV-1, geraet=%s)",
                 chat_id, geraet)
    return CaVerteilungResult(
        chat_id=chat_id,
        document_message_id=(sent_doc or {}).get("message_id"),
        guide_message_id=(sent_guide or {}).get("message_id"))


def _guide_for(geraet):
    """Wählt den Anleitungs-Block zum Zielgerät (CAV-5).

    Ein fehlendes oder unbekanntes `geraet` ist ein Aufruf-Fehler — die
    Funktion liefert dann *nichts* aus (keine stille Default-Wahl).
    """
    if geraet is None or geraet not in _GUIDES_BY_GERAET:
        raise ValueError(
            "CA-Verteilung verlangt 'geraet' aus %s — bekommen: %r (CAV-5)"
            % (sorted(_GUIDES_BY_GERAET), geraet))
    return _GUIDES_BY_GERAET[geraet]


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
