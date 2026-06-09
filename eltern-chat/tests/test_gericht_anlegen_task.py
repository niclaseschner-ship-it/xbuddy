"""Tests für GerichtAnlegenTask — GAN-7, AC3/AC4/AC5 (Refs #503).

Pflicht-Tests (Spec GAN-7 + AC aus Contract T503-S1):
- Katalog enthält 'gericht_anlegen' genau dann, wenn essen_origin_url
  UND icon_origin_url UND family_group_chat_id_getter gesetzt sind (Guard, AC5).
- GerichtAnlegenTask ist ein WriteTask (EC-10).
- Task-Name ist 'gericht_anlegen'.
- propose() liefert Proposal mit Label + Icon-ID.
- execute() ruft POST nach Bestätigung.
- propose() schreibt NICHT (E-GAN-2).
- Icon-Suche → Kandidaten → execute mit icon_id (GAN-4/D6-Muster).
- Nicht-Mitglied → kein Schreiben (GAN-2).
- Buddy-409 → ehrliche Grenze-Quittung (GAN-5).
"""

import contextlib
import json
import os
import tempfile

from fakes import FakeTelegram
from skills.essen_client import EssenClientError
from skills.gericht_anlegen import (
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
)
from skills.gericht_anlegen_task import GerichtAnlegenTask
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Doppelungen
# ============================================================

class FakeEssenClient:
    def __init__(self, post_response=None, post_error=None):
        self.post_calls = []
        self._post_response = post_response or {"id": "1"}
        self._post_error = post_error

    def post_gericht(self, name, icon_id):
        self.post_calls.append({"name": name, "icon_id": icon_id})
        if self._post_error is not None:
            raise self._post_error
        return dict(self._post_response)


class FakeIconClient:
    def __init__(self, response=None, error=None):
        self.suche_calls = []
        self._response = response if response is not None else []
        self._error = error

    def suche(self, stichwort, max_treffer=3):
        self.suche_calls.append({
            "stichwort": stichwort, "max_treffer": max_treffer})
        if self._error is not None:
            raise self._error
        return list(self._response)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_task(essen_client=None, icon_client=None, is_member_fn=None):
    return GerichtAnlegenTask(
        tg=FakeTelegram(),
        essen_client=essen_client or FakeEssenClient(),
        icon_client=icon_client or FakeIconClient(),
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=is_member_fn or _immer_mitglied,
    )


# ============================================================
#  Task-Klassifikation + Grundeigenschaften
# ============================================================

def test_GAN7_ist_write_task():
    """GAN-7: GerichtAnlegenTask ist ein WriteTask (EC-10)."""
    assert isinstance(_make_task(), WriteTask)


def test_GAN7_name():
    """GAN-7: Task-Name ist 'gericht_anlegen' (Catalog-Schlüssel)."""
    assert _make_task().name == "gericht_anlegen"


def test_GAN7_ist_sync():
    """GAN-7: is_async=False — V1 synchron (analog RPS-7), kein Worker."""
    assert _make_task().is_async is False


def test_GAN7_keine_post_execute_hooks():
    """GAN-7: keine Hooks (Essens-Buddy hat Reload-on-Read, ESSEN-20)."""
    assert _make_task().post_execute_hooks == ()


# ============================================================
#  propose() — E-GAN-2 / GAN-5
# ============================================================

def test_E_GAN2_propose_liefert_konkreten_vorschlag():
    """E-GAN-2 / GAN-5: propose nennt Label + Icon-ID (Ein-Schritt-Vorschlag)."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)
    proposal = task.propose({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }, ctx)
    assert isinstance(proposal, Proposal)
    assert "Lasagne" in proposal.summary
    assert "9999" in proposal.summary


def test_E_GAN2_propose_icon_suchen_lesend():
    """E-GAN-2: propose für icon_suchen nennt 'nur lesend, nichts schreiben'."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)
    proposal = task.propose({
        "aktion": AKTION_ICON_SUCHEN,
        "icon_stichwort": "Lasagne",
    }, ctx)
    assert isinstance(proposal, Proposal)
    # Soll deutlich machen, dass kein Schreiben passiert
    assert "lesend" in proposal.summary.lower() or "schreib" in proposal.summary.lower()


# ============================================================
#  execute(): vollständige Kette propose → execute → POST
# ============================================================

def test_VS_propose_schreibt_nicht():
    """E-GAN-2: propose() schreibt NICHTS (Vorschlag-Phase, kein Effekt)."""
    ec = FakeEssenClient(post_response={"id": "1"})
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    args = {
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }

    task.propose(args, ctx)

    assert ec.post_calls == [], "propose schreibt NICHTS (E-GAN-2)"


def test_VS_execute_ruft_post():
    """GAN-3: execute() ruft POST /api/v1/essen/katalog/gerichte."""
    ec = FakeEssenClient(post_response={"id": "42"})
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    args = {
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }

    quittung = task.execute(args, ctx)

    assert ec.post_calls == [{"name": "Lasagne", "icon_id": "9999"}]
    # Quittung enthält die ID (D6-Muster)
    assert "42" in quittung


def test_VS_icon_suchen_execute_liefert_kandidaten_ids():
    """GAN-4: execute(icon_suchen) → ICONS-7-Aufruf; Quittung enthält
    die Vorschlags-IDs (D6 — zweiter tool_use nutzt sie als icon_id)."""
    ic = FakeIconClient(response=[
        {"id": 1111, "url": "/x"},
        {"id": 2222, "url": "/y"},
    ])
    task = _make_task(icon_client=ic)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.execute({
        "aktion": AKTION_ICON_SUCHEN,
        "icon_stichwort": "Lasagne",
    }, ctx)

    assert ic.suche_calls == [{"stichwort": "Lasagne", "max_treffer": 3}]
    assert "1111" in quittung
    assert "2222" in quittung


def test_VS_nicht_mitglied_execute_kein_post():
    """GAN-2: Nicht-Mitglied → execute schreibt NICHT."""
    ec = FakeEssenClient()
    task = _make_task(essen_client=ec, is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=99)

    quittung = task.execute({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }, ctx)

    assert ec.post_calls == []
    assert "Familien-Gruppe" in quittung or "Mitglied" in quittung


def test_VS_buddy_409_grenze_quittung():
    """GAN-5: Buddy-409 → Quittung enthält ehrliche Grenz-Meldung."""
    ec = FakeEssenClient(
        post_error=EssenClientError(
            "Essens-Buddy: HTTP 409 bei POST /api/v1/essen/katalog/gerichte "
            "— Gericht existiert bereits"))
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.execute({
        "aktion": AKTION_HINZUFUEGEN,
        "label": "Lasagne",
        "icon_id": "9999",
    }, ctx)

    assert len(ec.post_calls) == 1
    # Quittung nennt die Ablehnung
    assert "abgelehnt" in quittung.lower() or "409" in quittung or "bereits" in quittung


def test_VS_keine_icons_quittung():
    """GAN-4: Icon-Suche ohne Treffer → Quittung fragt nach anderem Wort."""
    ic = FakeIconClient(response=[])
    task = _make_task(icon_client=ic)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.execute({
        "aktion": AKTION_ICON_SUCHEN,
        "icon_stichwort": "GlubschaugenGericht",
    }, ctx)

    assert "gefunden" in quittung.lower() or "anderes" in quittung.lower()


# ============================================================
#  Catalog-Registrierung (AND-Guard, GAN-7) — DREI Origins
# ============================================================

def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_GAN7_guard_alle_drei_gesetzt_registriert():
    """GAN-7 / AC5: Task erscheint im Katalog genau dann, wenn
    essen_origin_url UND icon_origin_url UND family_group_chat_id_getter
    gesetzt sind."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("gericht_anlegen")
        assert task is not None
        assert isinstance(task, WriteTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_ohne_essen_origin_nicht_registriert():
    """GAN-7 Guard: ohne essen_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            icon_origin_url="http://127.0.0.1:5000",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("gericht_anlegen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_ohne_icon_origin_nicht_registriert():
    """GAN-7 Guard: ohne icon_origin_url → keine Registrierung
    (E-GAN-3 — der Skill braucht die zentrale Icon-Suche)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("gericht_anlegen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_ohne_fgcid_nicht_registriert():
    """GAN-7 Guard: ohne family_group_chat_id_getter → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            icon_origin_url="http://127.0.0.1:5000",
        )
        assert catalog.get("gericht_anlegen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_GAN7_guard_build_catalog_signatur_kompatibel():
    """GAN-7 / additiv: build_catalog(tg, ca_pem_path) bleibt
    rückwärtskompatibel — essen_origin_url ist optional (Default None)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(tg=FakeTelegram(), ca_pem_path=ca)
        assert catalog.get("gericht_anlegen") is None
        assert catalog.get("ca_verteilen") is not None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Entry-Path-Test: Catalog → Task → Transport-Stub (AC3)
# ============================================================

def test_VS_entry_path_catalog_to_post_via_transport_stub():
    """Entry-Path-Probe (AC_ENTRY): build_catalog → Task → POST über den
    echten EssenClient mit Transport-Stub (CLIENT-1) — die Kette aus
    Routing + Skill + Client + Transport ist hookbar (GAN-7)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(members={7: {"status": "member"}}),
            ca_pem_path=ca,
            essen_origin_url="http://example",
            icon_origin_url="http://example",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("gericht_anlegen")
        assert isinstance(task, GerichtAnlegenTask)

        # Transport-Stub in den EssenClient einsetzen.
        post_calls = []
        def transport(method, path, *, body=None, content_type=None):
            post_calls.append({"method": method, "path": path, "body": body})
            return 201, json.dumps({"id": "1"}).encode("utf-8")
        task._essen_client._transport = transport

        ctx = TurnContext(chat_id=200, from_user_id=7, private_chat_id=7)
        task.execute({
            "aktion": AKTION_HINZUFUEGEN,
            "label": "Lasagne",
            "icon_id": "9999",
        }, ctx)

        assert len(post_calls) == 1
        assert post_calls[0]["method"] == "POST"
        assert post_calls[0]["path"] == "/api/v1/essen/katalog/gerichte"
        payload = json.loads(post_calls[0]["body"].decode("utf-8"))
        assert payload == {"label": "Lasagne", "bild_ref": "9999"}
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)
