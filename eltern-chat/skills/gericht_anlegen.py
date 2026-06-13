"""Gericht anlegen — specs/platform/gericht-anlegen.md
(GAN-1 … GAN-7, E-GAN-1 … E-GAN-3).

Aufrufbare, trigger-agnostische Funktion (GAN-1, E-GAN-1-Muster):
nimmt {Aktion, Gericht-Daten} und ruft die Essens-Buddy-Gerichte-API
(ESSEN-19) sowie die ICONS-7-Stichwort-Suche (GAN-4). Die Funktion ist
eine bewusste Copy der RPS-Linie (RAT-6/RAT-12 — keine gemeinsame
Schreib-Skill-Abstraktion, bis sie nach dem 2.–3. *gebauten* Skill
ehrlich entsteht).

Operationen (GAN-3):
  - gericht_hinzufuegen      → POST /api/v1/essen/katalog/gerichte
                                {label, bild_ref}      (Icon-Pfad)
  - foto_hinzufuegen         → POST /api/v1/essen/katalog/gerichte
                                {label, foto_ref}      (ESSEN-22 Pfad 1)
  - icon_suchen              → ICONS-7: GET /api/v1/icons/suche?q=<label>&max=3

Pattern (E-GAN-2): **propose→confirm**, NICHT Sofort-Wirkung. Ein neues
Gericht im Familien-Katalog prägt zukünftige Wunsch-Eingaben — die
Vorab-Bestätigung ist die richtige Reibung (RPS-5-analog).

Eingang: Aktion + Gericht-Daten (label/icon_id/foto_ref/icon_stichwort
je nach Aktion), ein EssenClient (GAN-6), ein IconClient (GAN-4,
ICONS-7), ein PhotoClient (ESSEN-22 Pfad 1, optional — nur bei
foto_hinzufuegen genutzt), `is_member_fn` (GAN-2), `from_user_id` (GAN-2).

Ausgang: Ergebnis-Tuple `(signal, daten)`:
  („angelegt",       {"id": <str>})          — POST erfolgreich.
  („icon_kandidaten", {"label": <str>,       — ICONS-7 lieferte Treffer;
                      "kandidaten": [...]}})   Skill legt sie zur Wahl vor.
  („keine_icons",    {"label": <str>})       — ICONS-7 ohne Treffer (GAN-4).
  („abgelehnt",      {})                     — Nicht-Mitglied (GAN-2).
  („grenze",         {"detail": <str>})      — Buddy-4xx (doppeltes Label,
                                               leeres Label, …), EC-7.
  („nicht_erreichbar", {"detail": <str>})   — Buddy nicht erreichbar.
  („nichts_zu_tun",  {"reason": <str>})     — Eingabe unvollständig.
"""

import logging

from skills.essen_client import EssenClientError
from skills.icon_client import IconClientError
from skills.photo_client import PhotoClientError

logger = logging.getLogger(__name__)


# Ergebnis-Signale der Funktion (GAN-1).
SIGNAL_ANGELEGT          = "angelegt"
SIGNAL_ICON_KANDIDATEN   = "icon_kandidaten"
SIGNAL_KEINE_ICONS       = "keine_icons"
SIGNAL_ABGELEHNT         = "abgelehnt"
SIGNAL_GRENZE            = "grenze"
SIGNAL_NICHT_ERREICHBAR  = "nicht_erreichbar"
SIGNAL_NICHTS_ZU_TUN     = "nichts_zu_tun"

# GAN-3: Operationen (V1) + ESSEN-22 Pfad 1.
AKTION_HINZUFUEGEN       = "hinzufuegen"
AKTION_ICON_SUCHEN       = "icon_suchen"
AKTION_FOTO_HINZUFUEGEN  = "foto_hinzufuegen"   # ESSEN-22 Pfad 1


def gericht_anlegen(*, aktion, essen_client, icon_client,
                    is_member_fn, from_user_id,
                    label=None, icon_id=None,
                    icon_stichwort=None, icon_max=3,
                    photo_client=None, medium_bytes=None,
                    filename=None, content_type=None):
    """Gericht anlegen — aufrufbare Funktion (GAN-1).

    Eine **schreibende** Aufgabe (EC-10, GAN-5) mit **propose→confirm**
    (E-GAN-2): die Funktion schreibt direkt im execute()-Pfad — die
    Vorab-Bestätigung sitzt eine Ebene höher (GerichtAnlegenTask.propose).

    `aktion`        — AKTION_HINZUFUEGEN, AKTION_ICON_SUCHEN oder
                      AKTION_FOTO_HINZUFUEGEN (GAN-3/GAN-4/ESSEN-22 Pfad 1).
    `essen_client`  — EssenClient-Instanz mit post_gericht() (GAN-6).
    `icon_client`   — IconClient-Instanz für ICONS-7 (GAN-4).
    `is_member_fn`  — Callable `(user_id) -> bool` (GAN-2).
    `from_user_id`  — Telegram-User-ID des Aufrufers (GAN-2).
    `photo_client`  — PhotoClient-Instanz (ESSEN-22 Pfad 1, nur bei
                      AKTION_FOTO_HINZUFUEGEN benötigt).

    Parameter je Aktion:
      hinzufuegen      — `label`, `icon_id` (ARASAAC-ID aus vorheriger
                         icon_suchen-Antwort).
      icon_suchen      — `icon_stichwort`, optional `icon_max` (≤3).
      foto_hinzufuegen — `label`, `medium_bytes`, optional `filename`,
                         `content_type` (ESSEN-22 Pfad 1).

    Ergebnis: (signal, daten) — siehe Modul-Docstring.
    """
    # GAN-2: Berechtigung — live geprüft, identisch zum RPS-/WZE-Muster.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("gericht_anlegen: User %s nicht in Familien-Gruppe "
                    "— abgelehnt (GAN-2)", from_user_id)
        return SIGNAL_ABGELEHNT, {}

    if aktion == AKTION_ICON_SUCHEN:
        return _icon_suchen(icon_client, icon_stichwort, icon_max)

    if aktion == AKTION_HINZUFUEGEN:
        return _hinzufuegen(essen_client, label, icon_id)

    if aktion == AKTION_FOTO_HINZUFUEGEN:
        return _foto_hinzufuegen(
            photo_client, essen_client, label,
            medium_bytes, filename, content_type)

    logger.warning("gericht_anlegen: unbekannte Aktion %r — nichts zu tun",
                   aktion)
    return SIGNAL_NICHTS_ZU_TUN, {"reason": "unbekannte Aktion"}


# ============================================================
#  GAN-4 — ICONS-7-Stichwort-Suche (kein Schreiben)
# ============================================================

def _icon_suchen(icon_client, stichwort, max_treffer):
    """GAN-4: ICONS-7-Suche mit bis zu drei Kandidaten.

    Liefert SIGNAL_ICON_KANDIDATEN mit der Liste der Treffer, oder
    SIGNAL_KEINE_ICONS, wenn der Router nichts findet. Erfindet **keine**
    ID, fällt **nicht** auf ARASAAC zurück (E-GAN-3, GAN-4 letzter Absatz).
    """
    if not stichwort or not str(stichwort).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Stichwort"}

    # GAN-4: bis zu drei Kandidaten — Hard-Cap auf 3.
    cap = min(int(max_treffer or 3), 3)

    try:
        kandidaten = icon_client.suche(stichwort, max_treffer=cap)
    except IconClientError as e:
        logger.warning("gericht_anlegen: ICONS-7 nicht erreichbar — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": str(e)}

    if not kandidaten:
        # GAN-4: keine Treffer → ehrlich melden, kein erfundenes Piktogramm
        # (E-GAN-3: kein eigener ARASAAC-Bezug).
        logger.info("gericht_anlegen: ICONS-7 keine Treffer für %r",
                    stichwort)
        return SIGNAL_KEINE_ICONS, {"label": stichwort}

    return SIGNAL_ICON_KANDIDATEN, {"label": stichwort,
                                    "kandidaten": list(kandidaten)}


# ============================================================
#  GAN-3 — POST /api/v1/essen/katalog/gerichte
# ============================================================

def _hinzufuegen(essen_client, label, icon_id):
    """GAN-3: ein neues Gericht anlegen (Icon-Pfad).

    Erwartet ein nicht-leeres `label` und eine gewählte `icon_id`
    (ARASAAC-ID aus einer ICONS-7-Suche; der Skill rät nichts, GAN-4/E-GAN-3).

    4xx-Antwort (z. B. doppeltes Label → 409, leeres Label → 4xx)
    → SIGNAL_GRENZE mit der Buddy-Fehlermeldung (GAN-5, EC-7), kein Re-Try.
    """
    if not label or not str(label).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Label"}
    if not icon_id or not str(icon_id).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Icon"}

    try:
        response = essen_client.post_gericht(
            name=str(label).strip(),
            icon_id=str(icon_id).strip(),
        )
    except EssenClientError as e:
        return _essen_fehler("POST", e)

    new_id = response.get("id")
    logger.info("gericht_anlegen: angelegt label=%r id=%s (ESSEN-19)",
                label, new_id)
    return SIGNAL_ANGELEGT, {"id": new_id}


def _foto_hinzufuegen(photo_client, essen_client, label,
                      medium_bytes, filename, content_type):
    """ESSEN-22 Pfad 1: Gericht mit Foto anlegen.

    Erwartet ein nicht-leeres `label` und `medium_bytes` (Foto-Bytes).
    Kein `photo_client` → SIGNAL_NICHTS_ZU_TUN.

    Ablauf:
      1. Foto an Photo-Buddy hochladen (PHOTO-13) → foto_ref.
      2. POST /api/v1/essen/katalog/gerichte {label, foto_ref} → Gericht-ID.

    4xx vom Photo-Buddy oder Essen-Buddy → SIGNAL_GRENZE (EC-7).
    Verbindungsfehler → SIGNAL_NICHT_ERREICHBAR.
    """
    if not label or not str(label).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Label"}
    if not medium_bytes:
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Foto"}
    if photo_client is None:
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Photo-Client"}

    # Schritt 1: Foto hochladen.
    # T799: in_library=False — Essen-Fotos sollen nicht im Bilderrahmen erscheinen.
    try:
        photo_response = photo_client.upload_medium(
            medium_bytes=medium_bytes,
            filename=filename or "foto.jpg",
            content_type=content_type or "image/jpeg",
            in_library=False,
        )
    except PhotoClientError as e:
        fehler_str = str(e)
        if "HTTP 4" in fehler_str:
            logger.info("gericht_anlegen: Photo-Buddy hat Foto abgelehnt — %s", e)
            return SIGNAL_GRENZE, {"detail": fehler_str}
        logger.warning("gericht_anlegen: Photo-Buddy nicht erreichbar — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}

    foto_ref = photo_response.get("id")
    logger.info("gericht_anlegen: Foto hochgeladen foto_ref=%s", foto_ref)

    # Schritt 2: Gericht mit foto_ref anlegen.
    try:
        response = essen_client.post_gericht(
            name=str(label).strip(),
            foto_ref=str(foto_ref),
        )
    except EssenClientError as e:
        return _essen_fehler("POST", e)

    new_id = response.get("id")
    logger.info("gericht_anlegen: angelegt mit Foto label=%r id=%s foto_ref=%s "
                "(ESSEN-22 Pfad 1)", label, new_id, foto_ref)
    return SIGNAL_ANGELEGT, {"id": new_id}


# ============================================================
#  Helpers
# ============================================================

def _essen_fehler(method, exc):
    """GAN-5/EC-7: übersetzt einen EssenClientError in (signal, daten).

    4xx (Buddy-Validierung — doppeltes Label, leeres Label, …)
    → SIGNAL_GRENZE: ehrliche fachliche Grenze, kein Re-Try.
    Sonst (5xx, Connection-refused, Timeout) → SIGNAL_NICHT_ERREICHBAR.
    """
    fehler_str = str(exc)
    if "HTTP 4" in fehler_str:
        logger.info("gericht_anlegen: Buddy hat %s abgelehnt — %s",
                    method, exc)
        return SIGNAL_GRENZE, {"detail": fehler_str}
    logger.warning("gericht_anlegen: Essens-Buddy nicht erreichbar — %s",
                   exc)
    return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}
