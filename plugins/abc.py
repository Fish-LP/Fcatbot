# python >= 3.11

# TODO 完善zip导入功能
# TODO 哈气

from __future__ import annotations
from abc import ABC, ABCMeta, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
import functools
import importlib
import importlib.util
from pathlib import Path
import sys
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Dict,
    Final,
    Iterable,
    List,
    NewType,
    Optional,
    Set,
    Tuple,
    TypeAlias,
    Union,
    Type,
    Pattern,
)
from uuid import UUID
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, Future
import asyncio
import time
from packaging.version import Version, InvalidVersion
from packaging.specifiers import SpecifierSet, InvalidSpecifier
from functools import partial
from contextlib import contextmanager
import logging
import uuid
import aiofiles.os
import aiofiles
import inspect
import json
import yaml
import zipfile
import os
import re


# 配置日志
logger = logging.getLogger("PluginsSys")

# -----------------------------------------------------------------------------
# 基础类型定义
# -----------------------------------------------------------------------------

PluginName = NewType("PluginName", str)
PluginVersion = NewType("PluginVersion", str)

SyncHandler: TypeAlias = Callable[["Event"], Any]
AsyncHandler: TypeAlias = Callable[["Event"], Awaitable[Any]]
EventHandler: TypeAlias = Union[SyncHandler, AsyncHandler]

# 框架级常量
PROTOCOL_VERSION: Final[int] = 0
DEFAULT_MAX_WORKERS: Final[int | None] = None
DEFAULT_REQUEST_TIMEOUT: Final[float] = 10.0
DEBUG_MODE: Final[bool] = True

# -----------------------------------------------------------------------------
# 异常类型定义
# -----------------------------------------------------------------------------

class PluginError(Exception):
    def __init__(self, message: str, plugin_name: Optional[PluginName] = None):
        self.plugin_name = plugin_name
        super().__init__(message)
        
    def add_note(self, note: str) -> None:
        if hasattr(super(), 'add_note'):
            super().add_note(note)

class PluginDependencyError(PluginError): pass
class PluginVersionError(PluginError): pass
class PluginValidationError(PluginError): pass
class PluginRuntimeError(PluginError): pass

# -----------------------------------------------------------------------------
# 事件相关定义（修复：添加事件模式匹配）
# -----------------------------------------------------------------------------

@dataclass
class Event:
    event: str
    data: Any = None
    source: Optional[Any] = None
    target: Optional[Any] = None
    timestamp: float = field(default_factory=time.time)
    
    def __str__(self) -> str:
        source = self.source or "System"
        target = self.target or "All"
        return f"Event(\033[32m{self.event}\033[0m, source=\033[36m{source}\033[0m, target=\033[34m{target}\033[0m, timestamp=\033[33m{self.timestamp}\033[0m)"


@dataclass
class EventHandlerInfo:
    """事件处理器信息"""
    handler: EventHandler
    event_pattern: Union[str, Pattern[str]]
    handler_id: UUID
    is_regex: bool = False
    
    def matches_event(self, event_name: str) -> bool:
        """检查事件是否匹配处理器"""
        if self.is_regex:
            return bool(self.event_pattern.match(event_name))
        else:
            return self.event_pattern == event_name


class EventBus(ABC):
    @abstractmethod
    def register_handler(
        self, 
        event: Union[str, Pattern[str]],  # 支持字符串或正则表达式
        handler: EventHandler
    ) -> UUID: 
        """注册事件处理器"""
        pass
    
    @abstractmethod
    def register_handlers(
        self, 
        event_handlers: Dict[Union[str, Pattern[str]], EventHandler]
    ) -> Dict[Union[str, Pattern[str]], UUID]:
        """批量注册事件处理器"""
        pass
    
    @abstractmethod
    def unregister_handler(self, handler_id: UUID) -> bool: 
        """取消注册事件处理器"""
        pass
    
    @abstractmethod
    async def request(
        self,
        event: str,
        data: Any = None,
        *,
        source: Optional[str] = None,
        target: Optional[str] = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT
    ) -> Dict[UUID, Union[Any, Exception]]: 
        """请求-响应模式"""
        pass
    
    @abstractmethod
    def publish(
        self,
        event: str,
        data: Any = None,
        *,
        source: Optional[str] = None,
        target: Optional[str] = None
    ) -> None:
        """发布-订阅模式"""
        pass
    
    @abstractmethod
    def close(self) -> None: 
        """关闭事件总线"""
        pass
    
    @abstractmethod
    def is_closed(self) -> bool: 
        """检查是否已关闭"""
        pass


def _handler_to_uuid(func) -> uuid.UUID:
    """生成处理器的UUID"""
    while isinstance(func, functools.partial):
        func = func.func
    qualname = getattr(func, "__qualname__", "")
    mod = getattr(func, "__module__", "")
    name = f"{mod}.{qualname}"
    return uuid.uuid5(uuid.NAMESPACE_DNS, name)


def _compile_event_pattern(event_pattern: Union[str, Pattern[str]]) -> Tuple[Union[str, Pattern[str]], bool]:
    """编译事件模式，支持正则表达式"""
    if isinstance(event_pattern, Pattern):
        return event_pattern, True
    
    # 检查是否是正则表达式模式（以re:开头）
    if event_pattern.startswith('re:'):
        pattern_str = event_pattern[3:]
        try:
            compiled_pattern = re.compile(pattern_str)
            return compiled_pattern, True
        except re.error as e:
            logger.warning(f"无效的正则表达式模式 '{pattern_str}': {e}, 将作为普通字符串处理")
            return event_pattern, False
    
    # 普通字符串模式
    return event_pattern, False


class ConcurrentEventBus(EventBus):
    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS) -> None:
        self._handlers: Dict[UUID, EventHandlerInfo] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="EventBus")
        self._lock = threading.RLock()
        self._closed = False
    
    def register_handler(self, handler: EventHandler, event: Union[str, Pattern[str]]) -> UUID:
        """注册事件处理器，支持正则表达式"""
        if self._closed: 
            raise RuntimeError("事件总线已关闭")
        
        # 编译事件模式
        event_pattern, is_regex = _compile_event_pattern(event)
        handler_id = _handler_to_uuid(handler)
        
        with self._lock:
            if handler_id in self._handlers:
                logger.warning(f"处理器 {handler_id} 已注册，将被替换")
            
            self._handlers[handler_id] = EventHandlerInfo(
                handler=handler,
                event_pattern=event_pattern,
                handler_id=handler_id,
                is_regex=is_regex
            )
            
            logger.debug(f"注册事件处理器: {event_pattern} -> {handler_id} (regex: {is_regex})")
        
        return handler_id
    
    def register_handlers(self, event_handlers: Dict[Union[str, Pattern[str]], EventHandler]) -> Dict[Union[str, Pattern[str]], UUID]:
        """批量注册事件处理器"""
        results = {}
        for event, handler in event_handlers.items():
            handler_id = self.register_handler(event, handler)
            results[event] = handler_id
        return results
    
    def unregister_handler(self, handler_id: UUID) -> bool:
        """取消注册事件处理器"""
        with self._lock:
            if handler_id in self._handlers:
                del self._handlers[handler_id]
                logger.debug(f"取消注册事件处理器: {handler_id}")
                return True
            return False
    
    def _get_matching_handlers(self, event: str | Event) -> List[EventHandlerInfo]:
        """获取匹配指定事件的所有处理器"""
        matching_handlers = []
        with self._lock:
            for handler_info in self._handlers.values():
                if handler_info.matches_event(event.event if isinstance(event, Event) else event):
                    matching_handlers.append(handler_info)
        return matching_handlers
    
    async def request(
        self,
        event: str,
        data: Any = None,
        *,
        source: Optional[str] = None,
        target: Optional[str] = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT
    ) -> Dict[UUID, Union[Any, Exception]]:
        """请求-响应模式，只发送给匹配的处理器"""
        if self._closed: 
            raise RuntimeError("事件总线已关闭")
            
        event_obj = event if isinstance(event, Event) else Event(event, data, source, target)
        
        # 获取匹配的处理器
        matching_handlers = self._get_matching_handlers(event)
        if not matching_handlers:
            logger.debug(f"没有找到匹配事件 '{event}' 的处理器")
            return {}
        
        # 在线程池中执行匹配的处理器
        loop = asyncio.get_event_loop()
        futures = []
        handler_infos = []
        
        for handler_info in matching_handlers:
            future = loop.run_in_executor(
                self._executor, 
                self._execute_handler, 
                handler_info.handler, 
                event_obj
            )
            futures.append(future)
            handler_infos.append(handler_info)
        
        # 等待所有处理器完成
        results: Dict[UUID, Union[Any, Exception]] = {}
        
        try:
            done, pending = await asyncio.wait(futures, timeout=timeout)
            
            # 处理已完成的任务
            for i, future in enumerate(futures):
                handler_info = handler_infos[i]
                if future in done:
                    try:
                        result = await future
                        results[handler_info.handler_id] = result
                    except Exception as e:
                        results[handler_info.handler_id] = e
                else:
                    # 取消未完成的任务
                    future.cancel()
                    results[handler_info.handler_id] = asyncio.TimeoutError("处理器执行超时")
                    
        except asyncio.TimeoutError:
            # 整体超时，取消所有未完成的Future
            for i, future in enumerate(futures):
                if not future.done():
                    handler_info = handler_infos[i]
                    future.cancel()
                    results[handler_info.handler_id] = asyncio.TimeoutError("处理器执行超时")
        
        return results
    
    def _execute_handler(self, handler: EventHandler, event: Event) -> Any:
        """在线程池中执行事件处理器"""
        try:
            result = handler(event)
            if isinstance(result, Awaitable):
                return asyncio.run(result)
            return result
        except Exception as e:
            logger.error(f"事件处理器执行失败 Event: {event} Error: {e}", exc_info=True)
            if hasattr(e, 'add_note'):
                e.add_note(f"Event: {event}")
                e.add_note(f"Handler: {handler.__name__ if hasattr(handler, '__name__') else type(handler).__name__}")
            raise
    
    def publish(
        self,
        event: str | Event,
        data: Any = None,
        *,
        source: Optional[str] = None,
        target: Optional[str] = None
    ) -> None:
        """发布-订阅模式，只发送给匹配的处理器"""
        if self._closed: 
            raise RuntimeError("事件总线已关闭")
            
        event_obj = event if isinstance(event, Event) else Event(event, data, source, target)
        
        # 获取匹配的处理器
        matching_handlers = self._get_matching_handlers(event)
        if not matching_handlers:
            logger.debug(f"没有找到匹配事件 '{event}' 的处理器")
            return
        
        # 异步执行所有匹配的处理器
        for handler_info in matching_handlers:
            future = self._executor.submit(self._execute_handler, handler_info.handler, event_obj)
            future.add_done_callback(self._log_handler_exception)
    
    def _log_handler_exception(self, future: Future) -> None:
        """记录处理器执行中的异常"""
        try:
            future.result()
        except Exception as e:
            logger.error(f"事件处理器中出现未处理的异常: {e}", exc_info=True)
    
    def close(self) -> None:
        """关闭事件总线，释放所有资源"""
        with self._lock:
            if self._closed:
                return
                
            self._closed = True
            self._handlers.clear()
            self._executor.shutdown(wait=False)
    
    def is_closed(self) -> bool:
        """检查事件总线是否已关闭"""
        return self._closed

# -----------------------------------------------------------------------------
# 插件相关定义（修复：PluginContext中的事件注册）
# -----------------------------------------------------------------------------

class PluginState(Enum):
    LOADED = auto()
    RUNNING = auto()
    STOPPED = auto()
    FAILED = auto()
    UNLOADED = auto()

@dataclass
class PluginStatus:
    state: PluginState
    error: Optional[Exception] = None
    last_updated: float = field(default_factory=time.time)
    
    def __str__(self) -> str:
        suffix = f": {self.error}" if self.error else ""
        return f"{self.state.name}{suffix}"

class PluginContext:
    def __init__(self, event_bus: EventBus, plugin_name: PluginName, data_dir: Path) -> None:
        self.event_bus = event_bus
        self.plugin_name = plugin_name
        self.data_dir = data_dir
        self.extra_params: Dict[str, Any] = {}  # 记录额外环境参数，服务于混入类
        self.event_handlers: Dict[UUID, Union[str, Pattern[str]]] = {}  # 记录处理器ID和对应的事件模式
        self.original_cwd: Optional[Path] = None
    
    def register_handler(self, event: Union[str, Pattern[str]], handler: EventHandler) -> UUID:
        """注册事件处理器，支持正则表达式"""
        handler_id = self.event_bus.register_handler(handler, event)
        self.event_handlers[handler_id] = event
        return handler_id
    
    def register_handlers(self, event_handlers: Dict[Union[str, Pattern[str]], EventHandler]) -> Dict[Union[str, Pattern[str]], UUID]:
        """批量注册事件处理器"""
        results = self.event_bus.register_handlers(event_handlers)
        self.event_handlers.update(results)
        return results
    
    def unregister_handler(self, handler_id: UUID) -> bool:
        """取消注册事件处理器"""
        if handler_id in self.event_handlers:
            result = self.event_bus.unregister_handler(handler_id)
            if result:
                del self.event_handlers[handler_id]
            return result
        return False
    
    @contextmanager
    def working_directory(self):
        """切换工作目录到插件数据目录的上下文管理器"""
        if self.original_cwd is None:
            self.original_cwd = Path.cwd()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(self.data_dir)
            yield self.data_dir
        finally:
            if self.original_cwd:
                os.chdir(self.original_cwd)
    
    async def run_in_data_dir(self, coro_func: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        """在插件数据目录中运行函数"""
        with self.working_directory():
            return await run_any(coro_func, *args, **kwargs)
        
    def close(self) -> None:
        """清理上下文资源"""
        # 取消注册所有事件处理器
        for handler_id in list(self.event_handlers.keys()):
            self.unregister_handler(handler_id)
        
        # 恢复原始工作目录
        if self.original_cwd:
            os.chdir(self.original_cwd)
    
    def get(self, key: str) -> dict | None:
        return getattr(self, key, None)
    
    def set(self, key: str, value: dict) -> None:
        setattr(self, key, value)

class PluginMeta(ABCMeta):
    def __init__(cls, name: str, bases: Tuple[type, ...], attrs: Dict[str, Any]) -> None:
        super().__init__(name, bases, attrs)
        if ABC in bases: return
        if not hasattr(cls, 'name') or not cls.name:
            raise PluginValidationError(f"插件 {name} 必须有一个非空的 'name' 属性")
        if not hasattr(cls, 'version') or not cls.version:
            raise PluginValidationError(f"插件 {name} 必须有一个非空的 'version' 属性")
        if not isinstance(cls.name, str): cls.name: PluginName = str(cls.name)
        if not isinstance(cls.version, str): cls.version: PluginVersion = str(cls.version)
        raw = getattr(cls, "authors", None)
        if raw is None: cls.authors = []
        elif isinstance(raw, str): cls.authors = [raw]
        elif isinstance(raw, Iterable): cls.authors = [str(a) for a in raw if a is not None]
        else: cls.authors = []
        if not hasattr(cls, 'dependency') or not isinstance(cls.dependency, dict): cls.dependency = {}
        if not hasattr(cls, 'protocol_version'): cls.protocol_version = PROTOCOL_VERSION

class Plugin(ABC, metaclass=PluginMeta):
    name: PluginName
    version: PluginVersion
    authors: List[str] = []
    dependency: Dict[PluginName, str] = {}
    protocol_version: int = PROTOCOL_VERSION
    
    
    def __init__(self, context: PluginContext, config: Dict[str, Any], debug: bool = False) -> None:
        self.context = context
        self.config = config
        self._status = PluginStatus(PluginState.LOADED)
        self._module_name: Optional[str] = None
        self._debug: bool = debug
    
    def __close__(self, close: bool = False) -> None:
        if close:
            self.context.close()
    
    @property
    def meta(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'version': self.version,
            'authors': self.authors,
            'dependency': self.dependency,
            'protocol_version': self.protocol_version
        }
    
    @property
    def status(self) -> PluginStatus: return self._status
    
    @property
    def debug(self) -> bool: return self._debug
    
    def set_module_name(self, module_name: str) -> None: self._module_name = module_name
    def get_module_name(self) -> Optional[str]: return self._module_name
    
    @abstractmethod
    async def on_load(self) -> None: pass
    
    @abstractmethod
    async def on_close(self) -> None: pass
    
    def _set_status(self, state: PluginState, error: Optional[Exception] = None) -> None:
        self._status = PluginStatus(state, error, time.time())

    def add_extra_params(self, **kwargs) -> None:
        """
        添加额外的参数到插件上下文中
        """
        if not hasattr(self.context, 'extra_params'):
            self.context.extra_params = {}
        self.context.extra_params.update(kwargs)

    def __str__(self) -> str:
        return f"Plugin({self.name}, v{self.version}, status={self.status})"

# -----------------------------------------------------------------------------
# 配置管理器（保持不变）
# -----------------------------------------------------------------------------

class ConfigManager:
    def __init__(self, config_base_dir: Path) -> None:
        self.config_base_dir = config_base_dir
    
    async def load_config(self, plugin_name: PluginName) -> Dict[str, Any]:
        plugin_config_dir = self.config_base_dir / plugin_name
        config_files = [
            plugin_config_dir / f"{plugin_name}.yaml",
            plugin_config_dir / f"{plugin_name}.yml",
            plugin_config_dir / f"{plugin_name}.json",
        ]
        
        for config_file in config_files:
            if await aiofiles.os.path.exists(config_file):
                try:
                    async with aiofiles.open(config_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        if config_file.suffix in ('.yaml', '.yml'):
                            return yaml.safe_load(content) or {}
                        else:
                            return json.loads(content) or {}
                except Exception as e:
                    logger.warning(f"加载配置 {config_file} 失败: {e}")
        
        return {}
    
    async def save_config(self, plugin_name: PluginName, config: Dict[str, Any]) -> bool:
        try:
            plugin_config_dir = self.config_base_dir / plugin_name
            await aiofiles.os.makedirs(plugin_config_dir, exist_ok=True)
            
            config_file = plugin_config_dir / f"{plugin_name}.yaml"
            async with aiofiles.open(config_file, 'w', encoding='utf-8') as f:
                await f.write(yaml.dump(config, default_flow_style=False, allow_unicode=True))
            
            return True
        except Exception as e:
            logger.error(f"保存配置失败 {plugin_name}: {e}")
            return False

# -----------------------------------------------------------------------------
# 插件源类型（保持不变）
# -----------------------------------------------------------------------------

class PluginSourceType(Enum):
    DIRECTORY = "directory"
    ZIP_PACKAGE = "zip"
    FILE = "file"

@dataclass
class PluginSource:
    source_type: PluginSourceType
    path: Path
    module_name: str
    
    def cleanup(self) -> None:
        if self.source_type == PluginSourceType.ZIP_PACKAGE:
            zip_path = str(self.path)
            if zip_path in sys.path:
                sys.path.remove(zip_path)
                
            modules_to_remove = []
            for name, module in sys.modules.items():
                if hasattr(module, '__file__') and module.__file__ and zip_path in module.__file__:
                    modules_to_remove.append(name)
            
            for name in modules_to_remove:
                del sys.modules[name]

# -----------------------------------------------------------------------------
# 插件查找器（保持不变）
# -----------------------------------------------------------------------------

class PluginFinder:
    def __init__(self, plugin_dirs: List[Path]) -> None:
        self.plugin_dirs = plugin_dirs
    
    async def find_plugins(self) -> List[PluginSource]:
        sources: List[PluginSource] = []
        
        for plugin_dir in self.plugin_dirs:
            if not await aiofiles.os.path.exists(plugin_dir):
                continue
                
            async for entry in self._scan_directory(plugin_dir):
                sources.append(entry)
        
        return sources
    
    async def _scan_directory(self, directory: Path) -> AsyncIterable[PluginSource]:
        try:
            entries = await aiofiles.os.scandir(directory)
            for entry in entries:
                if entry.is_dir():
                    init_file = Path(entry.path) / "__init__.py"
                    if await aiofiles.os.path.exists(init_file):
                        yield PluginSource(PluginSourceType.DIRECTORY, Path(entry.path), entry.name)

                elif entry.is_file():
                    
                    if entry.name.endswith('.zip'):
                        module_name = entry.name[:-4]
                        if await self._is_valid_zip_plugin(Path(entry.path)):
                            yield PluginSource(PluginSourceType.ZIP_PACKAGE, Path(entry.path), module_name)
                    
                    elif entry.name.endswith('.py') and entry.name != "__init__.py":
                        module_name = entry.name[:-3]  # 去掉 .py 扩展名
                        yield PluginSource(PluginSourceType.FILE, Path(entry.path), module_name)
        except OSError as e:
            logger.warning(f"扫描目录 {directory} 失败: {e}")
    
    async def _is_valid_zip_plugin(self, zip_path: Path) -> bool:
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                return any(name.endswith('__init__.py') for name in zf.namelist())
        except (zipfile.BadZipFile, OSError):
            return False

# -----------------------------------------------------------------------------
# 插件加载器（保持不变）
# -----------------------------------------------------------------------------

class PluginLoader(ABC):
    @abstractmethod
    async def load_from_source(self, source: PluginSource) -> List[Plugin]: pass
    
    @abstractmethod
    async def unload_plugin_module(self, plugin_name: PluginName) -> bool: pass

class DefaultPluginLoader(PluginLoader):
    def __init__(
        self, 
        event_bus: EventBus = None,
        config_manager: ConfigManager = None,
        data_base_dir: Path = './data',
        debug_mode: bool = DEBUG_MODE
    ) -> None:
        self.event_bus = event_bus or ConcurrentEventBus()
        self.config_manager = config_manager or ConfigManager(data_base_dir)
        self.data_base_dir = data_base_dir
        self.debug_mode = debug_mode
        self._loaded_modules: Dict[PluginName, Tuple[str, PluginSource]] = {}
    
    async def load_from_source(self, source: PluginSource) -> List[Plugin]:
        try:
            if source.source_type == PluginSourceType.DIRECTORY:
                return await self._load_from_directory(source)
            elif source.source_type == PluginSourceType.ZIP_PACKAGE:
                return await self._load_from_zip(source)
            elif source.source_type == PluginSourceType.FILE:
                return await self._load_from_file(source)
            else:
                raise PluginValidationError(f"未知的插件源类型: {source.source_type}")
        except Exception as e:
            logger.error(f"从源加载插件失败 {source.path}: {e}")
            return []
    
    async def _load_from_directory(self, source: PluginSource) -> List[Plugin]:
        plugin_dir = source.path
        module_name = source.module_name
        
        if not self.debug_mode and module_name in sys.modules:
            logger.debug(f"模块 {module_name} 已加载，跳过重新加载")
            return []
        
        config = await self.config_manager.load_config(PluginName(module_name))
        data_dir = self.data_base_dir / module_name
        await aiofiles.os.makedirs(data_dir, exist_ok=True)
        
        sys.path.insert(0, str(plugin_dir.parent))
        
        try:
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                spec = importlib.util.spec_from_file_location(module_name, plugin_dir / "__init__.py")
                if spec is None:
                    raise PluginValidationError(f"无法为 {plugin_dir} 创建导入规范")
                
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            
            plugin_classes = self._find_plugin_classes(module, module_name)
            plugins = []
            
            for plugin_cls in plugin_classes:
                context = PluginContext(self.event_bus, plugin_cls.name, data_dir)
                plugin = plugin_cls(context, config, self.debug_mode)
                plugin.set_module_name(module_name)
                self._loaded_modules[plugin.name] = (module_name, source)
                plugins.append(plugin)
            
            return plugins
            
        finally:
            if str(plugin_dir.parent) in sys.path:
                sys.path.remove(str(plugin_dir.parent))
    
    async def _load_from_zip(self, source: PluginSource) -> List[Plugin]:
        try:
            module_name = source.module_name
            
            if not self.debug_mode and module_name in sys.modules:
                logger.debug(f"模块 {module_name} 已加载，跳过重新加载")
                return []
            
            config = await self.config_manager.load_config(PluginName(module_name))
            data_dir = self.data_base_dir / module_name
            await aiofiles.os.makedirs(data_dir, exist_ok=True)
            
            zip_path = str(source.path)
            if zip_path not in sys.path:
                sys.path.insert(0, zip_path)
            
            try:
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                else:
                    module = importlib.import_module(module_name)
                
                plugin_classes = self._find_plugin_classes(module, module_name)
                plugins = []
                
                for plugin_cls in plugin_classes:
                    context = PluginContext(self.event_bus, plugin_cls.name, data_dir)
                    plugin = plugin_cls(context, config, self.debug_mode)
                    plugin.set_module_name(module_name)
                    self._loaded_modules[plugin.name] = (module_name, source)
                    plugins.append(plugin)
                
                return plugins
                
            except ImportError as e:
                raise PluginValidationError(f"无法从ZIP文件导入模块 {module_name}: {e}")
                
        except Exception as e:
            zip_path = str(source.path)
            if zip_path in sys.path:
                sys.path.remove(zip_path)
            raise

    async def _load_from_file(self, source: PluginSource) -> List[Plugin]:
        plugin_file = source.path
        module_name = source.module_name
        
        if not self.debug_mode and module_name in sys.modules:
            logger.debug(f"模块 {module_name} 已加载，跳过重新加载")
            return []
        
        config = await self.config_manager.load_config(PluginName(module_name))
        data_dir = self.data_base_dir / module_name
        await aiofiles.os.makedirs(data_dir, exist_ok=True)
        
        sys.path.insert(0, str(plugin_file.parent))
        
        try:
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                if spec is None:
                    raise PluginValidationError(f"无法为 {plugin_file} 创建导入规范")
                
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            
            plugin_classes = self._find_plugin_classes(module, module_name)
            plugins = []
            
            for plugin_cls in plugin_classes:
                context = PluginContext(self.event_bus, plugin_cls.name, data_dir)
                plugin = plugin_cls(context, config, self.debug_mode)
                plugin.set_module_name(module_name)
                self._loaded_modules[plugin.name] = (module_name, source)
                plugins.append(plugin)
            
            return plugins
            
        finally:
            if str(plugin_file.parent) in sys.path:
                sys.path.remove(str(plugin_file.parent))
    
    def _find_plugin_classes(self, module: Any, module_name: str) -> List[Type[Plugin]]:
        plugin_classes = []
        
        export_names = getattr(module, '__all__', getattr(module, '__plugin__', None))
        
        if export_names:
            export_items = []
            for item in export_names:
                if isinstance(item, str):
                    export_items.append(item)
                elif inspect.isclass(item):
                    export_items.append(item.__name__)
                else:
                    logger.warning(f"忽略__all__中的非字符串/类元素: {item}")
            
            for name in export_items:
                try:
                    obj = getattr(module, name, None)
                    if (inspect.isclass(obj) and issubclass(obj, Plugin) and 
                        obj is not Plugin and not inspect.isabstract(obj)):
                        plugin_classes.append(obj)
                except Exception as e:
                    logger.warning(f"获取导出项 {name} 失败: {e}")
        else:
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, Plugin) and obj is not Plugin and 
                    not inspect.isabstract(obj)):
                    plugin_classes.append(obj)
        
        if not plugin_classes:
            raise PluginValidationError(f"在模块 {module_name} 中未找到插件类")
        
        return plugin_classes
    
    async def unload_plugin_module(self, plugin_name: PluginName) -> bool:
        if plugin_name not in self._loaded_modules:
            return False
        
        module_name, source = self._loaded_modules[plugin_name]
        source.cleanup()
        del self._loaded_modules[plugin_name]
        return True

# -----------------------------------------------------------------------------
# 插件管理器（修复：使用新的事件总线API）
# -----------------------------------------------------------------------------

class PluginManager(ABC):
    @abstractmethod
    async def load_plugins(self) -> List[Plugin]: pass
    @abstractmethod
    async def unload_plugin(self, plugin_name: PluginName) -> bool: pass
    @abstractmethod
    async def start_plugin(self, plugin_name: PluginName) -> bool: pass
    @abstractmethod
    async def stop_plugin(self, plugin_name: PluginName) -> bool: pass
    @abstractmethod
    def get_plugin(self, plugin_name: PluginName) -> Optional[Plugin]: pass
    @abstractmethod
    def list_plugins(self) -> List[PluginName]: pass
    @abstractmethod
    def list_plugins_with_status(self) -> Dict[PluginName, PluginStatus]: pass
    @abstractmethod
    async def close(self) -> None: pass

async def run_any(func, *args, **kw):
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kw)
    loop = asyncio.get_running_loop()
    bound = partial(func, *args, **kw)
    return await loop.run_in_executor(None, bound)

def _topological_sort(plugins: List[Plugin]) -> List[Plugin]:
    name_to_plugin: Dict[PluginName, Plugin] = {p.name: p for p in plugins}
    graph: Dict[PluginName, Set[PluginName]] = {p.name: set() for p in plugins}
    in_degree: Dict[PluginName, int] = {p.name: 0 for p in plugins}

    for p in plugins:
        for dep_name, version_spec in p.dependency.items():
            if dep_name not in name_to_plugin:
                raise PluginDependencyError(f"插件 {p.name} 依赖缺失: {dep_name} {version_spec}", plugin_name=p.name)
            dep_plugin = name_to_plugin[dep_name]
            if not _version_satisfies(dep_plugin.version, version_spec):
                raise PluginDependencyError(f"插件 {p.name} 需要 {dep_name} {version_spec}, 但找到的是 {dep_plugin.version}", plugin_name=p.name)
            graph[dep_name].add(p.name)
            in_degree[p.name] += 1

    queue = [name for name, deg in in_degree.items() if deg == 0]
    sorted_names: List[PluginName] = []

    while queue:
        cur = queue.pop(0)
        sorted_names.append(cur)
        for neighbor in graph[cur]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_names) != len(plugins):
        remaining = [name for name in in_degree if in_degree[name] > 0]
        raise PluginDependencyError(f"插件之间存在循环依赖: {remaining}", plugin_name=remaining[0] if remaining else None)

    return [name_to_plugin[n] for n in sorted_names]

def _version_satisfies(found: PluginVersion, version_spec: str) -> bool:
    try:
        if version_spec.strip() and not any(c in version_spec for c in "<>!=~"):
            version_spec = "==" + version_spec
        specifier = SpecifierSet(version_spec)
        found_version = Version(found)
        return specifier.contains(found_version)
    except (InvalidVersion, InvalidSpecifier) as e:
        raise PluginValidationError(f"无效的版本: found={found}, spec={version_spec}, error={e}")

class DefaultPluginManager(PluginManager):
    def __init__(
        self,
        plugin_dirs: List[Path],
        config_base_dir: Path,
        data_base_dir: Path,
        event_bus: Optional[EventBus] = None,
        dev_mode: bool = DEBUG_MODE
    ) -> None:
        self.plugin_dirs = plugin_dirs
        self.config_base_dir = config_base_dir
        self.data_base_dir = data_base_dir
        self.event_bus = event_bus or ConcurrentEventBus()
        self.dev_mode = dev_mode
        
        self.config_manager = ConfigManager(config_base_dir)
        self.plugin_finder = PluginFinder(plugin_dirs)
        self.loader = DefaultPluginLoader(self.event_bus, self.config_manager, data_base_dir, dev_mode)
        
        self._plugins: Dict[PluginName, Plugin] = {}
        self._plugin_status: Dict[PluginName, PluginStatus] = {}
        self._shutdown = False
        self._lock = threading.RLock()
        
        # 注册插件事件处理器
        self._register_plugin_event_handlers()
    
    def _register_plugin_event_handlers(self):
        """注册插件事件处理器，使用正则表达式匹配所有插件事件"""
        # 注册插件加载事件处理器（匹配所有 plugin.*.load 事件）
        self.event_bus.register_handler(
            self._handle_plugin_load_event,
            "re:plugin\\..*\\.load",
        )
        
        # 注册插件错误事件处理器（匹配所有 plugin.*.error 事件）
        self.event_bus.register_handler(
            self._handle_plugin_error_event,
            "re:plugin\\..*\\.error",
        )
        
        # 注册插件成功事件处理器（匹配所有 plugin.*.ok 事件）
        self.event_bus.register_handler(
            self._handle_plugin_ok_event,
            "re:plugin\\..*\\.ok"
        )
        
        # 注册插件就绪事件处理器（匹配所有 plugin.*.ready 事件）
        self.event_bus.register_handler(
            self._handle_plugin_ready_event,
            "re:plugin\\..*\\.ready"
        )
    
    async def _handle_plugin_load_event(self, event: Event) -> None:
        """处理插件加载事件"""
        logger.debug(f"插件加载: {event.event} - {event.data}")
    
    async def _handle_plugin_error_event(self, event: Event) -> None:
        """处理插件错误事件"""
        logger.error(f"插件错误: {event.event} - {event.data}")
    
    async def _handle_plugin_ok_event(self, event: Event) -> None:
        """处理插件成功事件"""
        logger.debug(f"插件成功: {event.event} - {event.data}")
    
    async def _handle_plugin_ready_event(self, event: Event) -> None:
        """处理插件就绪事件"""
        logger.info(f"插件就绪: {event.event} - {event.data}")
    
    async def _send_plugin_event(self, event_suffix: str, plugin_name: PluginName, data: Any = None) -> None:
        """发送插件事件"""
        event_name = f"plugin.{plugin_name}.{event_suffix}"
        self.event_bus.publish(event_name, data, source="PluginManager", target=plugin_name)
    
    async def load_plugins(self, **kwd) -> List[Plugin]:
        '''额外参数将注入插件，作为属性存在'''
        if self._shutdown:
            raise RuntimeError("插件管理器已关闭")
        
        sources = await self.plugin_finder.find_plugins()
        all_plugins = []
        
        for source in sources:
            try:
                plugins = await self.loader.load_from_source(source)
                for key, val in kwd.items():
                    for p in plugins:
                        setattr(p, key, val)
                all_plugins.extend(plugins)
                
                for plugin in plugins:
                    await self._send_plugin_event("load", plugin.name, plugin.meta)
                    
            except Exception as e:
                logger.error(f"从源加载插件失败 {source.path}: {e}")
                plugin_name = source.module_name
                await self._send_plugin_event("error", PluginName(plugin_name), str(e))
        
        if not all_plugins:
            return []
        
        try:
            sorted_plugins = _topological_sort(all_plugins)
        except PluginDependencyError as e:
            logger.error(f"插件依赖解析失败: {e}")
            if e.plugin_name:
                await self._send_plugin_event("error", e.plugin_name, str(e))
            raise
        
        success_plugins: List[Plugin] = []
        
        for plugin in sorted_plugins:
            if plugin.name in self._plugins:
                logger.debug(f"插件 {plugin.name} 已加载，跳过")
                continue
                
            try:
                if plugin.protocol_version != PROTOCOL_VERSION:
                    raise PluginVersionError(f"插件 {plugin.name} 协议版本不兼容", plugin.name)
                
                await self._send_plugin_event("load", plugin.name, plugin.meta)
                
                await plugin.context.run_in_data_dir(plugin.on_load)
                plugin._set_status(PluginState.RUNNING)
                
                with self._lock:
                    self._plugins[plugin.name] = plugin
                    self._plugin_status[plugin.name] = plugin.status
                
                success_plugins.append(plugin)
                logger.info(f"插件已加载: {plugin.name}@{plugin.version}")
                
                await self._send_plugin_event("ok", plugin.name, plugin.meta)
                
            except Exception as e:
                plugin._set_status(PluginState.FAILED, e)
                logger.exception(f"插件 {plugin.name} 加载失败")
                
                await self._send_plugin_event("error", plugin.name, str(e))
                
                for loaded_plugin in reversed(success_plugins):
                    try:
                        await self.unload_plugin(loaded_plugin.name)
                    except Exception as unload_error:
                        logger.exception(f"卸载插件 {loaded_plugin.name} 时出错: {unload_error}")
                
                if isinstance(e, (PluginVersionError, PluginDependencyError)):
                    raise
                else:
                    raise PluginRuntimeError(str(e), plugin.name) from e
        
        for plugin in success_plugins:
            await self._send_plugin_event("ready", plugin.name, {
                "loaded_plugins": [p.name for p in success_plugins]
            })
        
        return success_plugins
    
    async def unload_plugin(self, plugin_name: PluginName) -> bool:
        with self._lock:
            plugin = self._plugins.pop(plugin_name, None)
            if plugin is None:
                return False
        
        try:
            await self._send_plugin_event("unload", plugin_name)
            
            
            if plugin.status.state == PluginState.RUNNING:
                await plugin.context.run_in_data_dir(plugin.__close__, close = True)
                await plugin.context.run_in_data_dir(plugin.on_close)
            
            plugin._set_status(PluginState.UNLOADED)
            
            await self.loader.unload_plugin_module(plugin_name)
            
            with self._lock:
                self._plugin_status[plugin_name] = plugin.status
            
            logger.info(f"卸载插件: {plugin_name}")
            return True
            
        except Exception as e:
            logger.exception(f"卸载插件 {plugin_name} 时出错: {e}")
            plugin._set_status(PluginState.FAILED, e)
            return False
    
    async def start_plugin(self, plugin_name: PluginName) -> bool:
        plugin = self.get_plugin(plugin_name)
        if plugin is None:
            return False
            
        if plugin.status.state == PluginState.STOPPED:
            try:
                await plugin.context.run_in_data_dir(plugin.on_load)
                plugin._set_status(PluginState.RUNNING)
                
                with self._lock:
                    self._plugin_status[plugin_name] = plugin.status
                
                await self._send_plugin_event("start", plugin_name)
                return True
                
            except Exception as e:
                plugin._set_status(PluginState.FAILED, e)
                logger.exception(f"启动插件 {plugin_name} 失败")
                await self._send_plugin_event("error", plugin_name, str(e))
                return False
        
        return plugin.status.state == PluginState.RUNNING
    
    async def stop_plugin(self, plugin_name: PluginName) -> bool:
        plugin = self.get_plugin(plugin_name)
        if plugin is None:
            return False
            
        if plugin.status.state == PluginState.RUNNING:
            try:
                await plugin.context.run_in_data_dir(plugin.__close__)
                await plugin.context.run_in_data_dir(plugin.on_close)
                plugin._set_status(PluginState.STOPPED)
                
                with self._lock:
                    self._plugin_status[plugin_name] = plugin.status
                
                await self._send_plugin_event("stop", plugin_name)
                return True
                
            except Exception as e:
                plugin._set_status(PluginState.FAILED, e)
                logger.exception(f"停止插件 {plugin_name} 失败")
                await self._send_plugin_event("error", plugin_name, str(e))
                return False
        
        return plugin.status.state == PluginState.STOPPED
    
    def get_plugin(self, plugin_name: PluginName) -> Optional[Plugin]:
        with self._lock:
            return self._plugins.get(plugin_name)
    
    def list_plugins(self) -> List[PluginName]:
        with self._lock:
            return list(self._plugins.keys())
    
    def list_plugins_with_status(self) -> Dict[PluginName, PluginStatus]:
        with self._lock:
            return self._plugin_status.copy()
    
    async def close(self) -> None:
        if self._shutdown:
            return
        
        self._shutdown = True
        
        plugin_names = self.list_plugins()
        for plugin_name in reversed(plugin_names):
            if not await self.unload_plugin(plugin_name):
                logger.error(f"关闭插件时发生错误: {plugin_name}")
        
        if hasattr(self.event_bus, 'close'):
            self.event_bus.close()
        
        logger.info("插件管理器已关闭")

# -----------------------------------------------------------------------------
# 应用程序接口
# -----------------------------------------------------------------------------

class PluginApplication:
    def __init__(
        self,
        plugin_dirs: List[Union[Path, str]],
        config_dir: Union[Path, str] = "config",
        data_dir: Union[Path, str] = "data",
        event_bus: Optional[EventBus] = None,
        plugin_manager: Optional[PluginManager] = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        dev_mode: bool = DEBUG_MODE
    ):
        self.plugin_dirs = [Path(d) for d in plugin_dirs]
        self.config_dir = Path(config_dir)
        self.data_dir = Path(data_dir)
        
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.event_bus = event_bus or ConcurrentEventBus(max_workers=max_workers)
        d = plugin_manager or DefaultPluginManager
        self.plugin_manager = d(
            self.plugin_dirs,
            self.config_dir,
            self.data_dir,
            self.event_bus,
        )
        self._running = False
    
    async def start(self) -> None:
        if self._running:
            return
        
        logger.info("正在启动插件应用程序...")
        
        try:
            await self.plugin_manager.load_plugins()
            self._running = True
            logger.info("插件应用程序已启动")
        except Exception as e:
            logger.error(f"启动插件应用程序失败: {e}")
            raise
    
    async def stop(self) -> None:
        if not self._running:
            return
        
        logger.info("正在停止插件应用程序...")
        await self.plugin_manager.close()
        self._running = False
        logger.info("插件应用程序已停止")
    
    def is_running(self) -> bool:
        return self._running
    
    def get_plugin_manager(self) -> PluginManager:
        return self.plugin_manager
    
    def get_event_bus(self) -> EventBus:
        return self.event_bus
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
