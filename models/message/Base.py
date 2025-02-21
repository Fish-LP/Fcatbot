# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 15:16:05
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-22 01:22:19
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from dataclasses import dataclass, field
from typing import Union, Dict

@dataclass
class Sender:
    """消息发送者"""
    user_id: str = field(default=None)
    nickname: str = field(default=None)
    card: str = field(default=None)
    role: str = field(default=None)

    def __post_init__(self):
        self.user_id = str(self.user_id)

    def __repr__(self):
        return f"Sender([{self.nickname}]({self.user_id}))"

@dataclass
class BaseMessage:
    """消息事件基类"""
    id: str = field(default=None)
    self_id: str = field(default=None)
    reply_to: str = field(default=None)
    time: int = field(default=None)
    post_type: str = field(default=None)
    sender: Sender = field(default=None)

    def __post_init__(self):
        self.self_id = str(self.self_id)
        if isinstance(self.sender, dict):
            self.sender = Sender(**self.sender)

    def __repr__(self):
        attrs = {field.name: getattr(self, field.name) for field in self.__dataclass_fields__.values()}
        return f"{self.__class__.__name__}({attrs})"