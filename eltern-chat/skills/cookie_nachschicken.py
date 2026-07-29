"""Pairing-Cookie nachschicken — frischer Pairing-Link auf Nachfrage
(Refs #1380, Nic-Setzung 2026-07-07; RAT-31 E6c 2026-07-29).

GAA-3.8 mintet einen Pairing-Link EINMALIG auf die »Gerät koppeln«-Bitte.
Der Link gilt 15 Minuten — läuft er ab, bevor Eltern ihn am Zielgerät
öffnen, braucht es einen NEUEN Link. Diese Funktion mintet ihn auf Nachfrage.

RAT-31 E6c: es gibt **keine geraete-Registry mehr**. Die Funktion listet
keine Geräte mehr auf und sucht kein bestehendes Gerät — sie mintet einfach
einen frischen Pairing-Link (`<origin>/auth/pair?token=<X>`, HMAC mit dem
Bot-Token, 15 Minuten, auf die **Funnel-FQDN** — LE-Cert, Familien-Geräte
brauchen so kein Zertifikat, nur den Cookie, auth.md AUTH-2). Der
Erwachsenen-Gate und die DM-Zustellung leben in der aufrufenden Aufgabe
(`cookie_nachschicken_task`).
"""

from skills.geraet_anlegen import baue_pairing_link

__all__ = ["baue_pairing_link"]
