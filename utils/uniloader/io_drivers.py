# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-07-24 19:11:57
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-28 21:19:01
# @Description  : 文件 I/O
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
import asyncio
import aiofiles
from pathlib import Path
from typing import Dict, Any, Tuple, Type

class PluginMeta(type):
    """元类，自动把 SerializerPlugin 子类注册到 FileDriver"""
    def __new__(mcls, name: str, bases, ns, **kw):
        cls = super().__new__(mcls, name, bases, ns, **kw)
        if bases:                       # 跳过基类本身
            FileDriver.register_plugin(cls)
        return cls


class SerializerPlugin(metaclass=PluginMeta):
    file_extension: str
    native_types: Tuple[Type, ...] = ()          # 子类必须声明
    codec_fallback: bool = True                  # 默认兜底
    encode_options: Dict[str, Any] = {}

    @classmethod
    def serialize(cls, data: Dict[str, Any]) -> bytes:
        raise NotImplementedError

    @classmethod
    def deserialize(cls, content: bytes) -> Dict[str, Any]:
        raise NotImplementedError

    # ----------- 可选工具 -----------
    @classmethod
    def is_native(cls, obj: Any) -> bool:
        return isinstance(obj, cls.native_types)


class FileDriver:
    _plugins: Dict[str, Type[SerializerPlugin]] = {}

    @classmethod
    def register_plugin(cls, plugin: Type[SerializerPlugin]):
        cls._plugins[plugin.file_extension.lstrip('.')] = plugin

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.plugin = self._get_plugin(self.file_path.suffix)
        self._lock = asyncio.Lock()

    @classmethod
    def _get_plugin(cls, extension: str) -> Type[SerializerPlugin]:
        ext = extension.lstrip('.')
        if ext not in cls._plugins:
            raise ValueError(f"不支持的文件格式 {extension}")
        return cls._plugins[ext]

    def load(self) -> Dict[str, Any]:
        with open(self.file_path, 'rb') as f:
            content = f.read()
        return self.plugin.deserialize(content)

    def save(self, data: Dict[str, Any]) -> None:
        content = self.plugin.serialize(data)
        with open(self.file_path, 'wb') as f:
            f.write(content)

    # 重命名原异步方法
    async def aload(self) -> Dict[str, Any]:
        async with self._lock:
            async with aiofiles.open(self.file_path, 'rb') as f:
                content = await f.read()
            return self.plugin.deserialize(content)

    async def asave(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            content = self.plugin.serialize(data)
            async with aiofiles.open(self.file_path, 'wb') as f:
                await f.write(content)