# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-05 14:35:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-24 11:53:45
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from typing import Dict, Any, List, Optional
from .permission_parser import Literal, Parser, Segment, Wildcard

class BaseTree:
    """权限树基类，提供基本的树操作功能"""
    def __init__(self) -> None:
        self.root: Dict[str, Any] = {}

    def __contains__(self, path: str) -> bool:
        return self.match(path)

class RuleTree(BaseTree):
    """支持规则匹配的权限树，优化了通配符 ** 的多级匹配"""
    
    def add_permission(self, path: str) -> None:
        """添加规则路径"""
        permission = Parser.parse(path)
        current = self.root
        for seg in permission:
            key = seg if isinstance(seg, (Wildcard, Literal)) else str(seg)
            current = current.setdefault(key, {})
        current[None] = None  # 标记终点

    def match(self, path: str) -> bool:
        """匹配字面量路径是否满足规则"""
        target = [Literal(s) for s in path.split('.')]
        return self._dfs(self.root, target, 0)

    def _dfs(self, node: dict, segments: List[Segment], idx: int) -> bool:
        if idx == len(segments):
            return None in node
        
        current_segment = segments[idx]
        
        # 处理 ** 通配符的贪婪匹配
        for key in list(node.keys()):
            if key is None:
                continue
            
            # ** 可以匹配当前及后续所有层级
            if isinstance(key, Wildcard) and key.scope == "**":
                # 尝试匹配剩余所有可能路径
                for i in range(idx, len(segments)+1):
                    if self._dfs(node[key], segments, i):
                        return True
            
            # 普通通配符或字面量匹配
            elif key.match(current_segment.value):
                if self._dfs(node[key], segments, idx+1):
                    return True
        
        return False

class LiteralTree(BaseTree):
    """存储字面量路径，支持规则路径匹配，并返回所有匹配的权限路径"""

    def add_permission(self, path: str) -> None:
        """添加字面量路径"""
        current = self.root
        for seg in path.split('.'):
            current = current.setdefault(seg, {})
        current[None] = None  # 标记路径终点

    def match(self, path: str) -> List[str]:
        """用规则路径匹配存储的字面量，并返回所有匹配的权限路径"""
        rule = Parser.parse(path)
        return self._dfs(self.root, rule.patterns, 0, [])

    def _dfs(self, node: dict, rule_segments: List[Segment], idx: int, current_path: List[str]) -> List[str]:
        if idx == len(rule_segments):
            if None in node:
                return ['.'.join(current_path)]
            return []

        current_rule = rule_segments[idx]
        matches = []

        # 处理 ** 通配符
        if isinstance(current_rule, Wildcard) and current_rule.scope == "**":
            # 当前节点直接匹配后续所有可能路径
            for key in node:
                if key is not None:
                    # 尝试匹配剩余规则
                    matches.extend(self._dfs(node[key], rule_segments, idx, current_path + [key]))
                    # 或者跳过当前层级继续匹配
                    matches.extend(self._dfs(node[key], rule_segments, idx + 1, current_path + [key]))
            return matches

        # 普通匹配
        for key in node:
            if key is None:
                continue
            if current_rule.match(key):
                matches.extend(self._dfs(node[key], rule_segments, idx + 1, current_path + [key]))
        return matches