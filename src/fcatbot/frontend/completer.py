"""基于 CommandRegistry 的 prompt_toolkit 补全器。

用法:
    session = PromptSession(completer=CommandCompleter(registry))
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from fcatbot.kernel.commands import CommandRegistry

log = logging.getLogger("fcatbot.completer")


class CommandCompleter(Completer):
    """命令补全器。

    补全规则:
    - 输入首词时补全所有顶层命令（含别名）；
    - 先补全已知子命令；遇到参数时由命令的自定义 completer 提供候选；
    - 无命令级补全器的参数位置不提供建议。
    - 补全项附带 help 文本作为显示元数据。
    """

    def __init__(self, registry: CommandRegistry):
        self._registry = registry

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterator[Completion]:
        text = document.text_before_cursor.lstrip()
        trailing_space = bool(text) and text[-1].isspace()
        parts = text.split()
        current = "" if trailing_space else parts.pop() if parts else ""

        if not parts:
            for name in self._registry.complete(current):
                spec, _ = self._registry.find([name])
                yield Completion(
                    name,
                    start_position=-len(current),
                    display_meta=spec.help if spec else "",
                )
            return

        spec, args = self._registry.find(parts)
        if spec is None:
            return

        subcommands = {
            name: child
            for name, child in spec.subcommands.items()
            if name.startswith(current)
        }
        if not args and subcommands:
            for name, child in sorted(subcommands.items()):
                yield Completion(
                    name,
                    start_position=-len(current),
                    display_meta=child.help,
                )
            return

        if spec.completer is None:
            return
        try:
            candidates = spec.completer(args)
            for candidate in candidates:
                if candidate.startswith(current):
                    yield Completion(
                        candidate,
                        start_position=-len(current),
                    )
        except Exception:
            log.exception("命令参数补全失败: command=%s", spec.full_name())
