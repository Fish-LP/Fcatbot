from dataclasses import dataclass, field
import time
from typing import Literal, Dict
from .base_message import BaseMessage

@dataclass(frozen=True)
class NoticeEvent:
    """通知事件基类"""
    post_type: Literal['notice'] = field(default='notice')
    '''上报类型'''
    notice_type: str = field(default=None)
    '''通知类型'''

@dataclass(frozen=True)
class GroupFileUpload(NoticeEvent):
    """群文件上传事件"""
    notice_type: Literal['group_upload'] = field(default='group_upload')
    '''通知类型'''
    group_id: int = field(default=None)
    '''群号'''
    user_id: int = field(default=None)
    '''发送者QQ号'''
    file: Dict = field(default_factory=dict)
    '''文件信息'''

@dataclass(frozen=True)
class GroupAdminChange(NoticeEvent):
    """群管理员变动事件"""
    notice_type: Literal['group_admin'] = field(default='group_admin')
    '''通知类型'''
    sub_type: Literal['set', 'unset'] = field(default=None)
    '''事件子类型'''
    group_id: int = field(default=None)
    '''群号'''
    user_id: int = field(default=None)
    '''管理员QQ号'''

@dataclass(frozen=True)
class GroupMemberDecrease(NoticeEvent):
    """群成员减少事件"""
    notice_type: Literal['group_decrease'] = field(default='group_decrease')
    '''通知类型'''
    sub_type: Literal['leave', 'kick', 'kick_me'] = field(default=None)
    '''事件子类型'''
    group_id: int = field(default=None)
    '''群号'''
    operator_id: int = field(default=None)
    '''操作者QQ号'''
    user_id: int = field(default=None)
    '''离开者QQ号'''

@dataclass(frozen=True)
class GroupMemberIncrease(NoticeEvent):
    """群成员增加事件"""
    notice_type: Literal['group_increase'] = field(default='group_increase')
    '''通知类型'''
    sub_type: Literal['approve', 'invite'] = field(default=None)
    '''事件子类型'''
    group_id: int = field(default=None)
    '''群号'''
    operator_id: int = field(default=None)
    '''操作者QQ号'''
    user_id: int = field(default=None)
    '''加入者QQ号'''

@dataclass(frozen=True)
class GroupBan(NoticeEvent):
    """群禁言事件"""
    notice_type: Literal['group_ban'] = field(default='group_ban')
    '''通知类型'''
    sub_type: Literal['ban', 'lift_ban'] = field(default=None)
    '''事件子类型'''
    group_id: int = field(default=None)
    '''群号'''
    operator_id: int = field(default=None)
    '''操作者QQ号'''
    user_id: int = field(default=None)
    '''被禁言QQ号'''
    duration: int = field(default=None)
    '''禁言时长(秒)'''

@dataclass(frozen=True)
class FriendAdd(NoticeEvent):
    """好友添加事件"""
    notice_type: Literal['friend_add'] = field(default='friend_add')
    '''通知类型'''
    user_id: int = field(default=None)
    '''新添加好友QQ号'''

@dataclass(frozen=True)
class GroupRecall(NoticeEvent):
    """群消息撤回事件"""
    notice_type: Literal['group_recall'] = field(default='group_recall')
    '''通知类型'''
    group_id: int = field(default=None)
    '''收到消息的群聊ID'''
    user_id: int = field(default=None)
    '''消息发送者QQ号'''
    operator_id: int = field(default=None)
    '''操作者QQ号'''
    message_id: int = field(default=None)
    '''被撤回的消息ID'''
    time: int = field(default=None)
    '''当前时间'''
    self_id: int = field(default=None)
    '''接收者ID'''

@dataclass(frozen=True)
class FriendRecall(NoticeEvent):
    """好友消息撤回事件"""
    notice_type: Literal['friend_recall'] = field(default='friend_recall')
    '''通知类型'''
    user_id: int = field(default=None)
    '''好友QQ号'''
    message_id: int = field(default=None)
    '''被撤回的消息ID'''

@dataclass(frozen=True)
class PokeNotify(NoticeEvent):
    """群内戳一戳事件"""
    notice_type: Literal['notify'] = field(default='notify')
    '''通知类型'''
    sub_type: Literal['poke'] = field(default='poke')
    '''提示类型'''
    group_id: int = field(default=None)
    '''群号'''
    user_id: int = field(default=None)
    '''发送者QQ号'''
    target_id: int = field(default=None)
    '''被戳者QQ号'''

@dataclass(frozen=True)
class LuckyKingNotify(NoticeEvent):
    """群红包运气王事件"""
    notice_type: Literal['notify'] = field(default='notify')
    '''通知类型'''
    sub_type: Literal['lucky_king'] = field(default='lucky_king')
    '''提示类型'''
    group_id: int = field(default=None)
    '''群号'''
    user_id: int = field(default=None)
    '''红包发送者QQ号'''
    target_id: int = field(default=None)
    '''运气王QQ号'''

@dataclass(frozen=True)
class HonorNotify(NoticeEvent):
    """群成员荣誉变更事件"""
    notice_type: Literal['notify'] = field(default='notify')
    '''通知类型'''
    sub_type: Literal['honor'] = field(default='honor')
    '''提示类型'''
    group_id: int = field(default=None)
    '''群号'''
    honor_type: Literal['talkative', 'performer', 'emotion'] = field(default=None)
    '''荣誉类型'''
    user_id: int = field(default=None)
    '''成员QQ号'''
