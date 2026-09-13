"""插件脚手架测试: 生成形态、覆盖保护、生成物可被三模式加载器发现。"""

from __future__ import annotations

from pathlib import Path

import pytest

from fcatbot.kernel.loader import PluginLoader
from fcatbot.tools.new_plugin import PluginSpec, ScaffoldError, create_plugin, main


def test_scaffold_package_plugin(tmp_path: Path) -> None:
    spec = PluginSpec(name="hello_world", description="示例插件", author="tester")
    written = create_plugin(
        spec,
        plugin_dir=tmp_path / "plugins",
        config_dir=tmp_path / "config" / "plugins",
    )

    package = tmp_path / "plugins" / "hello_world"
    assert (package / "__init__.py").exists()
    assert (package / "plugin.py").exists()
    assert (tmp_path / "config" / "plugins" / "hello_world.yaml").exists()
    assert len(written) == 3

    # 生成物必须是合法 Python，且能被三模式加载器发现
    classes = PluginLoader([tmp_path / "plugins"]).discover()
    assert [cls.__name__ for cls in classes] == ["HelloWorldPlugin"]
    plugin_cls = classes[0]
    assert plugin_cls.name == "hello_world"
    assert plugin_cls.default_config["prefix"] == "!hello_world"
    assert plugin_cls.provides == {"hello_world.api": None}

    # 已注册控制台命令（装饰器标记）
    assert hasattr(plugin_cls.cmd_hello_world, "__console_command__")


def test_scaffold_single_file_and_overwrite_guard(tmp_path: Path) -> None:
    spec = PluginSpec(name="quick", mode="single")
    written = create_plugin(spec, plugin_dir=tmp_path / "plugins", config_dir=None)
    assert written == [tmp_path / "plugins" / "quick.py"]

    with pytest.raises(ScaffoldError):
        create_plugin(spec, plugin_dir=tmp_path / "plugins", config_dir=None)

    create_plugin(spec, plugin_dir=tmp_path / "plugins", config_dir=None, force=True)
    classes = PluginLoader([tmp_path / "plugins"]).discover()
    assert [cls.__name__ for cls in classes] == ["QuickPlugin"]


def test_scaffold_rejects_invalid_spec() -> None:
    with pytest.raises(ScaffoldError):
        PluginSpec(name="Bad-Name").normalized()
    with pytest.raises(ScaffoldError):
        PluginSpec(name="class").normalized()
    with pytest.raises(ScaffoldError):
        PluginSpec(name="ok", mode="zip").normalized()


def test_scaffold_cli(tmp_path: Path) -> None:
    rc = main(
        [
            "cli_demo",
            "--dir",
            str(tmp_path / "plugins"),
            "--no-config",
            "--mode",
            "single",
            "--description",
            "CLI 生成",
        ]
    )
    assert rc == 0
    generated = tmp_path / "plugins" / "cli_demo.py"
    assert generated.exists()
    assert "CliDemoPlugin" in generated.read_text(encoding="utf-8")

    # 名称非法 → 退出码 1
    assert main(["Bad Name"]) == 1
