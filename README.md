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
   使用仓库中提供的测试文件进行快速测试：

   ```sh
   python test.py
   ```
4. **启动 Fbot**
   可直接运行 Fbot 主入口启动服务：

   ```sh
   python main.py
   ```

## 示例代码

在外部测试环境中，可以创建一个新的 Python 文件来调用 Fbot 提供的接口，例如 `external_test.py`：

```python
#!/usr/bin/env python3
# external_test.py
import asyncio
from Fbot.ws import WebSocketHandler
from Fbot import MessageChain  # 假定 MessageChain 为 Fbot 中的消息链实现

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

运行方式：

```sh
python external_test.py
```

## 关于

- 更多详细文档请参考 README.md 内的相关说明。
- 相关 API 接口可分别在 group.py 与 system.py 中查看。

## 许可

本项目基于 MIT 许可证，详细信息请参见 LICENSE 文件。
