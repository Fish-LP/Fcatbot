# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:35:26
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-30 13:15:10
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import inspect
from typing import Callable, Union, List, Dict, Any, Iterable, Type, Optional
import json
import os
import time

from ...utils import get_log
from ...config import MESSAGE_ERROR_LOG, PERSISTENT_DIR
LOG = get_log('MessageChain')
from .message_nope import *

class MessageElementError(Exception):
    """消息元素错误类"""
    def __init__(self, message: str, element: Any):
        self.element = element
        super().__init__(f"消息元素错误: {message}, 元素: {element}")

class MessageChain:
    """消息链类，用于管理多个消息元素。
    
    此类提供了一系列方法来操作和管理消息元素，支持添加、删除、过滤等操作。
    支持链式调用和多种消息类型的处理。
    """
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
    
    def __init__(self, elements: Optional[List[Union[dict, Element]]] = None):
        """初始化消息链实例。

        Args:
            elements: 初始消息元素列表。可以是字典或Element对象的列表。

        Example:
            >>> chain = MessageChain([{"type": "text", "data": {"text": "hello"}}])
        """
        self.decorate_add_methods(self.check_message_chain)
        self.elements = []
        self.error_elements = []  # 记录初始化失败的元素
        
        if isinstance(elements, Iterable):
            for element in elements:
                try:
                    if isinstance(element, dict):
                        self.elements.append(self._guessing_type(
                            data=element.get('data'), 
                            type_=element.get('type', None)
                        ))
                    elif isinstance(element, Element):
                        self.elements.append(element)
                    else:
                        raise MessageElementError("不支持的元素类型", element)
                except Exception as e:
                    self.error_elements.append({
                        'element': element,
                        'error': str(e)
                    })
        elif isinstance(elements, Element):
            self.elements.append(elements)
        elif isinstance(elements, dict):
            try:
                self.elements.append(self._guessing_type( 
                    data=elements.get('data'), 
                    type_=elements.get('type', None))
                )
            except Exception as e:
                self.error_elements.append({
                    'element': elements,
                    'error': str(e)
                })
        self.check_message_chain()
        if self.error_elements:
            self._save_error_log()
    
    def get_error_elements(self) -> List[Dict[str, Any]]:
        """获取初始化失败的元素列表。

        Returns:
            List[Dict[str, Any]]: 包含错误元素和错误信息的列表。
        """
        return self.error_elements
    
    def has_errors(self) -> bool:
        """检查是否有初始化失败的元素。

        Returns:
            bool: 如果有错误元素返回True，否则返回False。
        """
        return len(self.error_elements) > 0

    # region 魔术方法定义

    def add(self, element: Union[dict, Element, Iterable[Union[dict, Element]]]) -> 'MessageChain':
        """向消息链中添加新的消息元素。

        Args:
            element: 要添加的元素。可以是单个元素或元素列表。

        Returns:
            MessageChain: 返回自身用于链式调用。

        Raises:
            TypeError: 当添加的元素类型不正确时。

        Example:
            >>> chain.add(Text("hello")).add(Image("path/to/image"))
        """
        if isinstance(element, (list, tuple)):
            for elem in element:
                if isinstance(elem, (dict, Element)):
                    self.elements.append(
                        elem if isinstance(elem, Element) else self._guessing_type(elem)
                    )
                else:
                    raise TypeError(f"不支持的元素类型: {type(elem)}")
        elif isinstance(element, (dict, Element)):
            self.elements.append(
                element if isinstance(element, Element) else self._guessing_type(element)
            )
        else:
            raise TypeError(f"不支持的元素类型: {type(element)}")
        return self

    def remove(self, element_type: Union[Type[Element], List[Type[Element]]]) -> 'MessageChain':
        """从消息链中移除指定类型的所有消息元素。

        Args:
            element_type: 要移除的消息元素类型。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        types = (element_type,) if not isinstance(element_type, list) else tuple(element_type)
        self.elements = [elem for elem in self.elements if not isinstance(elem, types)]
        return self

    def filter(self, element_type: Union[Type[Element], List[Type[Element]]]) -> 'MessageChain':
        """仅保留指定类型的消息元素。

        Args:
            element_type: 要保留的消息元素类型。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        types = (element_type,) if not isinstance(element_type, list) else tuple(element_type)
        self.elements = [elem for elem in self.elements if isinstance(elem, types)]
        return self

    def to_dict(self) -> List[Dict[str, Any]]:
        """
        将消息链转换为可序列化的字典列表。

        Returns:
            List[Dict[str, Any]]: 可序列化的字典列表。
        """
        return [element.to_dict() for element in self.elements]

    def clear(self) -> None:
        """清空消息链中的所有元素。"""
        self.elements.clear()

    def __str__(self) -> str:
        """
        返回消息链的 JSON 字符串表示。

        Returns:
            str: JSON 字符串表示的消息链。
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def __call__(self) -> str:
        """
        直接调用时返回 JSON 字符串。

        Returns:
            str: JSON 字符串表示的消息链。
        """
        return self.__str__()

    def __iter__(self):
        """
        支持迭代消息链中的元素。

        Returns:
            Iterator: 消息链元素的迭代器。
        """
        return iter(self.elements)

    def __len__(self) -> int:
        """
        返回消息链中元素的数量。

        Returns:
            int: 消息链中元素的数量。
        """
        return len(self.elements)

    def __getitem__(self, index: Union[int, str]) -> Element:
        """
        根据索引获取消息链中的元素。

        Args:
            index: 索引，可以是整数或字符串。

        Returns:
            Element: 对应索引的消息元素。

        Raises:
            IndexError: 当索引错误时抛出。
        """
        if isinstance(index, int):
            return self.elements[index]
        elif index in self.type_handlers:
            return tuple(filter(lambda d:d.type == index, self.elements))
        raise IndexError(f'MessageChain 索引错误: {index}')

    def __setitem__(self, index: int, element: Union[dict ,Element]):
        """
        根据索引设置消息链中的元素。

        Args:
            index: 索引。
            element: 要设置的元素，可以是字典或Element对象。

        Raises:
            ValueError: 当添加的元素类型不正确时抛出。
        """
        if isinstance(element, dict):
            self.elements[index] = self._guessing_type(element)
        elif element.type in self.type_handlers.keys():
            self.elements[index] = element
        else:
            ValueError(f"添加的元素必须是消息元素或元素列表或字典,但收到类型为 {type(element)}")
    # endregion

    # region add_ 方法声明

    def add_text(self, text: str) -> 'MessageChain':
        """添加文本消息元素。

        Args:
            text: 要发送的文本内容。

        Returns:
            MessageChain: 返回自身用于链式调用。

        Example:
            >>> chain.add_text("Hello, world!")
        """
        self.elements.append(Text(text=text))
        return self

    def add_at(self, qq: Union[int, str]) -> 'MessageChain':
        """添加@消息元素。

        Args:
            qq: 要@的目标QQ号。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(At(qq=qq))
        return self

    def add_at_all(self) -> 'MessageChain':
        """添加 @全体消息元素。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(AtAll())
        return self

    def add_image(self, file: Union[str, bytes]) -> 'MessageChain':
        """添加图片消息元素。

        Args:
            file: 图片文件路径或图片二进制数据。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Image(file=file))
        return self

    def add_face(self, id: str) -> 'MessageChain':
        """添加QQ表情元素。

        Args:
            id: QQ表情的ID。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Face(id=id))
        return self

    def add_reply(self, id: str) -> 'MessageChain':
        """添加回复消息元素。

        Args:
            id: 要回复的消息ID。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Reply(id=id))
        return self

    def add_json(self, data: str) -> 'MessageChain':
        """添加JSON消息元素。

        Args:
            data: 要发送的JSON字符串。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Json(data=data))
        return self

    def add_record(self, file: str) -> 'MessageChain':
        """添加语音消息元素。

        Args:
            file: 语音文件的路径。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Record(file=file))
        return self

    def add_video(self, file: str) -> 'MessageChain':
        """添加视频消息元素。

        Args:
            file: 视频文件的路径。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Video(file=file))
        return self

    def add_dice(self) -> 'MessageChain':
        """添加骰子消息元素。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Dice())
        return self

    def add_rps(self) -> 'MessageChain':
        """添加猜拳消息元素。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Rps())
        return self

    def add_music(self, music_type: str, music_id: int) -> 'MessageChain':
        """添加音乐分享消息元素。

        Args:
            music_type: 音乐平台类型，可选值：'qq'、'163'、'kugou'、'migu'、'kuwo'。
            music_id: 音乐ID。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Music(music_type=music_type, music_id=music_id))
        return self

    def add_custom_music(self, url: str, audio: str, title: str, image: str = "", singer: str = "") -> 'MessageChain':
        """添加自定义音乐分享消息元素。

        Args:
            url: 点击后跳转的目标URL。
            audio: 音乐文件的URL。
            title: 音乐标题。
            image: 音乐封面图片URL。默认为空字符串。
            singer: 歌手名称。默认为空字符串。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(CustomMusic(url=url, audio=audio, title=title, image=image, singer=singer))
        return self

    def add_markdown(self, markdown: dict) -> 'MessageChain':
        """添加Markdown消息元素。

        Args:
            markdown: Markdown格式的消息内容字典。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Markdown(markdown=markdown))
        return self

    def add_nope(self, user_id: str, nickname: str, content: 'MessageChain') -> 'MessageChain':
        """添加转发消息节点。

        Args:
            user_id: 转发消息的用户ID。
            nickname: 转发消息的用户昵称。
            content: 转发消息的内容。

        Returns:
            MessageChain: 返回自身用于链式调用。
        """
        self.elements.append(Nope(NopeData(user_id=user_id, nickname=nickname, content=content)))
        return self

    # endregion

    @classmethod
    def _guessing_type(cls, data: Any, type_: Optional[str] = None) -> Element:
        """尝试将数据转换为消息元素。

        Args:
            data: 要转换的数据。
            type_: 指定的消息类型。

        Returns:
            Element: 转换后的消息元素实例。

        Raises:
            ValueError: 当无法识别数据类型时抛出。
        """
        if type_ is not None and type_ in cls.type_handlers:
            return cls.type_handlers[type_](data)

        if isinstance(data, Element):
            return data
            
        if isinstance(data, dict):
            for handler in cls.type_handlers.values():
                try:
                    return handler(data)
                except (TypeError, ValueError):
                    continue
                    
        raise ValueError(f"无法将类型 {type(data)} 转换为消息元素")

    def check_message_chain(self) -> None:
        """保证消息链中元素的顺序正确。

        根据每个元素的behavior属性对消息链进行重排序。
        """
        element: Element
        for element in self.elements.copy():
            self.elements = self.behavior_handlers[element.behavior](self.elements, element)

    def decorate_add_methods(self, func: Callable) -> None:
        """动态装饰以"add_"开头的方法。

        Args:
            func: 方法执行后要调用的回调函数。

        Note:
            此方法会修改所有以"add_"开头的实例方法，使其在执行后调用提供的回调函数。
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

    def _save_error_log(self) -> None:
        """保存错误日志到文件"""
        try:
            if not os.path.exists(PERSISTENT_DIR):
                os.makedirs(PERSISTENT_DIR)
                
            error_data = {
                'timestamp': time.time(),
                'errors': self.error_elements
            }
            
            # 读取现有日志
            existing_logs = []
            if os.path.exists(MESSAGE_ERROR_LOG):
                try:
                    with open(MESSAGE_ERROR_LOG, 'r', encoding='utf-8') as f:
                        existing_logs = json.load(f)
                except json.JSONDecodeError:
                    pass
            
            # 添加新的错误记录
            if not isinstance(existing_logs, list):
                existing_logs = []
            existing_logs.append(error_data)
            
            # 保存到文件
            with open(MESSAGE_ERROR_LOG, 'w', encoding='utf-8') as f:
                json.dump(existing_logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            LOG.error(f"保存消息错误日志失败: {e}")