"""Tests für »App öffnen« (EC-46, #1964) und den App-Knopf-Baustein.

Nic 26.09.2026: jede App ist im Chat erfragbar, einheitlich. Der Kern-Test
läuft über ALLE Einträge des Ansichts-Verzeichnisses — gebaut aus den
committeten `views.json` mit demselben Code wie der Aggregator
(`seiten.aggregator.manifest_eintraege`), nicht aus dem Live-Inventar.
Eine neue `views.json`-Zeile landet damit automatisch in diesem Test.
"""

import os
from unittest.mock import MagicMock

import pytest
from skills._errors import BerechtigungError
from skills.app_knoepfe import (
    BROWSER_LABEL,
    INSTALLIEREN_LABEL,
    absolute_url,
    app_knoepfe,
    installier_url,
)
from skills.app_oeffnen import MAX_APPS, AppVerzeichnis, app_oeffnen
from skills.app_oeffnen_task import AppOeffnenTask
from skills.seiten_client import SeitenClientError
from tasks import ReadTask, TurnContext, build_catalog, render_form_b

from seiten.aggregator import manifest_eintraege

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
_BASIS = "https://xbuddy.example.com"

#: Das Ansichts-Verzeichnis, wie es der Aggregator aus den views.json baut.
VERZEICHNIS = manifest_eintraege(_REPO_ROOT)
_NACH_KEY = {e["key"]: e for e in VERZEICHNIS}


class _Fest:
    """AppVerzeichnis-Doppelung mit festen Einträgen."""

    def __init__(self, eintraege):
        self._eintraege = list(eintraege)

    def eintraege(self):
        return self._eintraege


def _task(eintraege=VERZEICHNIS, basis=_BASIS, is_member=lambda uid: True):
    return AppOeffnenTask(is_member_fn=is_member, verzeichnis=_Fest(eintraege),
                          basis_url=basis)


def _turn():
    return TurnContext(chat_id=42, from_user_id=7)


# ── Das Verzeichnis ist das, was #1964 abdeckt ──────────────────────────────

def test_verzeichnis_traegt_alle_vierzehn_apps():
    """#1964-Ausgangslage: 14 Apps. Wächst das Verzeichnis, wächst der Test mit."""
    assert len(VERZEICHNIS) >= 14, sorted(_NACH_KEY)


# ── Jede App über den Skill erreichbar (parametrisiert über ALLE Einträge) ──

@pytest.mark.parametrize("key", sorted(_NACH_KEY))
def test_jede_app_steht_mit_label_und_synonymen_in_der_werkzeug_definition(key):
    eintrag = _NACH_KEY[key]
    definition = _task().to_def()
    assert key in definition.parameters["properties"]["apps"]["items"]["enum"]
    zeile = [z for z in definition.description.splitlines()
             if z.startswith("- %s:" % key)]
    assert len(zeile) == 1, "App %s fehlt in der Werkzeug-Beschreibung" % key
    assert eintrag["label"] in zeile[0]
    assert "[%s]" % eintrag["zielgruppe"] in zeile[0]
    for synonym in eintrag["synonyme"]:
        assert synonym in zeile[0]


@pytest.mark.parametrize("key", sorted(_NACH_KEY))
def test_jede_app_liefert_die_einheitliche_knopfreihe(key):
    eintrag = _NACH_KEY[key]
    result = _task().run({"apps": [key]}, _turn())

    url = _BASIS + eintrag["pfad"]
    knoepfe = result["presentation"]["inline_buttons"]
    assert result["text"].startswith("„%s“" % eintrag["label"])
    assert "\n" not in result["text"], "Ein Satz, nicht mehr"
    assert knoepfe[0] == {"label": "📱 %s öffnen" % eintrag["label"],
                          "web_app_url": url}
    assert knoepfe[1] == {"label": BROWSER_LABEL, "url": url}
    if eintrag["pwa"]:
        assert len(knoepfe) == 3
        assert knoepfe[2]["label"] == INSTALLIEREN_LABEL
        assert knoepfe[2]["url"] == installier_url(url)
        assert "installieren=1" in knoepfe[2]["url"]
    else:
        assert len(knoepfe) == 2


@pytest.mark.parametrize("key", sorted(_NACH_KEY))
def test_jede_app_url_ist_absolut_auf_der_funnel_origin(key):
    knoepfe = _task().run({"apps": [key]}, _turn())["presentation"]["inline_buttons"]
    for knopf in knoepfe:
        adresse = knopf.get("web_app_url") or knopf["url"]
        assert adresse.startswith(_BASIS + "/")
        assert "//" not in adresse[len("https://"):]


#: Natürliche Frage → erwartete App (die Tabelle aus dem PR). Geprüft wird,
#: dass das Verzeichnis-Vokabular (label/synonyme) die Frage trägt — genau
#: das bekommt das Modell zum Wählen.
FRAGEN = [
    ("Wie wird das Wetter heute?", "wetter-heute"),
    ("Garderobe bearbeiten", "wetter-regeln"),
    ("Mach die Essens-Wünsche auf", "essen-wunsch"),
    ("Ich will Sachen auf der Liste abhaken", "essen-einkauf"),
    ("Öffne den KIBuddy", "kibuddy-frage"),
    ("Schick mir den Bilderrahmen", "photo-rahmen"),
    ("Zeig mir den Wochenplan", "plan-woche"),
    ("Wer macht was am Montag?", "plan-einstellungen"),
    ("Die Checkliste für morgens bitte", "routine-morgen"),
    ("Routine bearbeiten", "routine-anpassen"),
    ("Gib mir die Übersicht", "seiten-uebersicht"),
    ("Kacheln bearbeiten", "seiten-kacheln"),
    ("Was kosten die KI-Anbieter?", "seiten-connector"),
    ("Hörbuch hören", "seiten-hoerspiel-player"),
]


def test_fragen_tabelle_deckt_das_ganze_verzeichnis():
    assert {k for _f, k in FRAGEN} == set(_NACH_KEY), (
        "Jede App braucht eine Beispiel-Frage (PR-Tabelle #1964)")


@pytest.mark.parametrize(("frage", "key"), FRAGEN)
def test_natuerliche_frage_trifft_das_vokabular_der_app(frage, key):
    eintrag = _NACH_KEY[key]
    begriffe = [eintrag["label"].lower()] + [s.lower() for s in eintrag["synonyme"]]
    assert any(b in frage.lower() for b in begriffe), (
        "%r trägt kein Label/Synonym von %s (%r)" % (frage, key, begriffe))


# ── Garderobe: der tote Knopf ist weg ───────────────────────────────────────

def test_garderoben_knopf_zeigt_auf_seiten_wetter_regeln():
    knoepfe = _task().run({"apps": ["wetter-regeln"]}, _turn())["presentation"]["inline_buttons"]
    assert knoepfe[0]["web_app_url"] == _BASIS + "/seiten/wetter/regeln"
    assert all("/display/wetter/regeln" not in (k.get("web_app_url") or k["url"])
               for k in knoepfe)


# ── Mehrdeutig: beide Knopfreihen in einer Nachricht ─────────────────────────

def test_mehrdeutig_wetter_schickt_beide_apps():
    result = _task().run({"apps": ["wetter-heute", "wetter-regeln"]}, _turn())
    knoepfe = result["presentation"]["inline_buttons"]
    assert result["text"] == "Dazu passen „Wetter heute“ und „Wetter-Regeln“."
    # Wetter heute: 2 Knöpfe, Wetter-Regeln (PWA): 3 Knöpfe.
    assert [k["label"] for k in knoepfe] == [
        "📱 Wetter heute öffnen", "🌐 Wetter heute im Browser",
        "📱 Wetter-Regeln öffnen", "🌐 Wetter-Regeln im Browser",
        "⬇ Wetter-Regeln installieren",
    ]


def test_hoechstens_drei_apps_und_keine_doppelten():
    keys = ["wetter-heute", "wetter-heute", "plan-woche", "routine-morgen",
            "kibuddy-frage"]
    result = _task().run({"apps": keys}, _turn())
    web_apps = [k for k in result["presentation"]["inline_buttons"] if "web_app_url" in k]
    assert len(web_apps) == MAX_APPS == 3


# ── Fehlerpfade ─────────────────────────────────────────────────────────────

def test_unbekannter_key_ehrlich_ohne_knopf():
    result = _task().run({"apps": ["gibt-es-nicht"]}, _turn())
    assert result["presentation"] == {}
    assert "kenne ich nicht" in result["text"]


def test_einzelner_key_als_string_wird_akzeptiert():
    result = _task().run({"apps": "plan-woche"}, _turn())
    assert result["presentation"]["inline_buttons"]


def test_ohne_verzeichnis_ehrlich_ohne_knopf():
    result = _task(eintraege=[]).run({"apps": ["plan-woche"]}, _turn())
    assert result["presentation"] == {}
    assert "nicht erreichbar" in result["text"]


def test_ohne_basis_url_fehler_text():
    result = _task(basis="").run({"apps": ["plan-woche"]}, _turn())
    assert result["presentation"] == {}
    assert "fehlt" in result["text"]


def test_nicht_mitglied_wird_abgewiesen():
    with pytest.raises(BerechtigungError):
        _task(is_member=lambda uid: False).run({"apps": ["plan-woche"]}, _turn())


def test_ohne_user_id_wird_abgewiesen():
    with pytest.raises(BerechtigungError):
        app_oeffnen(1, None, ["plan-woche"], VERZEICHNIS, lambda uid: True, _BASIS)


def test_werkzeug_definition_ohne_verzeichnis_hat_kein_enum():
    definition = _task(eintraege=[]).to_def()
    assert "enum" not in definition.parameters["properties"]["apps"]["items"]
    assert "nicht erreichbar" in definition.description


def test_ist_lesende_aufgabe_mit_anzeige_copy():
    task = _task()
    assert isinstance(task, ReadTask)
    assert task.name == "app_oeffnen"
    assert task.anzeige_copy


def test_render_form_b_schickt_die_knopfreihe_an_telegram():
    tg = MagicMock()
    result = _task().run({"apps": ["routine-anpassen"]}, _turn())
    render_form_b(result, tg, 42)
    knoepfe = tg.send_inline_keyboard.call_args[0][2]
    assert knoepfe[0]["web_app_url"] == _BASIS + "/seiten/routine/anpassen"
    assert knoepfe[2]["url"].endswith("?installieren=1")


# ── AppVerzeichnis: Zwischenspeicher über der Registry ──────────────────────

class _Client:
    def __init__(self, antworten):
        self._antworten = list(antworten)
        self.aufrufe = 0

    def inventar(self):
        self.aufrufe += 1
        antwort = self._antworten.pop(0)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort


def test_verzeichnis_haelt_den_stand_bis_zur_ttl():
    jetzt = [0.0]
    client = _Client([[_NACH_KEY["plan-woche"]], [_NACH_KEY["wetter-heute"]]])
    v = AppVerzeichnis(client, ttl=300, uhr=lambda: jetzt[0])
    assert [e["key"] for e in v.eintraege()] == ["plan-woche"]
    jetzt[0] = 299
    assert [e["key"] for e in v.eintraege()] == ["plan-woche"]
    assert client.aufrufe == 1
    jetzt[0] = 301
    assert [e["key"] for e in v.eintraege()] == ["wetter-heute"]


def test_verzeichnis_behaelt_letzten_stand_wenn_registry_weg_ist():
    jetzt = [0.0]
    client = _Client([[_NACH_KEY["plan-woche"]], SeitenClientError("weg")])
    v = AppVerzeichnis(client, ttl=1, uhr=lambda: jetzt[0])
    v.eintraege()
    jetzt[0] = 5
    assert [e["key"] for e in v.eintraege()] == ["plan-woche"]


def test_verzeichnis_ohne_je_einen_stand_ist_leer():
    v = AppVerzeichnis(_Client([SeitenClientError("weg")]))
    assert v.eintraege() == []


def test_verzeichnis_verwirft_unvollstaendige_eintraege():
    v = AppVerzeichnis(_Client([[{"key": "x"}, "kaputt", _NACH_KEY["plan-woche"]]]))
    assert [e["key"] for e in v.eintraege()] == ["plan-woche"]


# ── Katalog-Guard ───────────────────────────────────────────────────────────

def _katalog(**kw):
    return build_catalog(MagicMock(), "", **kw)


def test_guard_alle_drei_gesetzt_task_im_katalog():
    cat = _katalog(seiten_origin_url="http://127.0.0.1:5042",
                   mini_app_base_url=_BASIS,
                   family_group_chat_id_getter=lambda: -100)
    assert cat.get("app_oeffnen") is not None


@pytest.mark.parametrize("fehlt", ["seiten_origin_url", "mini_app_base_url",
                                   "family_group_chat_id_getter"])
def test_guard_fehlt_eins_nicht_im_katalog(fehlt):
    kw = {"seiten_origin_url": "http://127.0.0.1:5042",
          "mini_app_base_url": _BASIS,
          "family_group_chat_id_getter": lambda: -100}
    kw.pop(fehlt)
    assert _katalog(**kw).get("app_oeffnen") is None


def test_abgerissene_oeffnen_skills_sind_nicht_mehr_im_katalog():
    cat = _katalog(seiten_origin_url="http://127.0.0.1:5042",
                   mini_app_base_url=_BASIS,
                   routine_origin_url="http://127.0.0.1:5050",
                   hoerspiel_url_origin="http://127.0.0.1:5053",
                   family_group_chat_id_getter=lambda: -100)
    for name in ("hoerspiel_oeffnen", "routine_anpassen_oeffnen",
                 "wetter_regeln_oeffnen"):
        assert cat.get(name) is None


# ── Der App-Knopf-Baustein ──────────────────────────────────────────────────

def test_knopfreihe_ohne_pwa():
    assert app_knoepfe("https://x/a", "📱 A öffnen") == [
        {"label": "📱 A öffnen", "web_app_url": "https://x/a"},
        {"label": "🌐 Im Browser öffnen", "url": "https://x/a"},
    ]


def test_knopfreihe_mit_pwa_hat_installieren_als_dritten_knopf():
    knoepfe = app_knoepfe("https://x/a/", "A", pwa=True)
    assert knoepfe[2] == {"label": "⬇ Installieren",
                          "url": "https://x/a/?installieren=1"}


def test_knopfreihe_mit_namen_fuer_mehrere_apps():
    knoepfe = app_knoepfe("https://x/a", "A", pwa=True, name="Plan")
    assert [k["label"] for k in knoepfe] == [
        "A", "🌐 Plan im Browser", "⬇ Plan installieren"]


def test_installier_url_haengt_an_bestehende_query_an():
    assert installier_url("https://x/a?fit=viewport") == (
        "https://x/a?fit=viewport&installieren=1")
    assert installier_url("https://x/a") == "https://x/a?installieren=1"


@pytest.mark.parametrize(("basis", "pfad", "erwartet"), [
    ("https://x", "/seiten/a", "https://x/seiten/a"),
    ("https://x/", "/seiten/a", "https://x/seiten/a"),
    ("https://x", "seiten/a", "https://x/seiten/a"),
    ("https://x", "https://t.me/bot/app", "https://t.me/bot/app"),
])
def test_absolute_url(basis, pfad, erwartet):
    assert absolute_url(basis, pfad) == erwartet
