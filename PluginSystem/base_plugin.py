# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 20:08:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-02 20:22:44
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, List, Callable, Awaitable
import asyncio
from .event import EventBus, Event
from ..utils import ChangeDir
from ..utils import UniversalLoader
from ..utils.UniversalDataIO import FileTypeUnknownError, SaveError, LoadError
from ..config import PERSISTENT_DIR
from ..ws import WebSocketHandler

class BasePlugin:
    '''插件基类'''
    name: str
    version: str
    dependencies: dict
    meta_data: dict
    ws: WebSocketHandler
    http: None = None
    
    def __init__(self, event_bus: EventBus, **kwd):
        if not self.name: raise ValueError('缺失插件名称')
        if not self.version: raise ValueError('缺失插件版本号')
        if kwd:
            for k, v in kwd.items():
                setattr(self, k, v)
        
        if not self.dependencies: self.dependencies = {}
        self.event_bus = event_bus
        self.api = self.ws or self.http
        self.lock = asyncio.Lock()  # 创建一个异步锁对象
        self.work_path = Path(PERSISTENT_DIR) / self.name
        self._data_file = UniversalLoader(self.work_path / f"{self.name}.json")
        self._event_handlers = []
        
        try:
            self.data = self._data_file.load()
        except LoadError as e:
            self.data = self._data_file
        
        try:
            self.work_path.mkdir(parents=True)
            self.first_load = True
        except FileExistsError:
            self.first_load = False
        
        self.work_space = ChangeDir(self.work, create_missing=True)

    async def __unload__(self):
        self._close_()
        await self.on_unload()
        try:
            self.data.save()
        except (FileTypeUnknownError, SaveError, FileNotFoundError) as e:
            raise RuntimeError(self.name, f"保存持久化数据时出错: {e}")
        self.unregister_handlers()

    def publish_sync(self, event: Event) -> List[Any]:
        return self.event_bus.publish_sync(event)

    def publish_async(self, event: Event) -> Awaitable[List[Any]]:
        return self.event_bus.publish_async(event)

    def register_handler(self, event_type: str, handler: Callable[[Event], Any], priority: int = 0):
        handler_id = self.event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append(handler_id)

    def unregister_handlers(self):
        for handler_id in self._event_handlers:
            self.event_bus.unsubscribe(handler_id)

    async def on_load(self):
        pass

    async def on_unload(self):
        pass

    def _init_(self):
        pass

    def _close_(self):
        pass