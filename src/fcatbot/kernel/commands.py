"""控制台命令的注册与分发。

参考 Mirai Console 规范:
- 每个命令有主名 + 别名、usage、description、permission
- 支持子命令树（CompositeCommand 风格）
- 命令权限自动派生为 {plugin}:command.{name}
- Tab 补全从注册表动态生成

插件声明示例:
    class WeatherPlugin(FcatbotPlugin):
        @console_command("weather", help="查天气", permission="weather.query")
        async def cmd_weather(self, args):
            ...
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

log = logging.getLogger("fcatbot.commands")

# 处理器形态: ``(args)`` 或 ``(args, context)``（声明 ``context`` 形参时接收上下文）
CommandHandler = Callable[..., Any | Awaitable[Any]]


class CommandError(RuntimeError):
    pass


class CommandConflict(CommandError):
    def __init__(self, name: str, existing_plugin: str):
        super().__init__(f"Command '{name}' already registered by '{existing_plugin}'")
        self.name = name
        self.existing_plugin = existing_plugin


@dataclass(frozen=True)
class CommandContext:
    """命令执行上下文（过渡桥）。

    在 M3 的 ``CommandSender`` 落地前，为命令处理器提供**来源感知**能力:

    - ``source``: 命令来源（``console`` / 未来的 ``chat``、``web`` 等）；
    - ``user_id`` / ``group_id``: 来源身份（聊天适配器在事件 ``metadata`` 中提供）；
    - ``metadata``: 原始事件元数据（供扩展字段使用）。

    约定: 处理器通过声明 ``context`` 形参选择性接收（见 :func:`accepts_context`）；
    未提供上下文（``None``）视为**本地控制台**（兼容直接调用与测试）。
    """

    source: str = "console"
    user_id: str | None = None
    group_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_console(self) -> bool:
        """是否来自本地控制台。"""
        return self.source == "console"


def accepts_context(handler: Any) -> bool:
    """判断命令处理器是否声明了 ``context`` 形参。"""
    try:
        parameters = inspect.signature(handler).parameters
    except (TypeError, ValueError):
        return False
    return "context" in parameters


@dataclass
class CommandSpec:
    """单个命令的元数据。

    权限节点命名规则（参考 Mirai）:
    - 显式指定 permission 时用它
    - 否则自动派生为 {plugin}:command.{name}
    """

    name: str
    help: str = ""
    usage: str = ""
    aliases: list[str] = field(default_factory=list)
    plugin: str = ""
    handler: CommandHandler | None = None
    permission: str = ""
    parent: "CommandSpec | None" = None
    subcommands: dict[str, "CommandSpec"] = field(default_factory=dict)

    def resolved_permission(self) -> str:
        """返回最终权限节点。"""
        if self.permission:
            return self.permission
        if self.plugin and self.plugin != "__framework__":
            return f"{self.plugin}:command.{self.name}"
        return f"console:command.{self.name}"

    def full_name(self) -> str:
        """返回从根到当前节点的完整命令路径，如 'weather query'。"""
        parts: list[str] = [self.name]
        p = self.parent
        while p is not None:
            parts.append(p.name)
            p = p.parent
        return " ".join(reversed(parts))

    def usage_text(self) -> str:
        if self.usage:
            return self.usage
        return self.full_name()

    def source_text(self) -> str:
        return self.plugin or "framework"


def console_command(
    name: str | None = None,
    *,
    help: str = "",
    usage: str = "",
    aliases: list[str] | None = None,
    permission: str = "",
    parent: str = "",
):
    """声明一个控制台命令。

    Args:
        name: 命令名。为 None 时从函数名推导（去掉 cmd_ 前缀）。
        help: 一句话说明。
        usage: 完整用法，如 "weather <city>"。
        aliases: 别名列表。
        permission: 权限节点。为空时自动派生为 {plugin}:command.{name}。
        parent: 父命令名，用于声明子命令。空表示顶层命令。
    """

    def decorator(func):
        cmd_name = name
        if cmd_name is None:
            cmd_name = func.__name__
            if cmd_name.startswith("cmd_"):
                cmd_name = cmd_name[4:]
            elif cmd_name.startswith("_"):
                cmd_name = cmd_name[1:]

        func.__console_command__ = {
            "name": cmd_name,
            "help": help,
            "usage": usage,
            "aliases": list(aliases or []),
            "permission": permission,
            "parent": parent,
        }
        return func

    return decorator


class CommandRegistry:
    """命令注册表。支持层级结构（子命令）和别名。"""

    def __init__(self) -> None:
        self._roots: dict[str, CommandSpec] = {}  # 主名 → spec
        self._aliases: dict[str, CommandSpec] = {}  # 别名 → spec
        self._by_plugin: dict[str, set[str]] = {}  # 插件 → 根命令名集合

    # ---------- 注册 ----------
    def register(self, spec: CommandSpec) -> None:
        """注册一个顶层命令及其子命令树。"""
        if spec.name in self._roots:
            existing = self._roots[spec.name]
            raise CommandConflict(spec.name, existing.plugin or "framework")
        if spec.name in self._aliases:
            existing = self._aliases[spec.name]
            raise CommandConflict(spec.name, existing.plugin or "framework")

        self._roots[spec.name] = spec
        for alias in spec.aliases:
            if alias in self._roots or alias in self._aliases:
                raise CommandConflict(alias, spec.plugin or "framework")
            self._aliases[alias] = spec

        self._by_plugin.setdefault(spec.plugin, set()).add(spec.name)

    def register_subcommand(self, parent: CommandSpec, spec: CommandSpec) -> None:
        """注册子命令到已存在的父命令。"""
        spec.parent = parent
        if spec.name in parent.subcommands:
            raise CommandConflict(
                f"{parent.full_name()} {spec.name}",
                parent.subcommands[spec.name].plugin or "framework",
            )
        parent.subcommands[spec.name] = spec
        for alias in spec.aliases:
            parent.subcommands[alias] = spec

    def unregister_by_plugin(self, plugin: str) -> int:
        names = list(self._by_plugin.pop(plugin, set()))
        removed = 0
        for name in names:
            spec = self._roots.pop(name, None)
            if spec is None:
                continue
            removed += 1
            for alias in spec.aliases:
                self._aliases.pop(alias, None)
        return removed

    # ---------- 查询 ----------
    def find(self, tokens: list[str]) -> tuple[CommandSpec | None, list[str]]:
        """按 tokens 查找命令。

        Returns:
            (匹配到的 spec, 剩余参数)。
            未匹配返回 (None, tokens)。
            匹配到中间节点（有子命令但 tokens 已用尽）返回 (spec, [])。
        """
        if not tokens:
            return None, []

        key = tokens[0]
        spec = self._roots.get(key) or self._aliases.get(key)
        if spec is None:
            return None, tokens

        idx = 1
        # 逐层匹配子命令
        while idx < len(tokens):
            next_key = tokens[idx]
            child = spec.subcommands.get(next_key)
            if child is None:
                break
            spec = child
            idx += 1

        return spec, tokens[idx:]

    def all_roots(self) -> list[CommandSpec]:
        return sorted(self._roots.values(), key=lambda s: (s.plugin, s.name))

    def complete(self, prefix: str) -> list[str]:
        """返回匹配 prefix 的命令名（含别名和子命令路径）。"""
        prefix = prefix.strip()
        results: list[str] = []

        if not prefix or " " not in prefix:
            # 补全顶层命令
            for name in self._roots:
                if name.startswith(prefix):
                    results.append(name)
            for alias in self._aliases:
                if alias.startswith(prefix) and alias not in results:
                    results.append(alias)
            return sorted(results)

        # 补全子命令: "weather q" → 找 weather 的子命令以 q 开头的
        parts = prefix.split()
        head = parts[0]
        spec = self._roots.get(head) or self._aliases.get(head)
        if spec is None:
            return []

        for token in parts[1:-1]:
            spec = spec.subcommands.get(token)
            if spec is None:
                return []

        last = parts[-1]
        for name in spec.subcommands:
            if name.startswith(last):
                results.append(" ".join(parts[:-1] + [name]))
        return sorted(results)


# ---------- 扫描 ----------


def scan_plugin_commands(plugin: Any, plugin_name: str) -> list[CommandSpec]:
    """扫描实例上所有 @console_command 方法，返回顶层 spec 列表。

    子命令（parent 非空）先暂存，待父命令注册后挂载。
    """
    top_level: list[CommandSpec] = []
    children: list[tuple[str, CommandSpec]] = []

    for attr_name in dir(type(plugin)):
        attr = getattr(type(plugin), attr_name, None)
        if attr is None:
            continue
        marker = getattr(attr, "__console_command__", None)
        if marker is None:
            continue

        bound = getattr(plugin, attr_name)
        spec = CommandSpec(
            name=marker["name"],
            help=marker["help"],
            usage=marker["usage"],
            aliases=list(marker["aliases"]),
            plugin=plugin_name,
            handler=bound,
            permission=marker["permission"],
        )
        if marker["parent"]:
            children.append((marker["parent"], spec))
        else:
            top_level.append(spec)

    # 挂载子命令
    by_name = {s.name: s for s in top_level}
    for parent_name, child in children:
        parent = by_name.get(parent_name)
        if parent is None:
            log.error(
                "Subcommand '%s' of plugin '%s' has unknown parent '%s'",
                child.name,
                plugin_name,
                parent_name,
            )
            continue
        child.parent = parent
        parent.subcommands[child.name] = child
        for alias in child.aliases:
            parent.subcommands[alias] = child

    return top_level
