import asyncio

from fcatbot.app import FcatbotApp
from fcatbot.kernel.commands import (
    CommandContext,
    CommandRegistry,
    console_command,
    scan_plugin_commands,
)
from fcatbot.kernel.events import Event
from fcatbot.kernel.router import CommandRouter


def test_router_dispatches_with_context_and_async_authorization() -> None:
    class Commands:
        @console_command("who")
        def cmd_who(self, args: list[str], context: CommandContext) -> str:
            return f"{context.user_id}: {' '.join(args)}"

    registry = CommandRegistry()
    for spec in scan_plugin_commands(Commands(), "test"):
        registry.register(spec)

    async def authorize(context: CommandContext, node: str) -> bool:
        return context.user_id == "allowed" and node == "test:command.who"

    router = CommandRouter(registry, is_allowed=authorize)

    async def scenario() -> None:
        context = CommandContext(source="chat", user_id="allowed")
        assert (
            await router.handle("who argument", context=context) == "allowed: argument"
        )
        assert await router.handle("who", context=CommandContext(user_id="denied")) == (
            "[命令] 权限不足: 需要 test:command.who"
        )
        assert await router.handle("unknown", context=context) is None

    asyncio.run(scenario())


def test_app_routes_console_events_through_command_router(
    tmp_path, monkeypatch
) -> None:
    app = FcatbotApp(tmp_path / "app.yaml", [])
    app._admin.register()
    output: list[str] = []
    monkeypatch.setattr("fcatbot.app.console_print", output.append)

    assert not any(sub.spec == "console.command" for sub in app._bus._subs)

    async def scenario() -> None:
        event = Event(name="console.command", data="help", source="console")
        await app._dispatch_console_command(event)
        assert event.cancelled
        assert output

        unknown = Event(name="console.command", data="unknown", source="console")
        await app._dispatch_console_command(unknown)
        assert not unknown.cancelled

    try:
        asyncio.run(scenario())
    finally:
        app._admin.unregister()
