"""Vendor-File-Verzeichnis für `tools.llm` (LLMP-4).

Eine Datei je Vendor-Slug; jede deklariert `CAPABILITIES = frozenset({...})`
am Modulkopf (Watchdog-Regel LLMP-4). Externe Importe gehen **nur** über
`from tools.llm import …` — der Unterstrich macht die Privat-Natur sichtbar
(LLMP-4 Re-Export-Form, analog `tools.zugangsdaten`).
"""
