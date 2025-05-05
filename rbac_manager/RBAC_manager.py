from collections import defaultdict
from permission_tree import PermissionTree

class Role:
    """表示一个角色及其权限集合"""
    def __init__(self, name: str):
        self.name = name
        self.permission_tree = PermissionTree()

    def add_permission(self, permission_pattern: str) -> None:
        """为角色添加权限路径（仅支持纯字面量）"""
        self.permission_tree.add(permission_pattern)

class PermissionManager:
    """RBAC权限管理器"""
    def __init__(self):
        self.roles: dict[str, Role] = {}
        self.user_roles: dict[str, list[str]] = defaultdict(list)

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

    def add_permission(self, role_name: str, permission_pattern: str) -> None:
        """为角色添加权限"""
        role = self.roles.get(role_name)
        if not role:
            raise ValueError(f"角色 {role_name} 不存在")
        role.add_permission(permission_pattern)

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
        """检查用户是否具有指定权限"""
        for role_name in self.user_roles.get(user_id, []):
            role = self.roles.get(role_name)
            if role and role.permission_tree.check(permission_pattern):
                return True
        return False
