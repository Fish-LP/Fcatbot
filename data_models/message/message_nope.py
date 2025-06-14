# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:35:26
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-14 21:29:33
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from enum import Enum
from typing import Literal
from dataclasses import dataclass, field
from uuid import UUID

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
class DefaultElement(Element):
    '''强制置顶消息元素'''
    behavior: Behavior = field(init=False, default=Behavior.DAFAULT)

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
class Text(DefaultElement):
    '''[文本]消息元素'''
    text: str
    '''文本'''
    
    type: str = field(default='text', init=False)


@dataclass(frozen=True)
class At(DefaultElement):
    '''[@]消息元素'''
    qq: int
    '''qq号'''
    
    type: str = field(default='at', init=False)

@dataclass(frozen=True)
class AtAll(DefaultElement):
    '''[@全体]消息元素'''
    qq: str = field(default='all', init=False)
    
    type: str = field(default='at', init=False)


@dataclass(frozen=True)
class Face(DefaultElement):
    '''[表情]消息元素'''
    id: int
    resultId: int = field(default=None)
    raw: dict = field(default=None)
    chainCount: int = field(default=None)
    type: str = field(default='face', init=False)


@dataclass(frozen=True)
class Image(DefaultElement):
    '''[图片]消息元素'''
    file: str
    '''[参见napcat]推荐使用base64'''
    
    name: str = field(default=None)
    '''[可选]'''
    summary: str = field(default=None)
    '''[可选]'''
    # file: Union[str, bytes]
    sub_type: int = field(default=None)
    '''[可选]'''
    file_id: int = field(default=None)
    url: str = field(default=None)
    path: str = field(default=None)
    file_size: int = field(default=None)
    # file_unique: Any = None
    key: str = field(default=None, init=True)
    emoji_id: UUID = field(default=None, init=True)
    emoji_package_id: int = field(default=None, init=True)
    
    type: str = field(default='image', init=False)
    
    def __init__(self, *args, **kwargs):
        if 'emoji_id' in kwargs and kwargs['emoji_id']:
            kwargs['emoji_id'] = UUID(kwargs['emoji_id'])
    
    def to_dict(self) -> dict:
        return {
            'type': 'image',
            'data': { 
                'name': self.name or '图片', # [发] [选]
                'file': self.file,
                'summary': self.summary,
                'sub_type': self.sub_type, # [选]
                }
            }


@dataclass(frozen=True)
class Reply(TopElement):
    '''[回复]消息元素'''
    id: int = None
    type: str = field(default='reply', init=False)


@dataclass(frozen=True)
class Json(OccupyElement):
    '''[JSON]消息元素'''
    data: str
    type: str = field(default='json', init=False)


@dataclass(frozen=True)
class Record(OccupyElement):
    '''[语音]消息元素'''
    file: str
    '''[参见napcat]'''
    type: str = field(default='record', init=False)


@dataclass(frozen=True)
class Video(OccupyElement):
    '''[视频]消息元素'''
    file: str
    '''[参见napcat]'''
    type: str = field(default='video', init=False)


@dataclass(frozen=True)
class Dice(OccupyElement):
    '''[骰子]消息元素'''
    type: str = field(default='dice', init=False)


@dataclass(frozen=True)
class Rps(OccupyElement):
    '''[猜拳]消息元素'''
    type: str = field(default='rps', init=False)


@dataclass(frozen=True)
class Music(OccupyElement):
    '''[音乐分享]消息元素'''
    music_id: int
    '''[参见napcat]'''
    music_type: Literal['qq','163','kugou','migu','kuwo']
    '''[必选]'''
    type: str = field(default='music', init=False)
    
    def to_dict(self):
        return {
            'type': 'music',
            'data': {
                'type': self.music_type,
                'id': self.music_id
            }
        }


@dataclass(frozen=True)
class CustomMusic(OccupyElement):
    '''[自定义音乐分享]消息元素'''
    music_type: str = field(default='custom', init=False)
    url: str = None
    '''[网址]点击后跳转目标 URL'''
    audio: str = None
    '''[网址]音乐 URL'''
    title: str = None
    '''[参见napcat]'''
    image: str = "kuwo"
    singer: str = "kuwo"
    type: str = field(default='music', init=False)

    def to_dict(self) -> dict:
        return {
            'type': self.type,
            'data': {
                'type': self.music_type,
                'url': self.url,
                'audio': self.audio,
                'title': self.title,
                'image': self.image,
                'singer': self.singer
            }
        }

@dataclass(frozen=True)
class File(OccupyElement):
    '''文件信息元素'''
    file_id: int
    file_size: int
    file: str = None
    path: str = None
    url: str = None


@dataclass(frozen=True)
class Nope(OccupyTypeElement):
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
    '''MessageChain'''

# TODO: Markdown
@dataclass(frozen=True)
class Markdown(OccupyElement):
    content: dict
    type: str = field(default='markdown', init=False)
    def __post_init__(self, markdown: str):
        ValueError('这是TODO,还没实现呢')

    def to_dict(self) -> dict:
        ValueError('这是TODO,还没实现呢')