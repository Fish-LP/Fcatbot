"""宿主装配: 连接件 / HTTP 客户端的**输入参数**来自 ``config/app.yaml``。

覆盖 ``FcatbotApp._build_transport``  对各配置形态的解析: 

- ``transport.mode: none``（默认）→ 不启用连接件
- ``transport.mode: forward_ws`` → ``ForwardWebSocketTransport``（url/token/headers/重连/心跳）
- ``transport.mode: http`` → ``HttpTransport``（host/port/path/api_base_url）
- 未知 mode / forward_ws 缺 url → 跳过（返回 ``None``，不抛异常）
- ``api.base_url`` → ``ApiClient``
- ``plugins.dirs`` → 插件目录（CLI 已不再提供 ``-p``）
- ``webui.{enabled,host,port}`` → WebUI 启动参数（CLI 已不再提供 ``--webui*``）

注: 本测试只验证**构造**（读取输入参数），不启动网络（``start()`` 在 ``run()`` 中调用）。

运行: ``.venv\\Scripts\\python.exe -m pytest tests -q``
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from fcatbot import app as host_app
from fcatbot.adapter.transports import (
    ForwardWebSocketTransport,
    HttpTransport,
    Transport,
)

def _make_app(
    tmp_path: Path,
    *,
    transport: dict | None = None,
    api: dict | None = None,
    plugins: dict | None = None,
    webui: dict | None = None,
) -> host_app.FcatbotApp:
    config: dict = {"permissions": {"backend": "allow_all"}}
    if transport is not None:
        config["transport"] = transport
    if api is not None:
        config["api"] = api
    if plugins is not None:
        config["plugins"] = plugins
    if webui is not None:
        config["webui"] = webui
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return host_app.FcatbotApp(path, [tmp_path / "plugins"])


def _write_config(tmp_path: Path, config: dict) -> Path:
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------


def test_transport_none_by_default(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    assert app.transport is None


def test_transport_none_mode(tmp_path: Path) -> None:
    app = _make_app(tmp_path, transport={"mode": "none"})
    assert app.transport is None


def test_transport_forward_ws_params(tmp_path: Path) -> None:
    app = _make_app(
        tmp_path,
        transport={
            "mode": "forward_ws",
            "forward_ws": {
                "url": "ws://127.0.0.1:9999/onebot/v11/ws",
                "token": "s3cr3t",
                "headers": {"X-Test": "1"},
                "reconnect": False,
                "reconnect_delay": 2.0,
                "max_reconnect_delay": 10.0,
                "heartbeat": 15.0,
            },
        },
    )
    transport = app.transport
    assert isinstance(transport, ForwardWebSocketTransport)
    assert transport.url == "ws://127.0.0.1:9999/onebot/v11/ws"
    assert transport.running is False


def test_transport_forward_ws_missing_url_skipped(tmp_path: Path) -> None:
    app = _make_app(tmp_path, transport={"mode": "forward_ws", "forward_ws": {}})
    assert app.transport is None


def test_transport_http_params(tmp_path: Path) -> None:
    app = _make_app(
        tmp_path,
        transport={
            "mode": "http",
            "http": {
                "host": "0.0.0.0",
                "port": 9000,
                "path": "/callback",
                "api_base_url": "http://127.0.0.1:3000/",
            },
        },
    )
    transport = app.transport
    assert isinstance(transport, HttpTransport)
    assert transport.port == 9000
    assert transport.url == "http://0.0.0.0:9000/callback"


def test_transport_unknown_mode_skipped(tmp_path: Path) -> None:
    app = _make_app(tmp_path, transport={"mode": "reverse_ws"})
    assert app.transport is None


# ---------------------------------------------------------------------------
# 其余运行参数也从配置文件读取（CLI 只保留 -c/--config）
# ---------------------------------------------------------------------------


def test_plugin_dirs_from_config(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {"permissions": {"backend": "allow_all"}, "plugins": {"dirs": ["a", "b"]}},
    )
    app = host_app.FcatbotApp(path)
    assert app._plugin_dirs == [Path("a"), Path("b")]


def test_plugin_dirs_default(tmp_path: Path) -> None:
    path = _write_config(tmp_path, {"permissions": {"backend": "allow_all"}})
    assert host_app.FcatbotApp(path)._plugin_dirs == [Path("plugins")]


def test_plugin_dirs_explicit_override(tmp_path: Path) -> None:
    path = _write_config(tmp_path, {"permissions": {"backend": "allow_all"}})
    app = host_app.FcatbotApp(path, [tmp_path / "custom"])
    assert app._plugin_dirs == [tmp_path / "custom"]


def test_webui_config_defaults(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    assert app._webui_config == {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8765,
        "password": None,
        "secret_key": None,
        "session_ttl": 604800,
        "cookie_secure": False,
    }


def test_webui_config_from_file(tmp_path: Path) -> None:
    app = _make_app(
        tmp_path,
        webui={
            "enabled": False,
            "host": "0.0.0.0",
            "port": 9001,
            "password": "  s3cr3t  ",
            "secret_key": "sign-key",
            "session_ttl": 60,
            "cookie_secure": True,
        },
    )
    assert app._webui_config == {
        "enabled": False,
        "host": "0.0.0.0",
        "port": 9001,
        "password": "s3cr3t",  # 去空字符串
        "secret_key": "sign-key",
        "session_ttl": 60,
        "cookie_secure": True,
    }


def test_webui_blank_password_falls_back_to_generated(tmp_path: Path) -> None:
    app = _make_app(tmp_path, webui={"password": "   "})
    assert app._webui_config["password"] is None


# ---------------------------------------------------------------------------
# ws_task 驱动真实连接后端（取代模拟 sdk.raw 的假循环）
# ---------------------------------------------------------------------------


class _RecordingTransport(Transport):
    """记录 start/stop 调用顺序的假连接件。"""

    transport = "ws"

    def __init__(self, bus: Any, calls: list[str]) -> None:
        super().__init__(bus)
        self._calls = calls

    async def start(self) -> None:
        self._running = True
        self._calls.append("start")

    async def stop(self) -> None:
        self._running = False
        self._calls.append("stop")

    async def send(self, payload: Any) -> Any:  # pragma: no cover - 未使用
        return None


async def _wait_for(predicate: Any, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("等待条件超时")


def test_ws_task_drives_transport(tmp_path: Path) -> None:
    """``_ws_loop``（ws_task）应在收到停止信号后启停连接件。"""

    async def scenario() -> None:
        app = _make_app(tmp_path, transport={"mode": "none"})
        calls: list[str] = []
        app._transport = _RecordingTransport(app._bus, calls)

        task = asyncio.create_task(app._ws_loop(), name="ws")
        await _wait_for(lambda: "start" in calls)
        app._request_shutdown()
        await asyncio.wait_for(task, timeout=2.0)

        assert calls == ["start", "stop"]

    asyncio.run(scenario())


def test_ws_task_without_transport_returns(tmp_path: Path) -> None:
    """未启用连接件时 ``ws_task`` 应立即返回（不发假事件）。"""

    async def scenario() -> None:
        app = _make_app(tmp_path, transport={"mode": "none"})
        assert app.transport is None
        await asyncio.wait_for(app._ws_loop(), timeout=1.0)

    asyncio.run(scenario())

