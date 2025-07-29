# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-13 21:47:01
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-29 11:20:23
# @Description  : 通用文件加载器，支持JSON/TOML/YAML/PICKLE格式的同步/异步读写
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import asyncio
import logging
from pathlib import Path
from typing import Union

from .data_types import DataHolder
from .io_drivers import FileDriver

class UniversalLoader(DataHolder):
    Version = 2.0
    
    def __init__(self, file_path: Union[str, Path], **kwargs):
        super().__init__()
        self.file_path = Path(file_path)
        self.driver = FileDriver(self.file_path)
        self._save_task = None
        self._dirty = False
        
        # 功能开关
        self.auto_save = kwargs.get('auto_save', False) # 默认关闭自动保存
        self.auto_load = kwargs.get('auto_load', False) # 默认关闭自动读取
        self.save_delay = kwargs.get('save_delay', 0.1) # 自动保存延迟时间(秒)

    def load(self):
        """同步加载数据"""
        if self.file_path.exists():
            data = self.driver.load()
            self.clear()
            self.update(data)
        else:
            raise FileNotFoundError(f"文件 {self.file_path} 不存在", self.file_path)
        return self

    def save(self, path=None):
        """同步保存数据"""
        save_path = path or self.file_path
        self.driver.save(dict(self))
        self._dirty = False

    async def aload(self):
        """异步加载数据"""
        if self.file_path.exists():
            data = await self.driver.aload()
            self.clear()
            self.update(data)
        else:
            raise FileNotFoundError(f"文件 {self.file_path} 不存在", self.file_path)
        return self

    async def asave(self, path=None):
        """异步保存数据"""
        save_path = path or self.file_path
        await self.driver.asave(dict(self))
        self._dirty = False

    def _schedule_save(self):
        if not self.auto_save:
            return

        if self._save_task and not self._save_task.done():
            return

        async def _delayed_save():
            await asyncio.sleep(self.save_delay)
            if self._dirty:
                await self.asave()

        self._save_task = asyncio.create_task(_delayed_save())
        self._save_task.add_done_callback(self._on_save_error)

    def _on_save_error(self, fut):
        if fut.exception():
            logging.exception("Auto save failed", exc_info=fut.exception())

    def __setitem__(self, key, value):
        if key not in self or self[key] != value:
            super().__setitem__(key, value)
            self._dirty = True
            self._schedule_save()

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._dirty = True
        self._schedule_save()

    @property
    def is_auto_save(self) -> bool:
        """获取自动保存状态"""
        return self.auto_save

    @is_auto_save.setter
    def is_auto_save(self, value: bool):
        """设置自动保存状态"""
        self.auto_save = value
        if value and self._dirty:  # 如果开启自动保存且数据已修改
            self._schedule_save()

    @property
    def is_auto_load(self) -> bool:
        """获取自动读取状态"""
        return self.auto_load

    @is_auto_load.setter 
    def is_auto_load(self, value: bool):
        """设置自动读取状态"""
        self.auto_load = value
        # TODO: 实现自动读取的监听器

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._dirty:
            await self.asave()  # 确保退出时保存

    async def aclose(self) -> None:
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        if self._dirty:
            await self.asave()

    def close(self) -> None:
        """立即保存并清理自动保存任务"""
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()          # 1. 取消未开始的延迟保存
        if self._dirty:                       # 2. 立即刷盘
            try:
                self.save()
            except Exception:
                logging.exception("Close flush failed")

    def __del__(self):
        """兜底：解释器回收前再尝试保存一次"""
        try:
            self.close()
        except Exception:
            pass