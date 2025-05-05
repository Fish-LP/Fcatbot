import re
from typing import Dict, Any, List

from permission_parser import Parser, Literal, Segment, Wildcard, ChoiceGroup, RegexSegment, FormatSegment


class Tree:
    """
    负责管理字典树结构和相关操作。
    使用字典嵌套字典的方式构建树结构，其中每个节点可以是字典或 None。
    None 表示路径的尽头。
    """

    def __init__(self) -> None:
        self.root: Dict[str, Any] = {}

    def insert(self, pattern_str: str) -> None:
        """
        将解析后的权限路径片段插入到字典树中。
        只支持纯字面量路径的插入，通配符、选项组、正则表达式和格式化占位符段的路径无法插入。

        Args:
            pattern_str: 权限路径字符串。

        Raises:
            ValueError: 如果路径包含非 Literal 段。
        """
        segments = self._parse_segments(pattern_str)
        current: Dict[str, Any] = self.root
        for segment in segments:
            if not isinstance(segment, Literal):
                raise ValueError("只能添加纯字面量路径到权限树")
            key: str = segment.value
            if key not in current:
                current[key] = {}
            current = current[key]
        # 将 None 作为路径结束的标志
        current[None] = None

    def match(self, pattern_str: str) -> bool:
        """
        在字典树中查找匹配的权限路径。

        Args:
            pattern_str: 权限路径字符串。

        Returns:
            bool: 如果路径完全匹配，则返回 True；否则返回 False。
        """
        segments = self._parse_segments(pattern_str)
        return self._recursive_match(self.root, segments)

    def _parse_segments(self, pattern_str: str) -> List[Segment]:
        """
        使用内部的 Parser 解析路径字符串为 Segment 列表。

        Args:
            pattern_str: 权限路径字符串。

        Returns:
            List[Segment]: 解析后的路径片段列表。
        """
        parser = Parser()
        return parser.parse(pattern_str).patterns

    def _recursive_match(self, current_node: Dict[str, Any], segments: List[Segment]) -> bool:
        """
        递归地在字典树中查找匹配的路径。

        Args:
            current_node: 当前处理的字典树节点。
            segments: 剩余需要匹配的路径片段列表。

        Returns:
            bool: 如果路径完全匹配，则返回 True；否则返回 False。
        """
        if not segments:
            # 检查是否到达路径的尽头
            return None in current_node

        current_segment: Segment = segments[0]

        if isinstance(current_segment, Literal):
            # 处理字面量段
            key: str = current_segment.value
            if key in current_node:
                return self._recursive_match(current_node[key], segments[1:])
            return False

        elif isinstance(current_segment, Wildcard):
            # 处理通配符段
            if current_segment.scope == '*':
                # 单层通配符匹配当前层的所有可能
                for key in current_node.keys():
                    if key is not None:  # 跳过路径结束标志
                        if segments[1:]:
                            return self._recursive_match({key: current_node[key]}, segments[1:])
                        else:
                            return True
                return False
            else:
                # 多层通配符匹配所有可能的后续路径
                for key in current_node:
                    if key is not None:  # 跳过路径结束标志
                        if segments[1:]:
                            return self._recursive_match({key: current_node[key]}, segments[1:])
                        else:
                            return True
                return False

        elif isinstance(current_segment, ChoiceGroup):
            # 处理选项组段
            for option in current_segment.options:
                if option in current_node:
                    return self._recursive_match(current_node[option], segments[1:])
                else:
                    return False
            return False

        elif isinstance(current_segment, RegexSegment):
            # 处理正则表达式段
            for key in current_node:
                if key is not None and re.match(current_segment.pattern, key):
                    if self._recursive_match(current_node[key], segments[1:]):
                        return True
            return False

        elif isinstance(current_segment, FormatSegment):
            raise ValueError(f'意外的格式化字符串节点')
            for key in current_node:
                if key is not None:
                    if self._recursive_match(current_node[key], segments[1:]):
                        return True
            return False

        else:
            # 未知的段类型
            raise ValueError(f'未知节点: {type(current_segment)}', seq = current_segment)
            return False


class PermissionTree:
    """
    权限树的对外接口类。
    提供方法来添加权限路径和检查权限路径是否匹配。
    """

    def __init__(self) -> None:
        self.tree: Tree = Tree()

    def add(self, pattern_str: str) -> None:
        """
        将权限路径添加到权限树中。
        只支持纯字面量路径的添加。

        Args:
            pattern_str: 权限路径字符串。

        Raises:
            ValueError: 如果路径包含非字面量段。
        """
        self.tree.insert(pattern_str)

    def check(self, pattern_str: str) -> bool:
        """
        检查给定的权限路径是否匹配权限树中的任何路径。

        Args:
            pattern_str: 要检查的权限路径字符串。

        Returns:
            bool: 如果匹配，则返回 True；否则返回 False。
        """
        return self.tree.match(pattern_str)

    @classmethod
    def match(cls, pattern: str, pattern_str: str) -> bool:
        """
        静态方法，用于快速匹配给定的模式字符串和目标字符串。

        该方法会构建一个临时的字典树，并将模式字符串插入到树中，然后检查目标字符串是否匹配。

        Args:
            pattern (str): 模式字符串，用于构建字典树。
            pattern_str (str): 目标字符串，用于匹配。

        Returns:
            bool: 如果目标字符串匹配模式字符串，则返回 True；否则返回 False。
        """
        t: dict = {}
        c: dict = t
        for n in pattern.split('.'):
            t[n] = {}
            t = t[n]
        return Tree()._recursive_match(c, pattern_str)