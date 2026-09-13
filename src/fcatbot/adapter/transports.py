"""连接件（Transport）: 与外部平台之间的字节收发，并向总线发布 ``RawEvent``。

设计依据: ``docs/architecture.md`` §3.4（行 172-174 / 408）；ADR-0003；ADR-0001。

职责边界（ADR-0003 决策 C: 「框架管传输（帧级）+ 插件管协议」）
----------------------------------------------------------------
- **Transport 只管字节进出**: 连接生命周期、收发帧、发布 ``RawEvent``；
- 协议解析、``Bot`` / ``Contact`` 维护、平台事件发布、出站动作，全部由**适配器插件**负责；
- 适配器也可自带 Transport 实现（SSE、私有协议等），只需遵守「向总线发布 ``RawEvent``」。

内置连接件（本次范围: **正向 WS + HTTP**）
------------------------------------------
- :class:`ForwardWebSocketTransport` —— **正向 WebSocket**: 本框架作为客户端主动连接
  平台 WS 端点，收发双向帧（OneBot 正向 WS 形态）。
- :class:`HttpTransport` —— **HTTP**: 内置 aiohttp 服务器接收事件上报（HTTP POST 回调）
  → ``RawEvent``；并可选配置 ``api_base_url`` 作为出站 HTTP API 客户端。

暂不实现: 反向 WebSocket（平台回连本框架）、SSE 等——按需在适配器侧自带实现
（见 ADR-0003「备选方案 B / 影响」）。

事件键约定: ``raw.<transport>.<kind>``；``transport`` 取类属性 ``transport``，
``kind`` 由帧内容推断（``post_type`` / ``type`` / ``kind`` 字段）或由
``kind_extractor`` 自定义。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Callable, ClassVar

import aiohttp
from aiohttp import web

from fcatbot.kernel.events import EventBus, RawEvent

log = logging.getLogger("fcatbot.transport")


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class TransportError(Exception):
    """连接件错误的基类。"""


class TransportNotConnected(TransportError):
    """连接尚未就绪（未连接 / 已关闭），无法收发。"""


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def default_kind_extractor(payload: Any) -> str:
    """从原始载荷推断 ``RawEvent.kind`` 的默认实现。

    识别常见上报字段（``post_type`` / ``type`` / ``kind``）；无法识别时返回 ``"message"``。
    适配器可传入自定义 ``kind_extractor`` 覆盖。
    """
    if isinstance(payload, Mapping):
        for key in ("post_type", "type", "kind"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return "message"


KindExtractor = Callable[[Any], str]

RawListener = Callable[[Any, str], Any]
"""帧级直通监听器: ``listener(payload, kind)``，同步或异步（异步将被调度执行）。"""


# ---------------------------------------------------------------------------
# 协议基座
# ---------------------------------------------------------------------------


class Transport(ABC):
    """连接件协议: 连接生命周期 + 收发 + 发布 ``RawEvent``。

    子类至少实现 :meth:`start` / :meth:`stop` / :meth:`send`；

    - ``transport``（类属性）用于组装事件键 ``raw.<transport>.<kind>``；
    - :meth:`publish_raw` 是向总线发布原始事件的统一入口（收发两侧的「抓包」接口）。
    """

    transport: ClassVar[str] = ""

    def __init__(self, bus: EventBus, *, name: str | None = None) -> None:
        self._bus = bus
        self._name = name or self.transport or type(self).__name__
        self._running = False
        self._raw_listeners: list[RawListener] = []

    # ---------- 只读属性 ----------

    @property
    def name(self) -> str:
        """连接件实例名（用于日志 / 诊断）。"""
        return self._name

    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def running(self) -> bool:
        """是否已启动（``start()`` 与 ``stop()`` 之间）。"""
        return self._running

    # ---------- 生命周期（子类实现） ----------

    @abstractmethod
    async def start(self) -> None:
        """建立连接 / 开始监听（幂等）。"""

    @abstractmethod
    async def stop(self) -> None:
        """断开连接 / 停止监听（幂等，安全重复调用）。"""

    @abstractmethod
    async def send(self, payload: Any) -> Any:
        """向外部平台发送一帧；返回平台应答（无应答时为 ``None``）。"""

    # ---------- 帧级直通（旁路总线） ----------

    def add_raw_listener(self, listener: RawListener) -> Callable[[], None]:
        """注册**帧级直通**监听器，返回注销函数。

        用途: 协议层需要在总线派发**之外**拿到原始帧时使用（典型场景是
        OneBot 式「出站请求 → 入站应答」的 ``echo`` 路由）。

        与 ``raw.*`` 事件订阅的关键差别:

        - 监听器在**收帧任务**中被调用，不经过单 worker 总线队列；
        - 因此**不会**与正在执行的事件处理器互相等待——若改用事件订阅做应答
          路由，当调用方本身就处于事件处理器内时会死锁（worker 正被占用，
          应答事件永远排不到）；
        - 监听器应当是**快速、非阻塞**的: 同步函数直接调用；返回可等待对象时
          会以 ``ensure_future`` 调度（fire-and-forget）。异常被隔离，不影响收帧。
        """
        self._raw_listeners.append(listener)

        def _remove() -> None:
            try:
                self._raw_listeners.remove(listener)
            except ValueError:
                pass

        return _remove

    def remove_raw_listener(self, listener: RawListener) -> bool:
        """注销帧级直通监听器（幂等）。返回是否发生了移除。"""
        try:
            self._raw_listeners.remove(listener)
            return True
        except ValueError:
            return False

    def _notify_raw_listeners(self, payload: Any, kind: str) -> None:
        """把原始帧推送给直通监听器（在收帧任务内调用，异常隔离）。"""
        for listener in tuple(self._raw_listeners):
            try:
                result = listener(payload, kind)
                if inspect.isawaitable(result):
                    asyncio.ensure_future(result)
            except Exception:
                log.exception("原始帧监听器执行失败: %r", listener)

    # ---------- 发布原始事件 ----------

    def build_raw(
        self,
        kind: str,
        data: Any = None,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RawEvent:
        """构造一条 ``RawEvent``（不发布）。

        ``source`` 取自连接件实例名（:attr:`name`），便于在日志/调试中识别
        事件的发送源；``transport`` 字段仍用于组装事件键 ``raw.<transport>.<kind>``。
        """
        event = RawEvent(transport=self.transport, kind=kind, data=data)
        event.source = self._name
        if metadata:
            event.metadata = dict(metadata)
        return event

    async def publish_raw(
        self,
        kind: str,
        data: Any = None,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RawEvent:
        """构造并**等待分发完成**后发布 ``RawEvent``（提供背压）。"""
        return await self._bus.publish(self.build_raw(kind, data, metadata=metadata))

    def publish_raw_nowait(
        self,
        kind: str,
        data: Any = None,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> RawEvent:
        """构造并**立即入队**发布 ``RawEvent``（不等待分发）。"""
        return self._bus.publish_nowait(self.build_raw(kind, data, metadata=metadata))

    # ---------- 便利 ----------

    async def __aenter__(self) -> "Transport":
        await self.start()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.stop()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self._name!r} running={self._running}>"


# ---------------------------------------------------------------------------
# 正向 WebSocket
# ---------------------------------------------------------------------------


class ForwardWebSocketTransport(Transport):
    """正向 WebSocket 连接件（客户端主动连接平台）。

    - ``start()`` 后由后台任务负责连接与**自动重连**（指数退避）；
    - 收到文本帧（尝试 JSON 解析）/ 二进制帧 → 发布 ``RawEvent``（``raw.ws.<kind>``）；
    - 连接建立 / 断开时分别发布 ``raw.ws.connected`` / ``raw.ws.disconnected``；
    - :meth:`send` 向连接写入一帧（``bytes`` → 二进制；``str`` → 文本；其余 → JSON）。
    """

    transport = "ws"

    def __init__(
        self,
        bus: EventBus,
        url: str,
        *,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
        reconnect: bool = True,
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        heartbeat: float | None = 30.0,
        kind_extractor: KindExtractor | None = None,
        session: aiohttp.ClientSession | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(bus, name=name)
        self._url = url
        self._headers = dict(headers or {})
        if token:
            self._headers.setdefault("Authorization", f"Bearer {token}")
        self._reconnect = reconnect
        self._reconnect_delay = max(0.0, reconnect_delay)
        self._max_reconnect_delay = max(self._reconnect_delay, max_reconnect_delay)
        self._heartbeat = heartbeat
        self._kind_extractor = kind_extractor or default_kind_extractor

        self._session = session
        self._owns_session = session is None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        self._task = asyncio.create_task(self._run(), name=f"transport:{self._name}")

    async def stop(self) -> None:
        if not self._running and self._task is None:
            return
        self._running = False
        self._stop_event.set()

        if self._ws is not None and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                log.debug("WS 关闭异常", exc_info=True)
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("WS 后台任务退出异常")
            self._task = None
        self._ws = None

        if (
            self._owns_session
            and self._session is not None
            and not self._session.closed
        ):
            await self._session.close()
        self._session = None

    # ---------- 收发 ----------

    @property
    def url(self) -> str:
        """平台 WS 端点。"""
        return self._url

    @property
    def connected(self) -> bool:
        """当前是否持有可用连接。"""
        return self._ws is not None and not self._ws.closed

    async def send(self, payload: Any) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            raise TransportNotConnected(f"{self._name} 尚未连接: {self._url}")
        if isinstance(payload, (bytes, bytearray, memoryview)):
            await ws.send_bytes(bytes(payload))
        elif isinstance(payload, str):
            await ws.send_str(payload)
        else:
            await ws.send_json(payload)

    # ---------- 后台连接循环 ----------

    async def _run(self) -> None:
        delay = self._reconnect_delay
        while not self._stop_event.is_set():
            connected = False
            session = self._session
            if session is None or session.closed:
                break
            try:
                async with session.ws_connect(
                    self._url,
                    headers=self._headers or None,
                    heartbeat=self._heartbeat,
                ) as ws:
                    self._ws = ws
                    connected = True
                    delay = self._reconnect_delay
                    await self.publish_raw(
                        "connected", None, metadata={"url": self._url}
                    )
                    await self._read_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("%s 连接异常: %s", self._name, exc)
            finally:
                self._ws = None
                if connected:
                    self._publish_disconnected()

            if self._stop_event.is_set() or not self._reconnect:
                break
            log.info("%s 将在 %.1fs 后重连: %s", self._name, delay, self._url)
            await self._sleep_or_stop(delay)
            delay = min(
                delay * 2 if delay else self._reconnect_delay, self._max_reconnect_delay
            )

    async def _read_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._handle_payload(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await self._handle_payload(msg.data)
            elif msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                break
            # PING / PONG 由 aiohttp 自动处理（heartbeat），无需干预

    async def _handle_payload(self, raw: Any) -> None:
        payload = _maybe_json(raw)
        kind = self._kind_extractor(payload)
        # 先直通协议层（旁路总线，避免与事件处理器互相等待），再走总线分发。
        self._notify_raw_listeners(payload, kind)
        await self.publish_raw(kind, payload)

    def _publish_disconnected(self) -> None:
        # 断开通知使用 nowait: 避免在任务取消 / 总线关闭的收尾路径上再 await。
        try:
            self.publish_raw_nowait("disconnected", None, metadata={"url": self._url})
        except Exception:
            log.debug("发布 disconnected 失败", exc_info=True)

    async def _sleep_or_stop(self, delay: float) -> None:
        if delay <= 0:
            return
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass


# ---------------------------------------------------------------------------
# HTTP（回调服务器 + 可选出站 API）
# ---------------------------------------------------------------------------


class HttpTransport(Transport):
    """HTTP 连接件: **回调服务器**（入站）+ 可选 **HTTP API 客户端**（出站）。

    入站
    ----
    内置 aiohttp Web 服务器监听 ``host:port`` 的 ``path``（默认 ``/``）；收到 POST 时
    解析请求体（优先 JSON，否则文本）→ 发布 ``raw.http.<kind>``；响应 ``{"status": "ok"}``。

    出站
    ----
    配置 ``api_base_url`` 后可用 :meth:`send`: 把 ``payload`` **原样**作为 JSON
    ``POST`` 到 ``api_base_url``。连接件不解释动作 / 信封语义——那属于适配器。

    未配置 ``api_base_url`` 时 :meth:`send` 抛 :class:`TransportNotConnected`
    （纯回调模式，出站由适配器自备客户端）。
    """

    transport = "http"

    def __init__(
        self,
        bus: EventBus,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
        path: str = "/",
        api_base_url: str | None = None,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
        kind_extractor: KindExtractor | None = None,
        name: str | None = None,
    ) -> None:
        super().__init__(bus, name=name)
        self._host = host
        self._port = port
        self._path = path if path.startswith("/") else f"/{path}"
        self._api_base_url = api_base_url.rstrip("/") if api_base_url else None
        self._headers = dict(headers or {})
        if token:
            self._headers.setdefault("Authorization", f"Bearer {token}")
        self._kind_extractor = kind_extractor or default_kind_extractor

        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._session: aiohttp.ClientSession | None = None
        self._bound_port: int | None = None

    # ---------- 只读属性 ----------

    @property
    def port(self) -> int:
        """实际监听端口（``port=0`` 时由系统分配，``start()`` 后可读）。"""
        return self._bound_port if self._bound_port is not None else self._port

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}{self._path}"

    # ---------- 生命周期 ----------

    async def start(self) -> None:
        if self._running:
            return
        app = web.Application()
        app.router.add_post(self._path, self._handle_request)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        addresses = getattr(self._runner, "addresses", None) or []
        if addresses:
            self._bound_port = addresses[0][1]
        if self._api_base_url:
            self._session = aiohttp.ClientSession(
                headers=self._headers or None,
            )
        self._running = True
        log.info("%s 监听 %s", self._name, self.url)

    async def stop(self) -> None:
        if not self._running and self._runner is None:
            return
        self._running = False
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    # ---------- 入站 ----------

    async def _handle_request(self, request: web.Request) -> web.Response:
        try:
            payload = await self._parse_body(request)
        except Exception:
            log.exception("%s 解析请求体失败", self._name)
            return web.json_response(
                {"status": "error", "reason": "bad_body"}, status=400
            )

        kind = self._kind_extractor(payload)
        # 与 WS 连接件保持一致: 先直通协议层（旁路总线），再走总线分发。
        self._notify_raw_listeners(payload, kind)
        await self.publish_raw(
            kind,
            payload,
            metadata={
                "method": request.method,
                "path": request.path,
                "remote": request.remote,
            },
        )
        return web.json_response({"status": "ok"})

    @staticmethod
    async def _parse_body(request: web.Request) -> Any:
        raw = await request.read()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return raw.decode("utf-8", errors="replace")

    # ---------- 出站 ----------

    async def send(self, payload: Any) -> Any:
        """把 ``payload`` 作为 JSON 发送到 ``api_base_url``，返回平台响应。

        「动作 / 信封」语义属于适配器，连接件只负责发送；
        响应为 JSON 时返回解析结果，否则返回文本。
        """
        if self._session is None or self._session.closed or not self._api_base_url:
            raise TransportNotConnected(
                f"{self._name} 未配置 api_base_url，无法出站（纯回调模式）"
            )
        async with self._session.post(self._api_base_url, json=payload) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                return await resp.json()
            return await resp.text()


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _maybe_json(raw: Any) -> Any:
    """文本帧尝试 JSON 解析；失败或非文本原样返回。"""
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return bytes(raw)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


__all__ = [
    "KindExtractor",
    "Transport",
    "TransportError",
    "TransportNotConnected",
    "ForwardWebSocketTransport",
    "HttpTransport",
    "default_kind_extractor",
]
