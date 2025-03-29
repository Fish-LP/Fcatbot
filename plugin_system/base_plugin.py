# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 20:08:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-23 21:48:16
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import asyncio
import inspect

from pathlib import Path
from typing import Any, Dict, List, Callable, Awaitable, Optional, Tuple, Union, final
from uuid import UUID

from .custom_err import PluginLoadError
from .event import EventBus, Event
from ..utils import TimeTaskScheduler
from ..utils import ChangeDir
from ..utils import Color
from ..utils import UniversalLoader
from ..utils import get_log
from ..utils import visualize_tree
from ..utils.universal_data_IO import FileTypeUnknownError, SaveError, LoadError
from ..config import PERSISTENT_DIR, PLUGINS_DIR
from ..ws import WebSocketHandler

LOG = get_log('BasePlugin')

def extract_relative_path(base_path, target_path):
    base = Path(base_path).resolve()
    target = Path(target_path).resolve()
    try:
        relative_path = target.relative_to(base)
        return relative_path
    except ValueError:
        # 当路径不能求得相对路径时,返回目标路径的最后一级目录名
        return Path(target.name)

from .plugin_mixins import EventHandlerMixin, SchedulerMixin

class BasePlugin(EventHandlerMixin, SchedulerMixin):
    """插件基类

    所有插件必须继承此类来实现插件功能。提供了插件系统所需的基本功能支持。

    Attributes:
        name (str): 插件名称
        version (str): 插件版本号 
        dependencies (dict): 插件依赖项配置
        self_path (Path): 插件目录
        this_file_path (Path): 此文件路径
        meta_data (dict): 插件元数据
        api (WebSocketHandler): API接口处理器
        event_bus (EventBus): 事件总线实例
        lock (asyncio.Lock): 异步锁对象
        work_path (Path): 插件工作目录路径
        data (UniversalLoader): 插件数据管理器
        work_space (ChangeDir): 插件工作目录上下文管理器
        self_space (ChangeDir): 插件目录上下文管理器
        save_type (str): 私有数据保存类型
        first_load (bool): 是否首次加载标志
        debug (bool): 调试模式标记
    """

    name: str
    version: str
    dependencies: dict
    self_path: Path
    this_file_path: Path
    meta_data: dict
    api: WebSocketHandler
    save_type: str = 'json'
    first_load: bool = 'True'
    debug: bool = False  # 调试模式标记

    @final
    def __init__(self,
                event_bus: EventBus,
                time_task_scheduler: TimeTaskScheduler,
                debug: bool = False,
                **kwd):
        """初始化插件实例
        
        Args:
            event_bus: 事件总线实例
            time_task_scheduler: 定时任务调度器
            debug: 是否启用调试模式
            **kwd: 额外的关键字参数,将被设置为插件属性
            
        Raises:
            ValueError: 当缺少插件名称或版本号时抛出
            PluginLoadError: 当工作目录无效时抛出
        """
        # 插件信息检查
        if not self.name:
            raise ValueError('缺失插件名称')
        if not self.version:
            raise ValueError('缺失插件版本号')

        # 添加额外属性
        if kwd:
            for k, v in kwd.items():
                setattr(self, k, v)
        if not self.save_type:
            self.save_type = 'json'
        if not self.dependencies:
            self.dependencies = {}

        # 固定属性
        plugin_file = Path(inspect.getmodule(self.__class__).__file__).resolve()
        # plugins_dir = Path(PLUGINS_DIR).resolve()
        self.this_file_path = plugin_file
        # 使用插件文件所在目录作为self_path
        self.self_path = plugin_file.parent
        self.lock = asyncio.Lock()  # 创建一个异步锁对象

        # 隐藏属性
        self._debug = debug
        self._event_handlers = []
        self._event_bus = event_bus
        self._time_task_scheduler = time_task_scheduler
        # 使用插件目录名作为工作目录名
        plugin_dir_name = self.self_path.name
        self._work_path = Path(PERSISTENT_DIR).resolve() / plugin_dir_name
        self._data_path = self._work_path / f"{plugin_dir_name}.{self.save_type}"

        # 检查是否为第一次启动
        self.first_load = False
        if not self._work_path.exists():
            self._work_path.mkdir(parents=True)
            self.first_load = True
        elif not self._data_path.exists():
            self.first_load = True

        if not self._work_path.is_dir():
            raise PluginLoadError(self.name, f"{self._work_path} 不是目录文件夹")

        self.data = UniversalLoader(self._data_path)
        self.work_space = ChangeDir(self._work_path)
        self.self_space = ChangeDir(self.self_path)

    @property
    def debug(self) -> bool:
        """是否处于调试模式"""
        return self._debug

    @final 
    def check_debug(self, func_name: str) -> None:
        """检查是否允许在当前模式下调用某功能
        
        Args:
            func_name: 功能名称
        
        Raises:
            RuntimeError: 当在调试模式下调用受限功能时抛出
        """
        restricted_funcs = {
            'send_group_msg': '发送群消息',
            'send_private_msg': '发送私聊消息',
            'set_group_ban': '设置群禁言',
            'set_group_admin': '设置群管理员',
            # 添加其他需要限制的功能
        }
        
        if self._debug and func_name in restricted_funcs:
            raise RuntimeError(f"调试模式下禁止使用 {restricted_funcs[func_name]} 功能,触发者: {self.name}")

    @final
    async def __unload__(self, *arg, **kwd):
        """卸载插件时的清理操作
        
        执行插件卸载前的清理工作,保存数据并注销事件处理器
        
        Raises:
            RuntimeError: 保存持久化数据失败时抛出
        """
        self.unregister_handlers()
        await asyncio.to_thread(self._close_, *arg, **kwd)
        await self.on_close(*arg, **kwd)
        try:
            if self._debug:
                LOG.warning(f"{Color.YELLOW}debug模式{Color.RED}取消{Color.RESET}退出时的保存行为")
                print(f'{Color.GRAY}{self.name}\n', '\n'.join(visualize_tree(self.data.data)), sep='')
            else:
                self.data.save()
        except (FileTypeUnknownError, SaveError, FileNotFoundError) as e:
            raise RuntimeError(self.name, f"保存持久化数据时出错: {e}")

    @final
    async def __onload__(self):
        """加载插件时的初始化操作
        
        执行插件加载时的初始化工作,加载数据
        
        Raises:
            RuntimeError: 读取持久化数据失败时抛出
        """
        # load时传入的参数作为属性被保存在self中
        try:
            if isinstance(self.data,dict):
                data = UniversalLoader()
                data.data = self.data
                self.data = data
            self.data.load()
        except (FileTypeUnknownError, LoadError, FileNotFoundError) as e:
            open(self._data_path,'w').write('')
            self.data.save()
            self.data.load()
        await asyncio.to_thread(self._init_)
        await self.on_load()

    async def on_load(self):
        """插件初始化时的子函数,可被子类重写"""
        pass

    async def on_close(self, *arg, **kwd):
        """插件卸载时的子函数,可被子类重写"""
        pass

    def _init_(self):
        """插件初始化时的子函数,可被子类重写"""
        pass

    def _close_(self, *arg, **kwd):
        """插件卸载时的子函数,可被子类重写"""
        pass