# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 12:38:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-22 01:12:57
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from .http import HttpClient
from .ws import WebSocketHandler
from .utils import get_log
from .DataModels import GroupMessage
from .DataModels import PrivateMessage
from .PluginSystem import EventBus, Event
from .config import OFFICIAL_PRIVATE_MESSAGE_EVENT
from .config import OFFICIAL_GROUP_MESSAGE_EVENT
from .config import OFFICIAL_REQUEST_EVENT
from .config import OFFICIAL_NOTICE_EVENT

import asyncio
import json

_log = get_log('FBot')

class BotClient:
    def __init__(self, event_bus: EventBus, uri: str, token: str = None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.event_bus = event_bus
        self.http = HttpClient(uri, headers)
        self.ws = WebSocketHandler(uri, headers, message_handler=self.on_message)
    
    def run(self):
        self.ws.start()  # 启动 WebSocket 连接

    async def api(self, action: str, param: dict = None, **params) -> dict:
        '''
        :param action: 指定要调用的 API
        :param params: 用于传入参数, 可选
        :param echo  : 用于标识唯一请求
        '''
        return await self.ws.api(action, param or params)
    
    async def on_message(self, data: str):
        """
        消息处理器
        """
        msg = json.loads(data)
        if msg["post_type"] == "message" or msg["post_type"] == "message_sent":
            if msg["message_type"] == "group":
                # 群消息
                message = GroupMessage(**msg)
                group_name = (await self.ws.api('get_group_info',{"group_id": message.group_id}))['group_name']
                _log.info(f"Bot.{message.self_id}: [{group_name}({message.group_id})] {message.sender.nickname}({message.user_id}) -> {message.raw_message}")
                await self.event_bus.publish_async(Event(OFFICIAL_GROUP_MESSAGE_EVENT, message))
            elif msg["message_type"] == "private":
                # 私聊消息
                message = PrivateMessage(**msg)
                _log.info(f"Bot.{message.self_id}: [{message.sender.nickname}({message.user_id})] -> {message.raw_message}")
                await self.event_bus.publish_async(Event(OFFICIAL_PRIVATE_MESSAGE_EVENT, message))
        elif msg["post_type"] == "notice":
            self.event_bus.publish_async(Event(OFFICIAL_NOTICE_EVENT, msg))
            pass
        elif msg["post_type"] == "request":
            self.event_bus.publish_async(Event(OFFICIAL_REQUEST_EVENT, msg))
            pass
        elif msg["post_type"] == "meta_event":
            if msg["meta_event_type"] == "lifecycle":
                _log.info(f"机器人 {msg.get('self_id')} 成功启动")
            elif msg["post_type"] == "meta_event":
                try:
                    self.ping = abs(self.last_heartbeat['time'] + self.last_heartbeat['interval'] - msg['time'])
                    self.last_heartbeat = msg
                except Exception:
                    self.last_heartbeat = msg
        else:
            _log.error("这是一个错误，请反馈给开发者\n" + str(msg))