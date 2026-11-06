"""控制台命令的注册与分发。

参考 Mirai Console 规范:
- 每个命令有主名 + 别名、usage、description、permission
- 支持子命令树（CompositeCommand 风格）
- 命令权限自动派生为 {plugin}:command.{name}
- Tab 补全从注册表动态生成

声明示例::

    class WeatherPlugin(FcatbotPlugin):

        @console_command("weather", help="查天气")
        def cmd_weather(self, args): ...

        @cmd_weather.sub_command("query", help="查询", usage="weather query <city>")
        def cmd_query(self, args): ...

        @cmd_weather.sub_command("set", aliases=["config"])   # 名字从方法名推导
        def set_city(self, args): ...

父级声明的两种方式:

- **推荐**: ``@parent.sub_command(...)`` —— 声明期即 ``_attach``，重名冲突在类定义阶段抛错；
- **兼容**: ``@console_command(..., parent="lp")`` —— 声明期父节点可能尚未定义，
  由 :func:`scan_plugin_commands` 在扫描期按名字解析并补 ``_attach``。

分发约定:

- 处理器可同步或异步（``CommandHandler`` 已声明 ``Awaitable``）；
- 声明 ``context`` 形参的处理器由分发器注入 :class:`CommandContext`（见 :func:`accepts_context`）；
- 命令级门禁走 ``spec.resolved_permission()``，动作级门禁由处理器内部自行校验。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping

log = logging.getLogger("fcatbot.commands")

CommandHandler = Callable[..., Any | Awaitable[Any]]
CommandCompletionProvider = Callable[[list[str]], Iterable[str]]


class CommandError(RuntimeError):
    pass


class CommandConflict(CommandError):
    def __init__(self, name: str, existing_plugin: str):
        super().__init__(f"Command '{name}' already registered by '{existing_plugin}'")
        self.name = name
        self.existing_plugin = existing_plugin


@dataclass(frozen=True)
class CommandContext:
    """命令执行上下文（过渡桥）。"""

    source: str = "console"
    user_id: str | None = None
    group_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_console(self) -> bool:
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
    """单个命令的运行时元数据（供 CommandRegistry 使用）。"""

    name: str
    help: str = ""
    usage: str = ""
    aliases: list[str] = field(default_factory=list)
    plugin: str = ""
    handler: CommandHandler | None = None
    permission: str = ""
    parent: "CommandSpec | None" = None
    subcommands: dict[str, "CommandSpec"] = field(default_factory=dict)
    completer: CommandCompletionProvider | None = None

    def resolved_permission(self) -> str:
        if self.permission:
            return self.permission
        if self.plugin and self.plugin != "__framework__":
            return f"{self.plugin}:command.{self.name}"
        return f"console:command.{self.name}"

    def full_name(self) -> str:
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


# ---------- 声明期 API ----------


def _derive_name(func_name: str) -> str:
    if func_name.startswith("cmd_"):
        return func_name[4:]
    if func_name.startswith("_"):
        return func_name[1:]
    return func_name


class CommandNode:
    """命令声明节点（描述符 + 子命令挂载点）。

    作为**描述符**：类访问返回自身（保留元数据），实例访问返回绑定方法，
    这样注册表拿到的永远是可直接调用的协程。

    作为**挂载点**：``node.sub_command`` 在类定义阶段就把子节点挂上，
    避免运行时再做"父名 → 子 spec"的字符串解析。

    ``parent`` 字段支持两种取值：

    - ``CommandNode | None``：由 ``sub_command`` 声明期注入；
    - ``str``：老式 ``parent="lp"`` 写法，由 :func:`scan_plugin_commands` 扫描期解析。
    """

    __slots__ = (
        "func",
        "name",
        "help",
        "usage",
        "aliases",
        "permission",
        "completer",
        "parent",
        "subcommands",
        "_children",
        "_attr_name",
    )

    def __init__(
        self,
        func: Callable[..., Any],
        *,
        name: str | None = None,
        help: str = "",
        usage: str = "",
        aliases: list[str] | None = None,
        permission: str = "",
        completer: CommandCompletionProvider | None = None,
        parent: "CommandNode | str | None" = None,
    ) -> None:
        self.func = func
        self.name = name or _derive_name(getattr(func, "__name__", "cmd"))
        self.help = help
        self.usage = usage
        self.aliases = list(aliases or [])
        self.permission = permission
        self.completer = completer
        self.parent: "CommandNode | str | None" = parent
        self.subcommands: dict[str, CommandNode] = {}
        self._children: list[CommandNode] = []
        self._attr_name: str | None = None

    # ---- 描述符协议 ----
    def __set_name__(self, owner: type, name: str) -> None:
        self._attr_name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self
        return self.func.__get__(instance, owner)

    if TYPE_CHECKING:

        def __call__(self, *args, **kwargs):
            return self.func(*args, **kwargs)

    # ---- 子命令声明 ----
    def sub_command(self, func=None, **kwargs):
        """声明子命令。支持三种形态::

        @parent.sub_command                       # 无参
        def child(self, args): ...

        @parent.sub_command("child", aliases=["c"])   # 位置名
        @parent.sub_command(name="child", ...)        # 关键字名
        """

        def deco(f):
            child = CommandNode(f, parent=self, **kwargs)
            self._attach(child)
            return child

        if callable(func):
            return deco(func)
        if func is not None:
            kwargs["name"] = func
        return deco

    def _attach(self, child: "CommandNode") -> None:
        if child.name in self.subcommands:
            raise CommandConflict(child.name, "<subcommand>")
        for alias in child.aliases:
            if alias in self.subcommands:
                raise CommandConflict(alias, "<subcommand>")
        self._children.append(child)
        self.subcommands[child.name] = child
        for alias in child.aliases:
            self.subcommands[alias] = child

    # ---- 便捷 ----
    def full_name(self) -> str:
        parts = [self.name]
        p = self.parent
        while p is not None and not isinstance(p, str):
            parts.append(p.name)
            p = p.parent
        if isinstance(p, str):
            parts.append(p)
        return " ".join(reversed(parts))


def console_command(func=None, *, name: str | None = None, **kwargs):
    """把一个方法声明为控制台命令。

    ``completer`` 可选，接收当前参数之前已输入的参数列表并返回候选项。
    若传入类中的实例方法，会在注册时绑定到命令所属实例。
    """

    if callable(func):
        return CommandNode(func, name=name, **kwargs)
    if func is not None:
        name = func

    def deco(f):
        return CommandNode(f, name=name, **kwargs)

    return deco


# ---------- 注册表 ----------


class CommandRegistry:
    """命令注册表。支持层级结构（子命令）和别名。"""

    def __init__(self) -> None:
        self._roots: dict[str, CommandSpec] = {}
        self._aliases: dict[str, CommandSpec] = {}
        self._by_plugin: dict[str, set[str]] = {}

    # ---------- 注册 ----------
    def register(self, spec: CommandSpec) -> None:
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
        if not tokens:
            return None, []

        key = tokens[0]
        spec = self._roots.get(key) or self._aliases.get(key)
        if spec is None:
            return None, tokens

        idx = 1
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
        prefix = prefix.strip()
        results: list[str] = []

        if not prefix or " " not in prefix:
            for name in self._roots:
                if name.startswith(prefix):
                    results.append(name)
            for alias in self._aliases:
                if alias.startswith(prefix) and alias not in results:
                    results.append(alias)
            return sorted(results)

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
    """扫描实例上的所有 ``CommandNode``，转换为顶层 ``CommandSpec`` 树。

    支持两种父级声明：

    - ``@parent.sub_command(...)`` —— 声明期已 ``_attach``，这里直接复用；
    - ``@console_command(..., parent="lp")`` —— 声明期父节点可能尚未定义，
      这里在扫描期按名字解析并补 ``_attach``（向后兼容）。
    """
    # 1) 收集全部节点
    nodes: dict[int, CommandNode] = {}
    for attr_name in dir(type(plugin)):
        attr = getattr(type(plugin), attr_name, None)
        if isinstance(attr, CommandNode):
            nodes[id(attr)] = attr

    # 2) 字符串父级 → 节点引用（向后兼容）
    by_name: dict[str, CommandNode] = {}
    for node in nodes.values():
        by_name.setdefault(node.name, node)
    for node in nodes.values():
        parent_ref = node.parent
        if not isinstance(parent_ref, str):
            continue
        parent = by_name.get(parent_ref)
        if parent is None:
            raise CommandError(f"Command '{node.name}': unknown parent '{parent_ref}'")
        node.parent = parent
        if node not in parent._children:
            parent._attach(node)

    # 3) 展开根节点
    top_level: list[CommandSpec] = []
    seen: set[int] = set()

    for attr_name in dir(type(plugin)):
        attr = getattr(type(plugin), attr_name, None)
        if not isinstance(attr, CommandNode):
            continue
        if attr.parent is not None:
            continue  # 非根节点，由父节点递归处理
        if id(attr) in seen:
            continue
        seen.add(id(attr))
        top_level.append(_node_to_spec(attr, plugin, plugin_name))

    top_level.sort(key=lambda s: s.name)
    return top_level


def _node_to_spec(node: CommandNode, plugin: Any, plugin_name: str) -> CommandSpec:
    attr_name = node._attr_name or node.name
    bound = getattr(plugin, attr_name)
    completer = node.completer
    if inspect.isfunction(completer):
        completer = completer.__get__(plugin, type(plugin))
    spec = CommandSpec(
        name=node.name,
        help=node.help,
        usage=node.usage,
        aliases=list(node.aliases),
        plugin=plugin_name,
        handler=bound,
        permission=node.permission,
        completer=completer,
    )
    for child in node._children:
        child_spec = _node_to_spec(child, plugin, plugin_name)
        child_spec.parent = spec
        spec.subcommands[child_spec.name] = child_spec
        for alias in child_spec.aliases:
            spec.subcommands[alias] = child_spec
    return spec


# ---------- 分发 ----------


async def dispatch_command(
    registry: CommandRegistry,
    tokens: list[str],
    *,
    context: CommandContext,
    is_allowed: Callable[[CommandContext, str], bool | Awaitable[bool]],
) -> str | None:
    """解析、鉴权、调度一条命令。返回 None 表示未命中。

    - **命令级门禁**走 ``spec.resolved_permission()``；控制台放行由 ``is_allowed`` 决定；
    - **动作级门禁**（如 ``luckperms.user.permission.set``）由处理器内部 ``_authorize`` 负责；
    - 处理器同步返回透传；协程（如 ``cmd_editor`` / ``cmd_applyedits``）在这里被 await。
    """
    spec, args = registry.find(tokens)
    if spec is None:
        return None

    node = spec.resolved_permission()
    allowed = is_allowed(context, node)
    if inspect.isawaitable(allowed):
        allowed = await allowed
    if not allowed:
        return f"[命令] 权限不足: 需要 {node}"

    handler = spec.handler
    if handler is None:
        return f"[命令] {spec.full_name()} 未绑定处理器"

    if accepts_context(handler):
        result = handler(args, context=context)
    else:
        result = handler(args)

    if inspect.isawaitable(result):
        result = await result
    return result


def make_is_allowed(manager_provider: Callable[[], Any | None]):
    """构造 :func:`dispatch_command` 的 ``is_allowed`` 回调。

    控制台来源一律放行（本地操作员语义）；聊天来源按 ``manager.check`` 校验节点。
    """

    def is_allowed(context: CommandContext, node: str) -> bool:
        if context.is_console:
            return True
        if not context.user_id:
            return False
        manager = manager_provider()
        if manager is None:
            return False
        try:
            return bool(manager.check(str(context.user_id), node, None))
        except Exception:
            log.exception("授权检查失败: executor=%s node=%s", context.user_id, node)
            return False

    return is_allowed
