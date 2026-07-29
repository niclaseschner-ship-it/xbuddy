"""T712: Einkauf-Roundtrip-Test — EIN-1 … EIN-8, ESSEN-30, ICONS-7.

Roundtrip gegen ECHTE essen.app und seiten.app via Flask-test_client.
Kein FakeEssenClient, kein FakeIconClient — die Skill-Funktion
einkauf_hinzufuegen() spricht über EssenClient + IconClient mit den
echten Flask-Instanzen. Die ICONS-7-Stichwort-Suche wird seit RAT-31
(Router-Abriss, #1568) von der Seiten-Registry serviert (seiten/main.py
`/api/v1/icons/suche`, RAT-31 E6f-B/#1586) — vormals router.app.

Fünf Akzeptanz-Pfade (AC1 … AC5 des T712-Contracts):
  AC1 — frei-Item „Brot" → kein Katalog-Match → POST klasse=einkauf,
         kategorie=sonstiges, bild_ref aus ICONS-7-Fallback.
  AC2 — Katalog-Item „Apfel" → kategorie=obst_gemuese, item_id=apfel,
         bild_ref aus Katalog.
  AC3 — ICONS-7-Fallback: bild_ref = ICONS-7-ID wenn kein Katalog-Match.
  AC4 — 413 Liste voll → Skill-Klartext „Liste ist voll" / Aufräumen-Hinweis,
         kein zweiter Write.
  AC5 — ESSEN-30 PATCH aus_gericht → PATCH wuensche/<id> mit aus_gericht, 200.

Transport-Naht (CLIENT-1): Callable `(method, path, *, body, content_type)
→ (status, bytes)` leitet alle HTTP-Aufrufe an den Flask-test_client.

AC6 — Zwei Flask-test_clients (essen.app + seiten.app); EssenClient /
       IconClient erhalten jeweils ihre eigene Transport-Naht.
AC7 — ruff + lint-imports clean; alle Tests grün.
"""

import json
import os

import pytest
from skills.einkauf_hinzufuegen import einkauf_hinzufuegen
from skills.essen_client import EssenClient
from skills.icon_client import IconClient

# ── Importpfad-Setup ──────────────────────────────────────────────────────
#
# conftest.py (ein Verzeichnis höher in tests/) legt eltern-chat/ auf den
# Pfad, und unser integration/conftest.py legt zusätzlich Repo-Root drauf.
# Hier ist alles schon verfügbar.
import essen.main as essen_main
import seiten.main as seiten_main

# ============================================================
#  Hilfs-Konstanten
# ============================================================

_APFEL_BILD_REF = "2462"   # aus katalog.default.json
_APFEL_ITEM_ID  = "apfel"
_APFEL_KATEGORIE = "obst_gemuese"

# Eine beliebige bild_ref, die wir als ICONS-7-Ergebnis injizieren.
_BROT_ICON_ID = 9990        # int (wie seiten/icons-suche liefert)

# Pfad zur katalog.default.json im Repo.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
)
_KATALOG_DEFAULT = os.path.join(_REPO_ROOT, "essen", "katalog.default.json")


# ============================================================
#  Fixtures — Flask-Test-Clients
# ============================================================

@pytest.fixture
def essen_app_fixture(tmp_path):
    """Baut die essen.app mit eigenen Temp-Files und gibt (app, paths) zurück.

    Alle Datei-Pfade zeigen auf tmp_path, sodass jeder Test mit einem
    sauberen Zustand beginnt. Die essen.app ist zustandslos per Reload-on-Read;
    essen_main.configure() setzt den Pfad-Kontext.
    """
    paths = {
        "wuensche_file":         str(tmp_path / "wuensche.json"),
        "einkaufsliste_file":    str(tmp_path / "einkaufsliste.json"),
        "zaehler_file":          str(tmp_path / "zaehler.json"),
        "gerichte_file":         str(tmp_path / "gerichte.json"),
        "katalog_file":          str(tmp_path / "katalog.json"),  # leer = kein Override
        "katalog_default_file":  _KATALOG_DEFAULT,
        "foto_overrides_file":   str(tmp_path / "foto_overrides.json"),
    }
    # Reset runtime-Zustand der Modul-Singleton (wichtig: Tests laufen im
    # selben Prozess, also müssen Snapshots zurückgesetzt werden).
    essen_main.runtime["wuensche_snapshot"] = None
    essen_main.runtime["einkauf_snapshot"]  = None
    essen_main.runtime["zaehler_snapshot"]  = None
    essen_main.runtime["gerichte_snapshot"] = None
    essen_main.runtime["katalog_snapshot"]  = None

    essen_main.configure(paths, listen_grenze_einkauf=50)
    essen_main.app.testing = True
    return essen_main.app, paths


@pytest.fixture
def seiten_app_fixture(tmp_path):
    """Baut die seiten.app mit einer temporären Icon-Root und gibt
    (app, icon_root_path) zurück.

    Seit RAT-31 E6f-B (#1586) serviert die Seiten-Registry die
    ICONS-7-Stichwort-Suche (`/api/v1/icons/suche`, vormals Router).
    Damit sie Treffer liefert, braucht sie:
      1. Eine `pictogram_cache.json` in icon_root_path.
      2. PNGs unter icon_root_path/arasaac/<id>.png.

    Wir legen für den Test-Icon-ID `_BROT_ICON_ID` die nötigen Dateien an.
    """
    icon_root = str(tmp_path / "icons")
    arasaac_dir = os.path.join(icon_root, "arasaac")
    os.makedirs(arasaac_dir, exist_ok=True)

    # pictogram_cache.json: "brot" → _BROT_ICON_ID (int, wie seiten es erwartet)
    cache_data = {"brot": _BROT_ICON_ID}
    with open(os.path.join(icon_root, "pictogram_cache.json"), "w", encoding="utf-8") as f:
        json.dump(cache_data, f)

    # PNG muss existieren, damit seiten es ausliefert.
    png_path = os.path.join(arasaac_dir, "%d.png" % _BROT_ICON_ID)
    with open(png_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")  # minimal PNG-Header

    # seiten runtime auf icon_root setzen + Pictogram-Cache flushen.
    seiten_main.runtime["icon_root"] = icon_root
    seiten_main._pictogram_cache = {}
    seiten_main._pictogram_cache_root = ""

    seiten_main.app.testing = True
    return seiten_main.app, icon_root


# ============================================================
#  Transport-Naht-Helfer
# ============================================================

def make_flask_transport(flask_test_client):
    """Baut eine Transport-Callable, die HTTP-Aufrufe an flask_test_client leitet.

    Signatur: `(method, path, *, body=None, content_type=None) -> (status, bytes)`.
    Entspricht der CLIENT-1-Konvention in EssenClient und IconClient.
    """
    def transport(method, path, *, body=None, content_type=None):
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        m = method.upper()
        if m == "GET":
            resp = flask_test_client.get(path, headers=headers)
        elif m == "POST":
            resp = flask_test_client.post(path, data=body, headers=headers)
        elif m == "PATCH":
            resp = flask_test_client.patch(path, data=body, headers=headers)
        elif m == "DELETE":
            resp = flask_test_client.delete(path, headers=headers)
        else:
            raise AssertionError("unbekannte Methode: %s" % method)
        return resp.status_code, resp.data
    return transport


def _immer_mitglied(uid):
    return True


# ============================================================
#  Katalog aus katalog.default.json laden (EIN-4 Schritt 1)
# ============================================================

def _lade_katalog_default():
    """Liest den Katalog aus katalog.default.json und flacht ihn auf."""
    with open(_KATALOG_DEFAULT, encoding="utf-8") as f:
        data = json.load(f)
    items = []
    kategorien = data.get("kategorien", {})
    for kat_name, kat_items in kategorien.items():
        for item in kat_items:
            items.append({
                "id":        item.get("id", ""),
                "label":     item.get("label", ""),
                "bild_ref":  item.get("bild_ref", ""),
                "item_id":   item.get("id", ""),    # item_id == id im Default-Katalog
                "kategorie": kat_name,
            })
    return items


# ============================================================
#  AC1 — frei-Item „Brot": kein Katalog-Match, ICONS-7-Fallback
# ============================================================

def test_freitext_brot_routet_zu_einkauf(essen_app_fixture, seiten_app_fixture):
    """AC1 + AC3: frei-Item 'Brot' → keine Katalog-Übereinstimmung →
    ICONS-7-Fallback liefert bild_ref aus Router; POST hat klasse=einkauf,
    kategorie=sonstiges.

    Hinweis: 'Brot' ist IM Katalog (katalog.default.json, brotbelag).
    Wir übergeben daher katalog=None (kein Katalog-Match-Versuch), um
    den reinen ICONS-7-Fallback-Pfad zu testen.
    """
    essen_app, _paths = essen_app_fixture
    seiten_app, _icon_root = seiten_app_fixture

    essen_tc = essen_app.test_client()
    seiten_tc = seiten_app.test_client()

    essen_transport = make_flask_transport(essen_tc)
    icons_transport  = make_flask_transport(seiten_tc)

    essen_client = EssenClient(origin_url="http://essen.test", transport=essen_transport)
    icon_client  = IconClient(origin_url="http://icons.test",  transport=icons_transport)

    # katalog=None → kein Katalog-Match → ICONS-7-Fallback für "Brot" → bild_ref=_BROT_ICON_ID
    result = einkauf_hinzufuegen(
        text="Brot",
        from_user_id=7,
        essen_client=essen_client,
        icon_client=icon_client,
        is_member_fn=_immer_mitglied,
        katalog=None,
    )

    # Skill-Antwort enthält "Brot" und "dazu" (EIN-6)
    assert "Brot" in result, "Antwort muss 'Brot' nennen: %r" % result
    assert "dazu" in result.lower() or "offen" in result.lower(), \
        "Antwort muss Bestätigung enthalten: %r" % result

    # Write-Proof: GET /api/v1/essen/wuensche?klasse=einkauf zeigt den Eintrag
    resp = essen_tc.get("/api/v1/essen/wuensche?klasse=einkauf")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    wuensche = body["wuensche"]
    assert len(wuensche) == 1, "Genau ein Eintrag erwartet: %r" % wuensche

    eintrag = wuensche[0]
    assert eintrag["klasse"]    == "einkauf",   "klasse muss 'einkauf' sein"
    assert eintrag["kategorie"] == "sonstiges", "keine Katalog-Übereinstimmung → sonstiges"
    assert eintrag["quelle"]    == "eltern",    "quelle muss 'eltern' sein"
    # AC3: bild_ref kommt aus ICONS-7 (pictogram_cache hat brot → _BROT_ICON_ID)
    assert eintrag["bild_ref"]  == str(_BROT_ICON_ID), \
        "AC3: bild_ref muss ICONS-7-ID sein, bekam: %r" % eintrag["bild_ref"]
    assert eintrag["item_id"].startswith("frei:"), \
        "frei-Item muss item_id mit 'frei:'-Prefix haben: %r" % eintrag["item_id"]


# ============================================================
#  AC2 — Katalog-Item „Apfel": item_id + bild_ref aus Katalog
# ============================================================

def test_katalog_apfel_findet_item_id(essen_app_fixture, seiten_app_fixture):
    """AC2: 'Apfel' → Katalog-Match → POST mit kategorie=obst_gemuese,
    item_id=apfel, bild_ref=2462 (aus katalog.default.json).
    """
    essen_app, _paths = essen_app_fixture
    seiten_app, _icon_root = seiten_app_fixture

    essen_tc = essen_app.test_client()
    seiten_tc = seiten_app.test_client()

    essen_client = EssenClient(
        origin_url="http://essen.test",
        transport=make_flask_transport(essen_tc),
    )
    icon_client = IconClient(
        origin_url="http://icons.test",
        transport=make_flask_transport(seiten_tc),
    )

    katalog = _lade_katalog_default()

    result = einkauf_hinzufuegen(
        text="Apfel",
        from_user_id=7,
        essen_client=essen_client,
        icon_client=icon_client,
        is_member_fn=_immer_mitglied,
        katalog=katalog,
    )

    assert "Apfel" in result, "Antwort muss 'Apfel' nennen: %r" % result

    # Write-Proof
    resp = essen_tc.get("/api/v1/essen/wuensche?klasse=einkauf")
    assert resp.status_code == 200
    wuensche = json.loads(resp.data)["wuensche"]
    assert len(wuensche) == 1

    eintrag = wuensche[0]
    assert eintrag["klasse"]    == "einkauf",       "klasse muss 'einkauf' sein"
    assert eintrag["kategorie"] == _APFEL_KATEGORIE, \
        "Katalog-Match: kategorie muss obst_gemuese sein"
    assert eintrag["item_id"]   == _APFEL_ITEM_ID,  \
        "Katalog-Match: item_id muss 'apfel' sein, bekam: %r" % eintrag["item_id"]
    assert eintrag["bild_ref"]  == _APFEL_BILD_REF, \
        "Katalog-Match: bild_ref muss '2462' sein, bekam: %r" % eintrag["bild_ref"]


# ============================================================
#  AC3 — ICONS-7-Fallback: bild_ref aus ICONS-7-Antwort
# ============================================================

def test_icons7_fallback_brot_pikto(essen_app_fixture, seiten_app_fixture):
    """AC3: ICONS-7-Fallback — 'Brot' ohne Katalog → bild_ref kommt aus dem
    Router-Cache (pictogram_cache.json: brot → _BROT_ICON_ID).

    Dedizierter Test für den Fallback-Pfad: katalog=[] (leerer Katalog),
    damit der Skill direkt zu ICONS-7 springt.
    """
    essen_app, _paths = essen_app_fixture
    seiten_app, _icon_root = seiten_app_fixture

    essen_tc = essen_app.test_client()
    seiten_tc = seiten_app.test_client()

    essen_client = EssenClient(
        origin_url="http://essen.test",
        transport=make_flask_transport(essen_tc),
    )
    icon_client = IconClient(
        origin_url="http://icons.test",
        transport=make_flask_transport(seiten_tc),
    )

    # Leerer Katalog → ICONS-7-Fallback
    result = einkauf_hinzufuegen(
        text="Brot",
        from_user_id=7,
        essen_client=essen_client,
        icon_client=icon_client,
        is_member_fn=_immer_mitglied,
        katalog=[],
    )

    assert "Brot" in result or "dazu" in result.lower(), \
        "Antwort muss Bestätigung enthalten: %r" % result

    resp = essen_tc.get("/api/v1/essen/wuensche?klasse=einkauf")
    wuensche = json.loads(resp.data)["wuensche"]
    assert len(wuensche) == 1

    eintrag = wuensche[0]
    # ICONS-7 hat "brot" → _BROT_ICON_ID im pictogram_cache; der Router liefert
    # ihn als int, der EssenClient-Payload erwartet str.
    assert eintrag["bild_ref"] == str(_BROT_ICON_ID), \
        "AC3: bild_ref muss ICONS-7-ID %d sein, bekam: %r" % (_BROT_ICON_ID, eintrag["bild_ref"])
    assert eintrag["kategorie"] == "sonstiges", \
        "ICONS-7-Fallback ohne Katalog → sonstiges"
    assert eintrag["item_id"].startswith("frei:"), \
        "ICONS-7-Fallback → item_id mit frei:-Prefix"


# ============================================================
#  AC4 — 413 Liste voll: Klartext, kein zweiter Write
# ============================================================

def test_liste_voll_413_klartext_quittung(essen_app_fixture, seiten_app_fixture):
    """AC4: Listen-Grenze (413) → Skill-Klartext mit Aufräumen-Hinweis;
    zweites Item wird nicht geschrieben.

    Setup: listen_grenze_einkauf=1. Erstes Item → 201. Zweites Item → 413
    (Grenze erreicht). Skill darf danach kein weiteres POST senden.
    """
    essen_app, _paths = essen_app_fixture
    seiten_app, _icon_root = seiten_app_fixture

    # Grenze auf 1 setzen — ein offenes Item füllt die Liste.
    essen_main.configure(_paths, listen_grenze_einkauf=1)
    # Snapshots zurücksetzen damit configure wirkt.
    essen_main.runtime["einkauf_snapshot"] = None

    essen_tc = essen_app.test_client()
    seiten_tc = seiten_app.test_client()

    essen_client = EssenClient(
        origin_url="http://essen.test",
        transport=make_flask_transport(essen_tc),
    )
    icon_client = IconClient(
        origin_url="http://icons.test",
        transport=make_flask_transport(seiten_tc),
    )

    # Erstes Item: füllt die Liste (grenze=1)
    result1 = einkauf_hinzufuegen(
        text="Milch",
        from_user_id=7,
        essen_client=essen_client,
        icon_client=icon_client,
        is_member_fn=_immer_mitglied,
        katalog=None,
    )
    # Erstes Item muss OK sein
    assert "Milch" in result1 or "dazu" in result1.lower(), \
        "Erstes Item muss OK sein: %r" % result1

    # Zweites Item: Liste voll → 413
    result2 = einkauf_hinzufuegen(
        text="Joghurt",
        from_user_id=7,
        essen_client=essen_client,
        icon_client=icon_client,
        is_member_fn=_immer_mitglied,
        katalog=None,
    )

    # Skill-Antwort enthält Hinweis auf volle Liste
    aufraeum_hinweis = (
        "aufräumen" in result2.lower()
        or "aufr" in result2.lower()
        or "voll" in result2.lower()
        or "grenze" in result2.lower()
        or "konnte" in result2.lower()
        or "liste" in result2.lower()
    )
    assert aufraeum_hinweis, \
        "AC4: Skill muss Aufräum-/Grenz-Hinweis geben, bekam: %r" % result2

    # Write-Proof: nur 1 Item in der Einkaufsliste (kein zweites Write)
    resp = essen_tc.get("/api/v1/essen/wuensche?klasse=einkauf")
    wuensche = json.loads(resp.data)["wuensche"]
    assert len(wuensche) == 1, \
        "AC4: nach 413 darf kein zweites Item in der Liste sein, gefunden: %d" % len(wuensche)


# ============================================================
#  AC5 — ESSEN-30 PATCH aus_gericht → 200
# ============================================================

def test_aus_gericht_patch(essen_app_fixture, seiten_app_fixture):
    """AC5 / ESSEN-30: PATCH wuensche/<id> mit aus_gericht → HTTP 200;
    Eintrag hat aus_gericht-Feld gesetzt.

    Schritte:
    1. Item zur Einkaufsliste hinzufügen (POST, klasse=einkauf).
    2. ID aus der Antwort nehmen.
    3. PATCH mit aus_gericht='Kartoffelsuppe'.
    4. Assert: 200, Eintrag in GET hat aus_gericht='Kartoffelsuppe'.
    """
    essen_app, _paths = essen_app_fixture
    seiten_app, _icon_root = seiten_app_fixture

    essen_tc = essen_app.test_client()
    seiten_tc = seiten_app.test_client()

    essen_transport = make_flask_transport(essen_tc)
    icons_transport  = make_flask_transport(seiten_tc)

    essen_client = EssenClient(
        origin_url="http://essen.test",
        transport=essen_transport,
    )
    icon_client = IconClient(
        origin_url="http://icons.test",
        transport=icons_transport,
    )

    # 1. Item hinzufügen — "Karotte" ist im Katalog (obst_gemuese).
    katalog = _lade_katalog_default()
    result = einkauf_hinzufuegen(
        text="Karotte",
        from_user_id=7,
        essen_client=essen_client,
        icon_client=icon_client,
        is_member_fn=_immer_mitglied,
        katalog=katalog,
    )
    assert "Karotte" in result or "dazu" in result.lower(), \
        "Schritt 1: Karotte hinzufügen muss OK sein: %r" % result

    # 2. ID aus der Einkaufsliste holen
    resp = essen_tc.get("/api/v1/essen/wuensche?klasse=einkauf")
    assert resp.status_code == 200
    wuensche = json.loads(resp.data)["wuensche"]
    assert len(wuensche) == 1, "Genau ein Eintrag erwartet nach POST"
    eintrag_id = wuensche[0]["id"]

    # 3. PATCH via EssenClient (ESSEN-32 / patche_eintrag)
    patch_result = essen_client.patche_eintrag(
        eintrag_id=eintrag_id,
        aus_gericht="Kartoffelsuppe",
    )

    # 4. Assert PATCH-Antwort
    assert patch_result is not None, "patche_eintrag muss Dict zurückgeben"
    assert patch_result.get("aus_gericht") == "Kartoffelsuppe", \
        "AC5: aus_gericht muss 'Kartoffelsuppe' sein, bekam: %r" % patch_result

    # Write-Proof via GET
    resp2 = essen_tc.get("/api/v1/essen/wuensche?klasse=einkauf")
    wuensche2 = json.loads(resp2.data)["wuensche"]
    eintrag_nach_patch = next(
        (w for w in wuensche2 if w["id"] == eintrag_id), None
    )
    assert eintrag_nach_patch is not None, \
        "Eintrag %r muss nach PATCH noch in der Liste sein" % eintrag_id
    assert eintrag_nach_patch.get("aus_gericht") == "Kartoffelsuppe", \
        "AC5: GET nach PATCH muss aus_gericht='Kartoffelsuppe' zeigen"
