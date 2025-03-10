# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 18:38:11
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-10 21:42:08
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
import inspect
from functools import wraps
from .event import Event
from ..config import (
    OFFICIAL_PRIVATE_MESSAGE_EVENT,
    OFFICIAL_GROUP_MESSAGE_EVENT,
    OFFICIAL_REQUEST_EVENT,
    OFFICIAL_NOTICE_EVENT
)
from ..DataModels.message import BaseMessage

class CompatibleEnrollment:
    events = {
        OFFICIAL_PRIVATE_MESSAGE_EVENT: [],
        OFFICIAL_GROUP_MESSAGE_EVENT: [],
        OFFICIAL_REQUEST_EVENT: [],
        OFFICIAL_NOTICE_EVENT: [],
    }

    def __init__(self):
        raise ValueError("不需要实例化该类")

    class _EventDecorator:
        def __init__(self, event_type):
            self.event_type = event_type

        def __call__(self, types='all', row_event=False):
            def decorator(func):
                signature = inspect.signature(func)
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
            if types != 'all' and isinstance(event.data, BaseMessage):
                event.data.message.filter(types)

    # 类属性定义
    group_event = _EventDecorator(OFFICIAL_GROUP_MESSAGE_EVENT)
    private_event = _EventDecorator(OFFICIAL_PRIVATE_MESSAGE_EVENT)
    notice_event = _EventDecorator(OFFICIAL_NOTICE_EVENT)
    request_event = _EventDecorator(OFFICIAL_REQUEST_EVENT)