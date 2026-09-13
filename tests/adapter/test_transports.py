"""adapter.transports 单元测试（M4 连接件: 正向 WS + HTTP）。

覆盖:
- ``Transport`` 基座: ``build_raw`` / ``publish_raw`` / ``publish_raw_nowait`` / ``raw.*`` 事件键
- ``ForwardWebSocketTransport``: 连接 → 收帧发布 ``raw.ws.message``、``send`` 出站、断开事件
- ``HttpTransport``: 回调服务器入站 → ``raw.http.*``、出站 HTTP API（``send`` / ``call``）、
  未配置 ``api_base_url`` 时 ``send`` 抛 ``TransportNotConnected``
- ``default_kind_extractor`` 的帧类型推断

运行: ``.venv\\Scripts\\python.exe -m pytest tests -q``
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import WSMsgType, web

from fcatbot.adapter.transports import (
    ForwardWebSocketTransport,
    HttpTransport,
    TransportNotConnected,
    default_kind_extractor,
)
from fcatbot.kernel.events import EventBus


def run(coro: Any) -> Any:
    """在独立事件循环中运行测试场景。"""
    return asyncio.run(coro)


async def _start_site(app: web.Application) -> tuple[web.AppRunner, int]:
    """启动一个绑定随机端口的 aiohttp 站点，返回 (runner, port)。"""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, runner.addresses[0][1]


async def _wait_for(predicate: Any, timeout: float = 3.0) -> None:
    """轮询等待条件成立（避免依赖固定 sleep）。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("等待条件超时")


def _collect(bus: EventBus) -> list[tuple[str, str, Any]]:
    """订阅 raw.*，收集 (transport, kind, data)。"""
    seen: list[tuple[str, str, Any]] = []
    bus.subscribe(
        "raw.*",
        lambda event: seen.append((event.transport, event.kind, event.data)),
    )
    return seen


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def test_default_kind_extractor() -> None:
    assert default_kind_extractor({"post_type": "message"}) == "message"
    assert default_kind_extractor({"type": "notice"}) == "notice"
    assert default_kind_extractor({"kind": "request"}) == "request"
    assert default_kind_extractor("plain") == "message"
    assert default_kind_extractor(None) == "message"


def test_build_raw_event_key() -> None:
    async def scenario() -> None:
        bus = EventBus()
        transport = ForwardWebSocketTransport(bus, "ws://127.0.0.1:1/")
        event = transport.build_raw("message", {"a": 1}, metadata={"k": "v"})
        assert event.name == "raw.ws.message"
        assert event.transport == "ws"
        assert event.kind == "message"
        assert event.data == {"a": 1}
        assert dict(event.metadata) == {"k": "v"}

    run(scenario())


# ---------------------------------------------------------------------------
# 正向 WebSocket
# ---------------------------------------------------------------------------


def test_forward_ws_receives_and_sends() -> None:
    """正向 WS: 连接后收帧发布原始事件，send 出站并经平台回帧。"""

    async def scenario() -> None:
        bus = EventBus()
        bus.start()
        seen = _collect(bus)

        async def ws_handler(request: web.Request) -> web.WebSocketResponse:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json({"post_type": "message", "message": "hi from server"})
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    payload = json.loads(msg.data)
                    await ws.send_json({"post_type": "echo", "payload": payload})
            return ws

        app = web.Application()
        app.router.add_get("/ws", ws_handler)
        runner, port = await _start_site(app)

        transport = ForwardWebSocketTransport(
            bus, f"http://127.0.0.1:{port}/ws", reconnect=False
        )
        await transport.start()
        try:
            await _wait_for(lambda: any(kind == "message" for _, kind, _ in seen))
            await _wait_for(lambda: transport.connected)

            await transport.send({"hello": "world"})
            await _wait_for(
                lambda: any(
                    kind == "echo"
                    and data == {"post_type": "echo", "payload": {"hello": "world"}}
                    for _, kind, data in seen
                )
            )

            assert [t for t, _, _ in seen] == ["ws"] * len(seen)
            assert seen[0][1] == "connected"
        finally:
            await transport.stop()
            await runner.cleanup()

        assert transport.running is False
        assert any(kind == "disconnected" for _, kind, _ in seen)

    run(scenario())


def test_forward_ws_send_before_connect_raises() -> None:
    async def scenario() -> None:
        bus = EventBus()
        transport = ForwardWebSocketTransport(bus, "ws://127.0.0.1:9/", reconnect=False)
        try:
            await transport.send("x")
            raise AssertionError("未连接时应抛 TransportNotConnected")
        except TransportNotConnected:
            pass

    run(scenario())


def test_forward_ws_stop_publishes_disconnected() -> None:
    """正常连接后 stop() 应发布 raw.ws.disconnected（以事件键为准）。"""

    async def scenario() -> None:
        bus = EventBus()
        bus.start()
        seen = _collect(bus)

        async def ws_handler(request: web.Request) -> web.WebSocketResponse:
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for _ in ws:
                pass
            return ws

        app = web.Application()
        app.router.add_get("/ws", ws_handler)
        runner, port = await _start_site(app)

        transport = ForwardWebSocketTransport(bus, f"http://127.0.0.1:{port}/ws")
        await transport.start()
        await _wait_for(lambda: transport.connected)
        await transport.stop()
        await bus.drain()
        await runner.cleanup()

        assert any(kind == "disconnected" for _, kind, _ in seen)

    run(scenario())


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def test_http_inbound_publishes_raw() -> None:
    """HTTP 回调: POST 请求体（JSON）→ raw.http.<post_type>。"""

    async def scenario() -> None:
        import aiohttp

        bus = EventBus()
        bus.start()
        seen = _collect(bus)

        transport = HttpTransport(bus, host="127.0.0.1", port=0)
        await transport.start()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    transport.url, json={"post_type": "message", "group_id": 42}
                ) as resp:
                    assert resp.status == 200
                    assert await resp.json() == {"status": "ok"}
        finally:
            await transport.stop()

        assert ("http", "message", {"post_type": "message", "group_id": 42}) in seen

    run(scenario())


def test_http_inbound_text_body() -> None:
    """HTTP 回调: 非 JSON 文本体原样作为 data 发布。"""

    async def scenario() -> None:
        import aiohttp

        bus = EventBus()
        bus.start()
        seen = _collect(bus)

        transport = HttpTransport(bus, host="127.0.0.1", port=0)
        await transport.start()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(transport.url, data=b"raw-frame") as resp:
                    assert resp.status == 200
        finally:
            await transport.stop()

        assert ("http", "message", "raw-frame") in seen

    run(scenario())


def test_http_outbound_send() -> None:
    """HTTP 出站: 载荷**原样** POST 到 api_base_url（连接件不做动作路由）。"""

    async def scenario() -> None:
        received: list[tuple[str, Any]] = []

        async def api_handler(request: web.Request) -> web.Response:
            body = await request.json()
            received.append((request.path, body))
            return web.json_response({"status": "ok"})

        app = web.Application()
        app.router.add_post("/{tail:.*}", api_handler)
        runner, port = await _start_site(app)

        bus = EventBus()
        transport = HttpTransport(
            bus,
            host="127.0.0.1",
            port=0,
            api_base_url=f"http://127.0.0.1:{port}/api",
        )
        await transport.start()
        try:
            payload = {
                "action": "send_group_msg",
                "params": {"group_id": 7, "message": "hi"},
            }
            result = await transport.send(payload)
            assert result == {"status": "ok"}
        finally:
            await transport.stop()
            await runner.cleanup()

        # 动作/信封不被解释: 原样发往 api_base_url
        assert received == [
            (
                "/api",
                {
                    "action": "send_group_msg",
                    "params": {"group_id": 7, "message": "hi"},
                },
            )
        ]

    run(scenario())


def test_http_send_without_api_base_url_raises() -> None:
    async def scenario() -> None:
        bus = EventBus()
        transport = HttpTransport(bus, host="127.0.0.1", port=0)
        await transport.start()
        try:
            try:
                await transport.send({"x": 1})
                raise AssertionError("纯回调模式 send 应抛 TransportNotConnected")
            except TransportNotConnected:
                pass
        finally:
            await transport.stop()

    run(scenario())


def test_http_kind_extractor_override() -> None:
    """自定义 kind_extractor 生效。"""

    async def scenario() -> None:
        import aiohttp

        bus = EventBus()
        bus.start()
        seen = _collect(bus)

        transport = HttpTransport(
            bus, host="127.0.0.1", port=0, kind_extractor=lambda payload: "custom_kind"
        )
        await transport.start()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(transport.url, json={"a": 1}) as resp:
                    assert resp.status == 200
        finally:
            await transport.stop()

        assert ("http", "custom_kind", {"a": 1}) in seen

    run(scenario())
