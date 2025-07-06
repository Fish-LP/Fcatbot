# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:59:27
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-06 16:19:44
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import json
import asyncio
from logging import Logger
from typing import Any, Optional, Dict, Union
import uuid
from ..utils import get_log
from ..data_models import MessageChain
from .client import WebSocketClient
from .api import Apis

_LOG = get_log('WsClient')

class WebSocketHandler(WebSocketClient, Apis):
    """WebSocket 处理器类

    继承自 WebSocketClient 和 Apis 类,用于管理 WebSocket 连接和 API 调用。

    Attributes:
        ws_client (WebSocketClient): WebSocket 客户端实例
        ping (int): 连接延迟值(毫秒)
        request_cache (Dict[UUID, dict]): 请求缓存字典
    """

    def __init__(
        self,
        uri: str,
        headers: Optional[Dict[str, str]] = {},
        ping_interval: float = 30.0,
        ping_timeout: float = 5.0,
        reconnect_attempts: int = 3,
        timeout: float = 10.0,
        auth: Optional[Union[Dict[str, str], None]] = {},
        max_queue_size: int = 127,
        random_jitter: float = 0.5,
    ):
        """初始化WebSocket处理器

        Args:
            uri: WebSocket 服务器地址
            headers: 连接头信息
            ping_interval: 心跳间隔（秒）
            ping_timeout: 心跳超时（秒）
            reconnect_attempts: 最大重试次数
            timeout: 连接/读写操作超时时间（秒）
            auth: 认证信息（用于需要认证的 WebSocket 服务器）
            max_queue_size: 消息队列最大大小
            random_jitter: 重连随机延迟因子
        """
        self.uri = uri
        super().__init__(
            uri = uri,
            logger = _LOG,
            headers = headers,
            auth = auth,
            ping_interval = ping_interval,
            ping_timeout = ping_timeout,
            reconnect_attempts = reconnect_attempts,
            timeout = timeout,
            max_queue_size = max_queue_size,
            random_jitter = random_jitter,
        )
        self.ping:int = -1
        self.request_cache:Dict[uuid.UUID: dict] = {}
        self.request_interceptor = None

    def set_request_interceptor(self, interceptor):
        """设置请求拦截器函数
        
        Args:
            interceptor: 接收 action 和 params 参数的函数,返回修改后的响应数据
        """
        _LOG.warning(f'当前ws连接已被内部拦截: {self.uri} [{interceptor.__doc__}]')
        self.request_interceptor = interceptor
    
    async def api(self,
                action: str,
                param: Optional[Any] = None, 
                echo: uuid.UUID = uuid.uuid4().hex,
                ) -> Optional[dict]:
        """调用API接口

        Args:
            action: API动作名称
            param: API调用参数
            echo: 请求标识符

        Returns:
            API调用结果字典,失败时返回None

        Raises:
            JSONDecodeError: 响应数据JSON解析失败
            TypeError: 响应数据类型错误
        """
        if not echo: echo = uuid.uuid4().hex
        send_data = {
            "action": action,
            "params": param,
            "echo": echo,
        }

        # 如果在debug模式下且设置了拦截器,则使用拦截器处理请求
        if self.request_interceptor is not None:
            return await self.request_interceptor(action, param)

        data: str = self.request(
            send_data,
            self._api_hardler(echo)
        )
        if data is None:
            _LOG.error(f"API请求失败: {send_data}")
            return None
        data: dict = json.loads(str(data)) if isinstance(data, str) else data
        
        if data.get('wording', None):
            _LOG.error(f"API异常 {data['wording']}")
        if isinstance(data.get('status', ''), dict):
            return data
        elif data.get('status', '').lower() in ('ok', '200') or 'self_id' in data:
            if data.get('echo', None) == echo:
                return data['data']
            else:
                _LOG.error(f"API响应的 echo 标识不符")
        else:
            _LOG.error(f"API调用异常: {data}")
            return None
        
    async def send_group_msg(self, messagechain: MessageChain, group_id:str = None):
        """发送群消息.

        Args:
            messagechain: 消息链对象
            group_id: 目标群号
            wait: 是否等待响应  
        """
        await self.api('send_group_msg', group_id = group_id, message = messagechain.to_dict())

    async def send_privat_msg(self, messagechain: MessageChain, user_id:str = None):
        """发送私聊消息.

        Args:
            messagechain: 消息链对象
            user_id: 目标用户ID
            wait: 是否等待响应
        """
        await self.api('send_privat_msg', user_id = user_id, message = messagechain.to_dict())

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
    
    def _api_hardler(self, echo: str):
        def func(data: Any):
            if isinstance(data, str):
                try:
                    re: dict = json.loads(str(data))
                except: # 需要日志
                    _LOG.error(f"API响应数据解析失败: {data}")
                    return False
            return 'echo' in re and re.get('echo', None) == echo
        return func
