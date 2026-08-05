#!/usr/bin/env python3
"""Statische Telegram-Look-Transcript-Seite (#1768, Half 2).

Rendert eine Liste bereits **anonymisierter** Nachrichten (`{"role","text"}`) als
statische HTML-Seite im Telegram-Chat-Look — für Produkt-Screenshots der
Eltern-Chat-Sicht, ohne Bot/LLM-Key. Public-safe: dieses Modul trägt KEINE echten
Namen; die Anonymisierung passiert vorgelagert in build_transcript.py (gitignored
Scrub-Map). Der Eingang ist bereits Familie-Sonntag.

    from render_transcript import render
    html = render([{"role": "user", "text": "…"}, …], titel="Familie Sonntag")
"""

import html as _html

_CSS = """
:root{--bg:#0e1621;--in:#182533;--out:#2b5278;--txt:#e9edf0;--meta:#7d8b99}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:var(--txt)}
.wrap{max-width:520px;margin:0 auto;min-height:100vh;background:var(--bg)}
.head{position:sticky;top:0;background:#17212b;padding:12px 16px;font-weight:600;
  border-bottom:1px solid #0b1219;display:flex;align-items:center;gap:10px}
.head .av{width:34px;height:34px;border-radius:50%;background:#2b5278;display:flex;
  align-items:center;justify-content:center;font-size:15px}
.msgs{padding:12px 10px 24px}
.row{display:flex;margin:2px 0}
.row.user{justify-content:flex-end}
.b{max-width:78%;padding:7px 11px;border-radius:14px;line-height:1.34;font-size:15px;
  white-space:pre-wrap;word-wrap:break-word}
.row.assistant .b{background:var(--in);border-bottom-left-radius:5px}
.row.user .b{background:var(--out);border-bottom-right-radius:5px}
.day{text-align:center;margin:14px 0}
.day span{background:#1c2733;color:var(--meta);font-size:12px;padding:3px 10px;border-radius:10px}
""".strip()


def render(nachrichten: list[dict], titel: str = "Familie Sonntag") -> str:
    """Anonymisierte Nachrichten → Telegram-Look-HTML-String."""
    zeilen = []
    for m in nachrichten:
        rolle = "user" if m.get("role") == "user" else "assistant"
        text = _html.escape((m.get("text") or "").strip())
        if not text:
            continue
        zeilen.append('<div class="row %s"><div class="b">%s</div></div>' % (rolle, text))
    kopf_av = _html.escape(titel[:1] or "S")
    return (
        "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>%s — Eltern-Chat (Demo)</title><style>%s</style></head>"
        "<body><div class=\"wrap\"><div class=\"head\"><div class=\"av\">%s</div>"
        "<div>%s · Eltern-Chat <span style=\"color:var(--meta);font-weight:400\">"
        "(Demo)</span></div></div><div class=\"msgs\">%s</div></div></body></html>"
        % (_html.escape(titel), _CSS, kopf_av, _html.escape(titel), "\n".join(zeilen))
    )


if __name__ == "__main__":
    import json
    import sys
    daten = json.load(sys.stdin)
    sys.stdout.write(render(daten))
