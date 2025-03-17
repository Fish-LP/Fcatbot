# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 12:38:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-17 18:35:41
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import os
from typing import Any, List
from .ws import WebSocketHandler
from .utils import get_log
from .data_models import GroupMessage
from .data_models import PrivateMessage
from .plugin_system import EventBus, Event, PluginLoader
from .config import OFFICIAL_PRIVATE_MESSAGE_EVENT
from .config import OFFICIAL_GROUP_MESSAGE_EVENT
from .config import OFFICIAL_REQUEST_EVENT
from .config import OFFICIAL_NOTICE_EVENT
from .config import PLUGINS_DIR
from .config import OFFICIAL_PRIVATE_COMMAND_EVENT
from .config import OFFICIAL_GROUP_COMMAND_EVENT

import asyncio
import json

_log = get_log('FcatBot')

class BotClient:
    """QQ机器人客户端类.
    
    负责管理WebSocket连接、事件总线和插件系统。

    Attributes:
        event_bus: 事件总线实例
        plugin_sys: 插件加载器实例
        last_heartbeat: 最后一次心跳数据
        ws: WebSocket处理器实例
    """
    def __init__(self, uri: str, token: str = None, command_prefix: tuple[str] = ('/','#')):
        self.event_bus = EventBus()
        self.plugin_sys = PluginLoader(self.event_bus)
        self.last_heartbeat:dict = {}
        self.command_prefix = command_prefix
        
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.ws = WebSocketHandler(uri, headers, message_handler = self.on_message)

    def close(self):
        _log.info('用户主动触发关闭事件...')
        _log.info('准备关闭所有插件...')
        self.plugin_sys.unload_all()
        _log.info('Fcatbot 关闭完成')

    def run(self, load_plugins:bool = True):
        if load_plugins:
            _log.info('准备加载插件')
            if not os.path.exists(PLUGINS_DIR):
                os.makedirs(PLUGINS_DIR, exist_ok=True)
            asyncio.run(self.plugin_sys.load_plugins(api=self.ws))
        _log.info('准备启动Fcatbot')
        self.ws.close_handler = self.close
        try:
            self.ws.start()  # 启动 WebSocket 连接
        except KeyboardInterrupt:
            exit(0)

    async def api(self, action: str, **params) -> dict:
        """调用机器人API.

        Args:
            action: API名称
            **params: API参数

        Returns:
            dict: API响应数据
        """
        result = await self.ws.api(action, params, wait=True)
        return result
    
    def publish_sync(self, event: Event) -> List[Any]:
        """同步发布事件.

        Args:
            event: 要发布的事件

        Returns:
            List[Any]: 所有处理器返回的结果列表
        """
        self.event_bus.publish_sync(event)

    async def publish_async(self, event: Event) -> List[Any]:
        """异步发布事件.

        Args:
            event: 要发布的事件

        Returns:
            List[Any]: 所有处理器返回的结果列表
        """
        await self.event_bus.publish_async(event)
    
    async def on_message(self, data: str):
        """处理接收到的WebSocket消息.

        处理以下消息类型:
            - message/message_sent: 群聊/私聊消息
            - notice: 通知事件  
            - request: 请求事件
            - meta_event: 元事件(生命周期、心跳)

        Args:
            data: 接收到的消息数据(JSON格式)
        """
        msg = json.loads(data)
        if 'post_type' not in msg:
            return
        _LOG = get_log(f"Bot.{msg['self_id']}")
        if msg["post_type"] == "message" or msg["post_type"] == "message_sent":
            if msg["message_type"] == "group":
                # 群消息
                message = GroupMessage(**msg)
                group_info = await self.api('get_group_info', group_id = message.group_id)
                _LOG.info(f"[{group_info['group_name']}({message.group_id})] {message.sender.nickname}({message.user_id}) -> {message.raw_message}")
                if message.raw_message.startswith(self.command_prefix):
                    await self.event_bus.publish_async(Event(OFFICIAL_GROUP_COMMAND_EVENT, message))
                else:
                    await self.event_bus.publish_async(Event(OFFICIAL_GROUP_MESSAGE_EVENT, message))
            elif msg["message_type"] == "private":
                # 私聊消息
                message = PrivateMessage(**msg)
                _LOG.info(f"Bot.{message.self_id}: [{message.sender.nickname}({message.user_id})] -> {message.raw_message}")
                if message.raw_message.startswith(self.command_prefix):
                    await self.event_bus.publish_async(Event(OFFICIAL_PRIVATE_COMMAND_EVENT, message))
                else:
                    await self.event_bus.publish_async(Event(OFFICIAL_PRIVATE_MESSAGE_EVENT, message))
        elif msg["post_type"] == "notice":
            self.event_bus.publish_async(Event(OFFICIAL_NOTICE_EVENT, msg))
        elif msg["post_type"] == "request":
            self.event_bus.publish_async(Event(OFFICIAL_REQUEST_EVENT, msg))
        elif msg["post_type"] == "meta_event":
            if msg["meta_event_type"] == "lifecycle":
                _LOG.info(f"机器人 {msg.get('self_id')} 成功启动")
            elif msg["meta_event_type"] == "heartbeat":
                try:
                    self.ping = abs(self.last_heartbeat['time'] + self.last_heartbeat['interval'] - msg['time'])
                    self.last_heartbeat = msg
                    if 'status' in msg:
                        status: dict = msg['status']
                        if all(status.values()):
                            _LOG.debug(f'Status: {status}')
                        else:
                            _LOG.error(f'Status: {status}')
                except Exception:
                    self.last_heartbeat = msg
        else:
            _LOG.error("这是一个错误,请反馈给开发者\n" + str(msg))