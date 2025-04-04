import ast
import asyncio
import json
import os
from typing import Any, Dict, Literal
import unittest
from pathlib import Path
import tempfile
import shutil
# 测试数据
TEST_DATA = {
    'int_key': 42,
    'float_key': 3.14159,
    'str_key': 'Hello, World!',
    'bool_key': True,
    'none_key': None,
    'list_key': [1, 2, 3, 'four', None, True],
    'dict_key': {
        'nested_int': 123,
        'nested_str': 'nested value',
        'nested_list': ['a', 'b', 'c'],
        'nested_dict': {'a': 1, 'b': 2}
    },
    123: 'non_string_key',  # 非字符串键
    (1, 2): 'tuple_key'     # 元组键
}


from Fcatbot.utils.universal_data_IO import FileTypeUnknownError, ModuleNotInstalledError, UniversalLoader

# 创建临时测试目录
# TEST_DIR = Path(tempfile.mkdtemp())
TEST_DIR = Path('./test_cach')
TEST_FILES = {
    'json': TEST_DIR / 'test.json',
    'toml': TEST_DIR / 'test.toml',
    'yaml': TEST_DIR / 'test.yaml',
    # 'ini': TEST_DIR / 'test.ini',
    # 'xml': TEST_DIR / 'test.xml',
    # 'properties': TEST_DIR / 'test.properties',
    # 'pickle': TEST_DIR / 'test.pickle'
}


# 用于测试的异步函数
async def run_async_tests():
    # 测试异步加载和保存
    for file_type, file_path in TEST_FILES.items():
        loader = UniversalLoader(file_path)
        await loader.aload()
        await loader.asave()
        print(f"异步测试: {file_type} 文件加载和保存成功")

# 清理测试环境
def cleanup():
    # shutil.rmtree(TEST_DIR)
    # print("测试环境已清理")
    pass

# 主测试函数
def main():
    try:
        # 创建测试文件
        for file_type, file_path in TEST_FILES.items():
            loader = UniversalLoader(file_path)
            loader.update(TEST_DATA)
            loader.save()
            print(f"创建 {file_type} 测试文件成功")

        # 同步加载和保存测试
        for file_type, file_path in TEST_FILES.items():
            loader = UniversalLoader(file_path)
            loader.load()
            
            # 验证数据是否一致
            if loader != TEST_DATA:
                print()
                print(loader)
                print()
                print(TEST_DATA)
                print()
            assert loader == TEST_DATA, f"{file_type} 数据不一致"
            
            # 保存回文件
            loader.save()
            print(f"同步测试: {file_type} 文件加载和保存成功")

        # 运行异步测试
        asyncio.run(run_async_tests())

        # 错误处理测试
        try:
            UniversalLoader('nonexistent_file.json').load()
        except FileNotFoundError:
            print("文件不存在错误处理测试成功")

        try:
            UniversalLoader('unknown_type.txt').load()
        except FileTypeUnknownError:
            print("未知文件类型错误处理测试成功")

        try:
            UniversalLoader(TEST_FILES['toml']).file_type = 'unknown'
            UniversalLoader(TEST_FILES['toml']).load()
        except FileTypeUnknownError:
            print("手动设置未知文件类型错误处理测试成功")

        try:
            UniversalLoader(TEST_FILES['toml']).file_type = 'toml'
            UniversalLoader(TEST_FILES['toml']).load()
        except ModuleNotInstalledError as e:
            print(f"模块未安装错误处理测试成功: {e}")

        print("所有测试通过!")

    finally:
        cleanup()

if __name__ == "__main__":
    main()
