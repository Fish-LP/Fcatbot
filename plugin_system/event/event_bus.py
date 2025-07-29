# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-11 17:31:16
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-29 14:25:07
# @Description  : 事件总线类（优化版）
# -------------------------
from __future__ import annotations

import asyncio
import re
import threading
import uuid
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

from .event import Event

_Handler = Tuple[Optional[re.Pattern], int, Callable[[Event], Any], uuid.UUID]


class EventBus:
    """线程安全、支持同步/异步的事件总线"""

    # 钩子类型
    _HOOKS = (
        "before_publish",
        "after_publish",
        "before_handler",
        "after_handler",
        "on_error",
    )

    # ---------- 初始化 ----------
    def __init__(self) -> None:
        self._exact: Dict[str, List[_Handler]] = {}
        self._regex: List[_Handler] = []

        self._type_hooks: Dict[str, Dict[str, List[Callable]]] = {}
        self._uuid_hooks: Dict[uuid.UUID, Dict[str, List[Callable]]] = {}

        self._lock = threading.RLock()          # 支持同线程重入
        self._loop_lock = asyncio.Lock()        # 仅用于 async 钩子

    # ---------- 订阅/取消 ----------
    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Event], Any],
        priority: int = 0,
    ) -> uuid.UUID:
        """
        订阅事件处理器，返回唯一 ID。
        event_type 以 're:' 开头表示正则匹配。
        """
        with self._lock:
            hid = uuid.uuid4()
            if event_type.startswith("re:"):
                pattern = _compile_regex(event_type[3:])
                self._regex.append((pattern, priority, handler, hid))
                self._regex.sort(key=lambda t: (-t[1], t[2].__name__))  # 保持优先级
            else:
                bucket = self._exact.setdefault(event_type, [])
                bucket.append((None, priority, handler, hid))
                bucket.sort(key=lambda t: (-t[1], t[2].__name__))
            return hid

    def unsubscribe(self, handler_id: uuid.UUID) -> bool:
        """按 ID 移除处理器"""
        with self._lock:
            removed = False
            # 精确匹配
            for typ, bucket in list(self._exact.items()):
                self._exact[typ] = [h for h in bucket if h[3] != handler_id]
                if not self._exact[typ]:
                    del self._exact[typ]
                else:
                    removed |= len(self._exact[typ]) != len(bucket)
            # 正则匹配
            original = len(self._regex)
            self._regex = [h for h in self._regex if h[3] != handler_id]
            removed |= len(self._regex) != original

            self._uuid_hooks.pop(handler_id, None)
            return removed

    # ---------- 钩子 ----------
    def add_hook(
        self,
        hook_type: str,
        func: Callable[..., Any],
        *,
        event_type: Optional[str] = None,
        handler_id: Optional[uuid.UUID] = None,
    ) -> None:
        if hook_type not in self._HOOKS:
            raise ValueError(f"无效钩子类型: {hook_type}")
        if (event_type is None) == (handler_id is None):
            raise ValueError("必须且只能指定 event_type 或 handler_id")

        with self._lock:
            key = event_type if event_type else handler_id
            container = self._type_hooks if event_type else self._uuid_hooks
            bucket = container.setdefault(key, {t: [] for t in self._HOOKS})
            bucket[hook_type].append(func)

    # ---------- 发布 ----------
    async def publish_async(self, event: Event) -> List[Any]:
        """异步发布事件（核心实现）"""
        await self._run_hooks("before_publish", event)
        if event.intercepted:
            await self._run_hooks("after_publish", event)
            return event.results

        handlers = self._collect_handlers(event.type)
        for _, _, handler, hid in handlers:
            if event._propagation_stopped:
                break
            await self._run_hooks("before_handler", event, handler_id=hid)

            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    # 使用默认线程池执行同步回调
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, handler, event)
                await self._run_hooks("after_handler", event, handler_id=hid)
            except Exception as exc:
                await self._run_hooks("on_error", event, handler_id=hid, exc=exc)
                # 全局抛出
                # raise EventHandlerError(exc, handler) from exc

        await self._run_hooks("after_publish", event)
        return event._results.copy()

    def publish_sync(self, event: Event) -> List[Any]:
        """同步发布事件，复用当前线程已存在的事件循环；没有则新建临时循环。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 当前线程无事件循环
            return asyncio.run(self.publish_async(event))
        else:
            # 已在事件循环内（例如 jupyter / pytest-asyncio）
            if loop.is_running():
                # 防止嵌套事件循环
                return loop.create_task(self.publish_async(event)).result()
            return loop.run_until_complete(self.publish_async(event))

    # ---------- 内部工具 ----------
    def _collect_handlers(self, event_type: str) -> List[_Handler]:
        """收集所有匹配处理器，已按优先级排序"""
        with self._lock:
            # 精确匹配
            handlers = list(self._exact.get(event_type, []))
            # 正则匹配
            handlers.extend(h for h in self._regex if h[0] and h[0].match(event_type))
            # 按优先级降序
            handlers.sort(key=lambda t: (-t[1], t[2].__name__))
            return handlers

    async def _run_hooks(
        self,
        hook_type: str,
        event: Event,
        *,
        handler_id: Optional[uuid.UUID] = None,
        exc: Optional[Exception] = None,
    ) -> None:
        """执行钩子函数。锁仅保护钩子列表读取，不阻塞钩子本身。"""
        assert hook_type in self._HOOKS
        to_run: List[Callable[..., Any]] = []

        # 收集钩子（读操作，需加锁）
        async with self._loop_lock:
            if event.type in self._type_hooks:
                to_run.extend(self._type_hooks[event.type].get(hook_type, []))
            if handler_id and handler_id in self._uuid_hooks:
                to_run.extend(self._uuid_hooks[handler_id].get(hook_type, []))

        # 执行钩子（无锁，可并发）
        for hook in to_run:
            if asyncio.iscoroutinefunction(hook):
                await hook(event, exc=exc)
            else:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, hook, event, exc)


# ---------- 工具 ----------
@lru_cache(maxsize=128)
def _compile_regex(pattern: str) -> re.Pattern[str]:
    """正则编译缓存，避免重复编译"""
    try:
        return re.compile(pattern)
    except re.error as e:
        raise ValueError(f"无效正则表达式: {pattern}") from e