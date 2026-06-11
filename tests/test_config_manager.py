# -*- coding: utf-8 -*-
"""
test_config_manager.py — save_api_keys NO debe persistir env-dump ni secretos.

Bug histórico: la UI hacía save_api_keys(load_api_keys()) y, como load() mergea
todo el entorno, el JSON terminó con 48 variables de entorno volcadas (vscode_*,
xpc_*…) e incluso tokens reales. Estos tests congelan el filtro.
"""
import json

from memory import config_manager as cm


def test_save_filters_env_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "CONFIG_FILE", tmp_path / "api_keys.json")
    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cm, "_env_overlay", lambda: {"vscode_pid": "123", "path": "/usr/bin"})
    cm.save_api_keys({"jarvis_theme": "red", "vscode_pid": "123", "path": "/usr/bin"})
    saved = json.loads((tmp_path / "api_keys.json").read_text())
    assert saved == {"jarvis_theme": "red"}   # el env-dump no se persiste


def test_save_filters_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "CONFIG_FILE", tmp_path / "api_keys.json")
    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cm, "_env_overlay", lambda: {})
    cm.save_api_keys({"timezone": "America/Bogota",
                      "github_personal_access_token": "ghp_xxx",
                      "figma_api_key": "figd_xxx",
                      "gemini_api_key": "AIza_xxx"})
    saved = json.loads((tmp_path / "api_keys.json").read_text())
    assert saved == {"timezone": "America/Bogota"}   # secretos jamás al JSON


def test_setting_overridden_by_user_still_saves(tmp_path, monkeypatch):
    # un ajuste cuyo valor DIFIERE del overlay sí se guarda (el usuario lo cambió)
    monkeypatch.setattr(cm, "CONFIG_FILE", tmp_path / "api_keys.json")
    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cm, "_env_overlay", lambda: {"timezone": "UTC"})
    cm.save_api_keys({"timezone": "America/Bogota"})
    saved = json.loads((tmp_path / "api_keys.json").read_text())
    assert saved == {"timezone": "America/Bogota"}
