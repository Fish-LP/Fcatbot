# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-05-16 21:30:50
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-29 20:08:42
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
from typing import TYPE_CHECKING, Dict


if TYPE_CHECKING:
    from .loader import PluginLoader
    from .base_plugin import BasePlugin
else:
    PluginLoader = object
    BasePlugin = object

class PluginSysApi:
    """为Plugin提供管理其他插件的接口类"""
    def __init__(self, plugin_sys: PluginLoader):
        """初始化插件系统API。

        Args:
            plugin_sys (PluginLoader): 插件加载器实例
        """
        self._plugin_sys = plugin_sys
        
    async def unload_plugin(self, plugin_name: str, **kwargs) -> bool:
        """卸载指定的插件。

        Args:
            plugin_name (str): 要卸载的插件名称
            *args, **kwargs: 传递给插件卸载方法的额外参数

        Returns:
            bool: 卸载是否成功
        """
        return await self._plugin_sys.unload_plugin(plugin_name, **kwargs)
        
    async def reload_plugin(self, plugin_name: str, **kwargs) -> bool:
        """重新加载指定的插件。

        Args:
            plugin_name (str): 要重新加载的插件名称

        Returns:
            bool: 重载是否成功
        """
        return await self._plugin_sys.reload_plugin(plugin_name, **kwargs)
        
    def get_loaded_plugins(self) -> Dict[str, BasePlugin]:
        """获取所有已加载的插件。

        Returns:
            Dict[str, BasePlugin]: 插件名称到插件实例的映射
        """
        return self._plugin_sys.plugins
