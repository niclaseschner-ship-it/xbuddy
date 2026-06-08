"""Tests für routine/uhr.py — Fokus ROUTINE-9 AC-FIX4 (#364).

AC-FIX4: Fehlender Tag in aufstehzeit-Map → Default 07:00.
Ist aufstehzeit als Wochentag→Zeit-Map gegeben (ROUTINE-12) und der heutige
Tag fehlt (z. B. leeres Wochenende), fällt aufstehen auf "07:00" zurück —
nie None; die View rendert wie ein normaler Wochentag, kein TypeError.
"""

import os
import sys
from datetime import date, datetime

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from zoneinfo import ZoneInfo  # noqa: E402

from routine import uhr as uhr_mod  # noqa: E402  # isort:skip


ZEITZONE = "Europe/Berlin"
TZ = ZoneInfo(ZEITZONE)

# Samstag 2026-06-06 und Sonntag 2026-06-07 — fehlen in einer Mo-Fr-Map
SAMSTAG = date(2026, 6, 6)
SONNTAG = date(2026, 6, 7)
MONTAG = date(2026, 6, 8)

# Mo-Fr-Map — Sa+So fehlen absichtlich
AUFSTEHZEIT_MO_FR = {
    "Mo": "06:30",
    "Di": "06:30",
    "Mi": "06:30",
    "Do": "06:30",
    "Fr": "06:30",
}

# Fixwert-abfahrtszeit (gilt jeden Tag → losgehen wird immer gesetzt)
ABFAHRTSZEIT_FIX = "07:45"
ANZIEH_VORLAUF = 8


# ---- AC-FIX4: Fallback auf 07:00 wenn Tag fehlt ----------------------------------------

class TestAufstehzeitMapFallback:
    """ROUTINE-9 AC-FIX4: aufstehzeit-Map ohne heutigen Wochentag → Default 07:00."""

    def test_samstag_kein_eintrag_fallback_07_00(self):
        """Sa fehlt in Mo-Fr-Map + Fixwert-abfahrtszeit → aufstehen=07:00, kein TypeError."""
        zeiten = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SAMSTAG, aufstehzeit_cfg=AUFSTEHZEIT_MO_FR,
        )
        assert zeiten is not None, "Uhr sollte trotz fehlendem Sa-Eintrag Zeiten liefern"
        assert zeiten.aufstehen is not None, "aufstehen darf bei fehlendem Wochentag nicht None sein"
        assert zeiten.aufstehen.hour == 7
        assert zeiten.aufstehen.minute == 0

    def test_sonntag_kein_eintrag_fallback_07_00(self):
        """So fehlt in Mo-Fr-Map + Fixwert-abfahrtszeit → aufstehen=07:00."""
        zeiten = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SONNTAG, aufstehzeit_cfg=AUFSTEHZEIT_MO_FR,
        )
        assert zeiten is not None
        assert zeiten.aufstehen is not None
        assert zeiten.aufstehen.hour == 7
        assert zeiten.aufstehen.minute == 0

    def test_samstag_baue_uhr_view_kein_typeerror(self):
        """baue_uhr_view darf bei Fallback-aufstehen keinen TypeError werfen (#364)."""
        zeiten = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SAMSTAG, aufstehzeit_cfg=AUFSTEHZEIT_MO_FR,
        )
        assert zeiten is not None
        # now vor anziehen — Phase vor_anziehen
        now = datetime(SAMSTAG.year, SAMSTAG.month, SAMSTAG.day, 7, 10, tzinfo=TZ)
        view = uhr_mod.baue_uhr_view(zeiten, now)
        assert view is not None
        assert view.aufstehen_label == "07:00"
        assert view.phase == uhr_mod.PHASE_VOR_ANZIEHEN

    def test_sonntag_baue_uhr_view_alle_phasen(self):
        """Alle drei Phasen funktionieren an einem Sonntag mit Fallback-aufstehen."""
        zeiten = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SONNTAG, aufstehzeit_cfg=AUFSTEHZEIT_MO_FR,
        )
        assert zeiten is not None

        # Phase vor_anziehen
        now_vor = datetime(SONNTAG.year, SONNTAG.month, SONNTAG.day, 7, 10, tzinfo=TZ)
        view_vor = uhr_mod.baue_uhr_view(zeiten, now_vor)
        assert view_vor.phase == uhr_mod.PHASE_VOR_ANZIEHEN
        assert view_vor.rest_bis_anziehen_min is not None

        # Phase anziehen_phase
        now_an = datetime(SONNTAG.year, SONNTAG.month, SONNTAG.day, 7, 40, tzinfo=TZ)
        view_an = uhr_mod.baue_uhr_view(zeiten, now_an)
        assert view_an.phase == uhr_mod.PHASE_ANZIEHEN
        assert view_an.rest_bis_losgehen_min is not None

        # Phase nach_losgehen
        now_nach = datetime(SONNTAG.year, SONNTAG.month, SONNTAG.day, 8, 0, tzinfo=TZ)
        view_nach = uhr_mod.baue_uhr_view(zeiten, now_nach)
        assert view_nach.phase == uhr_mod.PHASE_NACH_LOSGEHEN


# ---- Negativtest: Map MIT dem heutigen Tag → kein Fallback ausgelöst --------------------

class TestAufstehzeitMapKeinFallback:
    """Negativtest: Wenn der Tag in der Map vorhanden ist, gilt der Map-Wert."""

    def test_montag_map_eintrag_wird_genutzt(self):
        """Mo ist in der Map → aufstehen=06:30, NICHT 07:00."""
        zeiten = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=MONTAG, aufstehzeit_cfg=AUFSTEHZEIT_MO_FR,
        )
        assert zeiten is not None
        assert zeiten.aufstehen is not None
        assert zeiten.aufstehen.hour == 6
        assert zeiten.aufstehen.minute == 30

    def test_vollstaendige_map_kein_fallback(self):
        """7-Tage-Map → kein Fallback ausgelöst, alle Tage liefern ihren Map-Wert."""
        volle_map = {
            "Mo": "06:00", "Di": "06:00", "Mi": "06:00",
            "Do": "06:00", "Fr": "06:00", "Sa": "08:00", "So": "09:00",
        }
        # Samstag → 08:00
        zeiten_sa = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SAMSTAG, aufstehzeit_cfg=volle_map,
        )
        assert zeiten_sa is not None
        assert zeiten_sa.aufstehen.hour == 8
        assert zeiten_sa.aufstehen.minute == 0

        # Sonntag → 09:00
        zeiten_so = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SONNTAG, aufstehzeit_cfg=volle_map,
        )
        assert zeiten_so is not None
        assert zeiten_so.aufstehen.hour == 9
        assert zeiten_so.aufstehen.minute == 0


# ---- Fixwert-aufstehzeit: unverändert (AC1, kein Fallback wenn String) -----------------

class TestAufstehzeitString:
    """aufstehzeit als String → wird direkt geparst, kein Fallback-Pfad."""

    def test_fixwert_string_samstag(self):
        """aufstehzeit='08:00' (String) an einem Samstag → 08:00, kein Fallback."""
        zeiten = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SAMSTAG, aufstehzeit_cfg="08:00",
        )
        assert zeiten is not None
        assert zeiten.aufstehen.hour == 8
        assert zeiten.aufstehen.minute == 0

    def test_default_parameter_07_00(self):
        """Default-Parameter aufstehzeit_cfg='07:00' liefert 07:00."""
        zeiten = uhr_mod.berechne_zeiten(
            ABFAHRTSZEIT_FIX, ANZIEH_VORLAUF, ZEITZONE,
            tag=SAMSTAG,
        )
        assert zeiten is not None
        assert zeiten.aufstehen.hour == 7
        assert zeiten.aufstehen.minute == 0


# ---- AC3: abfahrtszeit-'kein Kindi'-Semantik unberührt ----------------------------------

class TestAbfahrtszeitKeinKindi:
    """ROUTINE-9 AC-FIX4 explizit: abfahrtszeit-Map-Semantik bleibt unberührt."""

    def test_abfahrtszeit_map_ohne_samstag_ergibt_none(self):
        """abfahrtszeit-Map ohne Sa → kein Schultag → berechne_zeiten gibt None zurück."""
        abfahrt_mo_fr = {
            "Mo": "07:45", "Di": "07:45", "Mi": "07:45",
            "Do": "07:45", "Fr": "07:45",
        }
        zeiten = uhr_mod.berechne_zeiten(
            abfahrt_mo_fr, ANZIEH_VORLAUF, ZEITZONE,
            tag=SAMSTAG, aufstehzeit_cfg="07:00",
        )
        assert zeiten is None, (
            "abfahrtszeit-Map ohne Sa muss None liefern ('kein Kindi'-Semantik unverändert)"
        )
