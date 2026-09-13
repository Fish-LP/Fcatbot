"""NapCat 适配器（OneBot11）移植到 fcatbot4 后的回归测试。

覆盖:

- 插件按加载器的方式可被发现（顶层模块名 ``adapter``，插件名 ``NapcatAdapter``）；
- ``provides`` 使用「属性名」形式注册服务（fcatbot4 中 ``None`` 表示插件实例自身）；
- NCAPI 请求-响应闭环: 出站 ``Transport.send`` + 入站 echo 旁路（不经事件总线）；
- 原始帧 → 平台事件（``napcat.message.group``）+ 权限主体 / 上下文抽取。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from fcatbot import app as host_app
from fcatbot.kernel.events import Event, EventBus
from fcatbot.kernel.loader import PluginLoader
from fcatbot.kernel.permissions import AllowAllPermissionService
from fcatbot.kernel.services import ServiceRegistry

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIRS = [ROOT / "plugins"]

GROUP_MESSAGE: dict = {
    "post_type": "message",
    "message_type": "group",
    "sub_type": "normal",
    "time": 1700000000,
    "self_id": 10000,
    "message_id": 1,
    "message_seq": 1,
    "real_id": 1,
    "real_seq": "1",
    "group_id": 123456,
    "group_name": "测试群",
    "user_id": 10001,
    "raw_message": "hello",
    "font": 14,
    "message": [{"type": "text", "data": {"text": "hello"}}],
    "sender": {"user_id": 10001, "nickname": "Tester", "role": "admin"},
}


class FakeTransport:
    """最小双工通道: 记录出站载荷，并立即回一个带 echo 的应答帧。"""

    def __init__(self, retcode: int = 0) -> None:
        self.sent: list[dict] = []
        self._listener = None
        self._retcode = retcode

    def add_raw_listener(self, listener):
        self._listener = listener
        return lambda: setattr(self, "_listener", None)

    async def send(self, payload):
        self.sent.append(payload)
        self._listener(
            {
                "status": "ok" if self._retcode == 0 else "failed",
                "retcode": self._retcode,
                "data": {"message_id": 7},
                "echo": payload["echo"],
            }
        )


def _load_adapter_class():
    return PluginLoader(PLUGIN_DIRS).load_class("adapter")


def _make_adapter():
    adapter = _load_adapter_class()()
    bus = EventBus()
    services = ServiceRegistry()
    adapter._bus = bus
    adapter._services = services
    adapter._permissions = AllowAllPermissionService()
    adapter._transport = FakeTransport()
    services.register_from_plugin(adapter)
    return adapter, bus, services


def test_adapter_is_discoverable_and_declares_services() -> None:
    cls = _load_adapter_class()
    assert cls.name == "NapcatAdapter"
    assert cls.target_application == "fcatbot"
    # fcatbot4: provides 的值是「插件属性名」；None 会注册插件实例自身
    assert cls.provides == {"napcat.api": "api", "napcat.tap": "tap"}


def test_provides_registers_api_and_tap_services() -> None:
    adapter, _bus, services = _make_adapter()
    assert services.resolve("napcat.api") is adapter.api
    assert services.resolve("napcat.tap") == adapter.tap


def test_on_load_binds_transport_for_api_roundtrip() -> None:
    adapter, _bus, _services = _make_adapter()

    async def scenario():
        await adapter.on_load()
        return await adapter.api.group.send_group_msg(group_id=123456, message="hi")

    result = asyncio.run(scenario())

    assert result == {"message_id": 7}
    payload = adapter._transport.sent[0]
    assert payload["action"] == "send_group_msg"
    assert payload["params"]["group_id"] == "123456"
    assert "echo" in payload
    assert adapter.api.client is adapter._transport


def test_on_load_without_transport_degrades_gracefully() -> None:
    adapter, _bus, _services = _make_adapter()
    adapter._transport = None
    asyncio.run(adapter.on_load())  # 不应抛异常
    assert adapter.api.client is None


def test_on_raw_publishes_platform_event_with_permission_context() -> None:
    adapter, bus, _services = _make_adapter()
    received: list[Event] = []

    async def scenario() -> None:
        bus.start()
        bus.subscribe("napcat.message.group", received.append)
        await adapter.on_raw(
            Event(name="raw.ws.message", data=GROUP_MESSAGE, source="ws")
        )
        await bus.drain()

    asyncio.run(scenario())

    assert len(received) == 1, received
    event = received[0]
    assert event.metadata["group_id"] == 123456
    assert adapter.permission_subject(event) == "10001"
    context = adapter.permission_context(event)
    assert context["platform"] == "napcat"
    assert context["group"] == "123456"
    assert context["level"] == "admin"


def test_host_activation_registers_adapter_services(tmp_path: Path) -> None:
    """宿主装配路径: loader → PluginManager → IntegrationLayer。

    验证「目录名 adapter ≠ 插件名 NapcatAdapter」时仍能被 `plugins.enabled` 正确启用，
    且 `provides` 中声明的属性名服务在 pre_activate 阶段被成功解析注册。
    """
    config = tmp_path / "app.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "app": {"name": "Test"},
                "plugins": {"enabled": ["NapcatAdapter"]},
                "permissions": {"backend": "allow_all"},
                "transport": {"mode": "none"},  # 不建真实连接
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    async def scenario() -> None:
        app = host_app.FcatbotApp(config, PLUGIN_DIRS)
        app._bus.start()
        classes = app._loader.discover()
        app._ensure_plugin_configs(classes)
        app._pm.register_plugins(classes)
        await app._integration.start_all()
        try:
            assert "NapcatAdapter" in [p.name for p in app._pm.get_active_plugins()]
            assert app._services.resolve("napcat.api") is not None
            assert app._services.resolve("napcat.tap") is not None
        finally:
            await app._integration.stop_all()
            await app._bus.close()

    asyncio.run(scenario())


def test_on_raw_ignores_api_response_frames() -> None:
    adapter, bus, _services = _make_adapter()
    received: list[Event] = []

    async def scenario() -> None:
        bus.start()
        bus.subscribe("*", received.append)
        await adapter.on_raw(
            Event(
                name="raw.ws.message",
                data={"status": "ok", "retcode": 0, "echo": "abc"},
                source="ws",
            )
        )
        await bus.drain()

    asyncio.run(scenario())
    assert received == []
