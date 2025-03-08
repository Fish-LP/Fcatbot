# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-03-07 23:51:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-08 16:03:56
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
import curses
import time
from typing import Dict, List, Optional, Set, Tuple, Callable, Any

# ----------------------
# 全局配置常量
# ----------------------

THEMES = {
    'config':{
        'border': True,
    },
    '深海': {
        'title': (curses.COLOR_CYAN, curses.COLOR_BLACK),
        'menu': (curses.COLOR_WHITE, curses.COLOR_BLUE),
        'content': (curses.COLOR_WHITE, curses.COLOR_BLACK),
        'status': (curses.COLOR_BLACK, curses.COLOR_WHITE),
        'error': (curses.COLOR_WHITE, curses.COLOR_RED)
    },
    '极光': {
        'title': (curses.COLOR_GREEN, curses.COLOR_BLACK),
        'menu': (curses.COLOR_BLACK, curses.COLOR_CYAN),
        'content': (curses.COLOR_YELLOW, curses.COLOR_BLACK),
        'status': (curses.COLOR_WHITE, curses.COLOR_BLUE),
        'error': (curses.COLOR_RED, curses.COLOR_WHITE)
    }
}
"""可用主题配置字典
结构:
{
    主题名称: {
        元素名称: (前景色, 背景色),
        ...
    },
    ...
}
支持的元素: title, menu, content, status, error
"""

ICONS = {
    'installed': '✅',
    'error': '❌',
    'warning': '⚠️',
    'progress': '⏳',
    'radio': '◉',
    'checkbox': '◻'
}
"""状态图标配置字典
用于在不同状态下显示对应的Unicode符号图标
"""


# ----------------------
# UI引擎核心类
# ----------------------

class TerminalUI:
    """终端用户界面管理核心类
    
    职责: 
    - 界面布局管理
    - 颜色主题管理
    - 输入事件处理
    - 多窗口协调刷新

    属性:
        stdscr (curses.window): 主窗口对象
        theme (str): 当前主题名称
        selected_idx (int): 当前选中的菜单索引
        running (bool): 主循环运行标志
        focus (str): 当前焦点区域 ('menu' 或 'content')
        menu_items (List[Dict]): 菜单项配置列表
        content_state (Dict): 内容区域状态管理字典

    方法列表参见各方法文档注释
    """

    def __init__(self, stdscr: curses.window):
        """初始化UI框架
        
        Args:
            stdscr: curses标准窗口对象，由curses.wrapper传入
        """
        self.stdscr = stdscr
        self.theme = '深海'
        self._init_colors()
        self._create_windows()

        # 状态管理
        self.selected_idx = 0          # 当前选中菜单项索引
        self.running = True            # 主循环运行标志
        self.focus = 'menu'            # 当前焦点区域
        self.menu_items = []           # 菜单项配置列表
        
        # 内容区域状态
        self.content_state = {
            'scroll': 0,               # 滚动偏移量
            'selected': 0,             # 选中项索引
            'selections': set(),       # 多选模式下的选中集合
            'expanded_nodes': set()    # 树状结构展开的节点ID集合
        }

    def _init_colors(self) -> None:
        """初始化颜色对配置
        
        根据THEMES配置创建对应的颜色对，每个主题的颜色对ID范围: 
        主题索引*10 + 颜色元素索引
        """
        curses.start_color()
        curses.use_default_colors()
        for theme_idx, (theme_name, colors) in enumerate(THEMES.items()):
            if theme_name == 'config': continue
            for color_idx, (name, (fg, bg)) in enumerate(colors.items(), 1):
                pair_id = theme_idx * 10 + color_idx
                curses.init_pair(pair_id, fg, bg)

    def _create_windows(self) -> None:
        """创建并初始化各子窗口
        
        窗口布局: 
        +---------------------------------+
        | Title                           |
        +--------+-------------+----------+
        | Menu   | Content     | help     |
        |        |             |          |
        +--------+-------------+----------+
        | Status                          |
        +---------------------------------+
        """
        rows, cols = self.stdscr.getmaxyx()
        # 调整窗口尺寸计算，确保边框可见
        self.title_win = self.stdscr.subwin(3, cols-1, 0, 1)
        self.menu_win = self.stdscr.subwin(rows-6, 24, 2, 1)
        self.content_win = self.stdscr.subwin(rows-6, cols-44, 2, 25)
        self.sidebar_win = self.stdscr.subwin(rows-6, 18, 2, cols-19)
        self.status_win = self.stdscr.subwin(3, cols-2, rows-4, 1)

        # 初始化边框
        for win in [self.menu_win, self.content_win, self.sidebar_win]:
            win.border()

    def set_theme(self, theme_name: str) -> None:
        """切换当前主题
        
        Args:
            theme_name: 主题名称，必须存在于THEMES中
            
        Raises:
            ValueError: 当主题名称无效时
        """
        if theme_name not in THEMES:
            raise ValueError(f"无效主题: {theme_name}。可用主题: {list(THEMES.keys())}")
        self.theme = theme_name
        self.refresh_all()

    def get_theme(self, element: str) -> int:
        """获取指定元素的属性
        
        Args:
            element: 界面元素名称 (title/menu/content/status/error)
            
        Returns:
            curses.color_pair生成的颜色属性值
        """
        if element in THEMES['config']: return THEMES['config'][element]
        theme_idx = list(THEMES.keys()).index(self.theme)
        color_idx = list(THEMES[self.theme].keys()).index(element) + 1
        return curses.color_pair(theme_idx * 10 + color_idx)

    def refresh_all(self) -> None:
        """完全刷新所有界面元素"""
        self._create_windows()
        self.stdscr.erase()
        self.draw_title()
        self.draw_menu()
        self.draw_content()
        self.draw_sidebar()
        self.draw_status()
        if self.get_theme("border"):
            self._draw_borders()
        self.stdscr.refresh()

    def show_message(self, message: str, msg_type: str = 'info') -> None:
        """在状态栏显示临时消息
        
        Args:
            message: 要显示的消息文本
            msg_type: 消息类型 (info/error)，影响显示颜色
        """
        color = self.get_theme('error' if msg_type == 'error' else 'status')
        self.status_win.bkgd(' ', color)
        self.status_win.addstr(1, 2, message)
        self.status_win.refresh()
        time.sleep(2 if msg_type == 'error' else 1)

    def _draw_borders(self) -> None:
        """绘制所有窗口边框"""
        self.stdscr.border()
        for win in [self.menu_win, self.content_win, self.sidebar_win]:
            win.border()

    def draw_title(self, text: str = "") -> None:
        """绘制标题栏
        
        Args:
            text: 标题文本，为空时使用默认标题
        """
        self.title_win.erase()
        color = self.get_theme('title')
        self.title_win.bkgd(' ', color)
        title = text or "终端UI框架 1.2"
        self.title_win.addstr(1, 2, title, color | curses.A_BOLD)
        self.title_win.refresh()

    def draw_content(self) -> None:
        """绘制内容区域，根据内容类型自动分派渲染方法"""
        self.content_win.erase()
        color = self.get_theme('content')
        self.content_win.bkgd(' ', color)
        
        if not self.menu_items:
            return
            
        current_item = self.menu_items[self.selected_idx]
        content_type = current_item.get('content_type', 'list')
        
        # 根据内容类型调用不同渲染方法
        render_methods = {
            'list': self._draw_list_content,
            'tree': self._draw_tree_content,
            'radio': self._draw_radio_list,
            'checkbox': self._draw_checkbox_list
        }
        
        if content_type in render_methods:
            render_methods[content_type](current_item['content'])
        else:
            self._draw_list_content(current_item.get('content', []))

        self._draw_scrollbar()
        self.content_win.refresh()

    def _draw_list_content(self, items: List[str]) -> None:
        """渲染普通列表内容
        
        Args:
            items: 要显示的字符串列表
        """
        max_lines = self.content_win.getmaxyx()[0] - 2
        start_idx = self.content_state['scroll']
        
        for i in range(max_lines):
            idx = start_idx + i
            if idx >= len(items):
                break
                
            text = items[idx]
            attr = self.get_theme('content')
            if idx == self.content_state['selected'] and self.focus == 'content':
                attr |= curses.A_REVERSE
                
            try:
                self.content_win.addstr(i+1, 2, text[:self.content_win.getmaxyx()[1]-4], attr)
            except curses.error:
                pass

    def _draw_tree_content(self, nodes: List[Dict]) -> None:
        """渲染树状结构内容
        
        Args:
            nodes: 树节点列表，每个节点需包含: 
                - id: 唯一标识符
                - name: 显示名称
                - children (可选): 子节点列表
        """
        self.flat_tree = []  # 存储扁平化的可见节点
        expanded = self.content_state['expanded_nodes']

        def _flatten_nodes(nodes: List[Dict], level: int = 0, parent_prefix: str = "") -> None:
            """递归展开树节点"""
            for i, node in enumerate(nodes):
                is_last = i == len(nodes)-1
                prefix = "└─ " if is_last else "├─ "
                tree_prefix = parent_prefix + ("    " if level > 0 else "")
                
                self.flat_tree.append({
                    'node': node,
                    'level': level,
                    'prefix': tree_prefix + prefix
                })
                
                if node.get('children') and node['id'] in expanded:
                    _flatten_nodes(node['children'], level+1, parent_prefix + "   ") # ("   " if is_last else "│  "))

        _flatten_nodes(nodes)
        
        max_lines = self.content_win.getmaxyx()[0] - 2
        start_idx = self.content_state['scroll']
        
        for i in range(max_lines):
            idx = start_idx + i
            if idx >= len(self.flat_tree):
                break
                
            item = self.flat_tree[idx]
            node = item['node']
            line = f"{item['prefix']}{node['name']}"
            
            # 添加展开/折叠符号
            if node.get('children'):
                symbol = '▼' if node['id'] in expanded else '▶'
                line = f"{item['prefix'][:-3]}{symbol} {node['name']}"
            
            attr = self.get_theme('content')
            if idx == self.content_state['selected'] and self.focus == 'content':
                attr |= curses.A_REVERSE
                
            try:
                self.content_win.addstr(i+1, 2, line[:self.content_win.getmaxyx()[1]-4], attr)
            except curses.error:
                pass

    def _draw_radio_list(self, items: List[str]) -> None:
        """渲染单选列表"""
        max_lines = self.content_win.getmaxyx()[0] - 2
        start_idx = self.content_state['scroll']
        selected = self.content_state['selections']
        
        for i in range(max_lines):
            idx = start_idx + i
            if idx >= len(items):
                break
                
            symbol = ICONS['radio'] if idx in selected else '○'
            text = f"{symbol} {items[idx]}"
            attr = self.get_theme('content')
            if idx == self.content_state['selected'] and self.focus == 'content':
                attr |= curses.A_REVERSE
                
            self.content_win.addstr(i+1, 2, text[:self.content_win.getmaxyx()[1]-4], attr)

    def _draw_checkbox_list(self, items: List[str]) -> None:
        """渲染复选框列表"""
        max_lines = self.content_win.getmaxyx()[0] - 2
        start_idx = self.content_state['scroll']
        selected = self.content_state['selections']
        
        for i in range(max_lines):
            idx = start_idx + i
            if idx >= len(items):
                break
                
            symbol = ICONS['checkbox'].replace('◻', '◼') if idx in selected else ICONS['checkbox']
            text = f"{symbol} {items[idx]}"
            attr = self.get_theme('content')
            if idx == self.content_state['selected'] and self.focus == 'content':
                attr |= curses.A_REVERSE
                
            self.content_win.addstr(i+1, 2, text[:self.content_win.getmaxyx()[1]-4], attr)

    def draw_menu(self) -> None:
        """绘制菜单区域"""
        self.menu_win.erase()
        color = self.get_theme('menu')
        self.menu_win.bkgd(' ', color)
        
        if not self.menu_items:
            return
            
        max_lines = self.menu_win.getmaxyx()[0] - 2
        start_idx = max(0, self.selected_idx - max_lines + 2)
        
        for i in range(max_lines):
            idx = start_idx + i
            if idx >= len(self.menu_items):
                break
                
            item = self.menu_items[idx]
            text = f"{'➤' if idx == self.selected_idx else ' '} {item['label']}"
            attr = color
            if idx == self.selected_idx and self.focus == 'menu':
                attr |= curses.A_REVERSE
                
            self.menu_win.addstr(i+1, 2, text[:20], attr)
            
        self.menu_win.refresh()

    def draw_sidebar(self) -> None:
        """绘制侧边栏帮助信息"""
        self.sidebar_win.erase()
        color = self.get_theme('menu')
        self.sidebar_win.bkgd(' ', color)
        
        if not self.menu_items:
            return
            
        current_item = self.menu_items[self.selected_idx]
        help_text = current_item.get('help', '')
        max_lines = self.sidebar_win.getmaxyx()[0]-2
        
        for i, line in enumerate(help_text.split('\n')[:max_lines]):
            try:
                self.sidebar_win.addstr(i+1, 2, line[:16], color)
            except curses.error:
                pass
        self.sidebar_win.refresh()

    def draw_status(self, message: str = "") -> None:
        """绘制状态栏
        
        Args:
            message: 状态信息文本
        """
        self.status_win.erase()
        color = self.get_theme('status')
        self.status_win.bkgd(' ', color)
        self.status_win.addstr(1, 2, f"{ICONS['progress']} {message}")
        self.status_win.refresh()

    def _draw_scrollbar(self) -> None:
        """绘制内容区域滚动条"""
        current_item = self.menu_items[self.selected_idx]
        content = current_item.get('content', [])
        max_lines = self.content_win.getmaxyx()[0]-2
        total = len(content)
        
        if total <= max_lines:
            return
            
        height = self.content_win.getmaxyx()[0]-2
        thumb = max(1, int(height * (max_lines / total)))
        pos = int((self.content_state['scroll'] / total) * (height - thumb))
        
        for y in range(pos, pos + thumb):
            self.content_win.chgat(y+1, self.content_win.getmaxyx()[1]-3, 1, curses.A_REVERSE)

    def handle_input(self) -> None:
        """处理键盘输入事件"""
        key = self.stdscr.getch()
        
        if key == ord('q'):
            self.running = False
        elif key == ord('t'):
            self._switch_theme()
        elif self.focus == 'menu':
            self._handle_menu_input(key)
        elif self.focus == 'content':
            self._handle_content_input(key)

    def _switch_theme(self) -> None:
        """切换主题功能"""
        themes = list(THEMES.keys())
        new_theme = themes[(themes.index(self.theme)+1) % len(themes)]
        self.set_theme(new_theme)

    def _handle_menu_input(self, key: int) -> None:
        """处理菜单区域的键盘事件
        
        Args:
            key: 输入的键值
        """
        if key == curses.KEY_UP:
            self.selected_idx = max(0, self.selected_idx-1)
            self._reset_content_state()
        elif key == curses.KEY_DOWN:
            if self.selected_idx < len(self.menu_items)-1:
                self.selected_idx += 1
                self._reset_content_state()
        elif key == 10:  # Enter键
            self.focus = 'content'
            self._reset_content_state()
            # 执行菜单项回调
            if self.menu_items[self.selected_idx].get('callback'):
                self.menu_items[self.selected_idx]['callback'](self)

    def _handle_content_input(self, key: int) -> None:
        """处理内容区域的键盘事件
        
        Args:
            key: 输入的键值
        """
        current_item = self.menu_items[self.selected_idx]
        content_type = current_item.get('content_type', 'list')
        
        # 通用导航处理
        if key == curses.KEY_UP:
            self.content_state['selected'] = max(0, self.content_state['selected']-1)
            self._adjust_scroll()
        elif key == curses.KEY_DOWN:
            max_items = len(self.flat_tree) if content_type == 'tree' else len(current_item.get('content', []))
            if self.content_state['selected'] < max_items-1:
                self.content_state['selected'] += 1
                self._adjust_scroll()
                
        # 树状结构特定处理
        if content_type == 'tree':
            if key == ord(' '):  # 展开/折叠
                self._toggle_tree_node()
            elif key == 10:  # Enter键回调
                self._trigger_tree_action()

    def _toggle_tree_node(self) -> None:
        """切换树节点的展开/折叠状态"""
        if self.flat_tree:
            node = self.flat_tree[self.content_state['selected']]['node']
            if node['id'] in self.content_state['expanded_nodes']:
                self.content_state['expanded_nodes'].remove(node['id'])
            else:
                if node.get('children'):
                    self.content_state['expanded_nodes'].add(node['id'])
            # 重置滚动和选择状态
            self.content_state['selected'] = min(self.content_state['selected'], len(self.flat_tree)-1)

    def _trigger_tree_action(self) -> None:
        """触发树节点的动作回调"""
        current_item = self.menu_items[self.selected_idx]
        if self.flat_tree and current_item.get('action'):
            selected_node = self.flat_tree[self.content_state['selected']]['node']
            current_item['action'](self, selected_node)

    def _adjust_scroll(self) -> None:
        """调整内容滚动位置"""
        max_visible = self.content_win.getmaxyx()[0]-2
        if self.content_state['selected'] < self.content_state['scroll']:
            self.content_state['scroll'] = self.content_state['selected']
        elif self.content_state['selected'] >= self.content_state['scroll'] + max_visible:
            self.content_state['scroll'] = self.content_state['selected'] - max_visible + 1

    def _reset_content_state(self) -> None:
        """重置内容区域状态"""
        self.content_state = {
            'scroll': 0,
            'selected': 0,
            'selections': set(),
            'expanded_nodes': set()
        }


# ----------------------
# 主程序入口
# ----------------------

def main(stdscr: curses.window) -> None:
    """主程序入口函数
    
    Args:
        stdscr: curses标准窗口对象
    """
    ui = TerminalUI(stdscr)
    curses.curs_set(0)  # 隐藏光标
    
    # 示例树状数据结构
    sample_tree = [
        {
            'id': 1,
            'name': '根节点',
            'children': [
                {'id': 2, 'name': '文档', 'children': [
                    {'id': 4, 'name': '报告.pdf'},
                    {'id': 5, 'name': '笔记'}
                ]},
                {'id': 3, 'name': '图片', 'children': [
                    {'id': 6, 'name': '照片1.jpg'},
                    {'id': 7, 'name': '截图.png'}
                ]}
            ]
        }
    ]

    def tree_node_action(ui: TerminalUI, node: Dict) -> None:
        """树节点点击回调示例"""
        ui.show_message(f"选中节点: {node['name']} (ID: {node['id']})")

    # 配置菜单项
    ui.menu_items = [
        {
            'label': '🌳 文件树',
            'content_type': 'tree',
            'content': sample_tree,
            'help': "空格:展开/折叠\nEnter:选择节点",
            'action': tree_node_action
        },
        # 可扩展更多菜单项...
    ]
    
    # 主循环
    while ui.running:
        ui.refresh_all()
        ui.handle_input()

if __name__ == "__main__":
    curses.wrapper(main)