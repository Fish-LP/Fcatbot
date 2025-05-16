# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-05 14:35:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-16 19:13:42
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
import re
from typing import Dict, Any, List

from .permission_parser import Parser, Literal, Segment, Wildcard, ChoiceGroup, RegexSegment, FormatSegment


class Tree:
    """
    负责管理字典树结构和相关操作。
    使用字典嵌套字典的方式构建树结构，其中每个节点可以是字典或 None。
    None 表示路径的尽头。
    """

    def __init__(self) -> None:
        self.allow_root: Dict[str, Any] = {}
        self.deny_root: Dict[str, Any] = {}

    def insert_segments(self, segments: List[Segment], effect: str = 'allow'):
        """
        将解析后的权限路径片段插入到字典树中。
        
        Args:
            pattern_str: 权限路径字符串。
            effect: 权限规则效果，默认为 'allow'。

        Raises:
            ValueError: 如果路径包含非 Literal 段。
        """
        root = self.allow_root if effect == 'allow' else self.deny_root
        current = root
        for seg in segments:
            # 使用 Segment 对象本身作为键（需确保 __hash__ 正确）
            if seg not in current:
                current[seg] = {}
            current = current[seg]
        current[None] = None  # 标记路径终点

    def insert_segments(self, segments: List[Segment], effect: str = 'allow') -> None:
        """
        将解析后的权限路径片段插入到字典树中，支持任意类型的 Segment。
        """
        root = self.allow_root if effect == 'allow' else self.deny_root
        current = root
        for seg in segments:
            if seg not in current:
                current[seg] = {}
            current = current[seg]
        current[None] = None

    def match(self, pattern_str: str, effect: str = None) -> bool:
        """
        在字典树中查找匹配的权限路径。

        Args:
            pattern_str: 权限路径字符串。
            effect: 权限规则效果，默认为 None。

        Returns:
            bool: 如果路径完全匹配，则返回 True；否则返回 False。
        """
        segments = self._parse_segments(pattern_str)
        if effect == 'allow':
            return self._recursive_match(self.allow_root, segments)
        elif effect == 'deny':
            return self._recursive_match(self.deny_root, segments)
        else:
            # 如果未指定效果，则同时检查允许和拒绝规则
            return (self._recursive_match(self.allow_root, segments) or 
                    self._recursive_match(self.deny_root, segments))

    def match_segments(self, segments: List[Segment], effect: str = None) -> bool:
        """
        在字典树中查找匹配的权限路径（支持任意类型的 Segment）。
        """
        root = self.allow_root if effect == 'allow' else self.deny_root
        return self._recursive_match_segments(root, segments)

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

    @classmethod
    def _recursive_match_segments(cls, node: dict, segments: List[Segment]) -> bool:
        if not segments:
            return None in node
        seg = segments[0]
        for key in node:
            if key is not None and key == seg:
                if cls._recursive_match_segments(node[key], segments[1:]):
                    return True
        return False

    @classmethod
    def _recursive_match(cls, node: dict, target_segments: List[Segment]) -> bool:
        if not target_segments:
            return None in node  # 路径终点匹配

        current_seg = target_segments[0]
        remaining_segs = target_segments[1:]

        for pattern_seg in node:
            if pattern_seg is None:
                continue  # 跳过终点标记

            # 直接调用 Segment 的 match 方法
            if pattern_seg.match(current_seg):
                # 处理通配符递归（如 ** 的多层匹配）
                if isinstance(pattern_seg, Wildcard) and pattern_seg.scope == '**':
                    # 尝试匹配 0 到多个剩余段
                    for i in range(len(target_segments) + 1):
                        if cls._recursive_match(node[pattern_seg], target_segments[i:]):
                            return True
                else:
                    if cls._recursive_match(node[pattern_seg], remaining_segs):
                        return True
        return False


class PermissionTree:
    """
    权限树的对外接口类。
    提供方法来添加权限路径和检查权限路径是否匹配。
    """

    def __init__(self) -> None:
        self.tree: Tree = Tree()

    def add(self, pattern_str: str, effect: str = 'allow') -> None:
        """
        将权限路径添加到权限树中。
        只支持纯字面量路径的添加。

        Args:
            pattern_str: 权限路径字符串。
            effect: 权限规则效果，默认为 'allow'。

        Raises:
            ValueError: 如果路径包含非字面量段。
        """
        self.tree.insert(pattern_str, effect)

    def add_segments(self, segments: List[Segment], effect: str = 'allow') -> None:
        self.tree.insert_segments(segments, effect)

    def check(self, pattern_str: str, effect: str = None) -> bool:
        """
        检查给定的权限路径是否匹配权限树中的任何路径。

        Args:
            pattern_str: 要检查的权限路径字符串。
            effect: 权限规则效果，默认为 None。

        Returns:
            bool: 如果匹配，则返回 True；否则返回 False。
        """
        return self.tree.match(pattern_str, effect)

    def check_segments(self, segments: List[Segment], effect: str = None) -> bool:
        return self.tree.match_segments(segments, effect)

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