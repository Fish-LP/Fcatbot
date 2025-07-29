# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-07-24 19:12:14
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-29 16:08:14
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
# serializers.py 补丁
import json
from datetime import datetime
from typing import Any, Dict
from .codec import CodecConverter
from .io_drivers import SerializerPlugin


class JsonSerializer(SerializerPlugin):
    file_extension = "json"
    codec_fallback = True
    native_types = (type(None), bool, int, float, str, list, dict)
    encode_options: Dict[str, Any] = {"ensure_ascii": False, "indent": 4}

    @classmethod
    def serialize(cls, data: Dict[str, Any]) -> bytes:
        # 先把所有对象转成可 JSON 化的中间形式
        payload = CodecConverter.encode(data, cls.native_types)
        return json.dumps(payload, **cls.encode_options).encode()

    @classmethod
    def deserialize(cls, content: bytes) -> Dict[str, Any]:
        raw = json.loads(content.decode())
        return CodecConverter.decode(raw)

try:
    import yaml
    class YamlSerializer(SerializerPlugin):
        file_extension = "yaml"
        codec_fallback = True
        native_types = (
            type(None), bool, int, float, str,
            list, dict, datetime, bytes
        )
        encode_options: Dict[str, Any] = {"allow_unicode": True, "default_flow_style": False}

        @classmethod
        def serialize(cls, data: Dict[str, Any]) -> bytes:
            payload = CodecConverter.encode(data, cls.native_types)
            return yaml.dump(payload, **cls.encode_options).encode()

        @classmethod
        def deserialize(cls, content: bytes) -> Dict[str, Any]:
            raw = yaml.safe_load(content.decode()) or {}
            return CodecConverter.decode(raw)
except ImportError:
    pass

try:
    import toml
    class TomlSerializer(SerializerPlugin):
        file_extension = "toml"
        codec_fallback = True
        native_types = (
            type(None), bool, int, float, str,
            list, dict, datetime
        )
        encode_options: Dict[str, Any] = {}

        @classmethod
        def serialize(cls, data: Dict[str, Any]) -> bytes:
            payload = CodecConverter.encode(data, cls.native_types)
            return toml.dumps(payload, **cls.encode_options).encode()

        @classmethod
        def deserialize(cls, content: bytes) -> Dict[str, Any]:
            raw = toml.loads(content.decode())
            return CodecConverter.decode(raw)
except ImportError:
    pass