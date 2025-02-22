# Fbot

Fbot 是一个基于事件总线的插件化 QQ 机器人框架。它允许开发者通过编写插件来扩展机器人的功能。

## 核心概念

### 事件总线

事件总线是 Fbot 的核心概念之一。它允许插件之间通过发布和订阅事件进行通信。事件总线支持同步和异步事件处理。

### 插件

插件是 Fbot 的功能扩展单元。每个插件都是 `BasePlugin` 类的子类，并实现其 `on_load` 和 `on_unload` 方法。

## 快速开始

### 环境设置

1. 克隆项目到本地：

   ```bash
   git clone https://github.com/Fish-LP/FBot
   ```
2. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

### 编写插件

创建一个新的插件文件，例如 `my_plugin.py`：

```python
from Fbot.plugin_sys.base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    name = "MyPlugin"
    version = "1.0.0"
    dependencies = {}

    async def on_load(self):
        print(f"{self.name} loaded")

    async def on_unload(self):
        print(f"{self.name} unloaded")

    def _init_(self):
        print(f"{self.name} initialized")

    def _close_(self):
        print(f"{self.name} closed")
```

### 启动脚本

创建一个启动脚本，例如 `start_bot.py`：

```python
from Fbot.plugin_sys.event import EventBus, Event
from plugins.my_plugin import MyPlugin

def main():
    event_bus = EventBus()
    plugin = MyPlugin(event_bus)
    plugin._init_()
    event_bus.publish_sync(Event("plugin_loaded", plugin))
    # ... 其他启动逻辑 ...

if __name__ == "__main__":
    main()
```

### 运行机器人

使用以下命令启动机器人：

```bash
python start_bot.py
```

## 插件系统运行逻辑

1. 插件通过事件总线注册事件处理器。
2. 插件在加载时调用 `on_load` 方法，在卸载时调用 `on_unload` 方法。
3. 插件可以通过 `publish_sync` 和 `publish_async` 方法发布事件。

### 插件基类

以下是 `BasePlugin` 类的部分代码，展示了插件的基本结构和功能：

```python
class BasePlugin:
    '''插件基类'''
    # ...existing code...
    def __init__(self, event_bus: EventBus, **kwd):
        # ...existing code...
        self.lock = asyncio.Lock()  # 创建一个异步锁对象
        self._event_handlers = []
        # ...existing code...

    async def __unload__(self):
        self._close_()
        await self.on_unload()
        self._save_persistent_data()
        self.unregister_handlers()

    def _load_persistent_data(self) -> Dict[str, Any]:
        # ...existing code...

    def _save_persistent_data(self):
        # ...existing code...

    def publish_sync(self, event: Event) -> List[Any]:
        return self.event_bus.publish_sync(event)

    def publish_async(self, event: Event) -> Awaitable[List[Any]]:
        return self.event_bus.publish_async(event)

    def register_handler(self, event_type: str, handler: Callable[[Event], Any], priority: int = 0):
        handler_id = self.event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append(handler_id)

    def unregister_handlers(self):
        for handler_id in self._event_handlers:
            self.event_bus.unsubscribe(handler_id)

    async def on_load(self):
        pass

    async def on_unload(self):
        pass

    def _init_(self):
        pass

    def _close_(self):
        pass
```

通过以上步骤，您可以快速开始使用 Fbot 并编写自己的插件来扩展机器人的功能。

## 示例插件

以下是一个示例插件，展示了如何处理群消息并回复：

```python
from Fbot.plugin_sys.base_plugin import BasePlugin
from Fbot.message import GroupMessage

class ExamplePlugin(BasePlugin):
    name = "ExamplePlugin"
    version = "1.0.0"
    dependencies = {}

    async def on_load(self):
        self.register_handler("group_message", self.handle_group_message)
        print(f"{self.name} loaded")

    async def on_unload(self):
        print(f"{self.name} unloaded")

    async def handle_group_message(self, event):
        message: GroupMessage = event.data
        if "hello" == message.row:
            await message.reply("Hello! How can I help you?")
```

通过这个示例插件，当机器人收到包含 "hello" 的群消息时，它会自动回复 "Hello! How can I help you?"。

# 文档由ai创建，任何信息以实际实现为准
