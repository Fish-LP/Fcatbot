# 插件管理器
from pathlib import Path
from .abc import EventBus, DefaultPluginManager
from .loader import PluginLoader
from typing import List, Optional

class PluginManager(DefaultPluginManager):
    def __init__(
        self,
        plugin_dirs: List[Path],
        config_base_dir: Path,
        data_base_dir: Path,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        super().__init__(
            plugin_dirs,
            config_base_dir,
            data_base_dir,
            event_bus,
            False
        )
        self.loader = PluginLoader(self.event_bus, self.config_manager, data_base_dir, False)