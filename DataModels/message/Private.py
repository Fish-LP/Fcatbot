# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-13 20:31:31
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-10 21:13:48
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from .Base import BaseMessage, Sender
from .MessageChain import MessageChain
from dataclasses import dataclass, field
from typing import Union

@dataclass(frozen=True)
class PrivateMessage(BaseMessage):
    """私聊消息"""
    id: int
    self_id: int
    reply_to: int
    time: int
    post_type: str
    sender: Sender
    
    message_format: str= None
    message_type: str= None
    message_seq: int= None
    message_id: int= None
    message: MessageChain= None
    
    real_id: int= None
    # group_id: str= None
    user_id: int= None
    target_id: int= None
    
    sub_type: str= None

    raw_message: str= None
    font: int= None
    
    def __post_init__(self):
        if isinstance(self.message, list):
            object.__setattr__(self, 'message', MessageChain(self.message))
        if isinstance(self.sender, dict):
            object.__setattr__(self, 'sender', Sender(**self.sender))

    def __repr__(self):
        return f"PrivateMessage(user_id={self.user_id}, raw_message={self.raw_message})"