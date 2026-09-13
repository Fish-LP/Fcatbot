"""插件脚手架: 一键生成符合 Fcatbot 插件规范的骨架。

用法::

    python -m fcatbot.tools.new_plugin my_plugin
    python -m fcatbot.tools.new_plugin my_plugin --mode single --dir plugins
    fcatbot-new-plugin my_plugin --description "我的插件" --author Fish

生成内容（默认包模式）::

    plugins/<name>/
    ├── __init__.py                 # 导出插件类（__plugins__ = [XxxPlugin]）
    └── plugin.py                   # 插件实现（生命周期 + 事件订阅 + 控制台命令）
    config/plugins/<name>.yaml      # 默认配置（--no-config 可关闭）

约定（与框架一致）: 

- 插件名用作 ``FcatbotPlugin.name`` 与权限节点前缀；建议小写下划线命名；
- 单一插件直接使用**公共 API**（``from fcatbot import ...``），不 import 内部模块；
- ``default_config`` 会由宿主在启动时自动落盘为 ``config/plugins/<name>.yaml``；
- 生成的包/单文件均可被 :class:`fcatbot.kernel.loader.PluginLoader` 发现（三模式加载器）。
"""

from __future__ import annotations

import argparse
import keyword
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Iterable

__all__ = ["PluginSpec", "ScaffoldError", "create_plugin", "main"]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_MODES = ("package", "single")

DEFAULT_PLUGIN_DIR = Path("plugins")
DEFAULT_CONFIG_DIR = Path("config") / "plugins"

# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------

_PLUGIN_TEMPLATE = Template(
    '''"""$description"""

from __future__ import annotations

from fcatbot import Event, FcatbotPlugin, console_command, on_event


class $class_name(FcatbotPlugin):
    """$description"""

    name = "$name"
    version = "$version"
    description = "$description"
    author = "$author"
    target_application = "fcatbot"
    min_app_version = "1.0.0"

    # 依赖的插件名（按此顺序加载；被依赖插件失败时本插件不加载）
    depends_on: list[str] = []

    # 配置声明: {键: 类型}；default_config 会在启动时落盘为 config/plugins/$name.yaml
    config_schema = {"greeting": str, "prefix": str}
    default_config = {"greeting": "hello from $name", "prefix": "$prefix"}

    # 提供的服务: 其他插件通过 get_service("$name.api") 获取（值见 FcatbotPlugin.provides）
    provides = {"$name.api": None}

    # ---------- 生命周期 ----------

    def init(self, app_config, plugin_config):
        super().init(app_config, plugin_config)
        self._greeting = self.config.get("greeting", "hello")
        self._prefix = self.config.get("prefix", "$prefix")

    # 异步入口: pluginforge 的 init/activate 是同步的（无法 await），
    # 需要 await 权限/服务/事件时请写在这三个钩子里（由框架编排调用）。
    async def on_load(self) -> None:
        self.log.info("$name loaded")

    async def on_enable(self) -> None:
        self.log.info("$name enabled (prefix=%s)", self._prefix)
        # 常驻后台工作可在作用域内起任务（插件停用时自动取消）: 
        # self.create_task(self._worker(), name="worker")

    async def on_disable(self) -> None:
        self.log.info("$name disabled")

    # ---------- 事件订阅 ----------

    # 事件源（适配器）插件: 覆盖下面两个钩子，把平台语义注入权限上下文: 
    #   def permission_subject(self, event) -> str | None: ...        # 默认 metadata["user_id"]
    #   def permission_context(self, event) -> dict | None: ...       # 默认按 permission_context_keys 白名单

    @on_event("raw.*")
    async def on_raw_frame(self, event: Event) -> None:
        """示例: 观察原始连接帧（``raw.<transport>.<kind>``，载荷未解析）。

        业务插件通常应改为订阅**平台事件**: 内核契约类型（如 ``MessageEvent``）
        或适配器发布的 ``<platform>.<kind>``（如 ``napcat.message.group``）；
        此处用 ``raw.*`` 仅作不依赖任何适配器的通用示例。
        权限节点 ``$name.use``（无权限则静默忽略）。
        """
        data = event.data
        text = (
            str(data.get("raw_message", "")) if isinstance(data, dict) else str(data)
        ).strip()
        if not text.startswith(self._prefix):
            return
        if not await self.has_permission_for(event, "use"):
            return
        payload = text[len(self._prefix):].strip()
        self.log.info("echo: %s", payload or self._greeting)

    # ---------- 控制台命令 ----------

    @console_command(
        "$name",
        help="$description",
        usage="$name [text]",
    )
    def cmd_$name(self, args: list[str]) -> str:
        """权限节点未显式声明时自动派生为 ``$name:command.$name``。"""
        return f"{self._greeting} {' '.join(args)}".strip()

    # ---------- 对外 API（供其他插件/服务调用）----------

    async def greet(self, text: str = "") -> str:
        return f"{self._greeting} {text}".strip()
'''
)

_PACKAGE_INIT_TEMPLATE = Template(
    '''"""$name 插件（包模式）。"""

from __future__ import annotations

from .plugin import $class_name

__plugins__ = [$class_name]
# __all__ = ["$class_name"] # 二选一
'''
)

_SINGLE_TAIL_TEMPLATE = Template(
    """

__plugins__ = [$class_name]
"""
)

_CONFIG_TEMPLATE = Template(
    """# $name 插件配置（由 fcatbot-new-plugin 生成；缺省值见插件 default_config）
greeting: hello from $name
prefix: "$prefix"
"""
)


# ---------------------------------------------------------------------------
# 规格与校验
# ---------------------------------------------------------------------------


class ScaffoldError(Exception):
    """脚手架错误（参数非法 / 目标已存在等）。"""


@dataclass
class PluginSpec:
    """插件生成规格。"""

    name: str
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    mode: str = "package"          # package | single
    prefix: str = ""               # 聊天触发前缀（默认 "!<name>"）

    def normalized(self) -> "PluginSpec":
        """补齐默认值并校验，返回规范化后的新规格。"""
        name = self.name.strip()
        if not _NAME_RE.match(name):
            raise ScaffoldError(
                f"插件名 '{self.name}' 非法: 要求小写字母开头，仅含 [a-z0-9_]"
            )
        if keyword.iskeyword(name):
            raise ScaffoldError(f"插件名 '{name}' 是 Python 关键字，请换一个")
        mode = self.mode.strip().lower()
        if mode not in _MODES:
            raise ScaffoldError(f"未知模式 '{self.mode}': 可选 {', '.join(_MODES)}")
        description = self.description.strip() or f"{name} 插件"
        author = self.author.strip() or "unknown"
        version = self.version.strip() or "1.0.0"
        prefix = self.prefix.strip() or f"!{name}"
        return PluginSpec(
            name=name,
            description=description,
            author=author,
            version=version,
            mode=mode,
            prefix=prefix,
        )

    @property
    def class_name(self) -> str:
        """插件类名: ``my_plugin`` → ``MyPluginPlugin`` 之外的 ``MyPlugin``。"""
        parts = [part for part in self.name.split("_") if part]
        class_name = "".join(part[:1].upper() + part[1:] for part in parts) or "Plugin"
        if not class_name.endswith("Plugin"):
            class_name += "Plugin"
        return class_name

    def context(self) -> dict[str, str]:
        return {
            "name": self.name,
            "class_name": self.class_name,
            "description": self.description,
            "author": self.author,
            "version": self.version,
            "prefix": self.prefix,
        }


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------


def _render_plugin_module(spec: PluginSpec) -> str:
    module = _PLUGIN_TEMPLATE.substitute(spec.context())
    if spec.mode == "single":
        module += _SINGLE_TAIL_TEMPLATE.substitute(spec.context())
    return module


def _targets(spec: PluginSpec, plugin_dir: Path) -> Iterable[Path]:
    if spec.mode == "single":
        yield plugin_dir / f"{spec.name}.py"
        return
    yield plugin_dir / spec.name
    yield plugin_dir / spec.name / "__init__.py"
    yield plugin_dir / spec.name / "plugin.py"


def create_plugin(
    spec: PluginSpec,
    *,
    plugin_dir: Path | str = DEFAULT_PLUGIN_DIR,
    config_dir: Path | str | None = DEFAULT_CONFIG_DIR,
    force: bool = False,
) -> list[Path]:
    """按 ``spec`` 生成插件骨架，返回写入的文件路径列表。

    Args:
        spec: 插件规格（会先做校验与默认值补齐）。
        plugin_dir: 插件目录（包模式生成子目录，单文件模式生成 ``<name>.py``）。
        config_dir: 配置目录；None 表示不生成配置文件。
        force: 目标已存在时是否覆盖。

    Raises:
        ScaffoldError: 名称/模式非法，或目标已存在且未指定 ``force``。
    """
    spec = spec.normalized()
    plugin_dir = Path(plugin_dir)
    config_dir_path = Path(config_dir) if config_dir is not None else None

    existing = [path for path in _targets(spec, plugin_dir) if path.exists()]
    if existing and not force:
        shown = ", ".join(str(path) for path in existing)
        raise ScaffoldError(f"目标已存在: {shown}（使用 --force 覆盖）")

    written: list[Path] = []
    plugin_dir.mkdir(parents=True, exist_ok=True)

    if spec.mode == "package":
        package_dir = plugin_dir / spec.name
        package_dir.mkdir(parents=True, exist_ok=True)
        plugin_file = package_dir / "plugin.py"
        plugin_file.write_text(_render_plugin_module(spec), encoding="utf-8")
        written.append(plugin_file)
        init_file = package_dir / "__init__.py"
        init_file.write_text(
            _PACKAGE_INIT_TEMPLATE.substitute(spec.context()), encoding="utf-8"
        )
        written.append(init_file)
    else:
        single_file = plugin_dir / f"{spec.name}.py"
        single_file.write_text(_render_plugin_module(spec), encoding="utf-8")
        written.append(single_file)

    if config_dir_path is not None:
        config_dir_path.mkdir(parents=True, exist_ok=True)
        config_file = config_dir_path / f"{spec.name}.yaml"
        config_file.write_text(_CONFIG_TEMPLATE.substitute(spec.context()), encoding="utf-8")
        written.append(config_file)

    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fcatbot-new-plugin",
        description="生成 Fcatbot 插件骨架（包 / 单文件两种形态）",
    )
    parser.add_argument("name", help="插件名（小写字母开头，如 my_plugin）")
    parser.add_argument(
        "-d", "--dir", default=str(DEFAULT_PLUGIN_DIR), help="插件目录（默认 plugins）"
    )
    parser.add_argument(
        "--config-dir",
        default=str(DEFAULT_CONFIG_DIR),
        help="配置目录（默认 config/plugins；--no-config 时忽略）",
    )
    parser.add_argument(
        "--no-config", action="store_true", help="不生成 config/plugins/<name>.yaml"
    )
    parser.add_argument(
        "--mode", choices=_MODES, default="package", help="生成形态（默认 package）"
    )
    parser.add_argument("--description", default="", help="插件描述")
    parser.add_argument("--author", default="", help="作者")
    parser.add_argument("--version", default="1.0.0", help="插件版本（默认 1.0.0）")
    parser.add_argument("--prefix", default="", help="聊天触发前缀（默认 !<name>）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的目标")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。返回退出码（0 成功 / 1 失败）。"""
    args = _build_parser().parse_args(argv)
    spec = PluginSpec(
        name=args.name,
        description=args.description,
        author=args.author,
        version=args.version,
        mode=args.mode,
        prefix=args.prefix,
    )
    try:
        written = create_plugin(
            spec,
            plugin_dir=Path(args.dir),
            config_dir=None if args.no_config else Path(args.config_dir),
            force=args.force,
        )
    except ScaffoldError as exc:
        print(f"[new-plugin] {exc}", file=sys.stderr)
        return 1

    normalized = spec.normalized()
    print(f"[new-plugin] 已生成插件 '{normalized.name}'（模式: {normalized.mode}）: ")
    for path in written:
        print(f"  + {path}")
    print("\n下一步: ")
    print(f"  1. 在 config/app.yaml 的 plugins.enabled 中加入 '{normalized.name}'")
    print(f"  2. 启动宿主: python main.py")
    print(f"  3. 控制台执行 '{normalized.name}' 验证命令；聊天触发前缀 '{normalized.prefix}'")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI 自测
    raise SystemExit(main())
