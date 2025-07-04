# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-15 18:59:25
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-30 21:17:10
# @Description  : 扩展的插件功能
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from .event_bus_api import EventHandlerMixin
from .event_func_api import PluginFunctionMixin
from .queue import QueueManager
__all__ = [
    'EventHandlerMixin', # 事件发布和订阅功能
    'PluginFunctionMixin',  # 插件功能管理(快速添加功能)
    'QueueManager', # 管道管理器
]