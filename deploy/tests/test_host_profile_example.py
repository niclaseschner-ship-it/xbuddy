"""Guard: das Beispiel-Host-Profil ist ausfuehrbar und vollstaendig (#1888).

Hintergrund: `deploy/host-profile.example.env` dokumentiert in seinem eigenen
Kopf den Aufruf `bash deploy/bootstrap.sh --profile deploy/host-profile.env`.
Dieser Aufruf kann bis 2026-08-17 **nie gelaufen sein**: Zeile 36 trug den Wert
`https://buddyboard.<tailscale-id>.ts.net` ungequotet, und `<` ist in der Shell
eine Eingabe-Umleitung. `source` brach dort ab.

Gefunden hat das kein Waechter, sondern zufaellig ein Bau-Track (#1802), der den
dokumentierten Trockenlauf tatsaechlich fahren wollte. Ein Beispiel-Profil, das
niemand ausfuehrt, verrottet unbemerkt — dieselbe Klasse wie die toten Mechaniken
aus RAT-36.

**Die Feinheit, an der ein naiver Test scheitert** (gemessen, nicht vermutet):
`source` **bricht bei einer fehlgeschlagenen Umleitung nicht ab** — es laeuft
weiter und setzt die folgenden Variablen normal. Der Rueckgabewert spiegelt nur
den **letzten** Befehl der Datei. Steht die kaputte Zeile am Ende, ist er 1;
folgt ihr noch eine gute Zeile, ist er **0** und der Fehler unsichtbar.

Im realen Fall stand die kaputte Zeile zufaellig am Ende. Ein Guard, der sich
darauf verliesse, wuerde beim naechsten Platzhalter in der Mitte der Datei
schweigen. Deshalb ist **stderr** das tragende Signal, nicht der Rueckgabewert.
"""

import pathlib
import re
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROFIL = REPO_ROOT / "deploy" / "host-profile.example.env"
BOOTSTRAP = REPO_ROOT / "deploy" / "bootstrap.sh"


def _source(pfad: pathlib.Path) -> subprocess.CompletedProcess:
    """Sourct eine Datei in einer frischen Shell und gibt das Ergebnis zurueck."""
    return subprocess.run(
        ["bash", "-c", f"source {pfad}"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_beispiel_profil_ist_sourcebar():
    """Der im Dateikopf dokumentierte Aufruf muss tatsaechlich funktionieren."""
    ergebnis = _source(PROFIL)
    rel = PROFIL.relative_to(REPO_ROOT)

    # stderr zuerst: das ist das tragende Signal (siehe Modul-Docstring).
    assert not ergebnis.stderr.strip(), (
        "%s erzeugt beim Sourcen eine Shell-Fehlermeldung — der im Dateikopf "
        "dokumentierte bootstrap.sh-Aufruf laeuft damit nicht sauber.\n"
        "stderr:\n%s\n"
        "Haeufigste Ursache: ein ungequoteter Wert mit Shell-Sonderzeichen "
        "(<, >, |, &, Leerzeichen). Wert in doppelte Anfuehrungszeichen setzen."
        % (rel, ergebnis.stderr)
    )
    assert ergebnis.returncode == 0, (
        "%s liefert beim Sourcen den Rueckgabewert %d. Da stderr leer ist, liegt "
        "es nicht an einer fehlgeschlagenen Umleitung — sieh dir die letzte "
        "Zeile der Datei an." % (rel, ergebnis.returncode)
    )


def test_rueckfall_ungequoteter_wert_wird_erkannt(tmp_path):
    """Gegenprobe: genau der Fehler von 2026-08-17 muss rot werden.

    Ohne diese Probe waere nicht belegt, dass der Guard ueberhaupt ausloesen
    KANN — und ein Waechter, der nicht rot werden kann, erzeugt nur Zuversicht.
    """
    kaputt = tmp_path / "kaputt.env"
    kaputt.write_text(
        "XBUDDY_OK=/home/buddy\n"
        "XBUDDY_DISPLAY_ORIGIN_FUNNEL=https://buddyboard.<tailscale-id>.ts.net\n"
        # Die harmlose Zeile DANACH ist der Kern der Probe: sie stellt den
        # Rueckgabewert wieder auf 0 und macht den Fehler fuer jeden Guard
        # unsichtbar, der nur den Exit-Code liest.
        "XBUDDY_DANACH=egal\n",
        encoding="utf-8",
    )
    ergebnis = _source(kaputt)

    assert ergebnis.stderr.strip(), (
        "Der ungequotete Wert mit '<' haette eine Shell-Fehlermeldung erzeugen "
        "muessen. Ohne sie prueft test_beispiel_profil_ist_sourcebar nichts."
    )
    assert ergebnis.returncode == 0, (
        "Diese Probe soll belegen, dass der Rueckgabewert das Problem NICHT "
        "anzeigt, solange eine gute Zeile folgt — genau deshalb prueft der Guard "
        "stderr. Kommt hier ein anderer Wert heraus, hat sich das bash-Verhalten "
        "geaendert und die Begruendung im Modul-Docstring stimmt nicht mehr."
    )


def test_profil_belegt_jeden_platzhalter_den_bootstrap_ersetzt():
    """Jeder `__XBUDDY_*__`-Platzhalter aus `bootstrap.sh` hat eine Zeile im Profil.

    Der Dateikopf verspricht: „Alle 8 `__XBUDDY_*__`-Platzhalter muessen belegt
    sein — bootstrap.sh prueft das." Geprueft wird das dort erst zur Laufzeit auf
    der Maschine. Hier faellt eine Luecke schon im Testlauf auf — also bevor
    jemand mit einem unvollstaendigen Profil ein Neuaufsetzen startet.
    """
    ersetzt = set(re.findall(r"__XBUDDY_([A-Z_]+)__", BOOTSTRAP.read_text(encoding="utf-8")))
    belegt = set(re.findall(r"^XBUDDY_([A-Z_]+)=", PROFIL.read_text(encoding="utf-8"), re.M))

    fehlend = sorted(ersetzt - belegt)
    assert not fehlend, (
        "bootstrap.sh ersetzt Platzhalter, die das Beispiel-Profil nicht belegt: "
        "%s\nEin Neuaufsetzen mit diesem Profil liesse sie als rohen "
        "`__XBUDDY_*__`-Text in den systemd-Units stehen."
        % ", ".join("__XBUDDY_%s__" % n for n in fehlend)
    )
