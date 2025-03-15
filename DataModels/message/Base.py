# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 15:16:05
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-15 19:45:37
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from dataclasses import dataclass, field
from typing import Optional, Dict

@dataclass
class Sender:
    """消息发送者"""
    user_id: int = field(default=None)
    nickname: str = field(default=None)
    card: str = field(default=None)
    role: str = field(default=None)

    def __repr__(self):
        return f"Sender([{self.nickname}]({self.user_id}))"

@dataclass(frozen=True)
class BaseMessage:
    """消息事件基类"""
    id: int = field(default=None)
    self_id: int = field(default=None)
    real_seq: int = field(default=None)
    reply_to: int = field(default=None)
    time: int = field(default=None)
    post_type: str = field(default=None)
    sender: Sender = field(default=None)

    def __post_init__(self):
        if isinstance(self.sender, dict):
            self.sender = Sender(**self.sender)

    def __repr__(self):
        attrs = {field.name: getattr(self, field.name) for field in self.__dataclass_fields__.values()}
        return f"{self.__class__.__name__}({attrs})"