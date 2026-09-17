"""插件 API 测试: 异步生命周期入口、任务作用域、事件感知权限检查。"""

from __future__ import annotations

import asyncio
from typing import Any

from fcatbot.kernel.commands import CommandRegistry, console_command
from fcatbot.kernel.decorators import EventSpec, iter_event_specs, on_event
from fcatbot.kernel.events import Event, EventBus
from fcatbot.kernel.integration import IntegrationLayer
from fcatbot.kernel.plugins import FcatbotPlugin
from fcatbot.kernel.services import ServiceRegistry

# ---------------------------------------------------------------------------
# 测试替身
# ---------------------------------------------------------------------------


class FakePermissionService:
    """记录调用参数的权限服务（PermissionService 协议实现）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.allowed: set[tuple[str, str]] = set()

    async def has_permission(self, user_id, node, *, context=None):
        self.calls.append((str(user_id), str(node), dict(context) if context else None))
        return (str(user_id), str(node)) in self.allowed

    async def get_groups(self, user_id):  # pragma: no cover - 协议补齐
        return []

    async def get_prefix(self, user_id):  # pragma: no cover - 协议补齐
        return ""

    async def get_meta(self, user_id, key):  # pragma: no cover - 协议补齐
        return None


class FakePluginManager:
    def __init__(self, plugins: list[FcatbotPlugin]) -> None:
        self._plugins = plugins

    def get_active_plugins(self) -> list[FcatbotPlugin]:
        return list(self._plugins)


def _build(plugins: list[FcatbotPlugin], permissions: Any = None):
    """构造 IntegrationLayer 并注入依赖（等价于 FcatbotApp._pre_activate）。"""
    bus = EventBus()
    services = ServiceRegistry()
    commands = CommandRegistry()
    perms = permissions or FakePermissionService()
    layer = IntegrationLayer(FakePluginManager(plugins), bus, services, commands)
    for plugin in plugins:
        plugin._bus = bus
        plugin._permissions = perms
        plugin._services = services
        plugin._commands = commands  # 仅测试用: 断言装配时序
    return layer, bus, commands, perms


class _Probe(FcatbotPlugin):
    name = "probe"
    version = "1.0.0"
    description = "test plugin"
    target_application = "fcatbot"
    min_app_version = "1.0.0"

    def __init__(self) -> None:
        self.events: list[str] = []
        self.ticks = 0
        self.registered_at_load: bool | None = None
        self.registered_at_enable: bool | None = None

    @console_command("probe", help="probe")
    def cmd_probe(self, args: list[str]) -> str:
        return "pong"

    async def on_load(self) -> None:
        self.events.append("load")
        self.registered_at_load = self._commands.find(["probe"])[0] is not None

    async def on_enable(self) -> None:
        self.events.append("enable")
        self.registered_at_enable = self._commands.find(["probe"])[0] is not None
        self.create_task(self._tick(), name="tick")

    async def on_disable(self) -> None:
        self.events.append("disable")

    async def on_unload(self) -> None:
        self.events.append("unload")

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(0.005)
            self.ticks += 1


class _Plain(FcatbotPlugin):
    name = "plain"
    version = "1.0.0"
    description = "no-command plugin"
    target_application = "fcatbot"
    min_app_version = "1.0.0"

    def __init__(self) -> None:
        self.events: list[str] = []

    async def on_load(self) -> None:
        self.events.append("load")

    async def on_enable(self) -> None:
        self.events.append("enable")

    async def on_disable(self) -> None:
        self.events.append("disable")

    async def on_unload(self) -> None:
        self.events.append("unload")


# ---------------------------------------------------------------------------
# 异步生命周期
# ---------------------------------------------------------------------------


def test_async_lifecycle_order_and_wiring() -> None:
    """on_load → 装配（事件/命令）→ on_enable；停用逆序 + 任务自动取消。"""

    async def scenario() -> None:
        plugin = _Probe()
        layer, bus, commands, _ = _build([plugin])

        await layer.start_all()
        assert plugin.events == ["load", "enable"]
        # 命令在 on_load 之后、on_enable 之前完成注册
        assert plugin.registered_at_load is False
        assert plugin.registered_at_enable is True
        assert commands.find(["probe"])[0] is not None

        await asyncio.sleep(0.03)
        assert plugin.ticks > 0

        await layer.stop_all()
        assert plugin.events == ["load", "enable", "disable", "unload"]
        assert commands.find(["probe"])[0] is None
        assert not plugin._task_registry()  # 后台任务已取消并回收
        await bus.close()

    asyncio.run(scenario())


def test_on_enable_is_an_async_entry() -> None:
    """异步入口可用: on_enable 中可 await 权限检查等异步 API。"""

    async def scenario() -> None:
        class Checker(FcatbotPlugin):
            name = "checker"
            version = "1.0.0"
            description = "checks permission during enable"
            target_application = "fcatbot"
            min_app_version = "1.0.0"

            def __init__(self) -> None:
                self.result: bool | None = None

            async def on_enable(self) -> None:
                self.result = await self.has_permission("1", "use")

        plugin = Checker()
        layer, bus, _, perms = _build([plugin])
        perms.allowed.add(("1", "checker.use"))

        await layer.start_all()
        assert plugin.result is True
        await layer.stop_all()
        await bus.close()

    asyncio.run(scenario())


def test_hook_failure_is_isolated() -> None:
    """单个插件钩子异常不影响其他插件（失败隔离）。"""

    async def scenario() -> None:
        class Boom(_Plain):
            name = "boom"

            async def on_enable(self) -> None:
                self.events.append("enable")
                raise RuntimeError("boom")

        boom, plain = Boom(), _Plain()
        layer, bus, _, _ = _build([boom, plain])

        await layer.start_all()
        assert boom.events == ["load", "enable"]
        assert plain.events == ["load", "enable"]

        await layer.stop_all()
        assert plain.events == ["load", "enable", "disable", "unload"]
        await bus.close()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 权限: 上下文与事件感知
# ---------------------------------------------------------------------------


def test_has_permission_passes_context() -> None:
    async def scenario() -> None:
        plugin = _Probe()
        layer, bus, _, perms = _build([plugin])
        perms.allowed.add(("42", "probe.use"))

        assert (
            await plugin.has_permission("42", "use", context={"group_id": "9"}) is True
        )
        assert perms.calls[-1] == ("42", "probe.use", {"group_id": "9"})

        # 节点已含点: 不再加插件名前缀；无上下文传 None
        assert await plugin.has_permission(42, "probe.use") is True
        assert perms.calls[-1] == ("42", "probe.use", None)
        await bus.close()

    asyncio.run(scenario())


def test_has_permission_for_derives_subject_and_context() -> None:
    async def scenario() -> None:
        class Adapter(_Probe):
            name = "adapter"

            def permission_context(self, event: Event) -> dict[str, Any]:
                return {
                    "contact": "group",
                    "group": str(event.metadata.get("group_id")),
                }

        adapter = Adapter()
        layer, bus, _, perms = _build([adapter])
        perms.allowed.add(("7", "adapter.use"))
        event = Event(
            name="raw.test",
            data="hi",
            source="test",
            metadata={"user_id": 7, "group_id": 123},
        )

        # 适配器覆盖 permission_context → 平台语义上下文
        assert await adapter.has_permission_for(event, "use") is True
        assert perms.calls[-1] == (
            "7",
            "adapter.use",
            {"contact": "group", "group": "123"},
        )

        # extra_context 合并（同键覆盖）
        assert (
            await adapter.has_permission_for(
                event, "use", extra_context={"group": "999"}
            )
            is True
        )
        assert perms.calls[-1][2] == {"contact": "group", "group": "999"}

        # 无主体 → 直接拒绝，不查服务
        before = len(perms.calls)
        empty = Event(name="raw.test", data="x", source="test")
        assert await adapter.has_permission_for(empty, "use") is False
        assert len(perms.calls) == before
        await bus.close()

        # 默认实现: 按 permission_context_keys 白名单从 metadata 收集
        default = _Probe()
        layer2, bus2, _, perms2 = _build([default])
        perms2.allowed.add(("7", "probe.use"))
        assert await default.has_permission_for(event, "use") is True
        assert perms2.calls[-1][2] == {"group_id": 123}
        await bus2.close()

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# @on_event 叠加: 一个方法订阅多个事件
# ---------------------------------------------------------------------------


class _MultiEvent(FcatbotPlugin):
    """在同一个方法上叠加多个 @on_event，各自保留自己的 priority / filter。"""

    name = "multi"
    version = "1.0.0"
    description = "multi-event plugin"
    target_application = "fcatbot"
    min_app_version = "1.0.0"

    def __init__(self) -> None:
        self.seen: list[tuple[str, Any]] = []

    @on_event("napcat.message.group")
    @on_event("napcat.message.private", filter=lambda e: e.data.startswith("!"))
    async def on_message(self, event: Event) -> None:
        self.seen.append((event.name, event.data))

    @on_event("raw.a")
    @on_event("raw.b", priority=90)
    @on_event("raw.c", once=True)
    async def on_raw(self, event: Event) -> None:
        self.seen.append((event.name, event.data))


def test_on_event_can_be_stacked_on_one_method() -> None:
    async def scenario() -> None:
        plugin = _MultiEvent()
        layer, bus, _, _ = _build([plugin])
        layer.attach(plugin)

        # 两个声明都生效
        await bus.publish(Event(name="napcat.message.group", data="plain"))
        await bus.publish(Event(name="napcat.message.private", data="!cmd"))
        assert plugin.seen == [
            ("napcat.message.group", "plain"),
            ("napcat.message.private", "!cmd"),
        ]

        # 每个声明独立的 filter（不只是作用于第一条）
        await bus.publish(Event(name="napcat.message.private", data="no-prefix"))
        assert plugin.seen[-1] == ("napcat.message.private", "!cmd")

        # 三条 raw 声明全部生效；once 只作用于声明它的那条
        await bus.publish(Event(name="raw.a", data=1))
        await bus.publish(Event(name="raw.b", data=2))
        await bus.publish(Event(name="raw.c", data=3))
        await bus.publish(Event(name="raw.c", data=4))
        await bus.publish(Event(name="raw.b", data=5))
        assert plugin.seen[-4:] == [
            ("raw.a", 1),
            ("raw.b", 2),
            ("raw.c", 3),
            ("raw.b", 5),
        ]

        # detach 退订全部声明
        layer.detach(plugin)
        await bus.publish(Event(name="napcat.message.group", data="gone"))
        await bus.publish(Event(name="raw.a", data=9))
        assert plugin.seen[-4:] == [
            ("raw.a", 1),
            ("raw.b", 2),
            ("raw.c", 3),
            ("raw.b", 5),
        ]

        await bus.close()

    asyncio.run(scenario())


def test_iter_event_specs_preserves_declarations_and_legacy_attr() -> None:
    specs = list(iter_event_specs(_MultiEvent.on_message))
    # 自下而上: 离方法最近的装饰器先生效
    assert [s.spec for s in specs] == [
        "napcat.message.private",
        "napcat.message.group",
    ]
    assert specs[0].filter is not None and specs[0].priority == 50

    raw_specs = list(iter_event_specs(_MultiEvent.on_raw))
    assert [(s.spec, s.priority, s.once) for s in raw_specs] == [
        ("raw.c", 50, True),
        ("raw.b", 90, False),
        ("raw.a", 50, False),
    ]

    # 向后兼容: 单数形式属性指向最先声明的那条
    assert _MultiEvent.on_raw.__event_spec__ == "raw.c"
    assert _MultiEvent.on_raw.__event_priority__ == 50
    assert _MultiEvent.on_raw.__event_once__ is True

    # 无声明的方法不产出任何 spec
    assert list(iter_event_specs(_MultiEvent.on_load)) == []

    # 旧式手工设置单个 __event_spec__ 的对象仍然被识别
    class Legacy:
        __event_spec__ = "raw.legacy"
        __event_priority__ = 70

    assert list(iter_event_specs(Legacy)) == [EventSpec(spec="raw.legacy", priority=70)]
