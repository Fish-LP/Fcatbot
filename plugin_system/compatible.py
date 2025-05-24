from typing import Callable, Any, List, Optional, TypeVar, Dict, Union
import inspect
from functools import wraps
from datetime import datetime, timedelta

from .api import CompatibleHandler, COMPATIBLE_HANDLERS
from .base_plugin import BasePlugin
from .event.event_bus import EventBus
from .event import Event, Schedule
from ..config import (
    OFFICIAL_PRIVATE_MESSAGE_EVENT,
    OFFICIAL_GROUP_MESSAGE_EVENT,
    OFFICIAL_FRIEND_REQUEST_EVENT,
    OFFICIAL_GROUP_REQUEST_EVENT,
    OFFICIAL_NOTICE_EVENT,
    OFFICIAL_GROUP_COMMAND_EVENT,
    OFFICIAL_PRIVATE_COMMAND_EVENT,
)

from ..utils.time_task_scheduler import TimeTaskScheduler

# 定义泛型类型变量用于装饰器返回类型
F = TypeVar("F", bound=Callable[..., Any])

# 用于标记功能的元数据key
REGISTER_METADATA_KEY = "_register_metadata"
SCHEDULE_METADATA_KEY = "_schedule_metadata"

# 事件类型常量集合
OFFICIAL_SCHEDULE_EVENT = "schedule"
OFFICIAL_FUNCTION_EVENT = "function"

class CompatibleEnrollment:
    """
    提供事件、触发器、功能和定时任务的装饰器注册机制。
    """
    # 事件类型常量集合
    event_types = [
        OFFICIAL_GROUP_MESSAGE_EVENT,
        OFFICIAL_PRIVATE_MESSAGE_EVENT,
        OFFICIAL_FRIEND_REQUEST_EVENT,
        OFFICIAL_GROUP_REQUEST_EVENT,
        OFFICIAL_NOTICE_EVENT,
        OFFICIAL_GROUP_COMMAND_EVENT,
        OFFICIAL_PRIVATE_COMMAND_EVENT,
    ]

    def __init__(self):
        raise ValueError("该类不需要实例化")

    class _EventDecorator:
        """
        事件装饰器类，用于注册事件处理函数。
        """
        def __init__(self, event_type: str):
            """
            初始化事件装饰器。
            
            Args:
                event_type (str): 事件类型。
            """
            self.event_type = event_type

        def __call__(self, row_event: bool = False) -> Callable[[F], F]:
            """
            创建事件装饰器。
            
            Args:
                row_event (bool): 是否传递原始事件对象。默认为 False。
            """
            def decorator(func: F) -> F:
                """
                装饰器函数。
                """
                signature = inspect.signature(func)
                in_class = len(signature.parameters) > 1

                @wraps(func)
                def wrapper(*args, **kwargs) -> Optional[Any]:
                    """
                    包装函数，处理事件数据传递。
                    """
                    event = args[1] if in_class else args[0]
                    if row_event:
                        return func(*args, **kwargs)
                    else:
                        if in_class:
                            return func(args[0], event.data, *args[2:], **kwargs)
                        else:
                            return func(event.data, *args[1:], **kwargs)

                # 添加元数据用于事件注册
                setattr(wrapper, "_compatible_event", {
                    "event_type": self.event_type,
                    "priority": 0,
                    "in_class": in_class,
                    "row_event": row_event,
                })
                return wrapper  # type: ignore
            return decorator

    class _TriggerDecorator:
        """
        触发器装饰器类，用于为事件处理函数添加条件触发逻辑。
        """
        @staticmethod
        def keywords(*words: str, policy: str = "any") -> Callable[[F], F]:
            """
            关键词触发装饰器。
            
            Args:
                *words (str): 关键词列表。
                policy (str): 触发策略，支持 "any" 或 "all"。默认为 "any"。
            """
            def decorator(func: F) -> F:
                """
                装饰器函数。
                """
                @wraps(func)
                def wrapper(*args, **kwargs) -> Optional[Any]:
                    """
                    包装函数，检查消息是否包含关键词。
                    """
                    event = args[-1] if isinstance(args[-1], Event) else None
                    if not event or not hasattr(event.data, 'message'):
                        return func(*args, **kwargs)
                    msg_text = str(event.data.message)
                    if policy == "any":
                        if not any(word in msg_text for word in words):
                            return None
                    else:
                        if not all(word in msg_text for word in words):
                            return None
                    return func(*args, **kwargs)
                
                # 添加触发器元数据
                setattr(wrapper, "_compatible_trigger", {
                    "type": "keywords",
                    "words": words,
                    "policy": policy,
                })
                return wrapper  # type: ignore
            return decorator

        @staticmethod
        def has_elements(*elements: str) -> Callable[[F], F]:
            """
            消息元素类型触发装饰器。
            
            Args:
                *elements (str): 消息元素类型列表。
            """
            def decorator(func: F) -> F:
                """
                装饰器函数。
                """
                @wraps(func)
                def wrapper(*args, **kwargs) -> Optional[Any]:
                    """
                    包装函数，检查消息是否包含指定的元素类型。
                    """
                    event = args[-1] if isinstance(args[-1], Event) else None
                    if not event or not hasattr(event.data, 'message'):
                        return func(*args, **kwargs)
                    msg = event.data.message
                    if not all(msg.has_type(elem) for elem in elements):
                        return None
                    return func(*args, **kwargs)
                
                # 添加触发器元数据
                setattr(wrapper, "_compatible_trigger", {
                    "type": "has_elements",
                    "elements": elements,
                })
                return wrapper  # type: ignore
            return decorator

    class _FunctionDecorator:
        """
        功能注册装饰器类。
        """
        @staticmethod
        def register(name: str, description: str = "", permission: str = "default") -> Callable[[F], F]:
            """
            注册一个功能。
            
            Args:
                name (str): 功能名称。
                description (str): 功能描述。默认为空字符串。
                permission (str): 权限标识符。默认为 "default"。
            """
            def decorator(func: F) -> F:
                """
                装饰器函数。
                """
                setattr(func, REGISTER_METADATA_KEY, {
                    "name": name,
                    "description": description,
                    "permission": permission
                })
                return func
            return decorator

    class _ScheduleDecorator:
        """
        定时任务装饰器类。
        """
        @staticmethod
        def cron(cron: str, name: str = "", description: str = "") -> Callable[[F], F]:
            """
            使用 cron 表达式注册定时任务。
            
            Args:
                cron (str): cron 表达式。
                name (str): 任务名称。默认为空字符串。
                description (str): 任务描述。默认为空字符串。
            """
            def decorator(func: F) -> F:
                """
                装饰器函数。
                """
                setattr(func, SCHEDULE_METADATA_KEY, {
                    "type": "cron",
                    "cron": cron,
                    "name": name or func.__name__,
                    "description": description
                })
                return func
            return decorator
            
        @staticmethod
        def interval(
            seconds: int = 0,
            minutes: int = 0,
            hours: int = 0,
            days: int = 0,
            name: str = "",
            description: str = "",
            start_now: bool = True
        ) -> Callable[[F], F]:
            """
            按时间间隔注册定时任务。
            
            Args:
                seconds (int): 间隔秒数。默认为 0。
                minutes (int): 间隔分钟数。默认为 0。
                hours (int): 间隔小时数。默认为 0。
                days (int): 间隔天数。默认为 0。
                name (str): 任务名称。默认为空字符串。
                description (str): 任务描述。默认为空字符串。
                start_now (bool): 是否立即开始第一次执行。默认为 True。
            """
            def decorator(func: F) -> F:
                """
                装饰器函数。
                """
                total_seconds = (
                    seconds + 
                    minutes * 60 + 
                    hours * 3600 + 
                    days * 86400
                )
                
                setattr(func, SCHEDULE_METADATA_KEY, {
                    "type": "interval",
                    "interval": total_seconds,
                    "name": name or func.__name__,
                    "description": description,
                    "start_now": start_now
                })
                return func
            return decorator
            
        @staticmethod
        def daily(
            hour: int,
            minute: int = 0,
            name: str = "",
            description: str = ""
        ) -> Callable[[F], F]:
            """
            注册每日定时任务。
            
            Args:
                hour (int): 小时 (0-23)。
                minute (int): 分钟 (0-59)。默认为 0。
                name (str): 任务名称。默认为空字符串。
                description (str): 任务描述。默认为空字符串。
            """
            def decorator(func: F) -> F:
                """
                装饰器函数。
                """
                setattr(func, SCHEDULE_METADATA_KEY, {
                    "type": "daily",
                    "hour": hour,
                    "minute": minute,
                    "name": name or func.__name__,
                    "description": description
                })
                return func
            return decorator

    # 显式声明类属性类型以提供 IDE 提示
    def group_event(self, row_event: bool = False) -> F:
        """
        群消息事件装饰器。
        """
        return self._EventDecorator(OFFICIAL_GROUP_MESSAGE_EVENT)(row_event)

    def private_event(self, row_event: bool = False) -> F:
        """
        私聊消息事件装饰器。
        """
        return self._EventDecorator(OFFICIAL_PRIVATE_MESSAGE_EVENT)(row_event)

    def notice_event(self, row_event: bool = False) -> F:
        """
        通知事件装饰器。
        """
        return self._EventDecorator(OFFICIAL_NOTICE_EVENT)(row_event)

    def group_command(self, row_event: bool = False) -> F:
        """
        群命令事件装饰器。
        """
        return self._EventDecorator(OFFICIAL_GROUP_COMMAND_EVENT)(row_event)

    def private_command(self, row_event: bool = False) -> F:
        """
        私聊命令事件装饰器。
        """
        return self._EventDecorator(OFFICIAL_PRIVATE_COMMAND_EVENT)(row_event)

    def friend_request(self, row_event: bool = False) -> F:
        """
        好友请求事件装饰器。
        """
        return self._EventDecorator(OFFICIAL_FRIEND_REQUEST_EVENT)(row_event)

    def group_request(self, row_event: bool = False) -> F:
        """
        群请求事件装饰器。
        """
        return self._EventDecorator(OFFICIAL_GROUP_REQUEST_EVENT)(row_event)

    group_event = _EventDecorator(OFFICIAL_GROUP_MESSAGE_EVENT)
    private_event = _EventDecorator(OFFICIAL_PRIVATE_MESSAGE_EVENT)
    notice_event = _EventDecorator(OFFICIAL_NOTICE_EVENT)
    group_command = _EventDecorator(OFFICIAL_GROUP_COMMAND_EVENT)
    private_command = _EventDecorator(OFFICIAL_PRIVATE_COMMAND_EVENT)
    friend_request = _EventDecorator(OFFICIAL_FRIEND_REQUEST_EVENT)
    group_request = _EventDecorator(OFFICIAL_GROUP_REQUEST_EVENT)
    
    trigger: _TriggerDecorator = _TriggerDecorator()
    function: _FunctionDecorator = _FunctionDecorator()
    schedule: _ScheduleDecorator = _ScheduleDecorator()

class EventCompatibleHandler(CompatibleHandler):
    """
    事件兼容性处理器。
    """
    def check(self, obj: Any) -> bool:
        """
        检查对象是否包含事件元数据。
        
        Args:
            obj (Any): 待检查的对象。
        
        Returns:
            bool: 如果对象包含事件元数据，返回 True，否则返回 False。
        """
        return hasattr(obj, "_compatible_event")
        
    def handle(self, plugin: BasePlugin, func: Callable, event_bus: EventBus) -> None:
        """
        处理事件元数据，将事件处理函数注册到事件总线。
        
        Args:
            plugin (BasePlugin): 插件实例。
            func (Callable): 事件处理函数。
            event_bus (EventBus): 事件总线实例。
        """
        event_info = getattr(func, "_compatible_event")
        if event_info:
            if event_info["in_class"]:
                bound_func = func.__get__(plugin, plugin.__class__)
            else:
                bound_func = func
                
            handler_id = event_bus.subscribe(
                event_info["event_type"],
                bound_func,
                event_info.get("priority", 0)
            )
            plugin._event_handlers.append(handler_id)

class TriggerCompatibleHandler(CompatibleHandler):
    """
    触发器兼容性处理器。
    """
    def check(self, obj: Any) -> bool:
        """
        检查对象是否包含触发器元数据。
        
        Args:
            obj (Any): 待检查的对象。
        
        Returns:
            bool: 如果对象包含触发器元数据，返回 True，否则返回 False。
        """
        return hasattr(obj, "_compatible_trigger")
        
    def handle(self, plugin: BasePlugin, func: Callable, event_bus: EventBus) -> None:
        """
        处理触发器元数据，将触发器包装函数注册到事件总线。
        
        Args:
            plugin (BasePlugin): 插件实例。
            func (Callable): 原始函数。
            event_bus (EventBus): 事件总线实例。
        """
        trigger_info = getattr(func, "_compatible_trigger")
        if not trigger_info:
            return
            
        # 根据触发器类型进行适当的包装
        @wraps(func)
        def trigger_wrapper(*args, **kwargs) -> Optional[Any]:
            """
            触发器包装函数。
            """
            if not args or not isinstance(args[-1], Event):
                return None
                
            event = args[-1]
            if trigger_info["type"] == "keywords":
                # 关键词触发
                if not hasattr(event.data, 'message'):
                    return None
                    
                msg_text = str(event.data.message)
                words = trigger_info["words"]
                policy = trigger_info.get("policy", "any")
                
                if policy == "any":
                    if not any(word in msg_text for word in words):
                        return None
                else:
                    if not all(word in msg_text for word in words):
                        return None
                        
            elif trigger_info["type"] == "has_elements":
                # 消息元素类型触发
                if not hasattr(event.data, 'message'):
                    return None
                    
                msg = event.data.message
                elements = trigger_info["elements"]
                if not all(msg.has_type(elem) for elem in elements):
                    return None
                    
            # 调用原始函数
            if trigger_info.get("row_event", False):
                return func(*args, **kwargs)
            else:
                if len(args) > 1:
                    return func(args[0], event.data, *args[2:], **kwargs)
                else:
                    return func(event.data, *args[1:], **kwargs)
                    
        # 绑定到实例如果是类方法
        if len(inspect.signature(func).parameters) > 1:
            bound_func = trigger_wrapper.__get__(plugin, plugin.__class__)
        else:
            bound_func = trigger_wrapper
            
        # 订阅所有相关事件类型
        for event_type in CompatibleEnrollment.event_types:
            handler_id = event_bus.subscribe(
                event_type,
                bound_func,
                0  # 使用默认优先级
            )
            plugin._event_handlers.append(handler_id)

class FunctionCompatibleHandler(CompatibleHandler):
    """
    功能注册兼容性处理器。
    """
    def check(self, obj: Any) -> bool:
        """
        检查对象是否包含功能元数据。
        
        Args:
            obj (Any): 待检查的对象。
        
        Returns:
            bool: 如果对象包含功能元数据，返回 True，否则返回 False。
        """
        return hasattr(obj, REGISTER_METADATA_KEY)
        
    def handle(self, plugin: BasePlugin, func: Callable, event_bus: EventBus) -> None:
        """
        处理功能元数据，将功能注册到插件系统。
        
        Args:
            plugin (BasePlugin): 插件实例。
            func (Callable): 功能函数。
            event_bus (EventBus): 事件总线实例。
        """
        metadata = getattr(func, REGISTER_METADATA_KEY)
        if not metadata:
            return
            
        # 绑定到实例如果是类方法
        if len(inspect.signature(func).parameters) > 1:
            bound_func = func.__get__(plugin, plugin.__class__)
        else:
            bound_func = func
            
        # 注册功能到插件系统
        plugin.register_function(
            name=metadata["name"],
            description=metadata["description"],
            permission=metadata["permission"],
            func=bound_func
        )

class ScheduleCompatibleHandler(CompatibleHandler):
    """
    定时任务兼容性处理器。
    """
    def check(self, obj: Any) -> bool:
        """
        检查对象是否包含定时任务元数据。
        
        Args:
            obj (Any): 待检查的对象。
        
        Returns:
            bool: 如果对象包含定时任务元数据，返回 True，否则返回 False。
        """
        return hasattr(obj, SCHEDULE_METADATA_KEY)
        
    def handle(self, plugin: BasePlugin, func: Callable, event_bus: EventBus) -> None:
        """
        处理定时任务元数据，将定时任务注册到任务调度器。
        
        Args:
            plugin (BasePlugin): 插件实例。
            func (Callable): 定时任务函数。
            event_bus (EventBus): 事件总线实例。
        """
        metadata = getattr(func, SCHEDULE_METADATA_KEY)
        if not metadata:
            return
            
        # 绑定到实例如果是类方法
        if len(inspect.signature(func).parameters) > 1:
            bound_func = func.__get__(plugin, plugin.__class__)
        else:
            bound_func = func
            
        # 根据不同类型的定时任务进行注册
        scheduler = plugin.sys_api.get_scheduler()
        task_name = metadata["name"]
        
        if metadata["type"] == "cron":
            scheduler.add_cron_job(
                task_name,
                metadata["cron"],
                bound_func,
                metadata["description"]
            )
            
        elif metadata["type"] == "interval":
            scheduler.add_interval_job(
                task_name,
                metadata["interval"],
                bound_func,
                metadata["description"],
                start_now=metadata.get("start_now", True)
            )
            
        elif metadata["type"] == "daily":
            # 转换为 cron 表达式
            cron = f"0 {metadata['minute']} {metadata['hour']} * * *"
            scheduler.add_cron_job(
                task_name,
                cron,
                bound_func,
                metadata["description"]
            )

# 注册所有兼容性处理器
COMPATIBLE_HANDLERS.extend([
    EventCompatibleHandler("_compatible_event"),
    TriggerCompatibleHandler("_compatible_trigger"),
    FunctionCompatibleHandler(REGISTER_METADATA_KEY),
    ScheduleCompatibleHandler(SCHEDULE_METADATA_KEY),
])