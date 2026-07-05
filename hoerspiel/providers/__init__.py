"""Hörspiel-Buddy — LLM-Provider-Adapter (HSP-10).

T1084/#1084: Der strukturierte Folgen-Pfad (HSP-11, `complete_structured`) und
der Freitext-Synopse-Pfad (HSP-16, `complete`) laufen seit #1281 vollständig
über die geteilte Library `tools.llm`, gekapselt im `LibSingleshotAdapter`
(`lib_adapter.py`). Die alten direkten Anbieter-Adapter wurden mit #1281
entfernt; nur Modell-Konstanten (AVAILABLE_MODELS) verbleiben.
"""
