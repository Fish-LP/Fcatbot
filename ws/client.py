import asyncio
import random
import uuid
import threading
import queue
import json
import time
from typing import *
from concurrent.futures import ThreadPoolExecutor
from websockets.legacy.client import Connect
from websockets.exceptions import (
    ConnectionClosed,       # 连接关闭
    ConnectionClosedError,  # 连接错误(握手失败)
    ConnectionClosedOK,     # 正常关闭连接
)
from logging import Logger

class WebSocketClient:
    def __init__(
        self,
        *,
        uri: str,
        logger: Optional[Logger] = None,
        headers: Optional[Dict[str, str]] = None,
        ping_interval: float = 30,
        ping_timeout: float = 10,
        reconnect_attempts: int = 5,
        timeout: float = 20,
        auth: Optional[Dict[str, str]] = None,
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
        # 参数校验
        if not uri.startswith(("ws://", "wss://")):
            raise ValueError("无效的WebSocket URI")
        if ping_interval <= 0 or ping_timeout <= 0:
            raise ValueError("心跳间隔和超时必须大于0")
        if reconnect_attempts < 0:
            raise ValueError("重连尝试次数不能为负")
        
        # 设置
        self.uri = uri
        self.headers = headers or {}
        if auth:
            self.headers.update(auth)
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.reconnect_attempts = reconnect_attempts
        self.timeout = timeout
        self.max_queue_size = max_queue_size
        self.random_jitter = random_jitter
        self.logger = logger
        
        # 状态管理
        self._connected = threading.Event()
        self._closing = threading.Event()
        self._closed = threading.Event()
        
        # 队列系统
        self._send_queue = queue.Queue(maxsize=max_queue_size)
        self._receive_queue = queue.Queue(maxsize=max_queue_size)
        
        # 监听器系统
        self._listeners: Dict[str, queue.Queue] = {}
        self._listener_lock = threading.RLock()  # 使用可重入锁
        
        # 连接管理
        self._loop = asyncio.new_event_loop()
        self._connection_thread = threading.Thread(
            target=self._run_connection_loop,
            daemon=True,
            name=f"WSConnThread-{id(self)}"
        )
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix=f"WSWorker-{id(self)}"
        )

    def start(self):
        """启动客户端连接"""
        if self._closed.is_set():
            raise RuntimeError("客户端已关闭，无法重新启动")
        
        if self.logger:
            self.logger.info(f"启动WebSocket客户端，准备连接至 {self.uri}")
        
        self._connection_thread.start()
        if not self._connected.wait(timeout=self.timeout):
            if self.logger:
                self.logger.warning("初始连接超时，后台继续尝试连接")
    
    # 属性
    @property
    def connected(self) -> bool:
        """检查是否已连接"""
        return self._connected.is_set()
    
    @property
    def closing(self) -> bool:
        """检查是否正在关闭"""
        return self._closing.is_set()
    
    @property
    def closed(self) -> bool:
        """检查是否已关闭"""
        return self._closed.is_set()

    # 核心实现
    def _run_connection_loop(self):
        """运行连接管理的事件循环"""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connection_manager())
        except Exception as e:
            if self.logger:
                self.logger.critical(f"连接管理器意外终止: {e}")
        finally:
            # 清理资源
            self._loop.close()
            self._closed.set()
            if self.logger:
                self.logger.info("连接管理器已完全停止")

    async def _connection_manager(self):
        """连接管理协程，处理连接、重连和心跳"""
        reconnect_attempt = 0
        base_delay = 1.0
        max_delay = 60.0
        
        while not self._closing.is_set():
            try:
                # 连接前日志
                if self.logger:
                    self.logger.info(f"尝试连接至 {self.uri} (尝试 {reconnect_attempt+1}/{self.reconnect_attempts})")
                
                # 建立连接
                async with Connect(
                    uri=self.uri,
                    extra_headers=self.headers,
                    timeout=self.timeout,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout,
                ) as ws:
                    # 连接成功
                    self._connected.set()
                    reconnect_attempt = 0
                    
                    if self.logger:
                        self.logger.info(f"成功连接到 {self.uri}")
                    
                    # 创建任务
                    tasks = [
                        asyncio.create_task(self._receive_messages(ws), name="receive"),
                        asyncio.create_task(self._send_messages(ws), name="send"),
                        asyncio.create_task(self._monitor_connection(ws), name="monitor")
                    ]
                    
                    # 等待任务完成
                    done, pending = await asyncio.wait(
                        tasks,
                        return_when=asyncio.FIRST_EXCEPTION
                    )
                    
                    # 取消剩余任务
                    for task in pending:
                        task.cancel()
                    
                    # 记录任务结果
                    for task in done:
                        try:
                            await task
                        except Exception as e:
                            if self.logger:
                                self.logger.error(f"任务 {task.get_name()} 异常: {e}")
                    
                    # 检查关闭原因
                    if not self._closing.is_set():
                        if self.logger:
                            self.logger.warning("连接意外断开，准备重连")
            
            except (ConnectionClosedOK, ConnectionClosedError) as e:
                if self.logger:
                    code = e.code if hasattr(e, 'code') else 1006
                    reason = e.reason if hasattr(e, 'reason') else "未知原因"
                    self.logger.warning(f"连接关闭: 代码={code}, 原因={reason}")
            except asyncio.TimeoutError:
                if self.logger:
                    self.logger.warning("连接超时")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"连接错误: {type(e).__name__}: {e}")
            
            # 重连逻辑
            if not self._closing.is_set():
                self._connected.clear()
                reconnect_attempt += 1
                
                if reconnect_attempt > self.reconnect_attempts:
                    if self.logger:
                        self.logger.error(f"达到最大重连尝试次数 ({self.reconnect_attempts})")
                    break
                
                # 指数退避 + 随机抖动
                delay = min(base_delay * (2 ** (reconnect_attempt - 1)), max_delay)
                jitter = random.uniform(0, self.random_jitter)
                total_delay = delay + jitter
                
                if self.logger:
                    self.logger.info(f"将在 {total_delay:.2f} 秒后尝试重连 ({reconnect_attempt}/{self.reconnect_attempts})")
                
                await asyncio.sleep(total_delay)
        
        # 清理关闭
        self._closing.set()
        self._closed.set()
        if self.logger:
            self.logger.info("连接管理器停止")

    async def _receive_messages(self, ws: Connect):
        """接收消息并分发到监听器"""
        if self.logger:
            self.logger.debug("开始接收消息循环")
        
        try:
            while self.connected and not self.closing:
                try:
                    message = await asyncio.wait_for(
                        ws.recv(),
                        timeout=self.ping_interval + self.ping_timeout
                    )
                    
                    # 分发消息
                    self._broadcast_message(message)
                    
                except asyncio.TimeoutError:
                    # 正常超时，继续循环
                    continue
                except ConnectionClosed:
                    if self.logger:
                        self.logger.warning("接收循环中检测到连接关闭")
                    break
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"接收消息错误: {type(e).__name__}: {e}")
                    break
        finally:
            if self.logger:
                self.logger.debug("接收消息循环结束")

    def _broadcast_message(self, message: Any):
        """广播消息到所有监听器（线程安全）"""
        with self._listener_lock:
            # 创建监听器的快照避免在广播时修改
            listeners = list(self._listeners.items())
        
        # 使用线程池异步处理分发
        def _deliver(qid, queue, msg):
            try:
                if queue.full():
                    if self.logger:
                        self.logger.warning(f"监听器 {qid} 队列已满，丢弃消息")
                    return
                queue.put_nowait(msg)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"分发消息到监听器 {qid} 失败: {e}")
        
        for listener_id, q in listeners:
            self._executor.submit(_deliver, listener_id, q, message)

    async def _send_messages(self, ws: Connect):
        """从队列中获取消息并发送"""
        if self.logger:
            self.logger.debug("开始发送消息循环")
        
        try:
            while self.connected and not self.closing:
                try:
                    # 非阻塞获取消息
                    try:
                        message = self._send_queue.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.01)
                        continue
                    
                    # 发送消息
                    if self.logger:
                        self.logger.debug(f"发送消息: {message[:100]}{'...' if len(message) > 100 else ''}")
                    
                    await ws.send(message)
                    self._send_queue.task_done()
                    
                except ConnectionClosed:
                    if self.logger:
                        self.logger.warning("发送循环中检测到连接关闭")
                    # 将消息放回队列（如果可能）
                    if not self._send_queue.full():
                        self._send_queue.put(message)
                    break
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"发送消息失败: {type(e).__name__}: {e}")
                    self._send_queue.task_done()  # 即使失败也标记完成
        finally:
            if self.logger:
                self.logger.debug("发送消息循环结束")

    async def _monitor_connection(self, ws: Connect):
        """监控连接状态"""
        if self.logger:
            self.logger.debug("开始连接监控循环")
        
        try:
            while self.connected and not self.closing:
                await asyncio.sleep(self.ping_interval)
                
                # 简单检查连接是否活跃
                if not ws.open:
                    if self.logger:
                        self.logger.warning("监控检测到连接已关闭")
                    break
        finally:
            if self.logger:
                self.logger.debug("连接监控循环结束")

    # 公共接口
    def send(self, message: Union[str, bytes, dict]):
        """
        非阻塞发送消息
        
        Args:
            message: 可以是字符串、字节或字典（自动序列化为JSON）
        """
        if self.closing or self.closed:
            raise ConnectionError("连接正在关闭或已关闭")
        
        # 格式化消息
        if isinstance(message, dict):
            formatted = json.dumps(message)
        elif isinstance(message, bytes):
            formatted = message
        else:
            formatted = str(message).encode('utf-8')
        
        try:
            self._send_queue.put_nowait(formatted)
        except queue.Full:
            # 队列满时丢弃最旧的消息
            try:
                self._send_queue.get_nowait()
                self._send_queue.task_done()
                self._send_queue.put_nowait(formatted)
                if self.logger:
                    self.logger.warning("发送队列已满，丢弃最旧的消息")
            except queue.Empty:
                # 如果队列在获取时变空，重试
                self._send_queue.put_nowait(formatted)

    def create_listener(self, queue_size: int = 127) -> str:
        """
        创建消息监听器
        
        Return:
            监听器ID，用于接收消息
        """
        listener_id = str(uuid.uuid4())
        q = queue.Queue(maxsize=queue_size)
        
        with self._listener_lock:
            self._listeners[listener_id] = q
        
        if self.logger:
            self.logger.debug(f"创建监听器: {listener_id}")
        
        return listener_id

    def remove_listener(self, listener_id: str):
        """移除消息监听器"""
        with self._listener_lock:
            if listener_id in self._listeners:
                # 清空队列避免内存泄漏
                q = self._listeners.pop(listener_id)
                while not q.empty():
                    try:
                        q.get_nowait()
                        q.task_done()
                    except queue.Empty:
                        break
                if self.logger:
                    self.logger.debug(f"移除监听器: {listener_id}")

    def get_message(self, listener_id: str, timeout: Optional[float] = 1) -> Any:
        """
        从监听器获取消息
        
        Args:
            listener_id: 监听器ID
            timeout: 超时时间(秒)
            
        Return:
            消息内容，超时返回None
        """
        if self.closed:
            return None
        
        try:
            with self._listener_lock:
                q = self._listeners.get(listener_id)
            
            if q is None:
                raise ValueError(f"无效的监听器ID: {listener_id}")
            
            return q.get(timeout=timeout)
        except queue.Empty:
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"获取消息错误: {e}")
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
        listener_id = self.create_listener(queue_size=5)
        
        try:
            self.send(request)
            
            start_time = time.monotonic()
            while time.monotonic() - start_time < timeout:
                message = self.get_message(listener_id, timeout=0.1)
                if message is None:
                    continue
                
                try:
                    if response_matcher(message):
                        return message
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"响应匹配器错误: {e}")
        finally:
            self.remove_listener(listener_id)
        
        if self.logger:
            self.logger.warning(f"请求超时 (timeout={timeout}s)")
        return None

    def close(self, timeout: float = 5.0):
        """关闭连接"""
        if self.closed:
            return
        
        if self.logger:
            self.logger.info("正在关闭WebSocket客户端...")
        
        self._closing.set()
        self._connected.clear()
        
        # 等待连接线程停止
        if self._connection_thread.is_alive():
            self._connection_thread.join(timeout=timeout)
        
        # 清理资源
        with self._listener_lock:
            for qid in list(self._listeners.keys()):
                self.remove_listener(qid)
        
        # 清空队列
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
                self._send_queue.task_done()
            except queue.Empty:
                break
        
        self._closed.set()
        
        if self.logger:
            self.logger.info("WebSocket客户端已关闭")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        if not self.closed:
            self.close()