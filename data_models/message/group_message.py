# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 15:15:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-07 21:38:20
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from .base_message import BaseMessage, Sender
from .message_chain import MessageChain
from dataclasses import dataclass, field
from typing import Union, Literal

@dataclass(frozen=True)
class GroupMessage(BaseMessage):
    """群聊消息"""
    group_id: int = None
    '''群号'''
    def __repr__(self):
        return f"GroupMessage(group_id={self.group_id}, user_id={self.user_id}, raw_message={self.raw_message})"