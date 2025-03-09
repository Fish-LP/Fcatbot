from Fcatbot.utils import TestSuite, Color
from Fcatbot.RBACManager import RBACManager
import time


rbac = RBACManager()

# 创建角色
rbac.create_role("admin")
rbac.create_role("editor")
rbac.create_role("viewer")
rbac.create_role("test_role")
rbac.create_role("roleA")
rbac.create_role("roleB")
rbac.create_role("roleC")
rbac.create_role("roleD")

# 设置继承关系
rbac.add_role_parent("editor", "viewer")
rbac.add_role_parent("admin", "editor")
rbac.add_role_parent("roleA", "roleB")
rbac.add_role_parent("roleB", "roleC")
rbac.add_role_parent("roleC", "roleD")
rbac.add_role_parent("roleD", "viewer")  # roleD继承viewer的权限

# 分配权限
rbac.assign_permission("viewer", "article.read")
rbac.assign_permission("editor", "article.edit")
rbac.assign_permission("admin", "user.*")
rbac.assign_permission("admin", "system.**")
rbac.assign_permission("test_role", "folder.*.file.read")
try: rbac.assign_permission("test_role", "mix.*.**.test")
except ValueError: pass
rbac.assign_permission("test_role", "wildcard.*")
rbac.assign_permission("roleD", "base.permission")

# 创建用户并分配角色
rbac.create_user("alice")
rbac.assign_role_to_user("alice", "admin")
rbac.create_user("bob")
rbac.assign_role_to_user("bob", "roleA")
rbac.assign_role_to_user("bob", "test_role")
rbac.assign_role_to_user("bob", "viewer")  # Bob拥有多个角色

# 初始化测试套件
test_suite = TestSuite()

# 可视化权限树
time.sleep(0.5)
print(f"\n{Color.YELLOW}Admin 权限树:")
print(rbac.roles["admin"].permissions.visualize())
time.sleep(0.5)
print(f"\n{Color.YELLOW}Editor 权限树:")
print(rbac.roles["editor"].permissions.visualize())
time.sleep(0.5)
print(f"\n{Color.YELLOW}Viewer 权限树:")
print(rbac.roles["viewer"].permissions.visualize())

# 测试用户权限
# Alice 的权限测试
alice_has_permission = lambda path: rbac.users["alice"].has_permission(path)
test_suite.add_test("Alice 是否有 article.read 权限", alice_has_permission("article.read"), True)
test_suite.add_test("Alice 是否有 article.edit 权限", alice_has_permission("article.edit"), True)
test_suite.add_test("Alice 是否有 user.create 权限", alice_has_permission("user.create"), True)
test_suite.add_test("Alice 是否有 system.log.view 权限", alice_has_permission("system.log.view"), True)
test_suite.add_test("Alice 是否有 user.log.edit 权限", alice_has_permission("user.log.edit"), False)
test_suite.add_test("Alice 是否有 base.permission 权限", alice_has_permission("base.permission"), False)

# Bob 的权限测试
bob_has_permission = lambda path: rbac.users["bob"].has_permission(path)
test_suite.add_test("Bob 是否有 base.permission 权限", bob_has_permission("base.permission"), True)
test_suite.add_test("Bob 是否有 folder.subfolder.file.read 权限", bob_has_permission("folder.subfolder.file.read"), True)
test_suite.add_test("Bob 是否有 folder.subfolder.subsubfolder.file.edit 权限", bob_has_permission("folder.subfolder.subsubfolder.file.edit"), False)
test_suite.add_test("Bob 是否有 mix.level.one.test 权限", bob_has_permission("mix.level.one.test"), False)
test_suite.add_test("Bob 是否有 mix.level.one.two.three.test 权限", bob_has_permission("mix.level.one.two.three.test"), False)
test_suite.add_test("Bob 是否有 wildcard.here 权限", bob_has_permission("wildcard.here"), True)
test_suite.add_test("Bob 是否有 wildcard 权限", bob_has_permission("wildcard"), False)
test_suite.add_test("Bob 是否有 test.wildcard.end 权限", bob_has_permission("test.wildcard.end"), False)
test_suite.add_test("Bob 是否有 article.read 权限", bob_has_permission("article.read"), True)
test_suite.add_test("Bob 是否有 article.edit 权限", bob_has_permission("article.edit"), False)

# 通配符测试
rbac.assign_permission("test_role", "*.*.end")  # 分配 *.*.end 权限
test_suite.add_test("Bob 是否有 test.test.end 权限（单级通配符）", bob_has_permission("test.test.end"), True)
test_suite.add_test("Bob 是否有 test.test.test.end 权限（多级路径）", bob_has_permission("test.test.test.end"), False)

# 角色继承测试
try:
    rbac.add_role_parent("roleD", "roleA")  # 导致循环依赖
    test_suite.add_test("角色继承循环检测（roleA -> roleD）", False, True)
except ValueError as e:
    test_suite.add_test("角色继承循环检测（roleA -> roleD）", True, True)  # 成功检测到循环

# 权限撤销测试
rbac.assign_permission("test_role", "test.delete")
test_suite.add_test("Bob 是否有 test.delete 权限（授权后）", bob_has_permission("test.delete"), True)
rbac.roles["test_role"].permissions.remove_permission("test.delete", "test_role")
test_suite.add_test("Bob 是否有 test.delete 权限（撤销后）", bob_has_permission("test.delete"), False)

# 多角色测试
rbac.assign_role_to_user("bob", "editor")  # Bob获得editor角色
test_suite.add_test("Bob 是否有 article.edit 权限（分配editor角色后）", bob_has_permission("article.edit"), True)

# 运行测试套件
test_suite.run()