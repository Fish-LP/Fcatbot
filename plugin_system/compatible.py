# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 18:38:11
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-19 21:27:55
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
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

    # 类属性定义
    group_event = _EventDecorator(OFFICIAL_GROUP_MESSAGE_EVENT)          # 群消息事件装饰器
    private_event = _EventDecorator(OFFICIAL_PRIVATE_MESSAGE_EVENT)      # 私聊消息事件装饰器
    notice_event = _EventDecorator(OFFICIAL_NOTICE_EVENT)                # 通知事件装饰器
    group_command = _EventDecorator(OFFICIAL_GROUP_COMMAND_EVENT)        # 群命令事件装饰器
    private_command = _EventDecorator(OFFICIAL_PRIVATE_COMMAND_EVENT)    # 私聊命令事件装饰器
    friend_request = _EventDecorator(OFFICIAL_FRIEND_REQUEST_EVENT)      # 好友请求事件装饰器
    group_request = _EventDecorator(OFFICIAL_GROUP_REQUEST_EVENT)        # 群请求事件装饰器