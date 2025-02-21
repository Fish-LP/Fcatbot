# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:35:26
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-22 01:21:55
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
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
    """消息元素基类"""
    type: str = "element"
    behavior: str = Behavior.DAFAULT

    def to_dict(self) -> dict:
        """将元素转换为可序列化的字典"""
        data = {}
        # 获取当前对象的字段名和值
        for attr, value in self.__dict__.items():
            if attr == "element":
                continue
            data[attr] = value
        return {
            "type": self.type,
            "data": data
        }

class TopElement(Element):
    """强制置顶消息元素"""
    behavior: str = Behavior.TOP

class OccupyElement(Element):
    """独占消息元素"""
    behavior: str = Behavior.OCCUPY

class OccupyTypeElement(Element):
    """独占类型消息元素"""
    behavior: str = Behavior.OccupyType


@dataclass
class Text(Element):
    """文本消息元素"""
    text: str
    type: str = field(default="text", init=False)

    def __post_init__(self):
        self.type = "text"


@dataclass
class At(Element):
    """@消息元素"""
    qq: Union[int, str]
    type: str = field(default="at", init=False)

    def __post_init__(self):
        self.type = "at"


@dataclass
class AtAll(Element):
    """@全体消息元素"""
    type: str = field(default="at", init=False)

    def __post_init__(self):
        self.type = "at"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": {
                "qq": "all"
            }
        }


@dataclass
class Image(Element):
    """图片消息元素"""
    sub_type: int
    summary: str
    url: str
    file: Union[str, bytes]
    file_size: int
    path: str = None
    type: str = field(default="image", init=False)

    def __post_init__(self):
        self.type = "image"

    def to_dict(self) -> dict:
        return {
            'type': 'image',
            "data": base64.b64decode(self.file).decode('utf-8')
            }


@dataclass
class Face(Element):
    """表情消息元素"""
    id: int
    type: str = field(default="face", init=False)

    def __post_init__(self):
        self.type = "face"


@dataclass
class Reply(TopElement, Element):
    """回复消息元素"""
    id: str
    reply_to: str = field(default=None)
    type: str = field(default="reply", init=False)

    def __post_init__(self):
        self.type = "reply"


@dataclass
class Json(OccupyElement, Element):
    """JSON消息元素"""
    data: str
    type: str = field(default="json", init=False)

    def __post_init__(self):
        self.type = "json"


@dataclass
class Record(OccupyElement, Element):
    """语音消息元素"""
    file: str
    type: str = field(default="record", init=False)

    def __post_init__(self):
        self.type = "record"


@dataclass
class Video(OccupyElement, Element):
    """视频消息元素"""
    file: str
    type: str = field(default="video", init=False)

    def __post_init__(self):
        self.type = "video"


@dataclass
class Dice(OccupyElement, Element):
    """骰子消息元素"""
    type: str = field(default="dice", init=False)

    def __post_init__(self):
        self.type = "dice"


@dataclass
class Rps(OccupyElement, Element):
    """猜拳消息元素"""
    type: str = field(default="rps", init=False)

    def __post_init__(self):
        self.type = "rps"


@dataclass
class Music(OccupyElement, Element):
    """音乐分享消息元素"""
    music_type: str
    id: str
    type: str = field(default="music", init=False)

    def __post_init__(self):
        self.type = "music"


@dataclass
class CustomMusic(OccupyElement, Element):
    """自定义音乐分享消息元素"""
    url: str
    audio: str
    title: str
    image: str = None
    singer: str = None
    type: str = field(default="music", init=False)

    def __post_init__(self):
        self.type = "music"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "data": {
                "type": "custom",
                "url": self.url,
                "audio": self.audio,
                "title": self.title,
                "image": self.image,
                "singer": self.singer
            }
        }

@dataclass
class File(OccupyElement, Element):
    """文件信息元素"""
    file: str
    path: str
    url: str
    file_id: str
    file_size: int

@dataclass
class Markdown(OccupyElement, Element):
    """Markdown消息元素"""
    markdown: dict

@dataclass
class Nope(OccupyTypeElement, Element):
    type: str = field(default="nope", init=False)
    data: 'NopeData'
    
    def to_dict(self):
        return {
            "type": "node",
            "data": {
                "user_id": self.data.user_id,
                "nickname": self.data.nickname,
                "content": self.data.content.to_dict()
                }
            }

@dataclass
class NopeData():
    user_id: str
    nickname: str
    content: any # MessageChain

class Markdown(OccupyElement, Element):
    def __post_init__(self, markdown: str):
        self.type = "markdown"
        ValueError('这是TODO，还没实现呢')

    async def to_dict(self) -> dict:
        ValueError('这是TODO，还没实现呢')