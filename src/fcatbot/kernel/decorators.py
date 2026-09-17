"""事件处理器装饰器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator


@dataclass(frozen=True, slots=True)
class EventSpec:
    """一次 ``@on_event(...)`` 声明。

    同一个方法可以被多次装饰（叠加），每次产生一个 :class:`EventSpec`，
    由 :class:`~fcatbot.kernel.integration.IntegrationLayer` 逐条订阅。
    """

    spec: str | type
    priority: int = 50
    once: bool = False
    filter: Callable[[Any], bool] | None = None


def on_event(
    spec: str | type,
    *,
    priority: int = 50,
    once: bool = False,
    filter: Callable[[Any], bool] | None = None,
):
    """标记一个方法为 EventBus 事件处理器。**可叠加**。

    IntegrationLayer 在插件激活时扫描带此标记的方法并自动订阅，
    插件停用时自动取消订阅。

    同一个方法叠加多次即订阅多个事件（每个声明独立生效，可各自带
    ``priority`` / ``once`` / ``filter``）::

        @on_event("napcat.message.group")
        @on_event("napcat.message.private", priority=40, filter=_is_admin)
        async def on_private_message(self, event: Event[PrivateMessageEvent]) -> None:
            ...

    叠加顺序：离方法最近的装饰器先生效（Python 装饰器自下而上应用），
    :func:`iter_event_specs` 返回的列表保持这一顺序。
    """

    def decorator(func: Any) -> Any:
        specs: list[EventSpec] = list(getattr(func, "__event_specs__", None) or ())
        specs.append(EventSpec(spec=spec, priority=priority, once=once, filter=filter))
        func.__event_specs__ = specs

        # 向后兼容：单数形式属性保留，指向最先声明的那条订阅。
        first = specs[0]
        func.__event_spec__ = first.spec
        func.__event_priority__ = first.priority
        func.__event_once__ = first.once
        func.__event_filter__ = first.filter
        return func

    return decorator


def iter_event_specs(func: Any) -> Iterator[EventSpec]:
    """遍历某个方法上声明的全部事件订阅。

    优先读取 :func:`on_event` 写入的 ``__event_specs__``；对只设置了旧式
    单个 ``__event_spec__`` 属性的对象（历史代码 / 手工装配）回退为单条，
    保证向后兼容。
    """
    specs = getattr(func, "__event_specs__", None)
    if specs:
        yield from specs
        return

    legacy_spec = getattr(func, "__event_spec__", None)
    if legacy_spec is not None:
        yield EventSpec(
            spec=legacy_spec,
            priority=getattr(func, "__event_priority__", 50),
            once=getattr(func, "__event_once__", False),
            filter=getattr(func, "__event_filter__", None),
        )


def has_event_specs(func: Any) -> bool:
    """该方法是否带有任何事件订阅声明。"""
    if getattr(func, "__event_specs__", None):
        return True
    return getattr(func, "__event_spec__", None) is not None
