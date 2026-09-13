"""Fcatbot 插件基类。

在 PluginForge ``BasePlugin`` 之上扩展: 

- **异步生命周期入口**: ``on_load`` / ``on_enable`` / ``on_disable`` / ``on_unload``
  （由 :class:`~fcatbot.kernel.integration.IntegrationLayer` 在装配/停用前后 ``await`` 调用）。
  pluginforge 的 ``init`` / ``activate`` / ``deactivate`` 是**同步**的（pluggy 钩子不 await），
  异步能力请使用这四个钩子；M3 自研内核落地后二者合并。
- **极简任务作用域**: ``create_task`` / ``cancel_tasks``（停用时自动取消；M3 并入 ``PluginScope``）；
- 声明框架注入属性的类型，供 IDE 使用；
- 日志 / 事件发布 / 权限检查（含**事件感知**的带上下文检查）/ 服务查询的便捷方法；
- 声明式服务注册（``provides`` 类属性）。

权限模型
--------
本基类**不猜任何平台**。事件到 ``(主体, 上下文)`` 的翻译由适配器插件实现
:class:`~fcatbot.kernel.permissions.EventTranslator` 协议，并以服务形式注册在
``f"{event.source}.translator"``。基类的 ``has_permission_for(event, node)`` 按
``event.source`` 查找翻译器，再委托 :attr:`_permissions` 做实际判定。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, ClassVar, Iterable, Mapping

from pluginforge import BasePlugin

from fcatbot.adapter.transports import Transport
from fcatbot.kernel.events import Event, EventBus
from fcatbot.kernel.permissions import EventTranslator, PermissionService
from fcatbot.kernel.services import ServiceRegistry


class FcatbotPlugin(BasePlugin):
    """所有 Fcatbot 插件的基类。"""

    # ---- 类型声明（运行时由 FcatbotApp._pre_activate 注入）----
    _bus: EventBus
    _permissions: PermissionService
    _services: ServiceRegistry
    _transport: Transport
    _data_dir: Path
    _debug: bool

    # ---- 子类可覆盖: 声明本插件提供的服务 ----
    # 格式: {"service.name": None | "attr_name" | SomeType | instance}
    provides: ClassVar[dict[str, Any]] = {}

    # ==================== 生命周期（异步入口） ====================
    #
    # 调用顺序（由 IntegrationLayer 编排）: 
    #   init(同步) → activate(同步) → on_load → [装配: 事件订阅 + 命令注册] → on_enable
    #   停用: on_disable → [取消后台任务] → [拆卸: 退订/注销] → on_unload → deactivate(同步)
    #
    # 这四个钩子可以安全地 await 权限检查 / 服务查询 / 事件发布。

    async def on_load(self) -> None:
        """已加载并完成配置注入；此时尚未订阅事件 / 注册命令。"""

    async def on_enable(self) -> None:
        """已订阅事件并注册命令，插件正式生效。适合启动后台任务。"""

    async def on_disable(self) -> None:
        """即将停止接收事件（退订前）。适合收敛内部状态。"""

    async def on_unload(self) -> None:
        """已退订并注销命令 / 服务，即将卸载。适合释放外部资源。"""

    # ==================== 后台任务（过渡版作用域） ====================

    def create_task(self, coro: Any, *, name: str | None = None) -> asyncio.Task:
        """创建随插件停用而取消的后台任务（M3 起并入 ``PluginScope``）。

        需在运行中的事件循环里调用（如 ``on_enable`` 或事件处理器）。
        """
        task = asyncio.ensure_future(coro)
        if name:
            task.set_name(f"{self.name}:{name}")
        registry = self._task_registry()
        registry.add(task)
        task.add_done_callback(registry.discard)
        return task

    async def cancel_tasks(self) -> None:
        """取消并等待全部后台任务（由框架在 ``on_disable`` 之后调用）。"""
        tasks = [task for task in self._task_registry() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _task_registry(self) -> set[asyncio.Task]:
        registry = getattr(self, "_tasks", None)
        if registry is None:
            registry = set()
            self._tasks = registry
        return registry

    # ---- 便捷: 日志 ----
    @property
    def log(self) -> logging.Logger:
        return logging.getLogger(f"plugin.{self.name}")

    # ---- 便捷: 事件 ----
    async def publish(self, name: str, data: Any = None, **metadata: Any) -> None:
        await self._bus.publish(
            Event(name=name, data=data, source=self.name, metadata=metadata)
        )

    # ---- 调试 ----
    @property
    def debug(self) -> bool:
        return self._debug

    # ==================== 权限 ====================
    #
    # 两个层次:
    #   · 原语:   has_permission(user_id, node, ctx)   —— 平台无关
    #   · 事件感知: has_permission_for(event, node)     —— 翻译器由 event.source 决定

    # ---- 节点名补全 ----

    def _node(self, node: str) -> str:
        """补全权限节点: 不含点时自动加插件名前缀（"use" → "echo.use"）。"""
        return node if "." in node else f"{self.name}.{node}"

    # ---- 原语 ----

    async def has_permission(
        self,
        user_id: str,
        node: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """权限检查（原语）。主体与上下文由调用方显式提供。

        需要从事件推导主体/上下文时，请使用 :meth:`has_permission_for`。
        """
        return await self._permissions.has_permission(
            str(user_id),
            self._node(node),
            context=dict(context) if context else None,
        )

    async def has_any_permission(
        self,
        user_id: str,
        nodes: Iterable[str],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """任一节点通过即返回 True（短路）。"""
        for node in nodes:
            if await self.has_permission(user_id, node, context=context):
                return True
        return False

    async def has_all_permissions(
        self,
        user_id: str,
        nodes: Iterable[str],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """全部节点通过才返回 True（短路）。"""
        for node in nodes:
            if not await self.has_permission(user_id, node, context=context):
                return False
        return True

    # ---- 事件感知: 翻译器由 event.source 决定 ----

    def _translator_for(self, event: Event) -> EventTranslator | None:
        """查找事件来源对应的翻译器。

        约定：适配器在 ``f"{source}.translator"`` 服务名下注册一个
        :class:`EventTranslator`。找不到时返回 None——调用方据此拒绝。
        """
        service_name = f"{event.source}.translator"
        translator = self._services.resolve(service_name)
        if translator is None:
            self.log.warning(
                "事件来源 %r 未注册权限翻译器（期望服务 %r）；本次检查拒绝",
                event.source, service_name,
            )
        return translator

    def _resolve_event(
        self,
        event: Event,
        extra_context: Mapping[str, Any] | None,
    ) -> tuple[str, dict[str, Any]] | None:
        """事件 → ``(主体, 上下文)`` 的统一解析。

        返回 None 表示无法判定主体（无翻译器 / 翻译器返回 None）——
        调用方应立即拒绝，而非误放行。
        """
        translator = self._translator_for(event)
        if translator is None:
            return None
        subject = translator.permission_subject(event)
        if not subject:
            return None
        context = dict(translator.permission_context(event))
        if extra_context:
            context.update(extra_context)
        return subject, context

    async def has_permission_for(
        self,
        event: Event,
        node: str,
        *,
        extra_context: Mapping[str, Any] | None = None,
    ) -> bool:
        """**事件感知**的权限检查。

        业务插件最常见的用法::

            if not await self.has_permission_for(event, "use"):
                return

        ``extra_context`` 可补充 / 覆盖本次检查的上下文（如 ``{"world": "nether"}``）。
        """
        resolved = self._resolve_event(event, extra_context)
        if resolved is None:
            return False
        subject, context = resolved
        return await self.has_permission(subject, node, context=context)

    async def has_any_permission_for(
        self,
        event: Event,
        nodes: Iterable[str],
        *,
        extra_context: Mapping[str, Any] | None = None,
    ) -> bool:
        """**事件感知**的"任一"检查。"""
        resolved = self._resolve_event(event, extra_context)
        if resolved is None:
            return False
        subject, context = resolved
        return await self.has_any_permission(subject, nodes, context=context)

    async def has_all_permissions_for(
        self,
        event: Event,
        nodes: Iterable[str],
        *,
        extra_context: Mapping[str, Any] | None = None,
    ) -> bool:
        """**事件感知**的"全部"检查。"""
        resolved = self._resolve_event(event, extra_context)
        if resolved is None:
            return False
        subject, context = resolved
        return await self.has_all_permissions(subject, nodes, context=context)

    # ---- 元数据查询 ----

    async def get_groups(self, user_id: str) -> list[str]:
        """用户所属组列表；后端不支持时返回空列表。"""
        return await self._permissions.get_groups(str(user_id))

    async def get_prefix(self, user_id: str) -> str:
        """用户前缀（约定俗成的 ``meta["prefix"]``）；无则空字符串。"""
        return (await self._permissions.get_meta(str(user_id), "prefix")) or ""

    async def get_meta(self, user_id: str, key: str) -> str | None:
        """任意用户元数据。"""
        return await self._permissions.get_meta(str(user_id), key)

    # ---- 便捷: 服务 ----

    def get_service(self, name: str) -> Any | None:
        """宽松查询: 不存在返回 None。"""
        return self._services.resolve(name)

    def require_service(self, name: str) -> Any:
        """严格查询: 不存在抛 ServiceNotFound。"""
        return self._services.require(name)

    async def wait_for_service(
        self, name: str, *, timeout: float | None = None
    ) -> Any:
        """异步等待服务注册。用于无法静态声明依赖的场景。"""
        return await self._services.wait_for(name, timeout=timeout)

    @property
    def data_dir(self) -> Path:
        """当前插件的专属可写数据目录。"""
        return self._data_dir

    def get_data_path(self, *parts: str) -> Path:
        """拼出插件数据目录下的路径。"""
        return self._data_dir.joinpath(*parts)

    def ensure_data_dir(self) -> Path:
        """确保数据目录存在，并返回它。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir

    # ==================== zh ====================

    def init(self, app_config: dict[str, Any], plugin_config: dict[str, Any]) -> None:
        """在插件加载时调用。接收应用配置和插件配置。

        Args:
            app_config: 全局应用程序配置。
            plugin_config: 来自 YAML 的插件特定配置。
        """
        self.app_config = app_config
        self.config = plugin_config

    def activate(self) -> None:
        """在插件激活时调用。"""

    def deactivate(self) -> None:
        """在插件停用时调用。在此释放资源。"""

    def on_config_changed(self, old: dict[str, Any], new: dict[str, Any]) -> None:
        """当应用配置快照发生变化时，由 PluginManager.refresh_config 调用。

        默认实现为空操作。可重写以对配置变化做出反应
        （缓存失效、重新打开连接）。持有进行中工作的有状态插件
        应谨慎: 新配置适用于未来的操作，而不适用于进行中的操作。

        Args:
            old: 先前的应用配置字典。
            new: 新的应用配置字典。在调用此方法之前，
                已由管理器赋值给 self.app_config。
        """

    def get_routes(self) -> list:
        """返回要挂载的 FastAPI 路由器。可选。

        Return:
            FastAPI APIRouter 实例列表。
        """
        return []

    def get_frontend_manifest(self) -> dict[str, Any] | None:
        """返回前端 UI 组件的清单。可选。

        Return:
            前端清单字典或 None。
        """
        return None

    def health(self) -> dict[str, Any]:
        """返回插件健康状态。可选。

        可重写以检查外部依赖（API、数据库等）。

        Return:
            至少包含 "status" 键（"ok" 或 "error"）的字典。
        """
        return {"status": "ok"}

    def get_migrations_dir(self) -> str | None:
        """返回 Alembic 迁移脚本的路径。可选。

        Return:
            路径字符串，如果没有迁移则返回 None。
        """
        return None