"""kernel.events 单元测试（M1 内核事件层）。

覆盖（docs/architecture.md §6 M1 验收 + ADR-0002/0004/0005 契约）:

- 旧字符串事件 API 兼容（``Event(name=...)`` 发布 / 旧式订阅 / ``unsubscribe(token)``）
- 类型订阅与继承匹配、``raw.*`` 通配、``RawEvent`` 动态事件键
- 优先级、``cancel()`` 中断、``once``、``filter`` 谓词
- ``publish`` 等待分发与回读、``publish_nowait``、嵌套发布内联展开
- ``EventChannel``: ``filter`` / ``filter_isinstance`` / ``parent_scope`` / ``exception_handler``
- 异常隔离、``drain``、队列满丢弃（nowait）

运行: ``.venv\\Scripts\\python.exe -m pytest tests -q``
"""

from __future__ import annotations

import asyncio
from typing import Any

from fcatbot.kernel.events import (
    BotEvent,
    Event,
    EventBus,
    EventChannel,
    LifecycleEvent,
    MessageEvent,
    NoticeEvent,
    RawEvent,
    RequestEvent,
    Subscription,
)


def run(coro: Any) -> Any:
    """在独立事件循环中运行测试场景。"""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 兼容性: 旧字符串事件 API（M1 验收: 「现有插件不改代码可跑」）
# ---------------------------------------------------------------------------


def test_legacy_string_event_roundtrip() -> None:
    """旧式 Event(name=..., data=..., source=..., metadata=...) 发布/订阅不变。"""

    async def scenario() -> list[tuple[str, Any, str, dict]]:
        bus = EventBus()
        bus.start()
        received: list[tuple[str, Any, str, dict]] = []

        def handler(event: Event) -> None:  # 同步处理器（旧系统同样支持）
            received.append(
                (event.name, event.data, event.source, dict(event.metadata))
            )

        bus.subscribe("sdk.raw", handler)
        await bus.publish(
            Event(
                name="sdk.raw",
                data="!echo hello",
                source="sdk",
                metadata={"user_id": "10001", "group_id": 123456},
            )
        )
        await bus.close()
        return received

    assert run(scenario()) == [
        ("sdk.raw", "!echo hello", "sdk", {"user_id": "10001", "group_id": 123456})
    ]


def test_unsubscribe_accepts_token_and_subscription() -> None:
    async def scenario() -> tuple[bool, bool, bool]:
        bus = EventBus()
        bus.start()
        hits: list[str] = []
        sub = bus.subscribe("x", lambda e: hits.append("hit"))
        assert isinstance(sub, Subscription)
        # 旧式: unsubscribe(token 字符串)
        first = bus.unsubscribe(sub.token)
        # 新式: unsubscribe(Subscription 对象)；重复取消应返回 False
        second = bus.unsubscribe(sub)
        await bus.publish(Event(name="x"))
        await bus.close()
        return first, second, len(hits) == 0

    assert run(scenario()) == (True, False, True)


def test_integration_layer_call_shape() -> None:
    """模拟 IntegrationLayer 的订阅调用形态（priority/once/filter 关键字）。"""

    async def scenario() -> list[Any]:
        bus = EventBus()
        bus.start()
        hits: list[Any] = []

        async def wrapper(event: Event) -> None:
            hits.append(event.data)

        token = bus.subscribe("sdk.raw", wrapper, priority=50, once=False, filter=None)
        await bus.publish(Event(name="sdk.raw", data="!echo hi", source="sdk"))
        bus.unsubscribe(token)  # 旧代码用法: 同步调用、直接传 subscribe 的返回值
        await bus.publish(Event(name="sdk.raw", data="!echo again"))
        await bus.close()
        return hits

    assert run(scenario()) == ["!echo hi"]


# ---------------------------------------------------------------------------
# 双轨订阅: 类型 / 继承 / 通配 / RawEvent 动态事件键
# ---------------------------------------------------------------------------


class _AnimalEvent(Event):
    name = "animal"


class _CatEvent(_AnimalEvent):
    name = "cat"


def test_typed_subscription_matches_subclasses() -> None:
    async def scenario() -> list[tuple[str, str]]:
        bus = EventBus()
        bus.start()
        got: list[tuple[str, str]] = []
        bus.subscribe(_AnimalEvent, lambda e: got.append(("animal", e.name)))
        bus.subscribe(_CatEvent, lambda e: got.append(("cat", e.name)))
        await bus.publish(_CatEvent())
        await bus.publish(_AnimalEvent())
        await bus.close()
        return got

    # CatEvent 同时命中两个订阅（继承匹配）；同优先级按注册顺序
    assert run(scenario()) == [
        ("animal", "cat"),
        ("cat", "cat"),
        ("animal", "animal"),
    ]


def test_raw_event_dynamic_name_and_wildcard() -> None:
    """raw.* 通配仅匹配新 RawEvent；与旧 sdk.raw 命名空间互不干扰。"""

    async def scenario() -> list[str]:
        bus = EventBus()
        bus.start()
        got: list[str] = []
        bus.subscribe("raw.*", lambda e: got.append(e.name))
        bus.subscribe("sdk.raw", lambda e: got.append("legacy"))
        await bus.publish(RawEvent(transport="ws", kind="message", data="frame"))
        await bus.publish(RawEvent(transport="ws", kind="connected"))
        await bus.publish(Event(name="sdk.raw", data="old"))
        await bus.close()
        return got

    assert RawEvent(transport="ws", kind="message").name == "raw.ws.message"
    assert run(scenario()) == ["raw.ws.message", "raw.ws.connected", "legacy"]


def test_event_family_defaults() -> None:
    """平台事件基类与 RawEvent 的基本形状。"""
    raw = RawEvent(transport="ws", kind="message", data="x")
    assert raw.name == "raw.ws.message"
    assert not raw.cancelled

    class _FakeBot:
        pass

    bot = _FakeBot()
    for cls in (BotEvent, MessageEvent, NoticeEvent, RequestEvent, LifecycleEvent):
        event = cls(bot=bot)
        assert event.bot is bot
        assert event.name == ""  # 未声明事件键的子类保持空键


# ---------------------------------------------------------------------------
# 分发语义: 优先级 / cancel / once / filter
# ---------------------------------------------------------------------------


def test_priority_order_then_registration_order() -> None:
    async def scenario() -> list[str]:
        bus = EventBus()
        bus.start()
        order: list[str] = []
        bus.subscribe("x", lambda e: order.append("low"), priority=10)
        bus.subscribe("x", lambda e: order.append("high-1"), priority=90)
        bus.subscribe("x", lambda e: order.append("high-2"), priority=90)
        await bus.publish(Event(name="x"))
        await bus.close()
        return order

    assert run(scenario()) == ["high-1", "high-2", "low"]


def test_cancel_interrupts_following_subscribers() -> None:
    async def scenario() -> tuple[list[str], bool]:
        bus = EventBus()
        bus.start()
        order: list[str] = []

        def first(event: Event) -> None:
            order.append("first")
            event.cancel()

        bus.subscribe("x", first, priority=100)
        bus.subscribe("x", lambda e: order.append("second"), priority=10)
        event = await bus.publish(Event(name="x"))
        await bus.close()
        return order, event.cancelled

    assert run(scenario()) == (["first"], True)


def test_once_subscription() -> None:
    async def scenario() -> int:
        bus = EventBus()
        bus.start()
        count = 0

        def handler(event: Event) -> None:
            nonlocal count
            count += 1

        bus.subscribe("x", handler, once=True)
        await bus.publish(Event(name="x"))
        await bus.publish(Event(name="x"))
        await bus.close()
        return count

    assert run(scenario()) == 1


def test_subscription_filter_predicate() -> None:
    async def scenario() -> list[int]:
        bus = EventBus()
        bus.start()
        got: list[int] = []
        bus.subscribe(
            "x", lambda e: got.append(e.data), filter=lambda e: e.data % 2 == 0
        )
        for value in (1, 2, 3, 4):
            await bus.publish(Event(name="x", data=value))
        await bus.close()
        return got

    assert run(scenario()) == [2, 4]


# ---------------------------------------------------------------------------
# 发布语义: publish 等待 / publish_nowait / 嵌套内联
# ---------------------------------------------------------------------------


def test_publish_waits_and_allows_readback() -> None:
    async def scenario() -> Any:
        bus = EventBus()
        bus.start()

        async def handler(event: Event) -> None:
            await asyncio.sleep(0.01)
            event.data = "modified"

        bus.subscribe("x", handler)
        event = await bus.publish(Event(name="x", data="original"))
        await bus.close()
        return event.data

    # publish 返回时 handler 已执行完毕，修改可被发布者读取
    assert run(scenario()) == "modified"


def test_publish_nowait_returns_before_dispatch() -> None:
    async def scenario() -> tuple[list[str], list[str]]:
        bus = EventBus()
        bus.start()
        ran: list[str] = []

        async def handler(event: Event) -> None:
            await asyncio.sleep(0.01)
            ran.append("done")

        bus.subscribe("x", handler)
        bus.publish_nowait(Event(name="x"))
        before = list(ran)  # 尚未让出事件循环: 分发未开始
        await bus.drain()
        after = list(ran)
        await bus.close()
        return before, after

    assert run(scenario()) == ([], ["done"])


def test_nested_publish_inline_expansion() -> None:
    """处理器内的嵌套发布内联展开: 不经过队列、不死锁、顺序稳定。"""

    async def scenario() -> list[str]:
        bus = EventBus()
        bus.start()
        order: list[str] = []

        async def outer(event: Event) -> None:
            order.append("outer-start")
            await bus.publish(Event(name="inner"))
            order.append("outer-end")

        bus.subscribe("outer", outer)
        bus.subscribe("inner", lambda e: order.append("inner"))
        await bus.publish(Event(name="outer"))
        await bus.close()
        return order

    assert run(scenario()) == ["outer-start", "inner", "outer-end"]


def test_drain_waits_for_queued_events() -> None:
    async def scenario() -> int:
        bus = EventBus()
        bus.start()
        count = 0

        def handler(event: Event) -> None:
            nonlocal count
            count += 1

        bus.subscribe("x", handler)
        for _ in range(5):
            bus.publish_nowait(Event(name="x"))
        await bus.drain()
        await bus.close()
        return count

    assert run(scenario()) == 5


def test_publish_nowait_drops_when_queue_full() -> None:
    """队列满时 nowait 丢弃（不阻塞、不抛异常），await publish 才是可靠投递。"""

    async def scenario() -> int:
        bus = EventBus(max_queue=1)
        bus.subscribe("x", lambda e: None)  # 有订阅者才会入队
        # 不启动 worker: 队列不会被消费
        bus.publish_nowait(Event(name="x"))
        bus.publish_nowait(Event(name="x"))  # 触发 QueueFull → 丢弃
        size = bus._queue.qsize()
        await bus.close()
        return size

    assert run(scenario()) == 1


# ---------------------------------------------------------------------------
# EventChannel
# ---------------------------------------------------------------------------


class _FakeScope:
    """模拟 PluginScope 的订阅登记协议（真实实现见 M3）。"""

    def __init__(self) -> None:
        self.subscriptions: list[Subscription] = []

    def register_subscription(self, sub: Subscription) -> None:
        self.subscriptions.append(sub)

    def close(self) -> None:
        for sub in list(self.subscriptions):
            sub.cancel()


def test_channel_filter_and_isinstance() -> None:
    async def scenario() -> list[str]:
        bus = EventBus()
        bus.start()
        got: list[str] = []
        channel: EventChannel = bus.channel.filter_isinstance(_AnimalEvent).filter(
            lambda e: e.name != "cat"
        )
        channel.subscribe_always(lambda e: got.append(e.name))
        await bus.publish(_AnimalEvent())
        await bus.publish(_CatEvent())
        await bus.close()
        return got

    assert run(scenario()) == ["animal"]


def test_channel_parent_scope_cancels_on_close() -> None:
    async def scenario() -> list[int]:
        bus = EventBus()
        bus.start()
        scope = _FakeScope()
        got: list[int] = []
        bus.channel.parent_scope(scope).subscribe_always(lambda e: got.append(1))
        assert len(scope.subscriptions) == 1
        await bus.publish(Event(name="x"))
        scope.close()
        await bus.publish(Event(name="x"))  # scope 关闭后不再接收
        await bus.close()
        return got

    assert run(scenario()) == [1]


def test_channel_parent_scope_requires_protocol() -> None:
    """scope 不满足协议时: 报错并回滚已注册订阅。"""

    async def scenario() -> tuple[bool, bool]:
        bus = EventBus()
        bus.start()
        try:
            bus.channel.parent_scope(object()).subscribe_always(lambda e: None)
        except TypeError as exc:
            raised = "register_subscription" in str(exc)
        else:
            raised = False
        rolled_back = len(bus._subs) == 0
        await bus.close()
        return raised, rolled_back

    assert run(scenario()) == (True, True)


def test_channel_exception_handler_isolates() -> None:
    async def scenario() -> tuple[list[str], list[str]]:
        bus = EventBus()
        bus.start()
        errors: list[str] = []
        after: list[str] = []

        def boom(event: Event) -> None:
            raise ValueError("boom")

        bus.channel.exception_handler(lambda exc: errors.append(str(exc))).subscribe(
            boom
        )
        bus.subscribe("x", lambda e: after.append("after"))
        await bus.publish(Event(name="x"))
        await bus.close()
        return errors, after

    assert run(scenario()) == (["boom"], ["after"])


def test_default_exception_isolation() -> None:
    """无自定义异常处理器: 异常被记录，后续订阅者不受影响。"""

    async def scenario() -> list[str]:
        bus = EventBus()
        bus.start()
        got: list[str] = []

        def boom(event: Event) -> None:
            raise RuntimeError("boom")

        bus.subscribe("x", boom, priority=100)
        bus.subscribe("x", lambda e: got.append("after"))
        await bus.publish(Event(name="x"))
        await bus.close()
        return got

    assert run(scenario()) == ["after"]


def test_channel_subscribe_once() -> None:
    async def scenario() -> int:
        bus = EventBus()
        bus.start()
        count = 0

        def handler(event: Event) -> None:
            nonlocal count
            count += 1

        bus.channel.subscribe_once(handler, spec="x")
        await bus.publish(Event(name="x"))
        await bus.publish(Event(name="x"))
        await bus.close()
        return count

    assert run(scenario()) == 1
