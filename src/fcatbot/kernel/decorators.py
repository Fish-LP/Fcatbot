"""事件处理器装饰器。"""

from __future__ import annotations

from typing import Any, Callable


def on_event(
    spec: str | type,
    *,
    priority: int = 50,
    once: bool = False,
    filter: Callable[[Any], bool] | None = None,
):
    """标记一个方法为 EventBus 事件处理器。

    IntegrationLayer 在插件激活时扫描带此标记的方法并自动订阅，
    插件停用时自动取消订阅。
    """

    def decorator(func: Callable) -> Callable:
        func.__event_spec__ = spec
        func.__event_priority__ = priority
        func.__event_once__ = once
        func.__event_filter__ = filter
        return func

    return decorator