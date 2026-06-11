# -*- coding: utf-8 -*-
"""
test_mac_contacts.py — Resolución nombre↔número de la agenda de Apple.

Sin AppleScript ni I/O: inyecta una caché falsa. Caracteriza la normalización de
acentos (el bug de "Mama" vs "Mamá") y el código de país de los números locales.
"""
import pytest

from core import mac_contacts as mc


def test_norm_strips_accents_and_case():
    assert mc._norm("Mamá") == "mama"
    assert mc._norm("PAPÁ") == "papa"
    assert mc._norm("  José  ") == "jose"
    assert mc._norm("Niño") == "nino"


def test_natl_last10():
    assert mc._natl("573000000001") == "3000000001"
    assert mc._natl("3000000001") == "3000000001"
    assert mc._natl("123") == "123"


def test_intl_country_code():
    # número local de 10 dígitos → se antepone el código país
    assert mc._intl("300-000-0001", "3000000001", "57") == "573000000001"
    # ya internacional (con +) → se respeta
    assert mc._intl("+57 300 000 0001", "573000000001", "57") == "573000000001"
    # corto (no 10 dígitos) → sin tocar
    assert mc._intl("123", "123", "57") == "123"


@pytest.fixture
def fake_cache(monkeypatch):
    data = {
        "by_name": [
            ["Mamá", "573000000001"],
            ["Papá", "573000000002"],
            ["Mama Norma", "573000000003"],
            ["José Pérez", "573001112233"],
        ],
        "by_natl": {
            "3000000001": "Mamá",
            "3000000002": "Papá",
            "3000000003": "Mama Norma",
        },
        "built": 9e9,
        "count": 4,
    }
    monkeypatch.setattr(mc, "get_cache", lambda: data)
    return data


def test_find_by_name_accent_insensitive(fake_cache):
    # "Mama" (sin tilde) debe encontrar "Mamá" PRIMERO (match exacto normalizado)
    res = mc.find_by_name("Mama")
    assert res, "no encontró nada"
    assert res[0] == ("Mamá", "573000000001")


def test_find_by_name_exact_with_accent(fake_cache):
    # el match exacto ("Mamá") va PRIMERO; puede haber parciales después (Mama Norma)
    res = mc.find_by_name("mamá")
    assert res[0] == ("Mamá", "573000000001")


def test_find_by_name_partial(fake_cache):
    res = mc.find_by_name("jose")
    assert ("José Pérez", "573001112233") in res


def test_name_for_phone_reverse(fake_cache):
    assert mc.name_for_phone("573000000001") == "Mamá"
    assert mc.name_for_phone("3000000002") == "Papá"   # sin código país igual resuelve
    assert mc.name_for_phone("000000") == ""           # desconocido
