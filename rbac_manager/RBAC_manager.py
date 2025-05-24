# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-03-21 18:06:59
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-24 14:09:15
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from typing import Dict, List
from .permission_tree import RuleTree

class Role:
    """角色类，管理权限规则"""
    def __init__(self, name: str):
        self.name = name
        self.allow_tree = RuleTree()
        self.deny_tree = RuleTree()

    def add_permission(self, permission_pattern: str) -> None:
        """添加允许权限规则"""
        self.allow_tree.add_permission(permission_pattern)
        
    def deny_permission(self, permission_pattern: str) -> None:
        """添加拒绝权限规则"""
        self.deny_tree.add_permission(permission_pattern)

    def has_permission(self, path: str) -> bool:
        """检查是否拥有某权限，优先检查拒绝权限"""
        if self.deny_tree.match(path):
            return False
        return self.allow_tree.match(path)

class User:
    """用户类，关联多个角色"""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.roles: List[Role] = []

    def assign_role(self, role: Role) -> None:
        """分配角色"""
        if role not in self.roles:
            self.roles.append(role)

    def check_permission(self, path: str) -> bool:
        """验证权限"""
        for role in self.roles:
            if role.has_permission(path):
                return True
        return False

class PermissionManager:
    """RBAC权限管理核心类"""
    def __init__(self):
        self.roles: Dict[str, Role] = {}
        self.global_permissions = RuleTree()  # 全局权限树

    def register_permission(self, permission_pattern: str) -> None:
        """注册权限"""
        self.global_permissions.add_permission(permission_pattern)

    def create_role(self, role_name: str) -> Role:
        """创建角色"""
        if role_name not in self.roles:
            self.roles[role_name] = Role(role_name)
        return self.roles[role_name]

    def assign_role(self, user: User, role_name: str) -> None:
        """为用户分配角色"""
        role = self.roles.get(role_name)
        if role:
            user.assign_role(role)

    def add_permission(self, role_name: str, permission_pattern: str) -> None:
        """为角色添加允许权限规则"""
        role = self.roles.get(role_name)
        # 只有已经注册的权限才能被分配
        if role and self.global_permissions.match(permission_pattern):
            role.add_permission(permission_pattern)
            
    def deny_permission(self, role_name: str, permission_pattern: str) -> None:
        """为角色添加拒绝权限规则"""
        role = self.roles.get(role_name)
        if role and self.global_permissions.match(permission_pattern):
            role.deny_permission(permission_pattern)
