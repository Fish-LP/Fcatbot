"""命令系统的统一入口。

对外只暴露一个方法 :meth:`CommandRouter.handle`：

    字符串  →  分词  →  命令路径解析  →  鉴权  →  调度  →  文本结果

分段职责（不在这里重复实现）：

- **分词**: 可注入 ``tokenizer``（默认 ``str.split``，为将来支持引号留口子）；
- **路径解析**: :meth:`fcatbot.kernel.commands.CommandRegistry.find`；
- **鉴权 + 调度**: :func:`fcatbot.kernel.commands.dispatch_command`；
- **参数值解析**: 处理器内部用 :class:`fcatbot.kernel.args.CommandArgs`。

调用方（控制台循环、聊天适配器、测试）只面对 :meth:`handle`，
不再需要自己拼 ``tokens``、造 ``CommandContext``、传 ``is_allowed``。
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from fcatbot.kernel.commands import (
    CommandContext,
    CommandRegistry,
    dispatch_command,
)

log = logging.getLogger("fcatbot.router")

__all__ = ["CommandRouter", "default_tokenizer"]


def default_tokenizer(raw: str) -> list[str]:
    """默认分词：按空白切分。

    与 LuckPerms 官方一致（"暂不支持引号转义空格"）。将来若需要带引号解析，
    在 router 构造时传入替代实现即可，不必改 handler。
    """
    return raw.split()


class CommandRouter:
    """命令系统的唯一入口。

    Args:
        registry: 已注册命令的 :class:`CommandRegistry`。
        is_allowed: 命令级鉴权回调 ``(context, node) -> bool``。
            通常由 :func:`fcatbot.kernel.commands.make_is_allowed` 构造。
        tokenizer: 覆盖默认分词。签名 ``(raw: str) -> list[str]``。
        prefix: 若给出，仅处理以此前缀开头的输入；命中后剥离该前缀。
            便于聊天场景（如 ``/lp info``）。
        allow_without_prefix: 在前缀检查模式下允许无前缀命令进入。
    """

    def __init__(
        self,
        registry: CommandRegistry,
        *,
        is_allowed: Callable[[CommandContext, str], bool | Awaitable[bool]],
        tokenizer: Optional[Callable[[str], list[str]]] = None,
        prefix: Optional[str] = None,
        allow_without_prefix: bool = False,
    ) -> None:
        self._registry = registry
        self._is_allowed = is_allowed
        self._tokenize = tokenizer or default_tokenizer
        self._prefix = prefix
        self._allow_without_prefix = allow_without_prefix

    # ------------------------------------------------------------------
    # 对外唯一方法
    # ------------------------------------------------------------------

    async def handle(
        self,
        raw: str,
        *,
        context: Optional[CommandContext] = None,
    ) -> Optional[str]:
        """处理一条原始命令输入。

        Returns:
            - ``str``: 命令命中并执行完成，返回文本结果（可能为空串）；
            - ``None``: 未命中任何命令（路由层应视作"这不是给我的"）。
        """
        if raw is None:
            return None
        raw = raw.strip()
        if not raw:
            return None

        if self._prefix is not None:
            if raw.startswith(self._prefix):
                raw = raw[len(self._prefix) :].strip()
            elif not self._allow_without_prefix:
                return None
            if not raw:
                return None

        try:
            tokens = self._tokenize(raw)
        except Exception:
            log.exception("分词失败: raw=%r", raw)
            return None
        if not tokens:
            return None

        ctx = context if context is not None else CommandContext()

        try:
            return await dispatch_command(
                self._registry,
                tokens,
                context=ctx,
                is_allowed=self._is_allowed,
            )
        except Exception:
            log.exception("命令执行异常: raw=%r", raw)
            return "[命令] 执行失败（详见日志）"

    # ------------------------------------------------------------------
    # 便捷：同步场景（控制台 REPL、脚本）
    # ------------------------------------------------------------------

    def handle_sync(
        self,
        raw: str,
        *,
        context: Optional[CommandContext] = None,
    ) -> Optional[str]:
        """同步包装。仅用于无事件循环的场景（脚本 / 控制台）。

        若当前线程已有运行中的事件循环，会抛 ``RuntimeError``——
        这种情况请改用 ``await router.handle(...)``。
        """
        import asyncio

        return asyncio.run(self.handle(raw, context=context))
