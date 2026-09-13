"""LuckPerms 命令集（``lp``）——对齐官方命令结构，含参考实现扩展。

命令面与官方 `Command Usage <https://luckperms.net/wiki/Command-Usage>`_ 对齐，
同时保留旧版插件参考实现中的增强项（``lp check`` / ``lp root`` / ``me`` / 继承树 / Web Editor）。

官方结构: :

    lp [help] / info / sync
    lp editor [type] [filter] / applyedits <code>
    lp verbose <on|record|off|upload> [filter]
    lp tree
    lp creategroup <name> [weight] [displayname] / deletegroup / listgroups
    lp createtrack <name> [groups...] / deletetrack / listtracks
    lp user <user|me> info
    lp user <user|me> permission info|set|unset|settemp|unsettemp|check|clear <node> ...
    lp user <user|me> parent info|set|add|remove|clear <group>
    lp user <user|me> meta info|setprefix|setsuffix [priority] <value>
    lp user <user|me> promote / demote <track> / showtracks
    lp group <group> info
    lp group <group> permission info|set|unset|settemp|unsettemp|check|clear <node> ...
    lp group <group> parent info|set|add|remove|clear <parent>
    lp group <group> meta info|setprefix|setsuffix [priority] <value>
    lp group <group> setweight <n> / setdisplayname <name> / showtracks / create ...
    lp track <track> info|append|insert|remove|clear|create ...

参考实现扩展: 

- ``lp check <用户|me> <节点> [key=value ...]``: 快速权限检查（官方经由 ``user/group permission check``）；
- ``lp root <用户ID>``: **控制台专用**根管理员引导（授予 ``*``；聊天来源禁止分发 ``*``）；
- ``lp verbose`` 支持 ``me``（只记录执行者）、过滤器与本地 ``upload`` 摘要；
- ``lp tree <用户|组> [depth]``: 继承树视图（官方 tree 为权限注册表视图，此处以数据面继承树替代）；
- ``me`` / ``self``: 聊天来源解析为执行者；控制台解析为 ``console`` 身份——引导时自动创建并
  保留 ``*``（即拥有全部权限，与 ``permissions.console_user`` 配置对应）；
- ``lp editor`` / ``lp applyedits``: LuckPerms Web Editor（打开会话 → 手动应用 edit 码）；
  网络操作转入**后台任务**，命令立即返回（避免阻塞事件总线单 worker，ADR-0004）。

权限节点（官方风格 ``luckperms.*``）: 

- 命令入口 ``core:command.lp``（框架约定，决定 ``help`` 可见性）；
- 单一命令使用官方叶子节点（``luckperms.info`` / ``luckperms.creategroup`` / ``luckperms.editor`` …）；
- ``user`` / ``group`` / ``track`` 为聚合命令（动作位于参数中），规范节点为段节点
  （``luckperms.user`` / ``luckperms.group`` / ``luckperms.track``）；**聊天来源**的动作级门禁
  在处理器内部按官方叶子节点校验（如 ``luckperms.user.permission.set``）；
- 控制台来源一律放行（本地操作员语义）；``*`` 仅允许在控制台授予。

参数约定（与官方一致）: 

- 上下文 ``key=value``（可多个，空格分隔），省略即为全局上下文；
- 时长 ``30s`` / ``10m`` / ``2h`` / ``7d`` / ``1w``（纯数字视为秒，支持组合 ``1d2h30m``）；
- ``true|false`` 省略时默认 ``true``；``settemp`` 需要时长；
- 暂不支持引号转义空格（参数按空白切分）。

库能力边界（luckperms-python v1.0.6）: 

- 组临时权限（``group permission settemp``）由 ``Node(expiry=...)`` 直写实现（库无 duration 参数）；
- 任意键 ``meta set/unset`` 未实现（库仅识别 prefix/suffix/displayname/weight 元数据）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fcatbot.kernel.commands import CommandContext, console_command
from fcatbot.kernel.permissions import LuckPermsAdapter

log = logging.getLogger("fcatbot.lp")

# ---------------------------------------------------------------------------
# 权限节点（官方风格，https://luckperms.net/wiki/Permissions）
# ---------------------------------------------------------------------------

LP_ENTRY = "core:command.lp"          # 命令入口（框架约定）
LP_INFO = "luckperms.info"
LP_SYNC = "luckperms.sync"
LP_VERBOSE = "luckperms.verbose"
LP_TREE = "luckperms.tree"
LP_EDITOR = "luckperms.editor"
LP_APPLYEDITS = "luckperms.applyedits"
LP_CHECK = "luckperms.user.permission.check"
LP_CREATEGROUP = "luckperms.creategroup"
LP_DELETEGROUP = "luckperms.deletegroup"
LP_LISTGROUPS = "luckperms.listgroups"
LP_CREATETRACK = "luckperms.createtrack"
LP_DELETETRACK = "luckperms.deletetrack"
LP_LISTTRACKS = "luckperms.listtracks"

# 聚合命令段节点（动作级校验在处理器内部细化，见 _authorize）
LP_USER = "luckperms.user"
LP_GROUP = "luckperms.group"
LP_TRACK = "luckperms.track"

_NO_IDENTITY = (
    "[lp] 无法解析 'me': 聊天来源缺少 user_id"
    "（适配器需在命令事件的 metadata 中提供 user_id）"
)

_USER_USAGE = (
    "[lp] 用法: lp user <用户|me> "
    "<info | permission <info|set|unset|settemp|unsettemp|check|clear> <节点> [true|false] [时长] [key=value ...] "
    "| parent <info|set|add|remove|clear> <组> "
    "| meta <info|setprefix|setsuffix> [priority] <值> "
    "| promote|demote <轨道> | showtracks>"
)

_GROUP_USAGE = (
    "[lp] 用法: lp group <组> "
    "<info | permission <info|set|unset|settemp|unsettemp|check|clear> <节点> [true|false] [时长] [key=value ...] "
    "| parent <info|set|add|remove|clear> <组> "
    "| meta <info|setprefix|setsuffix> [priority] <值> "
    "| setweight <权重> | setdisplayname <显示名> | showtracks | create [权重] [显示名]>"
)

_TRACK_USAGE = (
    "[lp] 用法: lp track <轨道> "
    "<info | append <组> | insert <组> [position] | remove <组> | clear | create [组...]>"
)


# ---------------------------------------------------------------------------
# 参数解析辅助
# ---------------------------------------------------------------------------


def _parse_context(tokens: List[str]) -> tuple[Dict[str, str], List[str]]:
    """从 tokens 中分离 ``key=value`` 上下文与未识别参数。"""
    context: Dict[str, str] = {}
    rest: List[str] = []
    for token in tokens:
        if "=" in token and not token.startswith("="):
            key, _, value = token.partition("=")
            if key:
                context[key] = value
                continue
        rest.append(token)
    return context, rest


def _parse_bool(token: str) -> Optional[bool]:
    """``true/t/yes/1`` → True；``false/f/no/0`` → False；其他返回 None。"""
    lowered = token.strip().lower()
    if lowered in ("true", "t", "yes", "y", "1", "allow"):
        return True
    if lowered in ("false", "f", "no", "n", "0", "deny"):
        return False
    return None


def _parse_duration(text: str) -> Optional[int]:
    """``1d2h30m`` → 秒数；支持 s/m/h/d/w；纯数字视为秒。"""
    text = text.strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total = 0
    number = ""
    for ch in text:
        if ch.isdigit():
            number += ch
            continue
        unit = units.get(ch)
        if unit is None or not number:
            return None
        total += int(number) * unit
        number = ""
    if number:  # 结尾裸数字: 视为秒
        total += int(number)
    return total or None


def _fmt_duration(seconds: int) -> str:
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds % size == 0:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def _fmt_remain(seconds: int) -> str:
    """剩余时长的近似展示（取最大可用单位）。"""
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"~{seconds // size}{unit}"
    return f"{seconds}s"


def _fmt_ctx(context: Dict[str, Any]) -> str:
    """节点上下文 → `` ctx={k=v, ...}``（空上下文返回空串）。"""
    if not context:
        return ""
    parts: List[str] = []
    for key, value in context.items():
        if isinstance(value, (list, tuple, set)):
            rendered = ",".join(str(item) for item in value)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return " ctx={" + ", ".join(parts) + "}"


def _normalize_ctx(context: Dict[str, str]) -> Dict[str, List[str]]:
    """与 ``Node.normalize_context`` 对齐的简化归一化（用于 clear 过滤）。"""
    normalized: Dict[str, List[str]] = {}
    for key, value in context.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        if rendered:
            normalized[key] = [rendered]
    return normalized


def _match_verbose_filter(expr: str, user_id: str, node: str) -> bool:
    """Verbose 过滤器子集: ``!term`` 取反；``|`` 分隔为“或”；term 按节点/用户前缀匹配。"""
    for term in expr.split("|"):
        term = term.strip()
        if not term:
            continue
        negate = term.startswith("!")
        if negate:
            term = term[1:].strip()
        hit = node.startswith(term) or user_id.startswith(term)
        if negate:
            hit = not hit
        if hit:
            return True
    return False


# ---------------------------------------------------------------------------
# Verbose 记录器
# ---------------------------------------------------------------------------


@dataclass
class _VerboseRecord:
    timestamp: float
    user_id: str
    node: str
    context: Dict[str, str]
    result: bool
    source: str


class _VerboseLog:
    """内存中的权限检查日志（滚动记录，支持过滤器与执行者过滤）。"""

    def __init__(self, max_size: int = 500) -> None:
        self._records: List[_VerboseRecord] = []
        self._max_size = max_size
        self._active = False
        self._filter = ""
        self._target_user: Optional[str] = None
        self.notify = False

    @property
    def active(self) -> bool:
        return self._active

    def start(
        self,
        filter: str = "",
        target_user: Optional[str] = None,
        *,
        notify: bool = True,
    ) -> None:
        self._active = True
        self._filter = filter.strip()
        self._target_user = target_user
        self.notify = notify
        self._records.clear()

    def stop(self) -> None:
        self._active = False
        self.notify = False

    def append(self, record: _VerboseRecord) -> None:
        if not self._active:
            return
        if self._target_user is not None and record.user_id != self._target_user:
            return
        if self._filter and not _match_verbose_filter(
            self._filter, record.user_id, record.node
        ):
            return
        self._records.append(record)
        if len(self._records) > self._max_size:
            del self._records[: len(self._records) - self._max_size]

    def dump(self, limit: int = 20) -> str:
        if not self._records:
            return "暂无权限检查记录"
        lines = ["最近权限检查记录:"]
        for record in self._records[-limit:]:
            ts = time.strftime("%H:%M:%S", time.localtime(record.timestamp))
            ctx = f" {record.context}" if record.context else ""
            emoji = "✓" if record.result else "✗"
            lines.append(f"  [{ts}] {emoji} {record.user_id} | {record.node}{ctx}")
        return "\n".join(lines)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "metadata": {
                "generated_at": int(time.time() * 1000),
                "count": len(self._records),
            },
            "records": [
                {
                    "time": int(record.timestamp * 1000),
                    "user": record.user_id,
                    "node": record.node,
                    "context": record.context,
                    "result": record.result,
                    "source": record.source,
                }
                for record in self._records
            ],
        }


# ---------------------------------------------------------------------------
# 文本格式化器
# ---------------------------------------------------------------------------


class _PlainFormatter:
    """纯文本格式化（控制台 / 聊天消息通用）。"""

    @staticmethod
    def info(manager: Any) -> str:
        data_dir = getattr(manager, "_data_dir", "?")
        return (
            f"[lp] 数据目录: {data_dir}\n"
            f"用户数: {len(manager.list_users())}\n"
            f"组数: {len(manager.list_groups())}\n"
            f"轨道数: {len(manager.list_tracks())}"
        )

    @staticmethod
    def user_info(user: Any) -> str:
        lines = [f"[lp] 用户 {user.unique_id} ({user.display_name})"]
        lines.append(f"  groups: {', '.join(user.parents) or '(none)'}")
        if user.nodes:
            lines.append("  直接权限:")
            for node in user.nodes[:30]:
                value = "T" if node.value else "F"
                lines.append(f"    {node.key} = {value}{_fmt_ctx(node.context)}")
            if len(user.nodes) > 30:
                lines.append(f"    ... 共 {len(user.nodes)} 个节点")
        else:
            lines.append("  直接权限: (无)")
        prefix = user.get_meta("prefix")
        if prefix:
            lines.append(f"  prefix: {prefix}")
        suffix = user.get_meta("suffix")
        if suffix:
            lines.append(f"  suffix: {suffix}")
        return "\n".join(lines)

    @staticmethod
    def group_info(group: Any) -> str:
        lines = [f"[lp] 组 {group.name} (weight={group.weight})"]
        lines.append(f"  parents: {', '.join(group.parents) or '(none)'}")
        if group.nodes:
            lines.append("  直接权限:")
            for node in group.nodes[:30]:
                value = "T" if node.value else "F"
                lines.append(f"    {node.key} = {value}{_fmt_ctx(node.context)}")
            if len(group.nodes) > 30:
                lines.append(f"    ... 共 {len(group.nodes)} 个节点")
        else:
            lines.append("  直接权限: (无)")
        return "\n".join(lines)

    @staticmethod
    def track_info(track: Any) -> str:
        lines = [f"[lp] 轨道 {track.name}:"]
        for index, group_name in enumerate(track.groups):
            lines.append(f"  [{index + 1}] {group_name}")
        if not track.groups:
            lines.append("  (空)")
        return "\n".join(lines)

    @staticmethod
    def check(holder_id: str, node: str, context: Dict[str, str], result: bool) -> str:
        suffix = ""
        if context:
            suffix = " (" + ", ".join(f"{k}={v}" for k, v in context.items()) + ")"
        return f"[lp] {holder_id}: {node} → {'允许' if result else '拒绝'}{suffix}"

    @staticmethod
    def tree(holder_id: str, manager: Any, depth: int = 5) -> str:
        user = manager.get_user(holder_id)
        group = manager.get_group(holder_id)
        target = user or group
        if target is None:
            return f"[lp] 持有者 '{holder_id}' 不存在（用户或组）"

        try:
            depth = max(1, min(int(depth), 10))
        except (TypeError, ValueError):
            depth = 5

        lines = [f"[lp] {holder_id} ({'user' if user else 'group'}) 继承树:"]
        for node in target.nodes:
            value = "T" if node.value else "F"
            lines.append(f"  • {node.key} = {value}{_fmt_ctx(node.context)}")

        visited: set[str] = {holder_id}

        def walk(holder: Any, indent: int, level: int) -> None:
            if level <= 0:
                return
            for parent_name in holder.parents:
                prefix = "  " * indent
                if parent_name in visited:
                    lines.append(f"{prefix}└── {parent_name} [循环引用]")
                    continue
                visited.add(parent_name)
                parent_group = manager.get_group(parent_name)
                if parent_group is None:
                    lines.append(f"{prefix}└── {parent_name} [组不存在]")
                    continue
                lines.append(
                    f"{prefix}└── {parent_group.name} "
                    f"(weight={parent_group.weight}, nodes={len(parent_group.nodes)})"
                )
                for node in parent_group.nodes:
                    value = "T" if node.value else "F"
                    lines.append(
                        f"{prefix}    ├── {node.key} = {value}{_fmt_ctx(node.context)}"
                    )
                walk(parent_group, indent + 1, level - 1)

        walk(target, 0, depth)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 命令集
# ---------------------------------------------------------------------------


class LuckPermsCommands:
    """``lp`` 命令集。由 :class:`fcatbot.builtin.AdminCommands` 统一注册（core 命名空间）。

    处理器声明 ``context: CommandContext | None`` 形参以获得来源感知
    （``me`` 解析、``lp root`` 控制台限定、聊天来源动作级门禁）。
    """

    def __init__(self, app: Any) -> None:
        self._app = app
        self._verbose = _VerboseLog()
        self._webeditor_session: Any = None
        self._tasks: set[asyncio.Task] = set()

    # ==================== 顶层入口 ====================

    @console_command(
        "lp",
        aliases=["perm", "perms", "luckperms"],
        help="LuckPerms 权限管理（官方命令结构）",
        usage="lp <info|sync|check|verbose|tree|root|editor|applyedits|user|group|track|creategroup|deletegroup|listgroups|createtrack|deletetrack|listtracks> ...",
        permission=LP_ENTRY,
    )
    def cmd_lp(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        return self._lp_help()

    # ==================== 通用命令 ====================

    @console_command(
        "info",
        parent="lp",
        help="显示统计信息",
        usage="lp info",
        permission=LP_INFO,
    )
    def cmd_info(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        return _PlainFormatter.info(manager)

    @console_command(
        "sync",
        parent="lp",
        help="保存数据到磁盘",
        usage="lp sync",
        permission=LP_SYNC,
    )
    def cmd_sync(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        manager.save_all()
        return "[lp] 数据已同步到磁盘"

    @console_command(
        "check",
        parent="lp",
        help="检查用户权限",
        usage="lp check <用户|me> <节点> [key=value ...]",
        permission=LP_CHECK,
    )
    def cmd_check(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if len(args) < 2:
            return "[lp] 用法: lp check <用户|me> <节点> [key=value ...]"
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        uid = self._resolve_user(args[0], context)
        if uid is None:
            return _NO_IDENTITY
        ctx, extra = _parse_context(args[2:])
        if extra:
            return f"[lp] 无法识别的参数: {' '.join(extra)}（上下文格式: key=value）"
        result = self._check_with_verbose(manager, uid, args[1], ctx)
        return _PlainFormatter.check(uid, args[1], ctx, result)

    @console_command(
        "verbose",
        parent="lp",
        help="Verbose 调试记录",
        usage="lp verbose [on|record|off|upload] [filter|me]",
        permission=LP_VERBOSE,
    )
    def cmd_verbose(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if not args:
            if self._verbose.active:
                return self._verbose.dump(20)
            return "[lp] Verbose 未开启"

        action = args[0].lower()
        rest = args[1:]

        if action in ("on", "record"):
            scope = " ".join(rest).strip()
            target: Optional[str] = None
            if scope.lower() == "me":
                target = self._resolve_user("me", context)
                if target is None:
                    return _NO_IDENTITY
                scope = ""
            self._verbose.start(scope, target_user=target, notify=(action == "on"))
            mode = "告警模式" if action == "on" else "记录模式"
            if target is not None:
                return f"[lp] Verbose 已开启（{mode}，仅记录 {target}）"
            extra = f"，过滤器: {scope}" if scope else ""
            return f"[lp] Verbose 已开启（{mode}{extra}）"

        if action == "off":
            self._verbose.stop()
            return "[lp] Verbose 已关闭"

        if action in ("upload", "paste"):
            payload = self._verbose.to_payload()
            count = payload["metadata"]["count"]
            return (
                f"[lp] Verbose 记录: {count} 条（本地摘要，未上传网页查看器）\n"
                f"{self._verbose.dump(15)}"
            )

        return "[lp] 用法: lp verbose [on|record|off|upload] [filter|me]"

    @console_command(
        "tree",
        parent="lp",
        help="查看继承树",
        usage="lp tree <用户|组> [depth]",
        permission=LP_TREE,
    )
    def cmd_tree(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if not args:
            return "[lp] 用法: lp tree <用户|组> [depth]"
        depth = 5
        if len(args) > 1:
            if not args[1].lstrip("-").isdigit():
                return f"[lp] depth 必须是整数: {args[1]}"
            depth = int(args[1])
        holder = self._resolve_user(args[0], context)
        if holder is None:
            return _NO_IDENTITY
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        return _PlainFormatter.tree(holder, manager, depth)

    @console_command(
        "root",
        parent="lp",
        help="设置根管理员（仅控制台）",
        usage="lp root <用户ID>",
        permission=LP_ENTRY,
    )
    def cmd_root(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if context is not None and not context.is_console:
            return (
                "[lp] lp root 仅允许在控制台执行"
                "（聊天来源请通过 lp user ... permission set 分配权限，且禁止授予 *）"
            )
        if not args:
            return (
                "用法: lp root <用户ID>\n"
                "说明: 将指定用户设为根管理员并授予 * 全部权限\n"
                "注意: 仅控制台可用；根管理员无法通过聊天把 * 授予他人"
            )
        token = args[0].strip()
        uid = str(int(token)) if token.isdigit() else token
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        if manager.get_user(uid) is None:
            manager.create_user(uid, f"Root-{uid}")
        manager.user_add_node(uid, "*", True, None)
        manager.save_all()
        return (
            f"[lp] 已将 {uid} 设为根管理员（已授予 * 全部权限）\n"
            "  提示: 该命令仅控制台可用；根管理员无法通过聊天把 * 授予他人"
        )

    @console_command(
        "editor",
        parent="lp",
        help="打开 Web Editor 会话（后台执行）",
        usage="lp editor [type] [filter]",
        permission=LP_EDITOR,
    )
    async def cmd_editor(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        self._spawn(self._open_webeditor(args))
        return "[lp] 正在打开 Web Editor 会话（网络操作已转后台，完成后输出 URL）"

    async def _open_webeditor(self, args: List[str]) -> None:
        """后台打开 Web Editor 会话（网络 I/O 不阻塞事件分发）。"""
        try:
            session = self._webeditor()
            url = await session.open()
            await session.close()
        except Exception as exc:
            log.exception("Web Editor 会话打开失败")
            log.warning("[lp] Web Editor 会话打开失败: %s（需要可访问 luckperms.net）", exc)
            return
        note = "（type/filter 参数当前忽略）" if args else ""
        log.info("[lp] Web Editor 会话已打开: %s %s", url, note)
        log.info("[lp] 在浏览器中编辑并 Save 后，在控制台执行 lp applyedits <code> 应用更改")

    @console_command(
        "applyedits",
        parent="lp",
        help="应用 Web Editor 更改（后台执行）",
        usage="lp applyedits <code>",
        permission=LP_APPLYEDITS,
    )
    async def cmd_applyedits(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if not args:
            return "[lp] 用法: lp applyedits <code>"
        code = args[0].strip()
        self._spawn(self._apply_edits(code))
        return f"[lp] 正在应用 edits: {code}（网络操作已转后台，完成后输出结果）"

    async def _apply_edits(self, code: str) -> None:
        """后台下载并应用 Web Editor 变更（网络 I/O 不阻塞事件分发）。"""
        try:
            session = self._webeditor()
            await session.apply_edits(code)
        except Exception as exc:
            log.exception("应用 edits 失败: code=%s", code)
            log.warning("[lp] 应用 edits 失败: %s", exc)
            return
        log.info("[lp] 已应用 edits: %s", code)

    # ==================== 组 / 轨道管理（顶层） ====================

    @console_command(
        "creategroup",
        parent="lp",
        help="创建组",
        usage="lp creategroup <名称> [权重] [显示名]",
        permission=LP_CREATEGROUP,
    )
    def cmd_creategroup(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if not args:
            return "[lp] 用法: lp creategroup <名称> [权重] [显示名]"
        return self._create_group(args[0], args[1:])

    @console_command(
        "deletegroup",
        parent="lp",
        help="删除组",
        usage="lp deletegroup <名称>",
        permission=LP_DELETEGROUP,
    )
    def cmd_deletegroup(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if not args:
            return "[lp] 用法: lp deletegroup <名称>"
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        name = args[0]
        if manager.get_group(name) is None:
            return f"[lp] 组 '{name}' 不存在"
        manager.delete_group(name)
        return f"[lp] 已删除组 {name}（引用已清理）"

    @console_command(
        "listgroups",
        parent="lp",
        help="列出全部组",
        usage="lp listgroups",
        permission=LP_LISTGROUPS,
    )
    def cmd_listgroups(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        groups = sorted(manager.list_groups(), key=lambda g: g.weight, reverse=True)
        if not groups:
            return "[lp] 无组"
        lines = [f"[lp] 组列表 ({len(groups)}):"]
        for group in groups:
            parents = f" → {', '.join(group.parents)}" if group.parents else ""
            lines.append(
                f"  {group.name} (weight={group.weight}, "
                f"nodes={len(group.nodes)}){parents}"
            )
        return "\n".join(lines)

    @console_command(
        "createtrack",
        parent="lp",
        help="创建晋升轨道",
        usage="lp createtrack <名称> [组...]",
        permission=LP_CREATETRACK,
    )
    def cmd_createtrack(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if not args:
            return "[lp] 用法: lp createtrack <名称> [组...]"
        return self._create_track(args[0], args[1:])

    @console_command(
        "deletetrack",
        parent="lp",
        help="删除轨道",
        usage="lp deletetrack <名称>",
        permission=LP_DELETETRACK,
    )
    def cmd_deletetrack(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if not args:
            return "[lp] 用法: lp deletetrack <名称>"
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        name = args[0]
        if manager.get_track(name) is None:
            return f"[lp] 轨道 '{name}' 不存在"
        manager.delete_track(name)
        return f"[lp] 已删除轨道 {name}"

    @console_command(
        "listtracks",
        parent="lp",
        help="列出全部轨道",
        usage="lp listtracks",
        permission=LP_LISTTRACKS,
    )
    def cmd_listtracks(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        tracks = manager.list_tracks()
        if not tracks:
            return "[lp] 无轨道"
        lines = [f"[lp] 轨道列表 ({len(tracks)}):"]
        for track in tracks:
            lines.append(f"  {track.name}: {' → '.join(track.groups) or '(空)'}")
        return "\n".join(lines)

    # ==================== 用户 ====================

    @console_command(
        "user",
        parent="lp",
        help="用户管理",
        usage="lp user <用户|me> <info|permission|parent|meta|promote|demote|showtracks> ...",
        permission=LP_USER,
    )
    def cmd_user(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if len(args) < 2:
            return _USER_USAGE
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        uid = self._resolve_user(args[0], context)
        if uid is None:
            return _NO_IDENTITY
        action = args[1].lower()
        params = args[2:]

        handlers = {
            "info": lambda: self._user_info(manager, uid),
            "permission": lambda: self._handle_permission(
                manager, uid, params, kind="user", context=context
            ),
            "parent": lambda: self._handle_parent(
                manager, uid, params, kind="user", context=context
            ),
            "meta": lambda: self._handle_meta(
                manager, uid, params, kind="user", context=context
            ),
            "promote": lambda: self._user_track(manager, uid, params, up=True),
            "demote": lambda: self._user_track(manager, uid, params, up=False),
            "showtracks": lambda: self._showtracks(manager, uid, kind="user"),
        }
        handler = handlers.get(action)
        if handler is None:
            return _USER_USAGE
        try:
            return handler()
        except Exception as exc:
            log.exception("lp user 执行失败: %s", " ".join(args))
            return f"[lp] 操作失败: {exc}"

    # ==================== 组 ====================

    @console_command(
        "group",
        parent="lp",
        help="组管理",
        usage="lp group <组> <info|permission|parent|meta|setweight|setdisplayname|showtracks|create> ...",
        permission=LP_GROUP,
    )
    def cmd_group(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if len(args) < 2:
            return _GROUP_USAGE
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        name = args[0]
        action = args[1].lower()
        params = args[2:]

        if action == "create":
            return self._create_group(name, params)

        if manager.get_group(name) is None:
            return f"[lp] 组 '{name}' 不存在"

        handlers = {
            "info": lambda: self._group_info(manager, name),
            "permission": lambda: self._handle_permission(
                manager, name, params, kind="group", context=context
            ),
            "parent": lambda: self._handle_parent(
                manager, name, params, kind="group", context=context
            ),
            "meta": lambda: self._handle_meta(
                manager, name, params, kind="group", context=context
            ),
            "setweight": lambda: self._group_setweight(manager, name, params),
            "setdisplayname": lambda: self._group_setdisplayname(manager, name, params),
            "showtracks": lambda: self._showtracks(manager, name, kind="group"),
        }
        handler = handlers.get(action)
        if handler is None:
            return _GROUP_USAGE
        try:
            return handler()
        except Exception as exc:
            log.exception("lp group 执行失败: %s", " ".join(args))
            return f"[lp] 操作失败: {exc}"

    # ==================== 轨道 ====================

    @console_command(
        "track",
        parent="lp",
        help="轨道管理",
        usage="lp track <轨道> <info|append|insert|remove|clear|create> ...",
        permission=LP_TRACK,
    )
    def cmd_track(self, args: List[str], context: Optional[CommandContext] = None) -> str:
        if len(args) < 2:
            return _TRACK_USAGE
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        name = args[0]
        action = args[1].lower()
        rest = args[2:]

        if action == "create":
            err = self._authorize(context, LP_CREATETRACK)
            if err:
                return err
            return self._create_track(name, rest)

        track = manager.get_track(name)
        if track is None:
            return f"[lp] 轨道 '{name}' 不存在"

        if action == "info":
            return _PlainFormatter.track_info(track)

        if action in ("append", "insert"):
            if not rest:
                return f"[lp] 用法: lp track {name} {action} <组> [position]"
            err = self._authorize(context, f"luckperms.track.{action}")
            if err:
                return err
            group_name = rest[0]
            if manager.get_group(group_name) is None:
                return f"[lp] 组 '{group_name}' 不存在"
            if action == "append":
                track.append_group(group_name)
                manager.save_all()
                return f"[lp] 轨道 {name}: 已追加组 {group_name}"
            index = len(track.groups)
            if len(rest) > 1:
                if not rest[1].lstrip("-").isdigit():
                    return f"[lp] position 必须是整数: {rest[1]}"
                index = int(rest[1]) - 1  # 与官方一致: 1-based 展示
            if not track.insert_group(index, group_name):
                return "[lp] 插入失败: position 超出范围"
            manager.save_all()
            return f"[lp] 轨道 {name}: 已插入组 {group_name} @ {index + 1}"

        if action == "remove":
            if not rest:
                return f"[lp] 用法: lp track {name} remove <组>"
            err = self._authorize(context, "luckperms.track.remove")
            if err:
                return err
            if not track.remove_group(rest[0]):
                return f"[lp] 轨道 {name} 中不存在组 {rest[0]}"
            manager.save_all()
            return f"[lp] 轨道 {name}: 已移除组 {rest[0]}"

        if action == "clear":
            err = self._authorize(context, "luckperms.track.clear")
            if err:
                return err
            track.set_groups([])
            manager.save_all()
            return f"[lp] 轨道 {name}: 已清空全部组"

        return _TRACK_USAGE

    # ==================== 用户/组信息 ====================

    def _user_info(self, manager: Any, user_id: str) -> str:
        user = manager.get_user(user_id)
        if user is None:
            has_default = manager.get_group("default") is not None
            inherits = "（自动继承 default 组）" if has_default else ""
            return f"[lp] 用户 {user_id}: 未持久化（游客）{inherits}"
        return _PlainFormatter.user_info(user)

    def _group_info(self, manager: Any, name: str) -> str:
        group = manager.get_group(name)
        if group is None:
            return f"[lp] 组 '{name}' 不存在"
        return _PlainFormatter.group_info(group)

    def _format_parent_info(self, manager: Any, holder_id: str, kind: str) -> str:
        """父组视图: 用户为直连列表；组为 BFS 继承链。"""
        if kind == "user":
            user = manager.get_user(holder_id)
            if user is None:
                has_default = manager.get_group("default") is not None
                note = "（自动继承 default）" if has_default else ""
                return f"[lp] 用户 {holder_id}: 未持久化（游客）{note}"
            lines = [f"[lp] 用户 {holder_id} 的组:"]
            for group_name in user.parents or ["(none)"]:
                group = manager.get_group(group_name)
                if group is not None:
                    lines.append(f"  {group_name} (weight={group.weight})")
                else:
                    lines.append(f"  {group_name} (缺失)")
            return "\n".join(lines)

        group = manager.get_group(holder_id)
        if group is None:
            return f"[lp] 组 '{holder_id}' 不存在"
        lines = [f"[lp] group {holder_id} 继承链:"]
        queue: List[tuple[str, int]] = [(parent, 1) for parent in group.parents]
        visited: set[str] = set()
        while queue:
            name, depth = queue.pop(0)
            if name in visited:
                lines.append(f"  {'  ' * depth}└── {name} (循环引用，已省略)")
                continue
            visited.add(name)
            parent_group = manager.get_group(name)
            if parent_group is None:
                lines.append(f"  {'  ' * depth}└── {name} (缺失)")
                continue
            lines.append(f"  {'  ' * depth}└── {name} (weight={parent_group.weight})")
            queue.extend((parent, depth + 1) for parent in parent_group.parents)
        return "\n".join(lines)

    def _format_meta_info(self, manager: Any, holder_id: str, kind: str) -> str:
        holder = manager.get_user(holder_id) if kind == "user" else manager.get_group(holder_id)
        if holder is None:
            noun = "用户" if kind == "user" else "组"
            return f"[lp] {noun} {holder_id}: 未持久化（无 meta）"
        lines = [f"[lp] {holder_id} meta:"]
        found = False
        for meta_type in ("prefix", "suffix", "displayname", "weight"):
            value = holder.get_meta(meta_type)
            if value is not None:
                lines.append(f"  {meta_type}: {value}")
                found = True
        if not found:
            lines.append("  (无)")
        return "\n".join(lines)

    def _format_permission_info(self, manager: Any, holder_id: str, kind: str) -> str:
        holder = manager.get_user(holder_id) if kind == "user" else manager.get_group(holder_id)
        if holder is None:
            noun = "用户" if kind == "user" else "组"
            return f"[lp] {noun} {holder_id}: 无权限节点"
        if not holder.nodes:
            return f"[lp] {holder_id}: 无直接权限节点"
        lines = [f"[lp] {holder_id} 的权限节点 ({len(holder.nodes)}):"]
        for node in holder.nodes[:30]:
            value = "T" if node.value else "F"
            expired = ""
            if node.expiry is not None:
                remain = int(node.expiry - time.time())
                expired = (
                    f"（临时，剩余 {_fmt_remain(max(0, remain))}）"
                    if remain > 0
                    else "（已过期）"
                )
            lines.append(f"  {node.key} = {value}{_fmt_ctx(node.context)}{expired}")
        if len(holder.nodes) > 30:
            lines.append(f"  ... 共 {len(holder.nodes)} 个节点")
        return "\n".join(lines)

    # ==================== 权限节点操作（用户/组共用） ====================

    def _handle_permission(
        self,
        manager: Any,
        holder_id: str,
        args: List[str],
        *,
        kind: str,
        context: Optional[CommandContext],
    ) -> str:
        noun = "用户" if kind == "user" else "组"
        label = holder_id if kind == "user" else f"group {holder_id}"
        base = f"luckperms.{kind}.permission"

        if not args or args[0].lower() == "info":
            return self._format_permission_info(manager, holder_id, kind)

        action = args[0].lower()
        rest = args[1:]

        if action in ("set", "settemp"):
            if not rest:
                return (
                    f"[lp] 用法: lp {kind} {holder_id} permission {action} "
                    "<节点> [true|false] [时长] [key=value ...]"
                )
            node = rest[0]
            index = 1
            value = True
            if index < len(rest):
                parsed = _parse_bool(rest[index])
                if parsed is not None:
                    value = parsed
                    index += 1
            duration: Optional[int] = None
            if action == "settemp":
                if index >= len(rest):
                    return "[lp] settemp 需要时长，如: 30m / 2h / 7d"
                duration = _parse_duration(rest[index])
                if duration is None:
                    return f"[lp] 无效时长: {rest[index]}（示例: 30s / 10m / 2h / 7d）"
                index += 1
            ctx, extra = _parse_context(rest[index:])
            if extra:
                return f"[lp] 无法识别的参数: {' '.join(extra)}（上下文格式: key=value）"
            err = self._authorize(context, f"{base}.{action}", crown=node)
            if err:
                return err
            if kind == "user":
                self._ensure_user(manager, holder_id)
            elif manager.get_group(holder_id) is None:
                return f"[lp] 组 '{holder_id}' 不存在"
            self._add_node(manager, kind, holder_id, node, value, ctx, duration)
            mark = "允许" if value else "拒绝"
            suffix = f"（临时 {_fmt_duration(duration)}）" if duration is not None else ""
            return f"[lp] {label}: {node} = {mark}{suffix}"

        if action in ("unset", "unsettemp"):
            if not rest:
                return (
                    f"[lp] 用法: lp {kind} {holder_id} permission {action} "
                    "<节点> [key=value ...]"
                )
            node = rest[0]
            ctx, extra = _parse_context(rest[1:])
            if extra:
                return f"[lp] 无法识别的参数: {' '.join(extra)}"
            err = self._authorize(context, f"{base}.{action}")
            if err:
                return err
            if kind == "user":
                if manager.get_user(holder_id) is None:
                    return f"[lp] 用户 {holder_id} 不存在（无节点可移除）"
                removed = manager.user_remove_node(holder_id, node, ctx or None)
            else:
                if manager.get_group(holder_id) is None:
                    return f"[lp] 组 '{holder_id}' 不存在"
                removed = manager.group_remove_node(holder_id, node, ctx or None)
            return f"[lp] {label}: {'已移除' if removed else '未找到节点'} {node}"

        if action == "check":
            if not rest:
                return (
                    f"[lp] 用法: lp {kind} {holder_id} permission check "
                    "<节点> [key=value ...]"
                )
            node = rest[0]
            ctx, extra = _parse_context(rest[1:])
            if extra:
                return f"[lp] 无法识别的参数: {' '.join(extra)}"
            if kind == "user":
                result = self._check_with_verbose(manager, holder_id, node, ctx)
            else:
                result = self._check_group_with_verbose(manager, holder_id, node, ctx)
            return _PlainFormatter.check(label, node, ctx, result)

        if action == "clear":
            ctx, extra = _parse_context(rest)
            if extra:
                return f"[lp] 无法识别的参数: {' '.join(extra)}"
            err = self._authorize(context, f"{base}.clear")
            if err:
                return err
            holder = (
                manager.get_user(holder_id) if kind == "user" else manager.get_group(holder_id)
            )
            if holder is None:
                return f"[lp] {noun} {holder_id} 不存在（无节点可清空）"
            normalized = _normalize_ctx(ctx)
            removed = 0
            for node in list(holder.nodes):
                if ctx and node.context != normalized:
                    continue
                if holder.remove_node(node.key, node.context):
                    removed += 1
            manager.save_all()
            if not removed:
                return f"[lp] {label}: 没有可清空的权限节点"
            return f"[lp] {label}: 已清空 {removed} 个权限节点"

        return _USER_USAGE if kind == "user" else _GROUP_USAGE

    def _add_node(
        self,
        manager: Any,
        kind: str,
        holder_id: str,
        node: str,
        value: bool,
        context: Dict[str, str],
        duration: Optional[int],
    ) -> None:
        """写入节点；组临时权限因库缺 duration 参数而使用 Node(expiry) 直写。"""
        if kind == "user":
            manager.user_add_node(holder_id, node, value, context or None, duration=duration)
            return
        if duration is None:
            manager.group_add_node(holder_id, node, value, context or None)
            return
        from luckperms.models import Node  # 软依赖: 仅组临时权限需要

        group = manager.get_group(holder_id)
        group.add_node(Node(node, value, context or {}, expiry=time.time() + duration))
        manager.save_all()

    # ==================== 父组操作（用户/组共用） ====================

    def _handle_parent(
        self,
        manager: Any,
        holder_id: str,
        args: List[str],
        *,
        kind: str,
        context: Optional[CommandContext],
    ) -> str:
        noun = "用户" if kind == "user" else "组"
        label = holder_id if kind == "user" else f"group {holder_id}"

        if not args or args[0].lower() == "info":
            return self._format_parent_info(manager, holder_id, kind)

        action = args[0].lower()
        rest = args[1:]
        if action not in ("add", "remove", "set", "clear"):
            return _USER_USAGE if kind == "user" else _GROUP_USAGE
        if action in ("add", "remove", "set") and not rest:
            return f"[lp] 用法: lp {kind} {holder_id} parent {action} <组>"
        target = rest[0] if rest else ""

        holder = (
            manager.get_user(holder_id) if kind == "user" else manager.get_group(holder_id)
        )

        if action == "add":
            if manager.get_group(target) is None:
                return f"[lp] 组 '{target}' 不存在（先执行 lp creategroup {target}）"
            err = self._authorize(context, f"luckperms.{kind}.parent.add")
            if err:
                return err
            if kind == "user":
                self._ensure_user(manager, holder_id)
                manager.user_add_group(holder_id, target)
                return f"[lp] {label}: 已加入组 {target}"
            try:
                manager.group_inherit(holder_id, target)
            except ValueError as exc:
                return f"[lp] 继承失败: {exc}"
            return f"[lp] {label}: 现在继承 {target}"

        if action == "remove":
            if holder is None:
                return f"[lp] {noun} {holder_id} 不存在"
            if target not in holder.parents:
                return f"[lp] {label}: 未继承 {target}"
            err = self._authorize(context, f"luckperms.{kind}.parent.remove")
            if err:
                return err
            if kind == "user":
                manager.user_remove_group(holder_id, target)
                return f"[lp] {label}: 已移出组 {target}"
            manager.group_remove_inherit(holder_id, target)
            return f"[lp] {label}: 已移除继承 {target}"

        if action == "set":
            if manager.get_group(target) is None:
                return f"[lp] 组 '{target}' 不存在（先执行 lp creategroup {target}）"
            err = self._authorize(context, f"luckperms.{kind}.parent.set")
            if err:
                return err
            if kind == "user":
                self._ensure_user(manager, holder_id)
                holder = manager.get_user(holder_id)
            for existing in list(holder.parents):
                if existing != target:
                    holder.remove_parent(existing)
            holder.add_parent(target)
            manager.save_all()
            if kind == "user":
                return f"[lp] {label}: 组已设为 {target}"
            return f"[lp] {label}: 继承组已设为 {target}"

        # clear
        if holder is None:
            return f"[lp] {noun} {holder_id} 不存在"
        err = self._authorize(context, f"luckperms.{kind}.parent.clear")
        if err:
            return err
        for existing in list(holder.parents):
            holder.remove_parent(existing)
        manager.save_all()
        return f"[lp] {label}: 已清空继承组"

    # ==================== meta 操作（用户/组共用） ====================

    def _handle_meta(
        self,
        manager: Any,
        holder_id: str,
        args: List[str],
        *,
        kind: str,
        context: Optional[CommandContext],
    ) -> str:
        if not args or args[0].lower() == "info":
            return self._format_meta_info(manager, holder_id, kind)

        action = args[0].lower()
        rest = args[1:]
        if action not in ("setprefix", "setsuffix"):
            return _USER_USAGE if kind == "user" else _GROUP_USAGE
        if not rest:
            return f"[lp] 用法: lp {kind} {holder_id} meta {action} [priority] <值>"

        priority = 100
        if len(rest) > 1 and rest[0].lstrip("-").isdigit():
            priority = int(rest[0])
            value = " ".join(rest[1:])
        else:
            value = " ".join(rest)

        err = self._authorize(context, f"luckperms.{kind}.meta.{action}")
        if err:
            return err

        if kind == "user":
            self._ensure_user(manager, holder_id)
        holder = (
            manager.get_user(holder_id) if kind == "user" else manager.get_group(holder_id)
        )
        if holder is None:
            return f"[lp] 组 '{holder_id}' 不存在"

        meta_type = "prefix" if action == "setprefix" else "suffix"
        holder.remove_nodes_by_prefix(f"{meta_type}.")
        from luckperms.models import Node  # 软依赖: 仅写入时使用

        holder.add_node(Node(f"{meta_type}.{priority}.{value}", True))
        manager.save_all()
        return f"[lp] {holder_id}: {meta_type} = {value} (priority={priority})"

    # ==================== 轨道晋升 ====================

    def _user_track(self, manager: Any, user_id: str, params: List[str], *, up: bool) -> str:
        command = "promote" if up else "demote"
        if not params:
            return f"[lp] 用法: lp user {user_id} {command} <轨道>"
        track_name = params[0]
        if manager.get_track(track_name) is None:
            return f"[lp] 轨道 '{track_name}' 不存在（先执行 lp createtrack {track_name} ...）"
        self._ensure_user(manager, user_id)
        result = (
            manager.promote(user_id, track_name)
            if up
            else manager.demote(user_id, track_name)
        )
        if result:
            verb = "已晋升到" if up else "已降级到"
            return f"[lp] {user_id}: {verb} '{result}'"
        if up:
            return f"[lp] {user_id}: 已在轨道 '{track_name}' 的最高级"
        return f"[lp] {user_id}: 已移出轨道（或不在此轨道上）"

    def _showtracks(self, manager: Any, holder_id: str, *, kind: str) -> str:
        holder = (
            manager.get_user(holder_id) if kind == "user" else manager.get_group(holder_id)
        )
        if holder is None:
            noun = "用户" if kind == "user" else "组"
            return f"[lp] {noun} {holder_id}: 未持久化"
        # 用户: 父组是否出现在轨道中；组: 组自身是否出现在轨道中
        members = set(holder.parents) if kind == "user" else {holder_id}
        hits = [track for track in manager.list_tracks() if members & set(track.groups)]
        if not hits:
            return f"[lp] {holder_id}: 未加入任何轨道"
        lines = [f"[lp] {holder_id} 所在轨道:"]
        for track in hits:
            lines.append(f"  {track.name}: {' → '.join(track.groups)}")
        return "\n".join(lines)

    # ==================== 组 / 轨道创建辅助 ====================

    def _create_group(self, name: str, tokens: List[str]) -> str:
        """创建组；参数顺序同时兼容官方 ``[weight] [displayname]`` 与 ``[display] [weight]``。"""
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        if not name:
            return "[lp] 用法: lp creategroup <名称> [权重] [显示名]"
        if manager.get_group(name) is not None:
            return f"[lp] 组 '{name}' 已存在"

        weight = 0
        display = name
        for token in tokens:
            if not token:
                continue
            if token.lstrip("-").isdigit() and weight == 0:
                weight = int(token)
            elif display == name:
                display = token
        manager.create_group(name, display, weight=weight)
        if display != name:
            return f"[lp] 已创建组 {name} (display={display}, weight={weight})"
        return f"[lp] 已创建组 {name} (weight={weight})"

    def _create_track(self, name: str, group_names: List[str]) -> str:
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        if not name:
            return "[lp] 用法: lp createtrack <名称> [组...]"
        if manager.get_track(name) is not None:
            return f"[lp] 轨道 '{name}' 已存在"
        missing = [group for group in group_names if manager.get_group(group) is None]
        if missing:
            return f"[lp] 以下组不存在: {', '.join(missing)}"
        manager.create_track(name, group_names)
        chain = " → ".join(group_names) if group_names else "(空)"
        return f"[lp] 已创建轨道 {name}: {chain}"

    def _group_setweight(self, manager: Any, name: str, params: List[str]) -> str:
        if not params:
            return f"[lp] 用法: lp group {name} setweight <权重>"
        if not params[0].lstrip("-").isdigit():
            return f"[lp] 权重必须是整数: {params[0]}"
        group = manager.get_group(name)
        group.weight = int(params[0])
        manager.save_all()
        return f"[lp] group {name}: 权重已设为 {group.weight}"

    def _group_setdisplayname(self, manager: Any, name: str, params: List[str]) -> str:
        if not params:
            return f"[lp] 用法: lp group {name} setdisplayname <显示名>"
        group = manager.get_group(name)
        group.display_name = " ".join(params)
        manager.save_all()
        return f"[lp] group {name}: 显示名已设为 {group.display_name}"

    # ==================== 权限检查 ====================

    def _check_with_verbose(
        self,
        manager: Any,
        user_id: str,
        node: str,
        context: Optional[Dict[str, str]] = None,
        *,
        source: str = "check",
    ) -> bool:
        try:
            result = bool(manager.check(str(user_id), str(node), dict(context) if context else None))
        except Exception:
            log.exception("权限检查失败: user=%s node=%s", user_id, node)
            result = False
        if self._verbose.active:
            self._verbose.append(
                _VerboseRecord(
                    time.time(), str(user_id), str(node), dict(context or {}), result, source
                )
            )
        return result

    def _check_group_with_verbose(
        self,
        manager: Any,
        group_name: str,
        node: str,
        context: Optional[Dict[str, str]] = None,
        *,
        source: str = "check",
    ) -> bool:
        try:
            result = bool(
                manager.check_group(str(group_name), str(node), dict(context) if context else None)
            )
        except Exception:
            log.exception("组权限检查失败: group=%s node=%s", group_name, node)
            result = False
        if self._verbose.active:
            self._verbose.append(
                _VerboseRecord(
                    time.time(),
                    str(group_name),
                    str(node),
                    dict(context or {}),
                    result,
                    source,
                )
            )
        return result

    # ==================== 身份与授权 ====================

    @staticmethod
    def _resolve_user(token: str, context: Optional[CommandContext]) -> Optional[str]:
        """解析 ``me`` / ``self`` → 执行者标识；无法解析时返回 None。

        - 控制台（或未提供上下文）: 返回 ``console`` 许可人标识（框架约定，ADR-0010；
          与参考实现的 fallback 行为一致），该身份在引导时自动创建并保留 ``*``（拥有全部权限），
          因此 ``lp user me info`` / ``lp check me ...`` / ``lp tree me`` 均可用；
        - 聊天来源: 返回适配器提供的 ``user_id``；缺失时返回 None（调用方给出提示）。
        """
        if token.strip().lower() in ("me", "self"):
            if context is None or context.is_console:
                return "console"
            if context.user_id:
                return str(context.user_id)
            return None
        return token

    def _authorize(
        self,
        context: Optional[CommandContext],
        node: str,
        *,
        crown: Optional[str] = None,
    ) -> Optional[str]:
        """聊天来源的动作级授权；控制台放行。

        Args:
            context: 命令上下文（None 视为本地控制台）。
            node: 要求的官方叶子权限节点。
            crown: 待写入的权限节点（``*`` 禁止在聊天来源授予）。

        Return:
            通过返回 None，否则返回错误文本。
        """
        if context is None or context.is_console:
            return None
        if crown is not None and crown.strip() in ("*", "*:*"):
            return "[lp] 禁止通过聊天授予根权限 *（仅控制台 lp root 可授予）"
        executor = context.user_id
        if not executor:
            return "[lp] 无法校验执行者身份: 命令来源缺少 user_id"
        manager = self._manager()
        if manager is None:
            return self._backend_hint()
        try:
            allowed = bool(manager.check(str(executor), node, None))
        except Exception:
            log.exception("授权检查失败: executor=%s node=%s", executor, node)
            allowed = False
        if not allowed:
            return f"[lp] 权限不足: 需要节点 {node}"
        return None

    # ==================== 后端访问 ====================

    def _manager(self) -> Any | None:
        """返回 luckperms 管理面；当前后端不是 luckperms 时返回 None。"""
        adapter = self._app._permissions
        if not isinstance(adapter, LuckPermsAdapter):
            return None
        try:
            return adapter.manager
        except Exception:
            log.exception("luckperms 加载失败")
            return None

    @staticmethod
    def _backend_hint() -> str:
        return (
            "[lp] 当前权限后端不是 luckperms；"
            "请在 config/app.yaml 设置 permissions.backend: luckperms"
        )

    @staticmethod
    def _ensure_user(manager: Any, user_id: str) -> None:
        if manager.get_user(user_id) is None:
            manager.create_user(user_id, user_id)

    # ==================== Web Editor ====================

    def _spawn(self, coro: Any) -> asyncio.Task:
        """把耗时操作移出事件分发（ADR-0004）；句柄挂在本实例上防 GC。

        M3 起改由任务作用域（PluginScope 同机制）接管生命周期。
        """
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _webeditor(self) -> Any:
        if self._webeditor_session is None:
            if self._manager() is None:
                raise RuntimeError("当前权限后端不是 luckperms")
            self._webeditor_session = self._create_webeditor_session()
        return self._webeditor_session

    def _create_webeditor_session(self) -> Any:
        """创建 Web Editor 会话（测试可替换本方法以隔离网络）。"""
        from luckperms.webeditor.session import WebEditorSession  # 软依赖

        return WebEditorSession(
            get_payload=self._webeditor_payload,
            apply_changes=self._apply_webeditor_changes,
        )

    def _webeditor_payload(self) -> Dict[str, Any]:
        manager = self._manager()
        if manager is None:
            raise RuntimeError("当前权限后端不是 luckperms")
        return manager.to_webeditor_payload()

    def _apply_webeditor_changes(self, payload: Dict[str, Any]) -> None:
        manager = self._manager()
        if manager is None:
            raise RuntimeError("当前权限后端不是 luckperms")
        manager.apply_webeditor_changes(payload)
        manager.save_all()
        log.info("Web Editor 变更已应用并保存")

    # ==================== 帮助文本 ====================

    @staticmethod
    def _lp_help() -> str:
        return (
            "LuckPerms 命令帮助（官方结构 + 扩展）:\n"
            "  通用:\n"
            "    lp info | lp sync\n"
            "    lp check <用户|me> <节点> [key=value ...]\n"
            "    lp verbose [on|record|off|upload] [filter|me]\n"
            "    lp tree <用户|组> [depth]\n"
            "    lp root <用户ID>                （仅控制台）\n"
            "    lp editor [type] [filter] | lp applyedits <code>\n"
            "  用户:\n"
            "    lp user <用户|me> info\n"
            "    lp user <用户|me> permission info|set|unset|settemp|unsettemp|check|clear <节点> [true|false] [时长] [key=value ...]\n"
            "    lp user <用户|me> parent info|set|add|remove|clear <组>\n"
            "    lp user <用户|me> meta info|setprefix|setsuffix [priority] <值>\n"
            "    lp user <用户|me> promote|demote <轨道>\n"
            "    lp user <用户|me> showtracks\n"
            "  组:\n"
            "    lp group <组> info\n"
            "    lp group <组> permission info|set|unset|settemp|unsettemp|check|clear <节点> [true|false] [时长] [key=value ...]\n"
            "    lp group <组> parent info|set|add|remove|clear <组>\n"
            "    lp group <组> meta info|setprefix|setsuffix [priority] <值>\n"
            "    lp group <组> setweight <权重> | setdisplayname <显示名> | showtracks\n"
            "    lp group <组> create [权重] [显示名]\n"
            "  组/轨道管理:\n"
            "    lp creategroup <名称> [权重] [显示名] | deletegroup <名称> | listgroups\n"
            "    lp createtrack <名称> [组...] | deletetrack <名称> | listtracks\n"
            "  轨道:\n"
            "    lp track <轨道> info\n"
            "    lp track <轨道> append <组> | insert <组> [position] | remove <组> | clear\n"
            "    lp track <轨道> create [组...]\n"
        )
