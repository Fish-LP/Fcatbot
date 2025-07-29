# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-07-28 21:24:40
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-28 21:42:24
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
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
from Fcatbot.utils.uniloader.uniloader import UniversalLoader

data = {
    "uid": uuid.uuid4(),
    "ts": datetime.now().replace(microsecond=0),
    "tags": {"python", "yaml", "toml"},
}

d = UniversalLoader('data.json')
d.update(data)
d.save()

del d
d = UniversalLoader('data.json').load()
print(d)