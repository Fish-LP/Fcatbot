"""基于 prompt_toolkit 的运行时控制台。

- Tab 补全: CommandCompleter
- exit / quit 本地处理
- 其余命令走 EventBus → CommandRouter → CommandRegistry；AdminCommands 只负责注册内置命令
- patch_stdout() 确保日志在提示符上方
"""

from __future__ import annotations

import logging
import logging.handlers
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from fcatbot.frontend.completer import CommandCompleter
from fcatbot.kernel.commands import CommandRegistry
from fcatbot.kernel.events import Event, EventBus

log = logging.getLogger("fcatbot.console")

_CONSOLE_HANDLER_TAG = "_fcatbot_console_handler"


class _PromptToolkitHandler(logging.Handler):
    """把日志交给 prompt_toolkit 渲染，ANSI 颜色才能生效。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            self.handleError(record)
            return
        try:
            console_print(msg)
        except Exception:
            self.handleError(record)


class ConsoleApp:
    def __init__(
        self,
        bus: EventBus,
        request_stop: Callable[[], None],
        *,
        commands: CommandRegistry,
        prompt: str = "fcatbot> ",
    ):
        self._bus = bus
        self._request_stop = request_stop
        self._prompt = prompt
        self._session = PromptSession(
            completer=CommandCompleter(commands),
            complete_while_typing=False,  # 只在按 Tab 时补全
        )
        self._running = False

    async def run(self) -> None:
        self._running = True
        with patch_stdout():
            self._redirect_logging()
            while self._running:
                try:
                    line = await self._session.prompt_async(self._prompt)
                except (EOFError, KeyboardInterrupt):
                    self._running = False
                    self._request_stop()
                    break

                line = line.strip()
                if not line:
                    continue

                if line in ("exit", "quit"):
                    self._running = False
                    self._request_stop()
                    break

                try:
                    await self._bus.publish(
                        Event(name="console.command", data=line, source="console")
                    )
                except Exception:
                    log.exception("Failed to publish console command")

    def stop(self) -> None:
        self._running = False

    def _redirect_logging(self) -> None:
        root = logging.getLogger()

        # 清掉历史遗留（比如热重载残留）
        for h in root.handlers[:]:
            if getattr(h, _CONSOLE_HANDLER_TAG, False):
                root.removeHandler(h)

        # 找到 setup_logging 装的 console StreamHandler
        target = None
        for h in root.handlers:
            if type(
                h
            ) is logging.StreamHandler and not isinstance(  # 精确匹配，不误伤子类
                h, logging.FileHandler
            ):
                target = h
                break

        if target is None:
            # setup_logging 还没跑: 兜底装一个不带颜色的
            handler = _PromptToolkitHandler()
            handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] %(levelname)-8s %(name)s ➜ %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            setattr(handler, _CONSOLE_HANDLER_TAG, True)
            root.addHandler(handler)
            return

        # 把 target 换成 prompt_toolkit 感知的 handler，formatter/filter/level 全保留
        handler = _PromptToolkitHandler()
        handler.setFormatter(target.formatter)
        handler.setLevel(target.level)
        for f in target.filters:
            handler.addFilter(f)
        setattr(handler, _CONSOLE_HANDLER_TAG, True)

        root.removeHandler(target)
        root.addHandler(handler)


def console_print(message: str) -> None:
    from prompt_toolkit import ANSI, print_formatted_text

    print_formatted_text(ANSI(message))
