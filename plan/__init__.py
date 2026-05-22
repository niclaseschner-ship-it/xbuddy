"""Plan-Buddy-App — XBuddy-App mit Buddy-Slug `plan` (Refs #40).

Siehe specs/buddies/plan.md. Die App zeigt einer Familie ihren Wochenplan
auf einem Display: Verantwortlichkeiten, Kind-Aktivitäten und Termine.

Sie besitzt ihre Daten (Verantwortlichkeiten in plan.db) und ihre Funktion
(Kalender-Anbindung) und stellt beides über Schnittstellen bereit (PLAN-1,
E-PLAN-1). Was sie nicht selbst besitzt, holt sie von zentralen Komponenten:
Personen-Identität von der Familien-Registry, Geheimnisse vom
Zugangsdaten-Speicher.

Module:
  config    — Slot-Definitionen + Default-Verantwortlichkeiten (PLAN-6/10/28)
  db        — SQLite-Datenhaltung der Verantwortlichkeiten (PLAN-8/9)
  kalender  — Google-Kalender-Anbindung mit Test-Naht (PLAN-15…20, PLAN-29)
  render    — View-Modell der View `woche` (PLAN-3…14)
  main      — Flask-App: Display-Views + Schnittstellen (PLAN-21/22/23)
"""
