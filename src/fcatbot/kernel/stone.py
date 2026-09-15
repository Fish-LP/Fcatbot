from __future__ import annotations

import json
from collections.abc import ItemsView, Iterator, KeysView, ValuesView
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class StorageBackend(Protocol):
    extension: str

    def load(self, path: Path) -> dict[str, Any]: ...
    def save(self, path: Path, data: dict[str, Any]) -> None: ...


class YAMLBackend:
    extension = "yml"

    def load(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader=yaml.FullLoader) or {}

    def save(self, path: Path, data: dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)


class JSONBackend:
    extension = "json"

    def load(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, path: Path, data: dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 元数据约定
# ============================================================
# 用 Field(json_schema_extra={...}) 附加约定：
#   editable: bool   —— 用户是否可手工编辑
#   sensitive: bool  —— 是否敏感（展示/日志可脱敏）
#
# 例：
#   api_key: str = Field(default="", json_schema_extra={"sensitive": True})


# ============================================================
# 基类：声明式 + 动态字段
# ============================================================


class _DynamicBase(BaseModel):
    """声明式字段走 Pydantic 校验；动态字段存 _extra_data。"""

    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    _extra_data: dict[str, Any] = PrivateAttr(default_factory=dict)
    _allow_dynamic: ClassVar[bool] = True

    # ---------- 初始化 ----------

    def __init__(self, **data: Any) -> None:
        declared = self._declared_field_names()
        static = {k: v for k, v in data.items() if k in declared}
        dynamic = {k: v for k, v in data.items() if k not in declared}
        super().__init__(**static)
        object.__setattr__(self, "_extra_data", dict(dynamic))

    # ---------- 内部工具 ----------

    @classmethod
    def _declared_field_names(cls) -> set[str]:
        return set(cls.model_fields.keys())

    def _get_extra_data(self) -> dict[str, Any]:
        try:
            return object.__getattribute__(self, "_extra_data")
        except AttributeError:
            return {}

    def _ensure_extra_data(self) -> dict[str, Any]:
        try:
            return object.__getattribute__(self, "_extra_data")
        except AttributeError:
            object.__setattr__(self, "_extra_data", {})
            return object.__getattribute__(self, "_extra_data")

    # ---------- 属性访问 ----------

    def __getattr__(self, name: str) -> Any:
        # 先让 Pydantic 处理私有属性
        try:
            return BaseModel.__getattr__(self, name)
        except AttributeError:
            pass

        if not name.startswith("_"):
            try:
                return self._get_extra_data()[name]
            except KeyError:
                pass

        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in self._declared_field_names():
            super().__setattr__(name, value)
            return
        if not self._allow_dynamic:
            raise AttributeError(
                f"'{type(self).__name__}' has no attribute '{name}' "
                f"and dynamic fields are disabled"
            )
        self._ensure_extra_data()[name] = value

    def __delattr__(self, name: str) -> None:
        if name.startswith("_"):
            raise AttributeError(f"Cannot delete private attribute '{name}'")
        if name in self._declared_field_names():
            raise AttributeError(f"Cannot delete declared field '{name}'")
        extra = self._ensure_extra_data()
        if name in extra:
            del extra[name]
            return
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    # ---------- Mapping-like ----------

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        delattr(self, key)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self._declared_field_names() or key in self._get_extra_data()

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        yield from self._declared_field_names()
        yield from self._get_extra_data()

    def __len__(self) -> int:
        return len(self._declared_field_names()) + len(self._get_extra_data())

    def _as_dict(self) -> dict[str, Any]:
        d = {name: getattr(self, name) for name in self._declared_field_names()}
        d.update(self._get_extra_data())
        return d

    def keys(self) -> KeysView[str]:
        return self._as_dict().keys()

    def values(self) -> ValuesView[Any]:
        return self._as_dict().values()

    def items(self) -> ItemsView[str, Any]:
        return self._as_dict().items()

    # ---------- 序列化 ----------

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        base = super().model_dump(**kwargs)
        base.update(self._get_extra_data())
        return base

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        from_attributes: bool | None = None,
        context: dict[str, Any] | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
        extra: Literal["allow", "ignore", "forbid"] | None = None,
    ) -> Self:
        if isinstance(obj, dict):
            declared = cls._declared_field_names()
            static = {k: v for k, v in obj.items() if k in declared}
            dynamic = {k: v for k, v in obj.items() if k not in declared}
            instance = super().model_validate(
                static,
                strict=strict,
                from_attributes=from_attributes,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
                extra=extra,
            )
            object.__setattr__(instance, "_extra_data", dict(dynamic))
            return instance
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
            extra=extra,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls.model_validate(data)


# ============================================================
# 持久化基类：私有属性 + 方法
# ============================================================


class _PersistedBase(_DynamicBase):
    """
    叠加持久化能力。不调用 bind() 时纯内存使用。

    属性通过 Pydantic PrivateAttr 管理，每个实例独立。
    """

    _name: str = PrivateAttr(default="")
    _path: Path | None = PrivateAttr(default=None)
    _backend: StorageBackend = PrivateAttr(default_factory=YAMLBackend)

    # ---------- 配置 ----------

    def set_name(self, name: str) -> Self:
        """设置持久化文件名（不含后缀）。返回 self 支持链式。"""
        self._name = name
        return self

    def set_backend(self, backend: StorageBackend) -> Self:
        """切换存储后端。返回 self 支持链式。"""
        self._backend = backend
        return self

    # ---------- 绑定 ----------

    def bind(self, path: Path | str, *, as_dir: bool | None = None) -> Self:
        """
        绑定持久化路径。

        Args:
            path: 目录或文件路径。
            as_dir: 显式指定 path 的语义：

                - ``True``  —— path 是目录，追加 ``{_name}.{ext}``（需先 set_name）。
                - ``False`` —— path 是文件，直接用（无后缀会自动补后端后缀）。
                - ``None``  —— 启发式（默认，兼容旧行为）：
                    · 已存在的目录       → 目录
                    · 带后缀             → 文件
                    · 无后缀且不存在     → 文件，自动补后缀

        说明：
            ``None`` 下"无后缀且不存在"会被当成文件——这正是
            ``bind(self.data_dir)`` 在目录尚未创建时会生成
            ``.../echo.json`` 的原因。想避免歧义，传 ``as_dir=True``。

        文件存在则 load，否则 save。返回 self。
        """
        p = Path(path)

        if as_dir is True:
            if not self._name:
                raise RuntimeError(f"Cannot bind as directory {p!r} without set_name()")
            p = p / f"{self._name}.{self._backend.extension}"
        elif as_dir is False:
            if not p.suffix:
                p = p.with_suffix(f".{self._backend.extension}")
        else:
            # 启发式：保持旧行为
            if p.is_dir():
                if not self._name:
                    raise RuntimeError(
                        f"Cannot bind to directory {p!r} without set_name()"
                    )
                p = p / f"{self._name}.{self._backend.extension}"
            elif not p.suffix:
                p = p.with_suffix(f".{self._backend.extension}")

        self._path = p

        if p.exists():
            self.load()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            self.save()

        return self

    # ---------- 读写 ----------

    def load(
        self,
        *,
        merge: Literal["file_wins", "keep_current"] = "file_wins",
    ) -> None:
        """
        从磁盘加载。

        merge:
          - "file_wins"（默认）: 文件值完全覆盖内存。
          - "keep_current": 只填充未显式设置的字段；动态字段 setdefault 合并。
        """
        if self._path is None:
            raise RuntimeError("Not bound: call bind() first")

        raw = self._backend.load(self._path)
        if not isinstance(raw, dict):
            raw = {}

        raw = self._apply_migration(raw)
        loaded = type(self).model_validate(raw)

        if merge == "file_wins":
            for key in loaded._declared_field_names():
                setattr(self, key, getattr(loaded, key))
            object.__setattr__(self, "_extra_data", dict(loaded._get_extra_data()))
        elif merge == "keep_current":
            for key in loaded._declared_field_names():
                if key not in self.model_fields_set:
                    setattr(self, key, getattr(loaded, key))
            extra = self._ensure_extra_data()
            for k, v in loaded._get_extra_data().items():
                extra.setdefault(k, v)
        else:  # pragma: no cover
            raise RuntimeError(f"Unknown merge mode: {merge!r}")

    def save(self) -> None:
        """保存到磁盘。用 JSON 模式序列化，保证跨后端类型往返一致。"""
        if self._path is None:
            raise RuntimeError("Not bound: call bind() first")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._backend.save(self._path, self.model_dump(mode="json"))

    def reload(
        self,
        *,
        merge: Literal["file_wins", "keep_current"] = "file_wins",
    ) -> None:
        """文件存在时重新加载。"""
        if self._path and self._path.exists():
            self.load(merge=merge)

    # ---------- 状态 ----------

    @property
    def is_bound(self) -> bool:
        return self._path is not None

    @property
    def path(self) -> Path | None:
        return self._path

    # ---------- 迁移钩子 ----------

    @classmethod
    def _apply_migration(cls, raw: dict[str, Any]) -> dict[str, Any]:
        current = getattr(cls, "CONFIG_VERSION", None)
        migrate = getattr(cls, "migrate", None)
        if not isinstance(current, int) or not callable(migrate):
            return raw

        version = raw.get("config_version")
        if not isinstance(version, int) or version == current:
            return raw

        migrated = migrate(dict(raw), version)
        if isinstance(migrated, dict):
            raw = migrated
        raw["config_version"] = current
        return raw


# ============================================================
# 用户面向类
# ============================================================


class PluginConfig(_PersistedBase):
    """
    插件配置。禁止动态字段，用户可手工编辑 YAML，带持久化。

    - 字段用 Pydantic Field 声明；约定元数据放 json_schema_extra。
    - 覆盖 CONFIG_VERSION，并在 migrate() 里实现版本迁移。
    - 不调用 bind() 就是纯内存对象。
    """

    _allow_dynamic: ClassVar[bool] = False
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )

    CONFIG_VERSION: ClassVar[int] = 1

    config_version: int = Field(
        default=1,
        description="配置结构版本，用于迁移",
        json_schema_extra={"editable": False},
    )

    def model_post_init(self, __context: Any) -> None:
        # 未显式设置时，写入类声明的当前版本
        if "config_version" not in self.model_fields_set:
            self.config_version = type(self).CONFIG_VERSION

    @classmethod
    def migrate(cls, data: dict[str, Any], from_version: int) -> dict[str, Any]:
        """
        子类重写以支持从旧版本迁移。返回迁移后的字典；
        config_version 会由框架写回为当前值。

        示例:
            @classmethod
            def migrate(cls, data, from_version):
                if from_version < 2:
                    data["timeout"] = data.pop("timeout_ms", 30000) // 1000
                return data
        """
        return data


class PluginData(_PersistedBase):
    """插件运行时数据。声明式字段 + 动态字段，带持久化。"""

    _allow_dynamic: ClassVar[bool] = True
    model_config = ConfigDict(
        extra="ignore",
        validate_assignment=True,
        populate_by_name=True,
    )
