"""Tests für _media_naht — die Live-Pfad-Naht (FSE-3 / D4, Refs #393).

`_media_naht(msg)` übersetzt IncomingMessage-Felder in das Tupel
`(media_telegram_file_id, medium_typ)`, das der TurnContext bekommt.
Abgedeckt: alle Pfade gemäß Spec FSE-3 sowie die Prioritäts-Reihenfolge
(natives Foto > natives Video > Video-als-Dokument) und den Leer-Fall.
"""

import pytest
from fakes import make_message
from main import _media_naht

# ============================================================
#  Tabellen-Fälle — FSE-3 Pfade einzeln
# ============================================================

@pytest.mark.parametrize(("kwargs", "expected"), [
    # Pflicht-Fall 1: natives Foto → ("ph-1", "foto")
    ({"photo_file_id": "ph-1"}, ("ph-1", "foto")),
    # Pflicht-Fall 2: natives Video → ("vi-1", "video")
    ({"video_file_id": "vi-1"}, ("vi-1", "video")),
    # Pflicht-Fall 3: Dokument mit video/mp4-Mime → ("do-1", "video")
    ({"document_file_id": "do-1", "document_mime_type": "video/mp4"},
     ("do-1", "video")),
    # Pflicht-Fall 4: Dokument mit application/pdf → kein FSE-Medium
    ({"document_file_id": "do-2", "document_mime_type": "application/pdf"},
     (None, None)),
    # Leer-Default: keine Medien-Felder → (None, None)
    ({}, (None, None)),
    # Priorität photo > video: beide gesetzt → Foto gewinnt
    ({"photo_file_id": "ph-1", "video_file_id": "vi-1"}, ("ph-1", "foto")),
    # Priorität video > doc-video: beide gesetzt → natives Video gewinnt
    ({"video_file_id": "vi-1",
      "document_file_id": "do-1", "document_mime_type": "video/mp4"},
     ("vi-1", "video")),
    # Dokument ohne Mime-Type (leerer String) → kein FSE-Medium
    ({"document_file_id": "do-3", "document_mime_type": ""},
     (None, None)),
])
def test_media_naht_tabelle(kwargs, expected):
    """FSE-3: _media_naht bildet IncomingMessage-Felder korrekt auf (file_id, typ)
    ab — alle Pfade und Prioritäten abgedeckt."""
    msg = make_message(**kwargs)
    assert _media_naht(msg) == expected
