# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 18:38:11
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-30 12:22:20
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from ctypes import Union
import inspect
from functools import wraps
from .event import Event
from ..config import (
    OFFICIAL_PRIVATE_MESSAGE_EVENT,
    OFFICIAL_GROUP_MESSAGE_EVENT,
    OFFICIAL_FRIEND_REQUEST_EVENT,
    OFFICIAL_GROUP_REQUEST_EVENT,
    OFFICIAL_NOTICE_EVENT,
    OFFICIAL_GROUP_COMMAND_EVENT,
    OFFICIAL_PRIVATE_COMMAND_EVENT,
)
from ..data_models.message import BaseMessage
from ..rbac_manager.RBAC_manager import RBACManager

class CompatibleEnrollment:
    # 事件类型与处理函数的映射
    events = {
        OFFICIAL_GROUP_MESSAGE_EVENT: [],          # 群消息事件
        OFFICIAL_PRIVATE_MESSAGE_EVENT: [],        # 私聊消息事件
        OFFICIAL_FRIEND_REQUEST_EVENT: [],         # 好友请求事件
        OFFICIAL_GROUP_REQUEST_EVENT: [],          # 群请求事件
        OFFICIAL_NOTICE_EVENT: [],                 # 通知事件
        OFFICIAL_GROUP_COMMAND_EVENT: [],          # 群命令事件
        OFFICIAL_PRIVATE_COMMAND_EVENT: [],        # 私聊命令事件
    }

    def __init__(self):
        raise ValueError("不需要实例化该类")

    class _EventDecorator:
        def __init__(self, event_type):
            """
            初始化事件装饰器

            Args:
                event_type (str): 事件类型
            """
            self.event_type = event_type

        def __call__(self, types='all', row_event=False):
            """
            装饰器工厂函数

            Args:
                types (str/list, optional): 消息类型过滤器. Defaults to 'all'.
                row_event (bool, optional): 是否传递原始事件对象. Defaults to False.
            """
            def decorator(func):
                # 获取函数签名
                signature = inspect.signature(func)
                # 判断函数是否在类中定义
                in_class = len(signature.parameters) > 1

                if in_class:
                    if row_event:
                        @wraps(func)
                        def wrapper(self, event: Event):
                            self._process_event(event, types)
                            return func(self, event)
                    else:
                        @wraps(func)
                        def wrapper(self, event: Event):
                            self._process_event(event, types)
                            return func(self, event.data)
                else:
                    if row_event:
                        @wraps(func)
                        def wrapper(event: Event):
                            self._process_event(event, types)
                            return func(event)
                    else:
                        @wraps(func)
                        def wrapper(event: Event):
                            self._process_event(event, types)
                            return func(event.data)

                # 添加到事件列表
                CompatibleEnrollment.events[self.event_type].append(
                    (wrapper, 0, in_class)
                )
                return wrapper
            return decorator

        @staticmethod
        def _process_event(event: Event, types):
            """
            处理事件，根据类型过滤消息

            Args:
                event (Event): 事件对象
                types (str/list): 消息类型过滤器
            """
            if types != 'all' and isinstance(event.data, BaseMessage):
                event.data.message.filter(types)

    class _TriggerDecorator:
        @staticmethod
        def keywords(*words, policy="any"):
            """
            关键词触发装饰器
            
            Args:
                *words: 触发关键词
                policy: 触发策略，"any"表示任意一个关键词匹配即触发，"all"表示所有关键词都要匹配
            """
            def decorator(func):
                @wraps(func)
                def wrapper(*args, **kwargs):
                    event = args[-1] if isinstance(args[-1], Event) else None
                    if not event or not hasattr(event.data, 'message'):
                        return func(*args, **kwargs)
                    
                    msg_text = str(event.data.message)
                    if policy == "any":
                        if not any(word in msg_text for word in words):
                            return None
                    else:  # all
                        if not all(word in msg_text for word in words):
                            return None
                    
                    return func(*args, **kwargs)
                return wrapper
            return decorator
        
        @staticmethod
        def has_elements(*elements):
            """
            消息元素触发装饰器
            
            Args:
                *elements: 需要包含的消息元素类型
            """
            def decorator(func):
                @wraps(func)
                def wrapper(*args, **kwargs):
                    event = args[-1] if isinstance(args[-1], Event) else None
                    if not event or not hasattr(event.data, 'message'):
                        return func(*args, **kwargs)
                    
                    msg = event.data.message
                    if not all(msg.has_type(elem) for elem in elements):
                        return None
                        
                    return func(*args, **kwargs)
                return wrapper
            return decorator

    # 类属性定义
    group_event = _EventDecorator(OFFICIAL_GROUP_MESSAGE_EVENT)          # 群消息事件装饰器
    private_event = _EventDecorator(OFFICIAL_PRIVATE_MESSAGE_EVENT)      # 私聊消息事件装饰器
    notice_event = _EventDecorator(OFFICIAL_NOTICE_EVENT)                # 通知事件装饰器
    group_command = _EventDecorator(OFFICIAL_GROUP_COMMAND_EVENT)        # 群命令事件装饰器
    private_command = _EventDecorator(OFFICIAL_PRIVATE_COMMAND_EVENT)    # 私聊命令事件装饰器
    friend_request = _EventDecorator(OFFICIAL_FRIEND_REQUEST_EVENT)      # 好友请求事件装饰器
    group_request = _EventDecorator(OFFICIAL_GROUP_REQUEST_EVENT)        # 群请求事件装饰器
    trigger = _TriggerDecorator                                          # 触发器装饰器

class PermissionTool:
    # RBAC管理器实例
    _rbac_manager = None

    def __init__(self):
        raise ValueError("不需要实例化该类")

    @classmethod
    def init_rbac(cls, case_sensitive: bool = True, default_role: str = None):
        """初始化RBAC管理器"""
        if cls._rbac_manager is None:
            cls._rbac_manager = RBACManager(case_sensitive, default_role)

    @classmethod
    def get_rbac(cls) -> RBACManager:
        """获取RBAC管理器实例"""
        if cls._rbac_manager is None:
            cls.init_rbac()
        return cls._rbac_manager

    @classmethod
    def permission(cls, permission_path: str):
        """
        权限检查装饰器，使用RBAC系统
        
        Args:
            permission_path: RBAC权限路径
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # 获取事件对象
                event: Union[Event,None] = args[-1] if isinstance(args[-1], Event) else None
                if not event:
                    return func(*args, **kwargs)
                
                # 获取发送者ID
                sender_id = str(event.data.sender.id) if hasattr(event.data, 'sender') else None
                if sender_id is None:
                    return func(*args, **kwargs)

                # RBAC权限检查
                if not cls._rbac_manager.check_permission(sender_id, permission_path):
                    return "权限不足"
                
                return func(*args, **kwargs)
            
            # 为函数添加权限路径属性
            wrapper.__permission_path__ = permission_path
            return wrapper
        return decorator