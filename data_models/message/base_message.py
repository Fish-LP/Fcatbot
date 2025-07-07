# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 15:16:05
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-07 21:27:47
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from dataclasses import dataclass, field
import time
from typing import Literal, Optional, Dict

@dataclass(frozen=True)
class Sender:
    """消息发送者"""
    user_id: int = field(default=None)
    '''发送者 QQ 号'''
    nickname: str = field(default=None)
    '''昵称'''
    card: str = field(default='')
    '''群名片／备注'''
    sex: Literal['male', 'female', 'unknown'] = field(default='unknown')
    '''性别'''
    age	:int = field(default=0)
    '''年龄'''
    area :str = field(default=None)
    '''地区'''
    level :str = field(default=None)
    '''成员等级'''
    role: Literal['owner', 'admin', 'member'] = field(default=None)
    '''角色'''
    title :str = field(default=None)
    '''专属头衔'''

    def __repr__(self):
        return f"Sender([{self.nickname}]({self.user_id}))"

@dataclass(frozen=True)
class BaseMessage:
    """消息事件基类"""
    raw: dict = field(default=None)
    id: int = field(default=None)
    self_id: int = field(default=None)
    real_seq: int = field(default=None)
    reply_to: int = field(default=None)
    time: int = field(default_factory=lambda: int(time.time()))
    post_type: str = field(default=None)
    sender: Sender = field(default=None)

    def __post_init__(self):
        if isinstance(self.sender, dict):
            self.sender = Sender(**self.sender)

    def __repr__(self):
        attrs = {field.name: getattr(self, field.name) for field in self.__dataclass_fields__.values()}
        return f"{self.__class__.__name__}({attrs})"