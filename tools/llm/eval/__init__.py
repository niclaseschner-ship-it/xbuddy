# SYNTHETIC - kein echter Familientext (Privacy-Gate-Marker, T1315)
"""Golden-Set Eval-Paket für `tools.llm` (T1315).

Drei Teilmodule:
- `fixtures`  — 12 synthetische Testfälle (GoldenFixture-Dicts)
- `assertions` — deterministische Assertion-Funktionen ohne LLM-Call
- `runner`     — verbindet Fixture + Fakes + Assertions; kein Netz

Privacy-Gate: `privacy_gate.py` scannt alle Fixture-Texte auf
Familientext-Marker; läuft in pytest + als Standalone-Skript.
"""
