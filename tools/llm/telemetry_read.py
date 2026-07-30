"""JSONL-Telemetrie-Leser und Aggregator für `tools.llm` (CONN-4, CONN-5).

Generischer Lese-Gegenpart zu `telemetry.py` (write_call). Keine connector-
oder buddy-spezifische Logik — das liegt beim Consumer (seiten/).

Lese-Disziplin (CONN-4): Tail-Fenster begrenzt den Scan auf `tail_days` Tage,
schützt vor wachsender Datei (OPEN-LLMP-E). Defekte Zeilen werden übersprungen
(kein Crash, analog telemetry.py OSError-Verhalten, LLMP-S4).

Null-Preis-Semantik (OPEN-LLMP-A): `est_cost_eur` kann None sein, wenn ein
Modell keinen bekannten Preis hat. Aggregation summiert nur Nicht-None-Werte;
wenn **alle** Beiträge einer Gruppe None sind, bleibt die Summe None (nicht 0).
"""

import json
import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from tools.llm.pricing import as_of_for
from tools.llm.telemetry import resolve_jsonl_path

logger = logging.getLogger(__name__)


def read_calls(
    source: str | Iterable[str],
    *,
    tail_days: int | None = None,
    today: date | None = None,
    env: Mapping[str, str] | None = None,
) -> list[dict]:
    """Liest provider_calls.jsonl und gibt die Einträge als Liste von Dicts zurück.

    `source` ist entweder:
    - ein Dateipfad (str) — dann wird die Datei zeilenweise gelesen, oder
    - eine Iterable von JSONL-Zeilen (Test-Naht ohne echte Datei).

    Wenn `source` ein leerer String ist, wird der Default-Pfad via ENV/`env`
    aufgelöst (analog `resolve_jsonl_path`).

    `tail_days`: wenn gesetzt, werden nur Einträge zurückgegeben, deren `ts`-Datum
    ≥ (today − tail_days) ist. Einträge ohne `ts` oder mit ungültigem `ts` werden
    **behalten** (defensiv, kein Ausschluss bei fehlenden Feldern — LLMP-S4).

    Defekte Zeilen (kein gültiges JSON) werden übersprungen, kein Crash.
    Nicht existierende Datei: leere Liste zurück, kein Crash.
    """
    if isinstance(source, str):
        path = source if source else resolve_jsonl_path(env)
        try:
            with open(path, encoding="utf-8") as f:
                lines: Iterable[str] = f
                return _parse_lines(lines, tail_days=tail_days, today=today)
        except FileNotFoundError:
            return []
        except OSError as e:
            logger.warning("tools.llm.telemetry_read: konnte JSONL nicht lesen (%s): %s", path, e)
            return []
    else:
        return _parse_lines(source, tail_days=tail_days, today=today)


def _parse_lines(
    lines: Iterable[str],
    *,
    tail_days: int | None,
    today: date | None,
) -> list[dict]:
    """Parst JSONL-Zeilen und wendet das Tail-Fenster an."""
    cutoff: date | None = None
    if tail_days is not None:
        ref = today if today is not None else date.today()
        cutoff = ref - timedelta(days=tail_days)

    result = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            # Defekte Zeile überspringen (LLMP-S4 Fehler-Robustheit).
            continue
        if not isinstance(entry, dict):
            continue

        if cutoff is not None:
            ts_str = entry.get("ts")
            if ts_str:
                try:
                    # ISO 8601: "2026-06-21T19:30:00Z" → date(2026, 6, 21)
                    entry_date = date.fromisoformat(str(ts_str)[:10])
                    if entry_date < cutoff:
                        continue
                except (ValueError, TypeError):
                    # Ungültiger ts → Eintrag behalten (defensiv).
                    pass

        result.append(entry)
    return result


def aggregate(
    events: list[dict],
    *,
    group_keys: tuple[str, ...],
) -> list[dict]:
    """Aggregiert Events pro Gruppe der `group_keys`.

    Summiert pro Gruppe: `calls` (Anzahl), `input_tokens`, `output_tokens`,
    `est_cost_eur`. Null-Preis-Semantik (OPEN-LLMP-A):
    - Wenn **alle** Beiträge einer Gruppe `est_cost_eur: None` haben → None (nicht 0).
    - Wenn mindestens ein Beitrag eine Zahl hat → Summe der Zahlen (None-Werte werden
      wie 0 behandelt).

    Fehlende Felder (`input_tokens`, `output_tokens`, `est_cost_eur` fehlen im Dict)
    werden als 0 bzw. None betrachtet (LLMP-S4 defensiv).

    Rückgabe: Liste von Dicts mit den group_keys-Feldern + calls, input_tokens,
    output_tokens, est_cost_eur.
    """
    # Pro Gruppe: {calls, input_tokens, output_tokens, cost_sum, cost_has_value}
    groups: dict[tuple, dict] = defaultdict(
        lambda: {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_sum": 0.0,
            "cost_has_value": False,
        }
    )

    for event in events:
        key = tuple(event.get(k) for k in group_keys)
        bucket = groups[key]
        bucket["calls"] += 1
        bucket["input_tokens"] += int(event.get("input_tokens") or 0)
        bucket["output_tokens"] += int(event.get("output_tokens") or 0)
        cost = event.get("est_cost_eur")
        if cost is not None:
            bucket["cost_sum"] += float(cost)
            bucket["cost_has_value"] = True

    result = []
    for key, bucket in groups.items():
        row: dict = {}
        for i, k in enumerate(group_keys):
            row[k] = key[i]
        row["calls"] = bucket["calls"]
        row["input_tokens"] = bucket["input_tokens"]
        row["output_tokens"] = bucket["output_tokens"]
        # Null-Preis: None wenn kein einziger Wert vorhanden (OPEN-LLMP-A).
        row["est_cost_eur"] = bucket["cost_sum"] if bucket["cost_has_value"] else None
        result.append(row)
    return result


def daily_series(
    events: list[dict],
    *,
    group_keys: tuple[str, ...],
    days: int,
    today: date,
) -> dict:
    """Baut pro Gruppe eine `days`-Tage-Zeitreihe (CONN-5).

    Rückgabe: Dict mit Gruppen-Key (Tupel) → Liste von `days` Dicts:
    [{datum: str(ISO), calls: int, est_cost_eur: float|None}, …]

    Fehlende Tage erhalten `calls=0`, `est_cost_eur=None`.

    Gruppen-Key im Rückgabe-Dict: Tupel der Gruppen-Werte (analog `aggregate`).
    """
    date_range = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]

    # Aufbau: group_key → date → {calls, cost_sum, cost_has_value}
    per_group: dict[tuple, dict[date, dict]] = defaultdict(
        lambda: {
            d: {"calls": 0, "cost_sum": 0.0, "cost_has_value": False}
            for d in date_range
        }
    )

    for event in events:
        key = tuple(event.get(k) for k in group_keys)
        ts_str = event.get("ts")
        if not ts_str:
            continue
        try:
            entry_date = date.fromisoformat(str(ts_str)[:10])
        except (ValueError, TypeError):
            continue
        if entry_date not in set(date_range):
            continue

        bucket = per_group[key][entry_date]
        bucket["calls"] += 1
        cost = event.get("est_cost_eur")
        if cost is not None:
            bucket["cost_sum"] += float(cost)
            bucket["cost_has_value"] = True

    result: dict = {}
    for key, days_map in per_group.items():
        series = []
        for d in date_range:
            bucket = days_map[d]
            series.append(
                {
                    "datum": d.isoformat(),
                    "calls": bucket["calls"],
                    "est_cost_eur": bucket["cost_sum"] if bucket["cost_has_value"] else None,
                }
            )
        result[key] = series

    return result


def monthly_rollup(
    events: list[dict],
    *,
    today: date | None = None,
    staleness_days: int = 90,
) -> dict:
    """Monats-Roll-up: Gruppiert Events nach month × caller × model × modality.

    Rückgabe-Dict mit den Schlüsseln:
    - `rows`: Liste von Dicts (analog `aggregate`), zusätzlich pro Gruppe:
      - `month` (str, „YYYY-MM")
      - `caller`, `model` (aus dem Event-Feld `model_id`), `modality`
      - `calls`, `input_tokens`, `output_tokens`, `est_cost_eur`
      - `cache_read_ratio`: cache_read_tokens / input_tokens (float 0..1)
        oder None wenn input_tokens == 0 oder das Feld im Event fehlt.
      - `calls_per_day`: calls / Anzahl distinkter Tage im Monat (float)
    - `warnings`: Liste von Staleness-Warnungen (sichtbar oben, ENTSCHEID-1268).
      Jede Warnung: {"model_id": str, "as_of": str, "age_days": int}.
      Nur Modelle, die in den Rows vorkommen und deren as_of älter als
      `staleness_days` Tage (relativ zu `today`) ist, tauchen auf.

    Topf-Trennung (ENTSCHEID-1268, xbuddy-prozess#73): Dieser Roll-up summiert
    NUR Laufzeit-/Produkt-Kosten. Die Trennung zwischen Laufzeit- und Bau-/
    Handoff-Topf läuft über die Log-Datei/den Host: ein Pi = eine
    provider_calls.jsonl = ein Laufzeit-Topf. `monthly_rollup` mischt keine
    fremden Töpfe — wer zwei Dateien zusammenwirft, bricht die Trennung selbst.

    `instance_id` VERTAGT (n=1, ENTSCHEID-1268): Nicht nach instance_id
    gruppiert. Bei n>1 Instanzen kommt die Trennung aus dem Datei-/Host-Schnitt
    (Hardware-Trennung, SVC-5), nicht aus einem Feld im Event.
    """
    ref_today = today if today is not None else date.today()

    # -- Pass 1: pro Gruppe akkumulieren ------------------------------------
    # Gruppen-Key: (month, caller, model_id, modality)
    GroupKey = tuple  # (month: str, caller: str|None, model_id: str|None, modality: str|None)

    buckets: dict[GroupKey, dict] = defaultdict(
        lambda: {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cost_sum": 0.0,
            "cost_has_value": False,
            "saw_none_cost": False,
            "distinct_days": set(),
        }
    )

    for event in events:
        ts_str = event.get("ts")
        if not ts_str:
            continue
        try:
            entry_date = date.fromisoformat(str(ts_str)[:10])
        except (ValueError, TypeError):
            continue

        month = entry_date.strftime("%Y-%m")
        caller = event.get("caller")
        model_id = event.get("model_id")
        modality = event.get("modality")  # None wenn nicht gesetzt (Chat/Text)
        key: GroupKey = (month, caller, model_id, modality)

        bucket = buckets[key]
        bucket["calls"] += 1
        bucket["input_tokens"] += int(event.get("input_tokens") or 0)
        bucket["output_tokens"] += int(event.get("output_tokens") or 0)
        bucket["cache_read_tokens"] += int(event.get("cache_read_tokens") or 0)
        bucket["distinct_days"].add(entry_date)

        cost = event.get("est_cost_eur")
        if cost is not None:
            bucket["cost_sum"] += float(cost)
            bucket["cost_has_value"] = True
        else:
            bucket["saw_none_cost"] = True

    # -- Pass 2: Rows bauen -------------------------------------------------
    rows = []
    seen_models: set[str] = set()

    for key, bucket in buckets.items():
        month, caller, model_id, modality = key

        input_tok = bucket["input_tokens"]
        cache_read = bucket["cache_read_tokens"]
        if input_tok > 0:
            cache_read_ratio: float | None = cache_read / input_tok
        else:
            cache_read_ratio = None

        n_days = len(bucket["distinct_days"])
        calls_per_day = bucket["calls"] / n_days if n_days > 0 else 0.0

        # cost_complete: False wenn €-tragende Gruppe mindestens einen None-Beitrag hat
        # (still-halbierte Summe, Antiberater-Fund 1, ENTSCHEID-1268:17).
        # True wenn alle Beiträge €-Werte haben ODER alle None sind (nix zu halbieren).
        cost_complete: bool = not (bucket["cost_has_value"] and bucket["saw_none_cost"])

        row: dict = {
            "month": month,
            "caller": caller,
            "model": model_id,  # Feld heißt im Roll-up "model" (kürzer)
            "modality": modality,
            "calls": bucket["calls"],
            "input_tokens": input_tok,
            "output_tokens": bucket["output_tokens"],
            "est_cost_eur": bucket["cost_sum"] if bucket["cost_has_value"] else None,
            "cost_complete": cost_complete,
            "cache_read_ratio": cache_read_ratio,
            "calls_per_day": calls_per_day,
        }
        rows.append(row)

        if model_id is not None:
            seen_models.add(model_id)

    # -- Pass 3: Staleness-Warnungen ----------------------------------------
    warnings = []
    for model_id in sorted(seen_models):
        as_of_str = as_of_for(model_id)
        if as_of_str is None:
            continue  # Kein bekanntes Datum → keine Warnung möglich.
        try:
            as_of_date = date.fromisoformat(as_of_str)
        except ValueError:
            continue
        age_days = (ref_today - as_of_date).days
        if age_days > staleness_days:
            warnings.append({
                "model_id": model_id,
                "as_of": as_of_str,
                "age_days": age_days,
            })

    # Rückgabe: warnings oben (ENTSCHEID-1268: sichtbar oben, nicht im Log versickern).
    return {
        "warnings": warnings,
        "rows": rows,
    }


def daten_ab(events: list[dict]) -> str | None:
    """Gibt das früheste ts-Datum im Fenster zurück (CONN-4 Marker).

    Rückgabe: ISO-Datumsstring (YYYY-MM-DD) oder None wenn kein gültiger ts.
    """
    earliest: date | None = None
    for event in events:
        ts_str = event.get("ts")
        if not ts_str:
            continue
        try:
            d = date.fromisoformat(str(ts_str)[:10])
        except (ValueError, TypeError):
            continue
        if earliest is None or d < earliest:
            earliest = d
    return earliest.isoformat() if earliest is not None else None
