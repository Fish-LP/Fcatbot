# -------------------------
# @Author       : Fish-LP fish.zh, field@outlook.com
# @Date         : 2025-03-19 20:26:19
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-07 21:27:22
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from dataclasses import dataclass, field
import time
from typing import Literal, Dict, Any

@dataclass(frozen=True)
class MetaEvent:
    """元事件基类"""
    time: int = field(default_factory=lambda: int(time.time()))
    '''事件发生的时间戳'''
    self_id: int = field(default=None)
    '''收到事件的机器人 QQ 号'''
    post_type: Literal['meta_event'] = field(default='meta_event')
    '''上报类型'''


@dataclass(frozen=True)
class LifecycleEvent(MetaEvent):
    post_type: Literal['meta_event'] 
    """生命周期事件"""
    meta_event_type: Literal['lifecycle'] = field(default='lifecycle')
    '''元事件类型'''
    sub_type: Literal['enable', 'disable', 'connect'] = field(default=None)
    '''事件子类型'''

@dataclass(frozen=True)
class HeartbeatEvent(MetaEvent):
    post_type: Literal['meta_event'] 
    """心跳事件"""
    meta_event_type: Literal['heartbeat'] = field(default='heartbeat')
    '''元事件类型'''
    status: Dict[str, Any] = field(default_factory=dict)
    '''状态信息'''
    interval: int = field(default=None)
    '''到下次心跳的间隔,单位毫秒'''