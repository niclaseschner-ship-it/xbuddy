"""seiten/connector.py — Connector-Übersicht View-Kontext (CONN-1..CONN-8).

HTTP-frei wie ``seiten/render.py``: hier wohnt nichts, was Flask oder HTTP
braucht. Das Modul baut den JSON-Kontext für die Connector-PWA aus dem
Track-A-Aggregator (``tools.llm.telemetry_read``) plus dem ZD-Slot-Inventar
(nur Existenz/Status, CONN-7 — nie ein Key-Wert, nie ein Slot-Klartext-Name).

Datenquellen:
  - ``var/llm/provider_calls.jsonl`` (LLMP-S4) via ``telemetry_read`` — Verbrauch
    und Kosten, Tail-Fenster 30 Tage (CONN-4).
  - ``tools/zugangsdaten``-Slot-Inventar (ZD-2) — nur Anzahl/Status (CONN-7).

Mappings (gegen die realen caller/model_id der JSONL geerdet):
  - caller → Buddy-Anzeige: eltern-chat / hoerspiel / kibuddy.
  - model_id → Vendor: claude-* → Anthropic, mistral-* → Mistral,
    gpt-*/azure-* → Azure OpenAI.

TTS (CONN-3) und die Altlast-Verbindung (CONN-1) liegen außerhalb der
LLM-Telemetrie und werden als feste, ehrliche Zeilen ergänzt: Azure-TTS als
aktive Verbindung mit Kosten "Telemetrie folgt" (LLMP-S6), der generische
Altlast-Slot als "inaktiv / Altlast".
"""

from collections import defaultdict
from datetime import date

from tools.llm.telemetry_read import aggregate, daily_series, daten_ab, read_calls

# CONN-4: Tail-Fenster (30 Tage) + 7-Tage-Verlauf (CONN-5).
TAIL_DAYS = 30
CHART_DAYS = 7

# caller → Buddy-Anzeige (Icon-Emoji-Fallback wie im Mockup; arasaac später).
_BUDDY_META = {
    "eltern-chat": {"label": "eltern-chat", "emoji": "💬"},
    "hoerspiel": {"label": "hoerspiel", "emoji": "🎧"},
    "kibuddy": {"label": "kibuddy", "emoji": "🤖"},
}

# Vendor-Label → Logo-Slug (Datei seiten/static/connector/logos/<slug>.svg).
_VENDOR_LOGO = {
    "Anthropic": "anthropic",
    "Mistral": "mistral",
    "Azure OpenAI": "azure",
}

# CONN-2: feste Zeilen-Reihenfolge je Buddy×Funktion (Mockup-treu).
# eltern-chat LLM → hoerspiel LLM → hoerspiel TTS → kibuddy LLM.
_BUDDY_ORDER = ["eltern-chat", "hoerspiel", "kibuddy"]


def buddy_meta(caller):
    """caller → {label, emoji}. Unbekannte caller fallen auf einen Stecker."""
    return _BUDDY_META.get(caller, {"label": caller or "—", "emoji": "🔌"})


def model_to_vendor(model_id):
    """model_id → (Vendor-Label, Logo-Slug). Unbekannt → ('Unbekannt', None)."""
    m = (model_id or "").lower()
    if m.startswith("claude"):
        return ("Anthropic", "anthropic")
    if m.startswith("mistral"):
        return ("Mistral", "mistral")
    if m.startswith(("gpt", "azure")):
        return ("Azure OpenAI", "azure")
    return ("Unbekannt", None)


def _round_eur(value):
    """Kosten auf 4 Nachkommastellen runden; None bleibt None (OPEN-LLMP-A)."""
    return None if value is None else round(float(value), 4)


def _enrich(events):
    """Versieht jedes Event mit ``_vendor`` (Label) für vendorweise Aggregation."""
    for e in events:
        label, _logo = model_to_vendor(e.get("model_id"))
        e["_vendor"] = label
    return events


def _daily_list(daily, key):
    """daily_series-Dict (Tupel-Key) → Liste für eine einzelne Gruppe."""
    series = daily.get((key,), [])
    return [
        {
            "datum": p["datum"],
            "calls": p["calls"],
            "est_cost_eur": _round_eur(p["est_cost_eur"]),
        }
        for p in series
    ]


def _schnittstellen(events, today):
    """CONN-1: eine Zeile pro externer Verbindung (Vendor), aggregiert.

    LLM-Vendoren kommen aus der Telemetrie; Azure-TTS (CONN-3) und die
    Altlast-Verbindung werden als feste Zeilen ergänzt.
    """
    agg = {r["_vendor"]: r for r in aggregate(events, group_keys=("_vendor",))}
    daily = daily_series(events, group_keys=("_vendor",), days=CHART_DAYS, today=today)

    buddys_pro_vendor = defaultdict(set)
    for e in events:
        buddys_pro_vendor[e["_vendor"]].add(e.get("caller"))

    rows = []
    # Vendoren mit echter Telemetrie, teuerster zuerst.
    for vendor in sorted(
        agg, key=lambda v: agg[v].get("est_cost_eur") or 0.0, reverse=True
    ):
        if vendor == "Unbekannt":
            continue
        callers = sorted(c for c in buddys_pro_vendor[vendor] if c)
        rows.append(
            {
                "vendor": vendor,
                "logo": _VENDOR_LOGO.get(vendor),
                "status": "konfiguriert",
                "status_kind": "ok",
                "buddys": [buddy_meta(c) for c in callers],
                "abgerechnet_eur": _round_eur(agg[vendor].get("est_cost_eur")),
                "telemetrie_folgt": False,
                "inaktiv": False,
                "daily": _daily_list(daily, vendor),
                "key": _VENDOR_LOGO.get(vendor, vendor.lower()),
            }
        )

    # CONN-3: Azure-TTS als aktive Verbindung, Verbrauch noch nicht erfasst.
    rows.append(
        {
            "vendor": "Azure OpenAI",
            "logo": "azure",
            "status": "aktiv (TTS)",
            "status_kind": "tts",
            "buddys": [buddy_meta("hoerspiel")],
            "abgerechnet_eur": None,
            "telemetrie_folgt": True,
            "inaktiv": False,
            "daily": [],
            "key": "azure-tts",
        }
    )

    # CONN-1: Altlast-Slot ohne aktiven caller → inaktiv.
    rows.append(
        {
            "vendor": "Generisch",
            "logo": None,
            "status": "inaktiv / Altlast",
            "status_kind": "inactive",
            "buddys": [dict(buddy_meta("hoerspiel"), dim=True)],
            "abgerechnet_eur": None,
            "telemetrie_folgt": False,
            "inaktiv": True,
            "daily": [],
            "key": "legacy",
        }
    )
    return rows


def _llm_row(caller, modelle, daily):
    """Baut eine LLM-Zeile (CONN-2) für einen caller aus seinen Modell-Aggregaten."""
    # Primärmodell = meiste Calls; weitere Modelle = Fallback.
    modelle = sorted(modelle, key=lambda m: m.get("calls", 0), reverse=True)
    primary = modelle[0]
    vendor, _logo = model_to_vendor(primary.get("model_id"))
    fallback = modelle[1]["model_id"] if len(modelle) > 1 else None

    calls = sum(m.get("calls", 0) for m in modelle)
    kosten = sum(m.get("est_cost_eur") or 0.0 for m in modelle)
    hat_kosten = any(m.get("est_cost_eur") is not None for m in modelle)

    meta = buddy_meta(caller)
    return {
        "buddy": meta["label"],
        "emoji": meta["emoji"],
        "funktion": "LLM",
        "funktion_kind": "llm",
        "vendor": vendor,
        "modell": primary.get("model_id"),
        "fallback_modell": fallback,
        "calls": calls,
        "kosten_eur": _round_eur(kosten) if hat_kosten else None,
        "telemetrie_folgt": False,
        "daily": _daily_list(daily, caller),
        # CONN-6: nur eltern-chat ist über den Chat wechselbar (anbieter_wechseln).
        "wechsel": "chat" if caller == "eltern-chat" else "v2",
        "key": "%s-llm" % caller,
    }


def _tts_row():
    """CONN-3: feste hoerspiel-TTS-Zeile, Kosten 'Telemetrie folgt' (LLMP-S6)."""
    meta = buddy_meta("hoerspiel")
    return {
        "buddy": meta["label"],
        "emoji": meta["emoji"],
        "funktion": "TTS",
        "funktion_kind": "tts",
        "vendor": "Azure OpenAI",
        "modell": "azure-tts-*",
        "fallback_modell": None,
        "calls": None,
        "kosten_eur": None,
        "telemetrie_folgt": True,
        "daily": [],
        "wechsel": "v2",
        "key": "hoerspiel-tts",
    }


def _je_buddy(events, today):
    """CONN-2: eine Zeile pro Buddy×Funktion in fester Reihenfolge."""
    per_modell = aggregate(events, group_keys=("caller", "model_id"))
    daily = daily_series(events, group_keys=("caller",), days=CHART_DAYS, today=today)

    by_caller = defaultdict(list)
    for r in per_modell:
        by_caller[r.get("caller")].append(r)

    rows = []
    for caller in _BUDDY_ORDER:
        if by_caller.get(caller):
            rows.append(_llm_row(caller, by_caller[caller], daily))
        if caller == "hoerspiel":
            # CONN-3: TTS-Zeile immer (synthetisch, unabhängig von LLM-Telemetrie).
            rows.append(_tts_row())
    return rows


def _zd_inventar(slot_names=None, store_path=None):
    """CONN-7: nur Anzahl/Status der ZD-Slots — NIE Klartext-Name, NIE Wert.

    ``slot_names`` ist eine Test-Naht; im Normalfall liest das Modul die Namen
    via ``Zugangsdaten(resolve_store_path()).names()`` (nur Schlüssel, ZD-6).
    """
    if slot_names is None:
        try:
            # MOD-5: nur ueber die zugangsdaten-Public-API (Paket-Wurzel).
            from tools.zugangsdaten import Zugangsdaten, resolve_store_path

            slot_names = Zugangsdaten(store_path or resolve_store_path()).names()
        except Exception:
            slot_names = []
    return {"slots_total": len(slot_names), "konfiguriert": len(slot_names) > 0}


def baue_context(jsonl_source="", *, today=None, slot_names=None, store_path=None):
    """Baut den vollständigen Connector-View-Kontext (CONN-1..CONN-7).

    ``jsonl_source``: Dateipfad (str) ODER Iterable von JSONL-Zeilen (Test-Naht).
    Leerer String → Default-Pfad via ENV (telemetry_read.resolve_jsonl_path).
    ``today``: Referenzdatum für das Tail-/Chart-Fenster (Test-Naht).
    ``slot_names`` / ``store_path``: ZD-Inventar-Naht (CONN-7).
    """
    today = today or date.today()
    events = _enrich(read_calls(jsonl_source, tail_days=TAIL_DAYS, today=today))

    je_buddy = _je_buddy(events, today)
    gesamt = sum(r["kosten_eur"] for r in je_buddy if r.get("kosten_eur"))

    return {
        "daten_ab": daten_ab(events),
        "fenster_tage": TAIL_DAYS,
        "chart_tage": CHART_DAYS,
        "schnittstellen": _schnittstellen(events, today),
        "je_buddy": je_buddy,
        "gesamt_llm_eur": _round_eur(gesamt) if gesamt else (gesamt or None),
        "zd_inventar": _zd_inventar(slot_names=slot_names, store_path=store_path),
    }
