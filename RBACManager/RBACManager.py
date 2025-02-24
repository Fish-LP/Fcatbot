# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-24 21:56:27
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-24 22:00:00
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from .Role import Role
from .User import User
from typing import Dict

class RBACManager:
    """RBAC管理类，负责管理角色、用户和权限操作"""
    def __init__(self, case_sensitive: bool = True) -> None:
        self.roles: Dict[str, Role] = {}        # 角色映射
        self.users: Dict[str, User] = {}         # 用户映射
        self.case_sensitive: bool = case_sensitive  # 是否区分大小写

    def create_role(self, name: str) -> None:
        """创建新角色"""
        if name in self.roles:
            raise ValueError(f"Role {name} already exists")
        self.roles[name] = Role(name)

    def add_role_parent(self, role_name: str, parent_name: str) -> None:
        """为角色添加父角色"""
        role = self.roles.get(role_name)
        parent = self.roles.get(parent_name)
        if not role or not parent:
            raise ValueError("Role not found")
        role.add_parent(parent)

    def revoke_permission(self, role_name: str, path: str) -> bool:
        """撤销角色的权限"""
        role = self.roles.get(role_name)
        if not role:
            raise ValueError("角色不存在")
        return role.remove_permission(path)

    def assign_permission(self, role_name: str, path: str) -> None:
        """为角色分配权限路径"""
        role = self.roles.get(role_name)
        if not role:
            raise ValueError("角色不存在")
        try:
            role.permissions.add_permission(path, role.name)
        except ValueError as e:
            raise ValueError(f"无效权限路径 '{path}': {e}")

    def create_user(self, user_id: str) -> None:
        """创建新用户"""
        if user_id in self.users:
            raise ValueError(f"User {user_id} already exists")
        self.users[user_id] = User(user_id)

    def assign_role_to_user(self, user_id: str, role_name: str) -> None:
        """为用户分配角色"""
        user = self.users.get(user_id)
        role = self.roles.get(role_name)
        if not user or not role:
            raise ValueError("User or role not found")
        user.roles.append(role)
