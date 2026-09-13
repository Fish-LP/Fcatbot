"""
Fcatbot 启动器（``python main.py``）。
"""

from __future__ import annotations

from fcatbot.app import main
from fcatbot.tools.new_plugin import main as new_plugin

if __name__ == "__main__":
    main()
    # new_plugin()
