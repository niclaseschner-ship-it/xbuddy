"""T1340-S2 — Whitelist-Verdrahtung: zielgruppe-Durchreichung + META-Append.

AC1: POST /folgen-vorschlag reicht zielgruppe=instance.zielgruppe (und tiefe)
     an erzeuge_folgen_vorschlag durch. Emil-Instanz (erwachsen) != Kind-Default.
     Kind-Pfad DARF sich nicht ändern: zielgruppe default=kind unverändert.
AC2: album_builder.baue_album hängt den META-Block (via llm_service.format_meta_
     historie) an folgen-historie.md an, wenn meta übergeben wird. Kind-Eintrag
     (meta=None) bleibt byte-gleich zur Vorform (kein Anhang).
"""

import json
import os
import sys
from unittest.mock import patch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from hoerspiel import album_builder, data_io, llm_service  # noqa: E402  # noqa: E402

# ============================================================
#  Hilfsfunktionen
# ============================================================

_SAMPLE_META = {
    "these": "Die Zukunft gehört dem Qubit.",
    "schnitt": "Vom Transistor zum Quantengate.",
    "quellen": ["https://example.org/quantum"],
    "begriffe_neu": ["Qubit", "Superposition"],
}


def _vorschlag_erwachsen():
    return {
        "titel": "Deep Dive",
        "folgen-nr-vorschlag": 23,
        "text": "Folge 23: Deep Dive.\n\nKIM: Los.\n\nRUBEN: Ja.",
        "meta": _SAMPLE_META,
    }


# ============================================================
#  AC1 — zielgruppe-Durchreichung (main.py endpoint)
# ============================================================

class TestZielgruppeDurchreichung:
    """AC1: Der HTTP-Endpoint /folgen-vorschlag reicht zielgruppe durch."""

    def test_erwachsen_instanz_reicht_zielgruppe_erwachsen(self, client, data_root):
        """AC1: instance.json mit zielgruppe=erwachsen → erzeuge_folgen_vorschlag
        wird mit zielgruppe='erwachsen' aufgerufen."""
        instance = {
            "kind_id": "mia",
            "name": "Emil",
            "alter": 39,
            "zielgruppe": "erwachsen",
            "serien_name": "Emil Deep-Dives",
            "ton": "sachlich, direkt",
            "perspektive": "dialogisch",
        }
        with open(os.path.join(data_root, "instance.json"), "w") as f:
            json.dump(instance, f)

        captured = {}

        def fake_erzeuge(**kwargs):
            captured.update(kwargs)
            return _vorschlag_erwachsen()

        with patch.object(llm_service, "erzeuge_folgen_vorschlag",
                          side_effect=fake_erzeuge):
            resp = client.post(
                "/api/v1/hoerspiel/mia/folgen-vorschlag",
                json={"idee": "Quantencomputing und Risiken"},
            )

        assert resp.status_code == 200, resp.get_json()
        assert captured.get("zielgruppe") == "erwachsen", (
            "main.py muss zielgruppe=instance.zielgruppe ('erwachsen') durchreichen")

    def test_tiefe_aus_body_wird_durchgereicht(self, client, data_root):
        """AC1: ?tiefe aus dem Request-Body landet in erzeuge_folgen_vorschlag."""
        instance = {
            "kind_id": "mia",
            "name": "Emil",
            "zielgruppe": "erwachsen",
        }
        with open(os.path.join(data_root, "instance.json"), "w") as f:
            json.dump(instance, f)

        captured = {}

        def fake_erzeuge(**kwargs):
            captured.update(kwargs)
            return _vorschlag_erwachsen()

        with patch.object(llm_service, "erzeuge_folgen_vorschlag",
                          side_effect=fake_erzeuge):
            resp = client.post(
                "/api/v1/hoerspiel/mia/folgen-vorschlag",
                json={"idee": "Thema", "tiefe": "tief"},
            )

        assert resp.status_code == 200, resp.get_json()
        assert captured.get("tiefe") == "tief"

    def test_tiefe_default_mittel_ohne_body_feld(self, client, data_root):
        """AC1: fehlendes tiefe-Feld im Body → Default 'mittel'."""
        captured = {}

        def fake_erzeuge(**kwargs):
            captured.update(kwargs)
            return {
                "titel": "T", "folgen-nr-vorschlag": 1,
                "text": "Folge 1: T.\n\nText.",
            }

        with patch.object(llm_service, "erzeuge_folgen_vorschlag",
                          side_effect=fake_erzeuge):
            resp = client.post(
                "/api/v1/hoerspiel/mia/folgen-vorschlag",
                json={"idee": "Thema"},
            )

        assert resp.status_code == 200
        assert captured.get("tiefe") == "mittel"

    def test_kind_instanz_reicht_zielgruppe_kind(self, client, data_root):
        """AC1 / Kind-Pfad-Guard: ohne instance.json → zielgruppe Default 'kind'
        (mia/finn-Instanzen unverändert)."""
        # Kein instance.json → ENV-Fallback → zielgruppe="kind"
        captured = {}

        def fake_erzeuge(**kwargs):
            captured.update(kwargs)
            return {
                "titel": "T", "folgen-nr-vorschlag": 1,
                "text": "Folge 1: T.\n\nText.",
            }

        with patch.object(llm_service, "erzeuge_folgen_vorschlag",
                          side_effect=fake_erzeuge):
            resp = client.post(
                "/api/v1/hoerspiel/mia/folgen-vorschlag",
                json={"idee": "Stigi findet Federn"},
            )

        assert resp.status_code == 200
        assert captured.get("zielgruppe") == "kind", (
            "Kind-Instanz MUSS zielgruppe='kind' liefern — kein Recherche-Trigger")


# ============================================================
#  AC2 — META-Append (album_builder)
# ============================================================

class TestMetaAppend:
    """AC2: baue_album hängt META-Block an folgen-historie.md an."""

    def test_meta_block_wird_in_historie_angehaengt(self, data_root, fake_llm,
                                                     fake_tts, fixed_now):
        """AC2: baue_album(meta={...}) → folgen-historie.md enthält META-Felder."""
        text = "\n\n".join(["wort " * 80 for _ in range(2)])
        album_builder.baue_album(
            titel="Deep Dive Quantencomputing",
            text=text, voice="shimmer", idee="Quantencomputing",
            data_root=data_root, kind_id="mia",
            llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
            meta=_SAMPLE_META,
        )
        historie = data_io.read_text_or_empty(
            os.path.join(data_root, "folgen-historie.md"))

        assert "Die Zukunft gehört dem Qubit." in historie, (
            "META-These fehlt im Historie-Eintrag")
        assert "Qubit" in historie, "META-Begriffe fehlen im Historie-Eintrag"
        assert "https://example.org/quantum" in historie, (
            "META-Quelle fehlt im Historie-Eintrag")
        assert "Vom Transistor zum Quantengate." in historie, (
            "META-Schnitt fehlt im Historie-Eintrag")

    def test_kein_meta_eintrag_unpetraendert(self, data_root, fake_llm, fake_tts,
                                            fixed_now):
        """AC2 / Kind-Guard: baue_album ohne meta → kein META-Block in Historie
        (Kind-Einträge byte-gleich zur Vorform)."""
        text = "\n\n".join(["wort " * 80 for _ in range(2)])
        album_builder.baue_album(
            titel="Mia und der Schmetterling",
            text=text, voice="shimmer", idee="Schmetterling",
            data_root=data_root, kind_id="mia",
            llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
            # meta=None (explizit kein META)
        )
        historie = data_io.read_text_or_empty(
            os.path.join(data_root, "folgen-historie.md"))

        assert "These:" not in historie, (
            "META-Block darf NICHT in Kind-Eintrag (meta=None)")
        assert "Schnitt:" not in historie

    def test_leerer_meta_block_wird_nicht_angehaengt(self, data_root, fake_llm,
                                                      fake_tts, fixed_now):
        """AC2: leeres META-Dict (all fields empty) → kein Anhang."""
        leeres_meta = {"these": "", "schnitt": "", "quellen": [], "begriffe_neu": []}
        text = "\n\n".join(["wort " * 80 for _ in range(2)])
        album_builder.baue_album(
            titel="Test Leer",
            text=text, voice="shimmer", idee="leer",
            data_root=data_root, kind_id="mia",
            llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
            meta=leeres_meta,
        )
        historie = data_io.read_text_or_empty(
            os.path.join(data_root, "folgen-historie.md"))
        assert "These:" not in historie
        assert "Schnitt:" not in historie

    def test_format_historie_entry_haengt_meta_an(self):
        """Unit-Test: _format_historie_entry mit meta → enthält META-Block."""
        entry = album_builder._format_historie_entry(
            nummer=5, titel="Test", datum="2026-07-06",
            synopse="Ein Test.", meta=_SAMPLE_META,
        )
        assert "## Folge 5: Test" in entry
        assert "Die Zukunft gehört dem Qubit." in entry
        assert "https://example.org/quantum" in entry

    def test_format_historie_entry_ohne_meta_wie_vorher(self):
        """Unit-Test: _format_historie_entry ohne meta → exakt Vorform."""
        entry = album_builder._format_historie_entry(
            nummer=5, titel="Test", datum="2026-07-06", synopse="Synopse.",
        )
        expected = "\n## Folge 5: Test\n*Erschienen:* 2026-07-06\n\nSynopse.\n"
        assert entry == expected, (
            "Kind-Eintrag (meta=None) muss byte-gleich zur Vorform sein")
