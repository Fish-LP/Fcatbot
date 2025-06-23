import asyncio
import random
import uuid
import threading
import queue
import json
import time
from typing import *
from concurrent.futures import ThreadPoolExecutor
from websockets.legacy.client import WebSocketClientProtocol
from websockets.exceptions import (
    ConnectionClosed,       # 连接关闭
    ConnectionClosedError,  # 连接错误(握手失败)
    ConnectionClosedOK,     # 正常关闭连接
)
from logging import Logger

class WebSocketClient:
    def __init__(
        self,
        uri: str,
        logger: Optional[Logger] = None,
        headers: Optional[Dict[str, str]] = {},
        ping_interval: float = 30.0,
        ping_timeout: float = 5.0,
        reconnect_attempts: int = 3,
        timeout: float = 10.0,
        auth: Optional[Dict[str, str]] = {},
        max_queue_size: int = 127,
        random_jitter: float = 0.5,
    ):
        """
        WebSocket 客户端
        
        Args:
            uri: WebSocket 服务器地址
            logger: 日志记录器(为空不输出日志)
            headers: 连接头信息
            ping_interval: 心跳间隔（秒）
            ping_timeout: 心跳超时（秒）
            reconnect_attempts: 最大重试次数
            timeout: 连接/读写操作超时时间（秒）
            auth: 认证信息（用于需要认证的 WebSocket 服务器）
            max_queue_size: 消息队列最大大小
            random_jitter: 重连随机延迟因子
        """
        # 设置
        self.uri = uri
        '''连接地址'''
        self.headers = headers.update(auth)
        '''连接头 + 认证信息'''
        self.ping_interval = ping_interval
        '''心跳间隔(秒)'''
        self.ping_timeout = ping_timeout
        '''心跳超时(秒)'''
        self.reconnect_attempts = reconnect_attempts
        '''最大重试次数'''
        self.timeout = timeout
        '''操作超时时间（秒）'''
        self.max_queue_size = max_queue_size
        '''消息队列最大大小'''
        self.random_jitter = random_jitter
        '''重连随机延迟因子'''
        self.logger = logger
        '''日志记录器'''
        self.uri = uri
        '''连接地址'''
        self.headers = headers
        '''连接头'''
        self.ping_interval = ping_interval
        '''心跳间隔(秒)'''
        self.ping_timeout = ping_timeout
        '''心跳超时(秒)'''
        
        # 状态
        self._connected = threading.Event()
        '''连接状态'''
        self._closing = threading.Event()
        '''关闭信号'''
        self._closed = threading.Event()
        '''关闭标志'''
        
        # 队列系统
        self._send_queue = queue.Queue(maxsize=127)
        '''发送队列'''
        self._receive_queue = queue.Queue(maxsize=127)
        '''接收队列'''
        
        self._listeners: Dict[str, queue.Queue] = {}
        '''监听器管道''' # 收到消息后广播copy的消息(我tm直接广播，分什么类)
        self._listener_lock = threading.Lock()
        '''监听器管道锁'''
        
        # 异步事件循环和线程
        self._loop = asyncio.new_event_loop()
        '''异步循环'''
        self._connection_thread = threading.Thread(
            target=self._run_connection_loop,
            daemon=True,
            name="WebSocketConnectionThread"
        )
        '''ws客户端线程'''

    def start(self):
        self._connection_thread.start()
        # 等待连接就绪
        self._connected.wait(timeout=self.ping_timeout)

    # 属性
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected.is_set()
    @property
    def connected(self) -> bool:
        """检查是否已连接"""
        return self._connected.is_set()

    # 实现
    def _run_connection_loop(self):
        """运行连接管理的事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connection_manager())

    async def _connection_manager(self):
        """连接管理协程，处理连接、重连和心跳"""
        reconnect_attempt = 0   # 重连次数
        base_delay = self.ping_interval
        max_delay = 30.0    # 最大重连等待时间
        logger = self.logger
        
        # 建立连接
        while not self._closing.is_set():
            try:
                self._connected.clear()
                async with WebSocketClientProtocol(
                    self.uri,
                    extra_headers=self.headers,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout
                ) as ws:
                    # 更新连接状态
                    self._connected.set()
                    reconnect_attempt = 0
                    
                    # 启动
                    receive_task = asyncio.create_task(self._receive_messages(ws))
                    send_task = asyncio.create_task(self._send_messages(ws))
                    ping_task = asyncio.create_task(self._monitor_ping(ws))
                    
                    # 等待任何任务完成或关闭信号
                    done, pending = await asyncio.wait(
                        {receive_task, send_task, ping_task},
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # 取消所有任务
                    for task in pending:
                        task.cancel()
                    
                    # 检查关闭原因
                    if self._closing.is_set():
                        pass
                    elif ping_task in done:
                        if logger: logger.warning("检测到Ping超时，重新连接...")
                    elif receive_task in done:
                        if logger: logger.warning("接收任务终止，正在重新连接...")
                    
            except Exception as e:
                self.logger.error(f"连接错误: {e}")
            
            # 重连
            if not self._closing.is_set():
                reconnect_attempt += 1
                if reconnect_attempt > self.reconnect_attempts:
                    if logger: logger.error("达到的最大重连尝试数")
                    break
                
                delay = min(base_delay * (2 ** (reconnect_attempt - 1)), max_delay)
                if logger: logger.info(f"重连: {delay:.1f}s ({reconnect_attempt}/{self.reconnect_attempts})")
                await asyncio.sleep(delay + random.uniform(0, self.random_jitter))
        
        # 清理关闭
        self._closed.set()
        if logger: logger.debug("连接管理器已停止")

    async def _receive_messages(self, ws: WebSocketClientProtocol):
        """接收消息并分发到监听器"""
        logger = self.logger
        
        while not self._closing.is_set():
            try:
                message = await asyncio.wait_for(
                    ws.recv(),  # 如果网络不稳定，ws.recv() 可能会阻塞较长时间。
                    timeout=self.ping_interval + 1.0    # 所以加入这个
                )
                
                # 分发到所有监听器
                with self._listener_lock:
                    for listener_id, q in self._listeners.items():
                        if q.not_full:
                            q.put_nowait(message)
                        else:
                            if logger: logger.warning(f"监听器 '{listener_id}' 队列已满，消息被丢弃")
                
            except asyncio.TimeoutError:
                # 正常超时，继续循环
                continue
            except ConnectionClosedOK:
                # 正常关闭
                break
            except ConnectionClosedError as e:
                # e.code 属性用于向后兼容
                if logger: logger.warning(f"连接被错误的关闭, 错误代码: {1006 if e.rcvd is None else e.rcvd.code}")
                break
            except Exception as e:
                if logger: logger.error(f"未知接收时错误: {e}")
                break

    async def _send_messages(self, ws: WebSocketClientProtocol):
        """从队列中获取消息并发送"""
        logger = self.logger
        
        while not self._closing.is_set():
            try:
                if self._send_queue.empty():
                    await asyncio.sleep(0)  # 交还控制权给事件循环
                    continue
                else:
                    message = self._send_queue.get_nowait()
                
                # 发送消息
                try:
                    await ws.send(message)
                except ConnectionClosed:
                    # 重新放入队列，如果可以
                    if self._send_queue.not_full:
                        self._send_queue.put(message)
                        if logger: logger.warning("在发送消息期间关闭连接，消息被放回队列")
                    else:
                        self.logger.warning("在发送消息期间关闭连接，因为队列已满，消息被丢弃")
                    break
                except Exception as e:
                    if logger: logger.error(f"发送错误(消息被丢弃): {e}")
                    # 丢弃无法发送的消息
                
                # 标记任务完成
                self._send_queue.task_done()
                    
            except Exception as e:
                if logger: logger.error(f"未知发送错误: {e}")

    async def _monitor_ping(self, ws: WebSocketClientProtocol):
        """监控连接状态"""
        while not self._closing.is_set():
            try:
                # ping
                pong_waiter = await ws.ping()
                latency = asyncio.wait_for(
                    pong_waiter,
                    timeout=self.ping_timeout,
                )
                
                await asyncio.sleep(self.ping_interval)
                
            except ConnectionClosed:
                # 忽略关闭行为导致的错误
                return
            except TimeoutError:
                # 超时
                # _LOG.warning("Ping 超时") #   外部已经有提示
                return
            except Exception as e:
                if self.logger: self.logger.error(f"Ping错误: {e}")
                return  

    def send(self, message: Union[str, bytes, dict]):
        """
        非阻塞发送消息
        
        Args:
            message: 可以是字符串、字节或字典（自动序列化为JSON）
        """
        if self._closing.is_set() or self._closed.is_set():
            raise ConnectionError("连接正在关闭或已关闭")
        
        # 格式化消息
        if isinstance(message, dict):
            formatted = json.dumps(message)
        elif isinstance(message, bytes):
            formatted = message
        else:
            formatted = str(message)
        
        try:
            self._send_queue.put_nowait(formatted)
        except queue.Full:
            # 队列满时丢弃最旧的消息
            try:
                # 丢弃最旧的消息
                self._send_queue.get_nowait()
                self._send_queue.task_done()
            except queue.Empty:
                pass
            self._send_queue.put_nowait(formatted)
            if self.logger: self.logger.warning("发送队列已满, 丢弃最旧的消息")

    def create_listener(self, queue_size: int = 127) -> str:
        """
        创建消息监听器
        
        Return:
            监听器ID，用于接收消息
        """
        listener_id = uuid.uuid4()
        q = queue.Queue(maxsize=queue_size)
        
        with self._listener_lock:
            self._listeners[listener_id] = q
        
        return listener_id

    def remove_listener(self, listener_id: str):
        """移除消息监听器"""
        with self._listener_lock:
            if listener_id in self._listeners:
                del self._listeners[listener_id]

    def get_message(self, listener_id: uuid.UUID, timeout: Optional[float] = None) -> Any:
        """
        从监听器获取消息
        
        Args:
            listener_id: 监听器ID
            timeout: 超时时间(秒)
            
        Return:
            消息内容，超时返回None
        """
        if self._closed.is_set():
            return None
        
        try:
            with self._listener_lock:
                q = self._listeners.get(listener_id)
            
            if q is None:
                raise ValueError(f"无效的监听器ID: {listener_id}")
            
            return q.get(timeout=timeout)
        except queue.Empty:
            return None

    def request(
        self, 
        request: Union[str, dict], 
        response_matcher: Callable[[Any], bool],
        timeout: float = 5.0
    ) -> Any:
        """
        发送请求并等待响应
        
        Args:
            request: 请求内容
            response_matcher: 响应匹配函数
            timeout: 超时时间(秒)
            
        Return:
            匹配的响应消息，超时返回None
        """
        # 创建专用监听器
        listener_id = self.create_listener(queue_size=5)
        
        try:
            # 发送请求
            self.send(request)
            
            # 等待匹配的响应
            start_time = time.monotonic()
            while time.monotonic() - start_time < timeout:
                message = self.get_message(listener_id, timeout=0.1)
                if message is None:
                    continue
                
                # 尝试匹配响应
                try:
                    if response_matcher(message):
                        return message
                except Exception as e:
                    if self.logger: self.logger.error(f"响应匹配器错误: {e}")
            
            return None  # 超时
        finally:
            self.remove_listener(listener_id)

    def close(self, timeout: float = 5.0):
        """关闭连接"""
        if self._closed.is_set():
            return
        
        self._closing.set()
        self._closed.wait(timeout=timeout)
        
        # 清理资源
        with self._listener_lock:
            self._listeners.clear()
        
        # 清空队列
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
                self._send_queue.task_done()
            except queue.Empty:
                break

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        # 不可靠
        self.close()