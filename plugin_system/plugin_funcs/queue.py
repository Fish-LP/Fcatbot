# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-06-24 22:10:13
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-25 18:42:31
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from asyncio import Queue, Lock
from ..abc_api import AbstractPluginApi

class QueueManager(AbstractPluginApi):
    _queues = {}
    _queues_lock = Lock()
    
    async def get_queue(self, name, maxsize=8) -> Queue:
        '''获取管道，如果不存在则创建'''
        async with self._queues_lock:
            if name in self._queues:
                return self._queues[name]
            else:
                q = Queue(maxsize)
                self._queues[name] = q
                return q