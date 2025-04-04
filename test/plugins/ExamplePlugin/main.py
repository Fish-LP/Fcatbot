# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 18:46:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-04-04 15:53:35
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from Fcatbot import BasePlugin, Event, CompatibleEnrollment, get_log
from Fcatbot.utils import visualize_tree
import os

LOG = get_log('ExamplePlugin')
bot = CompatibleEnrollment

class ExamplePlugin(BasePlugin):
    name = "example_plugin"
    version = "1.0.0"
    dependencies = {}
    save_type = 'yaml'

    def _init_(self):
        """插件加载时调用"""
        print('=' * 50)
        print('【插件启动】正在初始化...')
        print('=' * 50)
        
        print("\n📦 基础信息:")
        print(f"├─ 插件名称: {self.name}")
        print(f"├─ 当前版本: {self.version}")
        print(f"├─ 加载状态: {'🆕 首次加载' if self.first_load else '♻️ 重新加载'}")
        print(f"├─ 数据格式: {self.save_type}")
        print(f"└─ 依赖组件: {self.dependencies or '无'}")
        
        print("\n📂 路径配置:")
        print(f"├─ 插件根目录: {self.self_path}")
        print(f"├─ 主程序文件: {self.this_file_path}")
        print(f"├─ 数据存储区: {self._data_path}")
        print(f"└─ 当前工作区: {os.getcwd()}")
        
        print("\n💾 数据状态:")
        print(f"├─ 插件元数据: {self.meta_data}")
        self.data['a'] = self.data.get('a', 0) + 1
        print(f"├─ 计数器值: {self.data['a']}")
        print(f"└─ 完整数据: {self.data}")

        with self.work_space:
            print(f"\n🔧 工作空间已切换到: {os.getcwd()}")
        
        # print("\n📝 可用方法列表:")
        # methods = [m for m in dir(self) if not m.startswith('__')]
        # print('\n'.join(visualize_tree(methods)))
        
        self.register_handlers()
        print('\n✅ 插件初始化完成\n' + '=' * 50)

    def _close_(self):
        """插件卸载时调用"""
        print('=' * 50)
        print(f'[{self.name}]正在卸载...')
        print(f"├─ 最终数据状态: {self.data}")
        print(f"└─ 插件 {self.name} 已安全卸载")
        print('=' * 50)

    def process_event(self, event: Event):
        """处理事件的方法"""
        print(f"📨 收到新事件: {event}")
        event.add_result("你好，这是来自示例插件的回复")
        handler_status = self.unregister_handler(self.id1)
        print(f"🔄 事件处理器状态: {'已注销' if handler_status else '注销失败'}")

    def register_handlers(self):
        """注册事件处理器"""
        self.id1 = self.register_handler("re:.*", self.process_event)
        print(f"📥 注册事件处理器: {self.id1}")

# @bot.group_event(row_event=True)
# def process_event(event: Event):
#     """处理事件的方法"""
#     print(event)
#     event.add_result("Hello, this is a response from ExamplePlugin")