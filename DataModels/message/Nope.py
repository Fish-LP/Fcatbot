# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:35:26
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-16 01:33:52
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import base64
from enum import Enum
from typing import Union, List, Dict, Any, Iterable
from dataclasses import dataclass, field
from typing import Any

class Behavior(Enum):
    DAFAULT: int = 0
    '''默认'''
    TOP: int = 1
    '''置顶'''
    OCCUPY: int = 2
    '''独占'''
    OccupyType: int = 3
    '''独占类型'''

class Element:
    '''消息元素基类'''
    type: str = field(default='element')
    behavior: Behavior = Behavior.DAFAULT

    def to_dict(self) -> dict:
        '''将元素转换为可序列化的字典'''
        data = {}
        for attr, value in self.__dict__.items():
            if attr.startswith('_') or attr == 'element':
                continue
            data[attr] = value
        return {
            'type': self.type,
            'data': data
        }

@dataclass(frozen=True)
class TopElement(Element):
    '''强制置顶消息元素'''
    behavior: Behavior = field(init=False, default=Behavior.TOP)

@dataclass(frozen=True)
class OccupyElement(Element):
    '''独占消息元素'''
    behavior: Behavior = field(init=False, default=Behavior.OCCUPY)

@dataclass(frozen=True)
class OccupyTypeElement(Element):
    '''独占类型消息元素''' 
    behavior: Behavior = field(init=False, default=Behavior.OccupyType)

@dataclass(frozen=True)
class Text(Element):
    '''文本消息元素'''
    text: str
    type: str = field(default='text', init=False)

@dataclass(frozen=True)
class At(Element):
    '''@消息元素'''
    qq: Union[int, str]
    type: str = field(default='at', init=False)


@dataclass(frozen=True)
class AtAll(Element):
    '''@全体消息元素'''
    type: str = field(default='at', init=False)

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'data': {
                'qq': 'all'
            }
        }


@dataclass(frozen=True)
class Image(Element):
    '''图片消息元素'''
    sub_type: int = None
    summary: str = None
    url: str = None
    file: Union[str, bytes] = None
    file_size: int = None
    path: str = None
    type: str = field(default='image', init=False)
    
    def to_dict(self) -> dict:
        return {
            'type': 'image',
            'data': { 
                'name': '图片', # [发] [选]
                'summary': self.summary,
                'file': self.file,
                'sub_type': self.sub_type, # [选]
                'file_id': self.sub_type, # [收]
                'url': self.sub_type, # [收]
                'path': self.sub_type, # [收]
                'file_size': self.sub_type, # [收]
                'file_unique': self.sub_type, # [收]
                }
            }


@dataclass(frozen=True)
class Face(Element):
    '''表情消息元素'''
    id: int = None
    type: str = field(default='face', init=False)
    raw: dict = None
    resultId: int = None
    chainCount: Any = None


@dataclass(frozen=True)
class Reply(TopElement, Element):
    '''回复消息元素'''
    id: int = None
    type: str = field(default='reply', init=False)


@dataclass(frozen=True)
class Json(OccupyElement, Element):
    '''JSON消息元素'''
    data: str
    type: str = field(default='json', init=False)


@dataclass(frozen=True)
class Record(OccupyElement, Element):
    '''语音消息元素'''
    file: str
    type: str = field(default='record', init=False)


@dataclass(frozen=True)
class Video(OccupyElement, Element):
    '''视频消息元素'''
    file: str
    type: str = field(default='video', init=False)

@dataclass(frozen=True)
class Dice(OccupyElement, Element):
    '''骰子消息元素'''
    type: str = field(default='dice', init=False)


@dataclass(frozen=True)
class Rps(OccupyElement, Element):
    '''猜拳消息元素'''
    type: str = field(default='rps', init=False)


@dataclass(frozen=True)
class Music(OccupyElement, Element):
    '''音乐分享消息元素'''
    id: int
    music_type: str
    type: str = field(default='music', init=False)


@dataclass(frozen=True)
class CustomMusic(OccupyElement, Element):
    '''自定义音乐分享消息元素'''
    url: str = None
    audio: str = None
    title: str = None
    image: str = None
    singer: str = None
    type: str = field(default='music', init=False)

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'data': {
                'type': 'custom',
                'url': self.url,
                'audio': self.audio,
                'title': self.title,
                'image': self.image,
                'singer': self.singer
            }
        }

@dataclass(frozen=True)
class File(OccupyElement, Element):
    '''文件信息元素'''
    file_id: int
    file_size: int
    file: str = None
    path: str = None
    url: str = None

@dataclass(frozen=True)
class Markdown(OccupyElement, Element):
    '''Markdown消息元素'''
    markdown: dict

@dataclass(frozen=True)
class Nope(OccupyTypeElement, Element):
    data: 'NopeData'
    type: str = field(default='nope', init=False)
    
    def to_dict(self):
        return {
            'type': 'node',
            'data': {
                'user_id': self.data.user_id,
                'nickname': self.data.nickname,
                'content': self.data.content.to_dict()
                }
            }

@dataclass(frozen=True)
class NopeData:
    user_id: int
    nickname: str
    content: any # MessageChain


@dataclass(frozen=True)
class Markdown(OccupyElement, Element):
    type: str = field(default='markdown', init=False)
    
    def __post_init__(self, markdown: str):
        ValueError('这是TODO,还没实现呢')

    def to_dict(self) -> dict:
        ValueError('这是TODO,还没实现呢')