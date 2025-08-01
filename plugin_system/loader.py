# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-03-21 18:06:59
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-29 16:38:40
# @Description  : 插件加载器
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from __future__ import annotations
import asyncio
import importlib
import importlib.util
import os
import sys
import pkg_resources
from collections import defaultdict, deque
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterable, List, Optional, Set, Tuple, Type, Union

from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version
from logging import getLogger

from .abc import CompatibleHandler
from .base_plugin import BasePlugin
from .event import EventBus
from .pip_tool import PipTool
from .pluginsys_err import (
    PluginCircularDependencyError,
    PluginDependencyError,
    PluginVersionError,
    PluginNameConflictError,
)
from .api import PluginSysApi
from .config import config

LOG = getLogger("PluginLoader")
_PLUGINS_DIR = config.plugins_dir
_PIP_TOOL = PipTool() if config.auto_install_pip_pack else None


# ---------------------------------------------------------------------------
# 工具函数 / 小类
# ---------------------------------------------------------------------------
class _ModuleImporter:
    """把「目录->模块对象」的细节收敛到这里，方便做单元测试。"""

    def __init__(self, directory: str, pip_tool: Optional[PipTool]):
        self.directory = Path(directory).resolve()
        self.pip_tool = pip_tool

    def load_all(self) -> Dict[str, ModuleType]:
        """返回 {插件名: 模块对象}。"""
        modules: Dict[str, ModuleType] = {}
        if not self.directory.exists():
            return modules

        original_path = [*sys.path]
        try:
            sys.path.insert(0, str(self.directory))
            for entry in self.directory.iterdir():
                if entry.is_dir() and (entry / "__init__.py").exists():
                    name, path = entry.name, entry
                elif entry.suffix == ".py":
                    name, path = entry.stem, entry
                else:
                    continue

                self._maybe_install_deps(path)
                modules[name] = self._import_single(name, path)
        finally:
            sys.path[:] = original_path
        return modules

    # ------------------------------------------------------------------
    # 私有
    # ------------------------------------------------------------------
    def _import_single(self, name: str, path: Path) -> ModuleType:
        try:
            if path.is_dir():
                return importlib.import_module(name)
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            LOG.info("成功导入插件模块: %s", name)
            return module
        except Exception as e:
            LOG.error("导入模块 %s 时出错: %s", name, e)
            raise

    def _maybe_install_deps(self, plugin_path: Path) -> None:
        if not self.pip_tool:
            return
        req_file = (
            plugin_path / "requirements.txt"
            if plugin_path.is_dir()
            else plugin_path.with_suffix(".requirements.txt")
        )
        if not req_file.exists():
            return

        for line in req_file.read_text(encoding="utf-8").splitlines():
            req = line.strip()
            if not req or req.startswith("#") or req.startswith("-"):
                continue
            self._ensure_package(req)

    def _ensure_package(self, req: str) -> None:
        """检查包是否存在，不存在则安装。"""
        try:
            # 尝试解析requirement字符串
            requirement = pkg_resources.Requirement.parse(req)
            
            # 检查包是否已安装
            pkg_resources.working_set.find(requirement)
            # LOG.info("依赖包已存在: %s", req)
            
        except pkg_resources.VersionConflict:
            LOG.warning("依赖包版本冲突，尝试更新: %s", req)
            self.pip_tool.install(req)
            
        except pkg_resources.DistributionNotFound:
            LOG.info("开始安装缺失的依赖: %s", req)
            self.pip_tool.install(req)


class _DependencyResolver:
    """把「依赖图 -> 加载顺序」的逻辑独立出来，方便测试。"""

    def __init__(self) -> None:
        self._graph: Dict[str, Set[str]] = {}
        self._constraints: Dict[str, Dict[str, str]] = {}

    def build(self, plugin_classes: Iterable[Type[BasePlugin]]) -> None:
        self._graph.clear()
        self._constraints.clear()
        for cls in plugin_classes:
            self._graph[cls.name] = set(cls.dependencies.keys())
            self._constraints[cls.name] = cls.dependencies.copy()

    def resolve(self) -> List[str]:
        """返回按依赖排序后的插件名；出错抛异常。"""
        self._check_duplicate_names()
        in_degree = {k: 0 for k in self._graph}
        adj = defaultdict(list)
        for cur, deps in self._graph.items():
            for d in deps:
                adj[d].append(cur)
                in_degree[cur] += 1

        q = deque([k for k, v in in_degree.items() if v == 0])
        order = []
        while q:
            cur = q.popleft()
            order.append(cur)
            for nxt in adj[cur]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    q.append(nxt)

        if len(order) != len(self._graph):
            raise PluginCircularDependencyError(set(self._graph) - set(order))
        return order

    # ------------------------------------------------------------------
    # 私有
    # ------------------------------------------------------------------
    def _check_duplicate_names(self) -> None:
        seen = set()
        for name in self._graph:
            if name in seen:
                raise PluginNameConflictError(name)
            seen.add(name)


# ---------------------------------------------------------------------------
# 主加载器
# ---------------------------------------------------------------------------
class PluginLoader:
    """插件加载器：负责插件的加载、卸载、重载、生命周期管理。"""

    def __init__(self, event_bus: EventBus, *, debug: bool = False) -> None:
        self.plugins: Dict[str, BasePlugin] = {}
        self.event_bus = event_bus or EventBus()
        self.sys_api = PluginSysApi(self)
        self._debug = debug
        self._resolver = _DependencyResolver()

        if debug:
            LOG.warning("插件系统已切换为调试模式")

    # -------------------- 对外 API --------------------
    async def from_class_load_plugins(
        self, plugin_classes: List[Type[BasePlugin]], **kwargs
    ) -> None:
        """从「插件类对象」加载。"""
        valid_classes = [cls for cls in plugin_classes if self._is_valid(cls)]
        self._resolver.build(valid_classes)

        load_order = self._resolver.resolve()
        temp = {}
        for name in load_order:
            cls = next(c for c in valid_classes if c.name == name)
            LOG.info("加载插件「%s」", name)
            temp[name] = cls(
                event_bus=self.event_bus,
                debug=self._debug,
                sys_api=self.sys_api,
                **kwargs,
            )

        self.plugins = temp
        self._validate_versions()
        await asyncio.gather(*(p.__onload__() for p in self.plugins.values()))

    async def load_plugins(self, plugins_path: str = _PLUGINS_DIR, **kwargs) -> None:
        """从目录批量加载。"""
        path = Path(plugins_path or _PLUGINS_DIR).resolve()
        if not path.exists():
            LOG.info("插件目录: %s 不存在……跳过加载插件", path)
            return

        LOG.info("从 %s 导入插件", path)
        importer = _ModuleImporter(str(path), _PIP_TOOL)
        modules = importer.load_all()

        plugin_classes: List[Type[BasePlugin]] = []
        for mod in modules.values():
            for cls_name in getattr(mod, "__all__", []):
                cls = getattr(mod, cls_name)
                if self._is_valid(cls):
                    plugin_classes.append(cls)

        await self.from_class_load_plugins(plugin_classes, **kwargs)
        LOG.info("已加载插件数 [%d]", len(self.plugins))
        self._load_compatible_data()

    async def unload_plugin(self, name: str, **kwargs) -> bool:
        """卸载单个插件。"""
        plugin = self.plugins.get(name)
        if not plugin:
            LOG.warning("插件 '%s' 未加载，无法卸载", name)
            return False
        try:
            await plugin.__unload__(**kwargs)
            del self.plugins[name]
            return True
        except Exception as e:
            LOG.error("卸载插件 '%s' 时发生错误: %s", name, e)
            return False

    async def reload_plugin(self, name: str, **kwargs) -> bool:
        """重载单个插件。"""
        try:
            old = self.plugins.get(name)
            if old and not await self.unload_plugin(name):
                return False

            module_name = old.__class__.__module__ if old else self._guess_module(name)
            module = importlib.import_module(module_name)
            importlib.reload(module)

            cls = self._find_plugin_class_in_module(module, name)
            if not cls:
                LOG.error("在模块中未找到插件 '%s'", name)
                return False

            new = cls(
                event_bus=self.event_bus,
                debug=self._debug,
                sys_api=self.sys_api,
                **kwargs,
            )
            await new.__onload__()
            self.plugins[name] = new
            LOG.info("插件 '%s' 重载成功", name)
            return True
        except Exception as e:
            LOG.error("重载插件 '%s' 失败: %s", name, e)
            return False

    def unload_all(self, **kwargs) -> None:
        """一键卸载全部插件。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                asyncio.gather(
                    *(self.unload_plugin(n, **kwargs) for n in self.plugins.keys())
                )
            )
        finally:
            loop.close()

    # -------------------- 查询 API --------------------
    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self.plugins.get(name)

    def get_metadata(self, name: str) -> dict:
        return self.plugins[name].meta_data

    def list_plugins(self, *, obj: bool = False) -> List[Union[str, BasePlugin]]:
        return list(self.plugins.values()) if obj else list(self.plugins.keys())

    # -------------------- 私有辅助 --------------------
    @staticmethod
    def _is_valid(cls: Type[BasePlugin]) -> bool:
        return all(hasattr(cls, attr) for attr in ("name", "version", "dependencies"))

    def _validate_versions(self) -> None:
        """检查已加载插件的版本约束。"""
        for plugin_name, constraints in self._resolver._constraints.items():
            for dep_name, constraint in constraints.items():
                dep = self.plugins.get(dep_name)
                if not dep:
                    raise PluginDependencyError(plugin_name, dep_name, constraint)
                if not SpecifierSet(constraint).contains(parse_version(dep.version)):
                    raise PluginVersionError(
                        plugin_name, dep_name, constraint, dep.version
                    )

    def _load_compatible_data(self) -> None:
        """运行兼容处理器。"""
        for plugin in self.plugins.values():
            for _, func in _iter_callables(plugin):
                for handler in CompatibleHandler._subclasses:
                    if handler.check(func):
                        handler.handle(plugin, func, self.event_bus)

    def _guess_module(self, plugin_name: str) -> str:
        """根据插件名猜模块名；简单实现，如有需要可扩展。"""
        for entry in Path(_PLUGINS_DIR).iterdir():
            if entry.name == plugin_name:
                return entry.stem
        raise ValueError(f"无法定位插件 {plugin_name} 的模块")

    def _find_plugin_class_in_module(
        self, module: ModuleType, plugin_name: str
    ) -> Optional[Type[BasePlugin]]:
        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BasePlugin)
                and getattr(obj, "name", None) == plugin_name
            ):
                return obj
        return None


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _iter_callables(obj):
    """遍历对象的所有可调用成员。"""
    for attr in dir(obj):
        value = getattr(obj, attr)
        if callable(value):
            yield attr, value