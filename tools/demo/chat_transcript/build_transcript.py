#!/usr/bin/env python3
"""Anonymisierten Eltern-Chat-Transcript bauen (#1768, Half 2).

Liest die echten Verläufe aus `conversations.db`, wendet die **gitignored**
Scrub-Map (`.scrub-map.json`, echte→Familie-Sonntag inkl. Genitiv-s) an und
rendert eine statische Telegram-Look-Seite (render_transcript.py).

⚠️ PRIVACY-GATE (Nic-Setzung 2026-08-05): Die erzeugte Datei ist ein **Entwurf
zum Review** — reiner Namens-Scrub reicht NICHT (gebeugte Formen, externe
Kontakte, echte Orte in Story-Wünschen brauchen Handprüfung). Ausgabe + Map sind
gitignored; die finale Datei geht NIE ohne Nic-Review ins public Repo.

    python3 build_transcript.py \
        --db /home/buddy/xbuddy-data/eltern-chat/db/conversations.db \
        --chat-id <CHAT_ID> --out transcript.html
"""

import argparse
import json
import os
import re
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _lade_map(pfad: str) -> dict[str, str]:
    if not os.path.isfile(pfad):
        sys.stderr.write(
            "FEHLER: Scrub-Map fehlt (%s). Sie ist gitignored (echte Namen) und "
            "muss lokal aus brainstorm/demo-screenshots/chat-anon/scrub-map.md "
            "gebaut werden.\n" % pfad)
        raise SystemExit(2)
    return json.loads(open(pfad, encoding="utf-8").read())


def _scrubber(mapping: dict[str, str]):
    """Baut eine Funktion text→text: Wortgrenzen + optionales Genitiv/Plural-s,
    case-insensitiv (fängt auch `nekos`). Längste Schlüssel zuerst (Teil-Overlap).
    """
    paare = sorted(mapping.items(), key=lambda kv: len(kv[0]), reverse=True)
    muster = [(re.compile(r"\b%s(s?)\b" % re.escape(k), re.IGNORECASE), v) for k, v in paare]

    def scrub(text: str) -> str:
        for rx, ersatz in muster:
            text = rx.sub(lambda m, e=ersatz: e + (m.group(1) or ""), text)
        return text
    return scrub


def _text_aus_blocks(roh: str) -> str:
    try:
        blocks = json.loads(roh)
    except (ValueError, TypeError):
        return ""
    teile = []
    for b in blocks if isinstance(blocks, list) else []:
        if isinstance(b, dict) and b.get("text"):
            teile.append(str(b["text"]))
    return "\n".join(teile).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--chat-id", type=int, required=True)
    ap.add_argument("--map", default=os.path.join(_HERE, ".scrub-map.json"))
    ap.add_argument("--out", default=os.path.join(_HERE, "transcript.html"))
    ap.add_argument("--titel", default="Familie Sonntag")
    args = ap.parse_args()

    mapping = _lade_map(args.map)
    scrub = _scrubber(mapping)

    con = sqlite3.connect(args.db)
    rows = con.execute(
        "SELECT role, blocks FROM messages WHERE chat_id=? ORDER BY seq",
        (args.chat_id,)).fetchall()

    nachrichten = []
    for role, blocks in rows:
        text = _text_aus_blocks(blocks)
        if text:
            nachrichten.append({"role": role, "text": scrub(text)})

    sys.path.insert(0, _HERE)
    from render_transcript import render
    html = render(nachrichten, titel=args.titel)

    # Sicherheitsnetz: KEIN Map-Schlüssel (echter Name) darf im Output verbleiben.
    rest = sorted({k for k in mapping
                   if re.search(r"\b%s\b" % re.escape(k), html, re.IGNORECASE)})
    if rest:
        sys.stderr.write(
            "⚠️  SCRUB UNVOLLSTÄNDIG: %d Map-Schlüssel noch im Output — NICHT "
            "veröffentlichen. (Details nur lokal.)\n" % len(rest))
        # Namen NICHT nach stdout drucken; nur Anzahl.

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    sys.stderr.write(
        "[transcript] %d Nachrichten → %s (%d bytes). ENTWURF — Nic-Review-Gate "
        "vor Publish (#1768).\n" % (len(nachrichten), args.out, len(html)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
