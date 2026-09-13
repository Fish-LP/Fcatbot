"""Fcatbot —— 聊天机器人平台框架。

本模块是**插件作者的唯一入口**: 常用 API 均在此导出。
包布局（架构 §2.3）: ``kernel/``（平台无关内核）、``adapter/``（适配器基座: 连接件，
正向 WS / HTTP）、``frontend/``（控制台 / WebUI）、``utils/``；应用装配与 CLI 见
:mod:`fcatbot.app`。
"""

from fcatbot.adapter.transports import (
    ForwardWebSocketTransport,
    HttpTransport,
    Transport,
    TransportError,
    TransportNotConnected,
)
from fcatbot.builtin import AdminCommands
from fcatbot.frontend.console import ConsoleApp, console_print
from fcatbot.kernel.commands import (
    CommandConflict,
    CommandContext,
    CommandError,
    CommandRegistry,
    CommandSpec,
    accepts_context,
    console_command,
)
from fcatbot.kernel.decorators import on_event
from fcatbot.kernel.events import (
    BotEvent,
    Event,
    EventBus,
    EventChannel,
    LifecycleEvent,
    MessageEvent,
    NoticeEvent,
    RawEvent,
    RequestEvent,
    Subscription,
)
from fcatbot.kernel.integration import IntegrationLayer
from fcatbot.kernel.loader import PluginLoader, PluginLoadError
from fcatbot.kernel.permissions import (
    AllowAllPermissionService,
    LuckPermsAdapter,
    NullPermissionService,
    PermissionService,
)
from fcatbot.kernel.plugins import FcatbotPlugin
from fcatbot.kernel.services import (
    ServiceConflict,
    ServiceError,
    ServiceInfo,
    ServiceNotFound,
    ServiceRegistry,
)
from fcatbot.tools.client import APIClient, ApiRequest
from fcatbot.utils import setup_logging

setup_logging()

__all__ = [
    # 事件
    "Event",
    "EventBus",
    "on_event",
    # 事件族（M1 内核事件层）
    "RawEvent",
    "BotEvent",
    "MessageEvent",
    "NoticeEvent",
    "RequestEvent",
    "LifecycleEvent",
    # 事件通道
    "EventChannel",
    "Subscription",
    # 命令
    "console_command",
    "CommandRegistry",
    "CommandSpec",
    "CommandContext",
    "accepts_context",
    "CommandError",
    "CommandConflict",
    # 权限
    "PermissionService",
    "NullPermissionService",
    "AllowAllPermissionService",
    "LuckPermsAdapter",
    # 服务
    "ServiceRegistry",
    "ServiceInfo",
    "ServiceError",
    "ServiceNotFound",
    "ServiceConflict",
    # 插件基类
    "FcatbotPlugin",
    # 适配器连接件（M4）
    "Transport",
    "TransportError",
    "TransportNotConnected",
    "ForwardWebSocketTransport",
    "HttpTransport",
    # 协议 API 客户端基类（适配器插件用）
    "APIClient",
    "ApiRequest",
    # 基础设施
    "AdminCommands",
    "ConsoleApp",
    "console_print",
    "IntegrationLayer",
    "PluginLoader",
    "PluginLoadError",
]

__version__ = "4.0.0"
__api_version__ = "1"
