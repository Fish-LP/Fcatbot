from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from fcatbot.app import FcatbotApp
from fcatbot.builtin import AdminCommands
from fcatbot.frontend.completer import CommandCompleter
from fcatbot.kernel.commands import (
    CommandRegistry,
    CommandSpec,
    console_command,
    scan_plugin_commands,
)


def _completions(completer: CommandCompleter, text: str) -> list:
    return list(completer.get_completions(Document(text), CompleteEvent()))


def test_completes_roots_subcommands_and_aliases() -> None:
    registry = CommandRegistry()
    root = CommandSpec("lp", help="permissions", aliases=["perm"])
    user = CommandSpec("user", help="manage users", aliases=["u"])
    permission = CommandSpec("permission", help="manage permissions")
    set_permission = CommandSpec("set", help="set a permission")
    registry.register(root)
    registry.register_subcommand(root, user)
    registry.register_subcommand(user, permission)
    registry.register_subcommand(permission, set_permission)
    completer = CommandCompleter(registry)

    roots = _completions(completer, "p")
    assert [item.text for item in roots] == ["perm"]
    assert roots[0].start_position == -1

    children = _completions(completer, "lp u")
    assert {item.text for item in children} == {"u", "user"}
    assert all(item.start_position == -1 for item in children)

    nested = _completions(completer, "lp user permission s")
    assert [(item.text, item.display_meta_text) for item in nested] == [
        ("set", "set a permission")
    ]


def test_does_not_complete_command_arguments() -> None:
    registry = CommandRegistry()
    root = CommandSpec("lp")
    user = CommandSpec("user")
    permission = CommandSpec("permission")
    registry.register(root)
    registry.register_subcommand(root, user)
    registry.register_subcommand(user, permission)
    completer = CommandCompleter(registry)

    assert _completions(completer, "lp user 10001 ") == []
    assert _completions(completer, "lp user permission set echo.use ") == []
    assert _completions(completer, "lp user x") == []


def test_only_indents_and_argument_only_commands_do_not_offer_commands() -> None:
    registry = CommandRegistry()
    registry.register(CommandSpec("echo"))
    completer = CommandCompleter(registry)

    assert [item.text for item in _completions(completer, "   ")] == ["echo"]
    assert _completions(completer, "echo ") == []


def test_custom_argument_completer_receives_previous_arguments() -> None:
    class Commands:
        def _choices(self, args: list[str]) -> list[str]:
            return ["apple", "apricot"] if not args else ["second"]

        @console_command("choose", completer=_choices)
        def cmd_choose(self, args: list[str]) -> str:
            return ""

    registry = CommandRegistry()
    for spec in scan_plugin_commands(Commands(), "test"):
        registry.register(spec)
    completer = CommandCompleter(registry)

    assert [item.text for item in _completions(completer, "choose ap")] == [
        "apple",
        "apricot",
    ]
    assert [item.text for item in _completions(completer, "choose apple sec")] == [
        "second"
    ]


def test_enable_and_disable_complete_plugins_by_runtime_state(
    tmp_path, monkeypatch
) -> None:
    app = FcatbotApp(tmp_path / "app.yaml", [])
    app._discovered_plugins = {
        "ActivePlugin": object,
        "InactivePlugin": object,
    }

    class ActivePlugin:
        name = "ActivePlugin"

    monkeypatch.setattr(app._pm, "get_active_plugins", lambda: [ActivePlugin()])
    admin = AdminCommands(app)
    admin.register()
    completer = CommandCompleter(app._commands)

    try:
        assert [item.text for item in _completions(completer, "enable In")] == [
            "InactivePlugin"
        ]
        assert [item.text for item in _completions(completer, "disable Ac")] == [
            "ActivePlugin"
        ]
        assert _completions(completer, "enable InactivePlugin ") == []
    finally:
        admin.unregister()
