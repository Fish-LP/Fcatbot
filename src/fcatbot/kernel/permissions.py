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
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Protocol, runtime_checkable

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
    """luckperms-python 权限服务适配器（对齐真实后端 API）。

    适配对象是本仓库内嵌的 :class:`luckperms.LuckPermsManager`（同步实现）。
    本类只做三件事：丢线程池、串行化写、TTL 缓存。

    **线程模型**
    - 所有 manager 调用走 :func:`asyncio.to_thread`，不阻塞事件循环；
    - 所有写操作（含缓存失效）经 :attr:`_write_lock` 串行化；
    - 读操作并发执行（底层 ``check`` 会创建临时 User，纯内存）。

    **缓存**：``has_permission`` 按 ``(user_id, node, frozenset(context))`` 做 TTL
    缓存；任何写操作清空缓存。

    **与后端的对应关系**
    - 用户节点：``user_add_node`` / ``user_remove_node``（后者返回是否删除）
    - 组节点：``group_add_node`` / ``group_remove_node``（**无 duration**）
    - 组继承：``group_inherit`` / ``group_remove_inherit``
    - 轨道：``promote`` / ``demote``
    - Web Editor：``to_webeditor_payload`` / ``apply_webeditor_changes``

    **后端没有的能力**（本类不提供空壳接口）
    - meta 写入（无 ``user_set_meta`` / ``group_set_meta``）——只有模型层的
      ``get_meta`` 可读；
    - 组节点的 ``duration``；
    - 批量事务。
    """

    #: 缓存条目存活秒数；<= 0 表示禁用
    CACHE_TTL: float = 5.0
    #: 缓存条目数上限
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

        self._write_lock: asyncio.Lock | None = None
        self._cache: dict[tuple, tuple[float, bool]] = {}
        self._cache_ttl = self.CACHE_TTL if cache_ttl is None else float(cache_ttl)

    # ---------- 内部辅助 ----------

    def _get_write_lock(self) -> asyncio.Lock:
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()
        return self._write_lock

    @property
    def write_lock(self) -> asyncio.Lock:
        """暴露给外部管理命令复用的写锁。"""
        return self._get_write_lock()

    @staticmethod
    def _cache_key(
        user_id: str,
        node: str,
        context: Mapping[str, Any] | None,
    ) -> tuple:
        if not context:
            return (user_id, node, ())
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
            now = time.monotonic()
            alive = {k: v for k, v in self._cache.items() if v[0] >= now}
            if len(alive) >= self.CACHE_MAXSIZE:
                self._cache.clear()
            else:
                self._cache = alive
        self._cache[key] = (time.monotonic() + self._cache_ttl, value)

    def _invalidate_cache(self) -> None:
        self._cache.clear()

    def _ensure_console_identity(self, manager: "LuckPermsManager") -> None:
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

    def _ensure_default_group(self, manager: "LuckPermsManager") -> None:
        name = self._default_group
        if not name or manager.get_group(name) is not None:
            return
        manager.create_group(name, "默认组", weight=0)
        log.info("luckperms: 已创建默认组 '%s'（%s）", name, self._data_dir)

    def _load_manager_sync(self) -> "LuckPermsManager":
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
            "luckperms 已加载: data_dir=%s users=%d groups=%d tracks=%d",
            self._data_dir,
            len(manager.list_users()),
            len(manager.list_groups()),
            len(manager.list_tracks()),
        )
        return manager

    # ---------- 底层访问 ----------

    @property
    def manager(self) -> "LuckPermsManager":
        """底层 ``LuckPermsManager``（懒加载 + 引导）。同步对象，async 里请用包装方法。"""
        if self._manager is None:
            self._manager = self._load_manager_sync()
        return self._manager

    async def preflight(self) -> None:
        """启动期预检：强制加载底层，让配置 / 依赖问题在启动期暴露。"""
        async with self._get_write_lock():
            if self._manager is None:
                self._manager = await asyncio.to_thread(self._load_manager_sync)

    @property
    def console_user(self) -> str | None:
        return self._console_user

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
            return False  # 失败结果不缓存

        self._cache_put(key, result)
        return result

    async def get_groups(self, user_id: str) -> list[str]:
        uid = str(user_id)
        try:
            manager = await asyncio.to_thread(lambda: self.manager)
            user = await asyncio.to_thread(manager.get_user, uid)
            if user is not None:
                return sorted(user.parents)
            # 游客继承 default 组（与 check 语义一致）
            if self._default_group:
                group = await asyncio.to_thread(manager.get_group, self._default_group)
                if group is not None:
                    return [self._default_group]
            return []
        except Exception:
            log.exception("luckperms get_groups 失败: user=%s", uid)
            return []

    async def get_meta(self, user_id: str, key: str) -> str | None:
        """用户元数据，沿父组 BFS 展开。"""
        uid = str(user_id)
        key_s = str(key)

        def _resolve() -> str | None:
            manager = self.manager
            user = manager.get_user(uid)
            if user is None:
                if not self._default_group:
                    return None
                group = manager.get_group(self._default_group)
                return group.get_meta(key_s) if group is not None else None

            value = user.get_meta(key_s)
            if value is not None:
                return value

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

    # ---------- 用户节点写操作 ----------

    async def grant_node(
        self,
        user_id: str,
        node: str,
        value: bool = True,
        *,
        context: Mapping[str, Any] | None = None,
        duration: int | None = None,
    ) -> None:
        """给用户授予（或显式拒绝）一个节点。``duration`` 为秒；``None`` 表示永久。"""
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

    async def grant_nodes(
        self,
        user_id: str,
        nodes: Iterable[str],
        value: bool = True,
        *,
        context: Mapping[str, Any] | None = None,
        duration: int | None = None,
    ) -> None:
        """批量授予多个节点。单次写锁内完成；后端每次 add 仍会触发 ``_save_all``。"""
        uid = str(user_id)
        node_list = [str(n) for n in nodes]
        if not node_list:
            return
        ctx = dict(context) if context else None
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            for n in node_list:
                await asyncio.to_thread(
                    manager.user_add_node, uid, n, bool(value), ctx, duration
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

    # ---------- 用户 / 组归属 ----------

    async def add_group(self, user_id: str, group_name: str) -> None:
        """把用户加入一个组。后端要求组存在，否则 ``KeyError``。"""
        uid = str(user_id)
        gname = str(group_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.user_add_group, uid, gname)
            self._invalidate_cache()

    async def remove_group(self, user_id: str, group_name: str) -> None:
        """把用户从一个组移除。"""
        uid = str(user_id)
        gname = str(group_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.user_remove_group, uid, gname)
            self._invalidate_cache()

    # ---------- 用户 CRUD ----------

    async def create_user(
        self,
        user_id: str,
        display_name: str | None = None,
    ) -> None:
        """创建一个持久化用户（自动带 default 组）。已存在时静默返回。"""
        uid = str(user_id)

        def _do(manager: "LuckPermsManager") -> None:
            if manager.get_user(uid) is not None:
                return
            manager.create_user(uid, display_name)

        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(_do, manager)
            self._invalidate_cache()

    async def delete_user(self, user_id: str) -> bool:
        """删除一个持久化用户。返回是否确实删除了。"""
        uid = str(user_id)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            removed = await asyncio.to_thread(manager.delete_user, uid)
            self._invalidate_cache()
            return bool(removed)

    async def list_user_nodes(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户**自身**持有的节点（不含继承，不展开通配，不含过期）。"""
        uid = str(user_id)

        def _collect() -> list[dict[str, Any]]:
            user = self.manager.get_user(uid)
            if user is None:
                return []
            return [
                {
                    "node": n.key,
                    "value": bool(n.value),
                    "context": dict(n.context) if n.context else None,
                    "expiry": n.expiry,
                }
                for n in user.nodes
                if not n.is_expired()
            ]

        try:
            return await asyncio.to_thread(_collect)
        except Exception:
            log.exception("luckperms list_user_nodes 失败: user=%s", uid)
            return []

    # ---------- 组 CRUD ----------

    async def create_group(
        self,
        name: str,
        display_name: str | None = None,
        *,
        weight: int = 0,
    ) -> None:
        """创建一个组。已存在时静默返回。"""
        gname = str(name)

        def _do(manager: "LuckPermsManager") -> None:
            if manager.get_group(gname) is not None:
                return
            manager.create_group(gname, display_name or gname, weight=int(weight))

        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(_do, manager)
            self._invalidate_cache()

    async def delete_group(self, name: str) -> bool:
        """删除一个组。后端会自动清理用户/组/轨道对它的引用。"""
        gname = str(name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            removed = await asyncio.to_thread(manager.delete_group, gname)
            self._invalidate_cache()
            return bool(removed)

    # ---------- 组节点写操作 ----------

    async def grant_group_node(
        self,
        group_name: str,
        node: str,
        value: bool = True,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """给组授予（或显式拒绝）一个节点。

        .. note:: 后端 ``group_add_node`` **不支持 duration**——组节点永久有效。
        """
        gname = str(group_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(
                manager.group_add_node,
                gname,
                str(node),
                bool(value),
                dict(context) if context else None,
            )
            self._invalidate_cache()

    async def revoke_group_node(
        self,
        group_name: str,
        node: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """移除组上的节点。返回是否确实删除了某条。"""
        gname = str(group_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            removed = await asyncio.to_thread(
                manager.group_remove_node,
                gname,
                str(node),
                dict(context) if context else None,
            )
            self._invalidate_cache()
            return bool(removed)

    async def list_group_nodes(self, group_name: str) -> list[dict[str, Any]]:
        """列出组**自身**持有的节点（不含继承，不展开通配，不含过期）。"""
        gname = str(group_name)

        def _collect() -> list[dict[str, Any]]:
            group = self.manager.get_group(gname)
            if group is None:
                return []
            return [
                {
                    "node": n.key,
                    "value": bool(n.value),
                    "context": dict(n.context) if n.context else None,
                    "expiry": n.expiry,
                }
                for n in group.nodes
                if not n.is_expired()
            ]

        try:
            return await asyncio.to_thread(_collect)
        except Exception:
            log.exception("luckperms list_group_nodes 失败: group=%s", gname)
            return []

    # ---------- 组继承（后端命名: group_inherit / group_remove_inherit） ----------

    async def group_inherit(self, group_name: str, parent_name: str) -> None:
        """让组继承另一个组。后端会做循环检测，成环抛 ``ValueError``。"""
        gname = str(group_name)
        pname = str(parent_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.group_inherit, gname, pname)
            self._invalidate_cache()

    async def group_uninherit(self, group_name: str, parent_name: str) -> None:
        """解除组的父级继承。后端不检查存在性，重复解除是安全的。"""
        gname = str(group_name)
        pname = str(parent_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.group_remove_inherit, gname, pname)
            self._invalidate_cache()

    # ---------- 只读清单（注意后端返回对象，不是字符串） ----------

    async def list_users(self) -> list[str]:
        """返回所有持久化用户 ID（不含隐式游客）。"""
        try:
            manager = await asyncio.to_thread(lambda: self.manager)
            users = await asyncio.to_thread(manager.list_users)
            return [u.unique_id for u in users]
        except Exception:
            log.exception("luckperms list_users 失败")
            return []

    async def list_groups(self) -> list[str]:
        """返回所有组名。"""
        try:
            manager = await asyncio.to_thread(lambda: self.manager)
            groups = await asyncio.to_thread(manager.list_groups)
            return [g.name for g in groups]
        except Exception:
            log.exception("luckperms list_groups 失败")
            return []

    async def list_tracks(self) -> list[str]:
        """返回所有轨道名。"""
        try:
            manager = await asyncio.to_thread(lambda: self.manager)
            tracks = await asyncio.to_thread(manager.list_tracks)
            return [t.name for t in tracks]
        except Exception:
            log.exception("luckperms list_tracks 失败")
            return []

    # ---------- Track（晋升轨道） ----------

    async def create_track(
        self,
        name: str,
        groups: Iterable[str] | None = None,
    ) -> None:
        """创建一条轨道。已存在时静默返回。"""
        tname = str(name)
        glist = [str(g) for g in (groups or [])]

        def _do(manager: "LuckPermsManager") -> None:
            if manager.get_track(tname) is not None:
                return
            manager.create_track(tname, glist)

        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(_do, manager)
            self._invalidate_cache()

    async def delete_track(self, name: str) -> bool:
        """删除一条轨道。返回是否确实删除了。"""
        tname = str(name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            removed = await asyncio.to_thread(manager.delete_track, tname)
            self._invalidate_cache()
            return bool(removed)

    async def promote(self, user_id: str, track_name: str) -> str | None:
        """沿轨道晋升一级。返回新组名；无法晋升返回 None。"""
        uid = str(user_id)
        tname = str(track_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            result = await asyncio.to_thread(manager.promote, uid, tname)
            self._invalidate_cache()
            return result

    async def demote(self, user_id: str, track_name: str) -> str | None:
        """沿轨道降一级。返回新组名；无法降级返回 None。"""
        uid = str(user_id)
        tname = str(track_name)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            result = await asyncio.to_thread(manager.demote, uid, tname)
            self._invalidate_cache()
            return result

    # ---------- Web Editor ----------

    async def export_webeditor_payload(self) -> dict[str, Any]:
        """导出官方 Web Editor 兼容 payload。"""
        try:
            manager = await asyncio.to_thread(lambda: self.manager)
            return await asyncio.to_thread(manager.to_webeditor_payload)
        except Exception:
            log.exception("luckperms export_webeditor_payload 失败")
            return {}

    async def apply_webeditor_payload(self, payload: Mapping[str, Any]) -> None:
        """应用 Web Editor 返回的 payload（全量或增量格式均可）。"""
        data = dict(payload)
        async with self._get_write_lock():
            manager = await asyncio.to_thread(lambda: self.manager)
            await asyncio.to_thread(manager.apply_webeditor_changes, data)
            self._invalidate_cache()
