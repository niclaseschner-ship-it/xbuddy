"""Familien-Registry — siehe specs/platform/familie.md (Refs #38).

Die Registry läuft als schlanke eigenständige Flask-App — ein Geschwister von
router/, eltern-chat/ und plan/. Sie besitzt die Personen-Daten der Familie
(FAM-1) und stellt sie über eine Schnittstelle bereit (FAM-7).

Dieses Verzeichnis ist ein Paket, damit `familie.main` und `familie.registry`
eindeutige Modulnamen tragen und beim repo-weiten pytest-Lauf nicht mit den
gleichnamigen main-Modulen anderer Komponenten kollidieren (#52) — analog
plan/ und tools/zugangsdaten/. plan/ konsumiert `familie.registry` ohnehin bereits
als Paket.

Module:
  registry — Personen-Modell + Datenhaltung (FAM-1/2/6/7)
  main     — Flask-App: Personen- und Foto-Schnittstellen (FAM-7/8)
"""
