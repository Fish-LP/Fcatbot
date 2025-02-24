# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-24 21:56:15
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-24 22:02:13
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from .Trie import PermissionTrie
from typing import List, Optional

class Role:
    """角色类，包含角色名、父角色、权限树等信息"""
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.parents: List['Role'] = []       # 父角色列表
        self.permissions: PermissionTrie = PermissionTrie()  # 权限Trie树
        self._all_parents: Optional[List['Role']] = None   # 缓存的全部父角色列表

    def remove_permission(self, path: str) -> bool:
        """调用权限Trie树的权限移除方法"""
        return self.permissions.remove_permission(path, self.name)

    def add_parent(self, parent: 'Role') -> None:
        """添加父角色，并检测循环依赖"""
        if self._check_cycle(parent):
            raise ValueError("Cycle detected in role inheritance")
        self.parents.append(parent)
        self._all_parents = None  # 清空缓存

    def _check_cycle(self, new_parent: 'Role') -> bool:
        """使用DFS检测循环依赖"""
        visited = set()
        stack = [new_parent]
        while stack:
            current = stack.pop()
            if current == self:
                return True  # 发现循环
            if current not in visited:
                visited.add(current)
                stack.extend(current.parents)
        return False

    def get_all_parents(self) -> List['Role']:
        """获取所有父角色（按拓扑排序）"""
        if self._all_parents is not None:
            return self._all_parents
        
        visited = set()
        result = []
        # 使用深度优先搜索遍历父角色
        def dfs(role: 'Role') -> None:
            if role in visited:
                return
            visited.add(role)
            for parent in role.parents:
                result.append(parent)
                dfs(parent)
        
        dfs(self)
        # 去重并保留顺序
        seen = set()
        self._all_parents = [x for x in result if not (x in seen or seen.add(x))]
        return self._all_parents
