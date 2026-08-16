#!/usr/bin/env python3
"""Mini-Server fuer den arbeitstag-prep HTML-Karten-Loop (Produktivcode).

GET  /        -> rendert current.html-Template mit injiziertem CARDS-JSON aus cards.json
POST /save    -> schreibt answers/answers-latest.json (+ Timestamp-Kopie)
GET  /latest  -> liefert answers-latest.json

Tailnet-Bind: PORT-3-Ausnahme — bindet bewusst auf Tailscale-IP (nicht 0.0.0.0),
damit nur Operator-Geraete im Tailnet zugreifen koennen.

Server-Lifecycle: Per Port beenden, z.B.:
    fuser -k 8765/tcp
KEIN pkill (wuerde andere Python-Prozesse treffen).

--self-check: Synthetischer Selbst-Check — DOM-Stub-Render aller Karten-Klassen
              (stempel/wahl/koord/schliessen/parken) + card_form_quote-Parser-
              Verifikation der 3 Mess-Metriken. Bricht bei Fehler ab → kein Loop.
              Wird auch beim regulaeren Start VOR dem Servieren ausgefuehrt.

cards.json-Format (geschrieben vom arbeitstag-prep-Skill):
    {
        "round": <int>,
        "summary": "<Retro-Zeile>",
        "subtitle": "<Kurzbeschreibung>",
        "cards": [<card>, ...]
    }
    oder als rohe Karten-Liste fuer Kompatibilitaet mit Altformat.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, "current.html")
CARDS_FILE = os.path.join(BASE, "cards.json")
ANSWERS_DIR = os.path.join(BASE, "answers")
PORT = 8765

# card_form_quote.py liegt im uebergeordneten tools/-Verzeichnis
TOOLS_DIR = os.path.dirname(BASE)


# ---------------------------------------------------------------------------
# Tailscale-IP-Ermittlung
# ---------------------------------------------------------------------------

def _tailscale_ip() -> str:
    """Ermittelt die Tailscale-IPv4 dynamisch.

    Probiert zuerst `tailscale ip -4`, faellt dann auf das tailscale0-Interface
    zurueck. Wirft RuntimeError wenn weder noch klappt.
    """
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        ip = result.stdout.strip()
        if ip and result.returncode == 0:
            return ip
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Fallback: tailscale0-Interface
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", "tailscale0"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("inet "):
                return stripped.split()[1].split("/")[0]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    raise RuntimeError(
        "Tailscale-IP nicht ermittelbar — ist tailscale aktiv? "
        "(tailscale up / systemctl status tailscaled)"
    )


# ---------------------------------------------------------------------------
# Template-Rendering
# ---------------------------------------------------------------------------

def _to_data(raw: object) -> dict:
    """Normalisiert cards.json-Inhalt: Liste oder Dict mit 'cards'-Key."""
    if isinstance(raw, list):
        return {"round": 0, "summary": "", "subtitle": "", "cards": raw}
    return raw


def _render_html(data: dict) -> bytes:
    """Liest current.html-Template, ersetzt __CARDS_JSON__ mit serialisiertem data."""
    with open(TEMPLATE, encoding="utf-8") as fh:
        template = fh.read()
    cards_json = json.dumps(data, ensure_ascii=False)
    rendered = template.replace("__CARDS_JSON__", cards_json)
    return rendered.encode("utf-8")


# ---------------------------------------------------------------------------
# DOM-Stub-Render-Check
# ---------------------------------------------------------------------------

SYNTHETIC_CARDS_DATA = {
    "round": "self-check",
    "summary": "Synthetischer Selbsttest — alle Karten-Klassen.",
    "subtitle": "5 Karten (eine je Klasse), kein Echtbetrieb.",
    "cards": [
        {
            "id": 9001,
            "title": "Stempel-Karte (Selbsttest)",
            "type": "stempel",
            "treiber": "Synthetischer Test — alle Stempel-Felder vorhanden.",
            "empf": "stempeln",
            "empfClass": "",
            "risiko": "gelb",
            "vertrautheit": "gruen",
            "belege": "T1193-Selbsttest",
            "actions": [["stempeln", "stempeln"], ["parken", "parken"]],
        },
        {
            "id": 9002,
            "title": "Arch-Wahl-Karte (Selbsttest)",
            "type": "wahl",
            "badge": "\U0001f531 ARCH-WAHL",
            "badgeClass": "wahl",
            "treiber": "Synthetischer Test — Wahl-Zweig.",
            "empf": "a",
            "empfClass": "",
            "kernfrage": "Welche Option soll gebaut werden?",
            "opts": [
                ["a", "Option A", "Einfachere Variante", True],
                ["b", "Option B", "Aufwaendigere Variante", False],
            ],
            "belege": "T1193-Selbsttest",
            "actions": [["a", "a: Option A"], ["b", "b: Option B"]],
        },
        {
            "id": 9003,
            "title": "Koord-Wahl-Karte (Selbsttest)",
            "type": "koord",
            "badge": "⚠️ KOORD-WAHL · RAT-XX",
            "badgeClass": "koord",
            "treiber": "Synthetischer Test — Koord-Zweig.",
            "empf": "a",
            "empfClass": "koord",
            "kernfrage": "Wie wird koordiniert?",
            "opts": [
                ["a", "Split", "Kleiner Schnitt jetzt", True],
            ],
            "belege": "T1193-Selbsttest",
            "actions": [["a", "a: Split"]],
        },
        {
            "id": 9004,
            "title": "Schliessen-Karte (Selbsttest)",
            "type": "schliessen",
            "treiber": "Synthetischer Test — Schliessen-Zweig.",
            "belege": "T1193-Selbsttest",
            "actions": [["schliessen", "schlie\xdfen"], ["parken", "parken"]],
        },
        {
            "id": 9005,
            "title": "Park-Karte (Selbsttest)",
            "type": "parken",
            "treiber": "Synthetischer Test — Parken-Zweig.",
            "belege": "T1193-Selbsttest",
            "actions": [["parken", "parken"], ["stempeln", "stempeln"]],
        },
    ],
}


def _dom_stub_render(data: dict) -> list[str]:
    """Rendert HTML und prueft mit HTMLParser; gibt Fehler-Liste zurueck."""
    html_bytes = _render_html(data)
    html = html_bytes.decode("utf-8")
    issues: list[str] = []

    # HTML-Parse-Check (strukturelle Gueltigkeit)
    parser = HTMLParser(convert_charrefs=True)
    try:
        parser.feed(html)
    except Exception as exc:
        issues.append(f"HTML-Parse-Fehler: {exc}")

    # Placeholder ersetzt?
    if "__CARDS_JSON__" in html:
        issues.append("Template-Placeholder __CARDS_JSON__ wurde nicht ersetzt")

    # Alle Karten-Klassen im Stapel vorhanden?
    required_types = {"stempel", "wahl", "koord", "schliessen", "parken"}
    present_types = {c.get("type") for c in data.get("cards", [])}
    missing = required_types - present_types
    if missing:
        issues.append(f"Karten-Klassen fehlen im Stapel: {sorted(missing)}")

    # Karten-JSON im HTML eingebettet (alle Typen als Strings auffindbar)?
    for ctype in required_types:
        if f'"type":"{ctype}"' not in html and f'"type": "{ctype}"' not in html:
            issues.append(f'Karten-Typ "{ctype}" nicht im gerenderten HTML gefunden')

    # Pflicht-Strukturen
    for marker, label in [
        ('id="cards"', "cards-Container"),
        ("/save", "save-Endpunkt"),
        ("<footer", "footer-Element"),
    ]:
        if marker not in html:
            issues.append(f"Struktur-Element fehlt: {label} ({marker!r})")

    # Stempel-Ampel-Felder in Karten-Daten
    stempel_cards = [c for c in data.get("cards", []) if c.get("type") == "stempel"]
    for card in stempel_cards:
        for field in ("risiko", "vertrautheit"):
            if not card.get(field):
                issues.append(
                    f"Stempel-Karte #{card.get('id')}: Ampel-Feld '{field}' fehlt"
                )

    return issues


# ---------------------------------------------------------------------------
# Mess-Naht: durablen Issue-Comment erzeugen (PREP-10)
# ---------------------------------------------------------------------------

# Abbildung interner Entscheidungs-Werte auf ACTION_LINE_RE-konforme Zeichenketten.
# ACTION_LINE_RE = r"^→\s*\[(stempeln|A|a|schließen|parken|Reihenfolge OK)"
# Wahl-/Koord-Optionen b, c, d sind kein eigenes ACTION_LINE_RE-Token;
# normieren auf "A" damit _card_line_count() > 0 (Mess-Naht PREP-10).
_ACTION_MAP: dict[str, str] = {
    "stempeln": "stempeln",
    "schliessen": "schlie\xdfen",  # ACTION_LINE_RE erwartet "schließen" (mit sz)
    "parken": "parken",
    "reihenfolge_ok": "Reihenfolge OK",
    "a": "a",
    "A": "A",
    "b": "A",
    "c": "A",
    "d": "A",
    "B": "A",
    "C": "A",
}

def make_durable_comment(card: dict, decision: str) -> str:
    """Erzeugt den durablen Issue-Comment in card_form_quote-konformer Form.

    Erste Zeile = <!-- card_pre_flight v1 ... -->-Marker (Mess-Naht, PREP-10).
    Darunter: #<nr>-Header + Karten-Text + Aktionszeile.

    Format wird so erstellt, dass card_form_quote.py alle drei Metriken korrekt
    messen kann:
    - preflight_missing=0  -> PREFLIGHT_RE matcht auf Zeile 1
    - over_14_lines        -> _card_line_count() > 0 (Header + Aktionszeile vorhanden)
    - followup_pain        -> spaetere Korrektur-Comments nach diesem Marker

    Die Funktion gibt nur den Comment-Text zurueck; das Posten via gh obliegt
    dem aufruenden Skill (arbeitstag-prep).
    """
    kind = card.get("type", "unbekannt")
    nr = card["id"]
    title = card["title"]
    treiber = card.get("treiber", "")
    empf = card.get("empf", "")

    lines = [
        f"<!-- card_pre_flight v1 issue:{nr} kind:{kind} -->",
        f"#{nr} {title}",
        "",
        f"TREIBER: {treiber}",
    ]

    if kind == "stempel":
        lines += [
            f"EMPFEHLUNG: {empf}",
            f"RISIKO: {card.get('risiko', '?')} | VERTRAUTHEIT: {card.get('vertrautheit', '?')}",
        ]
    elif kind in ("wahl", "koord"):
        if empf:
            lines.append(f"EMPFEHLUNG: {empf}")
        if card.get("kernfrage"):
            lines.append(f"KERNFRAGE: {card['kernfrage']}")
    elif kind == "schliessen":
        lines.append("AKTION: Ticket schliessen")
    elif kind == "parken":
        lines.append("AKTION: Ticket parken")

    action_val = _ACTION_MAP.get(decision, decision)
    lines.append(f"→ [{action_val}]")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Kanonischer Post-Pfad (einzige Quelle des Durable-Card-Comments, PREP-10)
# ---------------------------------------------------------------------------

def _post_durable_comment(
    issue_number: int,
    card: dict,
    decision: str,
    dry_run: bool = False,
) -> str:
    """Kanonische Quelle des Durable-Card-Comments (Mess-Naht PREP-10).

    Ruft make_durable_comment() auf und postet den resultierenden Text via
    `gh issue comment`. Mit dry_run=True wird nur der Text zurueckgegeben,
    nichts gepostet — identischer Pfad wie live, daher von self_check nutzbar.

    Diese Funktion ist der einzige Ort, der den Comment-Text produziert und
    abschickt. self_check verifiziert denselben Code-Pfad (dry_run=True).
    """
    body = make_durable_comment(card, decision)
    if not dry_run:
        # Lazy-Import damit der Server auch ohne card_form_quote startet (z.B. in Tests)
        old_path = sys.path[:]
        sys.path.insert(0, TOOLS_DIR)
        try:
            import card_form_quote as cfq
            repo = cfq.resolve_repo()
        finally:
            sys.path[:] = old_path
        subprocess.run(
            [
                "gh", "issue", "comment", str(issue_number),
                "--repo", repo,
                "--body", body,
            ],
            check=True,
        )
    return body


# ---------------------------------------------------------------------------
# card_form_quote-Parser-Verifikation
# ---------------------------------------------------------------------------

def _verify_card_form_quote(comment: str, label: str) -> list[str]:
    """Testet comment gegen card_form_quote.py-Regex-Parser. Gibt Fehler-Liste zurueck."""
    # Lazy-Import damit der Server auch ohne card_form_quote startet (z.B. in Tests)
    old_path = sys.path[:]
    sys.path.insert(0, TOOLS_DIR)
    try:
        import card_form_quote as cfq
    except ImportError as exc:
        return [f"[{label}] card_form_quote nicht importierbar: {exc}"]
    finally:
        sys.path[:] = old_path

    issues: list[str] = []

    if not cfq.PREFLIGHT_RE.search(comment):
        issues.append(
            f"[{label}] PREFLIGHT_RE ({cfq.PREFLIGHT_RE.pattern!r}) "
            f"matcht nicht — preflight_missing waere False-Positive"
        )

    count = cfq._card_line_count(comment)
    if count <= 0:
        issues.append(
            f"[{label}] _card_line_count={count}, erwartet >0 — "
            f"#<nr>-Header oder Aktionszeile fehlt im Comment"
        )

    # followup_pain: PAIN_RE muss in einem synthetischen Folge-Comment anschlagen
    followup = "nein, das stimmt nicht — war falsch gedacht"
    if not cfq.PAIN_RE.search(followup):
        issues.append(
            f"[{label}] PAIN_RE matcht nicht im synthetischen Folge-Comment — "
            f"followup_pain wuerde nie messen"
        )

    return issues


# ---------------------------------------------------------------------------
# Selbst-Check (Einstiegspunkt: --self-check oder interner Start-Check)
# ---------------------------------------------------------------------------

_DECISION_BY_TYPE: dict[str, list[str]] = {
    "stempel": ["stempeln"],
    "wahl": ["a", "b"],       # b normiert auf "A" via _ACTION_MAP — beide Pfade pruefen
    "koord": ["a"],
    "schliessen": ["schliessen"],
    "parken": ["parken"],
}


def self_check(verbose: bool = True) -> int:
    """Synthetischer Selbst-Check: DOM-Stub + card_form_quote-Verifikation.

    Gibt 0 (alles OK) oder 1 (Fehler) zurueck.
    """
    if verbose:
        print("[self-check] DOM-Stub-Render aller Karten-Klassen …")

    if not os.path.exists(TEMPLATE):
        print(f"[self-check] FEHLER: Template fehlt: {TEMPLATE}", file=sys.stderr)
        return 1

    dom_errors = _dom_stub_render(SYNTHETIC_CARDS_DATA)
    if dom_errors:
        print("[self-check] FEHLER DOM-Stub-Render:", file=sys.stderr)
        for err in dom_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    if verbose:
        n = len(SYNTHETIC_CARDS_DATA["cards"])
        print(f"[self-check] DOM-Stub-Render: {n} Karten-Klassen OK")

    if verbose:
        print("[self-check] card_form_quote-Parser-Kompatibilitaet …")

    all_ok = True
    for card in SYNTHETIC_CARDS_DATA["cards"]:
        kind = card["type"]
        decisions = _DECISION_BY_TYPE[kind]
        for decision in decisions:
            # Testet exakt denselben Pfad wie der Live-Post-Endpunkt (_post_durable_comment).
            comment = _post_durable_comment(card["id"], card, decision, dry_run=True)
            label = f"#{card['id']} {kind}/{decision}"
            errors = _verify_card_form_quote(comment, label)
            if errors:
                for err in errors:
                    print(f"[self-check] FEHLER: {err}", file=sys.stderr)
                all_ok = False
            elif verbose:
                print(f"[self-check] {label}: preflight✓ lines✓ pain✓")

    if not all_ok:
        return 1

    if verbose:
        print("[self-check] Alle Checks bestanden.")
    return 0


# ---------------------------------------------------------------------------
# HTTP-Handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes | str, ctype: str = "application/json; charset=utf-8") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if not os.path.exists(CARDS_FILE):
                self._send(
                    404,
                    "<h1>Noch keine Karten — cards.json fehlt</h1>"
                    "<p>Starte arbeitstag-prep, um Karten zu erzeugen.</p>",
                    "text/html; charset=utf-8",
                )
                return
            try:
                with open(CARDS_FILE, encoding="utf-8") as fh:
                    raw = json.load(fh)
                data = _to_data(raw)
                html = _render_html(data)
                self._send(200, html, "text/html; charset=utf-8")
            except Exception as exc:
                self._send(
                    500,
                    f"<h1>Render-Fehler: {exc}</h1>",
                    "text/html; charset=utf-8",
                )
        elif path == "/latest":
            p = os.path.join(ANSWERS_DIR, "answers-latest.json")
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    self._send(200, fh.read())
            else:
                self._send(404, json.dumps({"error": "keine Antworten"}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]

        if path == "/save":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                self._send(400, json.dumps({"error": f"bad json: {exc}"}))
                return
            os.makedirs(ANSWERS_DIR, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            payload["_saved_at"] = stamp
            pretty = json.dumps(payload, ensure_ascii=False, indent=2)
            latest = os.path.join(ANSWERS_DIR, "answers-latest.json")
            timestamped = os.path.join(ANSWERS_DIR, f"answers-{stamp}.json")
            with open(latest, "w", encoding="utf-8") as fh:
                fh.write(pretty)
            with open(timestamped, "w", encoding="utf-8") as fh:
                fh.write(pretty)
            self._send(200, json.dumps({"ok": True, "saved_at": stamp}))

        elif path == "/post-comment":
            # Postet den Durable-Card-Comment via _post_durable_comment (PREP-10).
            # Einziger Live-Pfad fuer den Mess-Comment — nutzt make_durable_comment().
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception as exc:
                self._send(400, json.dumps({"error": f"bad json: {exc}"}))
                return
            issue_number = payload.get("issue_number")
            card = payload.get("card")
            decision = payload.get("decision")
            if not all([issue_number is not None, card, decision]):
                self._send(
                    400,
                    json.dumps({"error": "Pflichtfelder: issue_number, card, decision"}),
                )
                return
            try:
                body = _post_durable_comment(int(issue_number), card, decision, dry_run=False)
                self._send(200, json.dumps({"ok": True, "comment": body}))
            except Exception as exc:
                self._send(500, json.dumps({"error": str(exc)}))

        else:
            self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *_args: object) -> None:
        pass  # ruhig


# ---------------------------------------------------------------------------
# Einstieg
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Synthetischer Check (DOM-Stub + card_form_quote); Exit 0=OK, 1=Fehler.",
    )
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (Default: {PORT})")
    args = parser.parse_args()

    if args.self_check:
        return self_check(verbose=True)

    # DOM-Stub-Render-Check VOR dem Servieren (Pflicht, PREP-10 Render-Medium)
    check_rc = self_check(verbose=False)
    if check_rc != 0:
        print(
            "FEHLER: DOM-Stub-Render-Check gescheitert — kein Loop an Nic.\n"
            "Fallback: Chat-Modus oder Code-Fix. Ausfuehrlich: --self-check",
            file=sys.stderr,
        )
        return 1

    try:
        host = _tailscale_ip()
    except RuntimeError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

    # PORT-3-Ausnahme: bewusst auf Tailscale-IP gebunden (nicht 0.0.0.0/LAN-offen).
    # Nur Operator-Geraete im Tailnet koennen zugreifen (Operator-Zugang unterwegs).
    srv = ThreadingHTTPServer((host, args.port), Handler)
    print(f"prep-karten server: http://{host}:{args.port}/")
    print(f"Karten-Loop ab N≥7 Karten (PREP-10). Beenden: fuser -k {args.port}/tcp")
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
