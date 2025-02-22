# Fbot

Fbot 是一个用于构建聊天机器人的框架，核心代码均位于 [Fbot](Fbot) 目录中。
注意：本仓库只包含 Fbot 部分，其他外部文件（如 [test.py](test.py)）仅用于本地测试。

## 快速开始

1. **环境要求**
   请确保安装 Python 3.10 或更高版本。
2. **安装依赖**
   在项目根目录下运行：

   ```sh
   pip install -e .
   ```
3. **运行测试脚本**
   暂时没有测试脚本

4. **启动 Fbot**
   可直接运行以下代码启动服务：

   ```python
   from Fbot import BotClient, EventBus, Event, PluginLoader
   from Fbot.config import PLUGINS_DIR

   event_bus = EventBus()

   loader = PluginLoader(event_bus)
   Client = BotClient(event_bus, 'ws://{your adder}')

   asyncio.run(loader.load_plugins(PLUGINS_DIR, ws=Client.ws))
   Client.run()
   ```

## 示例代码

```python
import asyncio
from Fbot.ws import WebSocketHandler
from Fbot import MessageChain

async def main():
    async with WebSocketHandler('ws://127.0.0.1:3001') as client:
        response = await client.send_group_msg(
            MessageChain().add_text('Hello from external test'),
            group_id='901031378'
        )
        print(f"返回: {response}")

if __name__ == '__main__':
    asyncio.run(main())
```

## 关于

- 更多详细请参考代码内的相关说明。
- 相关 API 接口可分别在 Fbot.ws.api 中查看。

## 许可

本项目基于 MIT 许可证，详细信息请参见 LICENSE 文件。
