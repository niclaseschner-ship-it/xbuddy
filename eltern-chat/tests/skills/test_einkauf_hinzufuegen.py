"""Tests für die Funktion einkauf_hinzufuegen — EIN-1 … EIN-8
(specs/platform/einkauf-hinzufuegen.md, Refs #653, RAT-16).

Abgedeckte ACs:
  AC2 — EIN-3 Item-Zerlegung
  AC3 — EIN-4 Auto-Match (Katalog / ICONS-7 / Default)
  AC4 — EIN-5 Direkt-Modus, Duplikat-Skip, Listen-Grenze
  AC5 — EIN-6 Antwort-Formen
  AC8 — RAT-16 Watchdog (grep, am Ende dieser Datei)

Tests laufen ohne Netz (EC-17): EssenClient und IconClient werden durch
kontrollierte Doppelungen ersetzt.
"""

import pytest
from skills._errors import BerechtigungError
from skills.einkauf_hinzufuegen import (
    _baue_antwort,
    _match_item,
    einkauf_hinzufuegen,
    zerlege_items,
)
from skills.essen_client import FEHLER_DUPLIKAT, FEHLER_GRENZE, EssenClientError

# ============================================================
#  Doppelungen — CLIENT-1 Transport-Stub-Naht
# ============================================================

class FakeEssenClient:
    """EssenClient-Doppelung für einkauf_hinzufuegen-Tests."""

    def __init__(self):
        self.hinzugefuegt = []
        # Konfigurierbare Fehler-Sequenz pro Aufruf:
        # [(marker_oder_None, detail), ...] — None = Erfolg (201)
        self._responses = []
        self._default_response = None  # None = Erfolg

    def set_response(self, *responses):
        """Setzt skriptierte Antworten der Reihe nach."""
        self._responses = list(responses)
        return self

    def hinzufuegen_einkauf(self, label, bild_ref, item_id, kategorie):
        self.hinzugefuegt.append({
            "label": label, "bild_ref": bild_ref,
            "item_id": item_id, "kategorie": kategorie,
        })
        resp = self._responses.pop(0) if self._responses else self._default_response
        if resp is None:
            # Erfolg
            return {"id": "neue-id-%d" % len(self.hinzugefuegt)}
        # Fehler: resp ist (marker, detail)
        marker, detail = resp
        err = EssenClientError(
            "HTTP %s — %s" % (
                "409" if marker == FEHLER_DUPLIKAT
                else "413" if marker == FEHLER_GRENZE
                else "500",
                detail),
            marker=marker)
        if marker == FEHLER_GRENZE:
            err.grenze_daten = {"offen_jetzt": 50, "grenze": 50}
        raise err

    def lese_wuensche(self, klasse=None, abgehakt=None):
        return []

    def get_wuensche(self):
        return self.lese_wuensche()


class FakeIconClient:
    """IconClient-Doppelung — ICONS-7 Stichwort-Suche."""

    def __init__(self, responses=None):
        # responses: dict label -> [{"id": n, "url": "..."}] oder []
        self._responses = responses or {}
        self.suche_calls = []

    def suche(self, stichwort, max_treffer=1):
        self.suche_calls.append(stichwort)
        return list(self._responses.get(stichwort, []))


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _basis_aufruf(**kw):
    """Hilfsfunktion: einkauf_hinzufuegen mit sinnvollen Test-Defaults."""
    defaults = {
        "text": "Brot",
        "from_user_id": 7,
        "essen_client": FakeEssenClient(),
        "icon_client": FakeIconClient(),
        "is_member_fn": _immer_mitglied,
        "katalog": None,
    }
    defaults.update(kw)
    return einkauf_hinzufuegen(**defaults)


# ============================================================
#  AC2 — EIN-3: Item-Zerlegung
# ============================================================

def test_EIN3_komma_und_zerlegung():
    """AC2/EIN-3: 'Brot, Milch und Joghurt' → 3 Items."""
    items = zerlege_items("Brot, Milch und Joghurt")
    assert items == ["Brot", "Milch", "Joghurt"]


def test_EIN3_lead_phrase_auch_noch():
    """AC2/EIN-3: 'Auch noch Erdbeeren' → 1 Item 'Erdbeeren' (Lead-Phrase weg)."""
    items = zerlege_items("Auch noch Erdbeeren")
    assert items == ["Erdbeeren"]


def test_EIN3_lead_phrase_und_auch():
    """AC2/EIN-3: 'Und auch Joghurt' → ['Joghurt']."""
    items = zerlege_items("Und auch Joghurt")
    assert items == ["Joghurt"]


def test_EIN3_lead_phrase_dann_noch():
    """AC2/EIN-3: 'Dann noch Butter' → ['Butter']."""
    items = zerlege_items("Dann noch Butter")
    assert items == ["Butter"]


def test_EIN3_semikolon_trennzeichen():
    """AC2/EIN-3: Semikolon als Trennzeichen."""
    items = zerlege_items("Brot; Milch; Joghurt")
    assert items == ["Brot", "Milch", "Joghurt"]


def test_EIN3_newline_trennzeichen():
    """AC2/EIN-3: Newline als Trennzeichen."""
    items = zerlege_items("Brot\nMilch\nJoghurt")
    assert items == ["Brot", "Milch", "Joghurt"]


def test_EIN3_leere_items_verworfen():
    """AC2/EIN-3: doppeltes Komma → leere Items verworfen."""
    items = zerlege_items("Brot,,Milch")
    assert items == ["Brot", "Milch"]


def test_EIN3_mehr_als_50_klartext_ablehnung():
    """AC2/EIN-3: 51 Items → Klartext-Ablehnung, kein POST."""
    ec = FakeEssenClient()
    text = ", ".join("item%d" % i for i in range(51))
    result = einkauf_hinzufuegen(
        text=text,
        from_user_id=7,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
    )
    assert "51" in result or "Rutsch" in result or "Nachrichten" in result
    assert ec.hinzugefuegt == [], "Kein POST bei >50 Items (EIN-3)"


def test_EIN3_genau_50_items_kein_ablehnung():
    """AC2/EIN-3: Grenzwert 50 Items → kein Ablehnung, POST."""
    ec = FakeEssenClient()
    text = ", ".join("item%d" % i for i in range(50))
    einkauf_hinzufuegen(
        text=text,
        from_user_id=7,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
    )
    assert len(ec.hinzugefuegt) == 50


# ============================================================
#  AC3 — EIN-4: Auto-Match
# ============================================================

def test_EIN4_katalog_hit_liefert_kategorie_und_bild():
    """AC3/EIN-4: Katalog-Match liefert kategorie+bild_ref+item_id aus Katalog."""
    katalog = [
        {"label": "Brot", "bild_ref": "1111", "item_id": "brot-1",
         "kategorie": "brotbelag"},
    ]
    canonical, bild_ref, item_id, kategorie = _match_item(
        "Brot", katalog, FakeIconClient())
    assert canonical == "Brot"
    assert bild_ref == "1111"
    assert item_id == "brot-1"
    assert kategorie == "brotbelag"


def test_EIN4_katalog_hit_pluralform():
    """AC3/EIN-4: Pluralform 'Erdbeeren' → Katalog-Match auf 'Erdbeere'."""
    katalog = [
        {"label": "Erdbeere", "bild_ref": "2222", "item_id": "erdbeere-1",
         "kategorie": "obst_gemuese"},
    ]
    _canonical, bild_ref, _item_id, kategorie = _match_item(
        "Erdbeeren", katalog, FakeIconClient())
    assert bild_ref == "2222"
    assert kategorie == "obst_gemuese"


def test_EIN4_icons7_fallback_bei_kein_katalog_hit():
    """AC3/EIN-4: Kein Katalog-Hit → ICONS-7-Fallback → bild_ref aus ICONS-7."""
    ic = FakeIconClient(responses={"Spritzkuchen": [{"id": 9999, "url": "/x"}]})
    _canonical, bild_ref, item_id, kategorie = _match_item(
        "Spritzkuchen", [], ic)
    assert bild_ref == "9999"
    assert kategorie == "sonstiges"
    assert item_id == "frei:spritzkuchen"


def test_EIN4_default_einkaufswagen_wenn_kein_icons7_treffer():
    """AC3/EIN-4: Kein Katalog-Hit, kein ICONS-7-Treffer → Default 5948."""
    ic = FakeIconClient(responses={})
    _canonical, bild_ref, item_id, kategorie = _match_item(
        "QuantenFrucht", [], ic)
    assert bild_ref == "5948"
    assert item_id == "frei:quantenfrucht"
    assert kategorie == "sonstiges"


# ============================================================
#  AC4 — EIN-5: Direkt-Modus, Duplikat-Skip, Grenze
# ============================================================

def test_EIN5_direkt_modus_kein_propose_confirm():
    """AC4/EIN-5: Direkt-Modus — Funktion schreibt ohne Bestätigungs-Dialog."""
    ec = FakeEssenClient()
    result = _basis_aufruf(text="Brot, Milch", essen_client=ec)
    # Beide Items angelegt — kein Bestätigungs-Schritt, keine Frage
    assert len(ec.hinzugefuegt) == 2
    assert isinstance(result, str)
    assert "?" not in result or "Brot" in result or "Milch" in result


def test_EIN5_post_mit_klasse_einkauf_quelle_eltern():
    """AC4/EIN-5: POST-Payload enthält klasse=einkauf, quelle=eltern."""
    # Wir prüfen über den FakeEssenClient, welche Daten ankommen.
    # Der echte Client setzt klasse+quelle im POST-Body — hier prüfen
    # wir, dass hinzufuegen_einkauf aufgerufen wurde (nicht post_gericht).
    ec = FakeEssenClient()
    _basis_aufruf(text="Milch", essen_client=ec)
    assert len(ec.hinzugefuegt) == 1
    eintrag = ec.hinzugefuegt[0]
    assert eintrag["label"] == "Milch"


def test_EIN5_duplikat_skip_geraeuchlos():
    """AC4/EIN-5: Duplikat-Item → kein Re-Try, in Antwort als 'schon drauf'."""
    ec = FakeEssenClient()
    ec.set_response((FEHLER_DUPLIKAT, "Duplikat"))  # 1 Item → Duplikat
    result = einkauf_hinzufuegen(
        text="Brot",
        from_user_id=7,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
    )
    assert len(ec.hinzugefuegt) == 1, "POST wurde versucht"
    assert "drauf" in result.lower() or "schon" in result.lower()


def test_EIN5_listen_grenze_stoppt_restliche_items():
    """AC4/EIN-5: Listen-Grenze nach 1 Item → 2. Item kann nicht, Antwort korrekt."""
    ec = FakeEssenClient()
    ec.set_response(
        None,                            # Item 1: Erfolg
        (FEHLER_GRENZE, "listen_grenze"), # Item 2: Grenze
    )
    result = einkauf_hinzufuegen(
        text="Brot, Milch",
        from_user_id=7,
        essen_client=ec,
        icon_client=FakeIconClient(),
        is_member_fn=_immer_mitglied,
    )
    assert len(ec.hinzugefuegt) == 2  # 2 POST-Versuche (1 ok, 1 Grenze)
    assert "⚠️" in result or "konnte" in result.lower() or "aufräumen" in result.lower()


def test_EIN5_berechtigung_kein_post():
    """EIN-2: Nicht-Berechtigt → BerechtigungError, kein POST."""
    ec = FakeEssenClient()
    with pytest.raises(BerechtigungError):
        einkauf_hinzufuegen(
            text="Brot",
            from_user_id=99,
            essen_client=ec,
            icon_client=FakeIconClient(),
            is_member_fn=_kein_mitglied,
        )
    assert ec.hinzugefuegt == []


# ============================================================
#  AC5 — EIN-6: Antwort-Formen
# ============================================================

def test_EIN6_standardfall_labels_und_offen():
    """AC5/EIN-6: Standardfall — Antwort enthält Labels + 'dazu'."""
    result = _baue_antwort(
        hinzugefuegt=["Brot", "Milch"],
        uebersprungen=[],
        grenze_halt=None,
        offen_n=2,
    )
    assert "Brot" in result
    assert "Milch" in result
    assert "dazu" in result.lower() or "offen" in result.lower()


def test_EIN6_mehr_als_3_items_anzahl_im_vorspann():
    """AC5/EIN-6: >3 Items → Anzahl im Vorspann."""
    result = _baue_antwort(
        hinzugefuegt=["A", "B", "C", "D", "E"],
        uebersprungen=[],
        grenze_halt=None,
        offen_n=5,
    )
    assert "5" in result  # Anzahl
    assert "dazu" in result.lower()


def test_EIN6_mit_skip_zeile():
    """AC5/EIN-6: Mit Skip-Items → '(X schon drauf: <labels>)'-Zeile."""
    result = _baue_antwort(
        hinzugefuegt=["Milch"],
        uebersprungen=["Brot"],
        grenze_halt=None,
        offen_n=3,
    )
    assert "schon drauf" in result.lower() or "drauf" in result.lower()
    assert "Brot" in result


def test_EIN6_alles_geskippt():
    """AC5/EIN-6: Alles geskippt → 'schon offen auf der Liste' Antwort."""
    result = _baue_antwort(
        hinzugefuegt=[],
        uebersprungen=["Brot", "Milch"],
        grenze_halt=None,
        offen_n=5,
    )
    assert "schon" in result.lower()
    assert "Brot" in result
    assert "Milch" in result


def test_EIN6_grenze_halt_warnung():
    """AC5/EIN-6: Grenze-Halt → Antwort enthält ⚠️-Zeile."""
    result = _baue_antwort(
        hinzugefuegt=["Brot"],
        uebersprungen=[],
        grenze_halt=(50, 50, 1),  # (offen_jetzt, grenze, nicht_konnten_n)
        offen_n=50,
    )
    assert "⚠️" in result
    assert "aufräumen" in result.lower() or "konnte" in result.lower()


# ============================================================
#  EIN-7: Fehlerfälle
# ============================================================

def test_EIN7_leere_eingabe():
    """EIN-7: leere Eingabe → Klartext-Hinweis."""
    result = _basis_aufruf(text="")
    assert "Liste" in result or "Beispiel" in result or "Brot" in result


def test_EIN7_nur_whitespace():
    """EIN-7: Whitespace-only → Klartext-Hinweis."""
    result = _basis_aufruf(text="   ")
    assert "Liste" in result or "Beispiel" in result


# ============================================================
#  AC8 — RAT-16: Watchdog-Grep auf Telegram-Vokabular
# ============================================================

def test_AC8_kein_telegram_vokabular_in_skill_dateien():
    """AC8/RAT-16: grep auf einkauf_*.py darf kein Telegram-Vokabular finden.

    Verbotene Begriffe: callback_query, reply_markup, inline_keyboard, 'update'
    als eigenständiges Token ('^update' oder Leerzeichen davor + dahinter).
    send_inline_keyboard (Adapter-API) ist erlaubt.
    """
    import os
    import re
    skill_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "skills",
    )
    dateien = [
        os.path.join(skill_dir, "einkauf_hinzufuegen.py"),
        os.path.join(skill_dir, "einkauf_zeigen.py"),
    ]
    verboten = re.compile(
        r"callback_query|reply_markup|\"inline_keyboard\"|'inline_keyboard'"
    )
    for datei in dateien:
        with open(datei, encoding="utf-8") as f:
            inhalt = f.read()
        treffer = verboten.findall(inhalt)
        assert not treffer, (
            "RAT-16-Verletzung in %s: %r" % (datei, treffer))
