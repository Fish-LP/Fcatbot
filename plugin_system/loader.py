# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-11 17:26:43
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-23 21:02:34
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import asyncio
import importlib
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
from ..utils import UniversalLoader
from ..utils import PipTool
from ..utils import TimeTaskScheduler

PM = PipTool()
LOG = get_log('PluginLoader')

class PluginLoader:
    """插件加载器,用于加载、卸载和管理插件。
    
    该类负责处理插件的完整生命周期管理，包括:
    - 插件的加载和初始化
    - 插件依赖关系的管理
    - 插件的版本控制
    - 插件的热重载
    - 插件的卸载清理
    
    Attributes:
        plugins (Dict[str, BasePlugin]): 存储已加载的插件实例
        event_bus (EventBus): 用于处理插件间事件通信的事件总线
        time_task_scheduler (TimeTaskScheduler): 管理定时任务的调度器
        meta_data (dict): 插件元数据配置信息
    """

    def __init__(self, event_bus: EventBus):
        """初始化插件加载器。

        Args:
            event_bus (EventBus): 事件总线实例，用于处理插件间的事件通信
        """
        self.plugins: Dict[str, BasePlugin] = {}  # 存储已加载的插件
        self.event_bus = event_bus  # 事件总线
        self._dependency_graph: Dict[str, Set[str]] = {}  # 插件依赖关系图
        self._version_constraints: Dict[str, Dict[str, str]] = {}  # 插件版本约束
        self._debug = False  # 调试模式标记
        self.time_task_scheduler:TimeTaskScheduler = TimeTaskScheduler()
        if META_CONFIG_PATH:
            self.meta_data = UniversalLoader(META_CONFIG_PATH).load().data
        else:
            self.meta_data = {}

    def set_debug(self, debug: bool = False):
        """设置插件系统的调试模式。

        Args:
            debug (bool, optional): 是否启用调试模式。默认为 False

        Note:
            启用调试模式后会输出更详细的日志信息。
        """
        self._debug = debug
        LOG.warning("插件系统已切换为调试模式") if debug else None

    def _validate_plugin(self, plugin_cls: Type[BasePlugin]) -> bool:
        """验证插件类是否符合规范要求。

        Args:
            plugin_cls (Type[BasePlugin]): 待验证的插件类

        Returns:
            bool: 如果插件符合规范返回 True，否则返回 False
        """
        return all(
            hasattr(plugin_cls, attr) for attr in ("name", "version", "dependencies")
        )

    def _build_dependency_graph(self, plugins: List[Type[BasePlugin]]):
        """构建插件之间的依赖关系图。

        Args:
            plugins (List[Type[BasePlugin]]): 插件类列表

        Note:
            会同时更新依赖图(_dependency_graph)和版本约束(_version_constraints)
        """
        self._dependency_graph.clear()
        self._version_constraints.clear()

        for plugin in plugins:
            self._dependency_graph[plugin.name] = set(plugin.dependencies.keys())
            self._version_constraints[plugin.name] = plugin.dependencies.copy()

    def _validate_dependencies(self):
        """验证所有插件的依赖关系是否满足要求。

        Raises:
            PluginDependencyError: 当缺少某个依赖插件时抛出
            PluginVersionError: 当依赖插件的版本不满足要求时抛出
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
        """解析插件的加载顺序，确保依赖关系正确。

        Returns:
            List[str]: 按正确顺序排列的插件名称列表

        Raises:
            PluginCircularDependencyError: 当发现循环依赖时抛出
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
        """从插件类列表加载插件。

        Args:
            plugins (List[Type[BasePlugin]]): 待加载的插件类列表
            **kwargs: 传递给插件实例化的额外参数

        Raises:
            PluginDependencyError: 依赖检查失败时抛出
            PluginVersionError: 版本检查失败时抛出
        """
        valid_plugins = [p for p in plugins if self._validate_plugin(p)]
        self._build_dependency_graph(valid_plugins)
        load_order = self._resolve_load_order()

        temp_plugins = {}
        for name in load_order:
            plugin_cls = next(p for p in valid_plugins if p.name == name)
            temp_plugins[name] = plugin_cls(
                event_bus = self.event_bus,
                time_task_scheduler = self.time_task_scheduler,
                debug = self._debug,  # 传递调试模式标记 
                meta_data=self.meta_data.copy(),
                **kwargs
            )

        self.plugins = temp_plugins
        self._validate_dependencies()

        for name in load_order:
            await self.plugins[name].__onload__()

    async def load_plugins(self, plugins_path: str = PLUGINS_DIR, **kwargs):
        """从指定目录加载所有插件。

        Args:
            plugins_path (str, optional): 插件目录路径。默认为 PLUGINS_DIR
            **kwargs: 传递给插件实例化的额外参数
        """
        if not plugins_path: plugins_path = PLUGINS_DIR
        if os.path.exists(plugins_path):
            LOG.info(f"从 {os.path.abspath(plugins_path)} 导入插件")
            modules = self._load_modules_from_directory(plugins_path)
            plugins = []
            for plugin in modules.values():
                for plugin_class_name in getattr(plugin, "__all__", []):
                    plugins.append(getattr(plugin, plugin_class_name))
            LOG.info(f"准备加载插件 [{len(plugins)}]......")
            await self.from_class_load_plugins(plugins, **kwargs)
            LOG.info(f"已加载插件数 [{len(self.plugins)}]")
            LOG.info(f"准备加载兼容内容......")
            self.load_compatible_data()
            LOG.info(f"兼容内容加载成功")
        else:
            LOG.info(f"插件目录: {os.path.abspath(plugins_path)} 不存在......跳过加载插件")


    def load_compatible_data(self):
        """加载并注册兼容性事件处理函数。

        Note:
            处理使用装饰器注册的兼容性事件，并将其绑定到对应的插件实例。
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

    async def unload_plugin(self, plugin_name: str, *arg, **kwd):
        """卸载指定的插件。

        Args:
            plugin_name (str): 要卸载的插件名称
            *arg: 传递给插件卸载方法的位置参数
            **kwd: 传递给插件卸载方法的关键字参数
        """
        if plugin_name not in self.plugins:
            return

        await self.plugins[plugin_name].__unload__(*arg, **kwd)
        del self.plugins[plugin_name]

    async def reload_plugin(self, plugin_name: str):
        """重新加载指定的插件。

        Args:
            plugin_name (str): 要重新加载的插件名称

        Raises:
            ValueError: 当插件未加载或无法找到插件类时抛出
        """
        if plugin_name not in self.plugins:
            raise ValueError(f"插件 '{plugin_name}' 未加载")

        old_plugin = self.plugins[plugin_name]
        await self.unload_plugin(plugin_name)

        # 获取插件模块路径
        module_path = old_plugin.__class__.__module__
        module = importlib.import_module(module_path)
        
        # 强制重新加载
        importlib.reload(module)

        # 获取插件类
        plugin_class = None
        for item_name in dir(module):
            item = getattr(module, item_name)
            if (isinstance(item, type)  
                and issubclass(item, BasePlugin)  
                and hasattr(item, 'name')  
                and item.name == plugin_name):
                plugin_class = item
                break

        if not plugin_class:
            raise ValueError(f"无法在模块中找到插件类 '{plugin_name}'")

        # 创建新的插件实例
        new_plugin = plugin_class(
            self.event_bus,
            debug=self._debug,
            time_task_scheduler = self.time_task_scheduler,
            meta_data=self.meta_data.copy(), 
            api=old_plugin.api
        )
        await new_plugin.__onload__()
        self.plugins[plugin_name] = new_plugin

    def _load_modules_from_directory(
        self, directory_path: str
    ) -> Dict[str, ModuleType]:
        """从指定目录动态加载Python模块。

        Args:
            directory_path (str): 模块所在的目录路径

        Returns:
            Dict[str, ModuleType]: 模块名称到模块对象的映射字典

        Note:
            会自动处理模块的依赖安装
        """
        modules = {}
        original_sys_path = sys.path.copy()
        all_install = {pack['name'].strip().lower() for pack in PM.list_installed() if 'name' in pack}
        download_new = False

        try:
            directory_path = os.path.abspath(directory_path)
            sys.path.append(directory_path)

            for filename in os.listdir(directory_path):
                if not os.path.isdir(os.path.join(directory_path, filename)):
                    continue
                if os.path.isfile(os.path.join(directory_path, filename, "requirements.txt")):
                    requirements = set([pack.strip().lower() for pack in open(os.path.join(directory_path, filename, "requirements.txt")).readlines()])
                    download = requirements - all_install
                    if download:
                        download_new = True
                        LOG.warning(f'即将安装 {filename} 中要求的库: {" ".join(download)}')
                        if input('是否安装(Y/n):').lower() in ('y', ''):
                            for pack in download:
                                LOG.info(f'开始安装库: {pack}')
                                PM.install(pack)

                try:
                    module = importlib.import_module(filename)
                    modules[filename] = module
                except ImportError as e:
                    LOG.error(f"导入模块 {filename} 时出错: {e}")
                    continue

            if download_new:
                LOG.warning('在某些环境中, 动态安装的库可能不会立即生效, 需要重新启动。')

        finally:
            sys.path = original_sys_path

        return modules

    def unload_all(self, *arg, **kwd):
        """卸载所有已加载的插件。

        Args:
            *arg: 传递给插件卸载方法的位置参数
            **kwd: 传递给插件卸载方法的关键字参数

        Note:
            会创建新的事件循环来处理异步卸载操作
        """
        # 创建一个新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)  # 设置当前线程的事件循环

        try:
            # 创建任务列表
            tasks = [self.unload_plugin(plugin, *arg, **kwd) for plugin in self.plugins.keys()]
            
            # 聚合任务并运行
            gathered = asyncio.gather(*tasks)
            loop.run_until_complete(gathered)
        except Exception as e:
            LOG.error(f"在卸载某个插件时产生了错误: {e}")
        finally:
            # 关闭事件循环
            loop.close()