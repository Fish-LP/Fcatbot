# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 20:08:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-11 21:56:20
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from pathlib import Path
from typing import Any, Dict, List, Callable, Awaitable, final
import asyncio
from uuid import UUID

from .custom_err import PluginLoadError
from .event import EventBus, Event
from ..utils import ChangeDir
from ..utils import UniversalLoader
from ..utils.UniversalDataIO import FileTypeUnknownError, SaveError, LoadError
from ..config import PERSISTENT_DIR
from ..ws import WebSocketHandler

class BasePlugin:
    """插件基类

    所有插件必须继承此类来实现插件功能。提供了插件系统所需的基本功能支持。

    Attributes:
        name (str): 插件名称
        version (str): 插件版本号 
        dependencies (dict): 插件依赖项配置
        meta_data (dict): 插件元数据
        api (WebSocketHandler): API接口处理器
        event_bus (EventBus): 事件总线实例
        lock (asyncio.Lock): 异步锁对象
        work_path (Path): 插件工作目录路径
        data (UniversalLoader): 插件数据管理器
        work_space (ChangeDir): 插件工作目录上下文管理器
        first_load (bool): 是否首次加载标志
    """

    name: str
    version: str
    dependencies: dict
    meta_data: dict
    api: WebSocketHandler
    
    @final
    def __init__(self, event_bus: EventBus, **kwd):
        """初始化插件实例
        
        Args:
            event_bus: 事件总线实例
            **kwd: 额外的关键字参数,将被设置为插件属性
            
        Raises:
            ValueError: 当缺少插件名称或版本号时抛出
            PluginLoadError: 当工作目录无效时抛出
        """
        if not self.name: raise ValueError('缺失插件名称')
        if not self.version: raise ValueError('缺失插件版本号')
        if kwd:
            for k, v in kwd.items():
                setattr(self, k, v)
        
        if not self.dependencies: self.dependencies = {}
        self.event_bus = event_bus
        self.lock = asyncio.Lock()  # 创建一个异步锁对象
        self.work_path = Path(PERSISTENT_DIR) / self.name
        self._event_handlers = []
        self.data = UniversalLoader(self.work_path / f"{self.name}.json")

        if not self.work_path.exists():
            try:
                self.work_path.mkdir(parents=True)
                self.first_load = True  # 表示是第一次启动
            except FileExistsError:
                self.first_load = False

        if not self.work_path.is_dir():
            raise PluginLoadError(self.name, f"{self.work_path} 不是目录文件夹")

        self.work_space = ChangeDir(self.work_path)

    @final
    def __unload__(self):
        """卸载插件时的清理操作
        
        执行插件卸载前的清理工作,保存数据并注销事件处理器
        
        Raises:
            RuntimeError: 保存持久化数据失败时抛出
        """
        self.unregister_handlers()
        self._close_()
        try:
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
        try:
            self.data.load()
        except (FileTypeUnknownError, LoadError, FileNotFoundError) as e:
            open(self.work_path / f'{self.name}.json','w').write('{}')
            self.data.load()
        await asyncio.to_thread(self._init_)
        await self.on_load()

    @final
    def publish_sync(self, event: Event) -> List[Any]:
        """同步发布事件

        Args:
            event (Event): 要发布的事件对象

        Returns:
            List[Any]: 事件处理器返回的结果列表
        """
        return self.event_bus.publish_sync(event)

    @final
    def publish_async(self, event: Event) -> Awaitable[List[Any]]:
        """异步发布事件

        Args:
            event (Event): 要发布的事件对象

        Returns:
            List[Any]: 事件处理器返回的结果列表
        """
        return self.event_bus.publish_async(event)

    @final
    def register_handler(self, event_type: str, handler: Callable[[Event], Any], priority: int = 0) -> UUID:
        """注册事件处理器
        
        Args:
            event_type (str): 事件类型
            handler (Callable[[Event], Any]): 事件处理函数
            priority (int, optional): 处理器优先级,默认为0
            
        Returns:
            处理器的唯一标识UUID
        """
        handler_id = self.event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append(handler_id)
        return handler_id

    @final
    def unregister_handler(self, handler_id: UUID) -> bool:
        """注销指定的事件处理器
        
        Args:
            handler_id (UUID): 事件id
        
        Returns:
            bool: 操作结果
        """
        if handler_id in self._event_handlers:
            self._event_handlers.append(handler_id)
            return True
        return False

    @final
    def unregister_handlers(self):
        """注销所有已注册的事件处理器"""
        for handler_id in self._event_handlers:
            self.event_bus.unsubscribe(handler_id)

    async def on_load(self):
        """插件初始化时的钩子函数,可被子类重写"""
        pass

    def _init_(self):
        """插件初始化时的子函数,可被子类重写"""
        pass

    def _close_(self):
        """插件卸载时的子函数,可被子类重写"""
        pass