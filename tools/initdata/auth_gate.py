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
die zwei PURE Funktionen `ist_operator_ip` / `hat_gueltigen_cookie` bleiben
Flask-frei — das Request-Objekt (Cookie-Wert, Client-IP) liefert der Aufrufer.
Wohnort neben `session_cookie.py` unter `tools/initdata/`, damit Services aus
`tools/` importieren (MOD-4 / MOD-6).

AUTH-Decorator-Lib (ratifiziert 2026-07-30, #1383, auth.md „AUTH-Decorator-Lib"):
Zusätzlich zu den pure funcs hostet dieses Modul drei **Decorator-Factories**,
die den bislang pro Buddy hand-kopierten Flask-Auth-Wrapper konsolidieren
(n=3-Lego-Extraktions-Trigger). Die Factories sind die einzige Flask-berührende
Stelle der Datei (`request`/`g`/`make_response`):

- `make_require_init_data(...)` — **HART** (Loopback → Cookie+Rolling-Refresh →
  tma-Header → 401). Konsumenten: essen/kibuddy/photo/plan.
- `make_require_soft_gate(...)` — **SOFT** (Loopback → tma → Pass-through, KEIN
  Cookie-Zweig). Konsumenten: routine + hoerspiel.
- `make_require_dual_gate(...)` — **AUTH-7b** (Cookie ODER Operator-IP,
  observe/hard). Konsument: seiten.

Die Pro-Buddy-Laufzeit kommt ausschließlich über **Getter-Closures** rein (kein
`g`-Read zur Konfig, keine App-Registrierung). Der `auth_401`-Renderer ist ein
eigener Injektionspunkt (D1), weil 401-HTML-Text und 403-Shape buddy-variant
sind — die Factory inlined NIE einen Auth-Text. Import strikt Buddy→Lib: dieses
Modul importiert NICHTS aus einem Buddy (kein Zyklus).
"""

from __future__ import annotations

import functools
import ipaddress
import logging

from flask import g, make_response, request

from tools.initdata import init_data as _init_data
from tools.initdata import session_cookie

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Flask-Glue-Helfer (nur von den Decorator-Factories genutzt)
# ---------------------------------------------------------------------------


def _ist_loopback() -> bool:
    """AUTH-5: True bei echtem Server-zu-Server-Loopback-Call.

    BEIDE Bedingungen zusammen sind load-bearing (auth.md AUTH-Decorator-Lib):
    nginx setzt bei jedem Fremd-Request `X-Forwarded-For`, `remote_addr` ist
    gegenüber dem Buddy immer `127.0.0.1` (lokaler Proxy). Nur das *Fehlen* von
    `X-Forwarded-For` unterscheidet einen echten Backend-Call von einem
    durchgereichten externen Request — `remote_addr` allein wäre ein
    Auth-Bypass-Loch.
    """
    return (
        not request.headers.get("X-Forwarded-For")
        and request.remote_addr in ("127.0.0.1", "::1")
    )


def _tma_leer(auth_header: str) -> bool:
    """True, wenn der Authorization-Header keine echte tma-Quelle trägt.

    Mini-App-JS außerhalb des Telegram-Kontexts sendet `"tma "` leer; das zählt
    wie ein fehlender Header (wörtlich aus photo/routine übernommen).
    """
    lowered = auth_header.lower()
    return (
        not auth_header
        or lowered in ("tma", "tma ")
        or (lowered.startswith("tma ") and not auth_header[4:].strip())
    )


# ---------------------------------------------------------------------------
# Decorator-Factories (auth.md „AUTH-Decorator-Lib", #1383)
# ---------------------------------------------------------------------------
#
# Jede Factory nimmt die Pro-Buddy-Laufzeit AUSSCHLIESSLICH über Getter-Closures
# + einen injizierten `auth_401`-Renderer (D1) und liefert einen fertigen
# Flask-Decorator. Kein `g`-Read zur Konfig, keine App-Registrierung, kein
# Buddy-Import (kein Zyklus).


def make_require_init_data(
    *,
    get_bot_token,
    get_familie_client,
    get_init_data_config,
    auth_401,
):
    """HART-AUTH-Factory (auth.md AUTH-2/3/5/8, D2-HART-Zweig).

    Faithful extrahiert aus `photo/main.py:require_init_data` (Zwilling in
    essen/kibuddy/plan). Der Decorator prüft in dieser Reihenfolge:

    - **AUTH-5 Loopback** (`_ist_loopback`): pass-through, `g.init_data=None`.
    - **AUTH-2 Cookie** `xbuddy_session`: valide Signatur reicht →
      pass-through **+ Rolling-Refresh** (frischer `exp`, Set-Cookie).
    - **AUTH-2 tma-Header** (MAD-7): valide + Familien-Mitglied → `g.init_data`;
      valide + Nicht-Mitglied → `("", 403)` (schmale, buddy-neutrale Shape wie
      photo/routine); ungültig → `auth_401()`.
    - **sonst**: `auth_401()` (D1 — die Factory inlined KEINEN 401-Text).

    Injektionspunkte (alles Callables):
      - ``get_bot_token()`` → str | None (APP-7 / MAD-9).
      - ``get_familie_client()`` → Objekt mit ``get_telegram_ids()`` (FAM-7/8).
      - ``get_init_data_config()`` → dict mit ``max_age_seconds`` (Tma-Config).
      - ``auth_401()`` → fertige Flask-Response (AUTH-8, buddy-variant).
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # AUTH-5: Loopback-Bypass für Internal-Service-Calls.
            if _ist_loopback():
                g.init_data = None
                return fn(*args, **kwargs)

            bot_token = get_bot_token()
            if not bot_token:
                return ("", 500)

            # AUTH-2: Session-Cookie. Valide Signatur (+ nicht abgelaufen) reicht.
            cookie_val = request.cookies.get(session_cookie.COOKIE_NAME)
            if cookie_val:
                subject = session_cookie.verify_session(cookie_val, bot_token)
                if subject is not None:
                    g.init_data = None
                    # Rolling-Refresh (AUTH-2:78): Cookie mit frischem exp neu setzen.
                    # make_response wrappt auch send_file-Binary-Responses korrekt.
                    resp = make_response(fn(*args, **kwargs))
                    resp.set_cookie(
                        session_cookie.COOKIE_NAME,
                        session_cookie.sign_session(subject, bot_token),
                        **session_cookie.session_cookie_kwargs(),
                    )
                    return resp

            # AUTH-2: tma-Header (MAD-7). Leerer/fehlender "tma "-Wert = keine Quelle.
            auth_header = request.headers.get("Authorization", "").strip()
            if not _tma_leer(auth_header):
                cfg = get_init_data_config()
                try:
                    parsed = _init_data.validate_header(
                        auth_header, bot_token, cfg["max_age_seconds"])
                except _init_data.InitDataError:
                    return auth_401()

                # FAM-7/8: User-ID gegen Familien-Registry prüfen (HTTP-Pfad).
                familie_ids = get_familie_client().get_telegram_ids()
                if familie_ids is not None and parsed.user_id not in familie_ids:
                    return ("", 403)

                g.init_data = parsed
                return fn(*args, **kwargs)

            # AUTH-3: weder Loopback noch Cookie noch tma → HART 401 (AUTH-8).
            return auth_401()
        return wrapper
    return decorator


def make_require_soft_gate(
    *,
    get_bot_token,
    get_familie_client,
    get_init_data_config,
    auth_401,
):
    """SOFT-AUTH-Factory (V3 #898, D2-SOFT-Zweig — eigene Factory, KEIN Flag).

    Faithful extrahiert aus `routine/main.py:require_init_data` (Zwilling
    `hoerspiel/main.py:require_mini_app_auth`). Strukturell divergent zum
    HART-Pfad: **kein** Cookie-/Rolling-Refresh-Zweig, **kein** Set-Cookie.

    - **AUTH-5 Loopback**: pass-through, `g.init_data=None`.
    - **Kein/leerer tma-Header**: pass-through, `g.init_data=None` (Kind-Tablet-
      Display-JS ohne initData ruft dieselben Routen wie die Eltern-Mini-App).
    - **tma-Header vorhanden**: valide + Mitglied → `g.init_data`; ungültig →
      `auth_401()` (D1); Nicht-Mitglied → 403.

    Injektionspunkte identisch zu `make_require_init_data` (Symmetrie der
    Consumer-Verdrahtung), obwohl der Cookie-Zweig entfällt.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # AUTH-5: Loopback-Bypass für Internal-Service-Calls.
            if _ist_loopback():
                g.init_data = None
                return fn(*args, **kwargs)

            # V3 Soft-Auth: Header optional → Pass-through (KEIN Cookie-Zweig).
            auth_header = (request.headers.get("Authorization") or "").strip()
            if _tma_leer(auth_header):
                g.init_data = None
                return fn(*args, **kwargs)

            bot_token = get_bot_token()
            if not bot_token:
                return ("", 500)

            cfg = get_init_data_config()
            try:
                parsed = _init_data.validate_header(
                    auth_header, bot_token, cfg["max_age_seconds"])
            except _init_data.InitDataError:
                return auth_401()

            # FAM-7/8: User-ID gegen Familien-Registry prüfen (HTTP-Pfad).
            familie_ids = get_familie_client().get_telegram_ids()
            if familie_ids is not None and parsed.user_id not in familie_ids:
                return ("", 403)

            g.init_data = parsed
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def make_require_dual_gate(
    *,
    get_bot_token,
    get_client_ip,
    auth_401,
    default_mode="observe",
):
    """AUTH-7b-Dual-Gate-Factory (auth.md AUTH-7, RAT-32).

    Faithful extrahiert aus `seiten/main.py:require_dual_gate`. Teilt die pure
    funcs `ist_operator_ip`/`hat_gueltigen_cookie` (kein tma-Pfad).

    - **Cookie gültig** → pass-through **+ Rolling-Refresh** (Set-Cookie).
    - **keine Cookie-Quelle, mode="hard"** → `auth_401()` (D1 — Re-Pair-HTML
      buddy-variant, hier über den injizierten Renderer).
    - **keine Cookie-Quelle, mode="observe"** → pass-through (200, Grace).

    RAT-32: Operator-IP ist als Zugangs-Alternative gestrichen; `get_client_ip`
    /`ist_operator_ip` speisen nur noch das Observe-Log (verhaltensneutral).

    Injektionspunkte:
      - ``get_bot_token()`` → str | None.
      - ``get_client_ip()`` → str | None (X-Real-IP-Auflösung, buddy-lokal).
      - ``auth_401()`` → fertige Flask-Response (AUTH-8-Re-Pair, buddy-variant).
      - ``default_mode`` → "observe" | "hard" (Buddy übergibt beim Dekorieren).
    """
    def make_decorator(mode=default_mode):
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                bot_token = get_bot_token()
                cookie_val = request.cookies.get(session_cookie.COOKIE_NAME)
                cookie_ok = bool(bot_token) and hat_gueltigen_cookie(
                    cookie_val, bot_token)
                # RAT-32: Operator-IP nur noch fürs Observe-Log.
                operator_ok = ist_operator_ip(get_client_ip())

                if cookie_ok:
                    # Rolling-Refresh (AUTH-2:78): Cookie mit frischem exp neu setzen.
                    subject = session_cookie.verify_session(cookie_val, bot_token)
                    resp = make_response(fn(*args, **kwargs))
                    resp.set_cookie(
                        session_cookie.COOKIE_NAME,
                        session_cookie.sign_session(subject, bot_token),
                        **session_cookie.session_cookie_kwargs(),
                    )
                    return resp

                # Keine Cookie-Quelle.
                if mode == "hard":
                    return auth_401()
                # AUTH-3.a Observe: 200 + Log (kein 401), Beobachtungs-Rollout.
                logger.warning(
                    "AUTH-3.a Observe (7b): %s — keine valide Quelle "
                    "(cookie_vorhanden=%s, operator_ip=%s) → 200 (Grace, kein 401)",
                    request.path, bool(cookie_val), operator_ok)
                return fn(*args, **kwargs)
            return wrapper
        return decorator
    return make_decorator
