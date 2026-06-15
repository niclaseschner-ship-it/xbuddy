"""Geteilte Standard-Quittungen für Klasse-C-Skills (TASK-10d).

Heimat der vier kanonisierten Quittungs-Texte, die in allen
Klasse-C-Katalog-Aufgaben vorkommen:

  abgelehnt(skill_verb)          — Nicht-Mitglied, kein Schreiben
  nicht_erreichbar(buddy_name)   — Buddy-API nicht erreichbar
  grenze(buddy_name, aktion, detail) — Buddy lehnt Aktion mit Grund ab
  KEINE_ICONS                    — Icon-Suche ohne Treffer (Template-String)

Konsumenten heute: routine_punkte_setzen_task, gericht_anlegen_task,
plan_aktivitaeten_setzen_task (gebaut mit TASK-10d #817).

Pflicht-Klausel: wer einen Klasse-C-Skill baut oder anfasst, nutzt
diese Helper für die vier Standard-Quittungen. Custom-Quittungen
(skill-eigene Erfolgs-Texte, _NICHTS_ZU_TUN_*-Varianten) bleiben
skill-lokal — sie tragen skill-eigene Semantik.
"""


def abgelehnt(skill_verb: str) -> str:
    """Quittung: Aufrufer ist kein Familien-Mitglied.

    `skill_verb` ist der Skill-Name als Verb-Phrase,
    z. B. 'Routine-Punkte setzen' oder 'Gericht anlegen'.
    """
    return "%s geht nur für Mitglieder der Familien-Gruppe." % skill_verb


def nicht_erreichbar(buddy_name: str) -> str:
    """Quittung: Buddy-API ist gerade nicht erreichbar.

    `buddy_name` ist der Name des Buddys, z. B. 'Routine-Buddy'
    oder 'Essens-Buddy'.
    """
    return (
        "Der %s ist gerade nicht erreichbar — bitte gleich nochmal "
        "versuchen." % buddy_name
    )


def grenze(buddy_name: str, aktion: str, detail: str) -> str:
    """Quittung: Buddy hat die Aktion mit einem Grund abgelehnt.

    `buddy_name` ist der Name des Buddys, z. B. 'Routine-Buddy'.
    `aktion` ist die Aktions-Nominalphrase, z. B. 'die Änderung'
    oder 'die Anlage'.
    `detail` ist die Begründung aus der Buddy-Antwort.
    """
    return "Der %s hat %s abgelehnt: %s" % (buddy_name, aktion, detail)


# Template-String für Icon-Suche ohne Treffer.
# Konsumenten: `KEINE_ICONS.format(label=<label>)`.
KEINE_ICONS = (
    "Ich habe für »{label}« kein Piktogramm gefunden — sag mir ein anderes "
    "Wort (Synonym), und ich suche erneut."
)
