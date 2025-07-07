# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 15:16:05
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-07 21:47:08
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from dataclasses import dataclass, field
import time
from typing import Literal, Optional, Dict
from .message_chain import MessageChain

@dataclass(frozen=True)
class Sender:
    """消息发送者"""
    user_id: int
    '''发送者 QQ 号'''
    nickname: str
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
    real_id: int
    '''真实消息 ID'''
    real_seq: int
    '''真实消息序列号'''
    self_id: int
    '''收到事件的机器人 QQ 号'''
    id: int
    '''消息 ID'''
    raw: dict
    '''原始数据'''
    post_type: str
    '''消息类型'''
    sender: Sender
    '''消息发送者信息'''
    raw_message: str
    '''原始消息内容'''
    message_id: int
    '''消息 ID'''
    message: MessageChain
    '''消息内容'''
    time: int = field(default_factory=lambda: int(time.time()))
    '''事件发生的时间戳'''
    sub_type: Literal['friend', 'group', 'other'] = 'other'
    '''消息子类型'''
    reply_to: int = None
    '''回复的消息 ID'''
    font: int = None
    '''字体'''
    user_id: int = None
    '''发送者 QQ 号'''
    target_id: int = None
    '''目标 QQ 号'''
    message_format: str = None
    '''消息格式'''
    message_type: Literal['private'] = None
    '''消息类型'''
    message_seq: int = None
    '''消息序列号'''
    
    def __post_init__(self):
        if isinstance(self.message, list):
            object.__setattr__(self, 'message', MessageChain(self.message))
        if isinstance(self.sender, dict):
            object.__setattr__(self, 'sender', Sender(**self.sender))

    def __repr__(self):
        attrs = {field.name: getattr(self, field.name) for field in self.__dataclass_fields__.values()}
        return f"{self.__class__.__name__}({attrs})"