# Eltern-Chat: KI-Anbieter-Adapter

Konvention für die KI-Anbieter-Adapter unter `eltern-chat/providers/`. Refs
specs/platform/eltern-chat.md (EC-11), specs/platform/zugangsdaten.md (ZD-2),
RAT-7 (Konventionen entstehen bei wiederkehrender Sache).

Auslöser: Welle-A-Watchdog auf #1019 (T663) — der Lookup „welcher
Brand-Vendor gehört zu welchem Adapter" lebte zweimal: einmal als
`ADAPTER_TO_VENDOR`-Dict in `eltern-chat/onboarding_store.py`, implizit ein
zweites Mal als Lazy-Import-Bedingung in `providers/__init__.py`. Drift
sichtbar: das Dict listete `openai` und `azure-openai`, die in
`get_provider()` nicht existieren.

## ECP-1 — Provider-Self-Declaration: Brand-Vendor lebt am Adapter

**Vorschrift.** Jede Provider-Klasse unter `eltern-chat/providers/` trägt
ihren Brand-Vendor-Slug als Klassen-Attribut:

```python
class ClaudeProvider:
    brand_vendor = "anthropic"
    ...

class MistralProvider:
    brand_vendor = "mistral"
    ...
```

Der Brand-Vendor-Slug folgt der ZD-2-Tabelle
(`specs/platform/zugangsdaten.md`) und ist Eingabe für den
Zugangsdaten-Slot-Namen (`eltern-chat-<brand_vendor>-api-key`).

**Eine Wahrheitsquelle.** Wer den Brand-Vendor eines Adapters sucht,
liest `provider_class.brand_vendor`. Es gibt keine zweite Tabelle, kein
Dict im Onboarding-Store, keine Registry-Datei. Wer einen neuen Adapter
ergänzt, fügt das Attribut hinzu — der Lookup zieht es automatisch.

**Folge für den Lookup-Helper.** `vendor_slug_for_adapter(adapter_name)`
(heute in `eltern-chat/onboarding_store.py`) löst den Adapter-Namen über
`providers.get_provider_class` zur Klasse und liest `brand_vendor` daraus —
nicht aus einem separaten Mapping.

**Drift-Sperre maschinell.** Ein Test in
`eltern-chat/tests/test_providers.py` prüft: jede Provider-Klasse, die
`iter_provider_classes()` liefert, trägt das Attribut, der Wert ist ein
nicht-leerer String, und für jeden bekannten `adapter_name` matcht der
Slug die zugehörige ZD-2-Tabellen-Zeile. Drift zwischen der Registry
und `brand_vendor` wird vom Test gesperrt.

**Wann diese Klausel wächst.** Wenn ein dritter Buddy eigene
Anbieter-Adapter führt (heute nur eltern-chat; Hörspiel hat eigene
Slot-Namen, aber keine eigenen LLM-Provider-Klassen), wird die Klausel
zu einer allgemeinen `providers.md` hochgezogen — vorher nicht (RAT-7,
„kein Vorrat").
