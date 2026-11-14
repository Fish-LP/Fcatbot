"""基于 prompt_toolkit 的运行时控制台。

- Tab 补全: CommandCompleter
- exit / quit 本地处理
- 其余命令走 EventBus → CommandRouter → CommandRegistry；AdminCommands 只负责注册内置命令
- patch_stdout() 确保日志在提示符上方
- handler 生命周期: 接管 root 上的控制台 handler，退出时原样还原，
  以便与 ``setup_logging`` / ``shutdown_logging`` 的 ``MANAGED_FLAG`` 协作而不泄漏
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable

from prompt_toolkit import ANSI, PromptSession, print_formatted_text
from prompt_toolkit.patch_stdout import patch_stdout

from fcatbot.frontend.completer import CommandCompleter
from fcatbot.kernel.commands import CommandRegistry
from fcatbot.kernel.events import Event, EventBus
from fcatbot.utils.logger import MANAGED_FLAG, LogConfig

log = logging.getLogger("fcatbot.console")

_CONSOLE_HANDLER_TAG = "_fcatbot_console_handler"


def console_print(message: str) -> None:
    """直接渲染到终端（不产生日志记录，也不受 handler 过滤级别影响）。"""
    print_formatted_text(ANSI(message))


def _safe_print(message: str) -> None:
    try:
        console_print(message)
    except Exception:
        pass


def _tag_handler(handler: logging.Handler) -> None:
    """同时打上本地标签和 logger 模块的托管标记，避免被 setup_logging 漏清。"""
    setattr(handler, _CONSOLE_HANDLER_TAG, True)
    setattr(handler, MANAGED_FLAG, True)


def _is_interactive() -> bool:
    for stream in (sys.stdin, sys.stdout):
        try:
            if stream is None or not stream.isatty():
                return False
        except (ValueError, AttributeError):
            return False
    return True


class _PromptToolkitHandler(logging.Handler):
    """把日志交给 prompt_toolkit 渲染，ANSI 颜色才能生效。

    ``print_formatted_text`` 会读写 prompt_toolkit 的 App 状态（invalidate/redraw），
    而 ``patch_stdout`` 只代理了 ``sys.stdout.write``，因此这里必须把日志调度回
    App 所在的事件循环线程，而不能在调用方线程里直接渲染。
    """

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        super().__init__()
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            self.handleError(record)
            return

        loop = self._loop
        if loop is None:
            _safe_print(msg)
            return

        try:
            in_loop = asyncio.get_running_loop() is loop
        except RuntimeError:
            in_loop = False
        if in_loop:
            _safe_print(msg)
            return

        try:
            loop.call_soon_threadsafe(_safe_print, msg)
        except RuntimeError:  # 事件循环已关闭
            _safe_print(msg)


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
        self._commands = commands
        # 延迟到 run() 里创建: PromptSession 会去探测终端，非 TTY 环境直接抛
        # NoConsoleScreenBufferError，构造期就崩会连累整个宿主
        self._session: PromptSession | None = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        # 被本实例替换下来的原始 handler，退出时归还 root
        self._replaced: list[logging.Handler] = []

    async def run(self) -> None:
        if not _is_interactive():
            log.info("非交互终端: 控制台输入已禁用（日志输出不受影响）")
            return

        try:
            self._session = self._create_session()
        except Exception:
            log.exception("控制台初始化失败，交互输入已禁用")
            return

        self._running = True
        self._loop = asyncio.get_running_loop()
        session = self._session
        try:
            with patch_stdout():
                self._takeover_logging()
                while self._running:
                    try:
                        line = await session.prompt_async(self._prompt)
                    except (EOFError, KeyboardInterrupt):
                        self._request_stop()
                        break

                    # stop() 会退出 prompt，此时返回 None 或 _running 已置 False
                    if line is None or not self._running:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    if line in ("exit", "quit"):
                        self._request_stop()
                        break

                    try:
                        await self._bus.publish(
                            Event(name="console.command", data=line, source="console")
                        )
                    except Exception:
                        log.exception("Failed to publish console command")
        finally:
            self._running = False
            self._restore_logging()
            self._loop = None

    def stop(self) -> None:
        """请求控制台循环退出（只停本循环，不通知宿主；停宿主请用 Ctrl-C/exit）。"""
        self._running = False
        self._wake_prompt()

    def _create_session(self) -> PromptSession:
        return PromptSession(
            completer=CommandCompleter(self._commands),
            complete_while_typing=False,  # 只在按 Tab 时补全
        )

    def _wake_prompt(self) -> None:
        """唤醒阻塞在 prompt_async 上的循环，否则 stop() 只能空等。"""
        session = self._session
        if session is None:
            return
        app = getattr(session, "app", None)
        if app is None:
            return
        loop = self._loop
        try:
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(app.exit)
            else:
                app.exit()
        except Exception:
            # prompt 未运行 / 已结束: 无需唤醒
            pass

    def _takeover_logging(self) -> None:
        root = logging.getLogger()

        # 清掉历史遗留（比如热重载残留 / 上一次运行没还原）
        self._restore_logging()

        candidates = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, (logging.FileHandler, logging.NullHandler))
        ]
        # 优先接管 setup_logging 装的 handler，避免热重载时把用户自建的 handler 换掉
        managed = [h for h in candidates if getattr(h, MANAGED_FLAG, False)]
        if managed:
            candidates = managed

        if not candidates:
            # setup_logging 还没跑: 兜底装一个不带颜色的
            handler = _PromptToolkitHandler(self._loop)
            handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] %(levelname)-8s %(name)s ➜ %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            handler.setLevel(LogConfig.from_env().console_level)
            _tag_handler(handler)
            root.addHandler(handler)
            return

        # 把每个控制台 handler 换成 prompt_toolkit 感知的，formatter/filter/level 全保留
        for target in candidates:
            handler = _PromptToolkitHandler(self._loop)
            handler.setFormatter(target.formatter)
            handler.setLevel(target.level)
            for f in target.filters:
                handler.addFilter(f)
            _tag_handler(handler)

            root.removeHandler(target)
            root.addHandler(handler)
            self._replaced.append(target)

    def _restore_logging(self) -> None:
        root = logging.getLogger()
        for h in root.handlers[:]:
            if getattr(h, _CONSOLE_HANDLER_TAG, False):
                root.removeHandler(h)
                try:
                    h.close()
                except Exception:
                    pass

        replaced, self._replaced = self._replaced, []
        if not replaced:
            return
        # 期间 setup_logging 已重装过控制台 handler（或被关闭）时不再复活，避免重复输出
        if _has_managed_console_handler(root):
            return

        for h in replaced:
            if getattr(h, "_closed", False) or h in root.handlers:
                continue
            root.addHandler(h)


def _has_managed_console_handler(root: logging.Logger) -> bool:
    return any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, (logging.FileHandler, logging.NullHandler))
        and getattr(h, MANAGED_FLAG, False)
        for h in root.handlers
    )
