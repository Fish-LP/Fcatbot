"""PluginForge 与 EventBus / CommandRegistry / ServiceRegistry 的协调。

除同步的事件订阅 / 命令注册 / 服务注销外，本层负责**插件异步生命周期的编排**: 

- ``enable(plugin)``: ``on_load`` → 装配（订阅 + 命令） → ``on_enable``
- ``disable(plugin)``: ``on_disable`` → 取消后台任务 → 拆卸 → ``on_unload``
- ``start_all()`` / ``stop_all()``: 应用启动 / 关闭时批量调用（ADR-0007 的过渡实现，
  M3 自研插件内核接管后迁移到 PluginManager/PluginScope）。

单个插件的钩子失败只记日志，不影响其他插件（失败隔离）。
"""

from __future__ import annotations

import inspect
import logging

from pluginforge import BasePlugin, PluginManager

from fcatbot.kernel.commands import (
    CommandConflict,
    CommandRegistry,
    scan_plugin_commands,
)
from fcatbot.kernel.events import Event, EventBus
from fcatbot.kernel.services import ServiceRegistry

log = logging.getLogger("fcatbot.integration")


class IntegrationLayer:
    def __init__(self, pm, bus, services, commands):
        self._pm = pm
        self._bus = bus
        self._services = services
        self._commands = commands
        self._tokens: dict[str, list[str]] = {}

    def attach(self, plugin: BasePlugin) -> None:
        if plugin.name in self._tokens:
            log.warning("Plugin '%s' already attached, skipping", plugin.name)
            return

        tokens = self._scan_and_subscribe(plugin)
        self._tokens[plugin.name] = tokens
        cmd_count = self._register_commands(plugin)

        log.info(
            "Plugin '%s' attached: %d event sub(s), %d command(s)",
            plugin.name, len(tokens), cmd_count,
        )

    def detach(self, plugin: BasePlugin) -> None:
        tokens = self._tokens.pop(plugin.name, [])
        for t in tokens:
            self._bus.unsubscribe(t)

        cmd_removed = self._commands.unregister_by_plugin(plugin.name)
        svc_removed = self._services.unregister_by_provider(plugin.name)

        log.info(
            "Plugin '%s' detached: %d sub(s), %d cmd(s), %d svc(s)",
            plugin.name, len(tokens), cmd_removed, len(svc_removed),
        )

    def attach_all(self) -> None:
        for p in self._pm.get_active_plugins():
            self.attach(p)

    def detach_all(self) -> None:
        for p in list(self._pm.get_active_plugins()):
            self.detach(p)

    # ---------- 异步生命周期编排（插件异步入口，ADR-0007 过渡实现） ----------

    async def enable(self, plugin: BasePlugin) -> None:
        """启用单个插件: ``on_load`` → 装配（事件/命令） → ``on_enable``。"""
        await self._run_hook(plugin, "on_load")
        self.attach(plugin)
        await self._run_hook(plugin, "on_enable")

    async def disable(self, plugin: BasePlugin) -> None:
        """停用单个插件: ``on_disable`` → 取消后台任务 → 拆卸 → ``on_unload``。"""
        await self._run_hook(plugin, "on_disable")
        await self._cancel_tasks(plugin)
        self.detach(plugin)
        await self._run_hook(plugin, "on_unload")

    async def start_all(self) -> None:
        """异步启用全部活跃插件（应用启动装配入口）。"""
        for plugin in self._pm.get_active_plugins():
            await self.enable(plugin)

    async def stop_all(self) -> None:
        """异步停用全部活跃插件（关闭/清理入口）。"""
        for plugin in list(self._pm.get_active_plugins()):
            await self.disable(plugin)

    async def _run_hook(self, plugin: BasePlugin, hook_name: str) -> None:
        hook = getattr(plugin, hook_name, None)
        if hook is None:
            return
        try:
            result = hook()
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception("Plugin '%s' %s() failed", plugin.name, hook_name)

    @staticmethod
    async def _cancel_tasks(plugin: BasePlugin) -> None:
        cancel = getattr(plugin, "cancel_tasks", None)
        if cancel is None:
            return
        try:
            result = cancel()
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception("Plugin '%s' cancel_tasks() failed", plugin.name)

    def _scan_and_subscribe(self, plugin: BasePlugin) -> list[str]:
        tokens: list[str] = []
        for attr_name in dir(type(plugin)):
            attr = getattr(type(plugin), attr_name, None)
            if attr is None or not hasattr(attr, "__event_spec__"):
                continue
            bound = getattr(plugin, attr_name)
            tokens.append(
                self._bus.subscribe(
                    attr.__event_spec__,
                    self._make_wrapper(bound),
                    priority=attr.__event_priority__,
                    once=attr.__event_once__,
                    filter=attr.__event_filter__,
                )
            )
        return tokens

    def _register_commands(self, plugin: BasePlugin) -> int:
        specs = scan_plugin_commands(plugin, plugin.name)
        count = 0
        for spec in specs:
            try:
                self._commands.register(spec)
                count += 1
            except CommandConflict as exc:
                log.error(
                    "Plugin '%s' command '%s' conflicts with '%s'",
                    plugin.name, spec.name, exc.existing_plugin,
                )
        return count

    @staticmethod
    def _make_wrapper(handler):
        async def wrapper(event: Event) -> None:
            r = handler(event)
            if inspect.isawaitable(r):
                await r
        return wrapper