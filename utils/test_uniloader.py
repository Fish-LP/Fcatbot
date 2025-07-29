#!/usr/bin/env python3
# test_uniloader_standalone.py
import os, sys, uuid, asyncio, tempfile, json, yaml, toml
from datetime import datetime
from pathlib import Path

# 动态添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# ------------- 动态插入项目根目录 -------------
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from Fcatbot.utils.uniloader.codec import CodecMeta, Codec, CodecConverter
from Fcatbot.utils.uniloader.io_drivers import FileDriver
from Fcatbot.utils.uniloader.serializers import JsonSerializer, YamlSerializer, TomlSerializer
from Fcatbot.utils.uniloader.uniloader import UniversalLoader

# ------------- 基础工具 -------------
TEST_DIR = Path(os.getenv("UNILOADER_TEST_DIR", "/tmp/uniloader_test"))
TEST_DIR.mkdir(exist_ok=True, parents=True)


def rand_path(suffix: str) -> Path:
    return TEST_DIR / f"{uuid.uuid4().hex}{suffix}"


async def _yield():
    """让出事件循环，确保后台任务完成。"""
    await asyncio.sleep(0.2)


# ------------- 测试用例 -------------
async def test_codec_roundtrip():
    data = {
        "uid": uuid.uuid4(),
        "ts": datetime.now().replace(microsecond=0),
        "tags": {"python", "yaml", "toml"},
    }
    for suffix, ser_cls in ((".json", JsonSerializer), (".yaml", YamlSerializer), (".toml", TomlSerializer)):
        path = rand_path(suffix)
        await FileDriver(path).asave(ser_cls.serialize(data))
        restored = ser_cls.deserialize(await FileDriver(path).aload())
        assert CodecConverter.decode(restored) == data, f"{suffix} round-trip failed"
    print("✔ test_codec_roundtrip")


async def test_encode_options():
    # JSON indent
    old = JsonSerializer.encode_options["indent"]
    JsonSerializer.encode_options["indent"] = 8
    raw = JsonSerializer.serialize({"a": 1})
    assert b"        " in raw  # 8 spaces
    JsonSerializer.encode_options["indent"] = old

    # YAML flow style
    old = YamlSerializer.encode_options["default_flow_style"]
    YamlSerializer.encode_options["default_flow_style"] = True
    raw = YamlSerializer.serialize({"x": [1, 2]})
    assert b"[1, 2]" in raw
    YamlSerializer.encode_options["default_flow_style"] = old
    print("✔ test_encode_options")


async def test_concurrent():
    path = rand_path(".json")
    loader1 = UniversalLoader(path)
    loader2 = UniversalLoader(path)
    loader1["a"] = 1
    await _yield()
    await loader2.aload()
    assert loader2["a"] == 1
    print("✔ test_concurrent")


async def test_large():
    big = {f"k{i}": i for i in range(10_000)}
    path = rand_path(".yaml")
    loader = UniversalLoader(path)
    loader.update(big)
    await loader.asave()
    await loader.aload()
    assert len(loader) == 10_000 and loader["k9999"] == 9999
    print("✔ test_large")


async def test_errors():
    class Foo:
        pass

    try:
        CodecConverter.encode({"bad": Foo()}, JsonSerializer.native_types)
    except TypeError:
        pass
    else:
        raise AssertionError("未捕获非法类型")

    bad = rand_path(".json")
    bad.write_text("{invalid json", encoding="utf-8")
    try:
        await UniversalLoader(bad).aload()
    except Exception:
        pass
    else:
        raise AssertionError("未捕获损坏文件")
    print("✔ test_errors")


# ------------- 扩展用例 -------------
async def test_custom_codec():
    class Point:
        def __init__(self, x: int, y: int):
            self.x, self.y = x, y

        def __eq__(self, other):
            return isinstance(other, Point) and (self.x, self.y) == (other.x, other.y)

    class PointCodec(Codec):
        tag = "__point__"
        py_type = Point

        @classmethod
        def encode(cls, obj: Point) -> Dict[str, Any]:
            return {cls.tag: [obj.x, obj.y]}

        @classmethod
        def decode(cls, dct: Dict[str, Any]) -> Point:
            x, y = dct[cls.tag]
            return Point(x, y)

    assert CodecMeta._by_type[Point] is PointCodec

    data = {"pos": Point(3, 4)}
    path = rand_path(".json")
    await FileDriver(path).asave(JsonSerializer.serialize(data))
    restored = JsonSerializer.deserialize(await FileDriver(path).aload())
    assert CodecConverter.decode(restored) == data
    print("✔ test_custom_codec")


async def test_auto_save_toggle():
    path = rand_path(".json")
    loader = UniversalLoader(path, auto_save=False)
    loader["x"] = 1
    await _yield()
    assert not path.exists()

    loader.is_auto_save = True
    await _yield()
    assert path.exists() and json.loads(path.read_bytes())["x"] == 1

    loader.is_auto_save = False
    loader["y"] = 2
    old_mtime = path.stat().st_mtime
    await _yield()
    assert path.stat().st_mtime == old_mtime
    print("✔ test_auto_save_toggle")


async def test_empty_file():
    path = rand_path(".json")
    path.touch()
    loader = UniversalLoader(path)
    try:
        await loader.aload()
    except json.decoder.JSONDecodeError:
        pass
    else:
        assert False
    print("✔ test_empty_file")


async def test_unknown_extension():
    path = rand_path(".unknown")
    try:
        FileDriver(path)
    except ValueError:
        pass
    else:
        raise AssertionError("未捕获未知扩展名")
    print("✔ test_unknown_extension")


async def test_bytes_exact_match():
    data = {"msg": "hello🐱"}
    for ser_cls in (JsonSerializer, YamlSerializer, TomlSerializer):
        blob = ser_cls.serialize(data)
        restored = ser_cls.deserialize(blob)
        assert CodecConverter.decode(restored) == data
        blob2 = ser_cls.serialize(data)
        assert blob == blob2
    print("✔ test_bytes_exact_match")


async def test_file_lock_timeout():
    path = rand_path(".json")
    async with FileDriver(path)._lock:
        loader = UniversalLoader(path)
        loader["a"] = 1
        await asyncio.wait_for(_yield(), timeout=1.0)
    print("✔ test_file_lock_timeout")


# ------------- 主入口 -------------
async def main():
    tests = [
        test_codec_roundtrip,
        test_encode_options,
        test_concurrent,
        test_large,
        test_errors,
        test_custom_codec,
        test_auto_save_toggle,
        test_empty_file,
        test_unknown_extension,
        test_bytes_exact_match,
        test_file_lock_timeout,
    ]
    for t in tests:
        await t()
    print("\n🎉 所有独立测试通过！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print("❌ 断言失败:", e)
        sys.exit(1)
    except Exception as e:
        print("❌ 发生异常:", e)
        sys.exit(2)