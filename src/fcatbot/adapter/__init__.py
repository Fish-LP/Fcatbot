"""适配器基座层（架构 §2.3 / ADR-0001 / ADR-0003）。

本层提供**适配器插件**（如 OneBot）复用的基座，不包含任何平台协议语义:

- :mod:`fcatbot.adapter.transports` —— ``Transport`` 协议与内置连接件
  （正向 WebSocket、HTTP 回调）。

依赖规则（ADR-0001 / ADR-0014）: ``adapter`` 依赖 ``kernel``，且**不被** ``kernel`` /
``frontend`` 依赖；业务插件只依赖 ``kernel`` 与**协议契约包**（事件类型的三层契约见
ADR-0014），**不**直接使用本层，也不 import 适配器插件包。
"""

from fcatbot.adapter import transports

__all__ = ["transports"]
