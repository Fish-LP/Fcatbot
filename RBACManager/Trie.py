# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-24 21:52:42
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-24 22:00:27
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from collections import deque
from typing import Dict, List, Optional, Set, Tuple

class TrieNode:
    """Trie树的节点类"""
    def __init__(self) -> None:
        """初始化节点"""
        self.children: Dict[str, TrieNode] = {}       # 普通子节点映射
        self.star: Optional[TrieNode] = None          # 单级通配符*指针
        self.star_star: Optional[TrieNode] = None     # 多级通配符**指针
        self.is_end: bool = False                     # 是否表示权限路径的终点
        self.granted_by: Set[str] = set()             # 授予该节点权限的角色集合

class PermissionTrie:
    """基于Trie树的权限管理类"""
    def __init__(self, case_sensitive: bool = True) -> None:
        """初始化权限Trie树"""
        self.root: TrieNode = TrieNode()              # 根节点
        self.case_sensitive: bool = case_sensitive    # 是否区分大小写

    def normalize_path(self, path: str) -> str:
        """路径规范化处理：
           - 统一使用小写（如果对应设置为不区分大小写）
           - 去除路径中的空段
        """
        segments = []
        for seg in path.strip().split('.'):
            if seg:  # 跳过空段
                segments.append(seg if self.case_sensitive else seg.lower())
        return '.'.join(segments)

    def remove_permission(self, path: str, role: str) -> bool:
        """移除特定角色授予的权限路径"""
        # 规范化路径
        path = self.normalize_path(path)
        segments = path.split('.') if path else []
        
        # 路径合法性校验
        try:
            self._validate_path(segments)
        except ValueError:
            return False  # 非法路径直接返回False

        # 定位到目标节点，并记录遍历路径
        traversal_path = [(self.root, None, None)]  # (当前节点, 父节点, 进入当前节点的路径段类型)
        current = self.root
        removed = False

        for seg in segments:
            # 根据当前段选择下一节点
            if seg == "*":
                next_node = current.star
                seg_type = "star"
            elif seg == "**":
                next_node = current.star_star
                seg_type = "star_star"
            else:
                next_node = current.children.get(seg)
                seg_type = "child"
            
            # 如果当前节点不存在，返回False
            if not next_node:
                return False
            
            traversal_path.append((next_node, current, seg_type))
            current = next_node

        # 检查是否到达有效权限终点
        if not current.is_end:
            return False

        # 移除角色授权记录
        if role not in current.granted_by:
            return False
        
        current.granted_by.remove(role)
        removed = True

        # 如果仍有其他角色授权，保留节点
        if current.granted_by:
            return removed

        # 标记当前节点不再作为权限终点，并尝试清理无效节点
        current.is_end = False
        self._cleanup_nodes(traversal_path)
        return removed

    def _validate_path(self, segments: List[str]) -> None:
        """校验路径格式：
           - 多级通配符**只能出现一次，并且必须位于路径末尾
        """
        star_star_positions = [i for i, seg in enumerate(segments) if seg == "**"]
        if len(star_star_positions) > 1:
            raise ValueError("路径中最多只能包含一个**通配符")
        if star_star_positions and star_star_positions[0] != len(segments)-1:
            raise ValueError("**通配符必须位于路径末尾")

    def _cleanup_nodes(self, traversal_path: List[Tuple[TrieNode, TrieNode, str]]) -> None:
        """反向遍历路径，清理不再需要的节点"""
        # 从叶子节点向上清理
        for i in range(len(traversal_path)-1, 0, -1):
            current_node, parent_node, seg_type = traversal_path[i]
            
            # 如果当前节点仍有子节点或授权记录，则保留
            retain_cond = (
                current_node.is_end
                or current_node.children
                or current_node.star
                or current_node.star_star
            )
            if retain_cond:
                break  # 不再继续清理
            
            # 根据进入类型删除节点引用
            if seg_type == "star":
                parent_node.star = None
            elif seg_type == "star_star":
                parent_node.star_star = None
            elif seg_type == "child":
                # 找到对应的子节点并删除
                for key, node in parent_node.children.items():
                    if node is current_node:
                        del parent_node.children[key]
                        break
            
            current_node = parent_node  # 继续处理父节点

    def add_permission(self, path: str, role: str) -> None:
        """添加权限路径并记录授权角色"""
        path = self.normalize_path(path)
        segments = path.split('.') if path else []
        
        # 路径合法性校验
        self._validate_path(segments)
        
        current = self.root
        for i, seg in enumerate(segments):
            is_last = i == len(segments)-1
            
            if seg == "*":
                # 单级通配符
                if not current.star:
                    current.star = TrieNode()
                current = current.star
            elif seg == "**":
                # 多级通配符，添加到当前节点
                if not current.star_star:
                    current.star_star = TrieNode()
                current = current.star_star
            else:
                # 普通段，添加到子节点
                if seg not in current.children:
                    current.children[seg] = TrieNode()
                current = current.children[seg]
        
        current.is_end = True
        current.granted_by.add(role)

    def has_permission(self, path: str) -> bool:
        """检查权限是否被授予"""
        path = self.normalize_path(path)
        segments = path.split('.') if path else []
        return self._check_segments(segments, 0, self.root)

    def _check_segments(self, segments: List[str], index: int, node: TrieNode) -> bool:
        """递归检查路径段是否匹配"""
        # 所有段匹配完成，判断是否到达权限终点
        if index == len(segments):
            return node.is_end
        
        current_seg = segments[index]
        if not self.case_sensitive:
            current_seg = current_seg.lower()  # 转换为小写

        # 尝试精确匹配
        if current_seg in node.children:
            if self._check_segments(segments, index+1, node.children[current_seg]):
                return True
        
        # 尝试单级通配符匹配
        if node.star:
            if self._check_segments(segments, index+1, node.star):
                return True
        
        # 尝试多级通配符匹配
        if node.star_star:
            # 多级通配符允许匹配当前段及后续所有段，或只匹配当前段
            return node.star_star.is_end or self._check_segments(segments, index+1, node.star_star)
        
        # 未匹配到任何段
        return False

    def visualize(self) -> str:
        """可视化权限树结构"""
        lines: List[str] = []
        self._visualize(self.root, lines, '', '', True)
        return '\n'.join(lines)

    def _visualize(self, node: TrieNode, lines: List[str], prefix: str, child_prefix: str, is_last: bool) -> None:
        """递归构建可视化字符串"""
        # 添加当前节点到展示行
        if prefix:
            line_end = '○' if not node.is_end else '●'
            lines.append(prefix + ' ' + line_end)
        
        # 构建子节点列表
        children = []
        for name, child in node.children.items():
            children.append(('child', name, child))
        if node.star:
            children.append(('star', '*', node.star))
        if node.star_star:
            children.append(('star_star', '**', node.star_star))
        
        # 遍历子节点
        for i, (type_, name, child) in enumerate(children):
            is_last_child = i == len(children)-1
            new_child_prefix = '│   ' if not is_last_child else '    '
            next_prefix = child_prefix + (new_child_prefix if not is_last else '    ')
            
            # 构建节点连接符号
            connector = '└──' if is_last_child else '├──'
            next_line_prefix = child_prefix + connector + ' ' + name
            
            self._visualize(
                child,
                lines,
                next_line_prefix,
                next_prefix,
                is_last_child
            )
