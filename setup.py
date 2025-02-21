# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-16 12:50:14
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-22 01:23:14
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from setup import setup, find_packages
from . import __version__
setup(
    name='Fbot',  # 包名称
    version=__version__,  # 版本号
    description='基于ncatbot开发',  # 简短描述
    author='Fish-LP',  # 作者姓名
    author_email='fish.zh@outlook.com',  # 作者邮箱
    url='https://github.com/Fish-LP/FBot',  # 项目地址，确保是一个有效的 URL
    packages=find_packages(),  # 自动发现所有包
    include_package_data=True,  # 包含包中的数据文件
    install_requires=[  # 依赖项
        'aifile',
        'aiohttp',
        'websockets',
        'tdqm',
    ],
    classifiers=[  # 分类器
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
    python_requires='>=3.10',  # 所需 Python 版本
    entry_points={},  # 如果没有可执行脚本，可以先留空
)