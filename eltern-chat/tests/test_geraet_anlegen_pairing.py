"""GAA-3.8 — Pairing-Link-Schritt der »Gerät anlegen«-Funktion (T948, AC4).

Prüft, dass `geraet_anlegen` nach erfolgreicher Registry-Anlage (GAA-3.7) einen
Pairing-Link postet (auth.md AUTH-2.a / geraet-anlegen.md GAA-3.8):
  - mit `pairing_bot_token` + `pairing_origin`: Anweisung mit
    `<origin>/auth/pair?token=<X>` wird gepostet; der Token verifiziert
    stateless gegen die Lib und kodiert die vergebene display_id.
  - ohne Pairing-Setup: KEIN Pairing-Link (Backward-Compat / Agnostik).

Wiederverwendung der Test-Doppelungen aus test_geraet_anlegen.py.
"""

from __future__ import annotations

from fakes import FakeTelegram
from skills.geraet_anlegen import geraet_anlegen
from test_geraet_anlegen import FakeGeraeteClient, stream

from tools.initdata import session_cookie as sc

BOT_TOKEN = "123456:ABCdef_testtoken"
ORIGIN = "https://buddyboard.taile235cf.ts.net"


def _member_tg():
    return FakeTelegram(members={7: {"status": "member"}})


def _vollanlage_tablet():
    return ["tablet", "Elias", "1280x800", "android", "display", "ok"]


def _pairing_texte(tg):
    return [m["text"] for m in tg.sent if "/auth/pair?token=" in m["text"]]


def test_gaa38_postet_pairing_link_mit_gueltigem_token():
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_tablet(), "nein")

    res = geraet_anlegen(
        tg, 42, 7, -100, client, next_msg,
        pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN,
    )
    assert res.vergebene_display_ids == ["tablet-elias-01"]

    treffer = _pairing_texte(tg)
    assert len(treffer) == 1, "genau ein Pairing-Link erwartet"
    text = treffer[0]
    assert ORIGIN + "/auth/pair?token=" in text
    assert "15 Minuten" in text

    # Token extrahieren und stateless verifizieren → kodiert die display_id.
    token = text.split("/auth/pair?token=", 1)[1].split()[0].strip()
    assert sc.verify_pairing(token, BOT_TOKEN) == "tablet-elias-01"


def test_gaa38_ohne_setup_kein_pairing_link():
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_tablet(), "nein")

    geraet_anlegen(tg, 42, 7, -100, client, next_msg)  # keine Pairing-Params
    assert _pairing_texte(tg) == [], "ohne Setup darf kein Pairing-Link kommen"


def test_gaa38_falscher_bot_token_verifiziert_nicht():
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_tablet(), "nein")

    geraet_anlegen(
        tg, 42, 7, -100, client, next_msg,
        pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN,
    )
    token = _pairing_texte(tg)[0].split("/auth/pair?token=", 1)[1].split()[0].strip()
    # Mit einem anderen Sign-Key schlägt die Verifikation fehl (HMAC-Bindung).
    assert sc.verify_pairing(token, "anderer-token") is None
