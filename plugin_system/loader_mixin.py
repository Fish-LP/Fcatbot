# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-16 21:30:50
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-16 21:36:29
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from typing import Dict, List, Optional
from .loader import LOG
from .base_plugin import BasePlugin


class PluginInfoMixin:
    """为PluginLoader提供插件信息管理能力的混入类"""
    plugins: Dict[str, BasePlugin]  # 已加载的插件

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """按名称获取插件实例"""
        return self.plugins.get(name)

    def get_metadata(self, name: str) -> dict:
        """获取插件元数据"""
        return self.plugins.get(name).meta_data

    def list_plugins(self) -> List[str]:
        """获取已加载插件列表"""
        return list(self.plugins.keys())

