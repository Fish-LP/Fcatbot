# Fcatbot

聊天机器人平台框架（Python 3.11+ / asyncio）。设计参考 [mirai](https://github.com/mamoe/mirai)：
三层架构、双轨事件、自研插件内核、命令树、双链权限模型、消息链；**核心自研、边缘复用**。

> 当前进度：M1（内核事件层）已完成；权限接入（luckperms）与 `lp` 命令集已落地（M5 部分提前）；
> 连接件基座（正向 WS / HTTP）与配置化启动已落地（M4 部分提前）。
> 路线图见 [`docs/architecture.md`](docs/architecture.md) §6。

## 特性

- **三层架构**：`kernel`（平台无关内核） / `adapter`（协议适配基座） / `frontend`（控制台、WebUI）；
  依赖规则见 [ADR-0001](docs/adr/0001-layered-architecture.md)。
- **两阶段事件管线**：`RawEvent` → 适配器插件解析 → 强类型 `PlatformEvent`；
  双轨订阅（类型继承匹配 / 字符串名 `fnmatch` 通配）。
- **单 worker 串行事件总线**：优先级、`cancel()` 中断、背压、嵌套发布内联展开
  （[ADR-0004](docs/adr/0004-event-dispatch-semantics.md)）。
- **插件体系**：三模式加载（包 / 单文件 / ZIP）+ 声明式事件订阅 / 命令 / 服务注册。
- **命令系统**：装饰器 + 子命令树 + Tab 补全 + 来源感知（控制台 / 聊天，临时 `CommandContext` 桥）。
- **权限**：`PermissionService` 协议，内置 `allow_all` / `null` / `luckperms`（[luckperms-python](https://github.com/Fish-LP/LuckPerms-Python)）；
  内置官方结构的 `lp` 命令集（[docs/005](docs/005-lp-command-official-alignment.md)）。
- **插件脚手架**：一条命令生成规范骨架。

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows（POSIX: source .venv/bin/activate）
pip install -e ".[dev]"

python main.py                       # 等价于 fcatbot / python -m fcatbot.app
python main.py -c config/app.yaml    # 指定配置文件（CLI 唯一参数）
```

除“到哪去找配置文件”外，**全部运行参数都在 `config/app.yaml`**：
`webui`（enabled / host / port / password / secret_key / session_ttl / cookie_secure）、
`transport`（正向 WS / HTTP）、`api`、`plugins.dirs`。
WebUI 未配置 `password` 时会在启动时随机生成 12 位密码，并在启动前打印到**本地控制台**
（只写终端 stdout，不进日志，避免被广播）；如需固定密码，请写入 `webui.password`。
控制台输入 `help` 查看命令，`exit` 退出。

## 目录结构

```
Fcatbot4/
├── main.py                  # 启动器（python main.py，实现见 fcatbot.app）
├── pyproject.toml           # 依赖 / CLI 入口（fcatbot、fcatbot-new-plugin）
├── config/
│   ├── app.yaml             # 应用配置（app / permissions / transport / api / webui / plugins）
│   └── plugins/<name>.yaml  # 插件配置（缺省值首次启动自动落盘）
├── data/permissions/        # luckperms 权限数据（运行时生成，YAML）
├── plugins/                 # 插件目录（包 / 单文件 / ZIP 三种形态）
│   ├── echo/  report/  weather/
├── src/fcatbot/
│   ├── __init__.py          # 公共 API（插件作者唯一入口）
│   ├── app.py               # FcatbotApp 装配 + CLI
│   ├── builtin.py           # 内置命令（help / plugins / reload / services / config / health）
│   ├── lp_commands.py       # lp 权限管理命令集
│   ├── api_client.py        # 通用 HTTP 发送客户端（协议无关）
│   ├── kernel/              # 平台无关内核
│   │   ├── events.py        # Event 族 / EventBus / EventChannel
│   │   ├── entities.py      # Bot / Contact 等实体抽象
│   │   ├── commands.py      # CommandRegistry / CommandSpec / CommandContext
│   │   ├── permissions.py   # PermissionService 协议与实现
│   │   ├── services.py      # ServiceRegistry（跨插件服务）
│   │   ├── loader.py        # 三模式插件加载器
│   │   ├── plugins.py       # FcatbotPlugin 基类
│   │   ├── integration.py   # PluginForge ↔ 总线/命令/服务（M3 移除）
│   │   └── decorators.py    # @on_event
│   ├── frontend/            # 前端层
│   │   ├── console.py  completer.py  term.py  theme.py  webui.py
│   │   └── webui_static/
│   ├── tools/new_plugin.py  # 插件脚手架
│   └── utils/               # 日志 / 颜色
└── tests/                   # pytest（71 项）
```

> **导入路径**：框架只使用规范路径（`fcatbot.kernel.*` / `fcatbot.frontend.*`）；插件代码请统一
> 使用公共 API `from fcatbot import ...`。旧的顶层路径（`fcatbot.commands`、`fcatbot.permissions` …）
> 已随结构重组**移除**，不再提供兼容 shim。

## 配置

`config/app.yaml`：

```yaml
app:
  name: Fcatbot
  version: 1.0.0
permissions:
  backend: luckperms        # luckperms（官方标准实现）| allow_all（开发全放行）| null（全拒绝）
  data_dir: data/permissions
  default_group: default    # 未注册用户的兜底组（自动继承）
  console_user: console     # 控制台身份：自动创建并保留 *
plugins:
  enabled: [report, weather, echo]   # 插件白名单：新增插件需加入此处
  disabled: []
```

- 权限后端为 `luckperms` 时，数据存于 `data/permissions/*.yaml`（原子写，可直接编辑或经 Web Editor 导出）。
- 首次启动可用 `lp root <用户ID>`（仅控制台）引导根管理员。

## 插件开发

### 脚手架

```bash
fcatbot-new-plugin my_plugin                          # 包模式（plugins/my_plugin/）
fcatbot-new-plugin my_plugin --mode single            # 单文件（plugins/my_plugin.py）
python -m fcatbot.tools.new_plugin my_plugin \
    --description "我的插件" --author Fish --version 1.0.0

# 常用参数
#   -d/--dir <目录>        插件目录（默认 plugins）
#   --config-dir <目录>    配置目录（默认 config/plugins）
#   --no-config            不生成配置文件
#   --force                覆盖已存在目标
```

生成后把插件名加入 `config/app.yaml → plugins.enabled`，再启动宿主。

### 最小插件（包模式）

```python
# plugins/my_plugin/plugin.py
from fcatbot import Event, FcatbotPlugin, console_command, on_event


class MyPluginPlugin(FcatbotPlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "我的插件"
    target_application = "fcatbot"
    min_app_version = "1.0.0"
    default_config = {"reply": "pong"}

    def init(self, app_config, plugin_config):
        super().init(app_config, plugin_config)
        self._reply = self.config.get("reply", "pong")

    def activate(self) -> None:
        self.log.info("my_plugin activated")

    @on_event("raw.*")                       # 原始轨：raw.<transport>.<kind>；业务插件更推荐订阅平台事件
    async def on_raw(self, event: Event) -> None:
        user_id = str(event.metadata.get("user_id", ""))
        if await self.has_permission(user_id, "use"):   # 节点：my_plugin.use
            ...

    @console_command("ping", help="Ping", usage="ping")   # 节点自动派生 my_plugin:command.ping
    def cmd_ping(self, args: list[str]) -> str:
        return self._reply
```

```python
# plugins/my_plugin/__init__.py
from .plugin import MyPluginPlugin

__plugins__ = [MyPluginPlugin]
```

### 异步生命周期与事件感知权限

pluginforge 的 `init` / `activate` / `deactivate` 是**同步**的（pluggy 钩子不 await），需要异步能力
时使用框架提供的四个异步钩子（由 `IntegrationLayer` 编排，`on_load` / `on_enable` 可以 `await`
权限检查、服务查询、事件发布）：

```
init(同步) → activate(同步) → on_load → [装配：事件订阅 + 命令注册] → on_enable
停用：on_disable → [取消后台任务] → [拆卸：退订/注销] → on_unload → deactivate(同步)
```

```python
    async def on_enable(self) -> None:
        # 可以 await：异步入口
        if await self.has_permission("10001", "use"):
            ...
        self.create_task(self._poll(), name="poll")   # 停用时自动取消
```

权限检查有两层：

| 场景 | 用法 |
|------|------|
| 已知用户 + 可选上下文 | `await self.has_permission(user_id, "use", context={"group_id": "123"})` |
| 从事件推导（业务插件） | `await self.has_permission_for(event, "use")` |
| 事件源（适配器）插件 | 覆盖 `permission_subject(event)` / `permission_context(event)`，把平台语义注入上下文 |

```python
    # 适配器插件：Mirai 风格上下文
    def permission_context(self, event: Event) -> dict[str, Any]:
        data = event.data
        sender = getattr(data, "sender", None)
        return {
            "contact": "group", "type": "group",
            "group": str(data.group_id),
            "level": getattr(sender, "role", "member"),
        }

    # 业务插件：主体与上下文都从事件推导
    if not await self.has_permission_for(event, "use"):
        return
```

> 不要改动 `has_permission` 的签名——框架与其他插件都按 `(user_id, node, *, context=...)` 调用；
> 事件→权限的映射属于**适配器插件**职责，用上面两个钩子表达（M2/M4 强类型事件落地后会改为读取实体字段）。

### 约定

| 主题 | 约定 |
|------|------|
| 导入 | 只用公共 API `from fcatbot import ...`；不要 import 框架内部模块 |
| 权限节点 | 显式 `permission=` 优先；否则派生 `{plugin}:command.{name}`；功能节点建议 `{plugin}.{feature}` |
| 配置 | `config_schema` / `default_config` 声明；读取 `self.config.get(key, default)`；文件 `config/plugins/<name>.yaml` |
| 数据 | 与配置分离：`data/<name>/`（M6 提供 DataStore；当前可自行读写该目录） |
| 生命周期 | 同步：`init` / `activate` / `deactivate`（pluginforge）；**异步入口**：`on_load` / `on_enable` / `on_disable` / `on_unload` |
| 后台任务 | `self.create_task(coro, name=...)`，插件停用时自动取消（M3 并入 PluginScope） |
| 服务 | `provides = {"<name>.api": None}` 注册；`self.get_service("<name>.api")` 获取 |
| 依赖 | `depends_on = ["other_plugin"]`（列表或带版本约束的映射，见 `docs/architecture.md` §3.5） |

## 内置命令

| 命令 | 说明 |
|------|------|
| `help [命令\|插件] [-p N]` | 命令列表 / 详情（分页、分组渲染） |
| `plugins` | 列出活跃插件 |
| `reload <name>\|all` | 重载插件 |
| `services` | 列出已注册服务 |
| `config reload` | 重载配置 |
| `health` | 插件健康状态 |
| `exit` / `quit` | 退出（控制台本地处理） |
| `lp ...` | 权限管理命令集（官方 LuckPerms 结构 + 扩展） |

`lp` 常用：`lp info` / `lp sync` / `lp check <用户|me> <节点>` / `lp user <用户|me> ...` /
`lp group <组> ...` / `lp tree <用户|组>` / `lp verbose on|off|upload` / `lp root <用户ID>`（仅控制台）/
`lp editor` + `lp applyedits <code>`（Web Editor）。完整说明见
[docs/005](docs/005-lp-command-official-alignment.md)，输入 `lp` 查看内置帮助。

## 测试

```bash
.venv\Scripts\python.exe -m pytest tests -q     # 41 passed
```

覆盖：内核事件层（双轨订阅 / 发布语义 / 通道）、真实插件端到端装配、权限适配器与 `lp` 命令、
插件脚手架。交互式控制台依赖真实 TTY，需人工验证。

## 文档

| 文档 | 内容 |
|------|------|
| [`docs/architecture.md`](docs/architecture.md) | 架构总览与目标模块结构（§2.3）、核心模型、路线图 |
| [`docs/adr/`](docs/adr/) | 13 项架构决策（三层架构、事件、插件内核、消息链、命令、权限、前端解耦、Web 安全…） |
| [`docs/003-m1-completion.md`](docs/003-m1-completion.md) | M1 事件层实施记录 |
| [`docs/004-permissions-integration.md`](docs/004-permissions-integration.md) | luckperms 权限接入记录 |
| [`docs/005-lp-command-official-alignment.md`](docs/005-lp-command-official-alignment.md) | `lp` 命令对齐官方规范与权限节点设计 |
| [`docs/006-structure-and-tooling.md`](docs/006-structure-and-tooling.md) | 目录结构整理、兼容 shim 策略、插件脚手架 |

## 许可

未指定（内部项目）。
