from asyncio import Protocol
from typing import Callable, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .abc import Plugin, EventBus

class LazyDecoratorResolver(Protocol):
    """延迟解析装饰器协议，用于解决装饰器无法拿到类实例的绑定问题。"""

    # -------------- 元类：自动注册所有实现 --------------
    class _Meta(type):
        def __new__(mcls, name: str, bases, namespace):
            cls_obj = super().__new__(mcls, name, bases, namespace)
            # 跳过协议自身
            if name != "LazyDecoratorResolver":
                LazyDecoratorResolver._subclasses.append(cls_obj())
            return cls_obj
    
    _subclasses: List["LazyDecoratorResolver"] = []

    # -------------- 协议接口 --------------
    def __init__(self, attr_name: str) -> None:
        self.attr_name = attr_name

    def check(self, func: Callable) -> bool:
        """返回 True 表示本解析器负责处理该函数。"""
        ...

    def handle(self, plugin: "Plugin", func: Callable, event_bus: "EventBus") -> None:
        """真正延迟执行的绑定/补丁/注册逻辑。"""
        ...