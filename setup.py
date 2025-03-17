# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-16 12:50:14
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-16 21:44:48
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from setuptools import setup, find_packages 
setup(
    name='Fcatbot',  # 包名称
    version='2.0.1-alpha',  # 版本号
    # 版本号的格式为: 主版本号.次版本号.修订号（MAJOR.MINOR.PATCH）,其中每个部分都是非负整数,且禁止在数字前补零。
    # 主版本号（MAJOR） : 表示软件的重大变更,通常涉及不兼容的 API 修改、重大功能新增或旧功能的废弃。当主版本号增加时,次版本号和修订号必须归零。
    # 次版本号（MINOR） : 表示向后兼容的功能新增或改进。当次版本号增加时,修订号必须归零。
    # 修订号（PATCH） : 表示向后兼容的问题修正或小的改进。
    # 每次提交前请视情况修改版本号
    # dev alpha bate release
    description='基于ncatbot开发',  # 简短描述
    author='Fish-LP',  # 作者姓名
    author_email='fish.zh@outlook.com',  # 作者邮箱
    url='https://github.com/Fish-LP/FcatBot',  # 项目地址,确保是一个有效的 URL
    packages=find_packages(),  # 自动发现所有包
    include_package_data=True,  # 包含包中的数据文件
    install_requires=[  # 依赖项
        'aifile',
        'aiohttp',
        'websockets',
        'tqdm',
        'packaging',
        'aiofile',
    ],
    python_requires='>=3.9',  # 所需 Python 版本
    # entry_points={
    #     'console_scripts':[]
    #     },
)