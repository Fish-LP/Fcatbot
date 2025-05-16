from typing import Optional, Callable, Any
import asyncio
import websockets
import collections
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from ..utils import get_log

_LOG = get_log('WebSocketClient')

MessageHandler = Callable[[str], None]

class WebSocketClient:
    """
    功能丰富的 WebSocket 客户端，支持自动重连、消息队列和线程安全操作。

    该客户端旨在为 WebSocket 通信提供一个健壮、灵活且易于使用的接口。它通过异步事件循环和线程池实现高性能和线程安全的消息处理，同时具备自动重连机制以增强连接的可靠性。

    Attributes:
        uri (str): WebSocket 服务器的 URI。
        headers (dict[str, str]): 发送连接请求时附加的 HTTP 头。
        initial_reconnect_interval (int): 初始重连间隔时间（秒）。
        max_reconnect_interval (int): 最大重连间隔时间（秒）。
        max_reconnect_attempts (int): 最大重连尝试次数。
        message_handler (Optional[MessageHandler]): 用户定义的消息处理器回调函数。
        close_handler (Optional[Callable[[], None]]): 用户定义的连接关闭回调函数。
        loop (Optional[asyncio.AbstractEventLoop]): 事件循环实例。
        websocket (Optional[websockets.WebSocketClientProtocol]): WebSocket 连接协议对象。
        running (bool): 客户端是否处于运行状态。
        _closed (bool): 客户端是否已关闭。
        reconnect_attempt (int): 当前重连尝试次数。
        _connect_task (Optional[asyncio.Task]): 连接任务。
        _message_deque (collections.deque): 消息队列。
        _message_available (threading.Event): 消息可用事件。
        _deque_lock (threading.Lock): 消息队列锁。
        _thread (Optional[threading.Thread]): 事件循环线程。
        _executor (ThreadPoolExecutor): 线程池执行器。
        _receive_task (Optional[asyncio.Task]): 消息接收任务。

    Methods:
        start(): 启动客户端后台线程。
        send_sync(data, timeout): 同步发送数据。
        send_async(data, wait): 异步发送数据。
        recv(prefer, wait): 接收消息。
        disconnect(timeout): 同步断开连接。
        disconnect_async(timeout): 异步断开连接。

    Example:
        >>> client = WebSocketClient("ws://example.com/socket")
        >>> client.start()
        >>> client.send_sync("Hello, server!")
        >>> message = client.recv()
        >>> print(message)
        >>> client.disconnect()

    Note:
        该客户端假设 WebSocket 服务器支持标准的 WebSocket 协议。自动重连机制会在达到最大重连尝试次数后停止尝试连接。

    See Also:
        websockets: WebSocket 客户端和服务器库。
    """

    def __init__(
            self,
            uri: str,
            headers: dict[str, str] = {},
            initial_reconnect_interval: int = 5,
            max_reconnect_interval: int = 60,
            max_reconnect_attempts: int = 5,
            message_handler: Optional[MessageHandler] = None,
            close_handler: Optional[Callable[[], None]] = None,
            loop: Optional[asyncio.AbstractEventLoop] = None,
        ):
        """
        初始化 WebSocket 客户端。

        Args:
                uri (str): WebSocket 服务器的 URI。
                headers (dict[str, str]): 发送连接请求时附加的 HTTP 头。
                initial_reconnect_interval (int): 初始重连间隔时间（秒）。默认为 5 秒。
                max_reconnect_interval (int): 最大重连间隔时间（秒）。默认为 60 秒。
                max_reconnect_attempts (int): 最大重连尝试次数。默认为 5 次。
                message_handler (Optional[MessageHandler]): 用户定义的消息处理器回调函数。
                close_handler (Optional[Callable[[], None]]): 用户定义的连接关闭回调函数。
                loop (Optional[asyncio.AbstractEventLoop]): 事件循环实例。
        """
        self.uri = uri
        self.headers = headers
        self.initial_reconnect_interval = initial_reconnect_interval
        self.max_reconnect_interval = max_reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.message_handler = message_handler or None
        self.close_handler = close_handler
        self.loop = loop or asyncio.new_event_loop()
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self._closed = False
        self.reconnect_attempt = 0
        self._connect_task: Optional[asyncio.Task] = None
        self._message_deque = collections.deque(maxlen=64)
        self._message_available = threading.Event()
        self._deque_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._receive_task: Optional[asyncio.Task] = None

    def _default_message_handler(self, message: str) -> None:
        """
        默认消息处理器，打印日志。

        Args:
                message (str): 接收到的消息内容。
        """
        _LOG.debug(f"接收消息: {message}")

    def start(self) -> None:
        """
        启动客户端后台线程。

        该方法会创建一个新的线程来运行事件循环，并在事件循环中初始化 WebSocket 连接。
        """
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run_event_loop, 
                daemon=True,
                name="WebSocketClientThread"
            )
            self._thread.start()
            # 在事件循环中初始化连接
            asyncio.run_coroutine_threadsafe(self.connect_async(), self.loop)

    def _run_event_loop(self) -> None:
        """
        运行事件循环的线程目标函数。

        该方法设置当前线程的事件循环，并运行事件循环直到停止。
        """
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def connect_async(self) -> None:
        """
        异步建立 WebSocket 连接并启动消息接收循环。

        该方法尝试连接到 WebSocket 服务器，并在成功连接后启动消息接收任务。
        如果连接失败，会触发自动重连机制。
        """
        if self._closed or self.running:
            return
        try:
            self.websocket = await websockets.connect(
                self.uri,
                extra_headers=self.headers,
                ping_interval=None  # 禁用自动 ping/pong
            )
            self.running = True
            self.reconnect_attempt = 0
            _LOG.info(f"正在连接到: {self.uri}")
            # 启动消息接收任务
            self._receive_task = asyncio.create_task(self._receive_messages())
        except Exception as e:
            _LOG.error(f"连接失败: {e}")
            await self._handle_disconnect()

    async def _receive_messages(self) -> None:
        """
        持续接收消息并存储到队列。

        该方法从 WebSocket 连接中接收消息，并将其存储到消息队列中。
        同时，会调用用户定义的消息处理器回调函数处理接收到的消息。
        如果连接关闭或发生错误，会停止接收消息并触发自动重连机制。
        """
        while self.running and self.websocket is not None:
            try:
                message = await self.websocket.recv()
                self._add_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                _LOG.error(f"连接关闭: {e}")
                await self._handle_disconnect()
                break
            except Exception as e:
                _LOG.error(f"接收时出现错误: {e}")
                await self._handle_disconnect()
                break
            if self.message_handler:
                try:
                    # 调用用户定义的消息处理器
                    if asyncio.iscoroutinefunction(self.message_handler):
                        # 如果 message_handler 是异步函数
                        await self.message_handler(message)
                    else:
                        # 如果 message_handler 是同步函数
                        self.message_handler(message)
                except Exception as e:
                    _LOG.error(f"自定义处理器错误: {e}")
                    continue

    def _add_message(self, message: str) -> None:
        """
        线程安全地将消息添加到队列并触发事件。

        Args:
                message (str): 要添加的消息内容。
        """
        with self._deque_lock:
            self._message_deque.append(message)
        self._message_available.set()

    async def _handle_disconnect(self) -> None:
        """
        处理连接断开并触发自动重连。

        该方法关闭现有连接，，并根据重连策略尝试重新连接。
        如果达到最大重连尝试次数，会停止重连执行用户定义的关闭回调函数并关闭客户端。
        """

        if self._closed:
            return
        self.running = False
        # 关闭现有连接
        if self.websocket is not None:
            await self.websocket.close()
            self.websocket = None
        # 自动重连逻辑
        if self.reconnect_attempt < self.max_reconnect_attempts:
            self.reconnect_attempt += 1
            delay = min(
                self.initial_reconnect_interval * (2 ** (self.reconnect_attempt - 1)),
                self.max_reconnect_interval
            )
            _LOG.info(f"在{delay}s内重新连接({self.reconnect_attempt}/{self.max_reconnect_attempts})")
            await asyncio.sleep(delay)
            await self.connect_async()
        else:
            _LOG.error("已达到最大重新连接尝试次数")
            # 执行用户定义的关闭回调
            if self.close_handler:
                self.close_handler()
            self._closed = True

    async def send_async(self, data: Any, wait: bool = False) -> None:
        """
        异步发送数据。

        Args:
                data (Any): 要发送的数据内容。
                wait (bool): 是否等待发送完成。默认为 False。

        Raises:
                ConnectionError: 如果客户端未连接到 WebSocket 服务器。
        """
        if not self.running or self.websocket is None:
            raise ConnectionError("Not connected to WebSocket server")
        await self.websocket.send(data)
        if wait:
            return await self.websocket.recv()

    def send_sync(self, data: Any, timeout: Optional[float] = None) -> None:
        """
        同步发送数据（线程安全）。

        Args:
                data (Any): 要发送的数据内容。
                timeout (Optional[float]): 发送操作的超时时间（秒）。默认为 None。

        Raises:
                TimeoutError: 如果发送操作超时。
        """
        future = asyncio.run_coroutine_threadsafe(self.send_async(data, wait=True), self.loop)
        try:
            result = future.result(timeout=timeout)
            return result
        except FutureTimeoutError as e:
            raise TimeoutError("Send operation timed out") from e

    def recv(self, prefer: str = 'oldest', wait: bool = True) -> Optional[str]:
        """
        接收消息。

        Args:
                prefer (str): 消息选择策略，'oldest' 返回最早的消息，'newest' 返回最新消息。默认为 'oldest'。
                wait (bool): 如果队列为空，是否阻塞等待。默认为 True。

        Returns:
                Optional[str]: 接收到的消息内容，如果非阻塞且队列为空则返回 None。
        """
        while True:
            with self._deque_lock:
                if prefer == 'oldest' and self._message_deque:
                    return self._message_deque.popleft()
                elif prefer == 'newest' and self._message_deque:
                    return self._message_deque.pop()
            if not wait:
                return None
            # 等待消息到达事件
            self._message_available.wait()
            self._message_available.clear()

    async def disconnect_async(self, timeout: Optional[float] = None) -> None:
        """
        异步断开连接。

        Args:
                timeout (Optional[float]): 断开连接的超时时间（秒）。默认为 None。
        """
        self._closed = True
        self.running = False
        if self.websocket is not None:
            await self.websocket.close(timeout=timeout)
            self.websocket = None
        # 取消接收任务
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

    def disconnect(self, timeout: Optional[float] = None) -> None:
        """
        同步断开连接。

        Args:
                timeout (Optional[float]): 断开连接的超时时间（秒）。默认为 None。
        """
        future = asyncio.run_coroutine_threadsafe(
            self.disconnect_async(timeout), 
            self.loop
        )
        future.result()

    def cleanup(self) -> None:
        """
        清理资源。

        该方法断开连接，停止事件循环，关闭线程池执行器，并等待事件循环线程退出。
        """
        self.disconnect()
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._executor.shutdown(wait=False)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def __del__(self):
        """
        析构函数，清理资源。
        """
        self.cleanup()

    async def __aenter__(self):
        """
        异步上下文管理器的进入方法。

        该方法建立 WebSocket 连接并返回客户端实例。
        """
        await self.connect_async()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        异步上下文管理器的退出方法。

        该方法断开 WebSocket 连接。
        """
        await self.disconnect_async()