# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:59:27
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-15 23:04:57
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import json
import asyncio
from typing import Any, Optional, Dict
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
    """WebSocket 处理器类

    继承自 WebSocketClient 和 Apis 类,用于管理 WebSocket 连接和 API 调用。

    Attributes:
        ws_client (WebSocketClient): WebSocket 客户端实例
        ping (int): 连接延迟值(毫秒)
        request_cache (Dict[UUID, dict]): 请求缓存字典
    """

    def __init__(self, uri, headers=None, initial_reconnect_interval=5, 
                 max_reconnect_interval=60, max_reconnect_attempts=5,
                 message_handler=None):
        """初始化WebSocket处理器

        Args:
            uri: WebSocket服务器地址
            headers: 连接请求头
            initial_reconnect_interval: 初始重连间隔(秒)
            max_reconnect_interval: 最大重连间隔(秒)
            max_reconnect_attempts: 最大重连尝试次数
            message_handler: 消息处理函数
        """
        super().__init__(uri, headers, initial_reconnect_interval, max_reconnect_interval, max_reconnect_attempts, message_handler)
        self.ws_client = self
        self.ping:int = -1
        self.request_cache:Dict[uuid.UUID: dict] = {}

    async def api(self,
                action: str,
                param: Optional[Any] = None, 
                echo = uuid.uuid4().hex,
                wait: bool = True,
                **params
                ) -> Optional[dict]:
        """调用API接口

        Args:
            action: API动作名称
            param: API调用参数
            echo: 请求标识符
            wait: 是否等待响应
            **params: 额外的API参数

        Returns:
            API调用结果字典,失败时返回None

        Raises:
            JSONDecodeError: 响应数据JSON解析失败
            TypeError: 响应数据类型错误
        """
        if not echo: echo = uuid.uuid4().hex
        data = {
            "action": action,
            "params": param or params,
            "echo": echo,
        }
        re = await self.send_data(json.dumps(data), wait=wait)
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
        """发送群消息.

        Args:
            messagechain: 消息链对象
            group_id: 目标群号
            wait: 是否等待响应  
        """
        await self.api('send_group_msg', wait = wait, group_id = group_id, message = messagechain.to_dict())

    async def send_privat_msg(self, messagechain: MessageChain, user_id:str = None, wait: bool = True):
        """发送私聊消息.

        Args:
            messagechain: 消息链对象
            user_id: 目标用户ID
            wait: 是否等待响应
        """
        await self.api('send_privat_msg', wait = wait, user_id = user_id, message = messagechain.to_dict())

    async def __aenter__(self):
        """异步上下文管理器入口.

        Returns:
            WebSocketHandler: 当前实例
        """
        if await self.connect():
            asyncio.create_task(self._start_client())
            lifecycle = json.loads(str(await self.recv(prefer='wait')))
            if lifecycle.get('post_type',None) == 'meta_event':
                _LOG.info(f"{lifecycle['self_id']} 连接成功")
        return self