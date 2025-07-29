# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-15 19:12:16
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-29 14:21:15
# @Description  : IPluginApi用于显示声明动态添加的属性
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from ..ws import WebSocketHandler
from typing import Callable, Protocol, TYPE_CHECKING
if TYPE_CHECKING:
    from .base_plugin import BasePlugin
    from .event.event_bus import EventBus   
else:
    BasePlugin = object
    EventBus = object

class AbstractPluginApi:
    def init_api(self):
        pass

class CompatibleHandler(Protocol):
    '''兼容性处理器基类'''
    _subclasses = []
    
    def __init__(self, attr_name: str):
        self.attr_name = attr_name
        
    def check(self, func: Callable) -> bool:
        """检查函数是否满足该处理器的处理条件"""
        ...
        
    def handle(self, plugin: BasePlugin, func: Callable, event_bus: EventBus) -> None:
        """处理对象的兼容性行为"""
        ...
    
    class __metaclass__(type):
        def __init__(cls, name, bases, attrs):
            super().__init__(name, bases, attrs)
            if cls is not CompatibleHandler:
                CompatibleHandler._subclasses.append(cls)