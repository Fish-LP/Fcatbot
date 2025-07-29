# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-07-25 10:46:27
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-28 21:02:02
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from datetime import datetime
from typing import Any, Dict, Tuple, Type, Optional

class CodecMeta(type):
    _by_type: Dict[Type, "Type[Codec]"] = {}     # type -> codec
    _by_tag:  Dict[str, "Type[Codec]"] = {}      # tag  -> codec

    def __new__(mcls, name: str, bases, ns, **kw):
        cls: "Codec" = super().__new__(mcls, name, bases, ns, **kw)
        if bases:                                  # 跳过基类本身
            mcls._by_type[cls.py_type] = cls
            mcls._by_tag[cls.tag] = cls
        return cls


class Codec(metaclass=CodecMeta):
    tag: str
    py_type: Type

    # ---------- 留给子类实现 ----------
    @classmethod
    def encode(cls, obj: Any) -> Dict[str, Any]:
        raise NotImplementedError
    
    @classmethod
    def decode(cls, dct: Dict[str, Any]) -> Any:
        raise NotImplementedError

    # ---------- 通用静态快捷 ----------
    @staticmethod
    def encode_any(obj: Any) -> Dict[str, Any]:
        codec = CodecMeta._by_type.get(type(obj), None)
        if codec is None:
            raise TypeError(f"不支持的类型 {type(obj)}")
        return codec.encode(obj)

    @staticmethod
    def decode_any(dct: Dict[str, Any]) -> Any:
        for tag, codec in CodecMeta._by_tag.items():
            if tag in dct:
                return codec.decode(dct)
        return dct        # 不是已知 tag，原样返回继续走默认流程

# ---------- 主要Codec ----------
class TupleCodec(Codec):
    tag = "__tuple__"
    py_type = tuple

    @classmethod
    def encode(cls, obj):
        return {cls.tag: [CodecConverter.encode(item, (str, int, float, bool, type(None))) for item in obj]}

    @classmethod
    def decode(cls, dct):
        return tuple(CodecConverter.decode(item) for item in dct[cls.tag])


class SetCodec(Codec):
    tag = "__set__"
    py_type = set

    @classmethod
    def encode(cls, obj):
        return {cls.tag: [CodecConverter.encode(item, (str, int, float, bool, type(None))) for item in obj]}

    @classmethod
    def decode(cls, dct):
        return set(CodecConverter.decode(item) for item in dct[cls.tag])


# ---------- 额外Codec ----------
import base64
class BytesCodec(Codec):
    tag = "__bytes__"
    py_type = bytes

    @classmethod
    def encode(cls, obj: bytes) -> Dict[str, Any]:
        b64_str = base64.b64encode(obj).decode("ascii")
        return {cls.tag: b64_str}

    @classmethod
    def decode(cls, dct: Dict[str, Any]) -> bytes:
        b64_str: str = dct[cls.tag]
        return base64.b64decode(b64_str.encode("ascii"))


from uuid import UUID
class UUIDCodec(Codec):
    tag = "__uuid__"
    py_type = UUID

    @classmethod
    def encode(cls, obj: Any) -> Dict[str, Any]:
        return {cls.tag: str(obj)}

    @classmethod
    def decode(cls, dct):
        return UUID(dct[cls.tag])


class DateTimeCodec(Codec):
    tag = "__datetime__"
    py_type = datetime

    @classmethod
    def encode(cls, obj: Any) -> Dict[str, Any]:
        return {cls.tag: str(obj)}

    @classmethod
    def decode(cls, dct):
        return datetime.fromisoformat(dct[cls.tag])


from pathlib import Path
class PathCodec(Codec):
    tag = "__path__"
    py_type = Path

    @classmethod
    def encode(cls, obj):
        return {cls.tag: str(obj)}

    @classmethod
    def decode(cls, dct):
        return Path(dct[cls.tag])


class CodecConverter:
    """把任意 Python 对象⇄可 JSON/YAML/TOML 化的中间形式"""

    @staticmethod
    def encode(obj: Any, native_types: Tuple[Type, ...]) -> Any:
        """向下转换（Python 对象 → 基本类型树）"""

        # 先判断是否需要 Codec
        if not isinstance(obj, native_types):
            codec = CodecMeta._by_type.get(type(obj))
            if codec is not None:
                return codec.encode(obj)

        # 容器递归，让异常直接冒泡
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                out[k] = CodecConverter.encode(v, native_types)
            return out
        if isinstance(obj, (list, tuple, set)):
            return [CodecConverter.encode(item, native_types) for item in obj]

        if isinstance(obj, native_types):
            return obj

        # 未注册类型
        raise TypeError(f"不支持的类型 {type(obj)}")

    @staticmethod
    def decode(obj: Any) -> Any:
        """向上还原（基本类型树 → Python 对象）"""
        if isinstance(obj, dict):
            decoded = Codec.decode_any(obj)   # 看看是不是带 tag 的对象
            if decoded is not obj:            # 命中 Codec
                return decoded
            # 普通 dict，继续递归
            return {k: CodecConverter.decode(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [CodecConverter.decode(item) for item in obj]
        return obj