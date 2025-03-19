from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class RequestEvent:
    """请求事件基类"""
    post_type: Literal['request'] = field(default='request')
    '''上报类型'''
    request_type: str = field(default=None)
    '''请求类型'''
    user_id: int = field(default=None)
    '''发送请求的 QQ 号'''
    comment: str = field(default=None)
    '''验证信息'''
    flag: str = field(default=None)
    '''请求 flag，在调用处理请求的 API 时需要传入'''

@dataclass(frozen=True)
class FriendRequestEvent(RequestEvent):
    """加好友请求事件"""
    request_type: Literal['friend'] = field(default='friend')
    '''请求类型'''
    approve: bool = field(default=False)
    '''是否同意请求'''
    remark: str = field(default=None)
    '''添加后的好友备注（仅在同意时有效）'''

@dataclass(frozen=True)
class GroupRequestEvent(RequestEvent):
    """加群请求/邀请事件"""
    request_type: Literal['group'] = field(default='group')
    '''请求类型'''
    sub_type: Literal['add', 'invite'] = field(default=None)
    '''请求子类型，分别表示加群请求、邀请登录号入群'''
    group_id: int = field(default=None)
    '''群号'''
    approve: bool = field(default=False)
    '''是否同意请求/邀请'''
    reason: str = field(default=None)
    '''拒绝理由（仅在拒绝时有效）'''
