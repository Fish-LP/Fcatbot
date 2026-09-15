"""Fcatbot 宿主应用: 装配、启动、停止与 CLI 入口（架构 §2.3 的 ``app.py``）。

- ``FcatbotApp`` 负责基础设施装配（总线/权限/服务/命令/插件/前端）；
- ``main()`` 为 CLI 入口（``pyproject`` 的 ``fcatbot`` 脚本指向 ``fcatbot.app:main``）；
- 仓库根 ``main.py`` 保留为兼容启动器（``python main.py``）。
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pluginforge import PluginManager

from fcatbot import __api_version__, __version__
from fcatbot.adapter.transports import (
    ForwardWebSocketTransport,
    HttpTransport,
    Transport,
)
from fcatbot.builtin import AdminCommands
from fcatbot.frontend.console import ConsoleApp
from fcatbot.kernel.commands import CommandRegistry

# Event 同时作为 ``fcatbot.app.Event`` 对外可见（宿主模块沿用旧引用习惯）
from fcatbot.kernel.events import EventBus
from fcatbot.kernel.integration import IntegrationLayer
from fcatbot.kernel.loader import PluginLoader
from fcatbot.kernel.permissions import (
    AllowAllPermissionService,
    LuckPermsAdapter,
    NullPermissionService,
    PermissionService,
)
from fcatbot.kernel.services import ServiceRegistry
from fcatbot.utils import LogConfig, setup_logging
from fcatbot.webui.server import WebUI

log = logging.getLogger("fcatbot")

# fcatbot/app.py —— 常量区（放在 log 定义之后、safe_name 之前）

DEFAULT_APP_CONFIG: dict[str, Any] = {
    "plugins": {
        "dirs": ["plugins"],
        "enabled": [],
        "data_dir": "data",
    },
    "permissions": {
        "backend": "luckperms",  # allow_all | null | luckperms
        "data_dir": "data/permissions",
        "default_group": "default",
        "console_user": "console",
    },
    "transport": {
        "mode": "forward_ws",  # none | forward_ws | http
        "forward_ws": {
            "url": "",
            "token": "",
            "reconnect": True,
            "reconnect_delay": 1.0,
            "max_reconnect_delay": 30.0,
            "heartbeat": 30.0,
        },
        "http": {
            "host": "127.0.0.1",
            "port": 8080,
            "path": "/",
            "api_base_url": "",
            "token": "",
        },
    },
    "webui": {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 8765,
        "password": "",  # 留空 → 启动时随机生成并打到本地控制台
        "auth_enabled": True,
        "secret_key": "",  # 留空 → 每次启动随机
        "session_ttl": 7 * 24 * 3600,
        "cookie_secure": False,
    },
}


def safe_name(name: str, *, max_length: int = 64) -> str:
    # 只允许字母数字下划线连字符，替换其他字符
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._-")
    if not cleaned:
        raise ValueError("invalid plugin name")
    return cleaned[:max_length]


def _opt_str(value: Any) -> str | None:
    """配置值 → 去空字符串: ``null`` / 空串 / 纯空白 → ``None``。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_float(value: Any) -> float | None:
    """配置值 → 可选浮点数: ``null`` → ``None``。"""
    if value is None:
        return None
    return float(value)


class FcatbotApp:
    def __init__(
        self,
        config_path: Path,
        plugin_dirs: list[Path] | None = None,
        *,
        debug: bool = False,
    ):
        self._config_path = Path(config_path)
        self._debug = bool(debug)
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
        self._ensure_app_config()
        self._app_config = self._load_app_config()
        self._plugin_dirs = self._resolve_plugin_dirs(plugin_dirs)

        # 基础设施
        self._bus = EventBus()
        self._permissions = self._build_permissions()
        self._services = ServiceRegistry()
        self._commands = CommandRegistry()
        self._transport: Transport | None = self._build_transport()
        self._webui: WebUI | None = None
        self._webui_config = self._build_webui_config()

        self._pm = PluginManager(
            str(self._config_path),
            api_version=__api_version__,
            app_version=__version__,
            app_id="fcatbot",
            pre_activate=self._pre_activate,
        )

        self._integration = IntegrationLayer(
            self._pm, self._bus, self._services, self._commands
        )
        self._loader = PluginLoader(self._plugin_dirs)
        # 启动时发现的插件（插件名 → 插件类）；供前端展示，避免用目录名冒充插件名
        self._discovered_plugins: dict[str, type] = {}
        self._admin = AdminCommands(self)

        self._console: ConsoleApp | None = None
        self._stop_event = asyncio.Event()
        self._cleaned = False
        # 运行时装卸保护：WebUI 按钮 / 命令可能并发触发。
        # asyncio.Lock 延迟到运行中的事件循环内创建（见 _get_runtime_lock）。
        self._runtime_lock: asyncio.Lock | None = None

    def _load_app_config(self) -> dict:
        """读取 ``config/app.yaml``（缺失 / 解析失败时返回空 dict，不阻断启动）。"""
        try:
            with open(self._config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            log.warning("配置文件不存在，使用内置默认值: %s", self._config_path)
            return {}
        except Exception:
            log.exception("读取配置失败，使用内置默认值: %s", self._config_path)
            return {}

    def rescan_plugins(self) -> dict[str, list[str]]:
        """重新扫描插件目录，只刷新 discovered 缓存，不激活任何插件。

        与启动装配保持同一套发现机制：都是 PluginLoader.discover()。
        与 PluginManager.rediscover() / discover_plugins() 的区别：
        - 那两个走 entry points，与本宿主使用的目录扫描不是一回事
        - 且会连带激活/停用插件，不符合「先发现、用户再决定」的语义
        """
        before = set(self._discovered_plugins.keys())

        plugin_classes = self._loader.discover()
        self._discovered_plugins = {
            cls.name: cls for cls in plugin_classes if getattr(cls, "name", None)
        }

        # 新发现的插件也要落一份默认配置，与 run() 里的做法一致
        try:
            self._ensure_plugin_configs(plugin_classes)
        except Exception:
            log.exception("重扫描后生成默认配置失败")

        after = set(self._discovered_plugins.keys())
        return {
            "added": sorted(after - before),
            "removed": sorted(before - after),
        }

    def _ensure_app_config(self) -> None:
        """配置文件缺失时落一份带默认值的 ``config/app.yaml``。

        - 已存在则**绝不覆盖**，避免抹掉用户改动；
        - 落盘失败只记日志，由 ``_load_app_config`` 回退到代码内默认值，
          不阻断启动。
        """
        if self._config_path.exists():
            return
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                yaml.dump(DEFAULT_APP_CONFIG, f, allow_unicode=True, sort_keys=False)
            log.info("已生成默认配置文件: %s", self._config_path)
        except Exception:
            log.exception(
                "生成默认配置文件失败，将使用内置默认值: %s", self._config_path
            )

    def _resolve_plugin_dirs(self, plugin_dirs: list[Path] | None) -> list[Path]:
        """插件目录: 显式入参优先，否则读 ``config/app.yaml → plugins.dirs``。

        ``plugins.dirs`` 缺省为 ``["plugins"]``；接受字符串（单个）或列表。
        """
        if plugin_dirs is None:
            raw = (self._app_config.get("plugins") or {}).get("dirs")
            if raw is None:
                raw = ["plugins"]
            elif isinstance(raw, (str, Path)):
                raw = [raw]
            plugin_dirs = [Path(str(d)) for d in raw]
        return [Path(d) for d in plugin_dirs]

    def _build_webui_config(self) -> dict:
        """按 ``config/app.yaml`` 的 ``webui`` 段读取 WebUI 输入参数。

        - ``enabled``（默认 ``True``）: 是否启动 Web 管理界面；
        - ``host``（默认 ``127.0.0.1``）/ ``port``（默认 ``8765``）；
        - ``password``: 访问密码；留空 / ``null`` → 启动时随机生成 12 位，
          并在 WebUI 启动前打印到本地可信控制台（不走日志，避免被广播）；
        - ``secret_key``: 会话签名密钥（留空 → 每次启动随机，重启后旧会话失效）；
        - ``session_ttl``（默认 7 天，秒）；
        - ``cookie_secure``（默认 ``False``；置于 HTTPS 反向代理后应置 ``True``）。
        """
        cfg = self._app_config.get("webui") or {}
        return {
            "enabled": bool(cfg.get("enabled", True)),
            "host": str(cfg.get("host") or "127.0.0.1"),
            "port": int(cfg.get("port", 8765)),
            "password": _opt_str(cfg.get("password")),
            "auth_enabled": bool(cfg.get("auth_enabled", True)),
            "secret_key": _opt_str(cfg.get("secret_key")),
            "session_ttl": int(cfg.get("session_ttl", 7 * 24 * 3600)),
            "cookie_secure": bool(cfg.get("cookie_secure", False)),
        }

    def _build_permissions(self) -> PermissionService:
        """按 ``config/app.yaml`` 的 ``permissions`` 段构建权限后端。

        backend 取值:
        - ``allow_all``（默认）: 开发模式，全部放行；
        - ``null``: 全部拒绝；
        - ``luckperms``: 接入 luckperms-python（组继承 / 通配符 / 上下文 / 临时权限）。

        luckperms 附加选项: ``data_dir``（默认 ``data/permissions``）、
        ``default_group``（游客兜底组，默认 ``default``）。
        """
        cfg = self._app_config.get("permissions") or {}
        backend = str(cfg.get("backend") or "allow_all").strip().lower()

        if backend == "luckperms":
            data_dir = Path(str(cfg.get("data_dir") or "data/permissions"))
            default_group = cfg.get("default_group") or "default"
            console_user = cfg.get("console_user", "console")
            if console_user is not None:
                console_user = str(console_user).strip() or None
            log.info(
                "权限后端: luckperms（data_dir=%s, default_group=%s, console_user=%s）",
                data_dir,
                default_group,
                console_user,
            )
            return LuckPermsAdapter(
                data_dir, default_group=default_group, console_user=console_user
            )
        if backend == "null":
            log.info("权限后端: null（全部拒绝）")
            return NullPermissionService()
        if backend != "allow_all":
            log.warning("未知权限后端 '%s'，已回退 allow_all", backend)
        log.info("权限后端: allow_all（开发模式；生产环境请使用 luckperms）")
        return AllowAllPermissionService()

    def _build_transport(self) -> Transport | None:
        """按 ``config/app.yaml`` 的 ``transport`` 段构建连接件（M4）。

        输入参数（``transport.mode`` 选择形态，其余为对应形态的参数）:

        - ``none``（默认）: 不启用；
        - ``forward_ws``: 正向 WebSocket 客户端，参数见 ``transport.forward_ws``
          （``url`` 必填；``token`` / ``headers`` / ``reconnect`` /
          ``reconnect_delay`` / ``max_reconnect_delay`` / ``heartbeat`` 可选）；
        - ``http``: HTTP 回调服务器，参数见 ``transport.http``
          （``host`` / ``port`` / ``path`` / ``api_base_url`` / ``token`` / ``headers``）。
        """
        cfg = self._app_config.get("transport") or {}
        mode = str(cfg.get("mode") or "none").strip().lower()

        if mode in ("", "none", "off", "disabled"):
            log.info("连接件: none（未启用）")
            return None

        if mode in ("forward_ws", "ws", "forward_websocket"):
            opts = dict(cfg.get("forward_ws") or {})
            url = _opt_str(opts.get("url"))
            if not url:
                log.error("连接件 forward_ws 缺少 url，已跳过")
                return None
            transport = ForwardWebSocketTransport(
                self._bus,
                url,
                token=_opt_str(opts.get("token")),
                headers=opts.get("headers") or None,
                reconnect=bool(opts.get("reconnect", True)),
                reconnect_delay=float(opts.get("reconnect_delay", 1.0)),
                max_reconnect_delay=float(opts.get("max_reconnect_delay", 30.0)),
                heartbeat=_opt_float(opts.get("heartbeat", 30.0)),
            )
            log.info("连接件: forward_ws → %s", url)
            return transport

        if mode == "http":
            opts = dict(cfg.get("http") or {})
            transport = HttpTransport(
                self._bus,
                host=str(opts.get("host") or "127.0.0.1"),
                port=int(opts.get("port", 8080)),
                path=str(opts.get("path") or "/"),
                api_base_url=_opt_str(opts.get("api_base_url")),
                token=_opt_str(opts.get("token")),
                headers=opts.get("headers") or None,
            )
            log.info("连接件: http 监听 %s", transport.url)
            return transport

        log.warning("未知连接件 mode '%s'，已跳过", mode)
        return None

    def _pre_activate(self, plugin, app_config: dict) -> bool:
        plugin._bus = self._bus
        plugin._permissions = self._permissions
        plugin._services = self._services
        plugin._transport = self._transport
        opts = dict(app_config.get("plugins") or {})
        plugin._data_dir = (
            Path(opts.get("data_dir", "data")) / "plugins" / safe_name(plugin.name)
        )
        plugin._debug = self._debug
        self._services.register_from_plugin(plugin)
        return True

    # ==================== 只读属性 ====================

    @property
    def discovered_plugins(self) -> dict[str, type]:
        """启动时发现的插件（插件名 → 插件类）。

        注意: 插件名取自插件类声明的 ``name``，与插件**目录名**无关
        （如 ``plugins/adapter/`` 的插件 name 为 ``"NapcatAdapter"``）。
        """
        return dict(self._discovered_plugins)

    @property
    def transport(self) -> Transport | None:
        """当前连接件实例（未启用时为 ``None``）。"""
        return self._transport

    # ==================== 运行时启用 / 停用 ====================
    #
    # 前端（WebUI）与命令统一走这两个入口，**不要**直接调 PluginForge 的
    # activate_plugin / deactivate_plugin:
    # - pluginforge 只切自己的生命周期与 pluggy 钩子，不碰内核的事件订阅 /
    #   命令注册 / 服务注册（停用后会残留资源）；
    # - 对启动时未加载（未在 plugins.enabled 内 / 后来才发现）的插件，
    #   activate_plugin 找不到实例，只会打一条 warning 而不报错。
    #
    # 并发保护：WebUI 按钮 / 命令行可能并发触发同名启用/停用/重载。
    # 所有对外入口统一串行化，避免 PluginForge 收到重复的 register/unregister。

    def _get_runtime_lock(self) -> asyncio.Lock:
        """延迟创建运行时锁。

        ``asyncio.Lock`` 必须在运行中的事件循环里创建（避免在 Python 3.10/3.11
        上绑定到错误的循环）。首次调用时创建即可。
        """
        if self._runtime_lock is None:
            self._runtime_lock = asyncio.Lock()
        return self._runtime_lock

    def _active_plugin(self, name: str):
        """按插件名（类属性 ``name``，非目录名）查找当前活跃实例。"""
        for plugin in self._pm.get_active_plugins():
            if plugin.name == name:
                return plugin
        return None

    async def enable_plugin(self, name: str) -> tuple[bool, str]:
        """运行时启用插件（并发安全）。参见 :meth:`_enable_plugin_locked`。"""
        async with self._get_runtime_lock():
            return await self._enable_plugin_locked(name)

    async def disable_plugin(self, name: str) -> tuple[bool, str]:
        """运行时停用插件（并发安全）。参见 :meth:`_disable_plugin_locked`。"""
        async with self._get_runtime_lock():
            return await self._disable_plugin_locked(name)

    async def reload_plugin(self, name: str) -> tuple[bool, str]:
        """运行时热重载插件（并发安全）。参见 :meth:`_reload_plugin_locked`。"""
        async with self._get_runtime_lock():
            return await self._reload_plugin_locked(name)

    async def _enable_plugin_locked(self, name: str) -> tuple[bool, str]:
        """运行时启用插件: ``init → activate``（PluginForge）+ ``on_load → 装配 → on_enable``。

        与启动装配序列一致；插件类取自 :attr:`discovered_plugins`（启动时发现，
        键为插件类声明的 ``name``）。每次启用都实例化**全新对象**，避免复用上次
        停用后残留的实例状态。

        Returns:
            ``(ok, message)``；``ok=False`` 时 ``message`` 可直接展示给用户。
        """
        if self._active_plugin(name) is not None:
            return True, f"插件 {name} 已处于启用状态"

        cls = self._discovered_plugins.get(name)
        if cls is None:
            known = "、".join(sorted(self._discovered_plugins)) or "（无）"
            return False, f"未发现插件 '{name}'（注意插件名 ≠ 目录名）；已发现: {known}"

        plugin = cls()
        try:
            # init → pre_activate（注入依赖 + 注册服务）→ pluggy 注册 → activate
            self._pm.register_plugin(plugin)
        except Exception as exc:
            log.exception("启用插件 '%s' 失败", name)
            return False, f"启用失败: {exc}"

        if self._active_plugin(name) is None:
            reason = self._pm.get_load_errors().get(name) or "激活未完成"
            log.warning("插件 '%s' 激活失败: %s", name, reason)
            return False, f"启用失败: {reason}"

        try:
            await self._integration.enable(plugin)
        except Exception as exc:
            log.exception("装配插件 '%s' 失败", name)
            return False, f"已激活，但事件/命令装配失败: {exc}"

        log.info("插件 '%s' 已运行时启用", name)
        return True, f"插件 {name} 已启用"

    async def _disable_plugin_locked(self, name: str) -> tuple[bool, str]:
        """运行时停用插件: ``on_disable → 取消任务 → 拆卸 → on_unload`` + PluginForge 反注册。

        「拆卸」会退订该插件的全部事件订阅、注销其命令与服务，
        因此停用后不残留任何运行资源。

        Returns:
            ``(ok, message)``；``ok=False`` 时 ``message`` 可直接展示给用户。
        """
        plugin = self._active_plugin(name)
        if plugin is None:
            if (
                self._pm.get_plugin(name) is None
                and name not in self._discovered_plugins
            ):
                return False, f"未发现插件 '{name}'"
            return True, f"插件 {name} 未在运行，无需停用"

        try:
            await self._integration.disable(plugin)
        except Exception as exc:
            log.exception("停用插件 '%s' 失败", name)
            return False, f"停用失败: {exc}"

        try:
            self._pm.deactivate_plugin(name)
        except Exception as exc:
            log.exception("deactivate_plugin('%s') 失败", name)
            return False, f"已拆卸，但反注册失败: {exc}"

        log.info("插件 '%s' 已运行时停用", name)
        return True, f"插件 {name} 已停用（事件/命令/服务已注销）"

    async def _reload_plugin_locked(self, name: str) -> tuple[bool, str]:
        """运行时热重载插件: ``disable`` → PluginForge 重新导入/实例化 → ``enable``。

        必须先走 :meth:`disable_plugin` 的拆卸: PluginForge 的 ``reload_plugin``
        只重建插件实例，内核里的事件订阅 / 命令仍指向**旧实例**的绑定方法，
        不拆卸就会出现「重载后旧代码仍在响应」的残留。

        内部直接调用集成层的 ``disable`` / ``enable``，避免与外层锁重入。

        Returns:
            ``(ok, message)``；``ok=False`` 时 ``message`` 可直接展示给用户。
        """
        plugin = self._active_plugin(name)
        if plugin is None:
            return False, f"插件 {name} 未在运行，无法重载（请先启用）"

        reload_fn = getattr(self._pm, "reload_plugin", None)
        if not callable(reload_fn):
            return False, "PluginForge 不支持 reload_plugin"

        try:
            await self._integration.disable(plugin)
        except Exception as exc:
            log.exception("重载前停用 '%s' 失败", name)
            return False, f"停用失败: {exc}"

        try:
            result = reload_fn(name)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            log.exception("reload_plugin('%s') 失败", name)
            return False, f"重载失败（插件已停止）: {exc}"
        if result is False:
            reason = self._pm.get_load_errors().get(name, "未知原因")
            return False, f"重载失败（插件已停止）: {reason}"

        new_plugin = self._active_plugin(name)
        if new_plugin is None:
            reason = self._pm.get_load_errors().get(name, "未知原因")
            return False, f"重载后未激活（插件已停止）: {reason}"

        try:
            await self._integration.enable(new_plugin)
        except Exception as exc:
            log.exception("重载后装配 '%s' 失败", name)
            return False, f"已重载，但事件/命令装配失败: {exc}"

        log.info("插件 '%s' 已重载", name)
        return True, f"插件 {name} 已重载"

    # ==================== 启动 / 停止 ====================

    async def run(self) -> None:
        log.info("Fcatbot starting ...")
        log.info("Plugin dirs: %s", self._plugin_dirs)

        self._bus.start()
        self._admin.register()  # 先注册框架命令

        plugin_classes = self._loader.discover()
        self._discovered_plugins = {
            cls.name: cls for cls in plugin_classes if getattr(cls, "name", None)
        }
        if plugin_classes:
            try:
                self._ensure_plugin_configs(plugin_classes)
                result = self._pm.register_plugins(plugin_classes)
                log.info("Activated: %s", getattr(result, "activated", "?"))
            except Exception:
                log.exception("register_plugins failed")
                raise
        else:
            log.warning("No plugins discovered in %s", self._plugin_dirs)

        # 异步生命周期: on_load → 装配（订阅/命令）→ on_enable
        await self._integration.start_all()

        log.info(
            "Registered services: %s",
            [s.name for s in self._services.list_services()],
        )
        log.info(
            "Registered commands: %s",
            [s.name for s in self._commands.all_roots()],
        )

        self._console = ConsoleApp(
            self._bus,
            self._request_shutdown,
            commands=self._commands,
        )
        console_task = asyncio.create_task(self._console.run(), name="console")
        ws_task = asyncio.create_task(self._ws_loop(), name="ws")

        try:
            # WebUI 启动放在 try 内: 任何异常都不会泄漏上面的两个任务，
            # 且会走到 finally 完成 clean shutdown。
            if self._webui_config.get("enabled"):
                await self._start_webui()

            log.info("Fcatbot started. Type 'help' for available commands.")
            await self._stop_event.wait()
        finally:
            console_task.cancel()
            ws_task.cancel()
            for t in (console_task, ws_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass
                except Exception:
                    log.exception("Task cleanup failed")
            await self._cleanup()

    async def _start_webui(self) -> None:
        """启动 WebUI（可选）。

        - 找宿主日志的 console handler 作为 WebUI 日志模板；找不到就传 None，
          由 WebUI 自造一个默认 formatter（修复了原先 ``next(...)`` 在无
          StreamHandler 环境下抛 ``StopIteration`` 的问题）。
        - 任何失败只记录日志，不影响主流程；``self._webui`` 会保持 ``None``。
        """
        # 尝试找一个 StreamHandler 作为日志格式模板（不是必须的）
        console_handler: logging.Handler | None = None
        for h in logging.getLogger().handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(
                h, logging.FileHandler
            ):
                console_handler = h
                break

        try:
            self._webui = WebUI(
                self,
                host=self._webui_config["host"],
                port=self._webui_config["port"],
                password=self._webui_config["password"],
                auth_enabled=self._webui_config["auth_enabled"],
                secret_key=self._webui_config["secret_key"],
                session_ttl=self._webui_config["session_ttl"],
                cookie_secure=self._webui_config["cookie_secure"],
                log_handler=console_handler,
                access_log_level=logging.DEBUG if self._debug else logging.WARN,
            )
            # 在 WebUI 启动**前**打印（可能自动生成的）访问密码到本地可信控制台。
            # 必须走 console_print 直写终端而非 logging: WebUI 的日志处理器会把
            # 日志广播给所有 WebSocket 客户端，密码进入日志即等于泄露。
            self._webui.report_access_password()

            await self._webui.start()
        except Exception:
            log.exception("WebUI 启动失败")
            self._webui = None

    def _request_shutdown(self) -> None:
        self._stop_event.set()

    def _ensure_plugin_configs(self, plugin_classes: list[type]) -> None:
        """为每个插件创建默认配置文件（如果不存在）。

        在 PluginForge.register_plugins() 之前调用，
        确保 PluginForge 读到的是包含默认值的文件。
        """
        config_dir = self._config_path.parent / "plugins"
        config_dir.mkdir(parents=True, exist_ok=True)

        for cls in plugin_classes:
            name = getattr(cls, "name", None)
            default = getattr(cls, "default_config", None)
            if not name or not default:
                continue

            path = config_dir / f"{name}.yaml"
            if path.exists():
                log.debug("Plugin config exists: %s", path)
                continue

            try:
                with open(path, "w", encoding="utf-8") as f:
                    yaml.dump(default, f, allow_unicode=True, sort_keys=False)
                log.info("Created default config: %s", path)
            except Exception:
                log.exception("Failed to create default config for '%s'", name)

    async def _cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        log.info("Cleaning up ...")

        if self._webui is not None:
            try:
                await self._webui.stop()
            except Exception:
                log.exception("webui.stop failed")
            self._webui = None

        try:
            self._admin.unregister()
        except Exception:
            log.exception("admin.unregister failed")

        try:
            await self._integration.stop_all()
        except Exception:
            log.exception("stop_all failed")

        if self._transport is not None:
            try:
                await self._transport.stop()
            except Exception:
                log.exception("transport.stop failed")
            self._transport = None

        try:
            self._pm.deactivate_all()
        except Exception:
            log.exception("deactivate_all failed")

        try:
            await self._bus.close()
        except Exception:
            log.exception("bus.close failed")

        log.info("Cleanup complete")

    async def _ws_loop(self) -> None:
        """连接后端（过渡实现）: 驱动 ``transport`` 配置选定的**真实连接件**。

        取代此前模拟发布 ``sdk.raw`` 的假循环: WS 后端 =
        :class:`ForwardWebSocketTransport`（收到帧发布 ``raw.ws.*``）。
        本期仅打通 WS（``transport.mode: forward_ws``）；HTTP 连接件走同一入口，
        M4 适配器插件落地后由插件接管。

        在本协程（``ws_task``）内启停连接件:
        - 启动时机晚于 ``integration.start_all()``（此时适配器插件已订阅 ``raw.*``，
          不会丢弃首帧）；
        - 收到停止信号 / 任务被取消时负责 ``stop()``（``_cleanup`` 另有一道幂等兜底）；
        - ``transport.start()`` 抛出的异常在此捕获并记录——宿主继续运行，
          连接件内部的重连逻辑负责其运行期恢复。
        """
        transport = self._transport
        if transport is None:
            log.info("未配置连接件（transport.mode = none），连接后端未启动")
            return

        try:
            await transport.start()
        except asyncio.CancelledError:
            raise
        except Exception:
            # 启动失败: 记录并退出 ws_task。不做自动重启——连接件自身的
            # reconnect 逻辑负责运行期重连；启动期失败多为配置错误，
            # 无意义地重试只会刷日志。
            log.exception("连接后端启动失败: %s", transport)
            return

        log.info("连接后端已启动: %s", transport)
        try:
            await self._stop_event.wait()
        finally:
            try:
                await transport.stop()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("连接件停止失败: %s", transport)
            else:
                log.info("连接后端已停止: %s", transport)


# ==================== CLI ====================


# 除「到哪去找配置文件」外，全部运行参数（webui / transport / api / plugins.dirs）
# 均来自 config/app.yaml；CLI 不再重复暴露。
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fcatbot", description="Fcatbot CLI")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=Path("config/app.yaml"),
        help="设置框架配置文件路径",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="开启调试模式",
    )
    return parser


def main() -> None:

    parser = _build_parser()
    args = parser.parse_args()
    setup_logging(
        LogConfig(console_level=logging.DEBUG if args.debug else logging.INFO)
    )

    app = FcatbotApp(args.config, debug=args.debug)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        log.info("Interrupted")


if __name__ == "__main__":
    main()
