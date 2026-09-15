"""框架级管理命令。

help 渲染特性:
- 扁平化展开: 子命令独立成行，不再显示 <subcommand> 占位符
- 分组渲染: 按插件分组，每组有标题和色条
- 宽度感知: CJK / Emoji 按 wcwidth 计宽，ANSI 码最后注入
- 动态对齐: 命令列宽全局统一，跨页不跳动
- 分页: 默认每页 16 行，可通过 -p N 翻页
- 权限标签右对齐到行尾

统一输出约定（所有非 help 命令走 Out 类）:
- 标签符号全部为 ASCII: [+][-][ ][!][?][i][>]，无立体感
- 颜色取自 Color 类，未启用时自动降级为空串
"""

from __future__ import annotations

import inspect
import logging

from fcatbot.frontend.term import pad_end, terminal_size, truncate
from fcatbot.frontend.term import width as term_width
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
from fcatbot.utils import Color

log = logging.getLogger("fcatbot.admin")

FRAMEWORK_PLUGIN = "Core"


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


# ==================== 统一输出格式 ====================


class Out:
    """所有命令的统一输出格式。

    符号约定（纯 ASCII，无立体感）::

        [+]  成功 / 启用 / 新增 / 活跃
        [-]  失败 / 禁用 / 移除 / 错误
        [ ]  中性 / 未激活 / 空闲
        [!]  警告
        [?]  未知
        [i]  信息
        [>]  提示 / 用法

    使用::

        Out.ok("插件已启用")               →  [+] 插件已启用（绿）
        Out.err("找不到插件")              →  [-] 找不到插件（红）
        Out.hint("用法: enable <name>")    →  [>] 用法: ...（青）
        Out.block("插件列表", "共 3 个")   →  标题块（上下分隔线）
    """

    # 标签符号
    OK = "[+]"
    OFF = "[-]"
    IDLE = "[ ]"
    WARN = "[!]"
    UNK = "[?]"
    INFO = "[i]"
    HINT = "[>]"

    # ---------- 状态行 ----------

    @classmethod
    def ok(cls, text: str) -> str:
        return f"{Color.Green}{cls.OK}{Color.Reset} {text}"

    @classmethod
    def err(cls, text: str) -> str:
        return f"{Color.Red}{cls.OFF}{Color.Reset} {text}"

    @classmethod
    def warn(cls, text: str) -> str:
        return f"{Color.Yellow}{cls.WARN}{Color.Reset} {text}"

    @classmethod
    def info(cls, text: str) -> str:
        return f"{Color.Cyan}{cls.INFO}{Color.Reset} {text}"

    @classmethod
    def idle(cls, text: str) -> str:
        return f"{Color.Gray}{cls.IDLE}{Color.Reset} {text}"

    @classmethod
    def unknown(cls, text: str) -> str:
        return f"{Color.Gray}{cls.UNK}{Color.Reset} {text}"

    @classmethod
    def hint(cls, text: str) -> str:
        return f"{Color.Cyan}{cls.HINT}{Color.Reset} {text}"

    # ---------- 结构元素 ----------

    @classmethod
    def title(cls, text: str) -> str:
        return f"{Color.Bold}{Color.Cyan}{text}{Color.Reset}"

    @classmethod
    def name(cls, text: str) -> str:
        return f"{Color.Bold}{text}{Color.Reset}"

    @classmethod
    def accent(cls, text: str) -> str:
        return f"{Color.Cyan}{text}{Color.Reset}"

    @classmethod
    def dim(cls, text: str) -> str:
        return f"{Color.Gray}{text}{Color.Reset}"

    @classmethod
    def rule(cls, width: int = 44, char: str = "-") -> str:
        return f"{Color.Gray}{char * width}{Color.Reset}"

    @classmethod
    def block(
        cls, title: str, subtitle: str = "", width: int | None = None
    ) -> list[str]:
        """统一标题块: 上下分隔线夹一行标题。"""
        if width is None:
            try:
                columns, _ = terminal_size()
                width = max(30, min(columns - 4, 60))
            except Exception:
                width = 44
        head = f"  {cls.title(title)}"
        if subtitle:
            head += f"  {cls.dim(subtitle)}"
        return [cls.rule(width, "="), head, cls.rule(width, "=")]

    @classmethod
    def kv(cls, key: str, value: str, key_w: int = 10) -> str:
        """统一键值行: 两空格缩进 + 键 + 值。"""
        return f"  {cls.dim(pad_end(key + ':', key_w))} {value}"


# ==================== 模块级渲染辅助 ====================


def _render_plugin_row(
    name: str,
    active: dict,
    discovered: dict,
    errors: dict,
) -> str:
    """渲染单个插件行，[+] / [ ] / [!] / [?] 四态统一。"""
    if name in active:
        p = active[name]
        ver = getattr(p, "version", "-")
        head = f"{Out.name(name)} {Out.dim('@' + str(ver))}"
        line = f"  {Color.Green}{Out.OK}{Color.Reset} {head}"
        deps = getattr(p, "depends_on", []) or []
        if deps:
            line += Out.dim(f"   deps={', '.join(str(d) for d in deps)}")
        return line

    if name in errors:
        body = f"{Out.name(name)}  {errors[name]}"
        return f"  {Color.Red}{Out.OFF}{Color.Reset} {body}"

    cls = discovered.get(name)
    if cls is not None:
        ver = getattr(cls, "version", "-")
        head = f"{Out.name(name)} {Out.dim('@' + str(ver))}"
        return f"  {Color.Gray}{Out.IDLE}{Color.Reset} {head}  {Out.dim('未激活')}"

    return f"  {Color.Gray}{Out.UNK}{Color.Reset} {name}"


def _health_marker(status: str) -> str:
    """健康状态 → 标签符号。"""
    s = str(status).lower()
    if s in ("ok", "healthy", "up", "good", "ready"):
        return f"{Color.Green}{Out.OK}{Color.Reset}"
    if s in ("error", "failed", "down", "bad", "dead"):
        return f"{Color.Red}{Out.OFF}{Color.Reset}"
    return f"{Color.Yellow}{Out.WARN}{Color.Reset}"


# ==================== 主类 ====================


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
            _print(Out.err(f"权限不足: {spec.resolved_permission()}"))
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
            _print(Out.err(str(exc)))

    async def _check_permission(self, spec: CommandSpec, event: Event) -> bool:
        if event.source == "console":
            return True
        user_id = event.metadata.get("user_id")
        if not user_id:
            return False
        return await self._app._permissions.has_permission(
            str(user_id), spec.resolved_permission()
        )

    # ==================== help ====================

    @console_command(
        "help",
        help="显示所有命令或命令详情",
        usage="help [命令|插件] [-p N]",
        aliases=["?"],
    )
    def _cmd_help(self, args: list[str]) -> str:
        if args and args[0] == "-p":
            try:
                page = int(args[1]) if len(args) > 1 else 1
            except ValueError:
                page = 1
            return self._render_list(page=page)

        if args:
            spec, _ = self._registry.find(args)
            if spec is not None:
                return self._render_detail(spec)
            by_plugin = self._filter_by_plugin(args[0])
            if by_plugin:
                return self._render_list(filter_plugin=args[0])
            return Out.err(f"未找到与 '{args[0]}' 相关的命令")

        return self._render_list()

    # ---------- 列表渲染 ----------

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
            return Out.info("无可用命令")

        rows = self._flatten(roots)
        cmd_col = self._compute_cmd_col(rows)

        groups: dict[str, list[dict]] = {}
        for row in rows:
            groups.setdefault(row["plugin"], []).append(row)

        columns, lines = terminal_size()
        ps = page_size if page_size is not None else max(6, min(lines - 8, 40))

        pages = self._paginate(groups, cmd_col, columns, ps)
        total_pages = len(pages)
        p = max(1, min(page, total_pages))

        rule = Theme.dim("-" * columns)
        lines_out: list[str] = [
            rule,
            " "
            + Theme.title("帮助")
            + Theme.dim(f" · 共 {len(rows)} 条 · {p}/{total_pages} 页"),
            rule,
            "",
        ]
        lines_out.extend(pages[p - 1])
        lines_out.extend(
            [
                "",
                rule,
                Theme.dim(" help <命令> 查看详情 · help <插件> 筛选 · help -p N 翻页"),
                rule,
            ]
        )
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
            rows.append(
                {
                    "spec": spec,
                    "plugin": spec.plugin or "内置",
                    "depth": depth,
                    "usage": spec.usage_text(),
                    "help": spec.help or "",
                    "permission": spec.resolved_permission(),
                    "is_root": depth == 0,
                    "has_subs": bool(spec.subcommands),
                }
            )
            for sub in spec.subcommands.values():
                walk(sub, depth + 1)

        for root in roots:
            walk(root, 0)
        return rows

    # ---------- 命令列宽 ----------

    @staticmethod
    def _compute_cmd_col(rows: list[dict]) -> int:
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
                "  "
                + Theme.plugin(f"{plugin_name}")
                + Theme.dim(f"  {len(items)} 条命令"),
            ]
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
            "  "
            + Theme.plugin(f"{spec.plugin or '内置'}")
            + Theme.dim(" / ")
            + Theme.title(spec.name)
        )
        lines.append("  " + Theme.dim("-" * max(8, columns - 4)))
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
                    "  "
                    + " " * label_w
                    + Theme.cmd(sub_usage)
                    + "  "
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
            r for r in self._registry.all_roots() if name.lower() in r.plugin.lower()
        ]

    # ==================== 插件扫描 ====================

    def _resolve_rescan(self):
        """查找宿主可用的「只重扫描、不激活」接口。

        与 WebUI 后端保持一致: 只认 FcatbotApp 上的专用方法，
        刻意不 fallback 到 PluginManager.discover_plugins / rediscover
        （那两个会连带激活插件，不符合「先发现、用户再决定」的语义）。
        """
        for attr in ("rescan_plugins", "scan_plugins"):
            fn = getattr(self._app, attr, None)
            if callable(fn):
                return fn
        return None

    @console_command(
        "scan",
        help="重新扫描 entry points，发现新安装的插件（不激活）",
        usage="scan",
        aliases=["rescan", "discover"],
    )
    async def _cmd_scan(self, args: list[str]) -> str:
        rescan = self._resolve_rescan()
        if rescan is None:
            return Out.err(
                "宿主未提供重扫描接口。请在 FcatbotApp 上实现 rescan_plugins()。"
            )
        try:
            result = rescan()
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            log.exception("scan failed")
            return Out.err(f"重扫描失败: {exc}")

        if isinstance(result, dict):
            added = list(result.get("added", []))
            removed = list(result.get("removed", []))
        elif isinstance(result, (list, tuple, set)):
            added, removed = list(result), []
        else:
            added, removed = [], []

        total = len(self._app.discovered_plugins)
        lines = Out.block("重扫描", f"共 {total} 个")
        if added:
            lines.append(f"  {Out.ok(f'新增 {len(added)} 个')}")
            for n in added:
                lines.append(f"      {Out.name(n)}")
        if removed:
            lines.append(f"  {Out.warn(f'移除 {len(removed)} 个')}")
            for n in removed:
                lines.append(f"      {Out.dim(n)}")
        if not added and not removed:
            lines.append(f"  {Out.info('未发现变化')}")
        lines.append("")
        lines.append(Out.dim("  提示: plugins -a 查看全部 · enable <name> 启用"))
        return "\n".join(lines)

    # ==================== 启停 ====================

    @console_command("enable", help="启用插件", usage="enable <name>")
    async def _cmd_enable(self, args: list[str]) -> str:
        if not args:
            return Out.hint("用法: enable <name>")
        name = args[0]
        try:
            ok, msg = await self._app.enable_plugin(name)
        except Exception as exc:
            log.exception("enable_plugin failed: %s", name)
            return Out.err(f"启用失败: {exc}")
        return Out.ok(msg) if ok else Out.err(msg)

    @console_command("disable", help="禁用插件", usage="disable <name>")
    async def _cmd_disable(self, args: list[str]) -> str:
        if not args:
            return Out.hint("用法: disable <name>")
        name = args[0]
        try:
            ok, msg = await self._app.disable_plugin(name)
        except Exception as exc:
            log.exception("disable_plugin failed: %s", name)
            return Out.err(f"禁用失败: {exc}")
        return Out.ok(msg) if ok else Out.err(msg)

    # ==================== 插件列表 ====================

    @console_command(
        "plugins",
        help="列出插件（默认仅活跃；-a 含全部）",
        usage="plugins [-a|--all]",
    )
    def _cmd_plugins(self, args: list[str]) -> str:
        show_all = any(a in ("-a", "--all") for a in args)
        active = {p.name: p for p in self._app._pm.get_active_plugins()}
        discovered = self._app.discovered_plugins
        errors = self._app._pm.get_load_errors()

        if show_all:
            names = sorted(set(active) | set(discovered) | set(errors))
            if not names:
                return Out.info("未发现任何插件（可执行 scan 重新扫描）")
            lines = Out.block("全部插件", f"共 {len(names)} 个")
            for name in names:
                lines.append(_render_plugin_row(name, active, discovered, errors))
            lines.append("")
            lines.append(
                Out.dim("  图例: ")
                + Out.ok("活跃")
                + Out.dim(" · ")
                + Out.idle("已发现")
                + Out.dim(" · ")
                + Out.err("加载失败")
            )
            return "\n".join(lines)

        if not active:
            return Out.info("无活跃插件（plugins -a 查看全部，或 scan 重新扫描）")
        lines = Out.block("活跃插件", f"共 {len(active)} 个")
        for name in sorted(active):
            lines.append(_render_plugin_row(name, active, discovered, errors))
        return "\n".join(lines)

    # ==================== 插件详情 ====================

    @console_command("info", help="查看插件详情", usage="info <name>")
    def _cmd_info(self, args: list[str]) -> str:
        if not args:
            return Out.hint("用法: info <name>")
        name = args[0]
        inspect_fn = getattr(self._app._pm, "inspect_plugin", None)
        if not callable(inspect_fn):
            return Out.err("PluginForge 不支持 inspect_plugin")
        try:
            info = inspect_fn(name)
        except Exception as exc:
            log.exception("inspect_plugin failed: %s", name)
            return Out.err(f"查询失败: {exc}")
        if info is None:
            return Out.err(f"未知插件: {name}")

        lines = [f"  {Out.title(info.name)}"]
        lines.append(Out.kv("版本", str(info.version or "-")))
        if getattr(info, "target_application", None):
            lines.append(Out.kv("目标应用", str(info.target_application)))
        if getattr(info, "min_app_version", None):
            lines.append(Out.kv("最低宿主", str(info.min_app_version)))

        state = getattr(info, "state", None)
        if state is not None:
            marks = []
            if getattr(state, "activated", False):
                marks.append(Out.ok("活跃"))
            if getattr(state, "discovered", False):
                marks.append(Out.idle("已发现"))
            reason = getattr(state, "filter_reason", None)
            if reason:
                marks.append(Out.warn(f"过滤={reason}"))
            lines.append(Out.kv("状态", " · ".join(marks) or "-"))
            activated_at = getattr(state, "activated_at", None)
            if activated_at:
                lines.append(Out.kv("激活于", str(activated_at)))
            load_error = getattr(state, "load_error", None)
            if load_error is not None:
                msg = getattr(load_error, "user_facing_message", str(load_error))
                lines.append(Out.kv("错误", msg))

        if getattr(info, "dependencies", None):
            lines.append(Out.kv("依赖", ", ".join(info.dependencies)))
        if getattr(info, "hooks", None):
            lines.append(Out.kv("钩子", ", ".join(info.hooks)))
        if getattr(info, "routes", None):
            lines.append(Out.kv("路由", ", ".join(info.routes)))
        if getattr(info, "health", None):
            h = info.health
            if isinstance(h, dict):
                status = h.get("status", "unknown")
                extra = {k: v for k, v in h.items() if k != "status"}
                tail = f"  {Out.dim(str(extra))}" if extra else ""
                lines.append(Out.kv("健康", f"{status}{tail}"))
            else:
                lines.append(Out.kv("健康", str(h)))
        return "\n".join(lines)

    # ==================== 加载错误 ====================

    @console_command("errors", help="列出插件加载/激活错误")
    def _cmd_errors(self, args: list[str]) -> str:
        errors = self._app._pm.get_load_errors()
        if not errors:
            return Out.ok("无加载错误")
        lines = Out.block("加载错误", f"共 {len(errors)} 个")
        for name, msg in errors.items():
            lines.append(f"  {Color.Red}{Out.OFF}{Color.Reset} {Out.name(name)}  {msg}")
        return "\n".join(lines)

    # ==================== 总体状态 ====================

    @console_command("status", help="框架总体状态")
    def _cmd_status(self, args: list[str]) -> str:
        active = self._app._pm.get_active_plugins()
        discovered = self._app.discovered_plugins
        try:
            services = self._app._services.list_services()
        except Exception:
            services = []
        errors = self._app._pm.get_load_errors()
        commands = self._app._commands.all_roots()

        lines = Out.block("框架状态")
        lines.append(Out.kv("活跃插件", str(len(active))))
        lines.append(Out.kv("已发现", str(len(discovered))))
        lines.append(Out.kv("注册服务", str(len(services))))
        lines.append(Out.kv("顶层命令", str(len(commands))))
        lines.append(
            Out.kv(
                "加载错误",
                (
                    f"{len(errors)}"
                    if not errors
                    else f"{Color.Red}{len(errors)}{Color.Reset}"
                ),
            )
        )
        return "\n".join(lines)

    # ==================== 框架命令 ====================

    @console_command("reload", help="热重载运行中的插件", usage="reload <name>|all")
    async def _cmd_reload(self, args: list[str]) -> str:
        if not args:
            return Out.hint("用法: reload <name>|all")
        targets = (
            [p.name for p in self._app._pm.get_active_plugins()]
            if args[0] == "all"
            else [args[0]]
        )
        if not targets:
            return Out.info("无可重载插件")
        if len(targets) == 1:
            return await self._reload_one(targets[0])
        lines = Out.block("批量重载", f"共 {len(targets)} 个")
        for n in targets:
            lines.append("  " + await self._reload_one(n))
        return "\n".join(lines)

    @console_command("services", help="列出已注册服务")
    def _cmd_services(self, args: list[str]) -> str:
        services = self._app._services.list_services()
        if not services:
            return Out.info("无已注册服务")
        lines = Out.block("服务", f"共 {len(services)} 个")
        for s in services:
            ver = Out.dim("@" + str(getattr(s, "version", "-")))
            provider = Out.dim(f"(by {getattr(s, 'provider', '?')})")
            lines.append(f"  {Out.accent(s.name)} {ver} {provider}")
        return "\n".join(lines)

    @console_command("config", help="配置管理", usage="config reload")
    def _cmd_config(self, args: list[str]) -> str:
        if not args or args[0] != "reload":
            return Out.hint("用法: config reload")
        refresh = getattr(self._app._pm, "refresh_config", None)
        if refresh is None:
            return Out.err("PluginForge 不支持 refresh_config")
        try:
            refresh()
            return Out.ok("配置已刷新")
        except Exception as exc:
            log.exception("refresh_config failed")
            return Out.err(f"配置刷新失败: {exc}")

    @console_command("health", help="查看插件健康状态")
    def _cmd_health(self, args: list[str]) -> str:
        plugins = list(self._app._pm.get_active_plugins())
        if not plugins:
            return Out.info("无活跃插件")
        lines = Out.block("插件健康", f"共 {len(plugins)} 个")
        for p in plugins:
            try:
                h = p.health()
                if isinstance(h, dict):
                    status = h.get("status", "unknown")
                    others = {k: v for k, v in h.items() if k != "status"}
                    extra = f"  {Out.dim(str(others))}" if others else ""
                else:
                    status, extra = "unknown", ""
                marker = _health_marker(status)
                lines.append(f"  {marker} {Out.name(p.name)}  {status}{extra}")
            except Exception as exc:
                lines.append(
                    f"  {Color.Red}{Out.OFF}{Color.Reset} {Out.name(p.name)}  {exc}"
                )
        return "\n".join(lines)

    # ==================== 内部 ====================

    async def _reload_one(self, name: str) -> str:
        ok, msg = await self._app.reload_plugin(name)
        if ok:
            return Out.ok(f"{Out.name(name)}  {msg}")
        return Out.err(f"{Out.name(name)}  {msg}")


# ==================== 渲染辅助函数 ====================


def _render_item(item: dict, cmd_col: int, columns: int) -> str:
    """渲染单条命令行。权限标签右对齐到行尾。"""
    indent = "  " * (item["depth"] + 1)

    usage = truncate(item["usage"], cmd_col)
    cmd_part = Theme.cmd(usage) + " " * max(0, cmd_col - term_width(usage))

    perm = item["permission"]
    tag = ""
    if perm and not perm.endswith(f":command.{item['spec'].name}"):
        tag = f"[{perm}]"
    tag_part = Theme.warn(f"  {tag}") if tag else ""

    used = len(indent) + cmd_col + _GAP + term_width(tag_part)
    avail = max(8, columns - used - 2)
    desc = truncate(item["help"], avail)

    return f"{indent}{cmd_part}{' ' * _GAP}{desc}{tag_part}"


def _detail_row(label: str, value: str, label_w: int) -> str:
    return "  " + Theme.dim(pad_end(label, label_w)) + value


def _print(msg: str) -> None:
    from fcatbot.frontend.console import console_print

    console_print(msg)
