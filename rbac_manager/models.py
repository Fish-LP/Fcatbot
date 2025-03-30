from typing import List, Set, Optional, Literal

class Role:
    """
    角色类，用于管理单个角色的权限和继承关系
    
    Attributes:
        manager: RBAC管理器实例
        name: 角色名称
    """
    def __init__(self, manager, role_name: str):
        """
        初始化角色实例
        
        Args:
            manager: RBAC管理器实例
            role_name: 角色名称
        
        Raises:
            ValueError: 当角色不存在时抛出异常
        """
        self.manager = manager
        self.name = role_name
        if not manager.check_availability(role_name=role_name):
            raise ValueError(f"角色 {role_name} 不存在")

    @property
    def white_permissions(self) -> List[str]:
        """获取角色的白名单权限列表"""
        return self.manager.roles[self.name]['white_permissions_list']

    @property
    def black_permissions(self) -> List[str]:
        """获取角色的黑名单权限列表"""
        return self.manager.roles[self.name]['black_permissions_list']

    @property
    def inherited_roles(self) -> List[str]:
        """获取此角色继承的所有角色列表"""
        return self.manager.role_inheritance.get(self.name, [])

    def grant_permission(self, permission_path: str, permission_type: Literal['white', 'black'] = 'white'):
        """
        为角色授予权限
        
        Args:
            permission_path: 权限路径
            permission_type: 权限类型（white=白名单，black=黑名单）
        """
        self.manager.grant_permission_to_role(self.name, permission_path, permission_type)

    def revoke_permission(self, permission_path: str, permission_type: Literal['white', 'black']):
        """
        撤销角色的权限
        
        Args:
            permission_path: 权限路径
            permission_type: 权限类型（white=白名单，black=黑名单）
        """
        self.manager.revoke_permission_from_role(self.name, permission_path, permission_type)

    def inherit_from(self, role_name: str):
        """
        设置角色继承关系
        
        Args:
            role_name: 被继承的角色名称
        """
        self.manager.set_role_inheritance(self.name, role_name)

    def remove_inheritance(self, role_name: str):
        """
        移除角色继承关系
        
        Args:
            role_name: 要移除继承的角色名称
        """
        self.manager.remove_role_inheritance(self.name, role_name)

    def delete(self):
        """删除该角色及其所有关联"""
        self.manager.delete_role(self.name)

class User:
    """
    用户类，用于管理单个用户的权限和角色
    
    Attributes:
        manager: RBAC管理器实例
        name: 用户名称
    """
    def __init__(self, manager, user_name: str):
        """
        初始化用户实例
        
        Args:
            manager: RBAC管理器实例
            user_name: 用户名称
            
        Raises:
            ValueError: 当用户不存在时抛出异常
        """
        self.manager = manager
        self.name = user_name
        if not manager.check_availability(user_name=user_name):
            raise ValueError(f"用户 {user_name} 不存在")

    @property
    def white_permissions(self) -> List[str]:
        """获取用户的白名单权限列表"""
        return self.manager.users[self.name]['white_permissions_list']

    @property
    def black_permissions(self) -> List[str]:
        """获取用户的黑名单权限列表"""
        return self.manager.users[self.name]['black_permissions_list']

    @property
    def roles(self) -> List[str]:
        """获取用户拥有的所有角色列表"""
        return self.manager.users[self.name]['role_list']

    def has_permission(self, permission_path: str, strict_match: bool = False) -> bool:
        """
        检查用户是否拥有指定权限
        
        Args:
            permission_path: 权限路径
            strict_match: 是否启用严格匹配模式（True=仅完全匹配，False=允许通配符）
            
        Returns:
            bool: 是否拥有权限
        """
        return self.manager.check_has_permission(self.name, permission_path, strict_match)

    def grant_permission(self, permission_path: str, permission_type: Literal['white', 'black']):
        """
        为用户直接授予权限
        
        Args:
            permission_path: 权限路径
            permission_type: 权限类型（white=白名单，black=黑名单）
        """
        self.manager.grant_permission_to_user(self.name, permission_path, permission_type)

    def revoke_permission(self, permission_path: str, permission_type: Literal['white', 'black']):
        """
        撤销用户的直接权限
        
        Args:
            permission_path: 权限路径
            permission_type: 权限类型（white=白名单，black=黑名单）
        """
        self.manager.revoke_permission_from_user(self.name, permission_path, permission_type)

    def assign_role(self, role_name: str):
        """
        为用户分配角色
        
        Args:
            role_name: 角色名称
        """
        self.manager.assign_role(self.name, role_name)

    def remove_role(self, role_name: str):
        """
        移除用户的角色
        
        Args:
            role_name: 角色名称
        """
        self.manager.remove_role(self.name, role_name)

    def delete(self):
        """删除该用户及其所有权限关联"""
        self.manager.delete_user(self.name)
