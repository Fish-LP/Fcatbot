# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 18:46:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-19 22:02:38
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from Fcatbot import BasePlugin, Event, CompatibleEnrollment, get_log
import os

LOG = get_log('ExamplePlugin')
bot = CompatibleEnrollment

class ExamplePlugin(BasePlugin):
    name = "example_plugin"
    version = "1.0.0"
    dependencies = {}

    def _init_(self):
        """插件加载时调用"""
        print('_init_')
        print(f"Plugin {self.name} loaded.")
        print(f"Plugin work in {os.getcwd()}")
        with self.work_space:
            print(f"Plugin work in {os.getcwd()}")
        print(self.data)
        # 获取当前文件的绝对路径
        current_file_path = os.path.abspath(__file__)
        print("当前文件路径:", current_file_path)

        # 获取当前文件所在的目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        print("当前文件所在目录:", current_file_dir)
        self.data ['a'] = self.data.get('a', 0) + 1
        self.register_handlers()

    def _close_(self):
        """插件卸载时调用"""
        print('_close_')
        print(self.data)
        print(f"Plugin {self.name} unloaded.")

    # @bot.group_event(row_event=True)
    def process_event(self, event: Event):
        """处理事件的方法"""
        print(event)
        event.add_result("Hello, this is a response from ExamplePlugin")
        print(self.unregister_handler(self.id1))

    def register_handlers(self):
        """注册事件处理器"""
        self.id1 = self.register_handler("re:.*", self.process_event)
        print(str(self.id1))

# @bot.group_event(row_event=True)
# def process_event(event: Event):
#     """处理事件的方法"""
#     print(event)
#     event.add_result("Hello, this is a response from ExamplePlugin")