"""Tests für die icon_album-Migration des RoutinePunkteSetzenTask — TASK-10b,
RPS-4, AC1 … AC5 des T626-Contracts.

Schwerpunkt: execute()-Pfad bei aktion='icon_suchen' sendet das Album per
icon_album.zeige_kandidaten UND liefert die Mapping-Quittung
'1 = <id>, 2 = <id>, …' im Tool-Result.

Alle anderen Pfade (HINZUFUEGEN/EINMALIG/LOESCHEN/NEU_ORDNEN) werden durch
AC5 abgedeckt — die bestehenden Tests in test_routine_punkte_setzen.py
laufen weiterhin grün.
"""

import contextlib
import os
import tempfile
import unittest.mock as mock

from fakes import FakeTelegram
from skills.routine_punkte_setzen import (
    AKTION_ICON_SUCHEN,
    AKTION_LISTE,
    AKTION_NEU_ORDNEN,
    SIGNAL_ICON_KANDIDATEN,
)
from skills.routine_punkte_setzen_task import RoutinePunkteSetzenTask
from tasks import Proposal, TurnContext, build_catalog

# ============================================================
#  Test-Helfer
# ============================================================

class FakeTelegramMitAlbum(FakeTelegram):
    """FakeTelegram mit send_photo + send_media_group für icon_album-Tests.

    send_photo-Aufrufe landen in `photos`, send_media_group-Aufrufe
    in `media_groups` — jeweils mit allen Argumenten, damit Tests die
    Reihenfolge und Anzahl prüfen können.
    """

    def __init__(self, **kw):
        super().__init__(**kw)
        self.photos = []          # [{chat_id, file_name, file_bytes, caption}]
        self.media_groups = []    # [{chat_id, items}]

    def send_photo(self, chat_id, file_name, file_bytes, caption=None):
        self.photos.append({
            "chat_id": chat_id,
            "file_name": file_name,
            "file_bytes": file_bytes,
            "caption": caption,
        })
        return {"message_id": 9000 + len(self.photos)}

    def send_media_group(self, chat_id, items):
        self.media_groups.append({"chat_id": chat_id, "items": list(items)})
        return [{"message_id": 9100 + i} for i in range(len(items))]


class FakeIconClient:
    """ICONS-7-Doppelung — analog test_routine_punkte_setzen.py."""

    def __init__(self, response=None, error=None):
        self.suche_calls = []
        self._response = response if response is not None else []
        self._error = error

    def suche(self, stichwort, max_treffer=3):
        self.suche_calls.append({"stichwort": stichwort, "max_treffer": max_treffer})
        if self._error is not None:
            raise self._error
        return list(self._response)


class FakeRoutineClient:
    """Minimal-Doppelung des RoutineClients — AC5 (andere Pfade unangetastet)."""

    def __init__(self):
        self.add_calls = []

    def add_item(self, quelle, label, piktogramm):
        self.add_calls.append({"quelle": quelle, "label": label,
                               "piktogramm": piktogramm})
        return {"id": "test-id"}

    def delete_item(self, item_id):
        return {"id": item_id}

    def replace_default_items(self, items):
        return {"count": len(items)}



def _make_task(icon_client=None, tg=None, icon_origin_url="http://icons.test"):
    return RoutinePunkteSetzenTask(
        tg=tg or FakeTelegramMitAlbum(),
        routine_client=FakeRoutineClient(),
        icon_client=icon_client or FakeIconClient(),
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=lambda uid: True,
        icon_origin_url=icon_origin_url,
    )


def _ctx(chat_id=42):
    return TurnContext(chat_id=chat_id, from_user_id=7, private_chat_id=42)


# ============================================================
#  AC1 + AC2: Mapping-Quittung + Album-Senden (drei Kandidaten)
# ============================================================

def test_AC1_quittung_traegt_mapping_form_drei_kandidaten():
    """AC1: Quittung trägt Mapping-Form '1 = <id>, 2 = <id>, 3 = <id>'
    für drei Kandidaten (TASK-10b, RPS-4)."""
    kandidaten = [
        {"id": 2349, "url": "/icons/2349.png"},
        {"id": 8800, "url": "/icons/8800.png"},
        {"id": 7777, "url": "/icons/7777.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://icons.test")

    # icon_album._holen mocken, damit kein Netz nötig.
    with mock.patch("skills.icon_album._holen",
                    side_effect=lambda url, opener=None: b"fakepng"):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Zähne",
        }, _ctx())

    # Mapping-Form: 1 = 2349, 2 = 8800, 3 = 7777
    assert "1 = 2349" in quittung
    assert "2 = 8800" in quittung
    assert "3 = 7777" in quittung
    assert "Piktogramm-Kandidaten als Bilder geschickt" in quittung
    assert "Antworte mit der ID" in quittung


def test_AC2_album_helper_wird_vor_quittung_aufgerufen():
    """AC2: icon_album.zeige_kandidaten wird aufgerufen (TASK-10b); die
    Quittung trägt das Mapping. Mock/Spy auf zeige_kandidaten."""
    kandidaten = [
        {"id": 2349, "url": "/icons/2349.png"},
        {"id": 8800, "url": "/icons/8800.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://icons.test")

    call_args = []

    def fake_zeige(tg_arg, chat_id_arg, kand_arg, origin_arg):
        call_args.append({
            "chat_id": chat_id_arg,
            "kandidaten": kand_arg,
            "origin": origin_arg,
        })

    with mock.patch("skills.routine_punkte_setzen_task.icon_album"
                    ".zeige_kandidaten", side_effect=fake_zeige):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Hund",
        }, _ctx(chat_id=42))

    assert len(call_args) == 1, "zeige_kandidaten genau einmal aufgerufen"
    assert call_args[0]["chat_id"] == 42
    assert call_args[0]["origin"] == "http://icons.test"
    assert len(call_args[0]["kandidaten"]) == 2

    # Quittung trägt Mapping
    assert "1 = 2349" in quittung
    assert "2 = 8800" in quittung


def test_AC2_album_helper_argumente_korrekt():
    """AC2: zeige_kandidaten erhält tg, chat_id, kandidaten UND icon_origin_url
    in der richtigen Reihenfolge (TASK-10b Signatur-Prüfung)."""
    kandidaten = [{"id": 111, "url": "/a.png"}, {"id": 222, "url": "/b.png"}]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg,
                      icon_origin_url="http://origin.test:5000")

    received = {}

    def spy(tg_arg, chat_id_arg, kand_arg, origin_arg):
        received["tg"] = tg_arg
        received["chat_id"] = chat_id_arg
        received["kandidaten"] = kand_arg
        received["origin"] = origin_arg

    with mock.patch("skills.routine_punkte_setzen_task.icon_album"
                    ".zeige_kandidaten", side_effect=spy):
        task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Tier",
        }, _ctx(chat_id=99))

    assert received["tg"] is tg
    assert received["chat_id"] == 99
    assert received["kandidaten"] == kandidaten
    assert received["origin"] == "http://origin.test:5000"


# ============================================================
#  AC1: Ein Kandidat — Mapping '1 = <id>'
# ============================================================

def test_AC1_ein_kandidat_mapping_und_send_photo():
    """AC1 + AC2: 1 Kandidat → Mapping '1 = <id>', send_photo wird aufgerufen.

    end-to-end durch den echten Helper mit FakeTelegramMitAlbum +
    FakeOpener (kein Netz).
    """
    kandidaten = [{"id": 5555, "url": "/icons/5555.png"}]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://ico.test")

    with mock.patch("skills.icon_album._holen",
                    return_value=b"fakepng"):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Hut",
        }, _ctx())

    # Genau ein send_photo, kein send_media_group
    assert len(tg.photos) == 1
    assert tg.media_groups == []
    assert tg.photos[0]["chat_id"] == 42
    assert tg.photos[0]["caption"] is None  # TASK-10b: keine Caption
    assert "1 = 5555" in quittung


def test_AC1_drei_kandidaten_send_media_group():
    """AC1 + AC2: 3 Kandidaten → send_media_group (end-to-end, FakeTG +
    _holen-Mock)."""
    kandidaten = [
        {"id": 1, "url": "/a.png"},
        {"id": 2, "url": "/b.png"},
        {"id": 3, "url": "/c.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg, icon_origin_url="http://ico.test")

    with mock.patch("skills.icon_album._holen",
                    return_value=b"fakepng"):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Schule",
        }, _ctx())

    # send_media_group mit 3 Items
    assert tg.photos == []
    assert len(tg.media_groups) == 1
    grp = tg.media_groups[0]
    assert grp["chat_id"] == 42
    assert len(grp["items"]) == 3
    # Captions sind alle None (TASK-10b)
    for _fname, _fbytes, fcaption in grp["items"]:
        assert fcaption is None

    # Mapping in Quittung
    assert "1 = 1" in quittung
    assert "2 = 2" in quittung
    assert "3 = 3" in quittung


# ============================================================
#  Fehlerfall: IconAlbumError → QUITTUNG_NICHT_ERREICHBAR
# ============================================================

def test_album_fehler_liefert_nicht_erreichbar_quittung():
    """RPS-4 / TASK-10b: wenn zeige_kandidaten IconAlbumError wirft,
    gibt execute() die NICHT_ERREICHBAR-Quittung zurück (kein Crash)."""
    from skills.icon_album import IconAlbumError

    kandidaten = [
        {"id": 100, "url": "/x.png"},
        {"id": 200, "url": "/y.png"},
    ]
    ic = FakeIconClient(response=kandidaten)
    tg = FakeTelegramMitAlbum()
    task = _make_task(icon_client=ic, tg=tg)

    with mock.patch("skills.routine_punkte_setzen_task.icon_album"
                    ".zeige_kandidaten",
                    side_effect=IconAlbumError("Netz weg")):
        quittung = task.execute({
            "aktion": AKTION_ICON_SUCHEN,
            "icon_stichwort": "Ball",
        }, _ctx())

    assert "nicht erreichbar" in quittung.lower()


# ============================================================
#  AC3: Konstruktor nimmt icon_origin_url; tasks.py reicht durch
# ============================================================

def test_AC3_konstruktor_speichert_icon_origin_url():
    """AC3: RoutinePunkteSetzenTask-Konstruktor nimmt icon_origin_url
    und macht ihn als _icon_origin_url verfügbar."""
    task = _make_task(icon_origin_url="http://test-origin:5001")
    assert task._icon_origin_url == "http://test-origin:5001"


def test_AC3_konstruktor_ohne_icon_origin_url_ist_leer():
    """AC3: ohne icon_origin_url (Rückwärtskompatibilität) → leerer String."""
    task = RoutinePunkteSetzenTask(
        tg=FakeTelegramMitAlbum(),
        routine_client=FakeRoutineClient(),
        icon_client=FakeIconClient(),
        family_group_chat_id_getter=lambda: 200,
    )
    assert task._icon_origin_url == ""


def test_AC3_build_catalog_reicht_icon_origin_url_durch():
    """AC3: tasks.build_catalog reicht icon_origin_url an den Task durch."""
    fd, pem = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    try:
        catalog = build_catalog(
            tg=FakeTelegramMitAlbum(),
            ca_pem_path=pem,
            routine_origin_url="http://127.0.0.1:5050",
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("routine_punkte_setzen")
        assert task is not None
        assert task._icon_origin_url == "http://127.0.0.1:5000"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(pem)


# ============================================================
#  AC5: Andere Pfade — unangetastet (Smoke-Tests)
# ============================================================

def test_AC5_hinzufuegen_unberuehrt():
    """AC5: HINZUFUEGEN-Pfad bleibt unangetastet — kein Album-Aufruf."""
    tg = FakeTelegramMitAlbum()
    task = _make_task(tg=tg)
    # kein Mock nötig — icon_album.zeige_kandidaten wird hier gar nicht gerufen
    quittung = task.execute({
        "aktion": "hinzufuegen",
        "label": "Frühstück",
        "piktogramm": "123",
    }, _ctx())
    assert tg.photos == []
    assert tg.media_groups == []
    # Quittung gehört zum Hinzufügen-Pfad
    assert "hinzugefügt" in quittung.lower() or "sichtbar" in quittung.lower()


def test_AC5_loeschen_unberuehrt():
    """AC5: LOESCHEN-Pfad bleibt unangetastet — kein Album-Aufruf."""
    tg = FakeTelegramMitAlbum()
    task = _make_task(tg=tg)
    quittung = task.execute({
        "aktion": "loeschen",
        "item_id": "zaehne-putzen",
    }, _ctx())
    assert tg.photos == []
    assert tg.media_groups == []
    assert "entfernt" in quittung or "weg" in quittung


# ============================================================
#  Mapping-Quittung bei leerem kandidaten-Fall (defensiver Fallback)
# ============================================================

def test_mapping_fallback_bei_leer_kandidaten():
    """Defensiver Fallback: wenn das Signal ICON_KANDIDATEN mit leerer Liste
    käme (sollte nicht passieren, aber Sicherheitsnetz), liefert die Quittung
    einen brauchbaren Text statt eines leeren Strings."""
    # Wir bauen das Signal direkt in _quittung_fuer ein, ohne den Skill.
    from skills.routine_punkte_setzen_task import _quittung_fuer

    quittung = _quittung_fuer(
        SIGNAL_ICON_KANDIDATEN,
        {"label": "Test", "kandidaten": []},
        aktion=AKTION_ICON_SUCHEN,
    )
    assert "Test" in quittung
    assert quittung  # nicht leer


# ============================================================
#  V1.2 Task-Tests: aktion=liste + Einzel-Verschieben propose/schema
# ============================================================

class FakeRoutineClientMitListe(FakeRoutineClient):
    """FakeRoutineClient mit get_items()-Unterstützung für V1.2."""

    def __init__(self, get_items_response=None, **kw):
        super().__init__(**kw)
        self._get_items_response = get_items_response or {
            "default": [], "einmalig_heute": []}
        self.get_items_calls = []

    def get_items(self):
        self.get_items_calls.append(True)
        return dict(self._get_items_response)


def _make_task_v12(icon_client=None, tg=None, routine_client=None,
                   icon_origin_url="http://icons.test"):
    return RoutinePunkteSetzenTask(
        tg=tg or FakeTelegramMitAlbum(),
        routine_client=routine_client or FakeRoutineClientMitListe(),
        icon_client=icon_client or FakeIconClient(),
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=lambda uid: True,
        icon_origin_url=icon_origin_url,
    )


def test_V12_propose_liste_liefert_proposal():
    """V1.2: propose(aktion=liste) liefert einen Proposal (WriteTask-Konvention).
    Der Text nennt »nur lesend«."""
    task = _make_task_v12()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({"aktion": AKTION_LISTE}, ctx)
    assert isinstance(proposal, Proposal)
    assert "lesen" in proposal.summary.lower() or "lesend" in proposal.summary.lower()


def test_V12_execute_liste_ruft_get_items():
    """V1.2: task.execute(aktion=liste) ruft get_items() auf."""
    rc = FakeRoutineClientMitListe(get_items_response={
        "default": [{"id": "a", "label": "A", "piktogramm": "1"}],
        "einmalig_heute": [],
    })
    task = _make_task_v12(routine_client=rc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    task.execute({"aktion": AKTION_LISTE}, ctx)
    assert len(rc.get_items_calls) == 1


def test_V12_execute_liste_quittung_enthaelt_dauerhaft():
    """V1.2 AC2: execute(liste) Quittung enthält 'Dauerhaft' + Item-Namen."""
    rc = FakeRoutineClientMitListe(get_items_response={
        "default": [
            {"id": "zaehne-putzen", "label": "Zähne putzen", "piktogramm": "🪥"},
        ],
        "einmalig_heute": [],
    })
    task = _make_task_v12(routine_client=rc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    quittung = task.execute({"aktion": AKTION_LISTE}, ctx)
    assert "Dauerhaft" in quittung
    assert "Zähne putzen" in quittung


def test_V12_propose_einzel_verschieben_nennt_name_und_position():
    """V1.2: propose(neu_ordnen, item_name, ziel_position) nennt den Namen
    und die Ziel-Position (Konversations-UX, Eltern sehen keine IDs)."""
    task = _make_task_v12()
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)
    proposal = task.propose({
        "aktion": AKTION_NEU_ORDNEN,
        "item_name": "Zähne putzen",
        "ziel_position": 1,
    }, ctx)
    assert isinstance(proposal, Proposal)
    assert "Zähne putzen" in proposal.summary
    assert "1" in proposal.summary


def test_V12_schema_enthaelt_liste():
    """V1.2: Task-Schema enthält 'liste' als erlaubte Aktion."""
    task = _make_task_v12()
    enum = task.parameters["properties"]["aktion"]["enum"]
    assert AKTION_LISTE in enum, "Schema muss 'liste' in aktion-enum enthalten"


def test_V12_schema_enthaelt_item_name_und_ziel_position():
    """V1.2: Task-Schema enthält item_name und ziel_position als Properties."""
    task = _make_task_v12()
    props = task.parameters["properties"]
    assert "item_name" in props, "Schema braucht 'item_name'"
    assert "ziel_position" in props, "Schema braucht 'ziel_position'"
    assert props["ziel_position"]["type"] == "integer"


def test_V12_execute_einzel_verschieben_ruft_replace():
    """V1.2 AC3: execute(neu_ordnen, item_name, ziel_position) löst Name auf
    und ruft replace_default_items mit der korrekten Reihenfolge."""
    rc = FakeRoutineClientMitListe(
        get_items_response={
            "default": [
                {"id": "a", "label": "A", "piktogramm": "1"},
                {"id": "b", "label": "B", "piktogramm": "2"},
                {"id": "c", "label": "C", "piktogramm": "3"},
            ],
            "einmalig_heute": [],
        },
    )
    replace_calls = []

    def capture_replace(items):
        replace_calls.append(list(items))
        return {"count": len(items)}

    rc.replace_default_items = capture_replace

    task = _make_task_v12(routine_client=rc)
    ctx = TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)

    task.execute({
        "aktion": AKTION_NEU_ORDNEN,
        "item_name": "C",
        "ziel_position": 1,
    }, ctx)

    assert len(replace_calls) == 1
    neue_liste = replace_calls[0]
    assert neue_liste[0]["id"] == "c", "C muss auf Position 1 stehen"
    assert neue_liste[1]["id"] == "a"
    assert neue_liste[2]["id"] == "b"
