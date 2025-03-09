# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 15:58:15
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-09 11:36:08
# @Description  : PyPI包管理器UI界面
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
import curses
from typing import List, Dict
from ..utils import BaseUI
from ..utils import PipTool

class PipUI(BaseUI):
    def __init__(self, stdscr: curses.window):
        super().__init__(stdscr)
        self.pip = PipTool()
        self.draw_title("PyPI包管理器")
        
        # 添加菜单项
        pkg_list = self.add_menu(
            "📦 已安装包列表",
            data_provider=self.load_packages,
            help_text="Enter:包信息\n快捷键\ni:安装包\nd:卸载包\nu:更新包"
        )
        
        deps_tree = self.add_menu(
            "🌳 依赖树",
            content_type='tree',
            data_provider=self.load_dep_tree,
            help_text="查看包依赖关系"
        )
        
        conflict_list = self.add_menu(
            "⚠️ 环境检查",
            data_provider=self.load_conflicts,
            help_text="检查包冲突"
        )
        
        # 绑定菜单快捷键
        self.bind_key('i', self.install_package, pkg_list)  # 安装新包
        self.bind_key('d', self.uninstall_package, pkg_list)  # 卸载包
        self.bind_key('u', self.upgrade_package, pkg_list)  # 更新包
        
    def load_packages(self) -> List[str]:
        """加载已安装包列表"""
        packages = self.pip.list_installed()
        if not packages:
            return ["未找到已安装的包"]
        return [f"{pkg['name']} ({pkg['version']})" for pkg in packages]

    def load_dep_tree(self) -> List[Dict]:
        """加载依赖树数据"""
        tree_data = self.pip.generate_dependency_tree()
        def convert_tree(items) -> List[Dict]:
            result = []
            for item in items:
                
                package_name = item.get('package_name', None) or item['package']['package_name']
                package_version = item.get('installed_version', None) or item['package']['installed_version']
                required_version = item.get('required_version')
                node = {
                    'id': package_name,
                    'name': f"{package_name} ({package_version})"
                    }
                if 'dependencies' in item:
                    node['children'] = convert_tree(item['dependencies'])

                result.append(node)
            return result
        return convert_tree(tree_data)

    def load_conflicts(self) -> List[str]:
        """加载环境冲突信息"""
        conflicts = self.pip.verify_environment()['conflicts']
        if not conflicts:
            return ["✅ 未发现包冲突"]
        return [
            f"❌ {c['package']}: 需要 {c['required']}, 当前 {c['installed']}"
            for c in conflicts
        ]

    def install_package(self, ui: BaseUI) -> None:
        """安装新包"""
        def handle_input(package: str) -> None:
            if package:
                progress = self.show_progress(3)
                progress.update(1, "正在安装...")
                result = self.pip.install(package)
                if result['status'] == 'success':
                    self.show_message(f"✅ 成功安装: {package}")
                    progress.update(3, "安装完成")
                    self.refresh_menu("menu_0")  # 刷新包列表
                    self.refresh_menu("menu_1")  # 刷新依赖树
                else:
                    self.show_message(f"❌ 安装失败: {result['error']}", 'error')
                    progress.update(3, "安装失败")
                    
        self.prompt_input("请输入要安装的包名", handle_input)

    def uninstall_package(self, ui: BaseUI) -> None:
        """卸载选中的包"""
        idx = self.content_state['selected']
        packages = self.pip.list_installed()
        if not packages or idx >= len(packages):
            return
            
        package = packages[idx]['name']
        
        def confirm_uninstall(confirmed: bool) -> None:
            if confirmed:
                result = self.pip.uninstall(package)
                if result['status'] == 'success':
                    self.show_message(f"✅ 已卸载: {package}")
                    self.refresh_menu("menu_0")
                    self.refresh_menu("menu_1")
                else:
                    self.show_message(f"❌ 卸载失败: {result['error']}", 'error')
                    
        self.confirm(f"确认卸载 {package}?", confirm_uninstall)

    def upgrade_package(self, ui: BaseUI) -> None:
        """更新选中的包"""
        idx = self.content_state['selected']
        packages = self.pip.list_installed()
        if not packages or idx >= len(packages):
            return
            
        package = packages[idx]['name']
        progress = self.show_progress(3)
        progress.update(1, "正在更新...")
        
        result = self.pip.install(package, upgrade=True)
        if result['status'] == 'success':
            self.show_message(f"✅ 已更新: {package}")
            progress.update(3, "更新完成")
            self.refresh_menu("menu_0")
            self.refresh_menu("menu_1")
        else:
            self.show_message(f"❌ 更新失败: {result['error']}", 'error')
            progress.update(3, "更新失败")

def main(stdscr: curses.window) -> None:
    ui = PipUI(stdscr)
    curses.curs_set(0)
    while ui.running:
        ui.refresh_all()
        ui.handle_input()

if __name__ == "__main__":
    curses.wrapper(main)
