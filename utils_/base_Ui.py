# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-03-08 18:38:31
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-10 21:40:32
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from typing import Dict, List, Optional, Callable, Any
from .Ui_engine import TerminalUI
import curses

class BaseUI(TerminalUI):
    """UI引擎基础封装类
    
    提供常用高级功能封装,简化应用开发
    """
    
    def __init__(self, stdscr: curses.window):
        super().__init__(stdscr)
        self.handlers: Dict[str, Callable] = {}
        self.data_providers: Dict[str, Callable] = {}

    def add_menu(self, label: str, content_type: str = 'list',
                data_provider: Optional[Callable] = None,
                action: Optional[Callable] = None,
                help_text: str = "") -> None:
        """添加菜单项
        
        Args:
            label: 菜单显示文本
            content_type: 内容类型(list/tree/radio/checkbox)
            data_provider: 数据提供函数
            action: 动作处理函数
            help_text: 帮助提示文本
            editable: 是否可编辑
            on_edit: 编辑回调函数(idx, new_value)
        """
        menu_id = f"menu_{len(self.menu_items)}"
        if data_provider:
            self.data_providers[menu_id] = data_provider
            
        self.menu_items.append({
            'id': menu_id,
            'label': label,
            'content_type': content_type,
            'content': data_provider() if data_provider else [],
            'action': action,
            'help': help_text,
        })
        return menu_id

    def confirm(self, message: str, callback: Callable[[bool], None]) -> None:
        """显示确认对话框
        
        Args:
            message: 确认提示文本
            callback: 确认结果回调
        """
        def handle_confirm(value: str) -> None:
            callback(value.lower() in ('y', 'yes'))
            
        self.prompt_input(
            f"{message} (y/n)", 
            handle_confirm,
            lambda x: x.lower() in ('y', 'yes', 'n', 'no')
        )

    def select_option(self, title: str, options: List[str], 
                     callback: Callable[[int, str], None]) -> None:
        """显示单选对话框
        
        Args:
            title: 选择标题
            options: 选项列表
            callback: 选择结果回调
        """
        temp_menu = {
            'label': title,
            'content_type': 'radio',
            'content': options,
            'action': lambda _, idx: callback(idx, options[idx])
        }
        self.menu_items.append(temp_menu)
        self.selected_idx = len(self.menu_items) - 1
        self.focus = 'content'

    def show_progress(self, total: int) -> 'ProgressBar':
        """创建进度条
        
        Args:
            total: 总进度值
        
        Returns:
            进度条控制器
        """
        return ProgressBar(self, total)

    def bind_key(self, key: str, handler: Callable[['BaseUI'], Any], menu_id: Optional[str] = None) -> None:
        """绑定快捷键处理函数
        
        Args:
            key: 键名(例如: 'a', 'F5')
            handler: 处理函数
            menu_id: 可选的菜单ID,指定后只在该菜单下生效
        """
        # 转换键名到键值
        key_value = ord(key) if len(key) == 1 else getattr(curses, f'KEY_{key}', None)
        if key_value is None:
            raise ValueError(f"无效的键名: {key}")
            
        self.register_key_handler(key_value, handler, menu_id)

    def unbind_key(self, key: str, menu_id: Optional[str] = None) -> None:
        """解除快捷键绑定
        
        Args:
            key: 键名
            menu_id: 可选的菜单ID
        """
        key_value = ord(key) if len(key) == 1 else getattr(curses, f'KEY_{key}', None)
        if key_value is not None:
            self.unregister_key_handler(key_value, menu_id)

    def refresh_menu(self, menu_id: str) -> None:
        """刷新指定菜单的数据
        
        Args:
            menu_id: 菜单ID
        """
        if menu_id in self.data_providers:
            for item in self.menu_items:
                if item.get('id') == menu_id:
                    item['content'] = self.data_providers[menu_id]()
                    break
        self.refresh_all()

    def set_content_editable(self, editable: bool) -> None:
        """设置当前内容是否可编辑
        
        Args:
            editable: 是否可编辑
        """
        if self.menu_items and self.selected_idx < len(self.menu_items):
            self.menu_items[self.selected_idx]['editable'] = editable
            self.content_state['editable'] = editable
            self.refresh_all()

    def on_item_edit(self, callback: Callable[[int, str], None]) -> None:
        """设置项目编辑回调
        
        Args:
            callback: 编辑回调函数(idx, new_value)
        """
        if self.menu_items and self.selected_idx < len(self.menu_items):
            self.menu_items[self.selected_idx]['on_edit'] = callback

class ProgressBar:
    """进度条控制器"""
    
    def __init__(self, ui: BaseUI, total: int):
        self.ui = ui
        self.total = total
        self.current = 0
        
    def update(self, current: Optional[int] = None, message: str = "") -> None:
        """更新进度
        
        Args:
            current: 当前进度值
            message: 进度消息
        """
        if current is not None:
            self.current = current
        else:
            self.current += 1
            
        percent = min(100, int(self.current * 100 / self.total))
        bar_width = 20
        filled = int(bar_width * percent / 100)
        bar = f"[{'=' * filled}{' ' * (bar_width-filled)}]"
        status = f"{bar} {percent}% {message}"
        self.ui.draw_status(status)
