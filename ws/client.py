# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:59:15
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-15 19:51:52
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from typing import Optional, Callable
import asyncio
import websockets
import json
import collections  # 用于双端队列
from urllib.parse import urlparse, urlencode, urlunparse

import websockets.client

from ..utils import get_log

# 日志工具
_LOG = get_log('WebSocketClient')

# 自定义处理器类型: 接受一个字符串参数、返回 None
MessageHandler = Callable[[str], None]

class WebSocketClient:
    """
    一个简单的Ws客户端。
    """
    def __init__(
        self,
        uri: str,
        headers: dict[str, str] = {},
        initial_reconnect_interval: int = 5,  # 初始重连间隔（秒）
        max_reconnect_interval: int = 60,     # 最大重连间隔（秒）
        max_reconnect_attempts: int = 5,      # 最大重连尝试次数
        message_handler: Optional[Callable[[str], None]] = None,  # 自定义消息处理器
        close_handler: Optional[Callable[[], None]] = None
    ):
        """
        WebSocket 客户端初始化方法。
        
        :param uri: WebSocket 服务器地址
        :param headers: 请求头
        :param initial_reconnect_interval: 初始重连间隔时间,默认为 5 秒
        :param max_reconnect_interval: 最大重连间隔时间,默认为 60 秒
        :param max_reconnect_attempts: 最大重连尝试次数,默认为 5 次
        :param message_handler: 消息处理器,可选
        :param close_handler: 额外关闭函数,可选
        """
        self.uri = uri  # WebSocket 服务器地址
        self.websocket = None  # WebSocket 连接对象
        self._connect_task = None  # 用于存储连接任务
        self.headers = headers  # 请求头
        self.running = False  # 客户端是否处于运行状态
        self.reconnect_attempt = 0  # 当前重连尝试次数
        self.initial_reconnect_interval = initial_reconnect_interval  # 初始重连间隔
        self.max_reconnect_interval = max_reconnect_interval  # 最大重连间隔
        self.max_reconnect_attempts = max_reconnect_attempts  # 最大重连尝试次数
        self.message_handler = message_handler  # 自定义消息处理器
        self.close_handler = close_handler  # 额外关闭函数
        self._closed = False  # 连接是否已主动关闭
        # 使用双端队列存储消息,支持获取最新或最旧消息
        self._message_deque = collections.deque()
        self._message_available = None

    async def connect(self):
        """
        建立 WebSocket 连接。
        """
        try:
            _LOG.info("尝试连接 WebSocket 服务器...")
            self.websocket = await websockets.client.connect(
                self.uri,
                logger=_LOG,
                extra_headers=self.headers
            )
            _LOG.info("连接成功！")
            self._closed = False
            if self._message_available is None:
                # 用于通知 recv 方法有新消息到来
                self._message_available = asyncio.Event()
            return self.websocket
        except Exception as e:
            _LOG.error(f"连接失败: {e}")
            if not self._closed:
                await self._start_reconnect()
            return None

    async def _start_reconnect(self):
        """
        启动自动重连逻辑。
        """
        while self.running and not self._closed:
            await self._backoff_reconnect()
            await self.connect()

    async def _handle_websocket(self):
        """
        处理 WebSocket 连接的逻辑。包括接收和处理消息,以及连接关闭后的重连逻辑。
        """
        async for message in self.websocket:  # 不断接收服务器发来的消息
            _LOG.debug(f"接收到消息: {message}")
            # 将消息存入双端队列
            self._message_deque.append(message)
            # 通知有新消息
            self._message_available.set()
            if self.message_handler:
                # 如果用户提供了自定义处理器,则调用该处理器
                await self._invoke_handler(message)
            else:
                # 如果没有自定义处理器,使用默认处理器
                self._default_message_handler(message)
        # 如果 WebSocket 连接断开,并且客户端仍处于运行状态,则尝试重连
        if self.running and not self._closed:
            await self._start_reconnect()

    async def _invoke_handler(self, data: str):
        """
        调用用户提供的自定义消息处理器。

        :param data: 接收到的消息内容
        """
        try:
            # 调用自定义处理器,处理接收到的消息
            await self.message_handler(data)
        except Exception as e:
            _LOG.error(f"自定义处理器抛出异常: {e}")

    def _default_message_handler(self, data: str):
        """
        默认的消息处理器。如果用户没有提供自定义处理器,将使用此默认处理器。

        :param data: 接收到的消息内容
        """
        _LOG.info(data)  # 打印消息内容

    async def _backoff_reconnect(self):
        """
        指数退避重连策略。

        根据当前重连尝试次数,计算重连间隔时间,并在达到最大尝试次数时停止重连。
        """
        self.reconnect_attempt += 1  # 增加重连尝试次数
        if self.reconnect_attempt > self.max_reconnect_attempts:
            _LOG.error(f"达到最大重连次数 {self.reconnect_attempt},停止重连！")
            self.running = False  # 停止运行
            return

        # 计算当前重连间隔时间,使用指数退避算法
        backoff = min(
            self.initial_reconnect_interval * (2 ** self.reconnect_attempt),
            self.max_reconnect_interval
        )
        backoff = max(backoff, self.initial_reconnect_interval)

        _LOG.info(
            f"重连尝试 {self.reconnect_attempt}/{self.max_reconnect_attempts},"
            f"等待 {backoff} 秒后重连..."
        )
        await asyncio.sleep(backoff)  # 等待一段时间后重连

    async def disconnect(self, timeout = 2):
        """
        断开与 WebSocket 服务器的连接。
        """
        self.running = False  # 设置运行状态为 False
        if self.websocket:
            # 创建关闭连接的任务
            close_task = asyncio.create_task(self.websocket.close(code=1001))
            try:
                # 等待最多 2 秒
                await asyncio.wait_for(close_task, timeout=timeout)
                _LOG.info("WebSocket 连接已关闭")
            except asyncio.TimeoutError:
                _LOG.warning("关闭 WebSocket 连接超时！")
            except Exception as e:
                _LOG.error(f"关闭 WebSocket 连接时发生异常: {e}")
            finally:
                # 确保连接对象被清理
                self.websocket = None

    def start(self):
        """
        启动客户端,进入事件循环并尝试连接 WebSocket 服务器。
        """
        try:
            asyncio.run(self._start_client())
        except KeyboardInterrupt:
            print()
            _LOG.info('用户触发主动关闭')
            if self.close_handler:
                try:
                    self.close_handler()
                except Exception as e:
                    _LOG.error(f"自定义关闭函数产生错误: {e}")
            asyncio.run(self.disconnect(5))

    async def _start_client(self):
        self.running = True
        # 建立连接
        while self.running:
            connection = await self.connect()
            if connection is not None:
                # 连接成功后,处理消息
                await self._handle_websocket()

    async def __aenter__(self):
        if await self.connect():
            asyncio.create_task(self._start_client())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    def __del__(self):
        """
        析构方法,在对象销毁时关闭 WebSocket 连接。
        """
        # 避免使用 asyncio.run,直接调用同步关闭方法
        if self.websocket and not self.websocket.closed:
            # 使用低级别的低层次方法关闭连接
            # 注意: 这可能无法保证完全关闭
            self.websocket._closing_handshake = True
            self.websocket._close_code = 1001  # 表示客户端主动关闭

            # 或者直接调用 close 方法而不关心结果
            # 注: 这可能引发警告,但可以避免异步调用问题
            try:
                self.websocket.transport._sock.close()
            except:
                pass

    async def send_data(self, data: str, wait: bool = True):
        """
        发送数据前确保 WebSocket 连接已建立
        """
        if not self.websocket:
            _LOG.error("WebSocket 连接尚未建立,请稍后再试！")
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

            if wait:
                self._message_available.clear()
                response = await self.recv(prefer = 'wait', wait = True)
                _LOG.debug(f"服务器响应: {response}")
                return response
            return True
        except websockets.exceptions.ConnectionClosed as e:
            _LOG.error(f"WebSocket 连接关闭: {e}")
            return None
        except Exception as e:
            _LOG.error(f"发送数据时发生异常: {e}")
            return None

    async def recv(
        self,
        *,
        prefer: str = 'latest',
        wait: bool = False
    ) -> Optional[str]:
        """
        非阻塞地接收 WebSocket 消息。可以选择接收最新或最旧消息,并指定是否等待。

        :param prefer: 可选参数,指定接收最新 ('latest','new') 或最旧 ('oldest','old') 消息,或者等待一个消息 ('wait'),默认为 'latest'。
        :param wait: 可选参数,如果没有缓存指定是否等待直到有消息,默认为 False（不等待）。
        :return: 接收到的消息,如果没有消息则返回 None。
        """
        try:
            if prefer in ['latest', 'new']:
                # 获取最新消息,即双端队列的末尾元素
                message = self._message_deque.popleft() if self._message_deque else None
            elif prefer in ['oldest', 'old']:
                # 获取最旧消息,即双端队列的头部元素
                message = self._message_deque.pop() if self._message_deque else None
            elif prefer == 'wait':
                # 等待下一个消息,不从队列中获取
                self._message_available.clear()
                await self._message_available.wait()  # 等待消息到来
                message = self._message_deque.popleft()  # 假设消息是按顺序添加的,返回最新的
            else:
                # 默认行为,不指定模式
                message = self._message_deque.popleft() if self._message_deque else None  # 默认返回最新消息

            if wait and message is None:
                # 如果需要等待,则等待下一个消息
                self._message_available.clear()
                await self._message_available.wait()  # 等待消息到来
                # 获取消息后重置事件,表示已经处理过
                self._message_available.clear()
                # 返回最新的消息
                message = self._message_deque.popleft() if self._message_deque else None
            else:
                # 如果不需要等待,直接返回消息
                pass

            return message

        except IndexError:
            # 队列为空时返回 None
            return None
        except Exception as e:
            _LOG.error(f"接收消息时发生异常: {e}")
            return None