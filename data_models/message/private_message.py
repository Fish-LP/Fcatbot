# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-13 20:31:31
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-19 20:27:54
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
    raw: dict
    '''原始数据'''
    id: int
    '''消息 ID'''
    self_id: int  
    '''收到事件的机器人 QQ 号'''
    real_seq: int
    '''真实序列号'''
    reply_to: int
    '''回复消息 ID'''
    time: int
    '''事件发生的时间戳'''
    post_type: Literal['message']
    '''上报类型'''
    sender: Sender
    '''发送人信息'''
    
    message_format: str = None
    '''消息格式'''
    message_type: Literal['private'] = None
    '''消息类型'''
    message_seq: int = None
    '''消息序列号'''
    message_id: int = None
    '''消息 ID'''
    message: MessageChain = None
    '''消息内容'''
    
    real_id: int = None
    '''真实消息 ID'''
    user_id: int = None
    '''发送者 QQ 号'''
    target_id: int = None
    '''目标 QQ 号'''
    
    sub_type: Literal['friend', 'group', 'other'] = None
    '''消息子类型'''
    
    raw_message: str = None
    '''原始消息内容'''
    font: int = None
    '''字体'''
    
    def __post_init__(self):
        if isinstance(self.message, list):
            object.__setattr__(self, 'message', MessageChain(self.message))
        if isinstance(self.sender, dict):
            object.__setattr__(self, 'sender', Sender(**self.sender))

    def __repr__(self):
        return f"PrivateMessage(user_id={self.user_id}, raw_message={self.raw_message})"