import logging
from typing import Any, Dict, Optional

from .base import BaseMixin
from ..abc import EventHandler

logger = logging.getLogger("PluginsSys")

class ServerMixin(BaseMixin):
    event = "server.{name}"

    def register_server(self, handler: EventHandler, name: str) -> None:
        """注册服务"""
        # 延迟初始化 server_ids
        server_ids: Dict[str, str] = self.context.set("server_ids", {})

        if name in server_ids:
            raise RuntimeError(f'服务 "{name}" 已经注册')

        server_id = self.context.register_handler(
            handler, self.event.format(name=name)
        )
        server_ids[name] = server_id
        logger.debug(
            '服务 "%s" 已使用处理程序 ID "%s" 注册', name, server_id
        )

    async def request_server(self, name: str, data: Any) -> Any:
        """向指定服务发送请求并返回结果"""
        event_name = self.event.format(name=name)
        logger.debug('请求服务 "%s" 处理事件 "%s"', name, event_name)

        resp: Dict[str, Any] = await self.context.event_bus.request(
            event_name,
            data,
            permission=f"{self.context.plugin_name}.server.request",
            source=self.context.plugin_name,
            target=f"server.{name}",
        )

        server_ids: Dict[str, str] = self.context.get("server_ids", {})
        # 只取第一个落在 server_ids 中的响应
        ret_data: Optional[Any] = next(
            (rdata for rid, rdata in resp.items() if rid in server_ids), None
        )

        if isinstance(ret_data, Exception):
            logger.error('服务 "%s" 请求失败：%s', name, ret_data)
            raise ret_data

        logger.debug('从服务 "%s" 收到响应：%s', name, ret_data)
        return ret_data