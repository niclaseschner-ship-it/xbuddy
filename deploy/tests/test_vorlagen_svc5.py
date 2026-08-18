"""Guard: keine Unit-Vorlage legt Instanz-Daten in den Checkout (SVC-5, #1891).

Hintergrund: `familie/familie.service` und `panel/panel.service` zeigten mit
`--registry` bzw. `--panels` auf `__XBUDDY_REPO__/…` — also in den Checkout.
SVC-5 verlangt das Gegenteil: Instanz-Daten liegen unter der Datenwurzel.

Live rettete das jeweils nur ein Drop-In mit `ExecStart=`-Reset. **Fiele es bei
einem Neuaufsetzen weg, startete der Dienst gegen den falschen Pfad** — und bei
`panel` nicht einmal mit einem Fehler: die Checkout-Datei `panel/panels.json`
existiert lokal (gitignoriert, Stand Juni), der Dienst haette also **still gegen
Monate alte Daten** gearbeitet. Das ist die schlimmere Sorte Fehler, weil sie
aussieht wie Erfolg.

Der Test prueft die **Vorlagen allein**, ohne Drop-Ins — genau den Zustand, den
ein frisches Aufsetzen erzeugt, bevor die Drop-Ins kopiert sind.
"""

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Platzhalter, der in den Checkout zeigt. `__XBUDDY_DATA__` ist der richtige.
CHECKOUT = "__XBUDDY_REPO__"

# Was als Instanz-Daten gilt: alles, was der Dienst zur Laufzeit SCHREIBT oder
# als Familien-Zustand liest. Code, Skripte und Templates duerfen selbst-
# verstaendlich im Checkout liegen — deshalb wird auf Datendateien gefiltert.
DATEN_ENDUNGEN = (".json", ".db", ".sqlite", ".sqlite3", ".jsonl")


def _vorlagen():
    return sorted(REPO_ROOT.glob("*/*.service"))


def test_es_gibt_ueberhaupt_vorlagen():
    """Sanitaets-Probe: ein leeres Glob wuerde den Guard stumm gruen machen."""
    assert _vorlagen(), "keine *.service-Vorlage gefunden — der Guard prueft nichts"


def test_keine_vorlage_legt_instanz_daten_in_den_checkout():
    """SVC-5: Instanz-Daten liegen unter der Datenwurzel, nicht im Checkout."""
    treffer = []
    for vorlage in _vorlagen():
        for nr, zeile in enumerate(vorlage.read_text(encoding="utf-8").splitlines(), 1):
            nackt = zeile.strip()
            if nackt.startswith("#") or CHECKOUT not in nackt:
                continue
            for pfad in re.findall(r"%s[/\w.-]*" % re.escape(CHECKOUT), nackt):
                if pfad.endswith(DATEN_ENDUNGEN):
                    treffer.append(
                        "%s:%d  %s" % (vorlage.relative_to(REPO_ROOT), nr, pfad)
                    )

    assert not treffer, (
        "Diese Unit-Vorlagen legen Instanz-Daten in den Checkout und verletzen "
        "damit SVC-5:\n  %s\n\n"
        "Ein Drop-In, das den Pfad live zurechtruecht, zaehlt nicht: faellt es "
        "beim Neuaufsetzen weg, startet der Dienst gegen den falschen Pfad — "
        "im schlimmsten Fall still gegen eine alte Checkout-Kopie.\n"
        "Richtig ist __XBUDDY_DATA__." % "\n  ".join(treffer)
    )
