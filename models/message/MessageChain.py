import inspect
from typing import Union, List, Dict, Any, Iterable
import json

from .Nope import *

class MessageChain:
    """消息链类，用于管理多个消息元素"""
    def __init__(self, elements: list = None):
        """
        初始化消息链
        :param elements: 初始消息元素列表
        """
        self.decorate_add_methods(self.check_message_chain)
        self.elements = []
        if elements is not None:
            for element in elements:
                self.elements.append(self._guessing_type(element['data'], element['type']))

    @staticmethod
    def _guessing_type(data: dict, type_: str = None):
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
            'file': lambda daata: File(**data)
        }
        if type_ is not None:
            try:
                result = type_handlers[type_](data)
                return result
            except TypeError as e:
                raise TypeError(f"{type_} 初始化错误 {e.args}")

        for handler in type_handlers.values():
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
        if isinstance(element, Element):
            self.elements.append(element)
        elif isinstance(element, dict):
            self.elements.append(self._guessing_type(element))
        elif isinstance(element, Iterable):
            for elem in element:
                if not isinstance(elem, Element):
                    self.elements.append(self._guessing_type(elem))
                self.elements.append(elem)
        else:
            raise TypeError(f"添加的元素必须是消息元素或元素列表或字典，但收到类型为 {type(elem)}")
        return self

    def remove(self, element_type: Union[Element, list[Element]]) -> 'MessageChain':
        """
        从消息链中移除指定类型的所有消息元素
        :param element_type: 要移除的消息元素类型
        """
        if isinstance(Element, element_type): types = [element_type]
        self.elements = [event for event in self.elements if not isinstance(event, tuple(types))]
        return self

    def filter(self, element_type: Union[Element, list[Element]]) -> 'MessageChain':
        """
        从消息链中移除指定类型外的所有消息元素
        :param element_type: 要保留的消息元素类型
        """
        if isinstance(Element, element_type): types = [element_type]
        self.elements = [event for event in self.elements if isinstance(event, tuple(types))]
        return self

    def to_dict(self) -> List[Dict[str, Any]]:
        """
        将消息链转换为可序列化的字典列表
        """
        return [element.to_dict() for element in self.elements]

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

    def __getitem__(self, index: int) -> Element:
        """
        根据索引获取消息链中的元素
        """
        return self.elements[index]

    def __setitem__(self, index: int, element: Union[dict ,Element]):
        """
        根据索引设置消息链中的元素
        """
        if isinstance(element, Element):
            self.elements[index] = element
        elif isinstance(element, dict):
            self.elements[index] = self._guessing_type(element)
        else:
            ValueError(f"添加的元素必须是消息元素或元素列表或字典，但收到类型为 {type(element)}")

    def add_text(self, text: str) -> 'MessageChain':
        """添加文本消息元素"""
        self.elements.append(Text(text=text))
        return self

    def add_at(self, qq: Union[int, str]) -> 'MessageChain':
        """添加 @ 消息元素"""
        self.elements.append(At(qq=qq))
        return self

    def add_at_all(self) -> 'MessageChain':
        """添加 @全体消息元素"""
        self.elements.append(AtAll())
        return self

    def add_image(self, file: Union[str, bytes]) -> 'MessageChain':
        """添加图片消息元素"""
        self.elements.append(Image(file=file))
        return self

    def add_face(self, face_id: int) -> 'MessageChain':
        """添加表情消息元素"""
        self.elements.append(Face(face_id=face_id))
        return self

    def add_reply(self, reply_to: str) -> 'MessageChain':
        """添加回复消息元素"""
        self.elements.append(Reply(reply_to=reply_to))
        return self

    def add_json(self, json_msg: str) -> 'MessageChain':
        """添加 JSON 消息元素"""
        self.elements.append(Json(json_msg=json_msg))
        return self

    def add_record(self, file: str) -> 'MessageChain':
        """添加语音消息元素"""
        self.elements.append(Record(file=file))
        return self

    def add_video(self, file: str) -> 'MessageChain':
        """添加视频消息元素"""
        self.elements.append(Video(file=file))
        return self

    def add_dice(self) -> 'MessageChain':
        """添加骰子消息元素"""
        self.elements.append(Dice())
        return self

    def add_rps(self) -> 'MessageChain':
        """添加猜拳消息元素"""
        self.elements.append(Rps())
        return self

    def add_music(self, music_type: str, id: str) -> 'MessageChain':
        """添加音乐分享消息元素"""
        self.elements.append(Music(music_type=music_type, id=id))
        return self

    def add_custom_music(self, url: str, audio: str, title: str, image: str = "", singer: str = "") -> 'MessageChain':
        """添加自定义音乐分享消息元素"""
        self.elements.append(CustomMusic(url=url, audio=audio, title=title, image=image, singer=singer))
        return self

    def add_markdown(self, markdown: dict) -> 'MessageChain':
        """添加 Markdown 消息元素"""
        self.elements.append(Markdown(markdown=markdown))
        return self

    def add_nope(self, user_id: str, nickname: str, content: 'MessageChain') -> 'MessageChain':
        '''添加转发消息节点'''
        self.elements.append(Nope(NopeData(user_id=user_id, nickname=nickname, content=content)))
        return self

    def check_message_chain(self, *args, **kwargs):
        '''保证elements顺序正确'''
        element: Element
        behavior_handlers = {
            Behavior.DAFAULT:   lambda elements, element: elements,
            Behavior.TOP:       lambda elements, element: move_element_to_front(elements, element),
            Behavior.OCCUPY:    lambda elements, element: [element],
            Behavior.OccupyType:lambda elements, element: [elt for elt in elements if elt.type == element.type],
        }
        def move_element_to_front(lst: list, element):
            lst.remove(element)
            lst.insert(0, element)
        for element in self.elements:
            behavior_handlers[element.behavior](self.elements, element) 

    def decorate_add_methods(self, func):
        """
        动态装饰以“add_”开头的方法，在方法执行后自动执行提供的函数 `func`
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