"""Plan-Aktivitäten setzen — specs/platform/plan-aktivitaeten-setzen.md
(PAS-1 … PAS-8, E-PAS-1 … E-PAS-4).

Aufrufbare, trigger-agnostische Funktion (PAS-1, E-RZS-1-Muster):
nimmt {Operation, Aktivitäts-Daten} und ruft die Plan-Admin-API
(PLAN-34) sowie die ICONS-7-Stichwort-Suche (PAS-4). Die Funktion ist
eine bewusste Copy des RPS-Musters (RAT-6/RAT-12 — keine gemeinsame
Schreib-Skill-Abstraktion, bis sie nach dem 2.–3. *gebauten* Skill
ehrlich entsteht; PAS ist der dritte Schreib-Skill auf einer Buddy-
Katalog-Liste).

Operationen (PAS-3, V1):
  - dauerhaft hinzufügen → POST /api/v1/plan/admin/aktivitaeten
                             {art, label, keywords[], piktogramm}
  - dauerhaft löschen    → DELETE /api/v1/plan/admin/aktivitaeten/<art>
  - Lesen des Bestands   → GET /api/v1/plan/aktivitaeten (PAS-5, lesend)
  - Icon-Suche           → ICONS-7 GET /api/v1/icons/suche?q=<wort>&max=3

**Umbenennen / Reihenfolge ändern sind NICHT Teil von V1** (E-PAS-1,
Nic-Entscheid Werft 2026-06-09). Der Skill bietet diese Verben gar nicht
erst an.

Pattern (E-PAS-1): **propose→confirm**, NICHT Sofort-Wirkung wie FSE. Eine
Änderung am dauerhaften Aktivitäts-Katalog prägt das tägliche Plan-Display —
die Vorab-Bestätigung (EC-10) ist die richtige Reibung.

**PAS-7 / APP-3: KEIN direkter Dateizugriff auf plan.json.** Schreiben
ausschließlich über PlanClient (Admin-Methoden) → PLAN-34.

Eingang: Operation + Aktivitäts-Daten (art/label/keywords/piktogramm /
art_loeschen / icon_stichwort je nach Aktion), ein PlanClient (Admin-Methoden)
(PAS-7, PLAN-34-Naht), ein IconClient (PAS-4, ICONS-7-Naht),
`is_member_fn` (PAS-2), `from_user_id` (PAS-2).

Ausgang: Ergebnis-Tuple `(signal, daten)`:
  („hinzugefuegt",   {"art": <str>})             — POST erfolgreich.
  („geloescht",      {"art": <str>})             — DELETE erfolgreich.
  („icon_kandidaten",{"label": <str>,             — ICONS-7 lieferte
                      "kandidaten": [...]}})        Treffer; Skill legt
                                                   sie zur Wahl vor (PAS-4).
  („keine_icons",    {"label": <str>})           — ICONS-7 ohne Treffer (PAS-4).
  („aktivitaeten",   {"liste": [...]})           — GET-Bestand (PAS-5).
  („abgelehnt",      {})                         — Nicht-Mitglied (PAS-2).
  („grenze",         {"detail": <str>})          — Buddy-4xx (doppelte art
                                                   → 409, nicht gefunden
                                                   → 404, …), EC-7.
  („nicht_erreichbar",{"detail": <str>})        — Buddy nicht erreichbar.
  („nichts_zu_tun",  {"reason": <str>})         — Eingabe unvollständig.
"""

import logging

from skills.icon_client import IconClientError
from skills.plan_client import PlanClientError

logger = logging.getLogger(__name__)


# PAS-1: Ergebnis-Signale der Funktion.
SIGNAL_HINZUGEFUEGT      = "hinzugefuegt"
SIGNAL_GELOESCHT         = "geloescht"
SIGNAL_ICON_KANDIDATEN   = "icon_kandidaten"
SIGNAL_KEINE_ICONS       = "keine_icons"
SIGNAL_AKTIVITAETEN      = "aktivitaeten"
SIGNAL_ABGELEHNT         = "abgelehnt"
SIGNAL_GRENZE            = "grenze"
SIGNAL_NICHT_ERREICHBAR  = "nicht_erreichbar"
SIGNAL_NICHTS_ZU_TUN     = "nichts_zu_tun"

# PAS-3: Operationen — V1, KEIN Umbenennen / Reihenfolge (E-PAS-1).
AKTION_HINZUFUEGEN   = "hinzufuegen"
AKTION_LOESCHEN      = "loeschen"
AKTION_ICON_SUCHEN   = "icon_suchen"     # PAS-4: ICONS-7-Suche ohne Schreiben
AKTION_LISTE_LESEN   = "liste_lesen"     # PAS-5: Bestand lesen (lesend)

# PAS-5: Seed-Liste typischer Familien-Aktivitäten (E-PAS-3: lebt im Skill,
# nicht im Plan-Code-Default). Spalten: (art, label, keywords[], icon_suchworte[]).
# icon_suchworte: Reihenfolge für ICONS-7 — Skill probiert Wort für Wort (PAS-5
# Synonym-Spalte V1.2).
SEED = [
    ("capueira", "Capueira",
     ["capueira", "capoeira"],
     ["capueira", "capoeira", "tanz", "tanzen"]),
    ("klettern", "Klettern",
     ["klettern", "kletter"],
     ["klettern"]),
    ("fahrrad",  "Fahrradfahren",
     ["fahrrad", "rad"],
     ["fahrrad", "rad"]),
    ("freunde",  "Freunde treffen",
     ["freunde", "spielen mit"],
     ["freunde", "treffen"]),
    ("schwimmen", "Schwimmen",
     ["schwimm"],
     ["schwimmen"]),
    ("ausflug",  "Ausflug",
     ["ausflug"],
     ["ausflug"]),
]


def plan_aktivitaeten_setzen(*, aktion, plan_client, icon_client,
                              is_member_fn, from_user_id,
                              art=None, label=None, keywords=None,
                              piktogramm=None, art_loeschen=None,
                              icon_stichwort=None, icon_max=3):
    """Plan-Aktivitäten setzen — aufrufbare Funktion (PAS-1).

    Eine **schreibende** Aufgabe (EC-10, PAS-6) mit **propose→confirm**
    (E-PAS-1): die Funktion schreibt direkt im execute()-Pfad — die
    Vorab-Bestätigung sitzt eine Ebene höher (PlanAktivitaetenSetzenTask.propose).

    `aktion`       — Eine der AKTION_*-Konstanten (PAS-3).
    `plan_client`  — PlanClient (Admin-Methoden)-Instanz mit aktivitaet_hinzufuegen/
                     loeschen/lesen-Methoden (PAS-7, PLAN-34-Naht).
    `icon_client`  — IconClient-Instanz für ICONS-7 (PAS-4).
    `is_member_fn` — Callable `(user_id) -> bool` (PAS-2).
    `from_user_id` — Telegram-User-ID des Aufrufers (PAS-2).

    Parameter je Aktion:
      hinzufuegen — `art`, `label`, `keywords` (Liste), `piktogramm` (ARASAAC-ID).
      loeschen    — `art_loeschen`.
      icon_suchen — `icon_stichwort`, optional `icon_max` (≤3).
      liste_lesen — (keine Zusatz-Parameter).

    Ergebnis: (signal, daten) — siehe Modul-Docstring.
    """
    # PAS-2: Berechtigung — live geprüft, identisch zum RPS-/GAN-Muster.
    # Die Prüfung liegt **bei der Funktion** (E-RZS-1), nicht beim Trigger.
    if from_user_id is None or not is_member_fn(from_user_id):
        logger.info("plan_aktivitaeten_setzen: User %s nicht in Familien-Gruppe "
                    "— abgelehnt (PAS-2)", from_user_id)
        return SIGNAL_ABGELEHNT, {}

    if aktion == AKTION_ICON_SUCHEN:
        return _icon_suchen(icon_client, icon_stichwort, icon_max)

    if aktion == AKTION_LISTE_LESEN:
        return _liste_lesen(plan_client)

    if aktion == AKTION_HINZUFUEGEN:
        return _hinzufuegen(plan_client, art, label, keywords, piktogramm)

    if aktion == AKTION_LOESCHEN:
        return _loeschen(plan_client, art_loeschen)

    logger.warning("plan_aktivitaeten_setzen: unbekannte Aktion %r — nichts zu tun",
                   aktion)
    return SIGNAL_NICHTS_ZU_TUN, {"reason": "unbekannte Aktion"}


# ============================================================
#  PAS-4 — ICONS-7-Stichwort-Suche (kein Schreiben)
# ============================================================

def _icon_suchen(icon_client, stichwort, max_treffer):
    """PAS-4: ICONS-7-Suche mit bis zu drei Kandidaten (Spec Z. 87-91).

    Liefert SIGNAL_ICON_KANDIDATEN mit der Liste der Treffer, oder
    SIGNAL_KEINE_ICONS, wenn der Router nichts findet. Erfindet **keine**
    ID, fällt **nicht** auf ARASAAC zurück (E-PAS-2, PAS-4 letzter Absatz).
    """
    if not stichwort or not str(stichwort).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Stichwort"}

    # Spec verlangt „bis zu drei Kandidaten" — Hard-Cap auf 3 (PAS-4 Z. 87).
    cap = min(int(max_treffer or 3), 3)

    try:
        kandidaten = icon_client.suche(stichwort, max_treffer=cap)
    except IconClientError as e:
        logger.warning("plan_aktivitaeten_setzen: ICONS-7 nicht erreichbar — %s", e)
        return SIGNAL_NICHT_ERREICHBAR, {"detail": str(e)}

    if not kandidaten:
        # PAS-4: ICONS-7 ohne Treffer → ehrlich melden, kein erfundenes
        # Piktogramm (E-PAS-2: kein eigener ARASAAC-Bezug).
        logger.info("plan_aktivitaeten_setzen: ICONS-7 keine Treffer für %r",
                    stichwort)
        return SIGNAL_KEINE_ICONS, {"label": stichwort}

    return SIGNAL_ICON_KANDIDATEN, {"label": stichwort,
                                    "kandidaten": list(kandidaten)}


# ============================================================
#  PAS-5 — Bestand lesen (GET PLAN-34, lesend)
# ============================================================

def _liste_lesen(plan_client):
    """PAS-5: aktuellen Aktivitäts-Katalog lesen (GET /api/v1/plan/aktivitaeten).

    Liefert SIGNAL_AKTIVITAETEN mit der aktuellen Liste — für Vorschlag-
    Aufbereitung (PAS-5) und Lösch-Dialog (PAS-3). Reload-on-Read (DCOMP-2).
    """
    try:
        liste = plan_client.aktivitaeten_lesen()
    except PlanClientError as e:
        return _plan_fehler("GET", e)
    return SIGNAL_AKTIVITAETEN, {"liste": liste}


# ============================================================
#  PAS-3 — POST /api/v1/plan/admin/aktivitaeten
# ============================================================

def _hinzufuegen(plan_client, art, label, keywords, piktogramm):
    """PAS-3: eine neue Aktivität anlegen.

    Alle vier Felder sind Pflicht (PLAN-34-Vertrag). art muss neu sein
    (doppelte art → 409); der Skill quittiert das als ehrliche Grenze (PAS-3,
    EC-7). Fachliche Validierung liegt im Plan-Buddy (PLAN-34, BUD-2).
    """
    if not art or not str(art).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein art-Schlüssel"}
    if not label or not str(label).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Label"}
    if not keywords or not isinstance(keywords, list) or not keywords:
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "keine Keywords"}
    if not piktogramm or not str(piktogramm).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein Piktogramm"}

    try:
        response = plan_client.aktivitaet_hinzufuegen(
            art=str(art).strip(),
            label=str(label).strip(),
            keywords=[str(k).strip() for k in keywords if str(k).strip()],
            piktogramm=str(piktogramm).strip(),
        )
    except PlanClientError as e:
        return _plan_fehler("POST", e)

    new_art = response.get("art")
    logger.info("plan_aktivitaeten_setzen: hinzugefügt art=%s (PLAN-34, #578)",
                new_art)
    return SIGNAL_HINZUGEFUEGT, {"art": new_art}


# ============================================================
#  PAS-3 — DELETE /api/v1/plan/admin/aktivitaeten/<art>
# ============================================================

def _loeschen(plan_client, art):
    """PAS-3: eine Aktivität entfernen (DELETE PLAN-34).

    `art` ist der stabile Schlüssel der Aktivität (PLAN-12). Die Familie
    sieht nie art-Schlüssel direkt — der Skill löst Label → art intern auf
    (PAS-3, PAS-6). Hier ist art bereits aufgelöst (vom Task übergeben).

    DELETE auf unbekannte art → 404 → SIGNAL_GRENZE (ehrliche Grenze, EC-7).
    """
    if not art or not str(art).strip():
        return SIGNAL_NICHTS_ZU_TUN, {"reason": "kein art-Schlüssel"}

    try:
        plan_client.aktivitaet_loeschen(str(art).strip())
    except PlanClientError as e:
        return _plan_fehler("DELETE", e)

    logger.info("plan_aktivitaeten_setzen: gelöscht art=%s (PLAN-34, #578)", art)
    return SIGNAL_GELOESCHT, {"art": art}


# ============================================================
#  Helpers
# ============================================================

def _plan_fehler(method, exc):
    """PAS-6/EC-7: übersetzt einen PlanClientError in (signal, daten).

    4xx (Buddy-Validierung — doppelte art → 409, leeres Feld → 400,
    nicht gefunden → 404, nicht-Loopback → 403)
    → SIGNAL_GRENZE: ehrliche fachliche Grenze, kein Re-Try.
    Sonst (5xx, Connection-refused, Timeout) → SIGNAL_NICHT_ERREICHBAR.
    """
    fehler_str = str(exc)
    if "HTTP 4" in fehler_str:
        logger.info("plan_aktivitaeten_setzen: Plan-Buddy hat %s abgelehnt — %s",
                    method, exc)
        return SIGNAL_GRENZE, {"detail": fehler_str}
    logger.warning("plan_aktivitaeten_setzen: Plan-Buddy nicht erreichbar — %s",
                   exc)
    return SIGNAL_NICHT_ERREICHBAR, {"detail": fehler_str}
