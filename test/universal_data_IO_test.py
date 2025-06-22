import asyncio
import tempfile
import time
import json
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from pathlib import Path

from Fcatbot.utils.universal_data_IO import LoadError, FileTypeUnknownError, UniversalLoader, WATCHDOG_AVAILABLE, PICKLE_AVAILABLE


# 创建临时目录
temp_dir = Path(tempfile.mkdtemp())
test_data = {
    "string": "Hello, World!",
    "integer": 42,
    "float": 3.14,
    "boolean": True,
    "none": None,
    "list": [1, 2, 3],
    "dict": {"nested": "value"},
    "uuid": UUID("12345678-1234-5678-1234-567812345678"),
    "datetime": datetime(2025, 1, 1, 12, 0, 0),
    "decimal": Decimal("123.45")
}

async def main():
    try:
        # 测试 JSON 格式
        json_file = temp_dir / "test.json"
        loader = UniversalLoader(json_file)
        loader.update(test_data)
        loader.save()
        loader.load()
        assert loader["string"] == test_data["string"]
        assert loader["integer"] == test_data["integer"]
        print("JSON 格式测试通过")

        # 测试 TOML 格式
        toml_file = temp_dir / "test.toml"
        loader = UniversalLoader(toml_file)
        loader.update(test_data)
        loader.save()
        loader.load()
        assert loader["string"] == test_data["string"]
        assert loader["integer"] == test_data["integer"]
        print("TOML 格式测试通过")

        # 测试 YAML 格式
        yaml_file = temp_dir / "test.yaml"
        loader = UniversalLoader(yaml_file)
        loader.update(test_data)
        loader.save()
        loader.load()
        assert loader["string"] == test_data["string"]
        assert loader["integer"] == test_data["integer"]
        print("YAML 格式测试通过")

        # 测试 PICKLE 格式
        pickle_file = temp_dir / "test.pickle"
        loader = UniversalLoader(pickle_file)
        loader.update(test_data)
        loader.save()
        loader.load()
        assert loader["string"] == test_data["string"]
        assert loader["integer"] == test_data["integer"]
        print("PICKLE 格式测试通过")

        # 测试实时保存功能
        realtime_save_file = temp_dir / "test_realtime.json"
        loader = UniversalLoader(realtime_save_file, realtime_save=True)
        loader.update(test_data)
        loader.save()
        loader["new_key"] = "new_value"
        time.sleep(0.5)  # 确保实时保存完成
        assert "new_key" in loader
        assert loader["new_key"] == "new_value"
        print("实时保存功能测试通过")

        # 测试实时加载功能
        if WATCHDOG_AVAILABLE:
            realtime_load_file = temp_dir / "test_realtime_load.json"
            loader = UniversalLoader(realtime_load_file, realtime_load=True)
            loader.update(test_data)
            loader.save()

            with open(realtime_load_file, "w") as f:
                json.dump({"new_key": "new_value"}, f)

            time.sleep(0.5)  # 确保文件修改事件处理完成
            assert "new_key" in loader
            assert loader["new_key"] == "new_value"
            print("实时加载功能测试通过")
        else:
            print("跳过实时加载功能测试: watchdog 模块未安装")

        # 测试异步操作
        async_json_file = temp_dir / "test_async.json"
        async with UniversalLoader(async_json_file) as loader:
            loader.update(test_data)
            await loader.asave()

        async with UniversalLoader(async_json_file) as loader:
            await loader.aload()
            assert loader["string"] == test_data["string"]
            assert loader["integer"] == test_data["integer"]
        print("异步操作测试通过")

        # 测试异常处理
        invalid_file = temp_dir / "test.invalid"
        try:
            UniversalLoader(invalid_file)
            assert False, "应抛出 FileTypeUnknownError"
        except FileTypeUnknownError:
            print("文件类型未知异常测试通过")

        non_existent_file = temp_dir / "nonexistent.json"
        loader = UniversalLoader(non_existent_file)
        try:
            loader.load()
            assert False, "应抛出 FileNotFoundError"
        except FileNotFoundError:
            print("文件不存在异常测试通过")

        pickle_file = temp_dir / "test.pickle"
        try:
            UniversalLoader(pickle_file)
            if not PICKLE_AVAILABLE:
                assert False, "应抛出 ValueError"
        except LoadError:
            if not PICKLE_AVAILABLE:
                print("PICKLE 安全警告测试通过")
            else:
                assert False, "应抛出 ValueError"
                

        print("所有测试通过！")

    finally:
        # 清理临时目录
        import shutil
        shutil.rmtree(temp_dir)

# 运行异步主函数
asyncio.run(main())