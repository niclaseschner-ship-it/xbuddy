"""EC-45 mechanischer Zustands-Wächter — keine Einkaufslisten-Behauptung ohne
Nachsehen.

specs/platform/eltern-chat.md EC-45 (Nic-Verdikt 2026-09-05, #1919): EC-30
verbietet dem Modell seit langem, XBuddy-Zustand aus Welt-Wissen zu erfinden —
bis zu diesem Wächter existierte die Regel nur als Prosa im SYSTEM_PROMPT,
kein Code prüfte sie. Live-Befund #1919: auf „zeig mir die Einkaufsliste"
antwortete das Modell mit erfundenen Listen-Einträgen, statt den
`einkauf_zeigen`-Mini-App-Knopf zu senden (EZG-8).

Bauform (EC-45, dieselbe Naht wie der EC-41-Knopf-Filter
`_markdown_button_strip.py`): kein Werkzeug-Zwang im Agent-Loop, sondern eine
deterministische Prüfung der FERTIGEN Antwort — sie wird ersetzt, wenn sie
Einkaufslisten-Inhalt behauptet, ohne dass `einkauf_zeigen` im selben Turn
gelaufen ist. Der Wächter urteilt über die Antwort, nicht über die Absicht.

Scope dieser Ausbaustufe: die Einkaufsliste (EZG) — der einzige belegte
Live-Fall. Die übrigen EC-30-Zustandsdomänen (Kalender, Routinen,
Familien-Mitglieder, Seiten-Übersicht …) bekommen ihre eigene Erweiterung
erst mit einem eigenen belegten Fall (EC-41-Präzedenz: Pattern kommen aus
echten Halluzinationen, nicht aus Vorratsbau).

Die EC-41-Ermahnung in den Werkzeug-Beschreibungen bleibt bestehen (Auflage
im Verdikt zu #1919) — dieser Wächter ergänzt sie, ersetzt sie nicht.
"""

import re

# Einkaufsliste-Nennung, gefolgt von einer Bullet-/Nummern-Aufzählung.
_LISTEN_INHALT_BULLETS = re.compile(
    r"(?:Einkaufsliste|Einkaufszettel|Shoppingliste)[^\n]{0,60}:?\s*\n"
    r"(?:\s*(?:[-•*]|\d+[.)])\s*[^\n]+\n?){1,}",
    re.IGNORECASE,
)

# Einkaufsliste-Nennung, gefolgt von einer Komma-Aufzählung in derselben Zeile
# (z. B. „Auf deiner Einkaufsliste stehen: Milch, Brot, Eier.").
_LISTEN_INHALT_INLINE = re.compile(
    r"(?:Einkaufsliste|Einkaufszettel|Shoppingliste)[^\n:]{0,60}:\s*"
    r"[^\n,]+,\s*[^\n,]+",
    re.IGNORECASE,
)

# EC-45-Ersatztext: sagt ehrlich, dass nicht nachgesehen wurde, und zeigt auf
# den Weg, der es kann (spec-Wortlaut).
_ERSATZTEXT = (
    "Ich habe gerade nicht in die Einkaufsliste geschaut und kann dir also "
    "nicht sagen, was draufsteht. Frag nochmal gezielt nach der "
    "Einkaufsliste, dann hole ich sie mit dem Mini-App-Knopf."
)


def guard_einkaufsliste_behauptung(text, einkauf_gelesen):
    """EC-45: ersetzt eine erfundene Einkaufslisten-Behauptung durch Ehrlichkeit.

    Args:
      text: der fertige Antwort-Text (nach dem EC-41-Markdown-Strip).
      einkauf_gelesen: True, wenn `einkauf_zeigen` (EZG-8) in diesem Turn
        aufgerufen wurde — dann darf der Text über die Liste reden, er hat
        nachgesehen.

    Returns:
      `_ERSATZTEXT`, wenn `text` ohne `einkauf_gelesen` konkreten
      Listen-Inhalt behauptet; sonst den unveränderten `text`.
    """
    if einkauf_gelesen or not text:
        return text
    if _LISTEN_INHALT_BULLETS.search(text) or _LISTEN_INHALT_INLINE.search(text):
        return _ERSATZTEXT
    return text
