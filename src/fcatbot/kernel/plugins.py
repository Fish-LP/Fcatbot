"""Fcatbot 插件基类。

本基类横跨两套独立调度的生命周期系统。请先理解"对称性"这一核心结构，
再看具体钩子。

────────────────────────────────────────────────────────────────
双架构总览
────────────────────────────────────────────────────────────────

插件由两个系统共同驱动，两条链**互不等待、职责正交**：

┌─ PluginForge 层（同步，pluggy 钩子链）─────────────────────┐
│  钩子: init / activate / deactivate / on_config_changed     │
│  调度: PluginManager                                        │
│  为何同步: pluggy 的钩子链本身不支持 await。                │
└─────────────────────────────────────────────────────────────┘
┌─ Fcatbot 层（异步，本类声明）──────────────────────────────┐
│  钩子: on_load / on_enable / on_disable / on_unload         │
│  调度: IntegrationLayer（由 FcatbotApp 编排）               │
│  为何异步: 权限查询 / 服务等待 / 异步连接都必须 await。     │
└─────────────────────────────────────────────────────────────┘

────────────────────────────────────────────────────────────────
对称性（重要，先看这张表）
────────────────────────────────────────────────────────────────

**Fcatbot 层内部是对称的**——四个钩子按插件"是否已装配"的状态镜像：

    状态               进入侧              离开侧
    ───────────────────────────────────────────────
    detached(未订阅)   on_load      ←→    on_unload
    attached(已订阅)   on_enable    ←→    on_disable
    装配动作           attach       ←→    detach

**PluginForge 层内部不对称**——进入 3 步、离开 1 步：

    进入:  _pre_activate → init → activate
    离开:  deactivate

    不对称是刻意的：Fcatbot 把大部分"准备"职责迁到了异步层，
    同步层只保留最小必要的装配 / 反注册。

**跨层时间序是镜像的**——进入"同步→异步"，离开"异步→同步"：

    进入:  [同步 _pre_activate/init/activate]  →  [异步 on_load/attach/on_enable]
    离开:  [异步 on_disable/cancel/detach/on_unload]  →  [同步 deactivate]

    离开时异步先跑，是为了让异步清理看到"活着的"事件订阅与命令。

────────────────────────────────────────────────────────────────
完整时间线（由 FcatbotApp 编排）
────────────────────────────────────────────────────────────────

**启动（FcatbotApp.run）** —— 与运行时启用的序列完全一致::

    # ── 同步侧 ──
    _pre_activate(plugin)     # 注入 _bus/_permissions/_services/...
                              # 注册 provides 声明的服务
    init(app_config, cfg)     # 配置注入（子类应在此解析 config）
    activate()                # 空实现；异步初始化请放 on_load/on_enable

    # ── 异步侧 ──
    on_load()                 # 服务已注册，事件尚未订阅
    attach()                  # 扫描 __event_specs__ 订阅事件
                              # 扫描命令声明注册命令
    on_enable()               # 事件/命令已生效，可启动后台任务

**停用（FcatbotApp.disable_plugin）**::

    # ── 异步侧 ──
    on_disable()              # 事件仍有效；收敛状态，勿启动新任务
    cancel_tasks()            # 取消 create_task 建的任务（框架自动调用）
    detach()                  # 退订事件 + 注销命令 + 注销服务
    on_unload()               # 已退订；最终持久化、释放外部资源

    # ── 同步侧 ──
    deactivate()              # 纯同步最终释放

**重载（FcatbotApp.reload_plugin）**::

    disable 序列 → PluginManager 重新导入 + 实例化 → enable 序列

**运行时启用（FcatbotApp.enable_plugin）**::

    与启动序列相同——每次启用都是全新实例，init 会重跑。

────────────────────────────────────────────────────────────────
钩子速查：各自看到的"世界"
────────────────────────────────────────────────────────────────

    ┌────────────┬────────┬──────────┬──────────────────────────┐
    │ 钩子        │ 同步?  │ 已装配?  │ 典型用途                 │
    ├────────────┼────────┼──────────┼──────────────────────────┤
    │ init       │  是    │ 服务已注册│ 解析配置（纯同步）       │
    │ activate   │  是    │ 同上      │ 几乎不用                 │
    │ on_load    │  否    │ 未订阅    │ 打开连接、预热、一次性校验│
    │ on_enable  │  否    │ 已订阅    │ 启动后台任务              │
    │ on_disable │  否    │ 仍订阅    │ 刷盘、向下线通知          │
    │ on_unload  │  否    │ 已退订    │ 最终持久化、关句柄        │
    │ deactivate │  是    │ 全清完成  │ 关闭同步句柄              │
    └────────────┴────────┴──────────┴──────────────────────────┘

────────────────────────────────────────────────────────────────
使用注意
────────────────────────────────────────────────────────────────

· **不要直接调** ``IntegrationLayer.enable/disable`` 或
  ``PluginManager.activate_plugin/deactivate_plugin``。前者绕过服务注册与
  ``init`` / ``activate``；后者不碰事件订阅/命令注册，停用后会残留资源。
  统一走 :meth:`FcatbotApp.enable_plugin` / :meth:`disable_plugin` /
  :meth:`reload_plugin`。

· **插件的 name 是类属性**（如 ``"NapcatAdapter"``），与插件目录名无关。
  查找、启停、重载都以 name 为准。

· **运行时启用是全新实例**。每次 ``cls()`` 都重新构造，``init`` 也会重跑，
  不要假设实例字段在停用/启用之间存活。

· **失败隔离**：钩子抛异常会被 :meth:`IntegrationLayer._run_hook` 捕获并
  记日志，不会中断其他插件。因此**不要依赖"钩子失败会整体回滚"**——
  重要状态收敛请显式写在 ``on_disable`` 里。

  各失败点的语义::

      on_load 失败     → 不 attach、不跑 on_enable
      on_enable 失败   → detach 回滚已完成的装配
      on_disable 失败  → 中止拆卸，保留已挂载状态
      on_unload 失败   → 仅记日志（拆卸已执行，无法回滚）

· **异步钩子里可以安全 await**：权限检查、服务查询、事件发布。
  同步钩子里**不要** ``run_until_complete``——事件循环通常已在运行，
  会直接抛 :class:`RuntimeError`。

────────────────────────────────────────────────────────────────
持久化工具
────────────────────────────────────────────────────────────────

插件不需要自己写 YAML/JSON 读写。两件工具，各管一件事：

· :class:`~src.protocol.data.PluginConfig`
    —— 用户可编辑的配置（强 schema、禁动态字段、支持版本迁移）。
    多数情况下**只用它的校验能力**：框架已把 YAML 解析成 dict 通过
    ``init(app_config, plugin_config)`` 交给你，用
    ``MyConfig.model_validate(plugin_config or {})`` 变成强类型对象即可，
    **不要**再 ``bind()`` 到同一份 YAML，否则会出现两份真相。

· :class:`~src.protocol.data.PluginData`
    —— 运行时状态（声明字段 + 任意动态字段）。绑定到本插件专属目录::

        self.state = (
            PluginData()
            .set_backend(JSONBackend())
            .set_name("state")                # → state.json
            .bind(self.ensure_data_dir())     # 目录已存在，追加文件名
        )
        self.state.tick_count = 0             # 动态字段，随便加
        self.state.save()                     # 落盘

    典型时机::

        init()         → MyConfig.model_validate(plugin_config or {})
        on_load()      → PluginData().bind(self.ensure_data_dir())
        on_disable()   → self.state.save()    # 最后能可靠收事件的机会
        on_unload()    → 最终持久化

    注意：``self.data_dir`` **未必存在**；绑定前先 ``self.ensure_data_dir()``，
    否则 ``bind()`` 会把不存在的目录当成文件，生成 ``.../echo.json`` 这种路径。
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
    """所有 Fcatbot 插件的基类。

    直接继承本类并实现需要的异步生命周期钩子即可；无需手动订阅/退订事件——
    :class:`IntegrationLayer` 会依据插件类上的 ``__event_specs__`` 与命令声明
    完成装配。

    ── 生命周期一句话概括 ─────────────────────────────────────

        进入:  同步 (init/activate)  →  异步 (on_load → attach → on_enable)
        离开:  异步 (on_disable → cancel_tasks → detach → on_unload)
                                     →  同步 (deactivate)

    **异步四钩子按状态镜像对称**：

        on_load     ←→  on_unload      （detached：事件未订阅）
        on_enable   ←→  on_disable     （attached：事件已订阅）

    完整时间线、失败语义、各钩子用途见模块 docstring。

    ── 一个方法订阅多个事件 ──────────────────────────────────

    同一方法可叠加多个 :func:`~fcatbot.kernel.decorators.on_event` 订阅多个事件::

        @on_event("napcat.message.group")
        @on_event("napcat.message.private")
        async def on_message(self, event) -> None:
            ...

    ── 最小示例 ─────────────────────────────────────────────

    ::

        from fcatbot.kernel.events import Event

        class EchoPlugin(FcatbotPlugin):
            name = "echo"

            async def on_load(self) -> None:
                # 同步侧已就绪：配置已注入，服务已注册
                # 事件尚未订阅 —— 适合打开文件/连接、做一次性校验
                self.log.info("echo: data_dir = %s", self.data_dir)

            async def on_enable(self) -> None:
                # 事件/命令已装配 —— 适合启动后台任务
                self.create_task(self._poll_loop(), name="poll")

            async def on_disable(self) -> None:
                # 事件仍有效 —— 收敛状态，勿在此启动新任务
                await self.publish("echo.stopping")

            async def on_unload(self) -> None:
                # 已退订/注销 —— 释放外部资源
                pass

            async def _poll_loop(self) -> None:
                while True:
                    await asyncio.sleep(60)
                    await self.publish("echo.tick")

    ── provides 声明格式 ─────────────────────────────────────

    ::

        provides = {
            "myplugin.cache": None,            # 注册 self 自身
            "myplugin.store": "_store",        # 注册 self._store
            "myplugin.api": MyApi,             # 类型标注（不参与运行时）
            "myplugin.raw": some_instance,     # 直接注册该实例
        }

    注册发生在 ``_pre_activate``（即 ``init`` 之前、``on_load`` 之前）；
    注销发生在 ``detach``（即 ``on_unload`` 之前）。
    """

    # ==================== 类型声明（运行时由 FcatbotApp._pre_activate 注入）====================
    #
    # 这些属性在插件被装配之前不存在；声明它们是为了：
    #   · IDE 补全 / 类型检查通过；
    #   · 提醒子类"这些字段不要自己赋值"。
    # 未装配就访问会抛 AttributeError —— 这是刻意的，便于尽早发现问题。
    _bus: EventBus
    _permissions: PermissionService
    _services: ServiceRegistry
    _transport: Transport | None
    _data_dir: Path
    _config_file: Path
    _debug: bool

    # 由 create_task 惰性初始化的任务集合；插件停用时由 cancel_tasks 清空。
    _tasks: set[asyncio.Task]

    # ==================== 由 init() 注入 ====================
    #
    # 装配阶段被赋值；子类应通过 self.config / self.app_config 读取。
    # 每次运行时启用都会重跑 init（全新实例），因此可以放心在 init 里做
    # 纯同步的配置解析；异步副作用请放到 on_load / on_enable。
    app_config: dict[str, Any]
    config: Any
    default_config: dict[str, Any]
    # 如果设置了 `default_config` 而没有 `config_schema` 会自动生成简单的单层模式 `config_schema`

    # 目标主机标识：PluginForge 用它区分不同宿主的插件。
    target_application = "fcatbot"

    # ==================== 子类可覆盖：provides ====================
    #
    # 格式: {"service.name": None | "attr_name" | SomeType | instance}
    #   · None         → 注册 self 自身
    #   · str          → 注册 self.<attr_name>
    #   · type         → 仅作文档/类型标注，不参与运行时
    #   · 其他实例      → 直接注册该实例
    #
    # 注册发生在 _pre_activate（即 init 之前、on_load 之前）；
    # 注销发生在 detach（即 on_unload 之前）。
    provides: ClassVar[dict[str, Any]] = {}

    def __init__(self) -> None:
        super().__init__()
        if hasattr(self, "default_config") and not hasattr(self, "config_schema"):
            self.config_schema = {k: type(v) for k, v in self.default_config.items()}

    # ==================== 异步侧 · 生命周期钩子 ====================
    #
    # 下面四个钩子按状态镜像对称：
    #
    #     on_load     ←→  on_unload      （detached：事件未订阅）
    #     on_enable   ←→  on_disable     （attached：事件已订阅）
    #
    # 抛异常由 IntegrationLayer._run_hook 捕获；失败隔离是设计意图。
    # 因此不要依赖"钩子失败会整体回滚"——重要状态收敛请在 on_disable 里做。
    #
    # 这四钩子可以安全地 await 权限检查 / 服务查询 / 事件发布。

    async def on_load(self) -> None:
        """已加载并完成配置注入；此时尚未订阅事件 / 注册命令。

        已具备的条件：

        - :attr:`_bus` / :attr:`_permissions` / :attr:`_services` /
          :attr:`_transport` / :attr:`_data_dir` / :attr:`_debug` 均已注入；
        - :attr:`app_config` / :attr:`config` 已由 :meth:`init` 赋值；
        - 本插件的 ``provides`` 服务已注册（其他插件可查询到）。

        适合：打开文件、建立连接、做一次性校验、预热缓存。
        不适合：启动后台任务（此时还未订阅事件，任务可能错过首帧）——
        后台任务放 :meth:`on_enable`。
        """

    async def on_enable(self) -> None:
        """已订阅事件并注册命令，插件正式生效。适合启动后台任务。

        这是"插件可用"的起点：其他插件此时查询本插件的服务、
        向本插件订阅的事件发布事件，都会正常生效。

        若需要启动常驻协程，用 :meth:`create_task` 创建，它们会随插件停用
        自动取消（框架在 :meth:`on_disable` 之后调 :meth:`cancel_tasks`）。
        """

    async def on_disable(self) -> None:
        """即将停止接收事件（退订前）。适合收敛内部状态。

        此时事件订阅仍有效，但不要再在此处启动新的后台任务——
        紧接着框架就会调用 :meth:`cancel_tasks` 取消它们。

        适合：把内存中的状态刷到磁盘、向其他插件发送下线通知。
        """

    async def on_unload(self) -> None:
        """已退订并注销命令 / 服务，即将卸载。适合释放外部资源。

        适合做最终持久化（保存状态、关闭文件句柄、断开连接）。
        :attr:`_bus` / :attr:`_services` 仍可读，但不应再依赖其他插件的
        服务——它们的卸载顺序不由本插件控制。
        """

    # ==================== 异步侧 · 后台任务作用域 ====================

    def create_task(self, coro: Any, *, name: str | None = None) -> asyncio.Task:
        """创建随插件停用而取消的后台任务（M3 起并入 ``PluginScope``）。

        需在运行中的事件循环里调用（如 ``on_enable`` 或事件处理器）。

        Args:
            coro: 任意可 await 对象（协程、Future、Task 均可）。
            name: 任务名后缀；实际名称形如 ``f"{self.name}:{name}"``，
                便于在调试器里区分不同插件的任务。

        Returns:
            创建出的 :class:`asyncio.Task`。若调用方不关心返回值可以忽略。

        Note:
            任务完成后会自动从内部登记表移除；异常不会被吞——
            未捕获异常会记录到日志（asyncio 默认行为），如需自定义请自行
            在协程内 try/except。
        """
        task = asyncio.ensure_future(coro)
        if name:
            task.set_name(f"{self.name}:{name}")
        registry = self._task_registry()
        registry.add(task)
        # 完成后立即移出，避免登记表随运行时长无限增长。
        task.add_done_callback(registry.discard)
        return task

    async def cancel_tasks(self) -> None:
        """取消并等待全部后台任务（由框架在 ``on_disable`` 之后调用）。

        对每个未完成任务调用 :meth:`asyncio.Task.cancel`，然后
        ``gather(..., return_exceptions=True)`` 等待它们真正结束。
        任务抛出的 :class:`asyncio.CancelledError` 与业务异常都会被静默吞掉，
        以免影响主停用流程——若需要感知取消原因，请在任务内部处理。
        """
        tasks = [task for task in self._task_registry() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _task_registry(self) -> set[asyncio.Task]:
        """惰性获取/创建任务登记表（不覆盖子类可能已定义的 ``_tasks``）。"""
        registry = getattr(self, "_tasks", None)
        if registry is None:
            registry = set()
            self._tasks = registry
        return registry

    # ==================== 通用 · 便捷方法（日志 / 事件 / 调试）====================

    @property
    def log(self) -> logging.Logger:
        """本插件专属 logger，名称固定为 ``f"plugin.{self.name}"``。

        使用方式：``self.log.info("...")``。
        不要用 ``logging.getLogger(__name__)``——热重载时会丢失命名空间。
        """
        return logging.getLogger(f"plugin.{self.name}")

    async def publish(self, name: str, data: Any = None, **metadata: Any) -> None:
        """以本插件为 source 发布一个事件到事件总线。

        Args:
            name: 事件名，约定使用 ``"{plugin}.{action}"`` 形式。
            data: 事件负载，任意可 JSON 化对象（取决于总线实现）。
            **metadata: 附加元数据，用于携带不影响事件语义的上下文。
        """
        await self._bus.publish(
            Event(name=name, data=data, source=self.name, metadata=metadata)
        )

    @property
    def debug(self) -> bool:
        """当前是否处于调试模式（由应用配置注入）。"""
        return self._debug

    # ==================== 通用 · 权限（原语 + 事件感知）====================
    #
    # 两个层次：
    #   · 原语:     has_permission(user_id, node, ctx)   —— 平台无关
    #   · 事件感知: has_permission_for(event, node)      —— 翻译器由 event.source 决定
    #
    # 业务插件绝大多数场景应使用事件感知版本；原语版本适合后台任务 / 定时器
    # 等没有事件对象的场景。

    # ---- 节点名补全 ----

    def _node(self, node: str) -> str:
        """补全权限节点：不含点时自动加插件名前缀（"use" → "echo.use"）。

        这样插件内部可以只写短名，避免硬编码自身前缀。
        """
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

        Args:
            user_id: 主体标识（会强制转成 str）。
            node: 权限节点；不含点时按 :meth:`_node` 规则补全。
            context: 判定上下文（如 ``{"world": "nether"}``）。

        Returns:
            bool: 通过为 True。
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
        """任一节点通过即返回 True（短路）。

        注意：``nodes`` 为空时返回 False（"任一"的空集语义）。
        """
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
        """全部节点通过才返回 True（短路）。

        注意：``nodes`` 为空时返回 True（"全部"的空集语义）。
        """
        for node in nodes:
            if not await self.has_permission(user_id, node, context=context):
                return False
        return True

    # ---- 事件感知: 翻译器由 event.source 决定 ----

    def _translator_for(self, event: Event) -> EventTranslator | None:
        """查找事件来源对应的翻译器。

        约定：适配器在 ``f"translator.{event.source}"`` 服务名下注册一个
        :class:`EventTranslator`。找不到时返回 None——调用方据此拒绝。

        Note:
            服务名方向是 **前缀** ``translator.`` + ``event.source``，
            与模块 docstring 的示例一致。
        """
        service_name = f"translator.{event.source}"
        translator = self._services.resolve(service_name)
        if translator is None:
            self.log.warning(
                "事件来源 %r 未注册权限翻译器（期望服务 %r）；本次检查拒绝",
                event.source,
                service_name,
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

        ``extra_context`` 会覆盖翻译器给出的同名键，便于调用方就地补充
        语义（如把默认的 ``world=overworld`` 覆写为 ``nether``）。
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

        Args:
            event: 触发本次检查的事件；其 ``source`` 决定使用哪个翻译器。
            node: 权限节点；短名会自动加插件前缀。
            extra_context: 补充 / 覆盖本次检查的上下文
                （如 ``{"world": "nether"}``）。

        Returns:
            bool: 通过为 True；无翻译器或无法判定主体时为 False。
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
        """**事件感知**的"任一"检查。无翻译器 / 无法判定主体时返回 False。"""
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
        """**事件感知**的"全部"检查。无翻译器 / 无法判定主体时返回 False。"""
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
        """用户前缀（约定俗成的 ``meta["prefix"]``）；无则空字符串。

        这是**跨插件约定**：不要在 ``on_load`` 之前依赖某个特定后端一定返回它。
        """
        return (await self._permissions.get_meta(str(user_id), "prefix")) or ""

    async def get_meta(self, user_id: str, key: str) -> str | None:
        """任意用户元数据。键不存在时返回 None（与空字符串区分）。"""
        return await self._permissions.get_meta(str(user_id), key)

    # ==================== 通用 · 服务查询 ====================

    def get_service(self, name: str) -> Any | None:
        """宽松查询：不存在返回 None。

        适合可选依赖场景：``cache = self.get_service("cache")``，
        再用 ``if cache is not None:`` 判断。

        Note:
            本插件的 ``provides`` 声明在 ``on_load`` 时已注册到服务表，
            但**其他插件**的服务是否可用取决于它们的启用顺序——
            跨插件依赖请用 :meth:`wait_for_service`。
        """
        return self._services.resolve(name)

    def require_service(self, name: str) -> Any:
        """严格查询：不存在抛 :class:`ServiceNotFound`。

        适合必需依赖场景；异常会向上冒泡到 IntegrationLayer，
        并计入插件装配失败。
        """
        return self._services.require(name)

    async def wait_for_service(self, name: str, *, timeout: float | None = None) -> Any:
        """异步等待服务注册。用于无法静态声明依赖的场景。

        典型用法：本插件 A 需要插件 B 的服务，但 B 的加载顺序不确定::

            store = await self.wait_for_service("b.store", timeout=5.0)

        Args:
            name: 服务名。
            timeout: 秒；None 表示无限等待（慎用，可能导致 ``on_enable`` 卡死）。

        Raises:
            asyncio.TimeoutError: 超时仍未注册。
        """
        return await self._services.wait_for(name, timeout=timeout)

    # ==================== 通用 · 数据目录 ====================

    @property
    def data_dir(self) -> Path:
        """当前插件的专属可写数据目录。

        由 ``FcatbotApp._pre_activate`` 按插件名分配，形如
        ``<app_config.plugins.data_dir>/plugins/<safe_name>/``，
        其中 ``safe_name`` 是插件 ``name`` 去掉不安全字符后的结果。

        目录**未必已存在**，写入前请用 :meth:`ensure_data_dir` 或自行 mkdir。
        """
        return self._data_dir

    def get_data_path(self, *parts: str) -> Path:
        """拼出插件数据目录下的路径。

        仅做拼接，不创建目录、不检查存在性。
        """
        return self._data_dir.joinpath(*parts)

    def ensure_data_dir(self) -> Path:
        """确保数据目录存在，并返回它。

        相当于 ``self.data_dir.mkdir(parents=True, exist_ok=True)`` 的快捷方式。
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir

    # ==================== 同步侧 · PluginForge 钩子 ====================
    #
    # 以下方法来自 PluginForge 的同步钩子链。异步逻辑请写在上面四个钩子
    # （on_load / on_enable / on_disable / on_unload）里，不要在同步钩子中
    # run_until_complete——事件循环通常已在运行，会直接抛 RuntimeError。
    #
    # 调用时机（由 FcatbotApp._enable_plugin_locked / run 触发）：
    #     _pre_activate → init → activate → …… → deactivate
    # 注：_pre_activate 由 FcatbotApp 提供，先于 init 完成依赖注入与服务注册。

    def init(self, app_config: dict[str, Any], plugin_config: dict[str, Any]) -> None:
        """在插件加载时调用。接收应用配置和插件配置。

        Args:
            app_config: 全局应用程序配置。
            plugin_config: 来自 YAML 的插件特定配置。

        Note:
            纯同步赋值即可；异步初始化放 :meth:`on_load`。
            运行时每次启用都会重跑本方法（全新实例），
            配置解析可以放心放在这里。
        """
        self.app_config = app_config
        self.config = plugin_config

    def activate(self) -> None:
        """在插件激活时调用。

        同步入口；需要 await 的初始化请放到 :meth:`on_load` / :meth:`on_enable`。

        Note:
            此时 :attr:`_bus` / :attr:`_permissions` / :attr:`_services` 已注入，
            本插件的 ``provides`` 服务也已注册（在 ``_pre_activate`` 里完成）。
            但事件订阅与命令注册尚未发生——请勿在此发布"我上线了"的事件，
            其他插件可能还没准备好。
        """

    def deactivate(self) -> None:
        """在插件停用时调用。在此释放资源。

        同步入口；需要 await 的清理请放到 :meth:`on_disable` / :meth:`on_unload`。

        Note:
            本方法的调用在异步清理（``on_disable`` / ``cancel_tasks`` /
            ``detach`` / ``on_unload``）**之后**，
            此时事件已退订、命令已注销、服务已注销、后台任务已取消。
            这里只适合做纯同步的最终释放（如关闭一个同步句柄）。
        """

    def on_config_changed(self, old: dict[str, Any], new: dict[str, Any]) -> None:
        """当应用配置快照发生变化时，由 ``PluginManager.refresh_config`` 调用。

        默认实现为空操作。可重写以对配置变化做出反应
        （缓存失效、重新打开连接）。持有进行中工作的有状态插件
        应谨慎：新配置适用于未来的操作，而不适用于进行中的操作。

        Args:
            old: 先前的应用配置字典。
            new: 新的应用配置字典。在调用此方法之前，
                已由管理器赋值给 ``self.app_config``。
        """

    # ==================== 可选 · Web / 前端 / 健康检查 / 迁移 ====================

    def get_routes(self) -> list:
        """返回要挂载的 FastAPI 路由器。可选。

        Returns:
            FastAPI ``APIRouter`` 实例列表；无路由时返回空列表。
        """
        return []

    def get_frontend_manifest(self) -> dict[str, Any] | None:
        """返回前端 UI 组件的清单。可选。

        Returns:
            前端清单字典；无前端时返回 None。
        """
        return None

    def health(self) -> dict[str, Any]:
        """返回插件健康状态。可选。

        可重写以检查外部依赖（API、数据库等）。
        返回的字典至少要包含 ``"status"`` 键，取值为 ``"ok"`` 或 ``"error"``。

        Returns:
            健康状态字典，至少包含 ``{"status": "ok"}``。
        """
        return {"status": "ok"}

    def get_migrations_dir(self) -> str | None:
        """返回 Alembic 迁移脚本的路径。可选。

        Returns:
            路径字符串；如果没有迁移则返回 None。
        """
        return None
