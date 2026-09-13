"""运行时启用 / 停用（WebUI 开关）集成测试。

回归两个缺陷:

1. **启动时未加载（未列入 ``plugins.enabled``）的插件无法在 WebUI 中启用**
   —— ``PluginForge.activate_plugin`` 只认已经初始化过的实例，找不到就只打 warning；
2. **停用插件后资源仍然存在** —— 直接调 ``PluginForge.deactivate_plugin`` 不会退订事件、
   注销命令 / 服务、取消后台任务，插件仍在响应。

因此装卸必须走宿主入口 ``FcatbotApp.enable_plugin`` / ``disable_plugin``。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from fcatbot import app as host_app
from fcatbot.frontend.webui import WebUI
from fcatbot.kernel.events import Event

ALPHA_SOURCE = """
from fcatbot import FcatbotPlugin, console_command, on_event


class AlphaPlugin(FcatbotPlugin):
    name = "alpha"
    version = "1.0.0"
    description = "startup plugin"
    target_application = "fcatbot"
    min_app_version = "1.0.0"

    def __init__(self) -> None:
        self.seen: list = []

    @console_command("alpha", help="alpha")
    def cmd_alpha(self, args: list[str]) -> str:
        return "alpha-ok"

    @on_event("raw.test")
    async def on_raw(self, event) -> None:
        self.seen.append(event.data)
"""

BETA_SOURCE = """
import asyncio

from fcatbot import FcatbotPlugin, console_command, on_event


class BetaPlugin(FcatbotPlugin):
    name = "beta"
    version = "1.0.0"
    description = "loadable on demand"
    target_application = "fcatbot"
    min_app_version = "1.0.0"
    provides = {"beta.api": None}

    def __init__(self) -> None:
        self.seen: list = []
        self.task = None

    async def on_enable(self) -> None:
        self.task = self.create_task(asyncio.sleep(3600), name="loop")

    @console_command("beta", help="beta")
    def cmd_beta(self, args: list[str]) -> str:
        return "beta-ok"

    @on_event("raw.test")
    async def on_raw(self, event) -> None:
        self.seen.append(event.data)
"""


def _write_workspace(tmp_path: Path, *, enabled: list[str]) -> tuple[Path, Path]:
    plugins_dir = tmp_path / "plugins"
    for name, source in (("alpha", ALPHA_SOURCE), ("beta", BETA_SOURCE)):
        package = plugins_dir / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text(source, encoding="utf-8")

    config = tmp_path / "app.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "app": {"name": "test", "version": "1.0.0"},
                "permissions": {"backend": "allow_all"},
                "webui": {"enabled": False},
                "plugins": {"dirs": [str(plugins_dir)], "enabled": enabled},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return config, plugins_dir


async def _boot(config: Path, plugins_dir: Path) -> host_app.FcatbotApp:
    """复刻 ``app.run()`` 的装配序列（不含 ConsoleApp / WebUI / 连接件）。"""
    app = host_app.FcatbotApp(config, [plugins_dir])
    app._bus.start()
    app._admin.register()
    classes = app._loader.discover()
    app._discovered_plugins = {
        cls.name: cls for cls in classes if getattr(cls, "name", None)
    }
    app._ensure_plugin_configs(classes)
    app._pm.register_plugins(classes)
    await app._integration.start_all()
    return app


def _active_names(app: host_app.FcatbotApp) -> list[str]:
    return sorted(p.name for p in app._pm.get_active_plugins())


def _command_names(app: host_app.FcatbotApp) -> set[str]:
    return {spec.name for spec in app._commands.all_roots()}


async def _teardown(app: host_app.FcatbotApp) -> None:
    await app._integration.stop_all()
    app._pm.deactivate_all()
    await app._bus.close()


def test_enable_previously_unloaded_plugin(tmp_path: Path) -> None:
    config, plugins_dir = _write_workspace(tmp_path, enabled=["alpha"])

    async def scenario() -> None:
        app = await _boot(config, plugins_dir)
        try:
            # 启动时 beta 未加载: 无命令、无事件订阅、无服务
            assert _active_names(app) == ["alpha"]
            assert _command_names(app) == {
                "alpha",
                "help",
                "plugins",
                "reload",
                "services",
                "config",
                "health",
                "lp",
            }

            ok, msg = await app.enable_plugin("beta")
            assert ok, msg

            # 装配到位: 活跃 + 命令 + 事件订阅 + 服务
            assert "beta" in _active_names(app)
            assert "beta" in _command_names(app)
            assert app._services.has("beta.api")

            await app._bus.publish(Event(name="raw.test", data="on-demand"))
            assert app._active_plugin("beta").seen == ["on-demand"]

            # 重复启用是幂等的，不会重复订阅
            ok, msg = await app.enable_plugin("beta")
            assert ok and "已处于启用状态" in msg
        finally:
            await _teardown(app)

    asyncio.run(scenario())


def test_disable_releases_all_resources(tmp_path: Path) -> None:
    config, plugins_dir = _write_workspace(tmp_path, enabled=["alpha", "beta"])

    async def scenario() -> None:
        app = await _boot(config, plugins_dir)
        try:
            plugin = app._active_plugin("beta")
            assert plugin is not None
            assert plugin.task is not None and not plugin.task.done()

            await app._bus.publish(Event(name="raw.test", data="before-disable"))
            assert plugin.seen == ["before-disable"]

            ok, msg = await app.disable_plugin("beta")
            assert ok, msg

            # 1. 不再活跃
            assert "beta" not in _active_names(app)
            # 2. 命令已注销
            assert "beta" not in _command_names(app)
            # 3. 服务已注销
            assert not app._services.has("beta.api")
            # 4. 后台任务已取消（停用后不再有残留协程）
            assert plugin.task.cancelled()
            # 5. 事件订阅已退订: 停用后的事件不再送达
            await app._bus.publish(Event(name="raw.test", data="after-disable"))
            assert plugin.seen == ["before-disable"]

            # alpha 不受影响
            assert "alpha" in _active_names(app)

            # 再次停用: 未在运行，但不算失败
            ok, msg = await app.disable_plugin("beta")
            assert ok and "无需停用" in msg
        finally:
            await _teardown(app)

    asyncio.run(scenario())


def test_enable_unknown_plugin_reports_reason(tmp_path: Path) -> None:
    config, plugins_dir = _write_workspace(tmp_path, enabled=["alpha"])

    async def scenario() -> None:
        app = await _boot(config, plugins_dir)
        try:
            # 目录名 ≠ 插件名: 用目录名启用应给出可读原因，而不是谎报成功
            ok, msg = await app.enable_plugin("plugins")
            assert not ok
            assert "未发现插件" in msg
            assert "alpha" in msg and "beta" in msg  # 已发现列表
        finally:
            await _teardown(app)

    asyncio.run(scenario())


def test_webui_toggle_persists_enabled_list(tmp_path: Path) -> None:
    config, plugins_dir = _write_workspace(tmp_path, enabled=["alpha"])
    app = host_app.FcatbotApp(config, [plugins_dir])
    ui = WebUI(app)

    assert ui._read_enabled_list() == ["alpha"]

    assert ui._set_enabled("beta", True) is True
    assert ui._read_enabled_list() == ["alpha", "beta"]
    # 无变化时不重写
    assert ui._set_enabled("beta", True) is False

    assert ui._set_enabled("alpha", False) is True
    assert ui._read_enabled_list() == ["beta"]
