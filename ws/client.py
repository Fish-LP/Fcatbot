# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:59:15
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-16 18:38:48
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from typing import Optional, Callable
import asyncio
import websockets
import collections  # 用于双端队列

import websockets.client

from ..utils import get_log

# 日志工具
_LOG = get_log('WebSocketClient')

# 自定义处理器类型: 接受一个字符串参数、返回 None
MessageHandler = Callable[[str], bool]

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
        """处理接收消息，自动存入队列并触发事件。"""
        async for msg in self.websocket:
            _LOG.debug(f"收到消息: {msg}")
            self._message_deque.append(msg)
            self._message_available.set()  # 触发有新消息
            # 若有自定义处理器，异步调用
            if self.message_handler:
                asyncio.create_task(self._invoke_handler(msg))

    async def _invoke_handler(self, data: str):
        """
        调用用户提供的自定义消息处理器。

        :param data: 接收到的消息内容
        """
        try:
            # 调用自定义处理器,处理接收到的消息
            return await self.message_handler(data)
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
            # 获取或创建事件循环
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # 运行客户端
            loop.run_until_complete(self._start_client())
        
        except KeyboardInterrupt:
            # 处理用户中断
            if self.close_handler:
                try:
                    print()
                    self.close_handler()
                except Exception as e:
                    _LOG.error(f"自定义关闭函数产生错误: {e}")
            raise  # 确保 KeyboardInterrupt 被重新抛出
        
        except Exception as e:
            _LOG.error(f"客户端启动时发生错误: {e}")
        
        finally:
            # 确保断开连接
            try:
                if loop.is_running():
                    loop.call_soon_threadsafe(loop.stop)
                elif not loop.is_closed():
                    loop.run_until_complete(self.disconnect(5))
            except NameError:
                # 如果 loop 未定义（如初始化失败），直接运行 disconnect
                asyncio.run(self.disconnect(5))
            
            # 关闭循环（如果存在）
            if 'loop' in locals() and not loop.is_closed():
                loop.close()

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

    async def send_data(
        self, 
        data: str, 
        wait: bool = True, 
        response_prefer: str = 'oldest'
    ) -> Optional[str]:
        """
        发送数据并可选等待响应。

        :param data: 要发送的数据。
        :param wait: 是否等待响应，默认是。
        :param response_prefer: 响应获取方式，默认'oldest'。
        :return: 响应内容或发送状态。
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

    async def recv(
        self,
        *,
        prefer: str = 'latest',
        wait: bool = False
    ) -> Optional[str]:
        """
        接收 WebSocket 消息。可选最新/最旧，支持等待新消息。

        :param prefer: 'latest'（默认）取最新，'oldest'取最旧。
        :param wait: 无消息时是否阻塞等待，默认否。
        :return: 消息内容，无消息且不等待时返回None。
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