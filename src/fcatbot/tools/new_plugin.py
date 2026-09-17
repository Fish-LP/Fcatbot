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

模板文件
--------

本工具使用的模板**不内嵌在代码里**，而是独立存放在::

    fcatbot/tools/templates/plugin/
    ├── plugin.py.tmpl          # 插件主模块
    ├── package_init.py.tmpl    # 包模式 __init__.py
    ├── single_tail.py.tmpl     # 单文件模式追加的 __plugins__ 声明
    └── config.yaml.tmpl        # 默认 config/plugins/<name>.yaml

模板语法为 :class:`string.Template`（占位符形如 ``$name``）。渲染上下文由
:meth:`PluginSpec.context` 提供，键集固定:

    name / class_name / description / author / version /
    prefix / app_version / api_version

这样模板文件可以直接被文本编辑器 / 翻译工具处理，也便于下游 fork 做本地化。

    打包注意：请把 ``templates/`` 目录纳入 package_data（setuptools 的
    ``package_data``、hatch 的 ``include``、poetry 的 ``include``），否则
    安装后找不到模板会抛 :class:`ScaffoldError`。

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
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import Iterable

from fcatbot import __api_version__, __version__

__all__ = ["PluginSpec", "ScaffoldError", "create_plugin", "main"]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*\Z", re.ASCII | re.IGNORECASE)
_MODES = ("package", "single")

DEFAULT_PLUGIN_DIR = Path("plugins")
DEFAULT_CONFIG_DIR = Path("config") / "plugins"

# 模板目录：与代码同级的 ``templates/plugin/``。
# 使用 ``resolve()`` 以避免在相对路径 / 符号链接场景下出现意外。
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "plugin"

# 逻辑名 → 模板文件名。
# 集中在一处，便于后续新增模板（如 tests / README）时统一管理。
_TEMPLATE_FILES: dict[str, str] = {
    "plugin": "plugin.py.tmpl",
    "package_init": "package_init.py.tmpl",
    "single_tail": "single_tail.py.tmpl",
    "config": "config.yaml.tmpl",
}


# ---------------------------------------------------------------------------
# 模板加载
# ---------------------------------------------------------------------------


class ScaffoldError(Exception):
    """脚手架错误（参数非法 / 目标已存在 / 模板缺失等）。"""


@lru_cache(maxsize=None)
def _load_template(name: str) -> Template:
    """按逻辑名加载模板（带缓存）。

    Args:
        name: ``_TEMPLATE_FILES`` 中的键，如 ``"plugin"``。

    Raises:
        ScaffoldError: 逻辑名未知，或磁盘上找不到对应文件。

    Note:
        用 :func:`functools.lru_cache` 缓存已解析的 :class:`Template` 对象——
        模板内容在进程生命周期内不会改变。读取失败不会写入缓存，
        因此重复失败每次都会重新尝试读取磁盘（便于用户即时修复）。
    """
    filename = _TEMPLATE_FILES.get(name)
    if filename is None:
        raise ScaffoldError(f"未知模板: {name!r}")
    path = _TEMPLATE_DIR / filename
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ScaffoldError(
            f"模板文件缺失: {path}\n"
            f"  · 若从源码运行，请确认 {_TEMPLATE_DIR} 存在；\n"
            f"  · 若从已安装的包运行，请确认打包时包含 templates/ 目录。"
        ) from exc
    return Template(text)


def _clear_template_cache() -> None:
    """清空模板缓存（供测试 / 热更新调用）。"""
    _load_template.cache_clear()


# ---------------------------------------------------------------------------
# 规格与校验
# ---------------------------------------------------------------------------


@dataclass
class PluginSpec:
    """插件生成规格。"""

    name: str
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    mode: str = "package"  # package | single
    prefix: str = ""  # 聊天触发前缀（默认 "!<name>"）
    # 类属性（非 dataclass 字段）：模板渲染上下文用，跟随当前框架版本。
    app_version = __version__
    api_version = __api_version__

    def normalized(self) -> "PluginSpec":
        """补齐默认值并校验，返回规范化后的新规格。"""
        name = self.name.strip()
        if not _NAME_RE.match(name):
            raise ScaffoldError(f"插件名 '{self.name}' 非法: {_NAME_RE}")
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
        """模板渲染上下文——与 ``templates/plugin/*.tmpl`` 中的占位符一一对应。"""
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
    """渲染插件主模块；单文件模式额外追加 ``__plugins__`` 声明。"""
    module = _load_template("plugin").substitute(spec.context())
    if spec.mode == "single":
        module += _load_template("single_tail").substitute(spec.context())
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
        ScaffoldError: 名称/模式非法，目标已存在且未指定 ``force``，或模板缺失。
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
            _load_template("package_init").substitute(spec.context()),
            encoding="utf-8",
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
            _load_template("config").substitute(spec.context()),
            encoding="utf-8",
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
