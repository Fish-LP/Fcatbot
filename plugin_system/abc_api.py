# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-15 19:12:16
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-15 19:22:17
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from ..ws import WebSocketHandler

class IPluginApi:
    api: WebSocketHandler

class AbstractPluginApi:
    def init_api(self):
        pass