"""HSP-7/HSP-14 — Bündel-Schnitt-Logik (deterministisch, ohne Netz).

Test-Implikationen aus HSP-14:
  - 5×200-Wörter-Absätze → 2 Bündel
  - 2×600-Wörter-Absätze → 2 Bündel
  - Schnitte fallen auf Absatzgrenzen — nie mitten in einem Satz
"""

from hoerspiel import album_builder


def _absatz(woerter: int, marker: str = "wort") -> str:
    return " ".join([marker] * woerter)


def test_buendel_5x200_woerter_ergibt_2_buendel():
    absaetze = [_absatz(200, "a%d" % i) for i in range(5)]
    bundles = album_builder.buendele(absaetze)
    assert len(bundles) == 2
    # Erstes Bündel hat die ersten 3 Absätze (600 Wörter, >= 450 nach 3.).
    assert bundles[0].count("\n\n") == 2  # drei Absätze = 2 Trenner
    # Schnittgrenze ist Absatzgrenze: kein Absatz wurde gesplittet.
    assert "a0" in bundles[0]
    for bundle in bundles:
        # Jedes Bündel besteht aus vollständigen Absätzen
        assert not bundle.startswith(" ")
        assert not bundle.endswith(" ")


def test_buendel_2x600_woerter_ergibt_2_buendel():
    absaetze = [_absatz(600, "x%d" % i) for i in range(2)]
    bundles = album_builder.buendele(absaetze)
    assert len(bundles) == 2
    # Jeder 600-W-Absatz übersteigt die Schwelle allein → eigenes Bündel.
    assert "x0" in bundles[0]
    assert "x1" not in bundles[0]
    assert "x1" in bundles[1]
    assert "x0" not in bundles[1]


def test_buendel_unter_schwelle_ergibt_1_buendel():
    absaetze = [_absatz(100, "k%d" % i) for i in range(3)]
    bundles = album_builder.buendele(absaetze)
    assert len(bundles) == 1


def test_buendel_schnitt_immer_auf_absatzgrenze():
    """HSP-14: Schnitte fallen NIE mitten in einen Absatz."""
    absaetze = [_absatz(300, "p%d" % i) for i in range(4)]
    bundles = album_builder.buendele(absaetze)
    # Jeder erhaltene Bündel-Block ist die exakte Verkettung ganzer Absätze.
    rekonstruiert = "\n\n".join(bundles)
    erwartet = "\n\n".join(absaetze)
    assert rekonstruiert == erwartet


def test_absaetze_splitten_an_leerzeilen():
    text = "Erster Absatz.\n\nZweiter Absatz.\n\n   \n\nDritter."
    teile = album_builder.absaetze(text)
    assert teile == ["Erster Absatz.", "Zweiter Absatz.", "Dritter."]


def test_buendel_einzelner_grosser_absatz():
    absaetze = [_absatz(1200)]
    bundles = album_builder.buendele(absaetze)
    assert len(bundles) == 1
    assert bundles[0] == absaetze[0]
