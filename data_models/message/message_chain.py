# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:35:26
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-22 15:57:16
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import inspect
from typing import Union, List, Dict, Any, Iterable
import json

from .message_nope import *

class MessageChain:
    """消息链类,用于管理多个消息元素"""
    type_handlers = {
        'text': lambda data: Text(**data),
        'at': lambda data: At(**data),
        'image': lambda data: Image(**data),
        'face': lambda data: Face(**data),
        'reply': lambda data: Reply(**data),
        'json': lambda data: Json(**data),
        'record': lambda data: Record(**data),
        'video': lambda data: Video(**data),
        'dice': lambda data: Dice(),
        'rps': lambda data: Rps(),
        'music': lambda data: Music(**data),
        'custom_music': lambda data: CustomMusic(**data),
        'markdown': lambda data: Markdown(**data),
        'file': lambda data: File(**data),
    }
    
    behavior_handlers = {
        Behavior.DAFAULT:   lambda elements, element: elements,
        Behavior.TOP:       lambda elements, element: [element] + [x for x in elements if x != element],
        Behavior.OCCUPY:    lambda elements, element: [element],
        Behavior.OccupyType:lambda elements, element: [elt for elt in elements if elt.type == element.type],
    }
    
    def __init__(self, elements: List[dict] = None):
        """
        初始化消息链
        :param elements: 初始消息元素列表
        """
        self.decorate_add_methods(self.check_message_chain)
        self.elements = []
        if elements is not None:
            for element in elements:
                if isinstance(element, dict):
                    self.elements.append(self._guessing_type(data = element['data'], type_ = element.get('type', None)))
                elif getattr(element,'type',None) in set(self.type_handlers.keys()):
                    self.elements.append(element)
        self.check_message_chain()

    @classmethod
    def _guessing_type(cls, data: dict, type_: str = None):
        if type_ is not None:
            try:
                result = cls.type_handlers[type_](data)
                return result
            except TypeError as e:
                raise TypeError(f"{type_} 初始化错误 {e.args}")

        for handler in cls.type_handlers.values():
            try:
                result = handler(data)
                return result
            except (TypeError, ValueError):
                continue
        raise ValueError("未知的数据类型")

    def add(self, element: Union[dict ,Element, Iterable[Element]]) -> 'MessageChain':
        """
        向消息链中添加新的消息元素
        :param element: 单个消息元素或元素列表
        """
        if isinstance(element, dict):
            self.elements.append(self._guessing_type(element))
        elif isinstance(element, Iterable):
            for elem in element:
                if not isinstance(elem, Element):
                    self.elements.append(self._guessing_type(elem))
                elif getattr(element,'type', None) in self.type_handlers:
                    self.elements.append(elem)
        elif getattr(element,'type', None) in set(self.type_handlers.keys()):
            self.elements.append(element)
        else:
            raise TypeError(f"添加的元素必须是消息元素或元素列表或字典,但收到类型为 {type(elem)}")
        return self

    def remove(self, element_type: Union[Element, list[Element]]) -> 'MessageChain':
        """
        从消息链中移除指定类型的所有消息元素
        :param element_type: 要移除的消息元素类型
        """
        if isinstance(element_type, list):
            types = tuple(element_type)
        else:
            types = element_type
        self.elements = [event for event in self.elements if not isinstance(event, types)]
        return self

    def filter(self, element_type: Union[Element, list[Element]]) -> 'MessageChain':
        """
        从消息链中移除指定类型外的所有消息元素
        :param element_type: 要保留的消息元素类型
        """
        if isinstance(element_type, list):
            types = tuple(element_type)
        else:
            types = element_type
        self.elements = [event for event in self.elements if event.type == types]
        return self

    def to_dict(self) -> List[Dict[str, Any]]:
        """
        将消息链转换为可序列化的字典列表
        """
        return [element.to_dict() for element in self.elements]

    def clear(self) -> None:
        self.elements.clear()

    def __str__(self) -> str:
        """
        返回消息链的 JSON 字符串表示
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def __call__(self) -> str:
        """
        直接调用时返回 JSON 字符串
        """
        return self.__str__()

    def __iter__(self):
        """
        支持迭代消息链中的元素
        """
        return iter(self.elements)

    def __len__(self) -> int:
        """
        返回消息链中元素的数量
        """
        return len(self.elements)

    def __getitem__(self, index: Union[int, str]) -> Element:
        """
        根据索引获取消息链中的元素
        """
        if isinstance(index, int):
            return self.elements[index]
        elif index in self.type_handlers:
            return tuple(filter(lambda d:d.type == index, self.elements))
        raise IndexError(f'MessageChain 索引错误: {index}')

    def __setitem__(self, index: int, element: Union[dict ,Element]):
        """
        根据索引设置消息链中的元素
        """
        if isinstance(element, dict):
            self.elements[index] = self._guessing_type(element)
        elif element.type in self.type_handlers.keys():
            self.elements[index] = element
        else:
            ValueError(f"添加的元素必须是消息元素或元素列表或字典,但收到类型为 {type(element)}")

    def add_text(self, text: str) -> 'MessageChain':
        """添加文本消息元素到消息链中。

        Args:
            text (str): 要发送的文本内容。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Text(text=text))
        return self

    def add_at(self, qq: Union[int, str]) -> 'MessageChain':
        """添加@消息元素到消息链中。

        Args:
            qq (Union[int, str]): 要@的目标QQ号。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(At(qq=qq))
        return self

    def add_at_all(self) -> 'MessageChain':
        """添加 @全体消息元素"""
        self.elements.append(AtAll())
        return self

    def add_image(self, file: Union[str, bytes]) -> 'MessageChain':
        """添加图片消息元素到消息链中。

        Args:
            file (Union[str, bytes]): 图片文件路径或图片二进制数据。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Image(file=file))
        return self

    def add_face(self, id: str) -> 'MessageChain':
        """添加QQ表情元素到消息链中。

        Args:
            id (str): QQ表情的ID。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Face(id=id))
        return self

    def add_reply(self, reply_to: str) -> 'MessageChain':
        """添加回复消息元素到消息链中。

        Args:
            reply_to (str): 要回复的消息ID。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Reply(reply_to=reply_to))
        return self

    def add_json(self, data: str) -> 'MessageChain':
        """添加JSON消息元素到消息链中。

        Args:
            data (str): 要发送的JSON字符串。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Json(data=data))
        return self

    def add_record(self, file: str) -> 'MessageChain':
        """添加语音消息元素到消息链中。

        Args:
            file (str): 语音文件的路径。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Record(file=file))
        return self

    def add_video(self, file: str) -> 'MessageChain':
        """添加视频消息元素到消息链中。

        Args:
            file (str): 视频文件的路径。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Video(file=file))
        return self

    def add_dice(self) -> 'MessageChain':
        """添加骰子消息元素到消息链中。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Dice())
        return self

    def add_rps(self) -> 'MessageChain':
        """添加猜拳消息元素到消息链中。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Rps())
        return self

    def add_music(self, music_type: str, music_id: int) -> 'MessageChain':
        """添加音乐分享消息元素到消息链中。

        Args:
            music_type (str): 音乐平台类型，可选值：'qq'、'163'、'kugou'、'migu'、'kuwo'。
            music_id (int): 音乐ID。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Music(music_type=music_type, music_id=music_id))
        return self

    def add_custom_music(self, url: str, audio: str, title: str, image: str = "", singer: str = "") -> 'MessageChain':
        """添加自定义音乐分享消息元素到消息链中。

        Args:
            url (str): 点击后跳转的目标URL。
            audio (str): 音乐文件的URL。
            title (str): 音乐标题。
            image (str, optional): 音乐封面图片URL。默认为空字符串。
            singer (str, optional): 歌手名称。默认为空字符串。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(CustomMusic(url=url, audio=audio, title=title, image=image, singer=singer))
        return self

    def add_markdown(self, markdown: dict) -> 'MessageChain':
        """添加Markdown消息元素到消息链中。

        Args:
            markdown (dict): Markdown格式的消息内容字典。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Markdown(markdown=markdown))
        return self

    def add_nope(self, user_id: str, nickname: str, content: 'MessageChain') -> 'MessageChain':
        """添加转发消息节点到消息链中。

        Args:
            user_id (str): 转发消息的用户ID。
            nickname (str): 转发消息的用户昵称。
            content (MessageChain): 转发消息的内容。

        Returns:
            MessageChain: 返回消息链本身，支持链式调用。
        """
        self.elements.append(Nope(NopeData(user_id=user_id, nickname=nickname, content=content)))
        return self

    def check_message_chain(self):
        '''保证elements顺序正确'''
        element: Element
        for element in self.elements.copy():
            self.elements = self.behavior_handlers[element.behavior](self.elements, element)

    def decorate_add_methods(self, func):
        """
        动态装饰以“add_”开头的方法,在方法执行后自动执行提供的函数 `func`
        :param func: 方法执行后要调用的函数
        """
        # 遍历类的实例方法
        for method_name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if method_name.startswith('add_'):
                # 创建闭包装饰器
                def wrapper(original_method):
                    def inner_wrapper(*args, **kwargs):
                        # 调用原始方法并等待其执行完毕
                        result = original_method(*args, **kwargs)
                        # 调用回调函数 `func`
                        func()
                        # 返回方法结果
                        return result
                    return inner_wrapper

                # 替换原始方法
                setattr(self, method_name, wrapper(method))