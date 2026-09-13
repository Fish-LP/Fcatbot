"""M1 兼容性冒烟: 真实 IntegrationLayer + @on_event 插件在迁移后的运行。

验证「现有插件不改代码可跑」验收标准的最接近环节: 
使用真实的 :class:`fcatbot.kernel.integration.IntegrationLayer`、``@on_event`` 装饰器、
``CommandRegistry`` / ``ServiceRegistry``，仅事件总线实现为 M1 新版。

（宿主应用 ``fcatbot.app`` 的交互式控制台依赖真实终端，无法在无 TTY 环境自动化；
本测试覆盖除控制台输入之外的完整事件链路。）
"""

from __future__ import annotations

import asyncio

from fcatbot.kernel.commands import CommandRegistry, console_command
from fcatbot.kernel.decorators import on_event
from fcatbot.kernel.events import Event, EventBus
from fcatbot.kernel.integration import IntegrationLayer
from fcatbot.kernel.services import ServiceRegistry


class _EchoStylePlugin:
    """模仿 plugins/echo 的插件形态（@on_event("sdk.raw") + 前缀命令）。"""

    name = "smoke-echo"

    def __init__(self) -> None:
        self.hits: list[str] = []

    @console_command("smoke", help="冒烟命令")
    async def cmd_smoke(self, args: list[str]) -> str:
        return f"[smoke] {' '.join(args)}"

    @on_event("sdk.raw", priority=50)
    async def handle_raw(self, event: Event) -> None:
        data = event.data
        if isinstance(data, str) and data.startswith("!echo "):
            self.hits.append(data[len("!echo "):])


def test_integration_layer_full_lifecycle() -> None:
    async def scenario() -> list[str]:
        bus = EventBus()
        bus.start()
        commands = CommandRegistry()
        services = ServiceRegistry()
        integration = IntegrationLayer(None, bus, services, commands)  # pm 仅 attach_all 使用

        plugin = _EchoStylePlugin()
        integration.attach(plugin)

        # 命令已注册（现有扫描逻辑不变）
        spec, args = commands.find(["smoke", "a", "b"])
        assert spec is not None and spec.handler is not None
        assert await spec.handler(["a", "b"]) == "[smoke] a b"

        # 事件链路: 旧式字符串事件 → @on_event 订阅
        await bus.publish(
            Event(
                name="sdk.raw",
                data="!echo hello from smoke",
                source="sdk",
                metadata={"user_id": "10001", "group_id": 123456},
            )
        )
        assert plugin.hits == ["hello from smoke"]

        # detach 后退订生效（现有清理语义不变）
        integration.detach(plugin)
        await bus.publish(Event(name="sdk.raw", data="!echo again"))
        assert plugin.hits == ["hello from smoke"]

        await bus.close()
        return plugin.hits

    assert asyncio.run(scenario()) == ["hello from smoke"]
