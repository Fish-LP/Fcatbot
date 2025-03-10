# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-20 20:49:52
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-10 21:43:02
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from .message import MessageAPi
from .group import GroupApi
from .system import SystemApi
from .user import UserAPi


class Apis(MessageAPi, GroupApi, SystemApi, UserAPi):
    def __init__(self, client):
        self.ws_client = client

__all__ = [
    'Apis'
]