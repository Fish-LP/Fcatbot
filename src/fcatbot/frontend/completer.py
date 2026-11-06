"""基于 CommandRegistry 的 prompt_toolkit 补全器。

用法:
    session = PromptSession(completer=CommandCompleter(registry))
"""

from __future__ import annotations

from collections.abc import Iterator

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from fcatbot.kernel.commands import CommandRegistry


class CommandCompleter(Completer):
    """命令补全器。

    补全规则:
    - 输入首词时补全所有顶层命令（含别名）；
    - 只有当前词仍匹配已知命令/子命令时才补全，进入参数位置后停止补全。
    - 补全项附带 help 文本作为显示元数据
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

        parent, args = self._registry.find(parts)
        if parent is None or args:
            return

        for name, spec in sorted(parent.subcommands.items()):
            if name.startswith(current):
                yield Completion(
                    name,
                    start_position=-len(current),
                    display_meta=spec.help,
                )
