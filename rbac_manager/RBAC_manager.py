# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-03-21 18:06:59
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-16 19:20:56
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from collections import defaultdict
from typing import Dict, List, Tuple
from .permission_tree import Tree, PermissionTree
from .permission_parser import Parser, PermissionPath, Segment

class Role:
    """表示一个角色及其权限集合"""
    def __init__(self, name: str):
        self.name = name
        self.parent_roles: set[str] = set()  # 父角色集合
        # 权限描述分为 allow/deny 两类
        self.permission_descriptions: dict[str, list[str]] = {'allow': [], 'deny': []}
        self._parser = Parser()

    def add_permission_description(self, permission_pattern: str, effect: str = 'allow') -> None:
        """为角色添加权限描述（可包含任意段），支持 allow/deny"""
        if effect not in ('allow', 'deny'):
            raise ValueError("effect 必须为 'allow' 或 'deny'")
        self.permission_descriptions[effect].append(permission_pattern)

    def get_permission_segments(self, effect: str = None) -> List[List[Segment]]:
        """获取所有权限描述的Segment列表，可指定 effect"""
        if effect:
            return [self._parser.parse(p).patterns for p in self.permission_descriptions.get(effect, [])]
        # 返回所有
        return [self._parser.parse(p).patterns for eff in self.permission_descriptions for p in self.permission_descriptions[eff]]

class PermissionManager:
    """RBAC权限管理器"""
    def __init__(self):
        self.roles: dict[str, Role] = {}
        self.user_roles: dict[str, list[str]] = defaultdict(list)
        self.real_permission_tree = PermissionTree()  # 真实权限树（仅字面量段）
        self._parser = Parser()

    def create_role(self, role_name: str) -> None:
        """创建新角色"""
        if role_name in self.roles:
            raise ValueError(f"角色 {role_name} 已存在")
        self.roles[role_name] = Role(role_name)

    def delete_role(self, role_name: str) -> None:
        """删除角色"""
        if role_name not in self.roles:
            raise ValueError(f"角色 {role_name} 不存在")
        del self.roles[role_name]

    def set_role_inheritance(self, role_name: str, parent_role_name: str) -> None:
        """设置角色继承关系"""
        if role_name not in self.roles:
            raise ValueError(f"角色 {role_name} 不存在")
        if parent_role_name not in self.roles:
            raise ValueError(f"父角色 {parent_role_name} 不存在")
        if role_name == parent_role_name:
            raise ValueError("不能自己继承自己")
        # 检查无循环继承
        if self._has_inheritance_cycle(role_name, parent_role_name):
            raise ValueError("不能形成循环继承关系")
        
        role = self.roles[role_name]
        role.parent_roles.add(parent_role_name)

    def _has_inheritance_cycle(self, role_name: str, parent_role_name: str) -> bool:
        """检测添加继承后是否会形成循环"""
        visited = set()
        def dfs(r):
            if r == role_name:
                return True
            visited.add(r)
            for p in self.roles[r].parent_roles:
                if p not in visited and dfs(p):
                    return True
            return False
        return dfs(parent_role_name)

    def remove_role_inheritance(self, role_name: str, parent_role_name: str) -> None:
        """移除角色继承关系"""
        if role_name in self.roles:
            self.roles[role_name].parent_roles.discard(parent_role_name)

    def add_real_permission(self, permission_pattern: str, effect: str = 'allow') -> None:
        """添加真实权限（仅字面量段）到总权限树"""
        segments = self._parser.parse(permission_pattern).patterns
        if not all(isinstance(seg, Segment) and seg.__class__.__name__ == 'Literal' for seg in segments):
            raise ValueError("只能添加纯字面量权限到真实权限树")
        self.real_permission_tree.add_segments(segments, effect)

    def add_permission_description(self, role_name: str, permission_pattern: str, effect: str = 'allow') -> None:
        """为角色添加权限描述（可包含任意段），支持 allow/deny"""
        role = self.roles.get(role_name)
        if not role:
            raise ValueError(f"角色 {role_name} 不存在")
        role.add_permission_description(permission_pattern, effect)

    def assign_role(self, user_id: str, role_name: str) -> None:
        """为用户分配角色"""
        if role_name not in self.roles:
            raise ValueError(f"角色 {role_name} 不存在")
        if role_name not in self.user_roles[user_id]:
            self.user_roles[user_id].append(role_name)

    def revoke_role(self, user_id: str, role_name: str) -> None:
        """移除用户的角色"""
        if role_name in self.user_roles.get(user_id, []):
            self.user_roles[user_id].remove(role_name)

    def check_permission(self, user_id: str, permission_pattern: str) -> bool:
        segments = self._parser.parse(permission_pattern).patterns
        checked_roles = set()
        deny_matched = False
        allow_matched = False

        # 检查所有角色的权限（包括继承）
        for role_name in self.user_roles.get(user_id, []):
            self._check_role(role_name, segments, checked_roles, deny_matched, allow_matched)

        # 最终结果：deny 优先
        return not deny_matched and allow_matched

    def _check_role(self, role_name: str, segments: List[Segment], checked_roles: set, deny_matched: bool, allow_matched: bool):
        if role_name in checked_roles:
            return
        checked_roles.add(role_name)
        role = self.roles.get(role_name)
        if not role:
            return

        # 检查当前角色的 deny 规则
        for desc in role.permission_descriptions.get('deny', []):
            desc_segments = self._parser.parse(desc).patterns
            if Tree._recursive_match(desc_segments, segments):
                deny_matched = True

        # 仅当未匹配 deny 时检查 allow
        if not deny_matched:
            for desc in role.permission_descriptions.get('allow', []):
                desc_segments = self._parser.parse(desc).patterns
                if Tree._recursive_match(desc_segments, segments):
                    allow_matched = True

        # 递归检查父角色
        for parent in role.parent_roles:
            self._check_role(parent, segments, checked_roles, deny_matched, allow_matched)

    def _get_role_real_permissions(self, role_name: str) -> List[List[Segment]]:
        """获取角色拥有的所有真实权限（字面量段）"""
        # 可扩展为角色分配的真实权限集合
        # 这里只返回空，实际应维护角色分配的真实权限
        return []

    def _match_permission(self, desc_segments: List[Segment], target_segments: List[Segment]) -> bool:
        """匹配权限描述与目标权限"""
        # 可用Tree._recursive_match或自定义匹配
        return Tree._recursive_match(target_segments, desc_segments)
