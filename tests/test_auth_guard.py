# tests/test_auth_guard.py
from pathlib import Path
import sys

# tests/ 配下から実行されても、プロジェクト直下を import 対象に入れる
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib
import os
import sys
import pytest


class FakeStreamlit:
    def __init__(self):
        self.title_called = False
        self.writes = []
        self.errors = []
        self.session_state = {}

        # テスト側から注入するUI入力
        self._text_inputs = {}   # key -> value
        self._buttons = {}       # label -> bool

    def title(self, *args, **kwargs):
        self.title_called = True

    def write(self, *args, **kwargs):
        self.writes.append((args, kwargs))

    def error(self, *args, **kwargs):
        self.errors.append((args, kwargs))

    def text_input(self, label, key=None, type=None):
        # keyがない場合もあるので label fallback
        k = key if key is not None else label
        return self._text_inputs.get(k, "")

    def button(self, label):
        return bool(self._buttons.get(label, False))

    def stop(self):
        raise RuntimeError("st.stop called")


@pytest.fixture
def fake_st(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return fake


def import_auth_guard():
    import auth_guard as m
    importlib.reload(m)
    return m


def test_auth_guard_calls_title(fake_st, monkeypatch):
    monkeypatch.delenv("DEV_NO_AUTH", raising=False)
    auth_guard = import_auth_guard()

    with pytest.raises(RuntimeError):
        auth_guard.auth_guard()

    assert fake_st.title_called is True


def test_dev_no_auth_bypasses_stop(fake_st, monkeypatch):
    monkeypatch.setenv("DEV_NO_AUTH", "1")
    auth_guard = import_auth_guard()

    # stop されずに通る
    assert auth_guard.auth_guard() is True
    assert fake_st.session_state.get("authed") is True


def test_already_authed_passes(fake_st, monkeypatch):
    monkeypatch.delenv("DEV_NO_AUTH", raising=False)
    auth_guard = import_auth_guard()

    fake_st.session_state["authed"] = True
    assert auth_guard.auth_guard() is True


def test_login_success_sets_session_and_passes(fake_st, monkeypatch):
    monkeypatch.delenv("DEV_NO_AUTH", raising=False)
    monkeypatch.setenv("APP_USERNAME", "tatsu")
    monkeypatch.setenv("APP_PASSWORD", "pass")
    auth_guard = import_auth_guard()

    # 入力値注入
    fake_st._text_inputs["login_username"] = "tatsu"
    fake_st._text_inputs["login_password"] = "pass"
    fake_st._buttons["Login"] = True

    assert auth_guard.auth_guard() is True
    assert fake_st.session_state.get("authed") is True


def test_login_fail_shows_error_and_stops(fake_st, monkeypatch):
    monkeypatch.delenv("DEV_NO_AUTH", raising=False)
    monkeypatch.setenv("APP_USERNAME", "tatsu")
    monkeypatch.setenv("APP_PASSWORD", "pass")
    auth_guard = import_auth_guard()

    fake_st._text_inputs["login_username"] = "tatsu"
    fake_st._text_inputs["login_password"] = "WRONG"
    fake_st._buttons["Login"] = True

    with pytest.raises(RuntimeError):
        auth_guard.auth_guard()

    # エラー表示が出てるはず
    assert len(fake_st.errors) >= 1
