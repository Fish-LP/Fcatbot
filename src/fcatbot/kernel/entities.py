"""内核实体抽象: 机器人（Bot）与联系人（Contact 族）。

设计依据: ``docs/architecture.md`` §3.3 / §3.4；ADR-0001 依赖规则 2。

- 跨层共享的实体抽象定义在**内核**，适配器插件提供具体实现；
- 本模块为 **M1 最小骨架**（只定义接口形状与约定），Transport 等适配器基座在 M4 落地；
- 运行时不依赖 adapter；类型注解对尚未落地的模块使用宽松标注，M2/M4 时收紧
  （如 ``send_message`` 的 ``MessageChain`` 在 M2 消息模型落地后补全注解）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fcatbot.kernel.events import EventChannel


@dataclass
class MessageReceipt:
    """消息回执（发送结果的轻量描述）。"""

    message_id: str

    async def recall(self) -> None:
        """撤回本条消息。默认未实现，由适配器覆写。"""
        raise NotImplementedError("当前适配器未实现消息撤回")


class Contact(ABC):
    """可发送消息的对象（好友 / 群 / 群成员等的共同抽象）。"""

    id: str

    @abstractmethod
    async def send_message(self, message: Any) -> MessageReceipt:
        """发送消息。

        ``message`` 接受 ``str``（等价纯文本）或 ``MessageChain``
        （后者在 M2 消息模型落地后生效，届时本注解收紧为 ``str | MessageChain``）。
        """


class User(Contact):
    """用户（私聊对象 / 群成员的上位概念）。"""


class Group(Contact):
    """群聊对象。"""


class Member(User):
    """群成员。"""

    @property
    @abstractmethod
    def group(self) -> Group:
        """成员所属的群。"""


class Bot(ABC):
    """机器人实例（由适配器为每条可用连接创建）。

    业务插件通过事件与 Bot / Contact 交互；需要调用平台特殊能力时使用 ``call_api``。
    """

    id: str
    platform: str

    @property
    @abstractmethod
    def ready(self) -> bool:
        """连接是否就绪。"""

    @property
    @abstractmethod
    def channel(self) -> EventChannel:
        """只包含本 Bot 事件的事件通道（适配器实现时按 ``bot`` 过滤）。"""

    @abstractmethod
    async def call_api(self, action: str, **params: Any) -> Any:
        """调用平台原始动作（高级用法；常规场景优先使用 Contact 方法）。"""
