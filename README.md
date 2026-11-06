# Fcatbot

聊天机器人平台框架 —— Python 3.11+ / asyncio

Fcatbot 是一个面向即时通讯场景的**聊天机器人平台框架**。设计上参考 [mirai](https://github.com/mamoe/mirai) 的三层架构与双轨事件模型，核心组件（事件总线、命令系统、插件内核、权限模型、连接件基座）自研，边缘能力（插件生命周期管理、权限存储）复用成熟库。框架以插件为核心扩展单元，插件可从目录、单文件或 ZIP 三种形态加载，通过声明式装饰器订阅事件、注册命令、发布服务。

---

## 特性

- **三层架构**：`kernel`（平台无关内核） / `adapter`（协议适配基座） / `frontend`（控制台、WebUI）。依赖方向严格单向：`adapter → kernel`、`frontend → app 公开 API`。
- **两阶段事件管线**：连接件发布 `RawEvent`（原始帧）→ 适配器插件解析并发布强类型平台事件；业务插件订阅强类型事件或原始事件通道。
- **双轨事件订阅**：支持按事件类（`isinstance` 继承匹配）或事件名（`fnmatch` 通配，如 `raw.*`）订阅，二者共享优先级、`once`、`filter` 语义。
- **单 worker 串行事件总线**：优先级降序分发、`event.cancel()` 中断后续订阅者、队列背压、嵌套发布自动内联展开（避免死锁）。
- **声明式插件体系**：`@on_event` 叠加式事件订阅、`@console_command` 命令声明、`provides` 服务导出、`depends_on` 依赖声明；三模式加载（包 / 单文件 / ZIP）。
- **命令系统**：命令树（子命令嵌套）、Tab 补全、来源感知（控制台 / 聊天，`CommandContext`）、权限节点自动派生。
- **多后端权限**：`PermissionService` 协议；内置 `allow_all` / `null` / `luckperms`（基于 [luckperms-python](https://github.com/Fish-LP/LuckPerms-Python)）；附带与官方结构对齐的 `lp` 命令集。
- **连接件基座**：正向 WebSocket 客户端 / HTTP 回调服务器；自动重连、心跳、帧级旁路监听（用于协议层 `echo` 路由）。
- **WebUI 管理界面**：插件启停、YAML 配置编辑、WebSocket 控制台（命令执行 + 日志流）、可选的登录认证（Cookie + HMAC 签名 token）。
- **插件脚手架**：一条命令生成规范插件骨架（包 / 单文件两种形态）。

---

## 快速开始

### 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\Activate.ps1
# POSIX
source .venv/bin/activate

pip install -e ".[dev]"
```

### 启动

```bash
python main.py                       # 等价于 fcatbot / python -m fcatbot.app
python main.py -c config/app.yaml    # 指定配置文件
```

除"到哪去找配置文件"以外，**全部运行参数均来自 `config/app.yaml`**：

- `webui`（`enabled` / `host` / `port` / `password` / `secret_key` / `session_ttl` / `cookie_secure`）
- `transport`（`none` / `forward_ws` / `http`）
- `permissions`（`allow_all` / `null` / `luckperms`）
- `plugins.dirs` / `plugins.enabled`

> 首次启动时若 `config/app.yaml` 缺失，会按内置默认值自动生成一份（已存在则**绝不覆盖**）。
>
> WebUI 的 `password` 留空时，启动时会随机生成 12 位密码，并在 WebUI `start()` **之前**通过本地控制台（`console_print` 直写 stdout，**不经 logging**）打印——避免被 `_WebLogHandler` 广播给已连接的 WebSocket 客户端。如需固定密码，写入 `webui.password`。

控制台输入 `help` 查看命令，`exit` / `quit` 退出。

---

## 目录结构

```
Fcatbot4/
├── main.py                  # 兼容启动器（python main.py）
├── pyproject.toml           # 依赖 / CLI 入口（fcatbot）
├── config/
│   ├── app.yaml             # 应用配置
│   └── plugins/<name>.yaml  # 插件配置（首次启动按 default_config 自动落盘）
├── data/
│   ├── permissions/         # luckperms 权限数据（YAML，运行时生成）
│   └── plugins/<name>/      # 插件专属可写数据目录
├── plugins/                 # 插件目录（包 / 单文件 / ZIP 三种形态）
└── src/fcatbot/
    ├── __init__.py          # 公共 API（插件作者唯一入口）
    ├── app.py               # FcatbotApp 装配 + CLI（fcatbot.app:main）
    ├── builtin.py           # 内置命令（help / plugins / reload / services / config / health）
    ├── lp_commands.py       # lp 权限管理命令集
    ├── adapter/
    │   └── transports.py    # Transport 协议 + 正向 WS / HTTP 连接件
    ├── kernel/
    │   ├── events.py        # Event 族 / EventBus / EventChannel
    │   ├── commands.py      # CommandRegistry / CommandSpec / CommandContext
    │   ├── permissions.py   # PermissionService 协议与实现
    │   ├── services.py      # ServiceRegistry（跨插件服务）
    │   ├── loader.py        # 三模式插件加载器
    │   ├── plugins.py       # FcatbotPlugin 基类
    │   ├── integration.py   # PluginForge ↔ 总线/命令/服务的协调层
    │   ├── decorators.py    # @on_event
    │   ├── args.py          # 命令参数解析流（CommandArgs）
    │   ├── router.py        # CommandRouter（命令统一入口）
    │   └── stone.py         # PluginConfig / PluginData（声明式 + 持久化）
    ├── frontend/
    │   ├── console.py       # prompt_toolkit 控制台
    │   ├── completer.py     # Tab 补全器
    │   ├── term.py          # 终端宽度工具（wcwidth）
    │   └── theme.py         # 终端着色主题
    ├── tools/
    │   ├── client.py        # APIClient 基座（适配器插件用）
    │   └── new_plugin.py    # 插件脚手架
    ├── utils/
    │   ├── color.py  logformat.py  logger.py  unixargs.py
    └── webui/
        ├── server.py        # WebUI 后端（aiohttp）
        └── static/          # 前端资源（index.html / login.html / css）
```

> **导入路径约定**：框架代码只使用规范路径（`fcatbot.kernel.*` / `fcatbot.frontend.*` 等）；
> 插件作者请统一使用公共 API `from fcatbot import ...`，不要依赖框架内部模块路径（内部模块可能在次版本调整）。

---

## 配置

`config/app.yaml` 关键字段：

```yaml
default_language: zh-CN

console:
  prefix: "/"
  allow_without_prefix: true

plugins:
  dirs: ["plugins"]
  enabled: []           # 白名单；为 null 表示全部启用
  disabled: []          # 黑名单（enabled 为 null 时生效）
  data_dir: "data"

permissions:
  backend: luckperms    # luckperms | allow_all | null
  data_dir: data/permissions
  default_group: default   # 游客兜底组
  console_user: console    # 控制台身份（自动保留 *）

transport:
  mode: forward_ws      # none | forward_ws | http
  forward_ws:
    url: ""
    token: ""
    token_type: Bearer
    reconnect: true
    reconnect_delay: 1.0
    max_reconnect_delay: 30.0
    heartbeat: 30.0
  http:
    host: 127.0.0.1
    port: 8080
    path: /
    api_base_url: ""
    token: ""

webui:
  enabled: true
  host: 127.0.0.1
  port: 8765
  password: ""          # 留空 → 启动时随机生成并打印到本地控制台
  auth_enabled: true
  secret_key: ""        # 留空 → 每次启动随机（重启后旧会话失效）
  session_ttl: 604800
  cookie_secure: false
```

**权限后端说明**：

- `allow_all`：开发模式，全部放行；**生产环境请勿使用**；
- `null`：全部拒绝；
- `luckperms`：接入 [luckperms-python](https://github.com/Fish-LP/LuckPerms-Python)，支持组继承、通配符、上下文、临时权限。首次启动可用 `lp root <用户ID>`（仅控制台）引导根管理员。

---

## 插件开发

### 脚手架

```bash
fcatbot new-plugin my_plugin                       # 包模式（plugins/my_plugin/）
fcatbot new-plugin my_plugin --mode single         # 单文件（plugins/my_plugin.py）
fcatbot new-plugin my_plugin --no-config           # 不生成配置文件
fcatbot new-plugin my_plugin --force               # 覆盖已存在目标
```

常用参数：`-d/--dir`（默认 `plugins`）、`--config-dir`（默认 `config/plugins`）、`--description` / `--author` / `--version`。

### 最小插件（包模式）

```python
# plugins/my_plugin/plugin.py
from fcatbot import Event, FcatbotPlugin, console_command, on_event


class MyPluginPlugin(FcatbotPlugin):
    name = "my_plugin"
    version = "1.0.0"
    description = "我的插件"
    min_app_version = "1.0.0"

    default_config = {"reply": "pong"}

    def init(self, app_config, plugin_config):
        super().init(app_config, plugin_config)
        self._reply = self.config.get("reply", "pong")

    @on_event("raw.*")
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

将插件名加入 `config/app.yaml → plugins.enabled`（或直接使用 `plugins -a` + `enable <name>` 运行时启用），重启或启用后生效。

### 异步生命周期

PluginForge 提供的 `init` / `activate` / `deactivate` 是**同步**的（pluggy 钩子不支持 `await`）。需要异步能力时使用框架提供的四个异步钩子，由 `IntegrationLayer` 编排：

```
进入:  init(同步) → activate(同步) → on_load → [装配: 订阅 + 命令] → on_enable
离开:  on_disable → [取消后台任务] → [拆卸: 退订/注销] → on_unload → deactivate(同步)
```

| 钩子 | 同步 | 已装配 | 典型用途 |
|------|------|--------|----------|
| `init` | ✓ | 服务已注册 | 纯同步配置解析 |
| `activate` | ✓ | 同上 | 极少使用 |
| `on_load` | ✗ | 未订阅 | 打开连接、预热、一次性校验 |
| `on_enable` | ✗ | 已订阅 | 启动后台任务 |
| `on_disable` | ✗ | 仍订阅 | 刷盘、下线通知（**勿启动新任务**） |
| `on_unload` | ✗ | 已退订 | 最终持久化、关闭句柄 |
| `deactivate` | ✓ | 全清完成 | 关闭同步句柄 |

异步钩子内可安全 `await`：权限检查、服务查询、事件发布。同步钩子内**不要** `run_until_complete`（事件循环通常已在运行）。

### 事件订阅：`@on_event` 可叠加

一个方法可叠加多个 `@on_event` 以复用逻辑；每个声明独立生效，各自可携带 `priority` / `once` / `filter`：

```python
@on_event("napcat.message.group")
@on_event("napcat.message.private", priority=40, filter=lambda e: e.data.startswith("!"))
async def on_message(self, event: Event) -> None:
    ...
```

叠加顺序为"离方法最近的装饰器先生效"（Python 装饰器自下而上应用）。插件停用时一并退订。

### 权限检查

| 场景 | 用法 |
|------|------|
| 已知用户 + 可选上下文 | `await self.has_permission(user_id, "use", context={"group_id": "123"})` |
| 从事件推导（业务插件） | `await self.has_permission_for(event, "use")` |
| 事件源（适配器）插件 | 覆盖 `permission_subject(event)` / `permission_context(event)`，将平台语义注入上下文 |

**不要**修改 `has_permission` 的签名——框架与其他插件按 `(user_id, node, *, context=...)` 调用；事件到主体的映射属于适配器插件职责。

### 约定

| 主题 | 约定 |
|------|------|
| 导入 | 只用公共 API `from fcatbot import ...` |
| 权限节点 | 显式 `permission=` 优先；否则派生 `{plugin}:command.{name}`；功能节点建议 `{plugin}.{feature}` |
| 配置 | `config_schema` / `default_config` 声明；读取 `self.config.get(key, default)`；文件 `config/plugins/<name>.yaml` |
| 数据 | 与配置分离：`self.ensure_data_dir()` → `data/plugins/<name>/` |
| 后台任务 | `self.create_task(coro, name=...)`，插件停用时自动取消 |
| 服务 | `provides = {"<name>.api": None}` 导出；`self.get_service("<name>.api")` 获取 |
| 依赖 | `depends_on = ["other_plugin"]`（列表或带版本约束的映射） |

---

## 内置命令

| 命令 | 说明 |
|------|------|
| `help [命令\|插件] [-p N]` | 命令列表 / 详情（分页、分组、宽度感知渲染） |
| `plugins [-a]` | 列出活跃插件（`-a` 含全部已发现） |
| `scan` | 重新扫描插件目录（发现新安装，不激活） |
| `enable / disable <name>` | 运行时启用 / 停用插件 |
| `reload <name>\|all` | 热重载插件 |
| `info <name>` | 查看插件详情 |
| `errors` | 列出加载错误 |
| `services` | 列出已注册服务 |
| `config reload` | 重载配置 |
| `status` | 框架总体状态 |
| `health` | 插件健康状态 |
| `exit` / `quit` | 退出（控制台本地处理） |
| `lp ...` | 权限管理命令集（官方 LuckPerms 结构 + 扩展） |

**`lp` 常用命令**：

- 通用：`lp info` / `lp sync` / `lp check <用户|me> <节点> [key=value ...]` / `lp verbose [on|record|off|upload]` / `lp tree <用户|组> [depth]`
- 用户：`lp user <用户|me> info|permission|parent|meta|promote|demote|showtracks ...`
- 组：`lp group <组> info|permission|parent|meta|setweight|setdisplayname|showtracks|create ...`
- 轨道：`lp track <轨道> info|append|insert|remove|clear|create ...`
- 组 / 轨道管理：`lp creategroup|deletegroup|listgroups`、`lp createtrack|deletetrack|listtracks`
- 扩展：`lp root <用户ID>`（仅控制台）、`lp editor` + `lp applyedits <code>`（Web Editor）、`me` / `self`（聊天来源解析为执行者）

输入 `lp` 查看内置帮助。

---

## 架构概览

### 分层与依赖

```
frontend  ─┐
           ├─→ app ─→ kernel
adapter   ─┘
```

- **`kernel`**：平台无关内核。事件总线、命令系统、权限协议、服务注册、插件基类、加载器。不依赖 `adapter` / `frontend`。
- **`adapter`**：协议适配基座。提供 `Transport` 协议与内置连接件（正向 WS / HTTP），向总线发布 `RawEvent`；协议解析、`Bot` / `Contact` 维护、平台事件发布由适配器插件实现。
- **`frontend`**：控制台、Tab 补全、WebUI、终端渲染。只使用 `app` 公开 API 与总线，不访问应用私有成员。

### 事件总线

- **双轨订阅**：`bus.subscribe(MessageEvent, handler)`（按类型继承匹配）或 `bus.subscribe("raw.*", handler)`（`fnmatch` 通配）。
- **单 worker 串行分发**：优先级降序（同优先级按注册顺序）；`event.cancel()` 中断后续订阅者；队列满时 `await put` 背压。
- **发布语义**：`await publish(event)` 等待分发完成并返回事件本身（可读取监听器修改后的属性）；`publish_nowait(event)` 仅入队；处理器内的嵌套发布自动内联展开，避免单 worker 等待自身死锁。
- **`EventChannel`**：不可变、链式的订阅视图；`parent_scope(scope)` 绑定插件生命周期，作用域关闭时自动取消订阅。

### 命令系统

- `CommandRegistry`：注册 / 查找命令树，返回 `CommandSpec`；子命令以 `parent.sub_command(...)` 声明。
- `CommandRouter`：命令系统对外唯一入口 `handle(raw, context=...)`——分词、路径解析、鉴权、调度、结果文本。
- `CommandContext`：来源感知（控制台 / 聊天），可携带 `user_id` / `group_id` / `metadata`。
- 参数解析：处理器内部用 `CommandArgs`（流式消费 + 静态纯函数，支持 `[true|false]` / `[时长]` 可选位置参数）。

### 权限模型

`PermissionService` 协议：

```python
async def has_permission(user_id, node, *, context=None) -> bool
async def get_groups(user_id) -> list[str]
async def get_meta(user_id, key) -> str | None
```

三种内置实现（`allow_all` / `null` / `luckperms`）；`luckperms` 适配器基于 luckperms-python 支持组继承、通配符、上下文、临时权限。

---

## 测试

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

覆盖：内核事件层（双轨订阅 / 发布语义 / 通道）、真实插件端到端装配、权限适配器与 `lp` 命令、插件脚手架。交互式控制台依赖真实 TTY，需人工验证。

---

## 设计文档

架构说明、ADR（架构决策记录）与各里程碑实施记录在项目**内部维护**，
暂未随本仓库发布。如需了解设计细节，可参考源码中的模块 docstring
（`fcatbot/kernel/events.py`、`fcatbot/kernel/plugins.py`、
`fcatbot/adapter/transports.py` 等处均包含较完整的设计意图与契约说明）。

---

## 许可

MIT

---

## 致谢

- [pluginforge](https://github.com/Fish-LP/pluginforge) —— 插件生命周期管理
- [luckperms-python](https://github.com/Fish-LP/LuckPerms-Python) —— 权限存储与检查
- [aiohttp](https://github.com/aio-libs/aiohttp) —— 异步 HTTP / WebSocket
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) —— 交互式控制台
- [mirai](https://github.com/mamoe/mirai) —— 架构设计参考
