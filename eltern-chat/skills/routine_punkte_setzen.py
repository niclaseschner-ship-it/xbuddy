"""Routine-Punkte setzen — specs/platform/routine-punkte-setzen.md
(RPS-1 … RPS-7, E-RPS-1, E-RPS-2).

Aufrufbare, trigger-agnostische Funktion (RPS-1, E-RZS-1-Muster):
nimmt {Operation, Punkt-Daten} und ruft die Routine-Items-API (ROUTINE-14)
sowie die ICONS-7-Stichwort-Suche (RPS-4). Die Funktion ist eine bewusste
Copy der RZS-/TES-Linie (RAT-6/RAT-12 — keine gemeinsame Schreib-Skill-
Abstraktion, bis sie nach dem 2.-3. *gebauten* Skill ehrlich entsteht).

**Nur Schreib-Operationen** (RPS-3 V1.2 Lego-Trennung): Lesen ist in
`routine_punkte_lesen.py` (EC-9, ReadTask) ausgegliedert.

Operationen (RPS-3, V1.2):
  - dauerhaft hinzufügen  → POST  /api/v1/routine/items {quelle: default}
  - dauerhaft löschen     → DELETE /api/v1/routine/items/<id>
  - dauerhaft Reihenfolge → PUT   /api/v1/routine/items (geordnete Liste)
  - einmalig hinzufügen   → POST  /api/v1/routine/items {quelle: einmalig}

**Umbenennen ist NICHT Teil von V1.2** (Spec Z. 31-32, 62 — Nic-Entscheid
2026-06-07): hinzufügen + löschen decken den Bedarf. Der Skill bietet
das Verb deshalb gar nicht erst an.

Pattern (E-RPS-1): **propose→confirm**, NICHT Sofort-Wirkung wie FSE. Eine
Änderung der dauerhaften Punkt-Liste ist nicht harmlos genug für ein Undo-
Sicherheitsnetz. Hier reicht das EC-10-Bestätigungs-Gate des Tasks; der Skill
selbst schreibt im execute()-Pfad direkt — die Bestätigung sitzt eine Ebene
höher (RoutinePunkteSetzenTask.propose/execute).

Eingang: Operation + Punkt-Daten (label/item_id/items je nach Operation),
ein RoutineClient (RPS-6, Items-API-Naht), ein IconClient (RPS-4, ICONS-7-
Naht), `is_member_fn` (RPS-2), `from_user_id` (RPS-2).

Ausgang: Ergebnis-Tuple `(signal, daten)`:
  („hinzugefuegt",  {"id": <str>, "quelle": <str>})  — POST erfolgreich.
  („geloescht",     {"id": <str>})                   — DELETE erfolgreich.
  („neugeordnet",   {"count": <int>})                — PUT erfolgreich.
  („icon_kandidaten", {"label": <str>, "kandidaten":  — ICONS-7 lieferte
                      [{id, url}, …]})                 Treffer; Skill legt
                                                       sie zur Wahl vor (RPS-4).
  („keine_icons",   {"label": <str>})                — ICONS-7 ohne Treffer (RPS-4).
  („abgelehnt",     {})                              — Nicht-Mitglied (RPS-2).
  („grenze",        {"detail": <str>})               — Buddy-4xx (>8 Punkte,
                                                       ID nicht gefunden …),
                                                       ehrliche Grenze (RPS-5,
                                                       EC-7).
  („nicht_erreichbar", {"detail": <str>})            — Buddy nicht erreichbar.
  („nichts_zu_tun", {"reason": <str>})               — Eingabe unvollständig
                                                       (kein Label/keine ID).
"""

import logging

from skills.icon_client import IconClientError
from skills.routine_client import RoutineClientError

logger = logging.getLogger(__name__)


# RPS-1: Ergebnis-Signale der Funktion (nur Schreib-Signale).
SIGNAL_HINZUGEFUEGT      = "hinzugefuegt"
SIGNAL_GELOESCHT         = "geloescht"
SIGNAL_NEUGEORDNET       = "neugeordnet"
SIGNAL_ICON_KANDIDATEN   = "icon_kandidaten"
SIGNAL_KEINE_ICONS       = "keine_icons"
SIGNAL_ABGELEHNT         = "abgelehnt"
SIGNAL_GRENZE            = "grenze"
SIGNAL_NICHT_ERREICHBAR  = "nicht_erreichbar"
SIGNAL_NICHTS_ZU_TUN     = "nichts_zu_tun"

# RPS-3: Schreib-Operationen — V1.2, KEIN Umbenennen (Spec Z. 31-32).
# AKTION_LISTE (Lesen) ist in routine_punkte_lesen.py ausgegliedert (EC-9).
AKTION_HINZUFUEGEN     = "hinzufuegen"      # dauerhaft (default)
AKTION_EINMALIG        = "einmalig"          # nur für heute (ROUTINE-6)
AKTION_LOESCHEN        = "loeschen"
AKTION_NEU_ORDNEN      = "neu_ordnen"
AKTION_ICON_SUCHEN     = "icon_suchen"       # RPS-4: ICONS-7-Suche ohne Schreiben

# RPS-3 / RPS-4: Quellen, in die der Buddy schreibt.
QUELLE_DEFAULT  = "default"
QUELLE_EINMALIG = "einmalig"


def routine_punkte_setzen(*, aktion, routine_client, icon_client,
                          is_member_fn, from_user_id,
                          label=None, piktogramm=None,
                          item_id=None, items=None,
                          item_name=None, ziel_position=None,
                          icon_stichwort=None, icon_max=3):
    """Routine-Punkte setzen — aufrufbare Funktion (RPS-1).

    Eine **schreibende** Aufgabe (EC-10, RPS-5) mit **propose→confirm**
    (E-RPS-1): die Funktion schreibt direkt im execute()-Pfad — die
    Vorab-Bestätigung sitzt eine Ebene höher (RoutinePunkteSetzenTask.propose).

    Lesen (aktion=liste) ist in `routine_punkte_lesen.py` ausgegliedert
    (EC-9, ReadTask — Lego-Trennung nach Genre).

    `aktion`        — Eine der AKTION_*-Konstanten (RPS-3).
    `routine_client`— RoutineClient-Instanz mit Items-Methoden (RPS-6).
    `icon_client`   — IconClient-Instanz für ICONS-7 (RPS-4).
    `is_member_fn`  — Callable `(user_id) -> bool` (RPS-2).
    `from_user_id`  — Telegram-User-ID des Aufrufers (RPS-2).

    Parameter je Aktion:
      hinzufuegen / einmalig — `label`, `piktogramm` (ARASAAC-ID).
      loeschen               — `item_id`.
      neu_ordnen             — `items` (Liste {id, label, piktogramm}).
      neu_ordnen mit Einzel-Verschieben — `item_name` + `ziel_position` (V1.2).
      icon_suchen            — `icon_stichwort`, optional `icon_max` (≤3).

    Ergebnis: (signal, daten) — siehe Modul-Docstring.
    """
    # RPS-2: Berechtigung — live geprüft, identisch zum RZS-/FSE-Muster.
    # Die Prüfung liegt **bei der Funktion** (E-RZS-1), nicht beim Trigger.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("routine_punkte_setzen: User %s nicht in Familien-Gruppe "
                    "— abgelehnt (RPS-2)", from_user_id)
        return SIGNAL_ABGELEHNT, {}

    if aktion == AKTION_ICON_SUCHEN:
        return _icon_suchen(icon_client, icon_stichwort, icon_max)

    if aktion == AKTION_HINZUFUEGEN:
        return _hinzufuegen(routine_client, QUELLE_DEFAULT, label, piktogramm)

    if aktion == AKTION_EINMALIG:
        return _hinzufuegen(routine_client, QUELLE_EINMALIG, label, piktogramm)

    if aktion == AKTION_LOESCHEN:
        return _loeschen(routine_client, item_id)

    if aktion == AKTION_NEU_ORDNEN:
        # V1.2: Einzel-Verschieben via item_name + ziel_position (RPS-3).
        if item_name is not None and ziel_position is not None:
            return _einzel_verschieben(routine_client, item_name, ziel_position)
        return _neu_ordnen(routine_client, items)

    logger.warning("routine_punkte_setzen: unbekannte Aktion %r — nichts zu tun",
                   aktion)
    return SIGNAL_NICHTS_ZU_TUN, {"reason": "unbekannte Aktion"}


# ============================================================
#  RPS-4 — ICONS-7-Stichwort-Suche (kein Schreiben)
# ============================================================

def _icon_suchen(icon_client, stichwort, max_treffer):
    """RPS-4: ICONS-7-Suche mit bis zu drei Kandidaten (Spec Z. 70-71).

    Liefert SIGNAL_ICON_KANDIDATEN mit der Liste der Treffer, oder
    SIGNAL_KEINE_ICONS, wenn der Router nichts findet. Erfindet **keine**
    ID, fällt **nicht** auf ARASAAC zurück (E-RPS-2, RPS-4 letzter Absatz).
    """
    if not stichwort or not str(stichwort).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Stichwort"}

    # Spec verlangt „bis zu drei Kandidaten" — wir hartcappen auf 3 als
    # obere Grenze, der Router-Endpunkt akzeptiert Größeres aber ICONS-7
    # ist der Vertrag (RPS-4 Z. 70).
    cap = min(int(max_treffer or 3), 3)

    try:
        kandidaten = icon_client.suche(stichwort, max_treffer=cap)
    except IconClientError as e:
        logger.warning("routine_punkte_setzen: ICONS-7 nicht erreichbar — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": str(e)}

    if not kandidaten:
        # RPS-4: ICONS-7 ohne Treffer → ehrlich melden, kein erfundenes
        # Piktogramm (E-RPS-2).
        logger.info("routine_punkte_setzen: ICONS-7 keine Treffer für %r",
                    stichwort)
        return SIGNAL_KEINE_ICONS, {"label": stichwort}

    return SIGNAL_ICON_KANDIDATEN, {"label": stichwort,
                                    "kandidaten": list(kandidaten)}


# ============================================================
#  RPS-3 V1.2 — Einzel-Verschieben (item_name → id intern auflösen)
# ============================================================

def _einzel_verschieben(routine_client, item_name, ziel_position):
    """RPS-3 V1.2: Einzel-Verschieben — löst item_name→id intern auf.

    Holt über GET /api/v1/routine/items die aktuelle default-Liste,
    findet das Item per case-insensitivem Best-Match auf dem Label,
    baut die neue geordnete Liste und schickt PUT.

    Eltern sehen keine IDs (RPS-3 V1.2-Klausel). Bug-#553-Regression:
    nicht die ID-Position wird neu gesetzt, sondern das Item mit dem
    passenden Namen wird auf ziel_position (1-basiert) verschoben.
    """
    if not item_name or not str(item_name).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein item_name"}
    try:
        ziel_pos_int = int(ziel_position)
    except (TypeError, ValueError):
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "ziel_position muss eine Ganzzahl sein"}

    # GET aktuelle Liste (intern — Eltern sehen keine IDs)
    try:
        liste_daten = routine_client.get_items()
    except RoutineClientError as e:
        return _routine_fehler("GET", e)

    default_items = list(liste_daten.get("default") or [])
    if not default_items:
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "keine default-Items vorhanden"}

    # item_name→id: case-insensitiver Best-Match auf label
    name_lower = str(item_name).strip().lower()
    gefundenes = None
    for item in default_items:
        if str(item.get("label", "")).strip().lower() == name_lower:
            gefundenes = item
            break
    # Fallback: enthaltener Teilstring
    if gefundenes is None:
        for item in default_items:
            if name_lower in str(item.get("label", "")).strip().lower():
                gefundenes = item
                break

    if gefundenes is None:
        return SIGNAL_NICHTS_ZU_TUN, {
            "reason": "Item mit Name %r nicht in der Liste gefunden" % item_name}

    # Einzel-Verschieben: gefundenes Item aus der Liste nehmen,
    # an ziel_position (1-basiert) einsetzen.
    # ziel_pos_int klemmen auf [1, len(default_items)]
    neue_pos_0 = max(0, min(ziel_pos_int - 1, len(default_items) - 1))
    neue_liste = [x for x in default_items if x.get("id") != gefundenes.get("id")]
    neue_liste.insert(neue_pos_0, gefundenes)

    try:
        response = routine_client.replace_default_items(neue_liste)
    except RoutineClientError as e:
        return _routine_fehler("PUT", e)

    count = response.get("count", len(neue_liste))
    logger.info("routine_punkte_setzen: Einzel-Verschieben %r → Position %d "
                "(id=%s, count=%d)",
                item_name, ziel_pos_int, gefundenes.get("id"), count)
    return SIGNAL_NEUGEORDNET, {"count": count}


# ============================================================
#  RPS-3 — POST /api/v1/routine/items
# ============================================================

def _hinzufuegen(routine_client, quelle, label, piktogramm):
    """RPS-3: einen neuen Punkt (default oder einmalig) anlegen.

    Erwartet ein nicht-leeres `label` und eine gewählte `piktogramm`-ID
    (RPS-4 hat sie geliefert; der Skill rät nichts).

    4xx-Antwort (z. B. >8 Punkte, ROUTINE-19) → SIGNAL_GRENZE mit der
    Buddy-Fehlermeldung (RPS-5, EC-7), kein Re-Try.
    """
    if not label or not str(label).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Label"}
    if not piktogramm or not str(piktogramm).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Piktogramm"}

    try:
        response = routine_client.add_item(
            quelle=quelle,
            label=str(label).strip(),
            piktogramm=str(piktogramm).strip(),
        )
    except RoutineClientError as e:
        return _routine_fehler("POST", e)

    new_id = response.get("id")
    logger.info("routine_punkte_setzen: hinzugefügt quelle=%s id=%s "
                "(ROUTINE-14, #354)", quelle, new_id)
    return SIGNAL_HINZUGEFUEGT, {"id": new_id, "quelle": quelle}


# ============================================================
#  RPS-3 — DELETE /api/v1/routine/items/<id>
# ============================================================

def _loeschen(routine_client, item_id):
    """RPS-3: einen Punkt entfernen (default oder einmalig — der Buddy
    entscheidet anhand des ID-Präfixes, ROUTINE-5)."""
    if not item_id or not str(item_id).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "keine item_id"}

    try:
        routine_client.delete_item(str(item_id).strip())
    except RoutineClientError as e:
        return _routine_fehler("DELETE", e)

    logger.info("routine_punkte_setzen: gelöscht id=%s (ROUTINE-14, #354)",
                item_id)
    return SIGNAL_GELOESCHT, {"id": item_id}


# ============================================================
#  RPS-3 — PUT /api/v1/routine/items (Reihenfolge / Bulk-Replace)
# ============================================================

def _neu_ordnen(routine_client, items):
    """RPS-3: die geordnete default-Liste neu setzen (Reihenfolge ändern
    oder Bulk-Replace). Idempotent: die übergebene Liste IST die neue
    Liste (ROUTINE-14).
    """
    if items is None or not isinstance(items, list):
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "keine items-Liste"}
    if not items:
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "leere items-Liste"}

    try:
        response = routine_client.replace_default_items(list(items))
    except RoutineClientError as e:
        return _routine_fehler("PUT", e)

    count = response.get("count", 0)
    logger.info("routine_punkte_setzen: neugeordnet count=%d "
                "(ROUTINE-14, #354)", count)
    return SIGNAL_NEUGEORDNET, {"count": count}


# ============================================================
#  Helpers
# ============================================================

def _routine_fehler(method, exc):
    """RPS-5/EC-7: übersetzt einen RoutineClientError in (signal, daten).

    4xx (Buddy-Validierung — >8 Punkte, leeres Label, ID nicht gefunden …)
    → SIGNAL_GRENZE: ehrliche fachliche Grenze, kein Re-Try.
    Sonst (5xx, Connection-refused, Timeout) → SIGNAL_NICHT_ERREICHBAR:
    Buddy nicht erreichbar (EC-7).
    """
    fehler_str = str(exc)
    if "HTTP 4" in fehler_str:
        logger.info("routine_punkte_setzen: Buddy hat %s abgelehnt — %s",
                    method, exc)
        return SIGNAL_GRENZE, {"detail": fehler_str}
    logger.warning("routine_punkte_setzen: Routine-Buddy nicht erreichbar — %s",
                   exc)
    return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}
