# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 15:58:15
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-15 17:56:13
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from Fcatbot.utils import TestSuite
from Fcatbot.RBACManager import RBACManager,PermissionPath,Trie
from Fcatbot import Color


# 创建测试套件实例
suite = TestSuite()
debug = True
# 测试 PermissionPath 类
def test_permission_path_initialization():
    # 不同初始化方式
    pp1 = PermissionPath("a.b.c")
    pp2 = PermissionPath(["a", "b", "c"])
    pp3 = PermissionPath(("a", "b", "c"))
    pp4 = PermissionPath(pp1)
    return pp1 == pp2 == pp3 == pp4 and pp1.path == ('a', 'b', 'c')

suite.add_test(
    description="PermissionPath 初始化测试",
    actual=test_permission_path_initialization,
    expected=True
)

# 测试路径匹配逻辑
pp_wildcard = PermissionPath("a.*.c")
suite.add_test(
    description="通配符 * 匹配测试",
    actual=lambda: pp_wildcard.matching_path("a.b.c"),
    expected=True
)

suite.add_test(
    description="通配符 ** 匹配测试",
    actual=lambda: PermissionPath("a.**").matching_path("a.b.c.d"),
    expected=True
)

suite.add_test(
    description="不同层级路径不匹配测试",
    actual=lambda: PermissionPath("a.*").matching_path("a.b.c"),
    expected=False
)

# 测试 Trie 类
def test_trie_add_check():
    trie = Trie(case_sensitive=True)
    trie.add_path("a.b.c")
    return trie.check_path("a.b.c", complete=True)

suite.add_test(
    description="Trie 添加并检查路径",
    actual=test_trie_add_check,
    expected=True
)

def test_trie_delete_wildcard():
    trie = Trie(case_sensitive=True)
    trie.add_path("a.b.c")
    trie.add_path("a.d.c")
    trie.del_path("a.*.c")  # 删除所有 a.任意单个节点.c
    return trie.check_path("a.b.c")  # 应返回 False

suite.add_test(
    description="Trie 删除通配符路径",
    actual=test_trie_delete_wildcard,
    expected=False
)

# 测试 RBACManager 类
def test_rbac_default_role():
    rbac = RBACManager(default_role="guest")
    rbac.add_user("test_user")
    return "guest" in rbac.users["test_user"]["role_list"]

suite.add_test(
    description="RBAC 默认角色分配测试",
    actual=test_rbac_default_role,
    expected=True
)

def test_rbac_blacklist_priority():
    rbac = RBACManager()
    rbac.add_user("user1")
    rbac.add_permissions("service.write")
    rbac.assign_permissions_to_user("user1", "service.*", mode="white")
    rbac.assign_permissions_to_user("user1", "service.write", mode="black")
    return rbac.check_permission("user1", "service.write")

suite.add_test(
    description="RBAC 黑名单优先级测试",
    actual=test_rbac_blacklist_priority,
    expected=False  # 黑名单应覆盖白名单
)

def test_rbac_wildcard_permission():
    rbac = RBACManager()
    rbac.add_user("user2")
    rbac.add_permissions("service.read")
    rbac.add_permissions("service.write")
    rbac.assign_permissions_to_user("user2", "service.*", mode="white")
    return all([
        rbac.check_permission("user2", "service.read"),
        rbac.check_permission("user2", "service.write")
    ])

suite.add_test(
    description="RBAC 通配符权限测试",
    actual=test_rbac_wildcard_permission,
    expected=True
)

# 测试大小写敏感性
def test_case_insensitive():
    RBACManager.case_sensitive = False # 需要手动修改
    rbac = RBACManager(case_sensitive=False)
    rbac.case_sensitive = False
    rbac.add_permissions("Service.Write")
    return rbac.check_availability(permissions_path="service.write")

suite.add_test(
    description="RBAC 大小写不敏感测试",
    actual=test_case_insensitive,
    expected=True
)

# 测试角色继承功能
def test_role_inheritance():
    rbac = RBACManager()
    rbac.add_role("parent")
    rbac.add_role("child")
    rbac.add_user("test_user")
    rbac.set_role_inheritance("child", "parent")
    
    rbac.add_permissions("system.admin")
    rbac.assign_permissions_to_role("parent", "system.*", mode="white")
    rbac.assign_role_to_user("child", "test_user")
    
    return rbac.check_permission("test_user", "system.admin")

suite.add_test(
    description="角色继承权限测试",
    actual=test_role_inheritance,
    expected=True
)

# 测试循环继承检测
def test_circular_inheritance():
    rbac = RBACManager()
    rbac.add_role("roleA")
    rbac.add_role("roleB")
    rbac.set_role_inheritance("roleA", "roleB")
    try:
        rbac.set_role_inheritance("roleB", "roleA")  # 应触发循环检测
        return False
    except ValueError:
        return True

suite.add_test(
    description="循环继承检测测试",
    actual=test_circular_inheritance,
    expected=True
)

# 测试缓存刷新机制
def test_cache_refresh():
    rbac = RBACManager()
    rbac.add_user("cache_user")
    rbac.add_permissions("cache.test")
    rbac.assign_permissions_to_user("cache_user", "cache.*", mode="white")
    
    # 首次检查应通过
    result1 = rbac.check_permission("cache_user", "cache.test")
    
    # 删除权限路径后刷新缓存
    rbac.del_permissions("cache.test")
    result2 = rbac.check_permission("cache_user", "cache.test")
    
    return result1, result2

suite.add_test(
    description="权限缓存刷新测试",
    actual=test_cache_refresh,
    expected=(True, False)
)

# 测试黑白名单交叉场景
def test_complex_permission_scenario():
    rbac = RBACManager()
    rbac.add_user("complex_user")
    rbac.add_permissions("api.read")
    rbac.add_permissions("api.write")
    
    # 白名单开放整个api，黑名单禁用write
    rbac.assign_permissions_to_user("complex_user", "api.*", mode="white")
    rbac.assign_permissions_to_user("complex_user", "api.write", mode="black")
    
    return all([
        rbac.check_permission("complex_user", "api.read"),
        not rbac.check_permission("complex_user", "api.write")
    ])

suite.add_test(
    description="复杂黑白名单交叉测试",
    actual=test_complex_permission_scenario,
    expected=True
)

# 测试无效路径处理
def test_invalid_path_handling():
    rbac = RBACManager()
    rbac.add_user("invalid_user")
    try:
        rbac.assign_permissions_to_user("invalid_user", "not.exist.path", mode="white")
        return False
    except ValueError:
        return True

suite.add_test(
    description="无效权限路径分配测试",
    actual=test_invalid_path_handling,
    expected=True
)

# 测试最大删除模式
def test_max_delete_mode():
    trie = Trie()
    trie.add_path("a.b.c")
    trie.add_path("a.b.d")
    trie.del_path("a.b.*")  # 应删除b节点下的所有子节点
    return not trie.check_path("a.b")  # b节点应该被删除

suite.add_test(
    description="Trie最大删除模式测试",
    actual=test_max_delete_mode,
    expected=True
)

# 测试多通配符路径
def test_multi_wildcard_matching():
    pp = PermissionPath("*.sub.*.end")
    return (
        pp.matching_path("a.sub.b.end"),
        pp.matching_path("any.sub.value.end"),
        pp.matching_path("wrong.sub.end"),
        not pp.matching_path("all.edit")
    )

suite.add_test(
    description="多通配符路径匹配测试",
    actual=test_multi_wildcard_matching,
    expected=(True, True, True, True)
)

# 运行测试套件
suite.run()