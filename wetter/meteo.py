"""Wetter-Buddy — Wetter-Anbindung (WETTER-16, WETTER-17).

Siehe specs/buddies/wetter.md §5. Die Anbindung ist eine Funktion **dieser
App** (E-WETTER-1) — keine Plattform-Fähigkeit, keine API für andere Apps
(E-WETTER-3). Sie liest für den konfigurierten Ort das Wetter je Tageszeit
(Morgens, Mittags) und übersetzt die Anbieter-Antwort in ein
**anbieter-neutrales Modell** (WETTER-16).

Aufbau — Test-Naht (WETTER-24, analog plan/kalender.py PLAN-29):

  OpenMeteoTransport   spricht HTTP mit Open-Meteo (kein API-Key). Das ist die
                       EINZIGE Stelle mit Netz-Zugriff.
  WetterAnbindung      die App-Funktion: nimmt einen `transport`, normalisiert
                       die Rohantwort je Tageszeit (WETTER-16) und leitet den
                       Sonnencreme-Boolean ab (WETTER-11).

Für Tests wird `OpenMeteoTransport` durch ein Fake ersetzt, das kontrollierte
Rohantworten liefert (WETTER-24) — kein Netz nötig. Die Normalisierung und die
Sonnencreme-Ableitung werden so vollständig ohne Open-Meteo geprüft.

Ist der Anbieter nicht erreichbar oder fehlt der Ort, wirft die App keinen
unbehandelten Fehler: sie liefert einen **neutralen Zustand** (WETTER-17) —
der Kiosk bleibt an, kein Fehler vor dem Kind, protokolliert.
"""

import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WETTER-7/WETTER-16: die neutrale Zustands-Kategorie `kind`. Open-Meteo liefert
# einen WMO-`weathercode` (0..99); wir mappen ihn auf eine kleine, stabile Menge
# neutraler Kategorien, die View und Szenen-Lib (WETTER-7) konsumieren. Die
# Kategorien sind anbieter-unabhängig — ein anderer Anbieter füllt dasselbe Set.
KIND_SONNIG = "sonnig"
KIND_BEWOELKT = "bewoelkt"
KIND_REGEN = "regen"
KIND_SCHNEE = "schnee"
KIND_GEWITTER = "gewitter"
KIND_NEUTRAL = "neutral"          # WETTER-17: Ausfall / unbekannt

# Kurztext je Kategorie (WETTER-7 `desc`). Bewusst kindgerecht-knapp.
KIND_DESC = {
    KIND_SONNIG:   "Sonnig",
    KIND_BEWOELKT: "Bewölkt",
    KIND_REGEN:    "Regen",
    KIND_SCHNEE:   "Schnee",
    KIND_GEWITTER: "Gewitter",
    KIND_NEUTRAL:  "Kein Wetter da",
}

# WMO-weathercode → neutrale Kategorie (WETTER-16). Quelle: Open-Meteo-Doku
# (WMO Weather interpretation codes). Gruppen statt Einzelcodes — die View
# braucht die grobe Kategorie, nicht den exakten Code.
def _kind_aus_weathercode(code):
    if code is None:
        return KIND_NEUTRAL
    try:
        code = int(code)
    except (TypeError, ValueError):
        return KIND_NEUTRAL
    if code in (0, 1):
        return KIND_SONNIG
    if code in (2, 3, 45, 48):
        return KIND_BEWOELKT
    if code in (95, 96, 99):
        return KIND_GEWITTER
    if code in (71, 73, 75, 77, 85, 86):
        return KIND_SCHNEE
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return KIND_REGEN
    return KIND_BEWOELKT


# WETTER-11: UV-Label-Stufen (für die Ableitung; dem Kind NICHT gezeigt). Nur
# zur internen Klassifikation — die View bekommt `uvLabel` nie zu sehen.
def _uv_label(uv):
    if uv is None:
        return "unbekannt"
    if uv < 3:
        return "niedrig"
    if uv < 6:
        return "mittel"
    if uv < 8:
        return "hoch"
    return "sehr hoch"


class Tageswetter:
    """Anbieter-neutrales Wetter einer Tageszeit (WETTER-16).

    Felder (WETTER-16): `desc`, `kind` (neutrale Zustands-Kategorie für
    WETTER-7), `temp`, `feelsLike`, `feelsLike_max`, `low`, `high`, `wind`,
    `rainProb`, `rainAmount`, `uv`, `uvLabel`, `sunscreen` (abgeleiteter
    Boolean, WETTER-11).

    `low`/`high` sind die Tages-Spanne (gilt für beide Tageszeiten gleich —
    WETTER-9 zeigt eine Tagesspanne). `sunscreen` ist Backend-entschieden;
    `uv`/`uvLabel` tragen wir mit, damit die Ableitung nachvollziehbar bleibt,
    aber die View zeigt sie nie (E-WETTER-2).

    `feelsLike_max` (WETTER-16 Pack-/Trage-Sicht): im Morgens-Tageswetter ist
    dies das Tages-Maximum der gefühlten Temperatur; im Mittags-Tageswetter
    ist es gleich `feelsLike` (Slot-Wert). Die Regel-Auswertung in
    clothing.py prüft `feels_min` gegen `feelsLike` und `feels_max` gegen
    `feelsLike_max` (WETTER-16).
    """

    __slots__ = (
        "desc",
        "feelsLike",
        "feelsLike_max",
        "high",
        "kind",
        "low",
        "rainAmount",
        "rainProb",
        "sunscreen",
        "temp",
        "uv",
        "uvLabel",
        "wind",
    )

    def __init__(self, desc, kind, temp, feelsLike, low, high, wind,
                 rainProb, rainAmount, uv, uvLabel, sunscreen,
                 feelsLike_max=None):
        self.desc = desc
        self.kind = kind
        self.temp = temp
        self.feelsLike = feelsLike
        # WETTER-16: feelsLike_max = Tages-Max im Morgens-Wetter;
        # im Mittags-Wetter fällt es auf feelsLike (Slot-Wert) zurück.
        self.feelsLike_max = feelsLike_max if feelsLike_max is not None else feelsLike
        self.low = low
        self.high = high
        self.wind = wind
        self.rainProb = rainProb
        self.rainAmount = rainAmount
        self.uv = uv
        self.uvLabel = uvLabel
        self.sunscreen = sunscreen

    def to_dict(self):
        """Serialisierbare Form für die Render-Schicht.

        Achtung: `uv`/`uvLabel` sind enthalten, weil das Modell sie trägt
        (WETTER-16) — die View (render.py) zieht sie NICHT in die Ausgabe
        (WETTER-11, E-WETTER-2). Der Test WETTER-11 prüft die Ausgabe, nicht
        dieses Dict.
        """
        return {
            "desc": self.desc,
            "kind": self.kind,
            "temp": self.temp,
            "feelsLike": self.feelsLike,
            "feelsLike_max": self.feelsLike_max,
            "low": self.low,
            "high": self.high,
            "wind": self.wind,
            "rainProb": self.rainProb,
            "rainAmount": self.rainAmount,
            "uv": self.uv,
            "uvLabel": self.uvLabel,
            "sunscreen": self.sunscreen,
        }


def neutrales_tageswetter():
    """Ein neutraler Tageszeit-Zustand (WETTER-17).

    Kein Fehler, kein leerer Bildschirm: `kind=neutral`, alle Zahlenwerte
    `None`, `sunscreen=False`. Die Render-Schicht zeigt daraus einen ruhigen
    Platzhalter (WETTER-17).
    """
    return Tageswetter(
        desc=KIND_DESC[KIND_NEUTRAL], kind=KIND_NEUTRAL,
        temp=None, feelsLike=None, low=None, high=None, wind=None,
        rainProb=None, rainAmount=None, uv=None, uvLabel=_uv_label(None),
        sunscreen=False)


class WetterUnavailable(Exception):
    """Der Anbieter ist nicht erreichbar oder die Antwort ist unbrauchbar.

    Wird vom Transport geworfen; `WetterAnbindung.heute()` fängt es ab und
    liefert einen neutralen Zustand (WETTER-17).
    """


# ============================================================
#  Transport — die Netz-Naht (WETTER-24)
# ============================================================

class OpenMeteoTransport:
    """Spricht HTTP mit Open-Meteo (WETTER-16). Kein API-Key (Spec §5).

    Dies ist die einzige Klasse mit Netz-Zugriff. In Tests wird sie durch ein
    Fake ersetzt (WETTER-24). `lat`/`lon` sind die Koordinaten des
    konfigurierten Orts (WETTER-21).
    """

    def __init__(self, lat, lon, timeout=12):
        self._lat = lat
        self._lon = lon
        self._timeout = timeout

    def fetch(self, tag):
        """Roh-Antwort von Open-Meteo für den Kalendertag `tag` (date).

        Fragt die stündlichen Felder ab, die das neutrale Modell braucht
        (WETTER-16), plus die Tages-Spanne (low/high) und Sonnenschutz-UV.
        Wirft WetterUnavailable bei jedem Netz-/Parse-Fehler (WETTER-17).
        """
        query = {
            "latitude": self._lat,
            "longitude": self._lon,
            "hourly": ("temperature_2m,apparent_temperature,"
                       "precipitation_probability,precipitation,"
                       "weathercode,windspeed_10m,uv_index"),
            "daily": "temperature_2m_min,temperature_2m_max",
            "timezone": "auto",
            "start_date": tag.isoformat(),
            "end_date": tag.isoformat(),
        }
        url = _OPEN_METEO_URL + "?" + urllib.parse.urlencode(query)
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
            return json.loads(raw)
        except Exception as e:  # jeder Netzfehler → WETTER-17
            raise WetterUnavailable(
                "Open-Meteo-Abruf fehlgeschlagen: %s" % e) from e


# ============================================================
#  WetterAnbindung — die App-Funktion (WETTER-16, WETTER-17)
# ============================================================

def _stunde_index(raw_hourly, ziel_stunde, tag):
    """Index der gesuchten Stunde in der `hourly.time`-Liste (WETTER-5).

    Open-Meteo liefert `time` als ISO-Stundenstempel (`YYYY-MM-DDTHH:MM`).
    Liefert den Index der Stunde `ziel_stunde` am Tag `tag`, oder None.
    """
    times = (raw_hourly or {}).get("time") or []
    ziel = "%sT%02d:00" % (tag.isoformat(), ziel_stunde)
    for i, t in enumerate(times):
        if t == ziel:
            return i
    # Fallback: erste Stunde des Tages, falls die exakte Stunde fehlt.
    prefix = tag.isoformat() + "T"
    for i, t in enumerate(times):
        if t.startswith(prefix):
            return i
    return None


def _at(seq, i):
    """Sicherer Listen-Zugriff: Wert bei Index `i`, sonst None."""
    if seq is None or i is None:
        return None
    if 0 <= i < len(seq):
        return seq[i]
    return None


class WetterAnbindung:
    """Die Wetter-Anbindung des Wetter-Buddys (WETTER-16, WETTER-17).

    Nimmt einen `transport` (OpenMeteoTransport in Produktion, ein Fake in
    Tests — WETTER-24) und die Konfigurations-Werte, die die Normalisierung
    braucht: die Tageszeit-Stunden (WETTER-5) und die Sonnencreme-UV-Schwelle
    (WETTER-11/WETTER-21).
    """

    def __init__(self, transport, stunde_morgens, stunde_mittags, sunscreen_uv):
        self._transport = transport
        self._stunde_morgens = stunde_morgens
        self._stunde_mittags = stunde_mittags
        self._sunscreen_uv = sunscreen_uv

    def fuer_tag(self, tag):
        """Liefert (morgens, mittags) als zwei `Tageswetter` für `tag` (date).

        Morgens verwendet Tages-Worst-Case-Aggregate (WETTER-12/16 Pack-Sicht);
        Mittags den Slot-Wert seiner Tageszeit (Trage-Sicht). Ist der Anbieter
        nicht erreichbar oder die Antwort unbrauchbar, kommen zwei neutrale
        Zustände zurück (WETTER-17) — kein unbehandelter Fehler.
        """
        try:
            raw = self._transport.fetch(tag)
        except WetterUnavailable as e:
            logger.warning(
                "Wetter nicht erreichbar (%s) — neutraler Zustand (WETTER-17)", e)
            return neutrales_tageswetter(), neutrales_tageswetter()

        if not isinstance(raw, dict):
            logger.warning(
                "Wetter-Rohantwort kein Objekt — neutraler Zustand (WETTER-17)")
            return neutrales_tageswetter(), neutrales_tageswetter()

        hourly = raw.get("hourly") or {}
        daily = raw.get("daily") or {}
        low = _at(daily.get("temperature_2m_min"), 0)
        high = _at(daily.get("temperature_2m_max"), 0)

        # WETTER-12/16: Morgens = Pack-Sicht → Tages-Worst-Case-Aggregate;
        # Mittags = Trage-Sicht → Slot-Wert.
        tages_aggregate = self._tages_aggregate(hourly, tag)
        morgens = self._normalise_pack(
            hourly, self._stunde_morgens, tag, low, high, tages_aggregate)
        mittags = self._normalise(hourly, self._stunde_mittags, tag, low, high)
        return morgens, mittags

    def _tages_indizes(self, hourly, tag):
        """Alle Stunden-Indizes des Tages `tag` in der `hourly`-Struktur."""
        times = (hourly or {}).get("time") or []
        prefix = tag.isoformat() + "T"
        return [i for i, t in enumerate(times) if isinstance(t, str) and t.startswith(prefix)]

    def _tages_aggregate(self, hourly, tag):
        """Tages-Worst-Case-Aggregate für die Pack-Sicht (WETTER-16).

        Liefert ein dict mit den ungünstigsten Stunden-Werten über den
        gesamten Tag:
          rain_prob    max Niederschlags-Wahrscheinlichkeit
          rain_amount  max stündliche Niederschlagsmenge
          wind         max Windgeschwindigkeit
          uv           max UV-Index
          feels_min    min gefühlte Temperatur (kältester Moment)
          feels_max    max gefühlte Temperatur (heißester Moment)

        Fehlt ein Wert komplett, bleibt er None.
        """
        idxs = self._tages_indizes(hourly, tag)
        if not idxs:
            return {}

        def _vals(key):
            return [v for i in idxs
                    for v in (_at(hourly.get(key), i),)
                    if v is not None]

        feels_vals = _vals("apparent_temperature")
        temp_vals = _vals("temperature_2m")
        # WETTER-8/E-WETTER-8: feelsLike fällt auf temp zurück, wenn nicht vorhanden.
        if not feels_vals:
            feels_vals = temp_vals

        rain_prob_vals = _vals("precipitation_probability")
        rain_amount_vals = _vals("precipitation")
        wind_vals = _vals("windspeed_10m")
        uv_vals = _vals("uv_index")

        return {
            "feels_min": min(feels_vals) if feels_vals else None,
            "feels_max": max(feels_vals) if feels_vals else None,
            "rain_prob": max(rain_prob_vals) if rain_prob_vals else None,
            "rain_amount": max(rain_amount_vals) if rain_amount_vals else None,
            "wind": max(wind_vals) if wind_vals else None,
            "uv": max(uv_vals) if uv_vals else None,
        }

    def _normalise_pack(self, hourly, ziel_stunde, tag, low, high, aggregate):
        """Morgens-Tageswetter als Pack-Sicht (WETTER-12/16).

        Regen/Wind/UV aus Tages-Worst-Case (aggregate); feelsLike = Tages-Min,
        feelsLike_max = Tages-Max; kind/desc aus dem Slot der Morgens-Stunde
        (für die Szene). Fehlt die Stunde, kommt ein neutraler Zustand.
        """
        i = _stunde_index(hourly, ziel_stunde, tag)
        if i is None:
            return neutrales_tageswetter()

        # kind/desc aus dem Morgens-Slot (für die Wetter-Szene WETTER-7).
        code = _at(hourly.get("weathercode"), i)
        kind = _kind_aus_weathercode(code)

        feels_min = aggregate.get("feels_min")
        feels_max = aggregate.get("feels_max")
        # WETTER-8: fehlt feelsLike, fällt es auf temp des Slots zurück.
        if feels_min is None:
            feels_min = _at(hourly.get("temperature_2m"), i)
        if feels_max is None:
            feels_max = feels_min

        uv = aggregate.get("uv")
        sunscreen = uv is not None and uv >= self._sunscreen_uv

        return Tageswetter(
            desc=KIND_DESC.get(kind, KIND_DESC[KIND_NEUTRAL]),
            kind=kind,
            temp=_at(hourly.get("temperature_2m"), i),
            feelsLike=feels_min,
            feelsLike_max=feels_max,
            low=low,
            high=high,
            wind=aggregate.get("wind"),
            rainProb=aggregate.get("rain_prob"),
            rainAmount=aggregate.get("rain_amount"),
            uv=uv,
            uvLabel=_uv_label(uv),
            sunscreen=sunscreen,
        )

    def _normalise(self, hourly, ziel_stunde, tag, low, high):
        """Mittags-Tageswetter als Trage-Sicht: Slot-Wert (WETTER-12/16).

        Fehlt die Stunde komplett, liefert die Methode einen neutralen Zustand
        (WETTER-17) — eine Tageszeit ohne Daten darf den anderen Block nicht
        kippen. feelsLike_max = feelsLike (Slot-Wert, WETTER-16).
        """
        i = _stunde_index(hourly, ziel_stunde, tag)
        if i is None:
            return neutrales_tageswetter()

        temp = _at(hourly.get("temperature_2m"), i)
        feels = _at(hourly.get("apparent_temperature"), i)
        # WETTER-8/E-WETTER-8: gefühlte Temperatur treibt; fehlt sie, fällt sie
        # auf die Lufttemperatur zurück (besser als kein Wert).
        if feels is None:
            feels = temp
        wind = _at(hourly.get("windspeed_10m"), i)
        rain_prob = _at(hourly.get("precipitation_probability"), i)
        rain_amount = _at(hourly.get("precipitation"), i)
        code = _at(hourly.get("weathercode"), i)
        uv = _at(hourly.get("uv_index"), i)

        kind = _kind_aus_weathercode(code)
        # WETTER-11: Sonnencreme ist ein Backend-entschiedener Boolean aus dem
        # UV-Index gegen die Schwelle. Fehlt UV, gilt "nein" (kein Vorwurf).
        sunscreen = uv is not None and uv >= self._sunscreen_uv

        return Tageswetter(
            desc=KIND_DESC.get(kind, KIND_DESC[KIND_NEUTRAL]),
            kind=kind,
            temp=temp,
            feelsLike=feels,
            feelsLike_max=feels,
            low=low,
            high=high,
            wind=wind,
            rainProb=rain_prob,
            rainAmount=rain_amount,
            uv=uv,
            uvLabel=_uv_label(uv),
            sunscreen=sunscreen,
        )
