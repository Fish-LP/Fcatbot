"""Fcatbot 启动器（``python main.py``）。

应用装配与 CLI 实现见 :mod:`fcatbot.app`（架构 §2.3）；也可以直接使用: 
``fcatbot``（安装后的脚本）或 ``python -m fcatbot.app``。
"""

from __future__ import annotations

from fcatbot.app import main

if __name__ == "__main__":
    main()
