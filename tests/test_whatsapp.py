# -*- coding: utf-8 -*-
"""
test_whatsapp.py — Lógica pura de resolución de WhatsApp (sin red ni SQLite).

Caracteriza: normalización de acentos, _resolve_phone (número directo + contactos
locales) y sender_to_name (LID→número→nombre) con dependencias mockeadas.
"""
import pytest

from actions import whatsapp as wa


def test_norm_accents():
    assert wa._norm("Mamá") == wa._norm("mama") == "mama"
    assert wa._norm("Tío Toño") == "tio tono"


def test_resolve_phone_direct_number():
    # 8+ dígitos → se usa tal cual (sin '+')
    phone, target = wa._resolve_phone("+57 300 000 0004", {})
    assert phone == "573000000004"


def test_resolve_phone_local_contact():
    contacts = {"juan": {"name": "Juan", "phone": "573001112233"}}
    phone, target = wa._resolve_phone("Juan", contacts)
    assert phone == "573001112233"
    assert target == "Juan"


def test_resolve_phone_unknown():
    phone, target = wa._resolve_phone("Fulano", {})
    assert phone == ""


def test_sender_to_name_number(monkeypatch):
    # número conocido en la agenda → nombre
    monkeypatch.setattr("core.mac_contacts.name_for_phone",
                        lambda p: "Mamá" if p == "573000000001" else "")
    assert wa.sender_to_name("573000000001@s.whatsapp.net") == "Mamá"


def test_sender_to_name_lid(monkeypatch):
    # LID → número (vía mapeo del bridge) → nombre de la agenda
    monkeypatch.setattr(wa, "_lid_to_phone", lambda lid: "573000000001")
    monkeypatch.setattr("core.mac_contacts.name_for_phone",
                        lambda p: "Mamá" if p == "573000000001" else "")
    assert wa.sender_to_name("11111111111111@lid") == "Mamá"


def test_sender_to_name_unknown_falls_back_to_number(monkeypatch):
    monkeypatch.setattr("core.mac_contacts.name_for_phone", lambda p: "")
    assert wa.sender_to_name("573999999999@s.whatsapp.net") == "+573999999999"


def test_sender_bare_lid_resolves_via_chat_jid(monkeypatch):
    # En messages.db el sender viene PELADO y el @lid está solo en chat_jid
    # (bug real: mostraba '+22222222222222' como si fuera un teléfono).
    monkeypatch.setattr(wa, "_lid_to_phone",
                        lambda lid: "573000000005" if lid == "22222222222222" else "")
    monkeypatch.setattr("core.mac_contacts.name_for_phone",
                        lambda p: "Ana" if p == "573000000005" else "")
    assert wa.sender_to_name("22222222222222", "22222222222222@lid") == "Ana"


def test_sender_bare_lid_without_marker_still_maps(monkeypatch):
    # Red final: ni siquiera hay @lid en ningún campo → igual intenta el mapeo
    monkeypatch.setattr(wa, "_lid_to_phone",
                        lambda lid: "573000000005" if lid == "22222222222222" else "")
    monkeypatch.setattr("core.mac_contacts.name_for_phone",
                        lambda p: "Ana" if p == "573000000005" else "")
    assert wa.sender_to_name("22222222222222", "") == "Ana"


def test_sender_lid_unmapped_shows_real_phone_if_possible(monkeypatch):
    # LID que mapea a número pero SIN nombre en la agenda → mostrar el número REAL
    monkeypatch.setattr(wa, "_lid_to_phone", lambda lid: "573000000001")
    monkeypatch.setattr("core.mac_contacts.name_for_phone", lambda p: "")
    assert wa.sender_to_name("99887766554433", "99887766554433@lid") == "+573000000001"
