"""Hörspiel-Buddy — LLM-Provider-Adapter (HSP-10).

V1 liefert ausschließlich `claude`. Das Pattern ist kopierfähig vorbereitet
(`base.py` + `claude.py`); ein zweiter Provider landet in V2 als neue Datei
hinter derselben Basis-Schnittstelle.

T1084: Der strukturierte Folgen-Pfad (HSP-11, `complete_structured`) läuft seit
#1084 über die geteilte Library `tools.llm` (Singleshot-Sicht), gekapselt im
`LibSingleshotAdapter` (`lib_adapter.py`). Der Freitext-Synopse-Pfad (HSP-16,
`complete`) bleibt ADDITIV beim Alt-Provider (`claude.py`/`mistral.py`), bis ein
Folge-Ticket auch ihn migriert (tools.llm hat heute keine reine Text-Sicht).
"""
