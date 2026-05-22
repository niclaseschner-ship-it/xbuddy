"""XBuddy Router V1 — siehe specs/platform/router.md (Refs #5).

Der Router ist eine schlanke eigenständige Flask-App — ein Geschwister von
familie/, eltern-chat/ und plan/. Adapter und Routing-Kern sind strikt
getrennt (ROU-1).

Dieses Verzeichnis ist ein Paket, damit `router.main` einen eindeutigen
Modulnamen trägt und beim repo-weiten pytest-Lauf nicht mit den gleichnamigen
main-Modulen anderer Komponenten kollidiert (#52) — analog plan/ und
zugangsdaten/.

Module:
  main — Flask-App: Event-Schnittstelle, Routing-Kern, State je Display
"""
