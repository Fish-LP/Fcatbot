# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-10-01 21:53:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-10-02 15:19:52
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from ..abc import PluginStatus, PluginContext, PluginName, PluginVersion, PROTOCOL_VERSION
from typing import List, Dict

class BaseMixin:
    name: PluginName
    version: PluginVersion
    authors: List[str] = []
    dependency: Dict[PluginName, str] = {}
    protocol_version: int = PROTOCOL_VERSION
    
    context: PluginContext
    status: PluginStatus
    config: Dict
    meta: Dict
    
    def __init__(self) -> None: pass
    def __close__(self) -> None: pass