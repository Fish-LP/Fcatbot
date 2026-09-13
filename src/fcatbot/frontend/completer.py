"""基于 CommandRegistry 的 prompt_toolkit 补全器。

用法: 
    session = PromptSession(completer=CommandCompleter(registry))
"""

from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from fcatbot.kernel.commands import CommandRegistry


class CommandCompleter(Completer):
    """命令补全器。

    补全规则: 
    - 输入首词时补全所有顶层命令（含别名）
    - 已输入主命令后，补全其子命令
    - 补全项附带 help 文本作为显示元数据
    """

    def __init__(self, registry: CommandRegistry):
        self._registry = registry

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor

        # 只在行首或行中（未进入参数阶段）补全命令
        # 参数补全留给插件自行扩展（未来可通过 hooks 提供）
        stripped = text.lstrip()
        if not stripped:
            # 空行: 补全所有顶层命令
            for spec in self._registry.all_roots():
                yield Completion(
                    spec.name,
                    start_position=0,
                    display_meta=spec.help,
                )
            return

        candidates = self._registry.complete(stripped)
        for cand in candidates:
            spec = self._resolve_spec(cand)
            meta = spec.help if spec else ""
            yield Completion(
                cand,
                start_position=-len(stripped),
                display_meta=meta,
            )

    def _resolve_spec(self, path: str):
        parts = path.split()
        spec, _ = self._registry.find(parts)
        return spec