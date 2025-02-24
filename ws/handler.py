# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:59:27
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-21 22:20:12
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
import json
import asyncio
from typing import Any, Optional
import uuid

from ..utils import get_log
from ..DataModels import GroupMessage
from ..DataModels import PrivateMessage
from ..DataModels import MessageChain
from .client import WebSocketClient
from .api import Apis
from ..DataModels import Nope

_LOG = get_log('WsClient')

class WebSocketHandler(WebSocketClient, Apis):
    def __init__(self, uri, headers = None, initial_reconnect_interval = 5, max_reconnect_interval = 60, max_reconnect_attempts = 5, message_handler = None):
        super().__init__(uri, headers, initial_reconnect_interval, max_reconnect_interval, max_reconnect_attempts, message_handler)
        self.ws_client = self
        self.last_heartbeat:dict = {}
        self.ping:int = -1

    async def api(self, action: str, param: Optional[Any] = None, echo = uuid.uuid4().hex, wait: bool = True, **params) -> Optional[dict]:
        '''
        :param action: 指定要调用的 API
        :param params: 用于传入参数, 可选
        :param echo  : 用于标识唯一请求
        :param wait  : 是否等待服务器响应
        '''
        data = {
            "action": action,
            "params": param or params,
            "echo": echo,
        }
        re = await self.send_data(data, wait=wait)
        if not wait:
            return None

        try:
            re = json.loads(str(re))
        except json.JSONDecodeError as e:
            _LOG.error(f"API响应数据解析失败: {e}")
            return None
        except TypeError as e:
            _LOG.error(f"API响应数据类型错误: {e}")
            return None

        if re.get('wording', None):
            _LOG.error(f"API异常 {re['wording']}")
        if re.get('status', None) in ('OK', 'ok', '200'):
            if re.get('echo', None) == echo:
                return re['data']
            else:
                _LOG.error(f"API响应的 echo 标识不符")
        else:
            _LOG.error(f"API调用异常: {re}")
            return None

    async def send_group_msg(self, messagechain: MessageChain, group_id:str = None, wait: bool = True):
        await self.api('send_group_msg', wait = wait, group_id = group_id, message = messagechain.to_dict())

    async def send_privat_msg(self, messagechain: MessageChain, user_id:str = None, wait: bool = True):
        await self.api('send_privat_msg', wait = wait, user_id = user_id, message = messagechain.to_dict())

    async def __aenter__(self):
        if await self.connect():
            asyncio.create_task(self._start_client())
            lifecycle = json.loads(str(await self.recv(prefer='wait')))
            if lifecycle.get('post_type',None) == 'meta_event':
                _LOG.info(f"{lifecycle['self_id']} 连接成功")
        return self