"""框架级管理命令。

help 渲染特性: 
- 扁平化展开: 子命令独立成行，不再显示 <subcommand> 占位符
- 分组渲染: 按插件分组，每组有标题和色条
- 宽度感知: CJK / Emoji 按 wcwidth 计宽，ANSI 码最后注入
- 动态对齐: 命令列宽全局统一，跨页不跳动
- 分页: 默认每页 16 行，可通过 -p N 翻页
- 权限标签右对齐到行尾
"""

from __future__ import annotations

import inspect
import logging

from fcatbot.frontend.term import pad_end, terminal_size, truncate, width as term_width
from fcatbot.frontend.theme import Theme
from fcatbot.kernel.commands import (
    CommandConflict,
    CommandContext,
    CommandRegistry,
    CommandSpec,
    accepts_context,
    console_command,
    scan_plugin_commands,
)
from fcatbot.kernel.events import Event
from fcatbot.lp_commands import LuckPermsCommands

log = logging.getLogger("fcatbot.admin")

FRAMEWORK_PLUGIN = "core"


def _as_str(value: object) -> str | None:
    return None if value is None else str(value)


def _build_command_context(event: Event) -> CommandContext:
    """从命令事件构建执行上下文（M3 ``CommandSender`` 之前的过渡桥）。"""
    metadata = dict(event.metadata)
    return CommandContext(
        source=str(event.source or ""),
        user_id=_as_str(metadata.get("user_id")),
        group_id=_as_str(metadata.get("group_id")),
        metadata=metadata,
    )

# 渲染常量
_GAP = 2
_MIN_CMD_COL = 18
_MAX_CMD_COL = 48


class AdminCommands:
    PRIORITY = 100

    def __init__(self, app):
        self._app = app
        self._registry: CommandRegistry = app._commands
        self._lp = LuckPermsCommands(app)
        self._token: str | None = None

    # ---------- 生命周期 ----------
    def register(self) -> None:
        if self._token is not None:
            return
        for component in (self, self._lp):
            specs = scan_plugin_commands(component, FRAMEWORK_PLUGIN)
            for spec in specs:
                try:
                    self._registry.register(spec)
                except CommandConflict:
                    log.exception("Framework command conflict: %s", spec.name)
        self._token = self._app._bus.subscribe(
            "console.command", self._handle, priority=self.PRIORITY
        )

    def unregister(self) -> None:
        if self._token is not None:
            self._app._bus.unsubscribe(self._token)
            self._token = None
        self._registry.unregister_by_plugin(FRAMEWORK_PLUGIN)

    # ---------- 分发 ----------
    async def _handle(self, event: Event) -> None:
        text = str(event.data).strip()
        if not text:
            return
        tokens = text.split()
        spec, args = self._registry.find(tokens)
        if spec is None:
            return
        event.cancel()

        if spec.handler is None:
            _print(self._render_detail(spec))
            return

        if not await self._check_permission(spec, event):
            _print(f"[admin] 权限不足: {spec.resolved_permission()}")
            return

        context = _build_command_context(event)
        try:
            if accepts_context(spec.handler):
                result = spec.handler(args, context)
            else:
                result = spec.handler(args)
            if inspect.isawaitable(result):
                result = await result
            if result:
                _print(str(result))
        except Exception as exc:
            log.exception("Command '%s' failed", spec.full_name())
            _print(f"[error] {exc}")

    async def _check_permission(self, spec: CommandSpec, event: Event) -> bool:
        if event.source == "console":
            return True
        user_id = event.metadata.get("user_id")
        if not user_id:
            return False
        return await self._app._permissions.has_permission(
            str(user_id), spec.resolved_permission()
        )

    # ==================== help 命令 ====================

    @console_command(
        "help",
        help="显示所有命令或命令详情",
        usage="help [命令|插件] [-p N]",
        aliases=["?"],
    )
    def _cmd_help(self, args: list[str]) -> str:
        # help -p N
        if args and args[0] == "-p":
            try:
                page = int(args[1]) if len(args) > 1 else 1
            except ValueError:
                page = 1
            return self._render_list(page=page)

        # help <命令> / help <插件>
        if args:
            spec, _ = self._registry.find(args)
            if spec is not None:
                return self._render_detail(spec)
            # 按插件名过滤
            by_plugin = self._filter_by_plugin(args[0])
            if by_plugin:
                return self._render_list(filter_plugin=args[0])
            return f"[help] 未找到与 '{args[0]}' 相关的命令"

        return self._render_list()

    # ==================== 列表渲染 ====================

    def _render_list(
        self,
        *,
        page: int = 1,
        filter_plugin: str | None = None,
        page_size: int | None = None,
    ) -> str:
        roots = self._registry.all_roots()
        if filter_plugin:
            roots = [r for r in roots if r.plugin == filter_plugin]
        if not roots:
            return f"[help] 无可用命令"

        # 扁平化: 收集所有命令（含子命令），去重
        rows = self._flatten(roots)

        # 计算全局命令列宽（跨页统一）
        cmd_col = self._compute_cmd_col(rows)

        # 分组
        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(row["plugin"], []).append(row)

        # 分页
        columns, lines = terminal_size()
        ps = page_size if page_size is not None else max(6, min(lines - 8, 40))

        pages = self._paginate(groups, cmd_col, columns, ps)
        total_pages = len(pages)
        p = max(1, min(page, total_pages))

        # 组装输出
        rule = Theme.dim("─" * columns)
        lines_out: list[str] = [
            rule,
            " " + Theme.title("帮助")
            + Theme.dim(f" · 共 {len(rows)} 条 · {p}/{total_pages} 页"),
            rule,
            "",
        ]
        lines_out.extend(pages[p - 1])
        lines_out.extend([
            "",
            rule,
            Theme.dim(" help <命令> 查看详情 · help <插件> 筛选 · help -p N 翻页"),
            rule,
        ])
        return "\n".join(lines_out)

    # ---------- 扁平化 ----------

    @staticmethod
    def _flatten(roots: list[CommandSpec]) -> list[dict]:
        """把命令树展开为行列表。子命令独立成行，使用完整路径。"""
        rows: list[dict] = []
        seen: set[int] = set()

        def walk(spec: CommandSpec, depth: int):
            if id(spec) in seen:
                return
            seen.add(id(spec))
            rows.append({
                "spec": spec,
                "plugin": spec.plugin or "内置",
                "depth": depth,
                "usage": spec.usage_text(),
                "help": spec.help or "",
                "permission": spec.resolved_permission(),
                "is_root": depth == 0,
                "has_subs": bool(spec.subcommands),
            })
            for sub in spec.subcommands.values():
                walk(sub, depth + 1)

        for root in roots:
            walk(root, 0)
        return rows

    # ---------- 命令列宽 ----------

    @staticmethod
    def _compute_cmd_col(rows: list[dict]) -> int:
        """全局命令列宽。"""
        max_w = 0
        for row in rows:
            max_w = max(max_w, term_width(row["usage"]))
        return max(_MIN_CMD_COL, min(max_w + 2, _MAX_CMD_COL))

    # ---------- 分页 ----------

    @staticmethod
    def _paginate(
        groups: dict[str, list[dict]],
        cmd_col: int,
        columns: int,
        page_size: int,
    ) -> list[list[str]]:
        """按组渲染，每页 page_size 行。"""
        pages: list[list[str]] = []
        current: list[str] = []
        used = 0

        def flush():
            nonlocal current, used
            if current:
                pages.append(current)
                current = []
                used = 0

        for plugin_name, items in groups.items():
            header = [
                "",
                "  " + Theme.plugin(f"▎{plugin_name}")
                + Theme.dim(f"  {len(items)} 条命令"),
            ]
            # 标题 + 至少一条命令
            if used > 0 and used + len(header) + 1 > page_size:
                flush()

            current.extend(header)
            used += len(header)

            for item in items:
                if used + 1 > page_size:
                    flush()
                current.append(_render_item(item, cmd_col, columns))
                used += 1

        flush()
        return pages

    # ---------- 详情渲染 ----------

    def _render_detail(self, spec: CommandSpec) -> str:
        columns, _ = terminal_size()
        label_w = 8
        lines: list[str] = [""]

        lines.append(
            "  " + Theme.plugin(f"▎{spec.plugin or '内置'}")
            + Theme.dim(" / ") + Theme.title(spec.name)
        )
        lines.append("  " + Theme.dim("─" * max(8, columns - 4)))
        lines.append(_detail_row("用法", spec.usage_text(), label_w))
        if spec.aliases:
            lines.append(_detail_row("别名", ", ".join(spec.aliases), label_w))
        lines.append(_detail_row("权限", spec.resolved_permission(), label_w))
        if spec.help:
            lines.append(_detail_row("说明", spec.help, label_w))

        subs = self._unique_subs(spec)
        if subs:
            lines.append(_detail_row("子命令", "", label_w))
            for sub in subs:
                sub_usage = sub.usage_text()
                lines.append(
                    "  " + " " * label_w
                    + Theme.cmd(sub_usage) + "  "
                    + (sub.help or "")
                )
        return "\n".join(lines)

    @staticmethod
    def _unique_subs(spec: CommandSpec) -> list[CommandSpec]:
        unique: dict[int, CommandSpec] = {}
        for sub in spec.subcommands.values():
            unique[id(sub)] = sub
        return sorted(unique.values(), key=lambda s: s.name)

    def _filter_by_plugin(self, name: str) -> list[CommandSpec]:
        return [
            r for r in self._registry.all_roots()
            if name.lower() in r.plugin.lower()
        ]

    # ==================== 框架命令 ====================

    @console_command("plugins", help="列出活跃插件")
    def _cmd_plugins(self, args: list[str]) -> str:
        plugins = list(self._app._pm.get_active_plugins())
        if not plugins:
            return "[admin] 无活跃插件"
        lines = [f"[admin] 活跃插件 ({len(plugins)}):"]
        for p in plugins:
            deps = getattr(p, "depends_on", []) or []
            dep_str = f" deps={deps}" if deps else ""
            lines.append(f"  {p.name}@{p.version} ({type(p).__name__}){dep_str}")
        return "\n".join(lines)

    @console_command("reload", help="重载插件", usage="reload <name>|all")
    async def _cmd_reload(self, args: list[str]) -> str:
        if not args:
            return "[admin] 用法: reload <name>|all"
        targets = (
            [p.name for p in self._app._pm.get_active_plugins()]
            if args[0] == "all"
            else [args[0]]
        )
        if not targets:
            return "[admin] 无可重载插件"
        results = [await self._reload_one(n) for n in targets]
        return results[0] if len(targets) == 1 else "[admin] reload all:\n" + "\n".join(results)

    @console_command("services", help="列出已注册服务")
    def _cmd_services(self, args: list[str]) -> str:
        services = self._app._services.list_services()
        if not services:
            return "[admin] 无已注册服务"
        lines = [f"[admin] 服务 ({len(services)}):"]
        for s in services:
            lines.append(f"  {s.name}@{s.version} (by {s.provider})")
        return "\n".join(lines)

    @console_command("config", help="配置管理", usage="config reload")
    def _cmd_config(self, args: list[str]) -> str:
        if not args or args[0] != "reload":
            return "[admin] 用法: config reload"
        refresh = getattr(self._app._pm, "refresh_config", None)
        if refresh is None:
            return "[admin] PluginForge 不支持 refresh_config"
        try:
            refresh()
            return "[admin] 配置已刷新"
        except Exception as exc:
            log.exception("refresh_config failed")
            return f"[admin] 配置刷新失败: {exc}"

    @console_command("health", help="查看插件健康状态")
    def _cmd_health(self, args: list[str]) -> str:
        plugins = list(self._app._pm.get_active_plugins())
        if not plugins:
            return "[admin] 无活跃插件"
        lines = ["[admin] 插件健康:"]
        for p in plugins:
            try:
                h = p.health()
                if isinstance(h, dict):
                    status = h.get("status", "unknown")
                    others = {k: v for k, v in h.items() if k != "status"}
                    extra = f" {others}" if others else ""
                else:
                    status, extra = "unknown", ""
                lines.append(f"  {p.name}: {status}{extra}")
            except Exception as exc:
                lines.append(f"  {p.name}: error - {exc}")
        return "\n".join(lines)

    # ==================== 内部 ====================

    async def _reload_one(self, name: str) -> str:
        ok, msg = await self._app.reload_plugin(name)
        return f"  {name}: {'ok' if ok else msg}"


# ==================== 渲染辅助函数 ====================

def _render_item(item: dict, cmd_col: int, columns: int) -> str:
    """渲染单条命令行。权限标签右对齐到行尾。"""
    indent = "  " * (item["depth"] + 1)  # 子命令额外缩进

    # 命令列
    usage = truncate(item["usage"], cmd_col)
    cmd_part = Theme.cmd(usage) + " " * max(0, cmd_col - term_width(usage))

    # 权限标签
    perm = item["permission"]
    tag = ""
    if perm and not perm.endswith(f":command.{item['spec'].name}"):
        tag = f"[{perm}]"
    tag_part = Theme.warn(f"  {tag}") if tag else ""

    # 描述可用宽度
    used = len(indent) + cmd_col + _GAP + term_width(tag_part)
    avail = max(8, columns - used - 2)
    desc = truncate(item["help"], avail)

    return f"{indent}{cmd_part}{' ' * _GAP}{desc}{tag_part}"


def _detail_row(label: str, value: str, label_w: int) -> str:
    return "  " + Theme.dim(pad_end(label, label_w)) + value


def _print(msg: str) -> None:
    from fcatbot.frontend.console import console_print
    console_print(msg)