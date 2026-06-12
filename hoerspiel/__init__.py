"""Hörspiel-Buddy-App — XBuddy-App mit Buddy-Slug `hoerspiel` (Refs #729).

Siehe specs/buddies/hoerspiel.md. Der Hörspiel-Buddy besitzt seine Daten
(Welt-Bible, Folgen-Historie, Album-Manifeste + Audio-Assets), seine
Funktion (LLM-Folgen-Erzeugung, TTS-Pipeline, Album-Sequencing) und stellt
das Ergebnis über seine Display-View bereit (HSP-1, APP-1).

Module:
  config          — Runtime-/Daten-Config-Auflösung (HSP-26/HSP-27)
  data_io         — JSON/Markdown read + atomic-write Helfer (DCOMP-4)
  album_manifest  — Manifest-Schema + Sortierung (HSP-5/6/9/26)
  album_builder   — TTS-Pipeline + Bündel-Logik + Idempotenz (HSP-14/15/16)
  llm_service     — Provider-Switch + Folgen-Vorschlag + Synopse (HSP-10/11)
  tts_service     — Voice-Resolution + Shared-Assets-Status (HSP-13/22/29)
  providers/      — LLM-Adapter (V1: claude), kopierfähiges Pattern (HSP-10)
  tts/            — TTS-Adapter (V1: azure)
  main            — Flask-App + alle HSP-17-Endpoints + Entrypoint (HSP-28)
"""
