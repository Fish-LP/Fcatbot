"""终端着色主题。ANSI 码仅在最后注入，不影响宽度计算。"""
from __future__ import annotations

import os
from fcatbot.utils import Color


class Theme:
    @classmethod
    def _c(cls, prefix: str, s: str) -> str:
        # 启用时 prefix 与 Reset 都是 ANSI 码；禁用时都是空串，无需额外判断
        return f"{prefix}{s}{Color.Reset}"

    @classmethod
    def title(cls, s: str) -> str:
        return cls._c(Color.Bold + Color.Cyan, s)

    @classmethod
    def plugin(cls, s: str) -> str:
        return cls._c(Color.Bold + Color.Magenta, s)

    @classmethod
    def cmd(cls, s: str) -> str:
        return cls._c(Color.Cyan, s)

    @classmethod
    def alias(cls, s: str) -> str:
        return cls._c(Color.Green, s)

    @classmethod
    def warn(cls, s: str) -> str:
        return cls._c(Color.Yellow, s)

    @classmethod
    def dim(cls, s: str) -> str:
        return cls._c(Color.Gray, s)

    @classmethod
    def init(cls) -> None:
        """根据 NO_COLOR 环境变量和终端能力决定是否启用颜色。"""
        if os.environ.get("NO_COLOR"):
            Color.disable()
            return
        try:
            from prompt_toolkit.output import ColorDepth
            from prompt_toolkit.output.defaults import create_output
            output = create_output()
            enabled = output.get_default_color_depth() != ColorDepth.DEPTH_1_BIT
        except Exception:
            enabled = True

        if enabled:
            Color.init()          # Windows 上顺手打开 VT
        else:
            Color.disable()