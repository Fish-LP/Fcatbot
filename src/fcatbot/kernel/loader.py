"""文件夹 + 单文件 + ZIP 三模式插件加载器。

保留原 fcatbot3 loader.py 的源发现与加载风格，适配 PluginForge 的 BasePlugin。

支持的源形态（按优先级）:
- <dir>/<name>/__init__.py   文件夹模式（包）
- <dir>/<name>.py            单文件模式
- <dir>/<name>.zip           ZIP 模式（内部须有 <name>/__init__.py，可选）

插件类提取规则（按优先级）:
- 若模块定义了 __plugins__ = [Cls1, Cls2]，只取列出的类
- 否则若模块定义了 __all__ = ["Cls1", "Cls2"]，只取其中是 BasePlugin 子类的类
- 否则自动扫描模块内所有非抽象 BasePlugin 子类

用法:
    loader = PluginLoader([Path("plugins")])
    classes = loader.discover()          # 返回 list[type[BasePlugin]]
    result = pm.register_plugins(classes)
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
import zipfile
from pathlib import Path
from types import ModuleType

from pluginforge import BasePlugin

log = logging.getLogger("fcatbot.loader")


class PluginLoadError(Exception):
    """插件加载失败。"""

    def __init__(self, name: str, message: str):
        self.name = name
        super().__init__(f"Plugin '{name}': {message}")


class PluginLoader:
    """扫描 plugin_dirs，发现并加载插件类。"""

    def __init__(self, plugin_dirs: list[Path], *, enable_zip: bool = True):
        self._plugin_dirs = [Path(d) for d in plugin_dirs]
        self._enable_zip = enable_zip

    @property
    def plugin_dirs(self) -> list[Path]:
        return list(self._plugin_dirs)

    # ---------- 公共 API ----------

    def discover(self) -> list[type[BasePlugin]]:
        """扫描所有插件目录，返回所有插件类。

        每个目录下的每个 entry 独立加载。加载失败的 entry 记录日志并跳过，
        不影响其他插件。同名插件（跨目录）只保留第一个。
        """
        classes: list[type[BasePlugin]] = []
        seen: set[str] = set()

        for directory in self._plugin_dirs:
            if not directory.exists():
                log.debug("Plugin dir does not exist: %s", directory)
                continue
            if not directory.is_dir():
                log.warning("Plugin dir is not a directory: %s", directory)
                continue

            for entry in sorted(directory.iterdir()):
                name = self._entry_to_name(entry)
                if name is None or name in seen:
                    continue
                seen.add(name)

                try:
                    cls = self._load_class_by_name(name)
                    classes.append(cls)
                    log.info(
                        "Discovered plugin: %s -> %s (from %s)",
                        name,
                        cls.__name__,
                        entry,
                    )
                except Exception:
                    log.exception("Failed to load plugin from %s", entry)

        return classes

    def load_class(self, name: str) -> type[BasePlugin]:
        """按名称加载单个插件类（用于热重载）。"""
        return self._load_class_by_name(name)

    def clear_cache(self, name: str) -> None:
        """清理 sys.modules 中的旧模块及子模块（供 reload 使用）。"""
        self._clean_module_cache(name)

    def get_source_path(self, name: str) -> Path | None:
        """返回插件的源路径（包目录 / .py 文件 / .zip 文件）。"""
        found = self._find_source(name)
        return found[0] if found else None

    # ---------- 内部: 源发现 ----------

    def _entry_to_name(self, entry: Path) -> str | None:
        """把一个目录项映射为插件名；不是插件源则返回 None。"""
        if entry.is_dir():
            if (entry / "__init__.py").exists():
                return entry.name
            return None

        if entry.is_file():
            if entry.suffix == ".py" and entry.stem != "__init__":
                return entry.stem
            if entry.suffix == ".zip" and self._enable_zip:
                if self._is_valid_zip(entry):
                    return entry.stem
            return None

        return None

    def _find_source(self, name: str) -> tuple[Path, str] | None:
        """在 plugin_dirs 中查找插件源。

        Returns:
            (path, kind)，kind ∈ {'package', 'file', 'zip'}
            未找到返回 None。
        """
        for directory in self._plugin_dirs:
            pkg = directory / name
            if (pkg / "__init__.py").exists():
                return (pkg, "package")

            single = directory / f"{name}.py"
            if single.exists():
                return (single, "file")

            if self._enable_zip:
                zip_pkg = directory / f"{name}.zip"
                if zip_pkg.exists() and self._is_valid_zip(zip_pkg):
                    return (zip_pkg, "zip")

        return None

    @staticmethod
    def _is_valid_zip(zip_path: Path) -> bool:
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                return any(n.endswith("__init__.py") for n in zf.namelist())
        except (zipfile.BadZipFile, OSError):
            return False

    # ---------- 内部: 加载 ----------

    def _load_class_by_name(self, name: str) -> type[BasePlugin]:
        found = self._find_source(name)
        if found is None:
            raise PluginLoadError(name, "source not found")

        path, kind = found
        module = self._load_module(name, path, kind)
        classes = self._extract_plugin_classes(name, module)
        if not classes:
            raise PluginLoadError(name, "no BasePlugin subclass found")

        # 多候选时优先 name 匹配的
        for cls in classes:
            if getattr(cls, "name", None) == name:
                return cls
        return classes[0]

    def _load_module(self, name: str, path: Path, kind: str) -> ModuleType:
        if kind == "zip":
            return self._load_from_zip(path, name)

        self._clean_module_cache(name)
        self._clear_pycache(path)

        if kind == "file":
            spec = importlib.util.spec_from_file_location(name, path)
        else:  # package
            spec = importlib.util.spec_from_file_location(
                name,
                path / "__init__.py",
                submodule_search_locations=[str(path)],
            )

        if spec is None or spec.loader is None:
            raise PluginLoadError(name, f"cannot create module spec from {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return module

    def _load_from_zip(self, zip_path: Path, module_name: str) -> ModuleType:
        """ZIP 模式: 把 ZIP 加入 sys.path 后用包名导入。

        要求 ZIP 内部有 <module_name>/__init__.py，且包名与文件名一致。
        """
        zip_str = str(zip_path)
        self._clean_module_cache(module_name)

        inserted = False
        if zip_str not in sys.path:
            sys.path.insert(0, zip_str)
            inserted = True
        try:
            module = importlib.import_module(module_name)
            return module
        finally:
            if inserted and zip_str in sys.path:
                sys.path.remove(zip_str)

    # ---------- 内部: 类提取 ----------

    @staticmethod
    def _is_plugin_class(obj: object, *, allow_base: bool = False) -> bool:
        return (
            isinstance(obj, type)
            and issubclass(obj, BasePlugin)
            and (allow_base or obj is not BasePlugin)
            and not inspect.isabstract(obj)
        )

    @classmethod
    def _extract_plugin_classes(
        cls, name: str, module: ModuleType
    ) -> list[type[BasePlugin]]:
        """按优先级提取插件类。

        1) 模块显式声明 __plugins__ = [Cls, ...]（或 tuple）→ 只取列出的类
        2) 否则模块声明 __all__ = ["Cls", ...] → 取其中为 BasePlugin 子类的类
        3) 否则自动扫描模块内所有非抽象 BasePlugin 子类
        """
        # 1) __plugins__ 显式导出
        explicit = getattr(module, "__plugins__", None)
        if explicit is not None:
            if not isinstance(explicit, (list, tuple)):
                raise PluginLoadError(
                    name,
                    f"__plugins__ must be list or tuple, "
                    f"got {type(explicit).__name__}",
                )
            return [c for c in explicit if cls._is_plugin_class(c, allow_base=True)]

        # 2) __all__ 过滤
        all_names = getattr(module, "__all__", None)
        if all_names is not None:
            if not isinstance(all_names, (list, tuple)):
                raise PluginLoadError(
                    name,
                    f"__all__ must be list or tuple, "
                    f"got {type(all_names).__name__}",
                )
            result: list[type[BasePlugin]] = []
            for attr_name in all_names:
                if not isinstance(attr_name, str):
                    continue
                obj = getattr(module, attr_name, None)
                if cls._is_plugin_class(obj):
                    result.append(obj)
            return result

        # 3) 自动扫描
        candidates: list[type[BasePlugin]] = []
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if cls._is_plugin_class(obj):
                candidates.append(obj)
        return candidates

    # ---------- 内部: 缓存清理 ----------

    @staticmethod
    def _clean_module_cache(module_name: str) -> None:
        sys.modules.pop(module_name, None)
        prefix = f"{module_name}."
        for key in [k for k in sys.modules if k.startswith(prefix)]:
            del sys.modules[key]
        importlib.invalidate_caches()

    @staticmethod
    def _clear_pycache(path: Path) -> None:
        if path.is_file():
            pycache = path.parent / "__pycache__"
            stem = path.stem
        else:
            pycache = path / "__pycache__"
            stem = "__init__"
        if not pycache.exists():
            return
        for pyc in pycache.glob(f"{stem}.*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass
