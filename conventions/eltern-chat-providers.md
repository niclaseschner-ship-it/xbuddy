# Eltern-Chat: KI-Anbieter-Adapter

> Rewrite #1537 (2026-07-28). #1510 hat die Provider-Klassen
> (`providers/{claude,mistral}.py`) gelöscht — der Motor-Call läuft jetzt über
> `tools.llm`. Der Brand-Vendor eines Adapters ist damit vom Klassen-Attribut in
> die Map `_ADAPTER_BRAND_VENDOR` (`onboarding_store.py`) gewandert; `get_provider_class`
> und die alte `test_providers.py`-Drift-Sperre existieren nicht mehr. Der Text
> unten ist der gültige Stand.

Konvention für die Adapter-Namen-→-Brand-Vendor-Auflösung im Eltern-Chat. Refs
specs/platform/eltern-chat.md (EC-11), specs/platform/zugangsdaten.md (ZD-2),
RAT-7 (Konventionen entstehen bei wiederkehrender Sache).

Auslöser: Welle-A-Watchdog auf #1019 (T663) — der Lookup „welcher
Brand-Vendor gehört zu welchem Adapter" lebte zweimal: einmal als
`ADAPTER_TO_VENDOR`-Dict in `eltern-chat/onboarding_store.py`, implizit ein
zweites Mal als Lazy-Import-Bedingung in `providers/__init__.py`. Drift
sichtbar: das Dict listete `openai` und `azure-openai`, die in
`get_provider()` nicht existierten. Mit #1510 sind die Provider-Klassen ganz
gefallen; die Zuordnung lebt seitdem an genau einer Stelle (siehe unten).

## ECP-1 — Brand-Vendor lebt in der zentralen Adapter-Map

**Vorschrift.** Der Brand-Vendor-Slug eines Adapter-Namens lebt in der Map
`_ADAPTER_BRAND_VENDOR` in `eltern-chat/onboarding_store.py` und wird
ausschließlich über `vendor_slug_for_adapter(adapter_name)` gelesen:

```python
_ADAPTER_BRAND_VENDOR = {
    "claude": "anthropic",
    "mistral": "mistral",
}
```

Der Brand-Vendor-Slug folgt der ZD-2-Tabelle
(`specs/platform/zugangsdaten.md`) und ist Eingabe für den
Zugangsdaten-Slot-Namen (`eltern-chat-<brand_vendor>-api-key`, gebaut über
`zd_name_provider_api_key`). Ein Adapter-Name, der nicht in der Map steht, wird
1:1 als Brand-Vendor zurückgegeben (Passthrough für künftige Adapter, deren
Adapter-Name dem Brand-Vendor entspricht).

**Eine Wahrheitsquelle.** Wer den Brand-Vendor eines Adapters sucht, ruft
`vendor_slug_for_adapter(adapter_name)`. Die EINE Wahrheitsquelle IST diese Map:
kein Klassen-Attribut (`provider_class.brand_vendor` ist mit #1510 gelöscht),
kein zweites Dict, keine Registry-Datei. Wer einen neuen Adapter ergänzt, fügt
GENAU einen Map-Eintrag hinzu — jeder Konsument (Slot-Namen-Bau,
Modell-Default-Lookup in `providers/lib_adapter.py`) zieht ihn automatisch.

**Folge für den Lookup-Helper.** `vendor_slug_for_adapter(adapter_name)` liest den
Slug direkt aus `_ADAPTER_BRAND_VENDOR` — nicht mehr über eine
Provider-Klasse (`get_provider_class` existiert nicht mehr). Der abgeleitete
ZD-Slot-Name (`zd_name_provider_api_key`) baut auf demselben Helper auf, damit
Slot-Name und Brand-Vendor nicht auseinanderdriften.

**Drift-Sperre maschinell.** Der Test
`eltern-chat/tests/test_onboarding_store.py::test_ECP_1_adapter_map_is_single_source_of_truth`
prüft: jeder Eintrag der Map `_ADAPTER_BRAND_VENDOR` hat einen nicht-leeren
String-Slug, und der daraus abgeleitete ZD-Slot-Name
(`eltern-chat-<brand_vendor>-api-key`) steht wörtlich in der ZD-2-Tabelle
(`specs/platform/zugangsdaten.md`). Drift zwischen der Map und der ZD-2-Tabelle
wird vom Test gesperrt.

**Wann diese Klausel wächst.** Wenn ein dritter Buddy eigene
Anbieter-Adapter mit eigener Namens-→-Vendor-Auflösung führt (heute nur
eltern-chat; Hörspiel hat eigene Slot-Namen, aber keine eigene Adapter-Map),
wird die Klausel zu einer allgemeinen `providers.md` hochgezogen — vorher nicht
(RAT-7, „kein Vorrat").
