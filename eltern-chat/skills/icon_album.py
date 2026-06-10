"""ID-Wahl-Album-Helper (TASK-10b).

Schickt ICONS-7-Trefferkandidaten als Telegram-Bild-Album (2-3 Treffer)
oder Einzel-Foto (1 Treffer) — ohne Captions. Bildquelle: relative URL
aus ICONS-7-Antwort, konkateniert mit icon_origin_url.

Konvention: conventions/tasks.md TASK-10b.
Konsumenten heute: routine_punkte_setzen, gericht_anlegen (gebaut),
plan_aktivitaeten_setzen (spec-aligned, noch nicht gebaut).
"""

import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class IconAlbumError(Exception):
    """Fehler beim Holen oder Senden der ID-Wahl-Bilder (TASK-10b)."""


def _holen(url, opener=None):
    """Holt das PNG-File von der HTTP-URL als bytes."""
    open_fn = opener.open if opener is not None else urllib.request.urlopen
    try:
        with open_fn(url) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as e:
        raise IconAlbumError(
            "Bild von %s nicht erreichbar: %s" % (url, e)) from e


def zeige_kandidaten(tg, chat_id, kandidaten, icon_origin_url, *, opener=None):
    """ID-Wahl-Album-Helper (TASK-10b).

    `kandidaten` ist eine Liste von {id, url}-Dicts in der vom Aufrufer
    übergebenen Reihenfolge — der Helper sortiert/filtert NICHT.
    Position 1 entspricht `kandidaten[0]`, Position 2 entspricht
    `kandidaten[1]`, usw.

    Trefferzahl-Fallback:
      - 0 Treffer → no-op (Sicherheitsnetz; Skill sollte vorher abfangen)
      - 1 Treffer → tg.send_photo
      - ≥2 Treffer → tg.send_media_group (Transport erlaubt 2-10 Items)

    TASK-10b nennt ICONS-7 als Begrenzung auf 3 Treffer; die Disziplin
    liegt im Skill (RPS-4 / GAN-4 / PAS-4 setzen max=3 in der ICONS-7-
    Suche), nicht im Helper. send_media_group wirft ValueError ab >10.

    Captions werden NICHT gesetzt (TASK-10b: das Mapping liefert der
    Skill im Tool-Result an das LLM).

    Bei HTTP-Fehler beim Holen eines Bildes: IconAlbumError.
    """
    if not kandidaten:
        return  # no-op

    origin = icon_origin_url.rstrip("/")

    if len(kandidaten) == 1:
        k = kandidaten[0]
        png = _holen(origin + k["url"], opener=opener)
        return tg.send_photo(chat_id, "%s.png" % k["id"], png, caption=None)

    items = []
    for k in kandidaten:
        png = _holen(origin + k["url"], opener=opener)
        items.append(("%s.png" % k["id"], png, None))  # caption=None
    return tg.send_media_group(chat_id, items)
