"""Hörspiel-Buddy — TTS-Adapter (HSP-13).

V1 liefert ausschließlich den Azure-OpenAI-Adapter (`azure.py`). Das Pattern
ist analog zu `providers/` aufgebaut (Basis-Schnittstelle + konkrete
Implementierung), damit ein zweiter TTS-Anbieter (OPEN-HSP-F ElevenLabs) in
V2 als neue Datei landen kann, ohne `tts_service.py` zu ändern.
"""
