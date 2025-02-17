from .Base import BaseMessage, Sender
from .MessageChain import MessageChain
from dataclasses import dataclass, field
from typing import Union

@dataclass
class PrivateMessage(BaseMessage):
    """私聊消息"""
    id: str
    self_id: str
    reply_to: str
    time: int
    post_type: str
    sender: Sender
    
    message_format: str= None
    message_type: str= None
    message_seq: str= None
    message_id: str= None
    message: MessageChain= None
    
    real_id: str= None
    # group_id: str= None
    user_id: str= None
    target_id: str= None
    
    sub_type: str= None

    raw_message: str= None
    font: int= None
    
    def __post_init__(self):
        super().__post_init__()
        if isinstance(self.message, list):
            self.message = MessageChain(self.message)

    def __repr__(self):
        return f"PrivateMessage(user_id={self.user_id}, raw_message={self.raw_message})"