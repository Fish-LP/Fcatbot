"""权限服务: 协议 + 内置实现（含 luckperms-python 真实适配）。

设计目标
--------
- **协议极小**: :class:`PermissionService` 只有 3 个方法——接一个新后端，
  最少实现 ``has_permission``，其余有默认值可用；
- **事件翻译独立**: :class:`EventTranslator` 是适配器与权限世界之间的桥，
  单独成协议，与后端协议互不依赖；
- **故障不击穿业务**: 后端查询异常 → 日志 + 安全默认值（False / 空）；
- 权限节点命名约定: ``{plugin_name}.{feature}.{action}``（如 ``echo.use``）。

内置后端
--------
- :class:`NullPermissionService`    — 全部拒绝（默认关权限时的安全选择）；
- :class:`AllowAllPermissionService`— 全部放行（开发 / 演示用）；
- :class:`LuckPermsAdapter`         — 对接 ``luckperms-python``
  （组 / 通配符 / 上下文 / 临时权限 / 控制台身份）。

后端选择由 ``config/app.yaml`` 的 ``permissions.backend`` 决定（见 ``FcatbotApp._build_permissions``）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Protocol, runtime_checkable

if TYPE_CHECKING:
    from luckperms import LuckPermsManager

    from fcatbot.kernel.events import Event

log = logging.getLogger("fcatbot.permissions")


# =====================================================================
# 事件翻译协议: 适配器与权限世界之间的桥
# =====================================================================


@runtime_checkable
class EventTranslator(Protocol):
    """把一个平台事件翻译成权限系统需要的主体与上下文。

    适配器实现本协议，并通过服务注册表对外提供（推荐服务名
    ``f"translator.{source}"``）。业务插件与基类都不直接依赖它——基类按
    ``event.source`` 查找，业务插件通过 ``has_permission_for`` 间接使用。

    翻译器是**纯函数**：
    - 不查询权限后端、不做权限判断；
    - 不知道 :class:`PermissionService` 存在；
    - 只做一件事：输入事件，输出 ``(主体 ID, 上下文字典)``。
    """

    def permission_subject(self, event: "Event") -> str | None:
        """返回事件主体 ID；返回 None 表示无法判定（调用方直接拒绝）。"""
        ...

    def permission_context(self, event: "Event") -> Mapping[str, Any]:
        """返回事件对应的权限上下文。

        空字典表示"本次检查不带上下文"——是合法值，不是错误。
        返回值会原样传给 ``PermissionService.has_permission(context=...)``。
        """
        ...


# =====================================================================
# 后端协议: 一个权限后端必须提供的最小能力
# =====================================================================


class PermissionService(Protocol):
    """权限服务协议。

    业务插件**不直接依赖**本协议的任何实现——它们通过
    :class:`~fcatbot.plugin.base.FcatbotPlugin` 暴露的便捷方法访问权限。

    自定义后端推荐继承 :class:`BasePermissionService`——它把可选方法的默认值
    都准备好了，实现者只需提供 :meth:`has_permission`。
    """

    async def has_permission(
        self,
        user_id: str,
        node: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """判断 ``user_id`` 是否拥有 ``node``；``context`` 是后端定义的上下文维度。"""
        ...

    async def get_groups(self, user_id: str) -> list[str]:
        """返回用户所属组名列表（继承展开与否由后端决定）。无此概念时返回空列表。"""
        ...

    async def get_meta(self, user_id: str, key: str) -> str | None:
        """返回用户的元数据（如 ``"prefix"``、``"suffix"``）；不存在返回 None。"""
        ...


# =====================================================================
# 便利基类: 自定义后端只需要实现 has_permission
# =====================================================================


class BasePermissionService:
    """权限服务便利基类。

    自定义后端继承本类后，**只需实现** :meth:`has_permission`。
    :meth:`get_groups` / :meth:`get_meta` 的默认返回（空列表 / None）对绝大多数
    简单后端已经足够；需要时覆盖即可。
    """

    async def has_permission(
        self,
        user_id: str,
        node: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        raise NotImplementedError

    async def get_groups(self, user_id: str) -> list[str]:
        return []

    async def get_meta(self, user_id: str, key: str) -> str | None:
        return None


# =====================================================================
# 内置实现
# =====================================================================


class NullPermissionService(BasePermissionService):
    """全部拒绝。用于显式关闭权限系统的场景。"""

    async def has_permission(self, user_id, node, *, context=None) -> bool:
        return False


class AllowAllPermissionService(BasePermissionService):
    """全部放行。用于开发 / 演示；生产环境请替换为 :class:`LuckPermsAdapter`。"""

    async def has_permission(self, user_id, node, *, context=None) -> bool:
        return True


class LuckPermsAdapter(BasePermissionService):
    """luckperms-python 权限服务适配器（真实接入）。

    对接 `luckperms-python <https://github.com/Fish-LP/LuckPerms-Python>`_
    （``luckperms`` 包，**同步实现**）；本类提供 async 门面以符合
    :class:`PermissionService` 协议。

    **线程模型**（重点）
    -------------------
    ``luckperms-python`` 的每次写操作末尾都会触发 ``_save_all()``——全量序列化
    + 磁盘写。因此：

    - 所有对底层 ``manager`` 的调用都通过 :func:`asyncio.to_thread` 丢进线程池，
      绝不阻塞事件循环；
    - 所有**写操作**（以及缓存失效）通过 :attr:`_write_lock` 串行化，
      避免 ``_save_all`` 期间的内存快照互相踩；
    - 读操作并发执行，但底层 ``check`` 会创建临时 ``User`` 对象，属于纯内存操作，
      不加锁也安全。

    **缓存**
    --------
    ``has_permission`` 结果按 ``(user_id, node, frozenset(context))`` 做 TTL 缓存
    （默认 5 秒）。任何写操作会清空缓存。高频消息路径下收益显著。

    **启动期预检**
    --------------
    :meth:`preflight` 会强制触发底层加载。调用方（``FcatbotApp._build_permissions``）
    应在启动时调用它，让"库没装 / 数据目录不可写"在启动期就暴露，而不是第一次
    权限检查时静默全拒。

    语义要点（与底层库一致）:

    - **游客继承**: 未持久化的用户自动继承 ``default`` 组权限（适合"未注册用户"场景）；
    - **通配符**: ``plugin.*``（单段）/ ``server.**``（多段），显式拒绝可覆盖通配；
    - **上下文敏感**: ``context={"group_id": "123456"}`` 等维度；
    - **用户唯一 ID**: 直接使用聊天平台用户 ID 字符串（如 QQ 号），无需映射。

    工程约定:

    - ``luckperms`` 为**软依赖**（延迟导入）: 未安装时仅影响本适配器；
    - 所有查询异常转为日志 + 安全默认值（False / 空），权限故障不击穿业务；
    - **控制台身份**: ``console_user``（默认 ``console``）在引导时自动创建并保留 ``*``
      节点；:meth:`has_permission` 对该身份直接放行——本地控制台拥有全部权限
      （ADR-0013 语义）；
    - :attr:`manager` 暴露底层 ``LuckPermsManager``，供管理命令 / WebUI 做 CRUD
      （授予节点、加组、上下文、临时权限、轨道晋升等）。**这些 CRUD 是同步的**，
      调用方若在 async 上下文里使用，请自行 ``to_thread`` + 复用 :attr:`write_lock`；
      或者优先使用本类提供的 :meth:`grant_node` / :meth:`revoke_node` /
      :meth:`add_group` / :meth:`remove_group` 等 async 包装方法。
    """

    #: 缓存条目存活秒数；<= 0 表示禁用缓存
    CACHE_TTL: float = 5.0
    #: 缓存条目数上限（粗粒度保护，避免内存无界增长）
    CACHE_MAXSIZE: int = 4096

    def __init__(
        self,
        data_dir: str | Path,
        *,
        default_group: str | None = "default",
        console_user: str | None = "console",
        bootstrap: bool = True,
        cache_ttl: float | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._default_group = default_group
        self._console_user = console_user
        self._bootstrap = bootstrap
        self._manager: "LuckPermsManager | None" = None

        # 写操作串行锁（懒创建，绑定到当前事件循环）
        self._write_lock: asyncio.Lock | None = None
        # 缓存: key -> (expire_ts, value)
        self._cache: dict[tuple, tuple[float, bool]] = {}
        self._cache_ttl = self.CACHE_TTL if cache_ttl is None else float(cache_ttl)

    # ---------- 内部辅助 ----------

    def _get_write_lock(self) -> asyncio.Lock:
        """懒创建写锁（必须在事件循环内调用）。"""
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()
        return self._write_lock

    @property
    def write_lock(self) -> asyncio.Lock:
        """暴露给外部管理命令使用的写锁（保证与适配器内部串行化一致）。"""
        return self._get_write_lock()

    @staticmethod
    def _cache_key(
        user_id: str,
        node: str,
        context: Mapping[str, Any] | None,
    ) -> tuple:
        if not context:
            return (user_id, node, ())
        # 排序保证不同插入顺序的等价 context 命中同一条目
        items = tuple(sorted((str(k), repr(v)) for k, v in context.items()))
        return (user_id, node, items)

    def _cache_get(self, key: tuple) -> bool | None:
        if self._cache_ttl <= 0:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        expire_at, value = entry
        if expire_at < time.monotonic():
            self._cache.pop(key, None)
            return None
        return value

    def _cache_put(self, key: tuple, value: bool) -> None:
        if self._cache_ttl <= 0:
            return
        if len(self._cache) >= self.CACHE_MAXSIZE:
            # 粗粒度淘汰：清空最旧的一半
            now = time.monotonic()
            alive = {k: v for k, v in self._cache.items() if v[0] >= now}
            if len(alive) >= self.CACHE_MAXSIZE:
                # 全都没过期，直接清掉一半
                self._cache.clear()
            else:
                self._cache = alive
        self._cache[key] = (time.monotonic() + self._cache_ttl, value)

    def _invalidate_cache(self) -> None:
        self._cache.clear()

    def _ensure_console_identity(self, manager: "LuckPermsManager") -> None:
        """同步实现：确保控制台用户存在且持有 ``*``。"""
        uid = self._console_user
        if not uid:
            return
        uid = str(uid)
        if manager.get_user(uid) is None:
            manager.create_user(uid, "Console")
            log.info("luckperms: 已创建控制台用户 '%s'（%s）", uid, self._data_dir)
        user = manager.get_user(uid)
        if user is None:  # pragma: no cover
            return
        if not any(
            node.key == "*" and node.value and not node.context for node in user.nodes
        ):
            manager.user_add_node(uid, "*", True, None)
            log.info("luckperms: 已确保控制台用户 '%s' 拥有全部权限（*）", uid)

    def _load_manager_sync(self) -> "LuckPermsManager":
        """同步实现：导入 + 构造 + 引导。只在 to_thread 里调用。"""
        try:
            from luckperms import LuckPermsManager
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "luckperms-python 未安装，无法使用 luckperms 权限后端: "
                "pip install luckperms-python"
            ) from exc

        manager = LuckPermsManager(self._data_dir)
        if self._bootstrap:
            self._ensure_default_group(manager)
            self._ensure_console_identity(manager)
        log.info(
            "luckperms 已加载: data_dir=%s users=%d groups=%d",
            self._data_dir,
            len(manager.list_users()),
            len(manager.list_groups()),
        )
        return manager

    # ---------- 底层访问 ----------

    @property
    def manager(self) -> "LuckPermsManager":
        """底层 ``LuckPermsManager``（懒加载；首次访问时引导 default 组与控制台身份）。

        注意：底层 API 是**同步的**。在 async 代码里请优先使用本类提供的
        async 包装方法，或自行 ``await asyncio.to_thread(...)``。
        """
        if self._manager is None:
            self._manager = self._load_manager_sync()
        return self._manager

    async def preflight(self) -> None:
        """启动期预检：强制触发底层加载与引导。

        推荐在 ``FcatbotApp._build_permissions`` 中调用，让配置错误在启动期
        暴露。若底层不可用，本方法会抛出异常，由调用方决定是否降级。
        """
        async with self._get_write_lock():
            if self._manager is None:
                self._manager = await asyncio.to_thread(self._load_manager_sync)

    @property
    def console_user(self) -> str | None:
        """控制台身份的用户 ID（None 表示未启用）。"""
        return self._console_user

    def _ensure_default_group(self, manager: "LuckPermsManager") -> None:
        name = self._default_group
        if not name or manager.get_group(name) is not None:
            return
        manager.create_group(name, "默认组", weight=0)
        log.info("luckperms: 已创建默认组 '%s'（%s）", name, self._data_dir)

    # ---------- PermissionService ----------

    async def has_permission(
        self,
        user_id: str,
        node: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        uid = str(user_id)
        node_s = str(node)

        # 控制台身份全放行（ADR-0013），不进缓存
        if self._console_user and uid == str(self._console_user):
            return True

        key = self._cache_key(uid, node_s, context)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        try:
            manager = await asyncio.to_thread(lambda: self.manager)
            ctx = dict(context) if context else None
            result = bool(await asyncio.to_thread(manager.check, uid, node_s, ctx))
        except Exception:
            log.exception("luckperms 权限检查失败: user=%s node=%s", uid, node_s)
            # 失败结果不缓存，避免瞬态故障被放大成 TTL 窗口
            return False

        self._cache_put(key, result)
        return result

    async def get_groups(self, user_id: str) -> list[str]:
        uid = str(user_id)
        try:
            manager = await asyncio.to_thread(lambda: self.manager)
            user = await asyncio.to_thread(manager.get_user, uid)
            if user is not None:
                return sorted(user.parents)
            # 与 has_permission 语义一致: 游客继承 default 组
            default = self._default_group
            if default:
                group = await asyncio.to_thread(manager.get_group, default)
                if group is not None:
                    return [default]
            return []
        except Exception:
            log.exception("luckperms get_groups 失败: user=%s", uid)
            return []

    async def get_meta(self, user_id: str, key: str) -> str | None:
        """返回用户元数据，**沿父组继承展开**（与 ``check`` 语义一致）。

        查找顺序：用户自身 → 深度优先遍历 ``parents``（用户组 + 组的组）。
        第一个命中的值返回；都没有则 None。
        """
        uid = str(user_id)
        key_s = str(key)

        def _resolve() -> str | None:
            manager = self.manager
            user = manager.get_user(uid)
            if user is None:
                # 游客：只能从 default 组继承
                if not self._default_group:
                    return None
                group = manager.get_group(self._default_group)
                if group is None:
                    return None
                return group.get_meta(key_s)

            # 1. 用户自身
            value = user.get_meta(key_s)
            if value is not None:
                return value

            # 2. BFS 遍历父组
            visited: set[str] = set()
            queue = list(user.parents)
            while queue:
                gname = queue.pop(0)
                if gname in visited:
                    continue
                visited.add(gname)
                group = manager.get_group(gname)
                if group is None:
                    continue
                value = group.get_meta(key_s)
                if value is not None:
                    return value
                queue.extend(group.parents)
            return None

        try:
            return await asyncio.to_thread(_resolve)
        except Exception:
            log.exception("luckperms get_meta 失败: user=%s key=%s", uid, key_s)
            return None

    # ---------- 写操作 async 包装（供管理命令 / WebUI 使用） ----------
    # 这些方法统一: to_thread + write_lock + 缓存失效。

    async def grant_node(
        self,
        user_id: str,
        node: str,
        value: bool = True,
        *,
        context: Mapping[str, Any] | None = None,
        duration: int | None = None,
    ) -> None:
        """给用户授予（或显式拒绝）一个节点。``duration`` 为秒。"""
        uid = str(user_id)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(
                manager.user_add_node,
                uid,
                str(node),
                bool(value),
                dict(context) if context else None,
                duration,
            )
            self._invalidate_cache()

    async def revoke_node(
        self,
        user_id: str,
        node: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """移除用户上的节点。返回是否确实删除了某条。"""
        uid = str(user_id)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            removed = await asyncio.to_thread(
                manager.user_remove_node,
                uid,
                str(node),
                dict(context) if context else None,
            )
            self._invalidate_cache()
            return bool(removed)

    async def add_group(self, user_id: str, group_name: str) -> None:
        """把用户加入一个组。"""
        uid = str(user_id)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.user_add_group, uid, str(group_name))
            self._invalidate_cache()

    async def remove_group(self, user_id: str, group_name: str) -> None:
        """把用户从一个组移除。"""
        uid = str(user_id)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.user_remove_group, uid, str(group_name))
            self._invalidate_cache()

    async def create_user(
        self,
        user_id: str,
        display_name: str | None = None,
    ) -> None:
        """显式创建一个持久化用户（会带上 default 组）。"""
        uid = str(user_id)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.create_user, uid, display_name)
            self._invalidate_cache()
