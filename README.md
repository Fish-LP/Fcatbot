# Fcatbot

Fbot 是一个基于事件总线的插件化 QQ 机器人框架。它允许开发者通过编写插件来扩展机器人的功能。

> 文档仅供参考，更新缓慢

## 核心概念

### 事件总线

事件总线是 Fbot 的核心概念之一。它允许插件之间通过发布和订阅事件进行通信。事件总线支持同步和异步事件处理。

### 插件

插件是 Fbot 的功能扩展单元。每个插件都是 `BasePlugin` 类的子类，并实现其 `on_load` 和 `on_unload` 方法。

## 快速开始

### 环境设置

1. 克隆项目到本地Fcatbot文件夹(解压后应该为Fcatbot-main文件夹，文件夹中存在READM.md)：

   ```bash
   git clone https://github.com/Fish-LP/FBot
   ```

2. 安装依赖与Fcatbot：

   ```bash
   mv ./Fcatbot-main ./Fcatbot
   pip install -r Fcatbot/requirements.txt
   pip install -e ./Fcatbot
   ```

### 编写插件

创建一个新的插件文件文件，如 `./plugins/my_plugin/main.py`：

```python
from Fcatbot import BasePlugin, Event, CompatibleEnrollment, get_log
import os

LOG = get_log('ExamplePlugin')
bot = CompatibleEnrollment

class ExamplePlugin(BasePlugin):
    name = "example_plugin"
    version = "1.0.0"
    dependencies = {}

    def _init_(self):
        """插件加载时调用"""
        print('_init_')
        print(f"Plugin {self.name} loaded.")
        print(f"Plugin work in {os.getcwd()}")
        with self.work_space:
            print(f"Plugin work in {os.getcwd()}")
        print(self.data)
        # 获取当前文件的绝对路径
        current_file_path = os.path.abspath(__file__)
        print("当前文件路径:", current_file_path)

        # 获取当前文件所在的目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        print("当前文件所在目录:", current_file_dir)
        self.data ['a'] = self.data.get('a', 0) + 1
        self.register_handlers()

    def _close_(self):
        """插件卸载时调用"""
        print('_close_')
        print(self.data)
        print(f"Plugin {self.name} unloaded.")

    # @bot.group_event(row_event=True)
    def process_event(self, event: Event):
        """处理事件的方法"""
        print(event)
        event.add_result("Hello, this is a response from ExamplePlugin")
        print(self.unregister_handler(self.id1))

    def register_handlers(self):
        """注册事件处理器"""
        self.id1 = self.register_handler("re:.*", self.process_event)
        print(str(self.id1))

# @bot.group_event(row_event=True)
# def process_event(event: Event):
#     """处理事件的方法"""
#     print(event)
#     event.add_result("Hello, this is a response from ExamplePlugin")
```

与 `__init__.py`

```python
from .main import MyPlugin

__all__ = [
    'MyPlugin'
]
```

同时支持可选文件`requirements.txt`用来定义额外依赖，当插件加载时会尝试安装

> 此文件通常由pip创建

```bash
pip freeze > requirements.txt
```

### 启动脚本

创建一个启动脚本，例如 `start_bot.py`：

```python
from Fcatbot import BotClient, Event,

def main():
    Client = BotClient('ws://127.0.0.1:3001')
    Client.run() # 添加参数 debug=True 就行简单调试

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
2. 插件在加载时调用 `on_load`  `_init_`方法，在卸载时调用 `on_unload` `_close_` 方法。
3. 插件可以通过 `publish_sync` 和 `publish_async` 方法发布事件。

### 插件基类

以下是 `BasePlugin` 类的部分代码，展示了插件的基本结构和功能：

```python
class BasePlugin:
    """插件基类

    所有插件必须继承此类来实现插件功能。提供了插件系统所需的基本功能支持。

    Attributes:
        name (str): 插件名称
        version (str): 插件版本号 
        dependencies (dict): 插件依赖项配置
        meta_data (dict): 插件元数据
        api (WebSocketHandler): API接口处理器
        event_bus (EventBus): 事件总线实例
        lock (asyncio.Lock): 异步锁对象
        work_path (Path): 插件工作目录路径
        data (UniversalLoader): 插件数据管理器
        work_space (ChangeDir): 插件工作目录上下文管理器
        first_load (bool): 是否首次加载标志
        _debug (bool): 调试模式标记
    """

    name: str
    version: str
    dependencies: dict
    meta_data: dict
    api: WebSocketHandler
    first_load: bool
    debug: bool = False  # 调试模式标记
  
    @final
    def __init__(self, event_bus: EventBus, debug: bool = False, **kwd):
        """初始化插件实例
  
        Args:
            event_bus: 事件总线实例
            debug: 是否启用调试模式
            **kwd: 额外的关键字参数,将被设置为插件属性
  
        Raises:
            ValueError: 当缺少插件名称或版本号时抛出
            PluginLoadError: 当工作目录无效时抛出
        """
        ...

    @property
    def debug(self) -> bool:
        """是否处于调试模式"""
        ...

    @final
    def check_debug(self, func_name: str) -> None:
        """检查是否允许在当前模式下调用某功能
  
        Args:
            func_name: 功能名称
  
        Raises:
            RuntimeError: 当在调试模式下调用受限功能时抛出
        """
        restricted_funcs = {
            'send_group_msg': '发送群消息',
            'send_private_msg': '发送私聊消息',
            'set_group_ban': '设置群禁言',
            'set_group_admin': '设置群管理员',
            # 添加其他需要限制的功能
        }
  
        if self._debug and func_name in restricted_funcs:
            raise RuntimeError(f"调试模式下禁止使用 {restricted_funcs[func_name]} 功能,触发者: {self.name}")

    @final
    async def __unload__(self, *arg, **kwd):
        """卸载插件时的清理操作
  
        执行插件卸载前的清理工作,保存数据并注销事件处理器
  
        Raises:
            RuntimeError: 保存持久化数据失败时抛出
        """
        self.unregister_handlers()
        await asyncio.to_thread(self._close_, *arg, **kwd)
        await self.on_close(*arg, **kwd)
        ...

    @final
    async def __onload__(self):
        """加载插件时的初始化操作
  
        执行插件加载时的初始化工作,加载数据
  
        Raises:
            RuntimeError: 读取持久化数据失败时抛出
        """
        # load时传入的参数作为属性被保存在self中
        try:
            if isinstance(self.data,dict):
                data = UniversalLoader()
                data.data = self.data
                self.data = data
            self.data.load()
        except (FileTypeUnknownError, LoadError, FileNotFoundError) as e:
            open(self._work_path / f'{self.name}.json','w').write('{}')
            self.data.load()
        await asyncio.to_thread(self._init_)
        await self.on_load()

    @final
    def publish_sync(self, event: Event) -> List[Any]:
        """同步发布事件

        Args:
            event (Event): 要发布的事件对象

        Returns:
            List[Any]: 事件处理器返回的结果列表
        """
        return self.event_bus.publish_sync(event)

    @final
    def publish_async(self, event: Event) -> Awaitable[List[Any]]:
        """异步发布事件

        Args:
            event (Event): 要发布的事件对象

        Returns:
            List[Any]: 事件处理器返回的结果列表
        """
        return self.event_bus.publish_async(event)

    @final
    def register_handler(self, event_type: str, handler: Callable[[Event], Any], priority: int = 0) -> UUID:
        """注册事件处理器
  
        Args:
            event_type (str): 事件类型
            handler (Callable[[Event], Any]): 事件处理函数
            priority (int, optional): 处理器优先级,默认为0
  
        Returns:
            处理器的唯一标识UUID
        """
        ...

    @final
    def unregister_handler(self, handler_id: UUID) -> bool:
        """注销指定的事件处理器
  
        Args:
            handler_id (UUID): 事件id
  
        Returns:
            bool: 操作结果
        """
        ...

    @final
    def unregister_handlers(self):
        """注销所有已注册的事件处理器"""
        ...

    async def on_load(self):
        """插件初始化时的子函数,可被子类重写"""
        pass

    async def on_close(self, *arg, **kwd):
        """插件卸载时的子函数,可被子类重写"""
        pass

    def _init_(self):
        """插件初始化时的子函数,可被子类重写"""
        pass

    def _close_(self, *arg, **kwd):
        """插件卸载时的子函数,可被子类重写"""
        pass
```

通过以上步骤，您可以快速开始使用 Fbot 并编写自己的插件来扩展机器人的功能。

## 文件结构

以下是一个文件结构，展示了正确设置的Fcatbot文件结构样式：

```python
./
--Fcatbot/
----...
--plugins/
----plugin/
------__init__.py
------...
----...
```

文档仅供参考，因为更新缓慢
