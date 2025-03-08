# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-11 17:26:43
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-08 23:05:26
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
import importlib
import asyncio
import os
import sys
from collections import defaultdict, deque
from types import ModuleType, MethodType
from typing import Dict, List, Set, Type

from packaging.specifiers import SpecifierSet
from packaging.version import parse as parse_version

from .custom_err import (
    PluginCircularDependencyError,
    PluginDependencyError,
    PluginVersionError,
)
from .base_plugin import BasePlugin
from .event import EventBus
from .compatible import CompatibleEnrollment
from ..config import PLUGINS_DIR, META_CONFIG_PATH
from ..utils import get_log
from ..utils import UniversalDataIO
from ..utils import PipTool

PM = PipTool()
LOG = get_log('PluginLoader')

class PluginLoader:
    """
    插件加载器,用于加载、卸载和管理插件
    """

    def __init__(self, event_bus: EventBus):
        """
        初始化插件加载器
        """
        self.plugins: Dict[str, BasePlugin] = {}  # 存储已加载的插件
        self.event_bus = event_bus  # 事件总线
        self._dependency_graph: Dict[str, Set[str]] = {}  # 插件依赖关系图
        self._version_constraints: Dict[str, Dict[str, str]] = {}  # 插件版本约束
        if META_CONFIG_PATH:
            self.meta_data = UniversalDataIO(META_CONFIG_PATH)
        else:
            self.meta_data = {}

    def _validate_plugin(self, plugin_cls: Type[BasePlugin]) -> bool:
        """
        验证插件类是否符合规范
        """
        return all(
            hasattr(plugin_cls, attr) for attr in ("name", "version", "dependencies")
        )

    def _build_dependency_graph(self, plugins: List[Type[BasePlugin]]):
        """
        构建插件依赖关系图
        """
        self._dependency_graph.clear()
        self._version_constraints.clear()

        for plugin in plugins:
            self._dependency_graph[plugin.name] = set(plugin.dependencies.keys())
            self._version_constraints[plugin.name] = plugin.dependencies.copy()

    def _validate_dependencies(self):
        """
        验证插件依赖关系是否满足
        """
        for plugin_name, deps in self._version_constraints.items():
            for dep_name, constraint in deps.items():
                if dep_name not in self.plugins:
                    raise PluginDependencyError(plugin_name, dep_name, constraint)

                installed_ver = parse_version(self.plugins[dep_name].version)
                if not SpecifierSet(constraint).contains(installed_ver):
                    raise PluginVersionError(
                        plugin_name, dep_name, constraint, installed_ver
                    )

    def _resolve_load_order(self) -> List[str]:
        """
        解析插件加载顺序,确保依赖关系正确
        """
        in_degree = {k: 0 for k in self._dependency_graph}
        adj_list = defaultdict(list)

        for dependent, dependencies in self._dependency_graph.items():
            for dep in dependencies:
                adj_list[dep].append(dependent)
                in_degree[dependent] += 1

        queue = deque([k for k, v in in_degree.items() if v == 0])
        load_order = []

        while queue:
            node = queue.popleft()
            load_order.append(node)
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(load_order) != len(self._dependency_graph):
            missing = set(self._dependency_graph.keys()) - set(load_order)
            raise PluginCircularDependencyError(missing)

        return load_order

    async def from_class_load_plugins(self, plugins: List[Type[BasePlugin]], **kwargs):
        """
        从插件类加载插件
        :param plugins: 插件类列表
        """
        valid_plugins = [p for p in plugins if self._validate_plugin(p)]
        self._build_dependency_graph(valid_plugins)
        load_order = self._resolve_load_order()

        temp_plugins = {}
        for name in load_order:
            plugin_cls = next(p for p in valid_plugins if p.name == name)
            temp_plugins[name] = plugin_cls(self.event_bus, meta_data = self.meta_data.copy(), **kwargs)

        self.plugins = temp_plugins
        self._validate_dependencies()

        for name in load_order:
            await self.plugins[name].__onload__()

    async def load_plugins(self, plugins_path: str = PLUGINS_DIR, **kwargs):
        """
        从指定目录加载插件
        :param plugins_path: 插件目录路径
        """
        if not plugins_path: plugins_path = PLUGINS_DIR
        modules = self._load_modules_from_directory(plugins_path)
        plugins = []
        for plugin in modules.values():
            for plugin_class_name in getattr(plugin, "__all__", []):
                plugins.append(getattr(plugin, plugin_class_name))
        await self.from_class_load_plugins(plugins, **kwargs)
        self.load_compatible_data()

    def load_compatible_data(self):
        """
        加载兼容注册事件
        """
        compatible = CompatibleEnrollment.events
        for event_type, packs in compatible.items():
            for func, priority, in_class in packs:
                if in_class:
                    for plugin_name, plugin in self.plugins.items():
                        if plugin.__class__.__qualname__ == func.__qualname__.split('.')[0]:
                            func = MethodType(func, plugin)
                            self.event_bus.subscribe(event_type, func, priority)
                            break
                else:
                    self.event_bus.subscribe(event_type, func, priority)

    async def unload_plugin(self, plugin_name: str):
        """
        卸载插件
        :param plugin_name: 插件名称
        """
        if plugin_name not in self.plugins:
            return

        await self.plugins[plugin_name].__unload__()
        del self.plugins[plugin_name]

    async def reload_plugin(self, plugin_name: str):
        """
        重新加载插件
        :param plugin_name: 插件名称
        """
        if plugin_name not in self.plugins:
            raise ValueError(f"插件 '{plugin_name}' 未加载")

        old_plugin = self.plugins[plugin_name]
        await self.unload_plugin(plugin_name)

        module = importlib.import_module(old_plugin.__class__.__module__)
        # 如果模块有依赖项，这些依赖项不会自动重新加载
        importlib.reload(module)

        new_cls = getattr(module, old_plugin.__class__.__name__)
        new_plugin = new_cls(self.event_bus)
        new_plugin._init_()
        await new_plugin.on_load()
        self.plugins[plugin_name] = new_plugin

    def _load_modules_from_directory(
        self, directory_path: str
    ) -> Dict[str, ModuleType]:
        """
        从指定文件夹动态加载模块，返回模块名到模块的字典。
        不修改 `sys.path`，仅在必要时临时添加路径。
        """
        modules = {}
        original_sys_path = sys.path.copy()
        all_install = {pack['name'] for pack in PM.list_installed() if 'name' in pack}

        try:
            directory_path = os.path.abspath(directory_path)
            sys.path.append(directory_path)

            for filename in os.listdir(directory_path):
                if not os.path.isdir(os.path.join(directory_path, filename)):
                    continue
                if os.path.isfile(os.path.join(directory_path, filename, "requirements.txt")):
                    requirements = {open(os.path.join(directory_path, filename, "requirements.txt")).readlines()}
                    if all_install <= requirements:
                        download = requirements - requirements
                        for pack in download:
                            PM.install(pack)

                try:
                    module = importlib.import_module(filename)
                    modules[filename] = module
                except ImportError as e:
                    LOG.error(f"导入模块 {filename} 时出错: {e}")
                    continue

        finally:
            sys.path = original_sys_path

        return modules

    def unload_all(self, *arg, **kwd):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            tasks = [self.unload_plugin(plugin) for plugin in self.plugins.keys()]
            loop.run_until_complete(asyncio.gather(*tasks))
        finally:
            loop.close()