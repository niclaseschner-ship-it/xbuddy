"""Tests pro GER-Requirement (GER-10).

Lauf: python3 -m pytest geraete/tests/ -v

Die Suite läuft ohne Netz und ohne externes Setup. Per-Instanz-Datei wird
in `tmp_path` simuliert; 0600-Permissions werden über `os.stat` geprüft.
Race-Freiheit (GER-6) wird über (a) den atomaren `os.replace`-Rename und
(b) das 0600-Anlegen via `os.open` belegt — analog FAM-11 und ONB-5.
"""

import json
import os
import stat
import sys

import pytest

# geraete/ ist ein Paket — Repo-Wurzel auf den Importpfad, damit
# `from geraete import …` funktioniert. Analog familie/tests/.
_GERAETE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_GERAETE_DIR)
sys.path.insert(0, _REPO_ROOT)

from geraete import registry as registry_mod  # noqa: E402

# ============================================================
#  Demo-Daten
# ============================================================

# Drei Geräte, die alle GER-3-Mengen mindestens einmal treffen.
DEMO_GERAETE = {
    "geraete": [
        {
            "id": "tablet-elias-01",
            "typ": "tablet",
            "name": "Tablet Elias",
            "aufloesung": {"w": 2560, "h": 1600},
            "os": "android",
            "verwendung": "beides",
            "status": "aktiv",
        },
        {
            "id": "pi-display-flur-01",
            "typ": "pi-display",
            "name": "Pi-Display Flur",
            "aufloesung": {"w": 1920, "h": 1080},
            "os": "linux",
            "verwendung": "display",
            "status": "aktiv",
        },
        {
            "id": "handy-mama-01",
            "typ": "handy",
            "name": "Handy Mama",
            "aufloesung": {"w": 1170, "h": 2532},
            "os": "ios",
            "verwendung": "controller",
            "status": "inaktiv",
        },
    ],
}


@pytest.fixture
def demo_pfad(tmp_path):
    """Schreibt DEMO_GERAETE in eine Datei und liefert den Pfad."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    return str(p)


# ============================================================
#  GER-1 — Eine Instanz, eine Geräte-Registry
# ============================================================

def test_GER_1_registry_describes_exactly_one_family(demo_pfad):
    """Die geladene Registry ist eine flache Liste — kein familien-
    übergreifender Bezeichner, kein Cross-Familie-Zugriff."""
    reg = registry_mod.load(demo_pfad)
    assert isinstance(reg, registry_mod.Registry)
    # Alle drei Geräte in EINER Liste — keine Gruppierung nach Familie.
    assert {g.id for g in reg.list_all()} == {
        "tablet-elias-01", "pi-display-flur-01", "handy-mama-01"}


# ============================================================
#  GER-2 — Geräte-Typen V1
# ============================================================

def test_GER_2_typen_is_the_fixed_set():
    """Die Typen-Menge ist genau die in der Spec genannte, endliche Liste."""
    assert registry_mod.TYPEN == ("tablet", "handy", "monitor", "pi-display")


def test_GER_2_unknown_typ_is_error(tmp_path):
    """Ein Typ außerhalb von GER-2 ist ein Datei-Fehler (RegistryError)."""
    bad = tmp_path / "geraete.json"
    bad.write_text(json.dumps({"geraete": [{
        "id": "drohne-elias-01", "typ": "drohne", "name": "X",
        "aufloesung": {"w": 1, "h": 1}, "os": "linux",
        "verwendung": "display", "status": "aktiv"}]}))
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


# ============================================================
#  GER-3 — Eigenschaften eines Geräts
# ============================================================

def test_GER_3_fields_required_and_loaded(demo_pfad):
    """Alle GER-3-Pflichtfelder sind nach load() zugreifbar."""
    reg = registry_mod.load(demo_pfad)
    g = reg.get("tablet-elias-01")
    assert g.id == "tablet-elias-01"
    assert g.typ == "tablet"
    assert g.name == "Tablet Elias"
    assert g.aufloesung == {"w": 2560, "h": 1600}
    assert g.os == "android"
    assert g.verwendung == "beides"
    assert g.status == "aktiv"


def test_GER_3_missing_required_field_is_error(tmp_path):
    """Fehlt ein GER-3-Pflichtfeld, ist die Datei ungültig."""
    bad = tmp_path / "geraete.json"
    # `status` fehlt.
    bad.write_text(json.dumps({"geraete": [{
        "id": "tablet-x-01", "typ": "tablet", "name": "X",
        "aufloesung": {"w": 1, "h": 1}, "os": "linux",
        "verwendung": "display"}]}))
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


def test_GER_3_unknown_os_or_verwendung_or_status_is_error(tmp_path):
    """Werte außerhalb der GER-3-Mengen werfen RegistryError."""
    template = {
        "id": "tablet-x-01", "typ": "tablet", "name": "X",
        "aufloesung": {"w": 1, "h": 1}, "os": "linux",
        "verwendung": "display", "status": "aktiv",
    }
    for feld, schlechter_wert in [
        ("os", "windows-phone"), ("verwendung", "wandschmuck"),
        ("status", "schlummert"),
    ]:
        bad = tmp_path / ("g_%s.json" % feld)
        eintrag = dict(template, **{feld: schlechter_wert})
        bad.write_text(json.dumps({"geraete": [eintrag]}))
        with pytest.raises(registry_mod.RegistryError):
            registry_mod.load(str(bad))


def test_GER_3_aufloesung_must_be_positive_int_pair(tmp_path):
    """`aufloesung` muss `{w,h}` mit positiven Ganzzahlen sein."""
    template = {
        "id": "tablet-x-01", "typ": "tablet", "name": "X",
        "os": "linux", "verwendung": "display", "status": "aktiv",
    }
    for kaputt in [
        {"w": 0, "h": 100},
        {"w": -1, "h": 100},
        {"w": "1920", "h": 1080},   # String statt int
        {"w": 1920},                # Achse fehlt
        "1920x1080",                # nicht dict
    ]:
        bad = tmp_path / "g.json"
        bad.write_text(json.dumps({"geraete": [
            dict(template, aufloesung=kaputt)]}))
        with pytest.raises(registry_mod.RegistryError):
            registry_mod.load(str(bad))


# ============================================================
#  GER-4 — Registry als Per-Instanz-Datei
# ============================================================

def test_GER_4_missing_file_warns_and_empty_registry(tmp_path, caplog):
    """Fehlt die Datei: EINE Warnung, leere Registry, kein Crash."""
    with caplog.at_level("WARNING"):
        reg = registry_mod.load(str(tmp_path / "no-such-file.json"))
    assert reg.list_all() == []
    assert any("nicht gefunden" in rec.message for rec in caplog.records)


def test_GER_4_unparseable_file_warns_and_empty_registry(tmp_path, caplog):
    """Nicht parsebare Datei: Warnung, leere Registry, kein Crash."""
    bad = tmp_path / "geraete.json"
    bad.write_text("{kaputt", encoding="utf-8")
    with caplog.at_level("WARNING"):
        reg = registry_mod.load(str(bad))
    assert reg.list_all() == []
    assert any("nicht parsebar" in rec.message for rec in caplog.records)


def test_GER_4_save_creates_file_with_0600(tmp_path):
    """Frisch angelegte Registry-Datei hat Dateirechte 0600 (GER-4 / ZD-3-Pattern)."""
    p = tmp_path / "geraete.json"
    reg = registry_mod.Registry([
        registry_mod.Geraet(
            id="tablet-test-01", typ="tablet", name="Test",
            aufloesung={"w": 800, "h": 600}, os="linux",
            verwendung="display", status="aktiv")])
    assert not p.exists()
    registry_mod.save(reg, str(p))
    mode = stat.S_IMODE(os.stat(str(p)).st_mode)
    assert mode == 0o600, "erwartet 0600, bekam %o" % mode
    assert registry_mod.is_owner_only(str(p))


def test_GER_4_save_overwrites_loose_permissions_to_0600(tmp_path):
    """Eine bestehende Datei mit offeneren Rechten wird beim save auf 0600
    zurückgesetzt (defense-in-depth gegen Vor-PR-Datenstände)."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps({"geraete": []}), encoding="utf-8")
    os.chmod(str(p), 0o644)  # bewusst zu offen
    reg = registry_mod.load(str(p))
    registry_mod.save(reg, str(p))
    assert stat.S_IMODE(os.stat(str(p)).st_mode) == 0o600


def test_GER_4_example_file_matches_format():
    """`geraete.example.json` dokumentiert das Format — sie muss ladbar sein."""
    example = os.path.join(_GERAETE_DIR, "geraete.example.json")
    reg = registry_mod.load(example)
    assert len(reg.list_all()) > 0
    for g in reg.list_all():
        assert g.typ in registry_mod.TYPEN
        assert g.os in registry_mod.OS_WERTE
        assert g.verwendung in registry_mod.VERWENDUNGEN
        assert g.status in registry_mod.STATUS_WERTE


# ============================================================
#  GER-5 — Lese-Schnittstelle
# ============================================================

def test_GER_5_get_by_id(demo_pfad):
    """Holen einer Person … äh, eines Geräts je `id`."""
    reg = registry_mod.load(demo_pfad)
    g = reg.get("pi-display-flur-01")
    assert g is not None
    assert g.typ == "pi-display"


def test_GER_5_unknown_id_returns_none(demo_pfad):
    """Unbekannte `id`: None — kein Fehler (GER-5; Konsument behandelt)."""
    reg = registry_mod.load(demo_pfad)
    assert reg.get("tablet-nichtda-99") is None


def test_GER_5_list_all_returns_all_devices_active_and_inactive(demo_pfad):
    """list_all liefert aktive UND inaktive Geräte (GER-5: Konsument filtert)."""
    reg = registry_mod.load(demo_pfad)
    ids = {g.id for g in reg.list_all()}
    # `handy-mama-01` ist inaktiv und muss enthalten sein.
    assert ids == {"tablet-elias-01", "pi-display-flur-01", "handy-mama-01"}


def test_GER_5_list_by_verwendung_display_includes_beides(demo_pfad):
    """`verwendung=display` liefert sowohl reine display-Geräte als auch
    `beides`-Geräte — sonst müssten Konsumenten zwei Listen mischen."""
    reg = registry_mod.load(demo_pfad)
    ids = {g.id for g in reg.list_by_verwendung("display")}
    # pi-display-flur-01 (display) + tablet-elias-01 (beides). handy-mama-01
    # (controller) fehlt.
    assert ids == {"pi-display-flur-01", "tablet-elias-01"}


def test_GER_5_list_by_verwendung_controller_includes_beides(demo_pfad):
    """Symmetrisch: `verwendung=controller` enthält `beides`."""
    reg = registry_mod.load(demo_pfad)
    ids = {g.id for g in reg.list_by_verwendung("controller")}
    assert ids == {"handy-mama-01", "tablet-elias-01"}


def test_GER_5_list_by_verwendung_beides_returns_only_beides(demo_pfad):
    """`verwendung=beides` liefert genau die echten `beides`-Geräte."""
    reg = registry_mod.load(demo_pfad)
    ids = {g.id for g in reg.list_by_verwendung("beides")}
    assert ids == {"tablet-elias-01"}


def test_GER_5_list_by_verwendung_rejects_unknown_value(demo_pfad):
    """Ein verwendung-Wert außerhalb GER-3 ist ein Programmierfehler."""
    reg = registry_mod.load(demo_pfad)
    with pytest.raises(ValueError):
        reg.list_by_verwendung("buchregal")


# ============================================================
#  GER-6 — Schreib-Schnittstelle
# ============================================================

def test_GER_6_add_then_save_then_load_round_trip(tmp_path):
    """add → save → load: das neue Gerät ist da, mit allen GER-3-Feldern."""
    p = tmp_path / "geraete.json"
    reg = registry_mod.Registry()
    reg.add(registry_mod.Geraet(
        id="tablet-test-01", typ="tablet", name="Tablet Test",
        aufloesung={"w": 1024, "h": 600}, os="android",
        verwendung="display", status="aktiv"))
    registry_mod.save(reg, str(p))
    reg2 = registry_mod.load(str(p))
    g = reg2.get("tablet-test-01")
    assert g is not None
    assert g.aufloesung == {"w": 1024, "h": 600}


def test_GER_6_existing_devices_unchanged_after_adding_one(tmp_path):
    """Bestehende Geräte bleiben byte-gleich, wenn ein neues dazukommt."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    reg = registry_mod.load(str(p))

    reg.add(registry_mod.Geraet(
        id="monitor-buero-01", typ="monitor", name="Monitor Büro",
        aufloesung={"w": 3840, "h": 2160}, os="unbekannt",
        verwendung="display", status="aktiv"))
    registry_mod.save(reg, str(p))

    nachher = json.loads(p.read_text(encoding="utf-8"))
    # Die ersten drei Einträge sind die DEMO-Geräte in Original-Reihenfolge
    # und mit denselben Feldwerten.
    for vor, nach in zip(DEMO_GERAETE["geraete"], nachher["geraete"][:3]):
        for feld in ("id", "typ", "name", "aufloesung", "os", "verwendung", "status"):
            assert nach[feld] == vor[feld], feld
    # Neues Gerät am Ende.
    assert nachher["geraete"][3]["id"] == "monitor-buero-01"


def test_GER_6_save_is_atomic_no_partial_file_on_failure(tmp_path, monkeypatch):
    """Simulierter Schreib-Abbruch hinterlässt KEINE halbe Zieldatei
    und KEIN verwaistes Temp im Zielverzeichnis (GER-6 race-freies Pattern)."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    original_bytes = p.read_bytes()

    reg = registry_mod.load(str(p))
    reg.add(registry_mod.Geraet(
        id="monitor-neu-01", typ="monitor", name="Neu",
        aufloesung={"w": 800, "h": 600}, os="linux",
        verwendung="display", status="aktiv"))

    def boom(_src, _dst):
        raise OSError("simulierter Schreibabbruch")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.save(reg, str(p))

    # Zieldatei unverändert.
    assert p.read_bytes() == original_bytes
    # Kein verwaistes Temp im Zielverzeichnis.
    temps = [n for n in os.listdir(str(tmp_path))
             if n.startswith(".geraete.") and n.endswith(".tmp")]
    assert temps == [], "verwaiste Temp-Datei(en): %r" % temps


def test_GER_6_update_changes_only_specified_fields(tmp_path):
    """update() ändert nur die angegebenen Felder; alles andere bleibt."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    reg = registry_mod.load(str(p))

    reg.update("tablet-elias-01", name="Tablet Elias (umbenannt)")
    g = reg.get("tablet-elias-01")
    assert g.name == "Tablet Elias (umbenannt)"
    # Andere Felder unverändert.
    assert g.typ == "tablet"
    assert g.aufloesung == {"w": 2560, "h": 1600}
    assert g.os == "android"
    assert g.verwendung == "beides"
    assert g.status == "aktiv"


def test_GER_6_update_rejects_invalid_value(tmp_path):
    """update() lehnt Werte außerhalb der GER-3-Mengen ab, BEVOR mutiert wird."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    reg = registry_mod.load(str(p))

    with pytest.raises(registry_mod.RegistryError):
        reg.update("tablet-elias-01", os="windows-phone")
    # Gerät unverändert.
    assert reg.get("tablet-elias-01").os == "android"


def test_GER_6_update_rejects_id_change(tmp_path):
    """Die `id` ist stabil (GER-7) — update darf sie nicht ändern."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    reg = registry_mod.load(str(p))
    with pytest.raises(registry_mod.RegistryError):
        reg.update("tablet-elias-01", id="tablet-elias-02")


def test_GER_6_deactivate_only_changes_status(tmp_path):
    """deactivate() ändert NUR `status` auf `inaktiv` (GER-6)."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")
    reg = registry_mod.load(str(p))
    vorher = reg.get("tablet-elias-01").to_dict()
    reg.deactivate("tablet-elias-01")
    nachher = reg.get("tablet-elias-01").to_dict()
    assert nachher["status"] == "inaktiv"
    # Alle anderen Felder unverändert.
    for feld in ("id", "typ", "name", "aufloesung", "os", "verwendung"):
        assert nachher[feld] == vorher[feld]


def test_GER_6_save_uses_atomic_rename_in_target_dir(tmp_path, monkeypatch):
    """Die Temp-Datei wird im Zielverzeichnis angelegt — sonst wäre
    os.replace kein In-Filesystem-Rename mehr. Wir prüfen das durch
    Beobachten der mkstemp-Argumente."""
    p = tmp_path / "geraete.json"
    reg = registry_mod.Registry()
    calls = []
    import tempfile as _tempfile
    original = _tempfile.mkstemp

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        "geraete.registry.tempfile.mkstemp", spy)
    registry_mod.save(reg, str(p))
    assert len(calls) == 1
    assert calls[0]["dir"] == os.path.dirname(os.path.abspath(str(p)))


# ============================================================
#  GER-7 — `display_id`-Vergabe
# ============================================================

def test_GER_7_slugify_lowercases_and_strips_specials():
    """slugify produziert Kleinbuchstaben, Bindestriche, keine Umlaute/Sonderzeichen."""
    assert registry_mod.slugify("Tablet Wohnzimmer") == "tablet-wohnzimmer"
    assert registry_mod.slugify("Mama's iPhone!") == "mama-s-iphone"
    assert registry_mod.slugify("Büro Süd") == "buero-sued"
    assert registry_mod.slugify("Straße") == "strasse"


def test_GER_7_slugify_rejects_empty_result():
    """Ein Name, der zum leeren Slug wird, ist ein Datenfehler."""
    with pytest.raises(ValueError):
        registry_mod.slugify("...")
    with pytest.raises(ValueError):
        registry_mod.slugify("")


def test_GER_7_neue_id_follows_schema(tmp_path):
    """Schema `<typ>-<slug>-<nn>` wird eingehalten — nullgepolstert."""
    reg = registry_mod.Registry()
    nid = registry_mod.neue_id(reg, "tablet", "Wohnzimmer")
    assert nid == "tablet-wohnzimmer-01"


def test_GER_7_neue_id_increments_per_typ_slug(tmp_path):
    """Folgenummer beginnt je (Typ+Slug)-Kombination bei 01 und zählt hoch."""
    reg = registry_mod.Registry()
    # Erstes Wohnzimmer-Tablet: 01.
    id1 = registry_mod.neue_id(reg, "tablet", "Wohnzimmer")
    reg.add(registry_mod.Geraet(
        id=id1, typ="tablet", name="Tablet Wohnzimmer",
        aufloesung={"w": 1, "h": 1}, os="linux",
        verwendung="display", status="aktiv"))
    # Zweites Wohnzimmer-Tablet: 02.
    id2 = registry_mod.neue_id(reg, "tablet", "Wohnzimmer")
    assert id2 == "tablet-wohnzimmer-02"
    # Erstes Tablet mit anderem Slug: 01 (eigene Sequenz).
    assert registry_mod.neue_id(reg, "tablet", "Küche") == "tablet-kueche-01"
    # Anderer Typ, gleicher Slug: 01 (eigene Sequenz).
    assert registry_mod.neue_id(reg, "handy", "Wohnzimmer") == "handy-wohnzimmer-01"


def test_GER_7_neue_id_does_not_collide_with_existing(tmp_path):
    """Eine neu vergebene `id` kollidiert nie mit einer bestehenden — auch
    dann nicht, wenn `01` schon manuell vergeben wurde."""
    reg = registry_mod.Registry([
        registry_mod.Geraet(
            id="tablet-wohnzimmer-01", typ="tablet", name="A",
            aufloesung={"w": 1, "h": 1}, os="linux",
            verwendung="display", status="aktiv"),
        registry_mod.Geraet(
            id="tablet-wohnzimmer-03", typ="tablet", name="C",
            aufloesung={"w": 1, "h": 1}, os="linux",
            verwendung="display", status="aktiv"),
    ])
    # Erwartet: 02 wird als nächste freie Nummer vergeben (Lücke füllen).
    nid = registry_mod.neue_id(reg, "tablet", "Wohnzimmer")
    assert nid == "tablet-wohnzimmer-02"


def test_GER_7_neue_id_skips_inactive_ids_too(tmp_path):
    """Eine einmal vergebene `id` wird nicht neu vergeben — auch nicht für
    inaktive Geräte. Identität ist stabil (URL-8 sinngemäß)."""
    reg = registry_mod.Registry([
        registry_mod.Geraet(
            id="tablet-wohnzimmer-01", typ="tablet", name="A",
            aufloesung={"w": 1, "h": 1}, os="linux",
            verwendung="display", status="inaktiv"),
    ])
    nid = registry_mod.neue_id(reg, "tablet", "Wohnzimmer")
    assert nid != "tablet-wohnzimmer-01"
    assert nid == "tablet-wohnzimmer-02"


def test_GER_7_add_rejects_duplicate_id():
    """add() lehnt eine bereits vergebene `id` ab — GER-7-Garantie auch
    gegen einen Bug im Aufrufer."""
    reg = registry_mod.Registry([
        registry_mod.Geraet(
            id="tablet-test-01", typ="tablet", name="A",
            aufloesung={"w": 1, "h": 1}, os="linux",
            verwendung="display", status="aktiv")])
    with pytest.raises(registry_mod.RegistryError):
        reg.add(registry_mod.Geraet(
            id="tablet-test-01", typ="tablet", name="A2",
            aufloesung={"w": 1, "h": 1}, os="linux",
            verwendung="display", status="aktiv"))


def test_GER_7_load_rejects_id_schema_violation(tmp_path):
    """Eine `id`, die das GER-7-Schema verletzt, ist ein Datei-Fehler."""
    bad = tmp_path / "geraete.json"
    bad.write_text(json.dumps({"geraete": [{
        "id": "TabletOhneSchema", "typ": "tablet", "name": "X",
        "aufloesung": {"w": 1, "h": 1}, "os": "linux",
        "verwendung": "display", "status": "aktiv"}]}))
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


def test_GER_7_load_rejects_id_prefix_typ_mismatch(tmp_path):
    """Der `<typ>`-Präfix der id muss zum `typ`-Feld passen — sonst lügt die id."""
    bad = tmp_path / "geraete.json"
    bad.write_text(json.dumps({"geraete": [{
        "id": "tablet-x-01", "typ": "handy", "name": "X",
        "aufloesung": {"w": 1, "h": 1}, "os": "ios",
        "verwendung": "controller", "status": "aktiv"}]}))
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


def test_GER_7_load_rejects_duplicate_ids(tmp_path):
    """Zwei Geräte mit derselben `id` in der Datei: Fehler."""
    bad = tmp_path / "geraete.json"
    bad.write_text(json.dumps({"geraete": [
        {"id": "tablet-x-01", "typ": "tablet", "name": "A",
         "aufloesung": {"w": 1, "h": 1}, "os": "linux",
         "verwendung": "display", "status": "aktiv"},
        {"id": "tablet-x-01", "typ": "tablet", "name": "B",
         "aufloesung": {"w": 1, "h": 1}, "os": "linux",
         "verwendung": "display", "status": "aktiv"},
    ]}))
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


# ============================================================
#  GER-8 — Konsumenten (Doku-only, kein Code-Verhalten)
# ============================================================
#
# GER-8 nennt nur die heutigen Konsumenten (Router, Display-Client,
# CA-Verteilung) — die Anbindung läuft in eigenen Tickets (#106 GAA,
# #82 CA-Anleitung). In V1 dieser Lieferung kein Code-Verhalten, also
# kein Test. Markiert mit einem Smoke-Test, dass die Public-API existiert,
# die diese Konsumenten brauchen werden.

def test_GER_8_public_api_is_importable_for_consumers():
    """Konsumenten importieren NUR aus `geraete` (Paket-Public-API)."""
    import geraete as g
    # Lese-Schnittstelle (Router/Display-Client).
    assert hasattr(g, "load")
    assert hasattr(g, "Registry")
    # Schreib-Schnittstelle (GAA, manuelle Pflege).
    assert hasattr(g, "save")
    assert hasattr(g, "neue_id")
    # Wert-Mengen für CA-Verteilung (OS-basiert).
    assert hasattr(g, "OS_WERTE")


# ============================================================
#  GER-9 — Konfigurationswerte
# ============================================================
#
# GER-9 hält nur EINEN konfigurierbaren Wert vor: den Pfad zur Registry-
# Datei selbst, per Env/CLI. In V1 dieser Lieferung gibt es keinen
# Entrypoint, der ENV/CLI parst (kommt mit den Konsumenten-Tickets). Wir
# belegen GER-9 hier durch: load() akzeptiert einen freien Pfad — der
# Aufrufer entscheidet, woher er ihn nimmt.

def test_GER_9_load_accepts_arbitrary_path(tmp_path):
    """load(path) nimmt einen beliebigen Pfad — Konsument liefert ENV/CLI."""
    p = tmp_path / "irgendwo" / "anders" / "g.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"geraete": []}), encoding="utf-8")
    reg = registry_mod.load(str(p))
    assert reg.list_all() == []


# ============================================================
#  GER-10 — Automatisierte Tests je Anforderung
# ============================================================

def test_GER_10_every_requirement_has_a_test():
    """GER-10: jede GER-ID 1..9 hat mindestens einen Test in diesem Modul."""
    quelle = open(os.path.abspath(__file__), encoding="utf-8").read()
    for ger in range(1, 10):
        assert "def test_GER_%d_" % ger in quelle, "GER-%d ungetestet" % ger


# ============================================================
#  OD3 / T948 — paired_at round-trip-treu (optionales Feld)
# ============================================================
#
# Der Pairing-Endpoint /auth/pair (seiten/main.py::_markiere_paired_at)
# stempelt `paired_at` (ISO-8601) additiv in geraete.json. Kennt die Registry
# das Feld nicht, DROPPT der nächste geraete-Write (GER-15 add/save) es für
# ALLE Einträge. Diese Tests belegen die Round-Trip-Treue.

_PAIRED_STAMP = "2026-07-06T09:15:00+00:00"


def _geraete_mit_paired_at():
    """DEMO_GERAETE, aber das erste Gerät trägt einen paired_at-Stempel —
    genau die Form, die /auth/pair schreibt (Stempel als letzter Schlüssel)."""
    import copy
    data = copy.deepcopy(DEMO_GERAETE)
    data["geraete"][0]["paired_at"] = _PAIRED_STAMP
    return data


def test_OD3_paired_at_survives_load_save_roundtrip(tmp_path):
    """Kern-AC: geraete.json MIT paired_at laden, save aufrufen, neu laden —
    der Stempel überlebt, die übrigen Felder bleiben unberührt."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(_geraete_mit_paired_at()), encoding="utf-8")

    reg = registry_mod.load(str(p))
    assert reg.get("tablet-elias-01").paired_at == _PAIRED_STAMP
    assert reg.get("tablet-elias-01").to_dict()["paired_at"] == _PAIRED_STAMP

    registry_mod.save(reg, str(p))

    reg2 = registry_mod.load(str(p))
    assert reg2.get("tablet-elias-01").paired_at == _PAIRED_STAMP, \
        "paired_at wurde beim save gedroppt (OD3-Regression)"
    # Übrige Felder unberührt.
    g = reg2.get("tablet-elias-01").to_dict()
    assert g["name"] == "Tablet Elias"
    assert g["status"] == "aktiv"


def test_OD3_paired_at_survives_add_of_another_geraet(tmp_path):
    """Der reale GER-15-Pfad (geraete/main.py post_geraet): load → add(neues
    Gerät) → save. Das bereits gepaarte Gerät behält seinen Stempel — der neue
    Eintrag hat keinen (nie gepaart)."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(_geraete_mit_paired_at()), encoding="utf-8")

    reg = registry_mod.load(str(p))
    reg.add(registry_mod.Geraet(
        id="monitor-buero-01", typ="monitor", name="Monitor Büro",
        aufloesung={"w": 3840, "h": 2160}, os="linux",
        verwendung="display", status="aktiv"))
    registry_mod.save(reg, str(p))

    roh = json.loads(p.read_text(encoding="utf-8"))
    paired = next(g for g in roh["geraete"] if g["id"] == "tablet-elias-01")
    neu = next(g for g in roh["geraete"] if g["id"] == "monitor-buero-01")
    assert paired["paired_at"] == _PAIRED_STAMP
    assert "paired_at" not in neu, \
        "neu angelegtes Gerät darf kein null/leeres paired_at bekommen"


def test_OD3_paired_at_survives_update(tmp_path):
    """update() eines anderen Feldes am gepaarten Gerät lässt paired_at
    unberührt (to_dict → _validate_dict → to_dict round-trip)."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(_geraete_mit_paired_at()), encoding="utf-8")

    reg = registry_mod.load(str(p))
    reg.update("tablet-elias-01", status="inaktiv")
    assert reg.get("tablet-elias-01").paired_at == _PAIRED_STAMP
    assert reg.get("tablet-elias-01").is_aktiv() is False


def test_OD3_paired_at_optional_fehlend_ist_ok(tmp_path):
    """paired_at ist OPTIONAL: eine geraete.json OHNE das Feld lädt weiter
    fehlerfrei, und to_dict trägt dann KEIN paired_at (kein null-Feld,
    byte-stabile Diffs für nie gepaarte Geräte)."""
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps(DEMO_GERAETE), encoding="utf-8")  # ohne paired_at

    reg = registry_mod.load(str(p))
    g = reg.get("tablet-elias-01")
    assert g.paired_at is None
    assert "paired_at" not in g.to_dict()


def test_OD3_paired_at_leer_oder_falscher_typ_ist_dateifehler(tmp_path):
    """Vorhandenes paired_at muss ein nicht-leerer String sein — leerer String
    oder falscher Typ ist ein Datei-Fehler (RegistryError), analog zur strengen
    Pflichtfeld-Behandlung. Fehlend bleibt separat davon erlaubt (Test oben)."""
    for kaputt in ("", 12345, {"x": 1}):
        import copy
        data = copy.deepcopy(DEMO_GERAETE)
        data["geraete"][0]["paired_at"] = kaputt
        p = tmp_path / "geraete.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(registry_mod.RegistryError):
            registry_mod.load(str(p))
