# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:59:15
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-04-06 14:03:02
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from typing import Optional, Callable
import asyncio
import websockets
import collections  # 用于双端队列
import threading
from concurrent.futures import ThreadPoolExecutor

import websockets.client

from ..utils import get_log

# 日志工具
_LOG = get_log('WebSocketClient')

# 自定义处理器类型: 接受一个字符串参数、返回 None
MessageHandler = Callable[[str], bool]

class WebSocketClient:
    """一个简单的Ws客户端。

    Attributes:
        uri (str): WebSocket 服务器地址
        websocket: WebSocket 连接对象
        headers (dict): 请求头
        running (bool): 客户端是否处于运行状态
        reconnect_attempt (int): 当前重连尝试次数
        initial_reconnect_interval (int): 初始重连间隔
        max_reconnect_interval (int): 最大重连间隔
        max_reconnect_attempts (int): 最大重连尝试次数
        message_handler (Callable): 自定义消息处理器
    """
    def __init__(
        self,
        uri: str,
        headers: dict[str, str] = {},
        initial_reconnect_interval: int = 5,  
        max_reconnect_interval: int = 60,     
        max_reconnect_attempts: int = 5,      
        message_handler: Optional[Callable[[str], None]] = None,  
        close_handler: Optional[Callable[[], None]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        """初始化 WebSocket 客户端。

        Args:
            uri: WebSocket 服务器地址
            headers: 请求头
            initial_reconnect_interval: 初始重连间隔时间，默认为 5 秒
            max_reconnect_interval: 最大重连间隔时间，默认为 60 秒
            max_reconnect_attempts: 最大重连尝试次数，默认为 5 次
            message_handler: 消息处理器，可选
            close_handler: 额外关闭函数，可选
            loop: 自定义事件循环，可选
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
        self._closed = False  # 连接是否已主动关闭
        # 使用双端队列存储消息,支持获取最新或最旧消息
        self._message_deque = collections.deque()
        self._message_available = None
        self.loop = loop or asyncio.new_event_loop()
        self._thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def connect(self):
        """建立 WebSocket 连接。

        Returns:
            WebSocket: 连接成功返回 websocket 对象，失败返回 None
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
        """启动自动重连逻辑。"""
        while self.running and not self._closed:
            await self._backoff_reconnect()
            await self.connect()

    async def _handle_websocket(self):
        """处理接收消息，自动存入队列并触发事件。"""
        async for msg in self.websocket:
            _LOG.debug(f"收到消息: {msg}")
            self._message_deque.append(msg)
            self._message_available.set()  # 触发有新消息
            # 若有自定义处理器，异步调用
            if self.message_handler:
                asyncio.create_task(self._invoke_handler(msg))

    async def _invoke_handler(self, data: str):
        """调用用户提供的自定义消息处理器。

        Args:
            data: 接收到的消息内容
        """
        try:
            # 调用自定义处理器,处理接收到的消息
            if asyncio.iscoroutinefunction(self.message_handler):
                await self.message_handler(data)
            else:
                await self.loop.run_in_executor(
                    self._executor,
                    self.message_handler,
                    data
                )
        except Exception as e:
            _LOG.error(f"自定义处理器抛出异常: {e}")

    def _default_message_handler(self, data: str):
        """默认的消息处理器。

        当用户没有提供自定义处理器时，将使用此默认处理器。

        Args:
            data: 接收到的消息内容
        """
        _LOG.info(data)  # 打印消息内容

    async def _backoff_reconnect(self):
        """指数退避重连策略。

        根据当前重连尝试次数，计算重连间隔时间，并在达到最大尝试次数时停止重连。
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
        """断开与 WebSocket 服务器的连接。

        Args:
            timeout: 关闭连接的超时时间，默认 2 秒
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
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def start(self):
        """启动客户端，运行在后台线程中。"""
        if self._thread and self._thread.is_alive():
            _LOG.warning("客户端已在运行中")
            return

        self.running = True
        self._thread = threading.Thread(
            target=self._run_event_loop,
            daemon=True,
            name="WebSocketClientThread"
        )
        self._thread.start()

    def _run_event_loop(self):
        """在独立线程中运行事件循环。"""
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start_client())
        except Exception as e:
            _LOG.error(f"事件循环异常终止: {e}")
        finally:
            self._cleanup()

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
        """析构方法,在对象销毁时关闭 WebSocket 连接。"""
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

    async def send_data(
        self, 
        data: str, 
        wait: bool = True, 
    ) -> Optional[str]:
        """发送数据并可选等待响应。

        Args:
            data: 要发送的数据
            wait: 是否等待响应，默认是

        Returns:
            str | bool: 若等待响应则返回响应内容，否则返回发送状态
        """
        if not self.websocket:
            _LOG.error("未连接，发送失败！")
            return False

        try:
            await self.websocket.send(data)
            _LOG.debug(f"发送成功: {data}")
            
            if wait:
                response = await self.recv(wait=True)
                _LOG.debug(f"收到响应: {response}")
                return response
            return True
        except websockets.ConnectionClosed:
            _LOG.error("连接已关闭，发送失败！")
            return False
        except Exception as e:
            _LOG.error(f"发送异常: {e}")
            return False

    def send_sync(self, data: str, timeout: float = 5.0) -> bool:
        """同步发送数据（线程安全）。

        Args:
            data: 要发送的数据
            timeout: 超时时间，默认 5 秒

        Returns:
            bool: 发送是否成功

        Raises:
            RuntimeError: 客户端未启动时抛出
        """
        if not self.running:
            raise RuntimeError("客户端未启动")
        future = asyncio.run_coroutine_threadsafe(
            self.send_data(data),
            self.loop
        )
        try:
            return future.result(timeout)
        except TimeoutError:
            _LOG.error("发送超时")
            return False

    async def recv(
        self,
        *,
        prefer: str = 'latest',
        wait: bool = False
    ) -> Optional[str]:
        """接收 WebSocket 消息。

        Args:
            prefer: 消息获取方式，'latest'（默认）取最新，'oldest'取最旧
            wait: 无消息时是否阻塞等待，默认否

        Returns:
            str | None: 消息内容，无消息且不等待时返回None
        """
        try:
            if not wait and self._message_deque:
                if len(self._message_deque) > 64:
                    self._message_deque.popleft()
                # 更新事件状态
                self._message_available.clear()
                message = None
                # 根据prefer选择消息
                if prefer in ['latest', 'new']:
                    message = self._message_deque.pop()
                elif prefer in ['oldest', 'old']:
                    message = self._message_deque.popleft()
                else:
                    _LOG.warning(f"无效prefer参数'{prefer}'，使用默认'latest'")
                    message = self._message_deque.pop()

                return message
            else:
                if not wait:
                    return None
                # 等待新消息
                self._message_available.clear()
                await self._message_available.wait()
                return self._message_deque.pop()
        except Exception as e:
            _LOG.error(f"接收消息出错: {e}")
            return None

    def _cleanup(self):
        """资源清理。"""
        if self._executor:
            self._executor.shutdown(wait=False)