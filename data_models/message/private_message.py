# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-13 20:31:31
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-07 21:38:35
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from .base_message import BaseMessage, Sender
from .message_chain import MessageChain
from dataclasses import dataclass, field
from typing import Union, Literal

@dataclass(frozen=True)
class PrivateMessage(BaseMessage):
    """私聊消息"""
    def __repr__(self):
        return f"PrivateMessage(user_id={self.user_id}, raw_message={self.raw_message})"