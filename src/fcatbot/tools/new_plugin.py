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

from fcatbot import __api_version__, __version__

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

from typing import Any

from fcatbot import Event, FcatbotPlugin, console_command, on_event


class $class_name(FcatbotPlugin):
    """$description"""

    # ---- 元信息（由 PluginLoader 在发现阶段读取）----
    name = "$name"
    version = "$version"
    description = "$description"
    author = "$author"
    # 当前框架版本限制
    api_version = "$api_version"
    min_app_version = "$app_version"

    # ---- 依赖 ----
    # 按此顺序加载；被依赖插件失败时本插件不加载。
    depends_on: list[str] = []

    # ---- 配置 ----
    # 宿主启动时若 config/plugins/$name.yaml 缺失，会用 default_config 自动落盘；
    # config_schema 用于启动前进行类型检查
    config_schema = {"greeting": str, "prefix": str}
    default_config = {"greeting": "hello from $name", "prefix": "$prefix"}

    # ---- 对外服务 ----
    # 值语义: None=插件实例自身 / "attr"=实例属性名 / 类型 / 实例。
    # 其他插件用 get_service("$name.api") 获取。
    provides = {"$name.api": None}

    # ==================== 生命周期（异步入口）====================
    #
    # 调用顺序（由 IntegrationLayer 编排）:
    #   init(同步) → activate(同步) → on_load → [装配: 订阅 + 命令] → on_enable
    #   停用: on_disable → [取消后台任务] → [拆卸: 退订/注销] → on_unload → deactivate(同步)
    #
    # 这四个钩子可安全 await 权限检查 / 服务查询 / 事件发布。

    def init(self, app_config: dict[str, Any], plugin_config: dict[str, Any]) -> None:
        super().init(app_config, plugin_config)
        self._greeting: str = self.config.get("greeting", "hello")
        self._prefix: str = self.config.get("prefix", "$prefix")

    async def on_load(self) -> None:
        """已加载并注入配置；此时尚未订阅事件 / 注册命令。"""
        self.log.info("$name loaded")

    async def on_enable(self) -> None:
        """已订阅事件并注册命令，插件正式生效；适合启动后台任务。"""
        self.log.info("$name enabled (prefix=%s)", self._prefix)
        # 常驻后台任务（插件停用时自动取消）:
        # self.create_task(self._worker(), name="worker")

    async def on_disable(self) -> None:
        """即将退订（还在接收事件）；先收敛内部状态。后台任务随后由框架统一取消。"""
        self.log.info("$name disabled")

    async def on_unload(self) -> None:
        """已退订并注销服务；释放外部资源。"""

    # ==================== 事件订阅 ====================
    #
    # 事件源（适配器）插件可覆盖 permission_subject / permission_context，
    # 把平台语义注入权限上下文；业务插件一般无需关心。

    @on_event("raw.*")
    async def on_raw_frame(self, event: Event) -> None:
        """示例: 观察原始连接帧 ``raw.<transport>.<kind>``（载荷未解析）。

        业务插件通常应改为订阅**平台事件**（如 ``napcat.message.group``）
        或内核契约类型（如 ``MessageEvent``）；这里用 ``raw.*`` 只是为了让
        生成的骨架不依赖任何具体适配器。权限节点 ``$name.use``。
        """
        if not isinstance(event.data, dict):
            return
        text = str(event.data.get("raw_message", "")).strip()
        if not text.startswith(self._prefix):
            return
        if not await self.has_permission_for(event, "use"):
            return
        payload = text[len(self._prefix):].strip()
        self.log.info("echo: %s", payload or self._greeting)

    # ==================== 控制台命令 ====================

    @console_command(
        "$name",
        help="$description",
        usage="$name [text]",
    )
    def cmd_$name(self, args: list[str]) -> str:
        """未显式声明权限节点时自动派生为 ``$name:command.$name``。"""
        return f"{self._greeting} {' '.join(args)}".strip()

    # ==================== 对外 API（供其他插件 / 服务调用）====================

    async def greet(self, text: str = "") -> str:
        return f"{self._greeting} {text}".strip()

    # ==================== 健康检查（可选）====================

    def health(self) -> dict[str, Any]:
        return {"status": "ok"}
'''
)

_PACKAGE_INIT_TEMPLATE = Template(
    '''"""$name 插件（包模式）。"""

from __future__ import annotations

from .plugin import $class_name

# PluginLoader 通过 __plugins__ 发现插件类。
__plugins__ = [$class_name]
'''
)

_SINGLE_TAIL_TEMPLATE = Template(
    """

__plugins__ = [$class_name]
"""
)

_CONFIG_TEMPLATE = Template(
    """# $name 插件配置
# 宿主启动时若本文件缺失，会用插件 default_config 自动生成；
# 此处填写的值会覆盖 default_config 中的同名键。
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
    mode: str = "package"  # package | single
    prefix: str = ""  # 聊天触发前缀（默认 "!<name>"）
    app_version = __version__
    api_version = __api_version__

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
        return PluginSpec(
            name=name,
            description=self.description.strip() or f"{name} 插件",
            author=self.author.strip() or "unknown",
            version=self.version.strip() or "1.0.0",
            mode=mode,
            prefix=self.prefix.strip() or f"!{name}",
        )

    @property
    def class_name(self) -> str:
        """插件类名: ``my_plugin`` → ``MyPlugin``；``echo`` → ``EchoPlugin``。"""
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
            "app_version": self.app_version,
            "api_version": self.api_version,
        }


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------


def _render_plugin_module(spec: PluginSpec) -> str:
    module = _PLUGIN_TEMPLATE.substitute(spec.context())
    if spec.mode == "single":
        module += _SINGLE_TAIL_TEMPLATE.substitute(spec.context())
    return module


def _targets(
    spec: PluginSpec,
    plugin_dir: Path,
    config_dir: Path | None,
) -> Iterable[Path]:
    """列出本次生成会涉及的所有路径（用于存在性判断）。"""
    if spec.mode == "single":
        yield plugin_dir / f"{spec.name}.py"
        # 同名包目录若已存在，会与单文件插件产生加载歧义。
        yield plugin_dir / spec.name
    else:
        yield plugin_dir / spec.name
        yield plugin_dir / spec.name / "__init__.py"
        yield plugin_dir / spec.name / "plugin.py"
    if config_dir is not None:
        yield config_dir / f"{spec.name}.yaml"


def create_plugin(
    spec: PluginSpec,
    *,
    plugin_dir: Path | str = DEFAULT_PLUGIN_DIR,
    config_dir: Path | str | None = DEFAULT_CONFIG_DIR,
    force: bool = False,
) -> list[Path]:
    """按 ``spec`` 生成插件骨架，返回写入的文件路径列表。

    Args:
        spec: 插件规格（会先做校验与默认值补齐；传入已规范化对象亦安全）。
        plugin_dir: 插件目录（包模式生成子目录，单文件模式生成 ``<name>.py``）。
        config_dir: 配置目录；None 表示不生成配置文件。
        force: 目标已存在时是否覆盖。

    Raises:
        ScaffoldError: 名称/模式非法，或目标已存在且未指定 ``force``。
    """
    spec = spec.normalized()
    plugin_dir = Path(plugin_dir)
    config_dir_path = Path(config_dir) if config_dir is not None else None

    existing = [
        path for path in _targets(spec, plugin_dir, config_dir_path) if path.exists()
    ]
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
        config_file.write_text(
            _CONFIG_TEMPLATE.substitute(spec.context()), encoding="utf-8"
        )
        written.append(config_file)

    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def add_cli_arguments(parser: argparse.ArgumentParser) -> None:
    """向 ``parser`` 注册 new-plugin 子命令的全部参数。

    供统一 CLI（:mod:`fcatbot.app`）与独立入口 ``fcatbot-new-plugin`` 复用。
    """
    parser.add_argument("name", help="插件名（小写字母开头，如 my_plugin）")
    parser.add_argument(
        "-d",
        "--dir",
        default=str(DEFAULT_PLUGIN_DIR),
        help=f"插件目录（默认 {DEFAULT_PLUGIN_DIR}）",
    )
    parser.add_argument(
        "--config-dir",
        default=str(DEFAULT_CONFIG_DIR),
        help=f"配置目录（默认 {DEFAULT_CONFIG_DIR}；--no-config 时忽略）",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="不生成 config/plugins/<name>.yaml",
    )
    parser.add_argument(
        "--mode",
        choices=_MODES,
        default="package",
        help="生成形态（默认 package）",
    )
    parser.add_argument("--description", default="", help="插件描述")
    parser.add_argument("--author", default="", help="作者")
    parser.add_argument("--version", default="1.0.0", help="插件版本（默认 1.0.0）")
    parser.add_argument("--prefix", default="", help="聊天触发前缀（默认 !<name>）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的目标")


def run_cli(args: argparse.Namespace) -> int:
    """执行生成，返回退出码（0 成功 / 1 失败）。

    Args:
        args: 由 :func:`add_cli_arguments` 注册参数后解析得到的命名空间。
    """
    raw_spec = PluginSpec(
        name=args.name,
        description=args.description,
        author=args.author,
        version=args.version,
        mode=args.mode,
        prefix=args.prefix,
    )
    try:
        spec = raw_spec.normalized()
        written = create_plugin(
            spec,
            plugin_dir=Path(args.dir),
            config_dir=None if args.no_config else Path(args.config_dir),
            force=args.force,
        )
    except ScaffoldError as exc:
        print(f"[new-plugin] {exc}", file=sys.stderr)
        return 1

    print(f"[new-plugin] 已生成插件 '{spec.name}'（模式: {spec.mode}）:")
    for path in written:
        print(f"  + {path}")
    print("\n下一步:")
    print(f"  1. 在 config/app.yaml 的 plugins.enabled 中加入 '{spec.name}'")
    print("  2. 启动宿主: fcatbot")
    print(f"  3. 控制台执行 '{spec.name}' 验证命令；聊天触发前缀 '{spec.prefix}'")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fcatbot-new-plugin",
        description="生成 Fcatbot 插件骨架（包 / 单文件两种形态）",
    )
    add_cli_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    """独立 CLI 入口（``fcatbot-new-plugin``）。返回退出码。"""
    args = _build_parser().parse_args(argv)
    return run_cli(args)


if __name__ == "__main__":  # pragma: no cover - CLI 自测
    raise SystemExit(main())
