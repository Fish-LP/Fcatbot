# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-05 14:34:56
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-05 15:34:04
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
import re
from abc import ABC
from typing import List, Tuple, Union, Optional


class Segment(ABC):
    """
    路径段基类（抽象类）。

    该类是所有路径段类型的基类，定义了路径段的基本属性和方法。
    路径段是构成权限路径的基本单元，可以是字面量、通配符、选项组、正则表达式或格式化占位符。

    Attributes:
        is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
    """

    def __init__(self, is_reversed: bool = False):
        """
        初始化路径段。

        Args:
            is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
        """
        self.is_reversed = is_reversed


class Literal(Segment):
    """
    字面量段。

    字面量段表示一个固定的字符串值，在匹配时会精确匹配该值。

    Attributes:
        value (str): 字面量段的值。
        is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
    """

    def __init__(self, value: str, is_reversed: bool = False):
        """
        初始化字面量段。

        Args:
            value (str): 字面量段的值。
            is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
        """
        super().__init__(is_reversed)
        self.value = value


class Wildcard(Segment):
    """
    通配符段。

    通配符段表示一个可以匹配任意值的占位符，可以是单层通配符（*）或多层通配符（**）。

    Attributes:
        scope (str): 通配符的范围，可以是 'single'（*）或 'recursive'（**）。
        is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
    """

    def __init__(self, scope: str, is_reversed: bool = False):
        """
        初始化通配符段。

        Args:
            scope (str): 通配符的范围，可以是 'single'（*）或 'recursive'（**）。
            is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。

        Raises:
            ValueError: 如果 scope 不是 'single' 或 'recursive'，则抛出 ValueError。
        """
        super().__init__(is_reversed)
        valid_scopes = {'single', 'recursive', '*', '**'}
        if scope not in valid_scopes:
            raise ValueError("通配符范围必须是'single'(*)或'recursive'(**)")
        self.scope = '*' if scope in {'single', '*'} else '**'


class ChoiceGroup(Segment):
    """
    选项组段。

    选项组段表示一个可以匹配多个选项之一的占位符。

    Attributes:
        options (Tuple[str]): 选项组段的选项列表。
        is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
    """

    def __init__(self, options: Union[List[str], Tuple[str]], is_reversed: bool = False):
        """
        初始化选项组段。

        Args:
            options (Union[List[str], Tuple[str]]): 选项组段的选项列表。
            is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
        """
        super().__init__(is_reversed)
        self.options = tuple(options)


class RegexSegment(Segment):
    """
    正则表达式段。

    正则表达式段表示一个可以匹配正则表达式的占位符。

    Attributes:
        pattern (str): 正则表达式段的正则表达式模式。
        is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
    """

    def __init__(self, pattern: str, is_reversed: bool = False):
        """
        初始化正则表达式段。

        Args:
            pattern (str): 正则表达式段的正则表达式模式。
            is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
        """
        super().__init__(is_reversed)
        self.pattern = pattern
        self._regex = re.compile(pattern)


class FormatSegment(Segment):
    """
    格式化占位段。

    格式化占位段表示一个可以匹配特定格式的占位符。

    Attributes:
        expression (str): 格式化占位段的格式化表达式。
        is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
    """

    def __init__(self, expression: str, is_reversed: bool = False):
        """
        初始化格式化占位段。

        Args:
            expression (str): 格式化占位段的格式化表达式。
            is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
        """
        super().__init__(is_reversed)
        self.expression = expression


class PermissionPath:
    """
    权限路径。

    权限路径由多个路径段组成，表示一个完整的权限路径。

    Attributes:
        path (str): 权限路径的原始字符串。
        patterns (List[Segment]): 权限路径的路径段列表。
    """

    def __init__(self, path: str, patterns: List[Segment]):
        """
        初始化权限路径。

        Args:
            path (str): 权限路径的原始字符串。
            patterns (List[Segment]): 权限路径的路径段列表。
        """
        self.path = path
        self.patterns = patterns


class PolicyRule:
    """
    权限规则容器。

    权限规则容器表示一个权限规则，包含规则效果和权限路径。

    Attributes:
        effect (str): 规则效果，可以是 'allow' 或 'deny'。
        patterns (PermissionPath): 权限路径。
    """

    def __init__(self, effect: str, patterns: PermissionPath):
        """
        初始化权限规则容器。

        Args:
            effect (str): 规则效果，可以是 'allow' 或 'deny'。
            patterns (PermissionPath): 权限路径。

        Raises:
            ValueError: 如果 effect 不是 'allow' 或 'deny'，则抛出 ValueError。
        """
        if effect not in ['allow', 'deny']:
            raise ValueError("规则效果必须是'allow'或'deny'")
        self.effect = effect
        self.patterns = patterns


class SegmentFactory:
    """
    段工厂类。

    段工厂类用于创建不同类型的路径段。
    """

    def create_segment(self, type_: str, is_reversed: bool = False, **kwargs) -> Segment:
        """
        创建路径段。

        Args:
            type_ (str): 路径段类型，可以是 'Literal'、'Wildcard'、'ChoiceGroup'、'RegexSegment' 或 'FormatSegment'。
            is_reversed (bool): 是否反转该路径段的匹配逻辑。默认为 False。
            **kwargs: 路径段的其他参数。

        Returns:
            Segment: 创建的路径段。

        Raises:
            ValueError: 如果 type_ 不是有效的路径段类型，则抛出 ValueError。
        """
        if type_ == 'Literal':
            return Literal(kwargs['value'], is_reversed)
        elif type_ == 'Wildcard':
            return Wildcard(kwargs['scope'], is_reversed)
        elif type_ == 'ChoiceGroup':
            return ChoiceGroup(kwargs['options'], is_reversed)
        elif type_ == 'RegexSegment':
            return RegexSegment(kwargs['pattern'], is_reversed)
        elif type_ == 'FormatSegment':
            return FormatSegment(kwargs['expression'], is_reversed)
        else:
            raise ValueError(f"未知的段类型: {type_}")


class Parser:
    """
    解析器类。

    解析器类用于解析权限路径字符串，将其转换为权限路径对象。
    """

    def __init__(self):
        """
        初始化解析器类。
        """
        self.segment_factory = SegmentFactory()

    def parse(self, pattern_str: str) -> PermissionPath:
        """
        解析权限路径字符串。

        Args:
            pattern_str (str): 权限路径字符串。

        Returns:
            PermissionPath: 解析后的权限路径对象。
        """
        permission_path = self._parse_single_pattern(pattern_str)
        return permission_path

    def _parse_single_pattern(self, pattern_str: str) -> PermissionPath:
        """
        解析单个权限路径字符串。

        Args:
            pattern_str (str): 权限路径字符串。

        Returns:
            PermissionPath: 解析后的权限路径对象。
        """
        segments = []
        for segment in pattern_str.split('.'):
            is_reversed, content = self._check_reversal(segment)
            seg = self._create_segment(content, is_reversed)
            segments.append(seg)
        return PermissionPath(pattern_str, segments)

    def _check_reversal(self, segment: str) -> Tuple[bool, str]:
        """
        检查路径段是否反转。

        Args:
            segment (str): 路径段字符串。

        Returns:
            Tuple[bool, str]: (是否反转, 路径段内容)
        """
        if segment.startswith('!'):
            remaining = segment[1:]
            if remaining not in ('*', '**'):
                return True, remaining
        return False, segment

    def _create_segment(self, content: str, is_reversed: bool) -> Segment:
        """
        创建路径段。

        Args:
            content (str): 路径段内容。
            is_reversed (bool): 是否反转该路径段的匹配逻辑。

        Returns:
            Segment: 创建的路径段。
        """
        if content == '*':
            return self.segment_factory.create_segment('Wildcard', is_reversed, scope='single')
        elif content == '**':
            return self.segment_factory.create_segment('Wildcard', is_reversed, scope='recursive')
        elif content.startswith('(') and content.endswith(')'):
            options = content[1:-1].split(',')
            return self.segment_factory.create_segment('ChoiceGroup', is_reversed, options=options)
        elif content.startswith('[') and content.endswith(']'):
            return self.segment_factory.create_segment('RegexSegment', is_reversed, pattern=content[1:-1])
        elif content.startswith('{') and content.endswith('}'):
            return self.segment_factory.create_segment('FormatSegment', is_reversed, expression=content[1:-1])
        else:
            return self.segment_factory.create_segment('Literal', is_reversed, value=content)