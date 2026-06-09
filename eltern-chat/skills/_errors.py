"""Geteilte Exception-Klassen für eltern-chat-Skills.

Heimat des Berechtigungs-Bruch-Patterns (TASK-10 / EC-29-Migration #551):
Eine Aufgabe, die feststellt, dass der Aufrufer nicht berechtigt ist
(kein Familien-Mitglied), wirft BerechtigungError aus dem Agent-Loop-Frame.
Der Agent-Loop (agent.py) fängt sie als is_error=True-Tool-Result; das
LLM antwortet entsprechend.

Analog `EssenClientError` (eltern-chat/skills/essen_client.py) — einfache
Exception-Klasse, kein Klassen-Hierarchie-Vorbau (CLAUDE.md §6: nichts
auf Vorrat anlegen).
"""


class BerechtigungError(Exception):
    """Aufrufer ist kein Familien-Mitglied — Skill bricht ab."""
