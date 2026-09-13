# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-06-22 17:03:21
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-22 19:15:54
# @Description  : 终端颜色 (Modernized + PascalCase)
# @Copyright (c) 2025 by Fish.zh@outlook.com, MIT 使用许可协议
# -------------------------

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple, Union


def _is_ansi_supported() -> bool:
    if not sys.platform.startswith("win"):
        return True
    try:
        version_info = sys.getwindowsversion()
        if version_info.major < 10:
            return False
    except AttributeError:
        return False

    kernel32 = ctypes.windll.kernel32
    stdout_handle = kernel32.GetStdHandle(-11)
    if stdout_handle == wintypes.HANDLE(-1).value:
        return False

    console_mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(stdout_handle, ctypes.byref(console_mode)):
        return False

    return (console_mode.value & 0x0004) != 0


def _enable_vt_mode() -> bool:
    if not sys.platform.startswith("win"):
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        stdout_handle = kernel32.GetStdHandle(-11)
        if stdout_handle == wintypes.HANDLE(-1).value:
            return False

        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode)):
            return False

        new_mode = mode.value | 0x0004
        return bool(kernel32.SetConsoleMode(stdout_handle, new_mode))
    except Exception:
        return False


class _AnsiCode:
    __slots__ = ("_code",)

    def __init__(self, code: str) -> None:
        self._code = code

    def __get__(self, instance: Optional[object], owner: type) -> str:
        if owner._ColorEnabled:
            return self._code
        return ""

    def __set__(self, instance: object, value: str) -> None:
        raise AttributeError("ANSI 颜色码不可修改")


class _ColorMeta(type):
    def __new__(mcs, name: str, bases: Tuple[type, ...], namespace: Dict[str, Any]):
        cls = super().__new__(mcs, name, bases, namespace)
        if not hasattr(cls, "_ColorEnabled"):
            cls._ColorEnabled = _is_ansi_supported()
        return cls


class Color(metaclass=_ColorMeta):
    _ColorEnabled: bool = _is_ansi_supported()

    # 前景颜色
    Black = _AnsiCode("\033[30m")
    Red = _AnsiCode("\033[31m")
    Green = _AnsiCode("\033[32m")
    Yellow = _AnsiCode("\033[33m")
    Blue = _AnsiCode("\033[34m")
    Magenta = _AnsiCode("\033[35m")
    Cyan = _AnsiCode("\033[36m")
    White = _AnsiCode("\033[37m")
    Gray = _AnsiCode("\033[90m")

    # 背景颜色
    BgBlack = _AnsiCode("\033[40m")
    BgRed = _AnsiCode("\033[41m")
    BgGreen = _AnsiCode("\033[42m")
    BgYellow = _AnsiCode("\033[43m")
    BgBlue = _AnsiCode("\033[44m")
    BgMagenta = _AnsiCode("\033[45m")
    BgCyan = _AnsiCode("\033[46m")
    BgWhite = _AnsiCode("\033[47m")
    BgGray = _AnsiCode("\033[100m")

    # 样式
    Reset = _AnsiCode("\033[0m")
    Bold = _AnsiCode("\033[1m")
    Underline = _AnsiCode("\033[4m")
    Reverse = _AnsiCode("\033[7m")
    Italic = _AnsiCode("\033[3m")
    Blink = _AnsiCode("\033[5m")
    Strike = _AnsiCode("\033[9m")

    @classmethod
    def init(cls, force: bool = False) -> bool:
        if force or not cls._ColorEnabled:
            if sys.platform.startswith("win"):
                _enable_vt_mode()
            cls._ColorEnabled = _is_ansi_supported()
        return cls._ColorEnabled

    @classmethod
    def disable(cls) -> None:
        cls._ColorEnabled = False

    @classmethod
    def enable(cls) -> None:
        cls._ColorEnabled = True

    def __init__(self, *codes: str) -> None:
        self._codes = "".join(codes)
        self._original_color_enabled = self.__class__._ColorEnabled

    def __enter__(self) -> Color:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._original_color_enabled:
            print(self.Reset, end="")

    def __str__(self) -> str:
        return self._codes if self._ColorEnabled else ""

    def __add__(self, other: Union[str, Color]) -> str:
        if isinstance(other, Color):
            return str(self) + str(other)
        return str(self) + other

    def __radd__(self, other: str) -> str:
        return other + str(self)

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int, background: bool = False) -> str:
        if not cls._ColorEnabled:
            return ""
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("RGB 值必须在 0-255 范围内")
        code = 48 if background else 38
        return f"\033[{code};2;{r};{g};{b}m"

    @classmethod
    def rgb(cls, r: int, g: int, b: int) -> str:
        return cls.from_rgb(r, g, b, background=False)

    @classmethod
    def bg_rgb(cls, r: int, g: int, b: int) -> str:
        return cls.from_rgb(r, g, b, background=True)

    @classmethod
    @lru_cache(maxsize=256)
    def _rgb_to_256(cls, r: int, g: int, b: int) -> int:
        if r == g == b:
            if r < 8:
                return 16
            if r > 248:
                return 231
            return round(((r - 8) / 247) * 24) + 232
        return (
            16 + 36 * round(r / 255 * 5) + 6 * round(g / 255 * 5) + round(b / 255 * 5)
        )

    @classmethod
    def color256(cls, color_code: int, background: bool = False) -> str:
        if not cls._ColorEnabled:
            return ""
        if not 0 <= color_code <= 255:
            raise ValueError("颜色代码必须在 0-255 范围内")
        code = 48 if background else 38
        return f"\033[{code};5;{color_code}m"

    @classmethod
    def rgb256(cls, r: int, g: int, b: int, background: bool = False) -> str:
        if not cls._ColorEnabled:
            return ""
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("RGB 值必须在 0-255 范围内")
        color_code = cls._rgb_to_256(r, g, b)
        return cls.color256(color_code, background)

    @classmethod
    def print(cls, *args, color: str = "", sep: str = " ", end: str = "\n") -> None:
        print(f"{color}{sep.join(args)}{cls.Reset}", end=end)
