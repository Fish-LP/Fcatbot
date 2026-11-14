import asyncio
import contextlib
import logging
import threading

import pytest

from fcatbot.frontend import console as console_mod
from fcatbot.frontend.console import (
    _CONSOLE_HANDLER_TAG,
    ConsoleApp,
    _PromptToolkitHandler,
)
from fcatbot.kernel.commands import CommandRegistry
from fcatbot.kernel.events import EventBus
from fcatbot.utils.logger import MANAGED_FLAG, _remove_managed_handlers


class _StubApp:
    def __init__(self) -> None:
        self.exit_calls = 0

    def exit(self) -> None:
        self.exit_calls += 1


class _StubPromptSession:
    def __init__(self, *args, **kwargs) -> None:
        self.app = _StubApp()


@pytest.fixture()
def root():
    root_logger = logging.getLogger()
    saved = root_logger.handlers[:]
    try:
        yield root_logger
    finally:
        root_logger.handlers[:] = saved


@pytest.fixture()
def make_app(monkeypatch):
    monkeypatch.setattr(console_mod, "PromptSession", _StubPromptSession)
    return lambda: ConsoleApp(EventBus(), lambda: None, commands=CommandRegistry())


def _managed_stream_handler(level: int = logging.INFO) -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setLevel(level)
    setattr(handler, MANAGED_FLAG, True)
    return handler


def test_takeover_replaces_stream_handler_and_marks_managed(root, make_app) -> None:
    original = _managed_stream_handler(logging.WARNING)
    root.handlers[:] = [original]

    make_app()._takeover_logging()

    assert original not in root.handlers
    assert len(root.handlers) == 1
    handler = root.handlers[0]
    assert isinstance(handler, _PromptToolkitHandler)
    assert getattr(handler, _CONSOLE_HANDLER_TAG, False)
    assert getattr(handler, MANAGED_FLAG, False)
    assert handler.level == logging.WARNING
    assert handler.formatter is original.formatter


def test_managed_cleanup_reclaims_prompt_handler(root, make_app) -> None:
    """setup_logging / shutdown_logging 走 _remove_managed_handlers，不能漏掉 console handler。"""
    root.handlers[:] = [_managed_stream_handler()]
    app = make_app()
    app._takeover_logging()

    _remove_managed_handlers(root)

    assert not any(isinstance(h, _PromptToolkitHandler) for h in root.handlers)


def test_restore_puts_original_handler_back(root, make_app) -> None:
    original = _managed_stream_handler()
    root.handlers[:] = [original]
    app = make_app()

    app._takeover_logging()
    app._restore_logging()

    assert root.handlers == [original]


def test_restore_skips_reinstalled_handler_from_setup_logging(root, make_app) -> None:
    root.handlers[:] = [_managed_stream_handler()]
    app = make_app()
    app._takeover_logging()

    # 模拟 console 运行期间再次调用 setup_logging：清旧 handler + 装新 console handler
    _remove_managed_handlers(root)
    reinstalled = _managed_stream_handler()
    root.addHandler(reinstalled)

    app._restore_logging()

    assert root.handlers == [reinstalled]


def test_takeover_covers_stream_handler_subclasses(root, make_app) -> None:
    class _CustomStreamHandler(logging.StreamHandler):
        pass

    original = _CustomStreamHandler()
    original.setLevel(logging.ERROR)
    root.handlers[:] = [original]

    make_app()._takeover_logging()

    handler = root.handlers[0]
    assert isinstance(handler, _PromptToolkitHandler)
    assert handler.level == logging.ERROR


def test_fallback_handler_takes_console_level(root, make_app, monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    root.handlers[:] = []

    make_app()._takeover_logging()

    handler = root.handlers[0]
    assert isinstance(handler, _PromptToolkitHandler)
    assert handler.level == logging.WARNING


def test_handler_dispatches_emit_to_event_loop_thread(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        console_mod,
        "console_print",
        lambda msg: calls.append((msg, threading.get_ident())),
    )

    async def scenario() -> None:
        loop_thread = threading.get_ident()
        handler = _PromptToolkitHandler(asyncio.get_running_loop())

        def _emit_from_worker() -> None:
            handler.emit(
                logging.LogRecord(
                    "test", logging.INFO, __file__, 1, "hello", None, None
                )
            )

        await asyncio.get_running_loop().run_in_executor(None, _emit_from_worker)
        await asyncio.sleep(0.05)

        assert calls == [("hello", loop_thread)]

    asyncio.run(scenario())


def test_stop_wakes_prompt(root, make_app) -> None:
    app = make_app()
    app._session = _StubPromptSession()

    async def scenario() -> None:
        app._loop = asyncio.get_running_loop()
        await asyncio.get_running_loop().run_in_executor(None, app.stop)

    asyncio.run(scenario())

    assert app._running is False
    assert app._session.app.exit_calls == 1


def test_stop_unblocks_a_real_prompt(root, make_app) -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    app = make_app()

    with create_pipe_input() as pipe_input:
        app._session = PromptSession(input=pipe_input, output=DummyOutput())

        async def scenario() -> str | None:
            app._loop = asyncio.get_running_loop()
            app._running = True
            prompt_task = asyncio.create_task(app._session.prompt_async("> "))
            await asyncio.sleep(0.1)
            assert not prompt_task.done()

            app.stop()

            await asyncio.wait_for(prompt_task, timeout=2)
            return prompt_task.result()

        assert asyncio.run(scenario()) is None


def test_run_exits_on_exit_command_and_restores_logging(root, monkeypatch) -> None:
    stopped: list[bool] = []

    class _Session(_StubPromptSession):
        async def prompt_async(self, *args, **kwargs):
            return "exit"

    monkeypatch.setattr(console_mod, "PromptSession", _Session)
    monkeypatch.setattr(console_mod, "_is_interactive", lambda: True)
    monkeypatch.setattr(console_mod, "patch_stdout", contextlib.nullcontext)

    original = _managed_stream_handler()
    root.handlers[:] = [original]
    app = ConsoleApp(
        EventBus(), lambda: stopped.append(True), commands=CommandRegistry()
    )

    asyncio.run(app.run())

    assert stopped == [True]
    assert app._running is False
    assert root.handlers == [original]


def test_run_returns_immediately_without_tty(root, make_app, monkeypatch) -> None:
    monkeypatch.setattr(console_mod, "_is_interactive", lambda: False)
    original = _managed_stream_handler()
    root.handlers[:] = [original]
    app = make_app()

    asyncio.run(app.run())

    assert app._running is False
    assert root.handlers == [original]
