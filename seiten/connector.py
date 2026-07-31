"""seiten/connector.py — Connector-Übersicht View-Kontext (CONN-1..CONN-8).

HTTP-frei wie ``seiten/render.py``: hier wohnt nichts, was Flask oder HTTP
braucht. Das Modul baut den JSON-Kontext für die Connector-PWA aus dem
Track-A-Aggregator (``tools.llm.telemetry_read``) plus dem ZD-Slot-Inventar
(nur Existenz/Status, CONN-7 — nie ein Key-Wert, nie ein Slot-Klartext-Name).

3-Block-Sicht (#1669): Der Kontext trägt die Daten für die drei View-Blöcke —
``gesamt_llm_eur`` + ``gesamt_7t_eur`` (Block ① Gesamtkosten, CONN-4),
``je_buddy`` (Block ② „Welche App nutzt was", CONN-2), ``schnittstellen``
(Block ③ Anbieter-Status/LiteLLM-Gateway, CONN-1). Die Datenform ändert sich
gegenüber der Zwei-Sektionen-Fassung NICHT bis auf das ergänzte
``gesamt_7t_eur``-Feld; die 3-Block-Gliederung ist rein clientseitig.

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

# Vendor-Slug (parse_slot, == _vendor/<slug>.py) → Anzeige-Label + Logo-Datei
# (seiten/static/connector/logos/<slug>.svg). Generischer Title-Case-Fallback:
# ein neues _vendor-Modul (Familie 3) rendert OHNE Code-Änderung — kein
# Familie-1-Hardcode (Familie-3-Probe, specs/platform/connector.md).
_VENDOR_LABEL = {"anthropic": "Anthropic", "mistral": "Mistral", "azure": "Azure OpenAI"}
_VENDOR_LOGO_SLUG = {"anthropic": "anthropic", "mistral": "mistral", "azure": "azure"}

# CONN-2: feste Zeilen-Reihenfolge je Buddy×Funktion (Mockup-treu).
# eltern-chat LLM → hoerspiel LLM → hoerspiel TTS → kibuddy LLM.
_BUDDY_ORDER = ["eltern-chat", "hoerspiel", "kibuddy"]


def buddy_meta(caller):
    """caller → {label, emoji}. Unbekannte caller fallen auf einen Stecker."""
    return _BUDDY_META.get(caller, {"label": caller or "—", "emoji": "🔌"})


def model_to_vendor(model_id):
    """model_id → (Vendor-Label, Logo-Slug). Unbekannt → ('Unbekannt', None).

    Nur Sektion 2 (Je-Buddy-Nutzung) — dort ist der Vendor das Beiwerk zum real
    genutzten Modell, also legitim modell-abgeleitet. Sektion 1 (Inventar) leitet
    den Vendor autoritativ aus dem Slot ab (``_slot_vendor``), nicht von hier.
    """
    m = (model_id or "").lower()
    if m.startswith("claude"):
        return ("Anthropic", "anthropic")
    if m.startswith("mistral"):
        return ("Mistral", "mistral")
    if m.startswith(("gpt", "azure")):
        return ("Azure OpenAI", "azure")
    return ("Unbekannt", None)


def vendor_label(slug):
    """Vendor-Slug → Anzeige-Label; unbekannt → generischer Title-Case-Fallback."""
    if not slug:
        return "—"
    return _VENDOR_LABEL.get(slug, slug.replace("-", " ").title())


def _slot_vendor(slot):
    """slot → (caller, vendor-slug) autoritativ via ``parse_slot`` (LLMP-5).

    Generisch gegen die real existierenden ``_vendor/<slug>.py``-Module — kein
    Hardcode. Trägt der Slot kein bekanntes Vendor-Segment (Nicht-LLM- oder
    Altlast-Slot wie ``*-provider-api-key``), wird (None, None) geliefert.
    """
    try:
        from tools.llm._resolver import parse_slot

        caller, vendor, _purpose = parse_slot(slot)
        return caller, vendor
    except Exception:
        return None, None


def _ist_legacy_provider_key(slot):
    """CONN-1: Slot sieht aus wie ein LLM-Provider-Key (endet auf ``-key``), trägt
    aber kein bekanntes Vendor-Segment und gehört nicht zur aktiven Azure-TTS-
    Bindung → Altlast-Kandidat. Rein aus der Slot-FORM abgeleitet (kein Klartext
    nach außen, CONN-7), generisch über jedes Inventar."""
    s = (slot or "").lower()
    if not s.endswith("-key"):
        return False
    if "azure" in s:  # Azure-TTS wird als aktive Verbindung geführt (CONN-3).
        return False
    _caller, vendor = _slot_vendor(slot)
    return vendor is None


def _round_eur(value):
    """Kosten auf 4 Nachkommastellen runden; None bleibt None (OPEN-LLMP-A)."""
    return None if value is None else round(float(value), 4)


def _enrich(events):
    """Versieht jedes Event mit ``_vendor`` (Slug) für vendorweise Aggregation.

    Autoritativ aus dem Slot (``_slot_vendor``/parse_slot, LLMP-5); Fallback auf
    den model_id-Prefix nur, wenn das Event keinen parsebaren Slot trägt (alte
    Zeile, Test-Mock) — damit keine Telemetrie still verschwindet.
    """
    for e in events:
        _caller, vendor = _slot_vendor(e.get("slot"))
        if vendor is None:
            _label, vendor = model_to_vendor(e.get("model_id"))  # logo-slug
        e["_vendor"] = vendor
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


def _schnittstellen(events, today, slot_names):
    """CONN-1: eine Zeile pro angebundenem LLM-Provider-Vendor AUS DEM SLOT-INVENTAR.

    Vendor + nutzende caller kommen generisch via ``parse_slot`` aus dem ZD-Slot-
    Inventar (ZD-2) — kein Familie-1-Hardcode (Familie-3-Probe). Telemetrie-Kosten
    und 7-Tage-Verlauf werden je Vendor left-joined; ein konfigurierter, aber
    ungenutzter Slot erscheint mit Kosten „—". Azure-TTS (CONN-3, aktiv) und eine
    Altlast-Sammelzeile (nur falls Legacy-Provider-Slots existieren) ergänzen.
    """
    slot_names = list(slot_names or [])

    # 1. Inventar → Vendor-Slug → nutzende caller (autoritativ, generisch).
    inv_caller = defaultdict(set)
    legacy = 0
    for slot in slot_names:
        caller, vendor = _slot_vendor(slot)
        if vendor is not None:
            inv_caller[vendor].add(caller)
        elif _ist_legacy_provider_key(slot):
            legacy += 1

    # 2. Telemetrie je Vendor-Slug (Kosten + 7-Tage-Verlauf + nutzende caller).
    agg = {r["_vendor"]: r for r in aggregate(events, group_keys=("_vendor",))}
    daily = daily_series(events, group_keys=("_vendor",), days=CHART_DAYS, today=today)
    tele_caller = defaultdict(set)
    for e in events:
        if e.get("_vendor"):
            tele_caller[e["_vendor"]].add(e.get("caller"))

    # Vendor-Menge = Inventar ∪ Telemetrie (beide Quellen ehrlich vereint; ein
    # Vendor mit Telemetrie, aber ohne aktuellen Inventar-Slot, bleibt sichtbar).
    slugs = {s for s in (set(inv_caller) | set(agg)) if s}

    rows = []
    for slug in sorted(
        slugs, key=lambda s: (-(agg.get(s, {}).get("est_cost_eur") or 0.0), s)
    ):
        callers = sorted(c for c in (inv_caller[slug] | tele_caller[slug]) if c)
        rows.append(
            {
                "vendor": vendor_label(slug),
                "logo": _VENDOR_LOGO_SLUG.get(slug),
                "status": "konfiguriert",
                "status_kind": "ok",
                "buddys": [buddy_meta(c) for c in callers],
                "abgerechnet_eur": _round_eur(agg.get(slug, {}).get("est_cost_eur")),
                "telemetrie_folgt": False,
                "inaktiv": False,
                "daily": _daily_list(daily, slug),
                "key": slug,
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

    # CONN-1: Altlast-Sammelzeile NUR wenn das Inventar Legacy-Provider-Slots
    # enthält (abgeleitet, kein fester Demo-Eintrag; CONN-7: nur Anzahl, kein Name).
    if legacy:
        rows.append(
            {
                "vendor": "Altlast",
                "logo": None,
                "status": "inaktiv / Altlast (%d)" % legacy,
                "status_kind": "inactive",
                "buddys": [],
                "abgerechnet_eur": None,
                "telemetrie_folgt": False,
                "inaktiv": True,
                "legacy_count": legacy,
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


def _resolve_slot_names(slot_names, store_path):
    """Liest die ZD-Slot-Namen EINMAL (Test-Naht ``slot_names``; sonst live via
    ``Zugangsdaten.names()`` — nur Schlüssel, nie Werte, ZD-6/CONN-7).

    Die Liste speist sowohl Sektion 1 (Inventar-Zeilen, CONN-1) als auch
    ``_zd_inventar`` (Status-Zähler, CONN-7) — eine Quelle, ein Lesevorgang.
    """
    if slot_names is not None:
        return list(slot_names)
    try:
        # MOD-5: nur über die zugangsdaten-Public-API (Paket-Wurzel).
        from tools.zugangsdaten import Zugangsdaten, resolve_store_path

        return list(Zugangsdaten(store_path or resolve_store_path()).names())
    except Exception:
        return []


def _zd_inventar(slot_names):
    """CONN-7: nur Anzahl/Status der ZD-Slots — NIE Klartext-Name, NIE Wert."""
    return {"slots_total": len(slot_names), "konfiguriert": len(slot_names) > 0}


def baue_context(jsonl_source="", *, today=None, slot_names=None, store_path=None):
    """Baut den vollständigen Connector-View-Kontext (CONN-1..CONN-7).

    ``jsonl_source``: Dateipfad (str) ODER Iterable von JSONL-Zeilen (Test-Naht).
    Leerer String → Default-Pfad via ENV (telemetry_read.resolve_jsonl_path).
    ``today``: Referenzdatum für das Tail-/Chart-Fenster (Test-Naht).
    ``slot_names`` / ``store_path``: ZD-Inventar-Naht (CONN-7).
    """
    today = today or date.today()
    slots = _resolve_slot_names(slot_names, store_path)
    events = _enrich(read_calls(jsonl_source, tail_days=TAIL_DAYS, today=today))

    je_buddy = _je_buddy(events, today)
    gesamt = sum(r["kosten_eur"] for r in je_buddy if r.get("kosten_eur"))

    # Block ① (CONN-4): 7-Tage-Summe für die prominente Gesamtkosten-Karte.
    # Aus den bereits gerechneten daily-Serien der LLM-Zeilen (CHART_DAYS=7) —
    # kein zusätzlicher Telemetrie-Lesevorgang, read-only.
    gesamt_7t = sum(
        p["est_cost_eur"] or 0.0
        for r in je_buddy
        for p in r.get("daily", [])
    )

    return {
        "daten_ab": daten_ab(events),
        "fenster_tage": TAIL_DAYS,
        "chart_tage": CHART_DAYS,
        "schnittstellen": _schnittstellen(events, today, slots),
        "je_buddy": je_buddy,
        "gesamt_llm_eur": _round_eur(gesamt) if gesamt else (gesamt or None),
        "gesamt_7t_eur": _round_eur(gesamt_7t) if gesamt_7t else (gesamt_7t or None),
        "zd_inventar": _zd_inventar(slots),
    }
