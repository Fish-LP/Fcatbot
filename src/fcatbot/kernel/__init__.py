"""Fcatbot 内核: 平台无关的核心抽象（架构 §2.3）。

模块: 
- ``events``       事件基类族 / EventBus / EventChannel（M1）
- ``entities``     Bot / Contact 等实体抽象（最小骨架，M4 扩展）
- ``commands``     CommandRegistry / CommandSpec / CommandContext
- ``permissions``  PermissionService 协议与实现（AllowAll / Null / LuckPerms）
- ``services``     ServiceRegistry（跨插件服务）
- ``loader``       三模式插件加载器（包 / 单文件 / ZIP）
- ``plugins``      FcatbotPlugin 基类（M3 自研内核替换 pluginforge）
- ``integration``  PluginForge ↔ 总线/命令/服务的临时协调层（M3 移除）
- ``decorators``   ``@on_event``

依赖规则（ADR-0001）: 内核不依赖 adapter / frontend；跨层共享的抽象在这里定义。
"""

from fcatbot.kernel import entities, events

__all__ = [
    "commands",
    "decorators",
    "entities",
    "events",
    "integration",
    "loader",
    "permissions",
    "plugins",
    "services",
]
