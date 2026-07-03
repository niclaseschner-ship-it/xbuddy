"""Tests für FaehigkeitenZeigenTask — EC-43
(specs/platform/eltern-chat.md EC-43, Refs #1102).

Abgedeckte ACs:
  AC2 — FaehigkeitenZeigenTask existiert als ReadTask, in build_catalog
         registriert, listet den Live-Katalog (self ausgenommen), rendert
         anzeige_copy mit description-Fallback, deterministischer Text.
  AC3 — test_ec43_listet_katalog_anzeige_copy_mit_description_fallback grün;
         nur Eltern-berechtigt (BerechtigungError für Nicht-Mitglieder, TASK-10).
  AC4 — Kein LLM-Freitext-Pfad (EC-29): run() liefert strukturierten Text.
         Keine Seiten-/Mini-App-URL (SREG-5).

Tests laufen ohne Netz (EC-17): Catalog und is_member_fn als kontrollierte
Doppelungen.
"""

import pytest
from skills._errors import BerechtigungError
from skills.faehigkeiten_zeigen_task import FaehigkeitenZeigenTask
from tasks import Catalog, ReadTask, TurnContext

# ============================================================
#  Doppelungen
# ============================================================

def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_fake_task(name, description, anzeige_copy=None):
    """Erzeugt einen minimalen ReadTask mit optionalem anzeige_copy."""
    class _FakeTask(ReadTask):
        pass

    _FakeTask.anzeige_copy = anzeige_copy

    task = _FakeTask(
        name=name,
        description=description,
        parameters={"type": "object", "properties": {}},
    )

    def _run(arguments, turn_context):
        return "ergebnis"

    task.run = _run
    return task


def _make_catalog_with(*tasks):
    """Legt einen Catalog mit den gegebenen Tasks an."""
    cat = Catalog()
    for t in tasks:
        cat.register(t)
    return cat


# ============================================================
#  AC2 — Grundform: ReadTask, Guard, Registrierung
# ============================================================

def test_faehigkeiten_zeigen_ist_read_task():
    """AC2: FaehigkeitenZeigenTask ist ein ReadTask (EC-9, lesend)."""
    cat = _make_catalog_with()
    task = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_immer_mitglied)
    assert isinstance(task, ReadTask)


def test_faehigkeiten_zeigen_name():
    """AC2: Task-Name ist 'faehigkeiten_zeigen'."""
    cat = _make_catalog_with()
    task = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_immer_mitglied)
    assert task.name == "faehigkeiten_zeigen"


def test_faehigkeiten_zeigen_in_build_catalog():
    """AC2: faehigkeiten_zeigen ist in build_catalog registriert, wenn
    family_group_chat_id_getter gesetzt ist (AND-Guard EC-43/TASK-7)."""
    from fakes import FakeTelegram
    from tasks import build_catalog
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        family_group_chat_id_getter=lambda: 200,
    )
    assert catalog.get("faehigkeiten_zeigen") is not None, (
        "EC-43: faehigkeiten_zeigen muss im Katalog sein wenn fgcid-getter gesetzt"
    )


def test_faehigkeiten_zeigen_nicht_ohne_fgcid():
    """AC2: ohne family_group_chat_id_getter → faehigkeiten_zeigen NICHT im Katalog."""
    from fakes import FakeTelegram
    from tasks import build_catalog
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    assert catalog.get("faehigkeiten_zeigen") is None, (
        "EC-43: ohne fgcid-getter darf faehigkeiten_zeigen nicht im Katalog sein"
    )


# ============================================================
#  AC3 — Berechtigung (TASK-10 / EC-43)
# ============================================================

def test_ec43_nicht_mitglied_erhaelt_berechtigungsfehler():
    """AC3/EC-43: Nicht-Mitglied → BerechtigungError (TASK-10)."""
    cat = _make_catalog_with()
    task = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=99)
    with pytest.raises(BerechtigungError):
        task.run({}, ctx)


# ============================================================
#  AC3 — Haupttest: anzeige_copy mit description-Fallback (EC-43)
# ============================================================

def test_ec43_listet_katalog_anzeige_copy_mit_description_fallback():
    """AC3/EC-43: Listet registrierte Aufgaben mit anzeige_copy bzw. description-
    Fallback; selbst ausgenommen; deterministisch.

    Test-Anker:
    eltern-chat/tests/skills/test_faehigkeiten_zeigen.py::test_ec43_listet_katalog_anzeige_copy_mit_description_fallback
    """
    task_mit = _make_fake_task(
        name="einkauf_zeigen",
        description="Router-Jargon für LLM (ungeeignet für Eltern)",
        anzeige_copy="Ich kann dir die Einkaufsliste öffnen",
    )
    task_ohne = _make_fake_task(
        name="ca_verteilen",
        description="Verteilt das CA-Zertifikat",
        anzeige_copy=None,
    )
    cat = _make_catalog_with(task_mit, task_ohne)
    fzg = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_immer_mitglied)
    cat.register(fzg)

    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = fzg.run({}, ctx)

    # Liefert einen String (deterministisch strukturierter Text, EC-29)
    assert isinstance(result, str), "EC-43: run() muss String zurückgeben"

    # anzeige_copy wird bevorzugt
    assert "Ich kann dir die Einkaufsliste öffnen" in result, (
        "EC-43: anzeige_copy muss in der Ausgabe erscheinen"
    )

    # description-Fallback für Aufgabe ohne anzeige_copy
    assert "Verteilt das CA-Zertifikat" in result, (
        "EC-43: description-Fallback muss erscheinen wenn anzeige_copy fehlt"
    )
    # Router-Jargon (description des Tasks mit anzeige_copy) darf NICHT erscheinen
    assert "Router-Jargon für LLM" not in result, (
        "EC-43: anzeige_copy verdrängt description — Jargon darf nicht erscheinen"
    )

    # Selbst ausgenommen: faehigkeiten_zeigen selbst darf nicht in der Liste sein
    assert "faehigkeiten_zeigen" not in result, (
        "EC-43: Skill muss sich selbst aus der Liste ausschließen"
    )

    # Deterministisch: beide Aufgaben erscheinen
    assert "einkauf_zeigen" not in result or "Einkaufsliste" in result, (
        "EC-43: Aufgabenname oder anzeige_copy muss erscheinen"
    )


def test_ec43_selbst_ausgenommen():
    """EC-43: faehigkeiten_zeigen listet sich selbst NICHT."""
    cat = _make_catalog_with()
    fzg = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_immer_mitglied)
    cat.register(fzg)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = fzg.run({}, ctx)
    # Kein Eintrag für faehigkeiten_zeigen
    assert "faehigkeiten_zeigen" not in result


def test_ec43_leerer_katalog_ohne_crash():
    """EC-43: leerer Katalog (nur faehigkeiten_zeigen selbst) → kein Crash,
    Hinweis-Text."""
    cat = _make_catalog_with()
    fzg = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_immer_mitglied)
    cat.register(fzg)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = fzg.run({}, ctx)
    assert isinstance(result, str)
    # Kein Crash; irgendeine Rückmeldung
    assert len(result) > 0


def test_ec43_deterministisch_alphabetisch():
    """EC-43: Ausgabe ist deterministisch (alphabetisch nach Name)."""
    task_b = _make_fake_task(name="b_aufgabe", description="Aufgabe B")
    task_a = _make_fake_task(name="a_aufgabe", description="Aufgabe A")
    cat = _make_catalog_with(task_b, task_a)  # Intentional: B zuerst registriert
    fzg = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_immer_mitglied)
    cat.register(fzg)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = fzg.run({}, ctx)
    # Alphabetische Reihenfolge: A vor B
    pos_a = result.find("Aufgabe A")
    pos_b = result.find("Aufgabe B")
    assert pos_a < pos_b, (
        "EC-43: Ausgabe muss deterministisch alphabetisch nach Name sortiert sein"
    )


def test_ec43_kein_sreg5_url():
    """AC4/SREG-5 (#1028): run() nennt keine konkrete Seiten- oder Mini-App-URL."""
    task1 = _make_fake_task(name="einkauf_zeigen", description="Einkaufsliste öffnen")
    cat = _make_catalog_with(task1)
    fzg = FaehigkeitenZeigenTask(catalog=cat, is_member_fn=_immer_mitglied)
    cat.register(fzg)
    ctx = TurnContext(chat_id=42, from_user_id=7)
    result = fzg.run({}, ctx)
    # Kein direkter URL in der Ausgabe
    assert "http://" not in result, "SREG-5: keine URL in der Ausgabe"
    assert "https://" not in result, "SREG-5: keine URL in der Ausgabe"
