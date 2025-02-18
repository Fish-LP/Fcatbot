import json
import asyncio
import uuid

from ..utils import get_log
from ..models import GroupMessage
from ..models import PrivateMessage
from .client import WebSocketClient
from ..models import Nope

_log = get_log('WsClient')

class Client(WebSocketClient):
    def __init__(self, uri, headers = None, initial_reconnect_interval = 5, max_reconnect_interval = 60, max_reconnect_attempts = 5, message_handler = None):
        super().__init__(uri, headers, initial_reconnect_interval, max_reconnect_interval, max_reconnect_attempts, message_handler)
        self.last_heartbeat:dict = {}
        self.ping:int = -1

    async def api(self, action: str, param: dict = None, echo = uuid.uuid4().hex, **params) -> dict:
        '''
        :param action: 指定要调用的 API
        :param params: 用于传入参数, 可选
        :param echo  : 用于标识唯一请求
        '''
        data = {
            "action": action,
            "params": param or params,
            "echo": echo
        }
        re = json.loads(await self.send_data(data))
        if re.get('wording', None):
            _log.error(f"api异常 {re['wording']}")
        if re.get('status', None) in ('OK', 'ok', '200'):
            if re.get('echo', None) == echo:
                return re['data']
            else:
                _log.error(f"echo行为异常 {re['echo']} != {echo}: {re}")
        else:
            _log.error(f"api异常 {re['echo']} != {echo}: {re}")
