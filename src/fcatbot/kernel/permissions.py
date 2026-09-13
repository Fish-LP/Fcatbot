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

import logging
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
    ``f"{source}.translator"``）。业务插件与基类都不直接依赖它——基类按
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
    （``luckperms`` 包，同步实现）；本类提供 async 门面以符合 :class:`PermissionService` 协议。

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
      （授予节点、加组、上下文、临时权限、轨道晋升等）。
    """

    def __init__(
        self,
        data_dir: str | Path,
        *,
        default_group: str | None = "default",
        console_user: str | None = "console",
        bootstrap: bool = True,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._default_group = default_group
        self._console_user = console_user
        self._bootstrap = bootstrap
        self._manager: "LuckPermsManager | None" = None

    # ---------- 底层访问 ----------

    @property
    def manager(self) -> "LuckPermsManager":
        """底层 ``LuckPermsManager``（懒加载；首次访问时引导 default 组与控制台身份）。"""
        if self._manager is None:
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
                self._ensure_console_user(manager)
            self._manager = manager
            log.info(
                "luckperms 已加载: data_dir=%s users=%d groups=%d",
                self._data_dir,
                len(manager.list_users()),
                len(manager.list_groups()),
            )
        return self._manager

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

    def _ensure_console_user(self, manager: "LuckPermsManager") -> None:
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
        if not any(node.key == "*" and node.value and not node.context for node in user.nodes):
            manager.user_add_node(uid, "*", True, None)
            log.info("luckperms: 已确保控制台用户 '%s' 拥有全部权限（*）", uid)

    # ---------- PermissionService ----------

    async def has_permission(
        self,
        user_id: str,
        node: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        if self._console_user and str(user_id) == str(self._console_user):
            # 本地控制台拥有全部权限（ADR-0013）
            return True
        try:
            return bool(
                self.manager.check(
                    str(user_id),
                    str(node),
                    dict(context) if context else None,
                )
            )
        except Exception:
            log.exception("luckperms 权限检查失败: user=%s node=%s", user_id, node)
            return False

    async def get_groups(self, user_id: str) -> list[str]:
        try:
            user = self.manager.get_user(str(user_id))
            if user is not None:
                return list(user.parents)
            # 与 has_permission 语义一致: 游客继承 default 组
            default = self._default_group
            if default and self.manager.get_group(default) is not None:
                return [default]
            return []
        except Exception:
            log.exception("luckperms get_groups 失败: user=%s", user_id)
            return []

    async def get_meta(self, user_id: str, key: str) -> str | None:
        try:
            user = self.manager.get_user(str(user_id))
            if user is None:
                return None
            return user.get_meta(str(key))
        except Exception:
            log.exception("luckperms get_meta 失败: user=%s key=%s", user_id, key)
            return None