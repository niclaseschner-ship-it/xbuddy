"""Dual-Gate-Pruefung fuer die AUTH-7b-Renderer-Routen (auth.md AUTH-7).

Die 7b-Routen (Shell-/Display-Renderer, `/shell/<panel_id>`,
`/display/<display_id>`, `/controller/*`, `/api/v1/displays/<id>/events`)
pruefen **beide** Quellen additiv (auth.md AUTH-7:495-504, „Dual-Gate"):

  - **Cookie** — ein valider `xbuddy_session`-Cookie (AUTH-2) deckt die
    User-Geraete (Eltern-Handy/-Tablet ueber den Funnel).
  - **Operator-IP** — die Quell-IP liegt in der 7a-Operator-Allowlist
    (auth.md AUTH-7:461: `192.168.0.0/16`, `10.0.0.0/8`, `100.64.0.0/10`),
    das deckt den cookie-losen headless Pi-Kiosk im Heim-LAN/Tailnet.

Berechtigt ist, wer **eine** der beiden Quellen hat; nur wer keins von beiden
mitbringt (fremder Funnel-Client ohne Cookie), wird `401` (AUTH-8).

Vendor-Adapter-Disziplin (RAT-16) wie `session_cookie.py` / `init_data.py`:
nur Standard-Python, **kein** Flask-Import. Zwei PURE Funktionen; das
Request-Objekt (Cookie-Wert, Client-IP) liefert der Service-Decorator. Wohnort
neben `session_cookie.py` unter `tools/initdata/`, damit Services aus `tools/`
importieren (MOD-4 / MOD-6).
"""

from __future__ import annotations

import ipaddress

from tools.initdata import session_cookie

# ---------------------------------------------------------------------------
# Operator-IP-Allowlist (auth.md AUTH-7:461 / 7a — WOERTLICH)
# ---------------------------------------------------------------------------
#
# Heim-LAN + Tailnet-CIDRs, aus denen der headless Operator-Pi die
# Renderer-Routen ohne Cookie erreichen darf.
_OPERATOR_CIDRS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("192.168.0.0/16", "10.0.0.0/8", "100.64.0.0/10")
)


def ist_operator_ip(client_ip: str | None) -> bool:
    """True, wenn `client_ip` in der 7a-Operator-Allowlist liegt (auth.md AUTH-7).

    Fehlende/leere/unparsbare Adresse → False (keine Quelle). Nur echte
    IPv4-Adressen aus den drei Heim-/Tailnet-CIDRs zaehlen als Operator.
    """
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip.strip())
    except ValueError:
        return False
    return any(addr in netz for netz in _OPERATOR_CIDRS)


def hat_gueltigen_cookie(cookie_value: str | None, bot_token: str) -> bool:
    """True, wenn `cookie_value` ein valider `xbuddy_session`-Cookie ist (AUTH-2).

    Duenner Wrapper ueber `session_cookie.verify_session` — die HMAC-Mechanik
    und Ablaufpruefung leben dort (kein zweites Geheimnis). Fehlender/leerer
    Cookie oder Bot-Token → False.
    """
    return session_cookie.verify_session(cookie_value, bot_token) is not None
