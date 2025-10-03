# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-10-02 14:45:10
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-10-03 08:12:02
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from re import Pattern
from typing import Any, Dict, Optional, Union
from uuid import UUID

from Fcatbot.plugins.abc import DEFAULT_REQUEST_TIMEOUT, EventHandler
from .base import BaseMixin


class EventBusApiMixin(BaseMixin):
    def register_handler(
        self, 
        event: Union[str, Pattern[str]],  # 支持字符串或正则表达式
        handler: EventHandler
    ) -> UUID: 
        """注册事件处理器"""
        return self.context.register_handler(event, handler)
    
    def register_handlers(
        self, 
        event_handlers: Dict[Union[str, Pattern[str]], EventHandler]
    ) -> Dict[Union[str, Pattern[str]], UUID]:
        """批量注册事件处理器"""
        return self.context.register_handlers(event_handlers)

    
    def unregister_handler(self, handler_id: UUID) -> bool: 
        """取消注册事件处理器"""
        return self.context.unregister_handler(handler_id)

    async def request(
        self,
        event: str,
        data: Any = None,
        *,
        source: Optional[str] = None,
        target: Optional[str] = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT
    ) -> Dict[UUID, Union[Any, Exception]]: 
        """请求-响应模式"""
        return self.context.event_bus.request(event,data,source=source,target=target,timeout=timeout)

    def publish(
        self,
        event: str,
        data: Any = None,
        *,
        source: Optional[str] = None,
        target: Optional[str] = None
    ) -> None:
        """发布-订阅模式"""
        self.context.event_bus.publish(event,data,source=source,target=target)
