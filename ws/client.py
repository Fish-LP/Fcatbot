from typing import Optional, Callable
import asyncio
import websockets
import json
from aiohttp import ClientConnectionError
from urllib.parse import urlparse, urlencode, urlunparse

import websockets.client

from ..utils import get_log

# 日志工具
_LOG = get_log('WebSocketClient')

# 自定义处理器类型：接受一个字符串参数、返回 None
MessageHandler = Callable[[str], None]  

class WebSocketClient:
    """
    一个简单的Ws客户端。
    """
    def __init__(
        self,
        uri: str,
        headers: dict = None,
        initial_reconnect_interval: int = 5,  # 初始重连间隔（秒）
        max_reconnect_interval: int = 60,     # 最大重连间隔（秒）
        max_reconnect_attempts: int = 5,      # 最大重连尝试次数
        message_handler: Optional[MessageHandler] = None  # 自定义消息处理器
    ):
        """
        WebSocket 客户端初始化方法。
        
        :param uri: WebSocket 服务器地址
        :param headers: 请求头
        :param initial_reconnect_interval: 初始重连间隔时间，默认为 5 秒
        :param max_reconnect_interval: 最大重连间隔时间，默认为 60 秒
        :param max_reconnect_attempts: 最大重连尝试次数，默认为 5 次
        :param message_handler: 消息处理器，可选
        """
        self.uri = uri  # WebSocket 服务器地址
        self.websocket = None  # WebSocket 连接对象
        self.headers = headers  # 请求头
        self.running = False  # 客户端是否处于运行状态
        self.reconnect_attempt = 0  # 当前重连尝试次数
        self.initial_reconnect_interval = initial_reconnect_interval  # 初始重连间隔
        self.max_reconnect_interval = max_reconnect_interval  # 最大重连间隔
        self.max_reconnect_attempts = max_reconnect_attempts  # 最大重连尝试次数
        self.message_handler = message_handler  # 自定义消息处理器

    async def connect(self):
        """
        连接到 WebSocket 服务器，并支持持久化连接和自动重连。

        该方法会不断尝试连接 WebSocket 服务器，如果连接失败，会根据重连策略自动重连。
        """
        self.running = True  # 设置运行状态为 True
        while self.running:
            try:
                _LOG.info("尝试连接 WebSocket 服务器...")
                self.websocket = await websockets.client.connect(
                    self.uri,    # 连接地址
                    logger=_LOG, # 使用自定义日志工具
                    extra_headers=self.headers  # 自定义请求头
                )
                _LOG.info("连接成功！")
                self.reconnect_attempt = 0  # 重置重连尝试次数
                await self._handle_websocket()  # 处理 WebSocket 连接和消息
            except websockets.InvalidHandshake as e:
                _LOG.error(f"连接失败: {e}，尝试重连...")
                await self._backoff_reconnect()  # 指数退避重连
            except (ConnectionRefusedError, ClientConnectionError, OSError) as e:
                _LOG.error(f"连接失败: {e}，尝试重连...")
                await self._backoff_reconnect()
            except Exception as e:
                _LOG.error(f"发生未知错误: {e}，尝试重连...")
                await self._backoff_reconnect()
            finally:
                # 如果 WebSocket 连接已建立，则确保其在异常后关闭
                if self.websocket:
                    await self.websocket.close()

    async def _handle_websocket(self):
        """
        处理 WebSocket 连接的逻辑。包括接收和处理消息，以及连接关闭后的重连逻辑。
        """
        async for message in self.websocket:  # 不断接收服务器发来的消息
            _LOG.debug(f"接收到消息: {message}")
            if self.message_handler:
                # 如果用户提供了自定义处理器，则调用该处理器
                await self._invoke_handler(message)
            else:
                # 如果没有自定义处理器，使用默认处理器
                self._default_message_handler(message)
        # 如果 WebSocket 连接断开，并且客户端仍处于运行状态，则尝试重连
        if self.running:
            await self._backoff_reconnect()

    async def _invoke_handler(self, data: str):
        """
        调用用户提供的自定义消息处理器。

        :param data: 接收到的消息内容
        """
        try:
            # 调用自定义处理器，处理接收到的消息
            await self.message_handler(data)
        except Exception as e:
            _LOG.error(f"自定义处理器抛出异常: {e}")

    def _default_message_handler(self, data: str):
        """
        默认的消息处理器。如果用户没有提供自定义处理器，将使用此默认处理器。

        :param data: 接收到的消息内容
        """
        _LOG.info(data)  # 打印消息内容

    async def _backoff_reconnect(self):
        """
        指数退避重连策略。

        根据当前重连尝试次数，计算重连间隔时间，并在达到最大尝试次数时停止重连。
        """
        self.reconnect_attempt += 1  # 增加重连尝试次数
        if self.reconnect_attempt > self.max_reconnect_attempts:
            _LOG.error(f"达到最大重连次数 {self.reconnect_attempt}，停止重连！")
            self.running = False  # 停止运行
            return

        # 计算当前重连间隔时间，使用指数退避算法
        backoff = min(
            self.initial_reconnect_interval * (2 ** self.reconnect_attempt),
            self.max_reconnect_interval
        )
        backoff = max(backoff, self.initial_reconnect_interval)

        _LOG.info(
            f"重连尝试 {self.reconnect_attempt}/{self.max_reconnect_attempts}，"
            f"等待 {backoff} 秒后重连..."
        )
        await asyncio.sleep(backoff)  # 等待一段时间后重连

    async def disconnect(self):
        """
        断开与 WebSocket 服务器的连接。
        """
        self.running = False  # 设置运行状态为 False
        if self.websocket:
            await self.websocket.close()  # 关闭 WebSocket 连接
            _LOG.info("WebSocket 连接已断开")

    def start(self):
        """
        启动客户端，进入事件循环并尝试连接 WebSocket 服务器。
        """
        asyncio.run(self.connect())  # 使用 asyncio 运行异步任务

    async def __aenter__(self):
        """
        异步上下文管理器的进入方法。
        自动调用 connect 方法建立 WebSocket 连接。
        """
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        异步上下文管理器的退出方法。
        自动调用 disconnect 方法断开 WebSocket 连接。
        """
        await self.disconnect()

    def __del__(self):
        """
        析构方法，在对象销毁时关闭 WebSocket 连接。
        """
        if self.websocket:
            asyncio.run(self.websocket.close())  # 确保 WebSocket 连接关闭

    async def send_data(
        self,
        data: str,
        wait: bool = True,
    ):
        """
        通过已建立的 WebSocket 连接发送数据。

        :param data: 要发送的数据（字符串或 JSON 序列化后的数据）
        :param wait: 等待服务器的下一次发送
        
        :return respons: 原始数据
        """
        if not self.websocket:
            _LOG.error("WebSocket 连接尚未建立或已关闭！")
            return None

        try:
            # 发送数据
            if data is None:
                _LOG.warning("没有数据可发送！")
                return None

            if isinstance(data, dict):
                await self.websocket.send(json.dumps(data))
            else:
                await self.websocket.send(str(data))

            _LOG.debug(f"发送数据成功: {data}")

            # 等待服务器响应
            response = None
            if wait:
                response = await self.websocket.recv()
                _LOG.debug(f"服务器响应: {response}")
                return response

            return True  # 发送成功

        except websockets.exceptions.ConnectionClosed as e:
            _LOG.error(f"WebSocket 连接关闭: {e}")
            await self._backoff_reconnect()
            return None
        except Exception as e:
            _LOG.error(f"发送数据时发生异常: {e}")
            return None