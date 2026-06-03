"""Wetter-Buddy — Garderoben-Regeln-Auswertung (WETTER-14, WETTER-15).

Siehe specs/buddies/wetter.md §4. Das Outfit je Tageszeit wird aus den
**Garderoben-Regeln** der Familie abgeleitet (Config, WETTER-21, E-WETTER-5) —
kein Code, kein hartcodiertes Familien-Wissen. Eine Regel bildet eine
**Wetterbedingung** (gefühlte-Temp-Band, Regen, Wind, Sonne) auf ein
**Kleidungs-Set** ab (Teile pflicht/optional + Hinweis).

Die Regeln sind geordnet; die **erste passende** gewinnt (WETTER-14). Trifft
keine zu, kommt das **Fallback-Set** zurück (nie leer, nie ein Fehler vor dem
Kind, WETTER-14).

Mützen- und Regen-/Matsch-Logik (WETTER-15) sind keine Sonder-Codepfade,
sondern gewöhnliche Regeln in der Config: eine warme Regel listet die
Sonnenmütze, eine kalte die Wintermütze; eine Regen-Regel matcht über
`rain_prob`/`rain_amount` und listet Regenjacke/Matschhose/Gummistiefel. Diese
Datei wertet die Bedingungen nur aus — welche Teile in welcher Bedingung
stehen, ist Familien-Daten.
"""

import logging

logger = logging.getLogger(__name__)


class Kleidungsstueck:
    """Ein Kleidungsstück eines Outfit-Sets (WETTER-13).

    `pikto` ist die numerische ARASAAC-ID (WETTER-18) — die Render-Schicht
    baut daraus die geteilte Icon-URL (ICONS-5). `name` ist das Label unter
    dem Piktogramm.
    """

    __slots__ = ("name", "pikto")

    def __init__(self, name, pikto):
        self.name = name
        self.pikto = pikto

    def to_dict(self):
        return {"name": self.name, "pikto": self.pikto}


class Outfit:
    """Das Ergebnis einer Regel-Auswertung für eine Tageszeit (WETTER-13).

    `pflicht`/`optional` sind Listen von `Kleidungsstueck` (MIT / WENN DU
    MAGST). `hinweis` ist der kurze Hinweistext.
    """

    __slots__ = ("pflicht", "optional", "hinweis")

    def __init__(self, pflicht, optional, hinweis):
        self.pflicht = pflicht
        self.optional = optional
        self.hinweis = hinweis

    def to_dict(self):
        return {
            "pflicht": [k.to_dict() for k in self.pflicht],
            "optional": [k.to_dict() for k in self.optional],
            "hinweis": self.hinweis,
        }


class Regel:
    """Eine Garderoben-Regel: Bedingung → Kleidungs-Set (WETTER-14).

    Die Bedingung ist eine Menge optionaler Schwellen. Eine Regel matcht,
    wenn ALLE gesetzten Schwellen erfüllt sind (UND-Verknüpfung):

      feels_min / feels_max   gefühlte-Temp-Band [feels_min, feels_max) (WETTER-8/14)
      rain_prob_min           rainProb >= Schwelle (WETTER-15)
      rain_amount_min         rainAmount >= Schwelle (WETTER-15)
      wind_min                wind >= Schwelle (WETTER-14)
      sunscreen               sunscreen-Boolean muss diesem Wert entsprechen

    Eine Schwelle, die `None` ist, wird nicht geprüft. Fehlt ein Wetterwert
    (None aus dem neutralen Zustand, WETTER-17), gilt eine Schwelle, die ihn
    bräuchte, als NICHT erfüllt — eine Regel mit `rain_prob_min` matcht ohne
    Regen-Wahrscheinlichkeit nicht.
    """

    __slots__ = ("feels_min", "feels_max", "rain_prob_min", "rain_amount_min",
                 "wind_min", "sunscreen", "pflicht", "optional", "hinweis")

    def __init__(self, feels_min=None, feels_max=None, rain_prob_min=None,
                 rain_amount_min=None, wind_min=None, sunscreen=None,
                 pflicht=None, optional=None, hinweis=""):
        self.feels_min = feels_min
        self.feels_max = feels_max
        self.rain_prob_min = rain_prob_min
        self.rain_amount_min = rain_amount_min
        self.wind_min = wind_min
        self.sunscreen = sunscreen
        self.pflicht = pflicht or []
        self.optional = optional or []
        self.hinweis = hinweis

    def matcht(self, wetter):
        """True, wenn alle gesetzten Schwellen vom `wetter` (Tageswetter) erfüllt sind."""
        feels = wetter.feelsLike
        if self.feels_min is not None:
            if feels is None or feels < self.feels_min:
                return False
        if self.feels_max is not None:
            if feels is None or feels >= self.feels_max:
                return False
        if self.rain_prob_min is not None:
            if wetter.rainProb is None or wetter.rainProb < self.rain_prob_min:
                return False
        if self.rain_amount_min is not None:
            if wetter.rainAmount is None or wetter.rainAmount < self.rain_amount_min:
                return False
        if self.wind_min is not None:
            if wetter.wind is None or wetter.wind < self.wind_min:
                return False
        if self.sunscreen is not None:
            if bool(wetter.sunscreen) != bool(self.sunscreen):
                return False
        return True

    def outfit(self):
        return Outfit(list(self.pflicht), list(self.optional), self.hinweis)


class Garderobe:
    """Die geordnete Garderoben-Regel-Liste einer Familie + Fallback (WETTER-14).

    `regeln` ist die geordnete Liste; die erste passende gewinnt. `fallback`
    ist das Outfit, das gilt, wenn keine Regel matcht (nie leer, WETTER-14).
    """

    def __init__(self, regeln, fallback):
        self._regeln = list(regeln)
        self._fallback = fallback

    def outfit_fuer(self, wetter):
        """Das Outfit für ein `Tageswetter` (WETTER-14).

        Die erste passende Regel gewinnt; trifft keine zu, kommt das
        Fallback-Set (WETTER-14). Liefert nie None.
        """
        for regel in self._regeln:
            if regel.matcht(wetter):
                return regel.outfit()
        # Fallback ist bereits ein Outfit — eine frische Kopie zurückgeben,
        # damit der Aufrufer das geteilte Fallback-Objekt nie mutiert.
        return Outfit(list(self._fallback.pflicht),
                      list(self._fallback.optional),
                      self._fallback.hinweis)
