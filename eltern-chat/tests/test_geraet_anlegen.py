"""Tests für »Gerät anlegen« — RAT-31 E6c (Refs #106, #215, #1565).

RAT-31 E6c (Nic-Setzung 2026-07-29): die geraete-Registry stirbt. »Gerät
koppeln« mintet nur noch einen Pairing-Link (auth.md AUTH-2.a / GAA-3.8) —
kein Registry-Schreiben, keine Verwendungs-/Rollen-Abfrage. Die Rolle wählt
die Familie beim PWA-Installieren.

Telegram wird durch die FakeTelegram aus `fakes.py` ersetzt (Pattern wie
FAA-11 / ONB-9).
"""

from __future__ import annotations

from fakes import FakeTelegram
from skills.geraet_anlegen import (
    NOT_AUTHORIZED,
    PAIRING_SETUP_FEHLT,
    geraet_anlegen,
)

from tools.initdata import session_cookie as sc

BOT_TOKEN = "123456:ABCdef_testtoken"
ORIGIN = "https://buddyboard.<tailscale-id>.ts.net"


def _member_tg():
    return FakeTelegram(members={7: {"status": "member"}})


def _nonmember_tg():
    return FakeTelegram(members={})


def _sent_texte(tg):
    return [m["text"] for m in tg.sent]


def _pairing_texte(tg):
    return [t for t in _sent_texte(tg) if "/auth/pair?token=" in t]


# ------------------------------------------------------------------
#  GAA-2: Berechtigung
# ------------------------------------------------------------------

def test_nicht_mitglied_wird_abgewiesen_ohne_link():
    tg = _nonmember_tg()
    res = geraet_anlegen(
        tg, 42, 7, -100,
        pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN)
    assert res.authorized is False
    assert res.pairing_links == []
    assert _sent_texte(tg) == [NOT_AUTHORIZED]
    assert _pairing_texte(tg) == []


# ------------------------------------------------------------------
#  RAT-31 E6c: reines Link-Minten
# ------------------------------------------------------------------

def test_mitglied_bekommt_pairing_link_mit_gueltigem_token():
    tg = _member_tg()
    res = geraet_anlegen(
        tg, 42, 7, -100,
        pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN)
    assert res.authorized is True
    assert len(res.pairing_links) == 1

    treffer = _pairing_texte(tg)
    assert len(treffer) == 1, "genau ein Pairing-Link erwartet"
    text = treffer[0]
    assert ORIGIN + "/auth/pair?token=" in text
    assert "15 Minuten" in text
    # Anweisung nennt die Rollenwahl beim Installieren (kein Server-Redirect).
    assert "Kinder-Display" in text and "Elterngerät" in text

    # Token extrahieren und stateless verifizieren → gültiges Subjekt.
    token = text.split("/auth/pair?token=", 1)[1].split()[0].strip()
    assert sc.verify_pairing(token, BOT_TOKEN) is not None


def test_falscher_bot_token_verifiziert_nicht():
    tg = _member_tg()
    geraet_anlegen(
        tg, 42, 7, -100,
        pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN)
    token = _pairing_texte(tg)[0].split(
        "/auth/pair?token=", 1)[1].split()[0].strip()
    # Mit einem anderen Sign-Key schlägt die Verifikation fehl (HMAC-Bindung).
    assert sc.verify_pairing(token, "anderer-token") is None


def test_jeder_aufruf_mintet_frisches_subjekt():
    tg = _member_tg()
    geraet_anlegen(tg, 42, 7, -100,
                   pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN)
    geraet_anlegen(tg, 42, 7, -100,
                   pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN)
    tokens = [t.split("/auth/pair?token=", 1)[1].split()[0].strip()
              for t in _pairing_texte(tg)]
    assert len(tokens) == 2
    # Kein Registry-Subjekt mehr → zwei distinkte Tokens (frisches Subjekt).
    assert tokens[0] != tokens[1]


def test_ohne_pairing_setup_kein_link_aber_hinweis():
    tg = _member_tg()
    res = geraet_anlegen(tg, 42, 7, -100)  # keine Pairing-Params
    assert res.authorized is True
    assert res.pairing_links == []
    assert _pairing_texte(tg) == []
    assert _sent_texte(tg) == [PAIRING_SETUP_FEHLT]
