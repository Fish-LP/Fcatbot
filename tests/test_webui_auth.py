"""WebUI 访问凭据: 配置文件密码 + 无密码时随机生成并打印到本地控制台。

覆盖:

- ``webui.password`` 缺省 → 随机生成 12 位密码（``WebUI.password_generated``）；
- 生成的密码经 ``report_access_password()`` 打印到本地可信控制台
  （直接走 ``console_print``，**不产生日志记录**，因此不会被 ``_WebLogHandler``
  广播给 WebSocket 客户端），且幂等；
- 显式配置的密码不打印；
- 密码校验走 ``hmac.compare_digest``（错误密码拒绝）。

运行: ``.venv\\Scripts\\python.exe -m pytest tests -q``
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fcatbot import app as host_app
from fcatbot.frontend.webui import _PASSWORD_ALPHABET, WebUI


class _StubApp:
    """``WebUI.__init__`` 只需要宿主的 ``_config_path``。"""

    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path


def _stub(tmp_path: Path) -> _StubApp:
    return _StubApp(tmp_path / "config" / "app.yaml")


def _make_ui(tmp_path: Path, **kwargs) -> WebUI:
    return WebUI(_stub(tmp_path), **kwargs)


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------


def test_password_generated_when_absent(tmp_path: Path) -> None:
    ui = _make_ui(tmp_path)
    assert ui.password_generated is True
    assert len(ui._password) == 12
    assert set(ui._password) <= set(_PASSWORD_ALPHABET)


def test_generated_passwords_are_random(tmp_path: Path) -> None:
    passwords = {_make_ui(tmp_path)._password for _ in range(10)}
    assert len(passwords) == 10


def test_configured_password_is_kept(tmp_path: Path) -> None:
    ui = _make_ui(tmp_path, password="manual-pw")
    assert ui._password == "manual-pw"
    assert ui.password_generated is False


# ---------------------------------------------------------------------------
# 打印到本地可信控制台
# ---------------------------------------------------------------------------


def test_report_prints_locally_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ui = _make_ui(tmp_path)
    printed: list[str] = []
    monkeypatch.setattr("fcatbot.frontend.console.console_print", printed.append)

    assert ui.report_access_password() is True
    assert len(printed) == 1
    assert ui._password in printed[0]
    assert "http://127.0.0.1:8765" in printed[0]

    # 幂等: 重复调用不再打印
    assert ui.report_access_password() is False
    assert len(printed) == 1


def test_report_skipped_for_configured_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ui = _make_ui(tmp_path, password="manual-pw")
    printed: list[str] = []
    monkeypatch.setattr("fcatbot.frontend.console.console_print", printed.append)

    assert ui.report_access_password() is False
    assert printed == []


def test_report_does_not_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """密码不得进入日志（日志会被广播给 WebSocket 客户端）。"""
    ui = _make_ui(tmp_path)
    printed: list[str] = []
    monkeypatch.setattr("fcatbot.frontend.console.console_print", printed.append)

    with caplog.at_level(0):
        assert ui.report_access_password() is True

    assert printed
    assert ui._password not in caplog.text


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def test_check_password(tmp_path: Path) -> None:
    ui = _make_ui(tmp_path, password="manual-pw")
    assert ui._check_password("manual-pw") is True
    assert ui._check_password("wrong") is False
    assert ui._check_password("") is False


# ---------------------------------------------------------------------------
# 宿主装配: config/app.yaml → webui.* → WebUI 入参
# ---------------------------------------------------------------------------


def test_host_wires_webui_config(tmp_path: Path) -> None:
    config_path = tmp_path / "app.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "permissions": {"backend": "allow_all"},
                "webui": {
                    "host": "127.0.0.1",
                    "port": 8765,
                    "password": "cfg-pw",
                    "secret_key": "cfg-key",
                    "session_ttl": 120,
                    "cookie_secure": True,
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    app = host_app.FcatbotApp(config_path, [tmp_path / "plugins"])
    cfg = app._webui_config

    # 复刻 app.run() 的构造方式
    ui = WebUI(
        app,
        host=cfg["host"],
        port=cfg["port"],
        password=cfg["password"],
        secret_key=cfg["secret_key"],
        session_ttl=cfg["session_ttl"],
        cookie_secure=cfg["cookie_secure"],
    )
    assert ui._password == "cfg-pw"
    assert ui.password_generated is False
    assert ui._secret_key == b"cfg-key"
    assert ui._session_ttl == 120
    assert ui._cookie_secure is True
