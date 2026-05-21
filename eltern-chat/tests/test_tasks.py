"""Tests für den Aufgaben-Katalog-Rahmen — EC-8/EC-9/EC-10 (Refs #27)."""

import pytest

from conftest import FakeReadTask, FakeWriteTask
from model import READ, WRITE
from tasks import Catalog, build_catalog


def test_EC_8_register_and_get():
    cat = Catalog()
    task = FakeReadTask(name="wetter")
    cat.register(task)
    assert cat.get("wetter") is task


def test_EC_8_unknown_task_returns_none():
    """Eine nicht registrierte Aufgabe ist nicht im Katalog."""
    assert Catalog().get("gibt_es_nicht") is None


def test_EC_8_duplicate_registration_is_rejected():
    cat = Catalog()
    cat.register(FakeReadTask(name="wetter"))
    with pytest.raises(ValueError):
        cat.register(FakeReadTask(name="wetter"))


def test_EC_8_task_defs_are_provider_neutral():
    cat = Catalog()
    cat.register(FakeReadTask(name="lesen"))
    cat.register(FakeWriteTask(name="schreiben"))
    defs = {d.name: d for d in cat.task_defs()}
    assert defs["lesen"].kind == READ
    assert defs["schreiben"].kind == WRITE


def test_EC_9_read_task_kind_is_read():
    assert FakeReadTask().kind == READ


def test_EC_10_write_task_kind_is_write():
    assert FakeWriteTask().kind == WRITE


def test_EC_8_build_catalog_v1_is_empty():
    """V1 registriert keine konkrete Aufgabe — die erste kommt aus eigenem Ticket."""
    assert build_catalog().task_defs() == []
