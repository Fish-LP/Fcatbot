from .http import HttpClient
from .ws import Client as WsClient
from .utils import get_log
from .models import GroupMessage
from .models import PrivateMessage

import json

_log = get_log('FBot')

class BotClient:
    def __init__(self, uri, token = None):
        headers = {"Content-Type": "application/json",}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = HttpClient(uri, headers)
        self.ws = WsClient(uri, headers, message_handler=self.headers)
    
    def run(self):
        self.ws.start()

    async def api(self, action: str, params: dict) -> dict:
        '''
        :param action: 指定要调用的 API
        :param params: 用于传入参数, 可选
        :param echo  : 用于标识唯一请求
        '''
        return self.ws.api(action, params)
    
    async def headers(self, data: str):
        msg = json.loads(data)
        if msg["post_type"] == "message" or msg["post_type"] == "message_sent":
            if msg["message_type"] == "group":
                # 群消息
                message = GroupMessage(**msg)
                group_name = (await self.ws.api('get_group_info',{"group_id": message.group_id}))['group_name']
                _log.info(f"Bot.{message.self_id}: [{group_name}({message.group_id})] {message.sender.nickname}({message.user_id}) -> {message.raw_message}")
            elif msg["message_type"] == "private":
                # 私聊消息
                message = PrivateMessage(**msg)
                _log.info(f"Bot.{message.self_id}: [{message.sender.nickname}({message.user_id})] -> {message.raw_message}")
        elif msg["post_type"] == "notice":
            pass
        elif msg["post_type"] == "request":
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