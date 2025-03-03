# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-24 21:56:27
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-03 23:04:26
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

    def create_role(self, role_name: str) -> None:
        """
        创建新角色
        
        Args:
            role_name: 角色名称
        """
        if role_name in self.roles:
            raise ValueError(f"角色 {role_name} 已经存在")
        self.roles[role_name] = Role(role_name)

    def add_role_parent(self, role_name: str, parent_name: str) -> None:
        """
        为角色添加父角色
        
        Args:
            role_name: 角色名称
            parent_name: 父角色名称
        """
        role = self.roles.get(role_name)
        parent = self.roles.get(parent_name)
        if not role or not parent:
            raise ValueError(f"角色 {role_name} 没有找到, 请先创建")
        role.add_parent(parent)

    def revoke_permission(self, role_name: str, path: str) -> None:
        """
        移除角色的权限
        
        Args:
            role_name: 角色名称
            path: 权限路径
        """
        role = self.roles.get(role_name)
        if not role:
            raise ValueError(f"角色 {role_name} 没有找到, 请先创建")
        role.remove_permission(path)

    def assign_permission(self, role_name: str, path: str) -> None:
        """
        为角色添加权限
        
        Args:
            role_name: 角色名称
            path: 权限路径
        """
        role = self.roles.get(role_name)
        if not role:
            raise ValueError("角色不存在")
        try:
            role.permissions.add_permission(path, role.name)
        except ValueError as e:
            raise ValueError(f"无效权限路径 '{path}': {e}")

    def create_user(self, user_name: str) -> None:
        """
        创建新用户
        
        Args:
            user_name: 用户名称
        """
        if user_name in self.users:
            raise ValueError(f"用户 {user_name} 已经存在")
        self.users[user_name] = User(user_name)

    def assign_role_to_user(self, user_name: str, role_name: str) -> None:
        """
        为用户分配角色
        
        Args:
            user_name: 用户名称
            role_name: 角色名称
        """
        user = self.users.get(user_name)
        role = self.roles.get(role_name)
        if not user:
            raise ValueError(f"用户 {user_name} 没有找到, 请先创建")
        if not role:
            raise ValueError(f"角色 {role_name} 没有找到, 请先创建")
        user.roles.append(role)
