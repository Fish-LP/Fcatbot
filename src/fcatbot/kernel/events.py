"""内核事件系统: 事件基类族、事件总线（EventBus）与事件通道（EventChannel）。

设计依据: ``docs/architecture.md`` §3.1/§3.2；ADR-0002 / ADR-0004 / ADR-0005。

核心契约
--------
1. **双轨订阅**: 按事件类订阅（``isinstance`` 继承匹配，推荐）或按事件名订阅
   （精确匹配，或 ``raw.*`` 这样的 fnmatch 通配）。
2. **单 worker 串行分发**: 优先级降序（同优先级按注册顺序）、``event.cancel()``
   中断后续订阅者、队列背压（满时 ``await put`` 等待，不丢事件）。
3. **发布语义**: ``await publish(event)`` 等待事件分发完成后返回**事件本身**
   （可读取监听器修改后的属性）；``publish_nowait(event)`` 仅入队立即返回；
   处理器内的嵌套发布自动**内联展开**，避免单 worker 等待自身死锁。
4. **EventChannel**: 不可变、链式的订阅视图；``parent_scope(scope)`` 绑定生命周期。
5. **兼容旧形态**: ``Event(name=..., data=..., source=..., metadata=...)`` 通用事件
   与 ``bus.subscribe(spec, handler, ...)`` 旧调用保持有效（M1 验收标准）。

scope 协议（结构化鸭子类型）
---------------------------
``EventChannel.parent_scope(scope)`` 要求 ``scope`` 提供
``register_subscription(sub: Subscription) -> None`` 方法；``PluginScope``
将在 M3 实现该协议，用于「作用域关闭 ⇒ 订阅自动取消」。
"""

from __future__ import annotations

import asyncio
import contextvars
import fnmatch
import inspect
import logging
import secrets
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from fcatbot.kernel.entities import Bot

log = logging.getLogger("fcatbot.bus")

_EMPTY_METADATA: Mapping[str, Any] = MappingProxyType({})

# 标记「当前协程正处于事件分发中」，用于嵌套发布的内联展开（ADR-0004）。
_in_dispatch: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "fcatbot_in_dispatch", default=False
)


class Event:
    """所有事件的基类。

    - **可变对象**: 广播过程中允许被监听器修改（mirai ``broadcast`` 同款语义）。
    - 事件键 ``name``: 静态事件类用类属性声明（如 ``name = "onebot.group_message"``）；
      动态事件用 ``@property`` 覆盖（见 :class:`RawEvent`）。订阅匹配始终读取**实例属性**。
    - ``data / source / metadata`` 为通用形态字段（兼容旧 API）；强类型事件子类
      可自行定义更精确的字段。
    """

    name: ClassVar[str] = ""
    data: Any = None
    source: str = ""
    metadata: Mapping[str, Any] = _EMPTY_METADATA
    _cancelled: bool = False

    def __init__(
        self,
        name: str | None = None,
        data: Any = None,
        source: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """通用事件构造（旧 API 兼容）。

        强类型事件子类（dataclass）有自己的构造签名，不走这里。
        """
        if name is not None:
            self.name = name
        self.data = data
        self.source = source
        if metadata is not None:
            self.metadata = dict(metadata)

    def cancel(self) -> None:
        """取消事件: 当前监听器之后的分发将被中断（见 ADR-0004）。"""
        self._cancelled = True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name={self.name!r} "
            f"source={self.source!r} data={self.data!r}>"
        )


@dataclass
class RawEvent(Event):
    """原始事件（框架传输层发布，未经协议解析）。

    事件键为动态属性: ``raw.<transport>.<kind>``（如 ``raw.ws.message``），
    因此 ``fnmatch(event.name, "raw.*")`` 可以正确命中（ADR-0002/ADR-0003）。
    """

    transport: str = ""
    kind: str = ""
    data: Any = None

    @property
    def name(self) -> str:  # type: ignore[override]
        return f"raw.{self.transport}.{self.kind}"


# ---------------------------------------------------------------------------
# 平台事件基类: 内核提供形状，适配器插件继承并具体化（ADR-0003）。
# 字段引用（Bot / MessageChain）随 M2/M4 落地收紧，当前保持最小骨架。
# ---------------------------------------------------------------------------


@dataclass
class BotEvent(Event):
    """平台事件基类: 与某个机器人实例关联。"""

    bot: "Bot"


@dataclass
class MessageEvent(BotEvent):
    """消息事件基类。

    ``message`` / ``sender`` 字段将在 M2（消息模型）落地后补齐；
    在此之前适配器可以直接继承本类并自行声明所需字段。
    """


@dataclass
class NoticeEvent(BotEvent):
    """通知事件基类（成员变动、撤回、戳一戳等）。"""


@dataclass
class RequestEvent(BotEvent):
    """请求事件基类（加好友、加群申请等）。"""


@dataclass
class LifecycleEvent(BotEvent):
    """Bot 生命周期事件（上线 / 下线 / 状态变化）。

    注: architecture §3.1 骨架写为 ``LifecycleEvent(Event)``，此处按语义
    细化为 ``BotEvent`` 子类（生命周期总是与某个 Bot 关联）。
    """


EventHandler = Callable[[Event], "None | Awaitable[None]"]
"""事件处理器: 接收事件对象，返回值可为 None 或可等待对象。"""

ExceptionHandler = Callable[[BaseException], Any]
"""订阅级异常处理器（``EventChannel.exception_handler`` 传入）。"""

ScopeLike = Any
"""scope 协议对象: 需提供 ``register_subscription(subscription)``（M3 PluginScope）。"""


class Subscription:
    """一条事件订阅。由 ``subscribe`` 系列方法返回，可主动取消。

    - ``cancel()`` 幂等；``active`` 反映当前状态；
    - 兼容旧代码: ``token`` 属性（字符串）可作为旧式 token 使用。
    """

    __slots__ = (
        "token",
        "spec",
        "priority",
        "once",
        "handler",
        "filter",
        "exception_handler",
        "_bus",
        "_active",
    )

    def __init__(
        self,
        token: str,
        spec: str | type | None,
        handler: EventHandler,
        *,
        priority: int = 50,
        once: bool = False,
        filter: Callable[[Event], bool] | None = None,
        exception_handler: ExceptionHandler | None = None,
        bus: "EventBus | None" = None,
    ) -> None:
        self.token = token
        self.spec = spec
        self.handler = handler
        self.priority = priority
        self.once = once
        self.filter = filter
        self.exception_handler = exception_handler
        self._bus = bus
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    def cancel(self) -> bool:
        """取消订阅（幂等）。返回 True 表示本次调用发生了取消。"""
        if self._bus is not None:
            return self._bus.unsubscribe(self)
        if self._active:
            self._active = False
            return True
        return False

    def matches(self, event: Event) -> bool:
        """该订阅是否接收此事件（spec 匹配 + filter 谓词）。"""
        if not self._match_spec(event):
            return False
        if self.filter is None:
            return True
        try:
            return bool(self.filter(event))
        except Exception:
            log.exception("事件订阅 filter 执行失败: %r", self)
            return False

    def _match_spec(self, event: Event) -> bool:
        spec = self.spec
        if spec is None:
            return True  # 匹配一切（EventChannel 默认）
        if isinstance(spec, type):
            return isinstance(event, spec)
        name = getattr(event, "name", "") or ""
        return fnmatch.fnmatchcase(name, spec)

    def __repr__(self) -> str:
        spec_repr = getattr(self.spec, "__name__", repr(self.spec))
        return (
            f"<Subscription spec={spec_repr} priority={self.priority} "
            f"once={self.once} active={self._active}>"
        )


class EventChannel:
    """不可变、链式的事件订阅视图（ADR-0005）。

    链式操作均返回**新通道**，不影响原对象::

        channel = bus.channel.filter_isinstance(MessageEvent)
        channel = channel.parent_scope(plugin.scope)
        sub = channel.subscribe_always(on_message, priority=50)

    ``bus.subscribe(...)``（低层 API）与其等价，二者共享同一优先级与取消语义。
    """

    __slots__ = ("_bus", "_predicates", "_scope", "_exception_handler")

    def __init__(
        self,
        bus: "EventBus",
        predicates: tuple[Callable[[Event], bool], ...] = (),
        scope: ScopeLike | None = None,
        exception_handler: ExceptionHandler | None = None,
    ) -> None:
        self._bus = bus
        self._predicates = predicates
        self._scope = scope
        self._exception_handler = exception_handler

    # ---------- 链式操作 ----------

    def filter(self, predicate: Callable[[Event], bool]) -> "EventChannel":
        """附加谓词过滤，返回新通道。"""
        return EventChannel(
            self._bus,
            self._predicates + (predicate,),
            self._scope,
            self._exception_handler,
        )

    def filter_isinstance(self, event_type: type) -> "EventChannel":
        """类型过滤（``isinstance``，含子类），返回新通道。"""
        return self.filter(lambda event: isinstance(event, event_type))

    def parent_scope(self, scope: ScopeLike) -> "EventChannel":
        """绑定生命周期: scope 提供的 ``register_subscription`` 会收到此后订阅。"""
        return EventChannel(self._bus, self._predicates, scope, self._exception_handler)

    def exception_handler(self, handler: ExceptionHandler) -> "EventChannel":
        """为后续订阅设置异常处理器，返回新通道。"""
        return EventChannel(self._bus, self._predicates, self._scope, handler)

    # ---------- 订阅 ----------

    def subscribe(
        self,
        handler: EventHandler,
        *,
        spec: str | type | None = None,
        priority: int = 50,
        once: bool = False,
        filter: Callable[[Event], bool] | None = None,
    ) -> Subscription:
        """订阅事件并返回 Subscription。

        - ``spec``: 事件类 / 事件名 / None（匹配一切，由通道谓词过滤）；
        - 通道谓词与 ``filter`` 依次应用，全部通过才调用 handler。
        """
        sub = self._bus.subscribe(
            spec,
            handler,
            priority=priority,
            once=once,
            filter=self._combine_filter(filter),
            exception_handler=self._exception_handler,
        )
        if self._scope is not None:
            register = getattr(self._scope, "register_subscription", None)
            if not callable(register):
                sub.cancel()
                raise TypeError(
                    "parent_scope() 绑定的 scope 需要提供 "
                    f"register_subscription(subscription) 方法；实际得到 {self._scope!r}"
                )
            register(sub)
        return sub

    def subscribe_always(
        self,
        handler: EventHandler,
        *,
        spec: str | type | None = None,
        priority: int = 50,
    ) -> Subscription:
        """一直监听（subscribe 的 once=False 别名）。"""
        return self.subscribe(handler, spec=spec, priority=priority, once=False)

    def subscribe_once(
        self,
        handler: EventHandler,
        *,
        spec: str | type | None = None,
        priority: int = 50,
    ) -> Subscription:
        """只监听一次。"""
        return self.subscribe(handler, spec=spec, priority=priority, once=True)

    # ---------- 内部 ----------

    def _combine_filter(
        self, extra: Callable[[Event], bool] | None
    ) -> Callable[[Event], bool] | None:
        predicates = self._predicates
        if not predicates and extra is None:
            return None

        def combined(event: Event) -> bool:
            for predicate in predicates:
                if not predicate(event):
                    return False
            if extra is not None:
                return bool(extra(event))
            return True

        return combined

    def __repr__(self) -> str:
        return (
            f"<EventChannel predicates={len(self._predicates)} "
            f"scope={self._scope!r}>"
        )


class EventBus:
    """单 worker 串行事件总线（ADR-0004）。

    - 通过 :meth:`subscribe` / :attr:`channel` 注册订阅；
    - :meth:`publish` 入队并等待分发完成；:meth:`publish_nowait` 仅入队；
    - :meth:`start` 启动分发 worker（幂等）；:meth:`close` 排空队列后停止。
    """

    def __init__(self, *, max_queue: int = 1000, slow_handler_warn: float | None = 0.5):
        self._queue: asyncio.Queue[
            tuple[Event, list[Subscription], asyncio.Future | None]
        ] = asyncio.Queue(maxsize=max_queue)
        self._subs: list[Subscription] = []
        self._token_map: dict[str, Subscription] = {}
        self._worker: asyncio.Task[None] | None = None
        self._closed = False
        self._slow_handler_warn = slow_handler_warn

    # ---------- 入口 ----------

    @property
    def channel(self) -> EventChannel:
        """全局事件通道（链式操作的起点）。"""
        return EventChannel(self)

    # ---------- 订阅 ----------

    def subscribe(
        self,
        spec: str | type | None,
        handler: EventHandler,
        *,
        priority: int = 50,
        once: bool = False,
        filter: Callable[[Event], bool] | None = None,
        exception_handler: ExceptionHandler | None = None,
    ) -> Subscription:
        """注册一条订阅（低层 API，推荐经 ``channel`` 使用）。

        - ``spec``: 事件类（继承匹配）/ 事件名（精确或 fnmatch 通配）/ None（匹配一切）；
        - ``priority``: 数字越大越先；同优先级按注册顺序；
        - ``once``: 触发一次后自动取消；
        - ``filter``: 附加谓词；
        - 返回 :class:`Subscription`（``token`` 属性兼容旧式字符串 token）。
        """
        if self._closed:
            raise RuntimeError("EventBus is closed")
        sub = Subscription(
            token=secrets.token_hex(8),
            spec=spec,
            handler=handler,
            priority=priority,
            once=once,
            filter=filter,
            exception_handler=exception_handler,
            bus=self,
        )
        self._subs.append(sub)
        self._token_map[sub.token] = sub
        return sub

    def unsubscribe(self, subscription: "Subscription | str") -> bool:
        """取消订阅。接受 :class:`Subscription` 或旧式 token 字符串；幂等。"""
        sub: Subscription | None
        if isinstance(subscription, Subscription):
            sub = subscription
        else:
            sub = self._token_map.get(subscription)
        if sub is None or not sub._active:
            return False
        sub._active = False
        self._token_map.pop(sub.token, None)
        try:
            self._subs.remove(sub)
        except ValueError:
            pass
        return True

    # ---------- 发布 ----------

    async def publish(self, event: "Event | object") -> Event:
        """发布事件并**等待分发完成后返回事件本身**。

        在事件处理器内调用时（嵌套发布）自动内联展开，避免死锁（ADR-0004）。
        """
        if self._closed:
            raise RuntimeError("EventBus is closed")
        ev = self._ensure_event(event)
        subs = self._resolve(ev)
        if not subs:
            return ev
        if _in_dispatch.get():
            await self._dispatch(ev, subs)
            return ev
        if self._worker is None:
            self.start()
        waiter: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put((ev, subs, waiter))
        await waiter
        return ev

    def publish_nowait(self, event: "Event | object") -> Event:
        """仅入队、立即返回（不保证分发完成）。

        队列满时丢弃事件并记录警告——需要可靠投递时使用 ``await publish(...)``。
        """
        if self._closed:
            raise RuntimeError("EventBus is closed")
        ev = self._ensure_event(event)
        subs = self._resolve(ev)
        if not subs:
            return ev
        try:
            self._queue.put_nowait((ev, subs, None))
        except asyncio.QueueFull:
            log.warning(
                "EventBus 队列已满（max_queue=%d），丢弃事件 %r",
                self._queue.maxsize,
                ev,
            )
        return ev

    async def drain(self) -> None:
        """等待队列中已入队的事件全部处理完成。"""
        if self._worker is None and not self._closed:
            self.start()
        await self._queue.join()

    # ---------- 生命周期 ----------

    def start(self) -> None:
        """启动分发 worker（幂等）。"""
        if self._worker is not None or self._closed:
            return
        self._worker = asyncio.create_task(self._loop(), name="fcatbot-eventbus")

    async def close(self) -> None:
        """排空队列后停止 worker。"""
        if self._closed:
            return
        self._closed = True
        if self._worker is None:
            # 从未启动: 清空队列，避免 join 挂起
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    break
            return
        await self._queue.join()
        self._worker.cancel()
        try:
            await self._worker
        except asyncio.CancelledError:
            pass
        self._worker = None

    # ---------- 内部 ----------

    @staticmethod
    def _ensure_event(event: "Event | object") -> Event:
        if isinstance(event, Event):
            return event
        # 兼容旧行为: 非 Event 对象包装为以其类型名为键的通用事件
        return Event(name=type(event).__name__, data=event)

    def _resolve(self, event: Event) -> list[Subscription]:
        matched = [sub for sub in self._subs if sub._active and sub.matches(event)]
        matched.sort(key=lambda sub: sub.priority, reverse=True)
        return matched

    async def _dispatch(self, event: Event, subs: list[Subscription]) -> None:
        token = _in_dispatch.set(True)
        threshold = self._slow_handler_warn
        try:
            for sub in subs:
                if not sub._active:
                    continue
                if event._cancelled:
                    break
                started = time.perf_counter()
                await self._invoke(sub, event)
                if threshold is not None:
                    cost = time.perf_counter() - started
                    if cost >= threshold:
                        log.warning(
                            "事件处理器耗时过长: %.2fs (>= %.2fs) handler=%r event=%r；"
                            "请将耗时操作移入 PluginScope 任务（ADR-0004）",
                            cost,
                            threshold,
                            sub.handler,
                            event,
                        )
                if sub.once:
                    self.unsubscribe(sub)
        finally:
            _in_dispatch.reset(token)

    @staticmethod
    async def _invoke(sub: Subscription, event: Event) -> None:
        try:
            result = sub.handler(event)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            handler = sub.exception_handler
            if handler is None:
                log.exception(
                    "事件处理器抛出未处理异常: handler=%r event=%r", sub.handler, event
                )
                return
            try:
                result = handler(exc)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                log.exception("事件订阅的异常处理器执行失败: %r", sub)

    async def _loop(self) -> None:
        while True:
            event, subs, waiter = await self._queue.get()
            try:
                await self._dispatch(event, subs)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("事件分发失败: %r", event)
            finally:
                if waiter is not None and not waiter.done():
                    waiter.set_result(None)
                self._queue.task_done()

    def __repr__(self) -> str:
        return (
            f"<EventBus subs={len(self._subs)} queue={self._queue.qsize()} "
            f"closed={self._closed}>"
        )


__all__ = [
    # 事件族
    "Event",
    "RawEvent",
    "BotEvent",
    "MessageEvent",
    "NoticeEvent",
    "RequestEvent",
    "LifecycleEvent",
    # 分发
    "EventBus",
    "EventChannel",
    "Subscription",
    # 类型别名
    "EventHandler",
    "ExceptionHandler",
]
