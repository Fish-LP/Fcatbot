# 插件加载器
from .abc import DefaultPluginLoader, PluginSource, Plugin
from .compatible import LazyDecoratorResolver
from typing import List

class PluginLoader(DefaultPluginLoader):
    async def load_from_source(self, source: PluginSource) -> List[Plugin]:
        plugins = await super().load_from_source(source)
        event_bus = self.event_bus

        for plugin in plugins:
            # 遍历所有延迟解析器
            for resolver in LazyDecoratorResolver._subclasses:
                for attr_name in dir(plugin):
                    attr = getattr(plugin, attr_name)
                    if callable(attr) and resolver.check(attr):
                        resolver.handle(plugin, attr, event_bus)
        return plugins