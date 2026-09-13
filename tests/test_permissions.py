"""权限服务测试: LuckPermsAdapter 真实接入 + 应用配置装配 + echo 端到端权限链路。

覆盖:

- 适配器语义（真实 ``luckperms-python``）: default 组引导、游客继承、组继承与通配符、
  显式拒绝、上下文敏感、临时权限过期、meta/prefix、异常安全；
- ``FcatbotApp`` 按 ``config/app.yaml`` 的 ``permissions.backend`` 选择后端；
- 端到端: echo 插件的 ``has_permission`` 真实走 luckperms（拒绝 → 授权放行 → 显式拒绝）。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any

import yaml

from fcatbot import app as host_app
from fcatbot.kernel.commands import CommandContext, accepts_context
from fcatbot.kernel.permissions import (
    AllowAllPermissionService,
    LuckPermsAdapter,
    NullPermissionService,
)

ROOT = Path(__file__).resolve().parent.parent


def run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _run_command(
    registry: Any, text: str, context: CommandContext | None = None
) -> str:
    """执行命令文本（直调处理器，与 AdminCommands 分发语义一致）。"""
    spec, args = registry.find(text.split())
    assert spec is not None and spec.handler is not None, text
    if context is not None and accepts_context(spec.handler):
        result = spec.handler(args, context)
    else:
        result = spec.handler(args)
    if inspect.isawaitable(result):
        result = await result
    return str(result)


# ---------------------------------------------------------------------------
# LuckPermsAdapter（真实 luckperms-python）
# ---------------------------------------------------------------------------


def test_adapter_bootstraps_default_group(tmp_path: Path) -> None:
    adapter = LuckPermsAdapter(tmp_path / "perms")
    manager = adapter.manager
    assert manager.get_group("default") is not None
    # 幂等: 再次访问不重复创建
    assert adapter.manager.get_group("default") is not None


def test_console_identity_has_all_permissions(tmp_path: Path) -> None:
    """控制台身份（默认 ``console``）引导即获得 ``*``，且服务层直接放行。"""
    adapter = LuckPermsAdapter(tmp_path / "perms")
    manager = adapter.manager

    console = manager.get_user("console")
    assert console is not None
    assert any(node.key == "*" and node.value for node in console.nodes)
    assert manager.check("console", "任意.节点", None) is True
    assert run(adapter.has_permission("console", "luckperms.editor")) is True

    # 幂等: 重新加载不重复授予
    adapter2 = LuckPermsAdapter(tmp_path / "perms")
    stars = [n.key for n in adapter2.manager.get_user("console").nodes if n.key == "*"]
    assert stars == ["*"]

    # 可禁用: console_user=None 时不创建、不放行
    plain = LuckPermsAdapter(tmp_path / "plain", console_user=None)
    assert plain.manager.get_user("console") is None
    assert run(plain.has_permission("console", "任意.节点")) is False


def test_adapter_guest_inherits_default_group(tmp_path: Path) -> None:
    async def scenario() -> tuple[bool, bool, bool]:
        adapter = LuckPermsAdapter(tmp_path / "perms")
        # default 组初始无权限 → 游客（未持久化用户）无权限
        before = await adapter.has_permission("10001", "echo.use")
        # 给 default 组授权 → 游客自动继承（库语义）
        adapter.manager.group_add_node("default", "echo.use", True)
        granted = await adapter.has_permission("10001", "echo.use")
        other = await adapter.has_permission("10001", "weather.use")
        return before, granted, other

    assert run(scenario()) == (False, True, False)


def test_adapter_inheritance_wildcard_deny_and_context(tmp_path: Path) -> None:
    async def scenario() -> tuple[bool, bool, bool, bool, bool]:
        adapter = LuckPermsAdapter(tmp_path / "perms")
        m = adapter.manager
        m.create_group("vip", weight=50)
        m.create_group("mod", weight=100)
        m.group_inherit("mod", "vip")  # mod 继承 vip
        m.group_add_node("vip", "plugin.*", True)  # 通配符: 全部 plugin 权限
        m.group_add_node("mod", "plugin.ban", False)  # 显式拒绝覆盖通配符
        m.create_user("10001", "Alice")
        m.user_add_group("10001", "mod")
        # 上下文: 仅群 123456 内允许（注意避开 plugin.* 通配符以免被覆盖）
        m.user_add_node("10001", "chat.fly", True, {"group_id": "123456"})

        wildcard = await adapter.has_permission("10001", "plugin.chat")
        denied = await adapter.has_permission("10001", "plugin.ban")
        ctx_match = await adapter.has_permission(
            "10001", "chat.fly", context={"group_id": "123456"}
        )
        ctx_miss = await adapter.has_permission(
            "10001", "chat.fly", context={"group_id": "999"}
        )
        ctx_absent = await adapter.has_permission("10001", "chat.fly")
        return wildcard, denied, ctx_match, ctx_miss, ctx_absent

    assert run(scenario()) == (True, False, True, False, False)


def test_adapter_temp_permission_expires(tmp_path: Path) -> None:
    async def scenario() -> tuple[bool, bool]:
        adapter = LuckPermsAdapter(tmp_path / "perms")
        m = adapter.manager
        m.create_user("10001")
        # 库注解为 int，运行时支持 float（0.1s 便于快速验证过期）
        m.user_add_node("10001", "temp.node", True, duration=0.1)  # type: ignore[arg-type]
        before = await adapter.has_permission("10001", "temp.node")
        await asyncio.sleep(0.15)
        after = await adapter.has_permission("10001", "temp.node")
        return before, after

    assert run(scenario()) == (True, False)


def test_adapter_groups_prefix_and_meta(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[str], list[str], str, str | None]:
        adapter = LuckPermsAdapter(tmp_path / "perms")
        m = adapter.manager
        guest_groups = await adapter.get_groups("10001")  # 游客 → default
        m.create_user("10001")
        m.user_add_group("10001", "default")
        m.user_add_node("10001", "prefix.100.&cVIP", True)
        user_groups = await adapter.get_groups("10001")
        prefix = await adapter.get_prefix("10001")
        suffix = await adapter.get_meta("10001", "suffix")
        return guest_groups, user_groups, prefix, suffix

    assert run(scenario()) == (["default"], ["default"], "&cVIP", None)


def test_adapter_exception_safety(tmp_path: Path) -> None:
    """底层异常 → 日志 + 安全默认值（False / 空），不向上抛出。"""

    class _BrokenManager:
        def check(self, *args: Any, **kwargs: Any) -> bool:
            raise RuntimeError("boom")

        def get_user(self, uid: str) -> Any:
            raise RuntimeError("boom")

        def get_group(self, name: str) -> Any:
            raise RuntimeError("boom")

    adapter = LuckPermsAdapter(tmp_path / "perms")
    adapter._manager = _BrokenManager()  # type: ignore[assignment]

    assert run(adapter.has_permission("1", "x")) is False
    assert run(adapter.get_groups("1")) == []
    assert run(adapter.get_prefix("1")) == ""
    assert run(adapter.get_meta("1", "prefix")) is None


# ---------------------------------------------------------------------------
# 应用装配: config/app.yaml → permissions.backend
# ---------------------------------------------------------------------------


def _write_app_config(path: Path, permissions: dict | None) -> Path:
    config: dict = {
        "app": {"name": "Test"},
        # pluginforge 白名单: 空列表会导致全部插件被禁用，这里显式列出示例插件
        "plugins": {"enabled": ["echo", "weather", "report"]},
    }
    if permissions is not None:
        config["permissions"] = permissions
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def test_app_selects_backend_from_config(tmp_path: Path) -> None:
    app_lp = host_app.FcatbotApp(
        _write_app_config(
            tmp_path / "lp.yaml",
            {"backend": "luckperms", "data_dir": str(tmp_path / "perms")},
        ),
        [],
    )
    assert isinstance(app_lp._permissions, LuckPermsAdapter)

    app_null = host_app.FcatbotApp(
        _write_app_config(tmp_path / "null.yaml", {"backend": "null"}), []
    )
    assert isinstance(app_null._permissions, NullPermissionService)

    app_default = host_app.FcatbotApp(
        _write_app_config(tmp_path / "default.yaml", None), []
    )
    assert isinstance(app_default._permissions, AllowAllPermissionService)

    app_unknown = host_app.FcatbotApp(
        _write_app_config(tmp_path / "unknown.yaml", {"backend": "nope"}), []
    )
    assert isinstance(app_unknown._permissions, AllowAllPermissionService)


# ---------------------------------------------------------------------------
# 端到端: echo 插件 × luckperms 权限
# ---------------------------------------------------------------------------


class _CollectHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_luckperms_adapter_permission_semantics(tmp_path: Path) -> None:
    """LuckPermsAdapter: 默认拒绝 → 显式授权放行 → 显式拒绝覆盖。"""
    config = _write_app_config(
        tmp_path / "app.yaml",
        {"backend": "luckperms", "data_dir": str(tmp_path / "perms")},
    )

    async def scenario() -> None:
        app = host_app.FcatbotApp(config, [ROOT / "plugins"])
        # 只起权限后端所需的部分
        app._bus.start()
        app._admin.register()
        await app._integration.start_all()

        adapter = app._permissions
        assert isinstance(adapter, LuckPermsAdapter)
        manager = adapter.manager

        # 1) 未授权（用户不存在 / 无节点）→ 拒绝
        assert not await adapter.has_permission("10001", "echo.use")

        # 2) 显式授权 → 放行
        manager.create_user("10001", "Tester")
        manager.user_add_node("10001", "echo.use", True)
        assert await adapter.has_permission("10001", "echo.use")

        # 3) 覆盖为显式拒绝 → 拒绝
        manager.user_add_node("10001", "echo.use", False)
        assert not await adapter.has_permission("10001", "echo.use")

        # 清理
        await app._integration.stop_all()
        await app._bus.close()

    run(scenario())


# ---------------------------------------------------------------------------
# lp 命令集（标准 LuckPerms 命令结构）
# ---------------------------------------------------------------------------


def test_lp_commands_with_luckperms_backend(tmp_path: Path) -> None:
    async def scenario() -> None:
        config = _write_app_config(
            tmp_path / "app.yaml",
            {"backend": "luckperms", "data_dir": str(tmp_path / "perms")},
        )
        app = host_app.FcatbotApp(config, [])
        app._admin.register()
        registry = app._commands

        async def run_cmd(text: str) -> str:
            spec, args = registry.find(text.split())
            assert spec is not None and spec.handler is not None, text
            result = spec.handler(args)
            if inspect.isawaitable(result):
                result = await result
            return str(result)

        # 1) user permission set（省略 true/false 时默认 true）→ check 允许
        assert "= 允许" in await run_cmd("lp user 30001 permission set echo.use")
        assert "→ 允许" in await run_cmd("lp user 30001 permission check echo.use")

        # 2) set false（显式拒绝）
        assert "= 拒绝" in await run_cmd("lp user 30001 permission set echo.use false")
        assert "→ 拒绝" in await run_cmd("lp user 30001 permission check echo.use")

        # 3) unset → 恢复为无节点（游客语义）
        assert "已移除" in await run_cmd("lp user 30001 permission unset echo.use")
        assert "→ 拒绝" in await run_cmd("lp user 30001 permission check echo.use")

        # 4) settemp / unsettemp（标准时长格式）
        out = await run_cmd("lp user 30001 permission settemp temp.node true 30m")
        assert "临时 30m" in out
        assert "→ 允许" in await run_cmd("lp user 30001 permission check temp.node")
        assert "已移除" in await run_cmd("lp user 30001 permission unsettemp temp.node")
        assert "→ 拒绝" in await run_cmd("lp user 30001 permission check temp.node")

        # 5) 上下文参数（key=value）
        await run_cmd("lp user 30002 permission set chat.fly true group_id=999")
        assert "→ 允许" in await run_cmd(
            "lp user 30002 permission check chat.fly group_id=999"
        )
        assert "→ 拒绝" in await run_cmd(
            "lp user 30002 permission check chat.fly group_id=111"
        )

        # 6) 组流程: 创建组 → 组授权 → parent add → 权限经组继承
        assert "已创建组 vip (weight=50)" in await run_cmd("lp creategroup vip 50")
        assert "= 允许" in await run_cmd("lp group vip permission set weather.use true")
        assert "已加入组 vip" in await run_cmd("lp user 40001 parent add vip")
        assert "→ 允许" in await run_cmd("lp user 40001 permission check weather.use")
        assert "vip" in await run_cmd("lp user 40001 parent info")

        # 7) 组继承: staff 继承 vip
        assert "已创建组 staff" in await run_cmd("lp creategroup staff 10")
        assert "现在继承 vip" in await run_cmd("lp group staff parent add vip")
        assert "已加入组 staff" in await run_cmd("lp user 40002 parent add staff")
        assert "→ 允许" in await run_cmd("lp user 40002 permission check weather.use")

        # 8) parent remove / set / clear
        assert "已移出组 staff" in await run_cmd("lp user 40002 parent remove staff")
        assert "→ 拒绝" in await run_cmd("lp user 40002 permission check weather.use")
        assert "组已设为 vip" in await run_cmd("lp user 40002 parent set vip")
        assert "→ 允许" in await run_cmd("lp user 40002 permission check weather.use")
        assert "已清空继承组" in await run_cmd("lp user 40002 parent clear")
        assert "→ 拒绝" in await run_cmd("lp user 40002 permission check weather.use")

        # 9) meta setprefix → 适配器 get_prefix 可见
        out = await run_cmd("lp user 30001 meta setprefix 100 &cVIP")
        assert "prefix = &cVIP" in out
        adapter = app._permissions
        assert isinstance(adapter, LuckPermsAdapter)
        assert await adapter.get_prefix("30001") == "&cVIP"

        # 10) 轨道与晋升: createtrack → promote × 3（到顶）→ demote
        assert "已创建组 mod" in await run_cmd("lp creategroup mod 100")
        assert "已创建轨道 stafftrack" in await run_cmd(
            "lp createtrack stafftrack vip mod"
        )
        assert "已晋升到 'vip'" in await run_cmd("lp user 50001 promote stafftrack")
        assert "已晋升到 'mod'" in await run_cmd("lp user 50001 promote stafftrack")
        assert "最高级" in await run_cmd("lp user 50001 promote stafftrack")
        assert "已降级到 'vip'" in await run_cmd("lp user 50001 demote stafftrack")

        # 11) 列表 / 轨道编辑 / 删除组
        out = await run_cmd("lp listgroups")
        assert "vip" in out and "staff" in out
        out = await run_cmd("lp listtracks")
        assert "stafftrack" in out
        out = await run_cmd("lp track stafftrack info")
        assert "[1] vip" in out and "[2] mod" in out
        assert "已删除组 staff" in await run_cmd("lp deletegroup staff")

    run(scenario())


def test_lp_commands_require_luckperms_backend(tmp_path: Path) -> None:
    app = host_app.FcatbotApp(_write_app_config(tmp_path / "app.yaml", None), [])
    app._admin.register()
    spec, args = app._commands.find(["lp", "user", "1", "info"])
    assert spec is not None and spec.handler is not None
    assert "luckperms" in str(spec.handler(args))


# ---------------------------------------------------------------------------
# lp 命令集（官方命令结构对齐 + 参考实现扩展）
# ---------------------------------------------------------------------------


def test_lp_official_and_reference_commands(tmp_path: Path) -> None:
    """官方命令面（info/sync/tree/creategroup/setweight/showtracks…）+ 参考扩展。"""

    async def scenario() -> None:
        config = _write_app_config(
            tmp_path / "app.yaml",
            {"backend": "luckperms", "data_dir": str(tmp_path / "perms")},
        )
        app = host_app.FcatbotApp(config, [])
        app._admin.register()
        registry = app._commands
        adapter = app._permissions
        assert isinstance(adapter, LuckPermsAdapter)
        manager = adapter.manager

        # 通用命令: info / sync
        out = await _run_command(registry, "lp info")
        assert "数据目录" in out and "用户数" in out
        assert "已同步" in await _run_command(registry, "lp sync")

        # check: 控制台 me → console 身份（拥有全部权限 *）
        out = await _run_command(registry, "lp check me echo.use")
        assert "console" in out and "→ 允许" in out
        out = await _run_command(registry, "lp user me info")
        assert "console" in out and "*" in out
        await _run_command(registry, "lp user 70001 permission set echo.use true")
        assert "→ 允许" in await _run_command(registry, "lp check 70001 echo.use")

        # verbose: 记录检查 → 本地摘要 → 关闭
        await _run_command(registry, "lp verbose on")
        await _run_command(registry, "lp check 70001 echo.use")
        out = await _run_command(registry, "lp verbose upload")
        assert "最近权限检查记录" in out and "echo.use" in out
        assert "已关闭" in await _run_command(registry, "lp verbose off")

        # tree: 继承树（组权重与节点展示）
        assert "已创建组 vip (weight=50" in await _run_command(
            registry, "lp creategroup vip 50"
        )
        await _run_command(registry, "lp group vip permission set weather.use true")
        await _run_command(registry, "lp user 70002 parent add vip")
        out = await _run_command(registry, "lp tree 70002")
        assert "vip" in out and "weight=50" in out and "weather.use" in out

        # creategroup 兼容参考实现顺序（显示名在前）
        out = await _run_command(registry, "lp creategroup mod Mod组 100")
        assert "display=Mod组" in out
        assert manager.get_group("mod").weight == 100

        # group setweight / setdisplayname / create
        assert "权重已设为 77" in await _run_command(
            registry, "lp group mod setweight 77"
        )
        assert "显示名已设为 Mod-2" in await _run_command(
            registry, "lp group mod setdisplayname Mod-2"
        )
        assert "已创建组 aux" in await _run_command(
            registry, "lp group aux create 5 辅助组"
        )

        # showtracks（用户 / 组）
        await _run_command(registry, "lp createtrack stafftrack vip mod")
        assert "stafftrack" in await _run_command(registry, "lp user 70002 showtracks")
        assert "stafftrack" in await _run_command(registry, "lp group mod showtracks")

        # permission info / clear（含临时节点展示）
        await _run_command(
            registry, "lp user 70001 permission settemp temp.node true 30m"
        )
        out = await _run_command(registry, "lp user 70001 permission info")
        assert "echo.use" in out and "temp.node" in out and "临时" in out
        assert "已清空" in await _run_command(
            registry, "lp user 70001 permission clear"
        )
        assert "→ 拒绝" in await _run_command(registry, "lp check 70001 echo.use")

        # track clear
        assert "已清空全部组" in await _run_command(
            registry, "lp track stafftrack clear"
        )
        assert "(空)" in await _run_command(registry, "lp track stafftrack info")

        # root（控制台）: 授予全局 *
        assert "根管理员" in await _run_command(registry, "lp root 79999")
        assert manager.check("79999", "任意.节点", None) is True

    run(scenario())


def test_lp_chat_context_gate(tmp_path: Path) -> None:
    """聊天来源: 动作级门禁、* 保护、lp root 拒绝、me 解析。"""

    async def scenario() -> None:
        config = _write_app_config(
            tmp_path / "app.yaml",
            {"backend": "luckperms", "data_dir": str(tmp_path / "perms")},
        )
        app = host_app.FcatbotApp(config, [])
        app._admin.register()
        registry = app._commands

        # 控制台授予执行者的动作叶子节点
        await _run_command(
            registry, "lp user 80001 permission set luckperms.user.permission.set true"
        )
        chat = CommandContext(source="chat", user_id="80001", group_id="555")

        # 1) 具备叶子节点 → 聊天可分配普通节点
        out = await _run_command(
            registry, "lp user 80002 permission set echo.use true", context=chat
        )
        assert "= 允许" in out

        # 2) 聊天禁止授予根权限 *
        out = await _run_command(
            registry, "lp user 80002 permission set * true", context=chat
        )
        assert "禁止" in out

        # 3) 无叶子节点 → 权限不足
        stranger = CommandContext(source="chat", user_id="80003")
        out = await _run_command(
            registry, "lp user 80002 permission set x.y true", context=stranger
        )
        assert "权限不足" in out

        # 4) lp root 拒绝聊天来源
        out = await _run_command(registry, "lp root 80004", context=chat)
        assert "仅允许在控制台" in out

        # 5) me 解析为执行者；聊天来源缺少 user_id → 明确提示
        out = await _run_command(registry, "lp check me echo.use", context=chat)
        assert "80001" in out and "→ 拒绝" in out
        out = await _run_command(
            registry, "lp check me echo.use", context=CommandContext(source="chat")
        )
        assert "无法解析" in out

    run(scenario())


def test_lp_editor_commands(tmp_path: Path) -> None:
    """lp editor / lp applyedits: 网络操作转后台任务（假会话隔离网络）。"""

    class _FakeSession:
        def __init__(self) -> None:
            self.applied: list[str] = []

        async def open(self) -> str:
            return "https://luckperms.net/editor/FAKE123"

        async def close(self) -> None:
            return None

        async def apply_edits(self, code: str) -> None:
            self.applied.append(code)

    collector = _CollectHandler()

    async def scenario() -> None:
        config = _write_app_config(
            tmp_path / "app.yaml",
            {"backend": "luckperms", "data_dir": str(tmp_path / "perms")},
        )
        app = host_app.FcatbotApp(config, [])
        app._admin.register()
        registry = app._commands
        lp = app._admin._lp

        fake = _FakeSession()
        lp._create_webeditor_session = lambda: fake  # type: ignore[method-assign]

        async def drain() -> None:
            pending = list(getattr(lp, "_tasks", ()))
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        lp_logger = logging.getLogger("fcatbot.lp")
        lp_logger.addHandler(collector)
        try:
            # 命令立即返回（不阻塞事件总线），结果由后台任务日志输出
            out = await _run_command(registry, "lp editor")
            assert "后台" in out
            await drain()
            assert any(
                "FAKE123" in message for message in collector.messages
            ), collector.messages

            out = await _run_command(registry, "lp applyedits abc123")
            assert "后台" in out
            await drain()
            assert fake.applied == ["abc123"]
            assert any(
                "已应用 edits: abc123" in message for message in collector.messages
            ), collector.messages
        finally:
            lp_logger.removeHandler(collector)

    run(scenario())
