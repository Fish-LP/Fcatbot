# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-06-22 17:03:21
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-22 19:15:54
# @Description  : 终端颜色
# @Copyright (c) 2025 by Fish.zh@outlook.com, Fcatbot使用许可协议
# -------------------------

import ctypes
from ctypes import wintypes
import sys


def is_ansi_supported() -> bool:
    """
    检查系统是否支持 ANSI 转义序列。
    """
    if not sys.platform.startswith("win"):
        # 非 Windows 系统通常支持 ANSI 转义序列
        return True

    # 检查 Windows 版本
    is_windows_10_or_higher = False
    try:
        # 获取 Windows 版本信息
        version_info = sys.getwindowsversion()
        major_version = version_info[0]

        # Windows 10 (major version 10) 或更高版本
        if major_version >= 10:
            is_windows_10_or_higher = True
    except AttributeError:
        # 如果无法获取版本信息，假设不支持
        return False

    # 检查控制台是否支持虚拟终端处理
    kernel32 = ctypes.windll.kernel32
    stdout_handle = kernel32.GetStdHandle(-11)
    if stdout_handle == wintypes.HANDLE(-1).value:
        return False

    # 获取当前控制台模式
    console_mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(stdout_handle, ctypes.byref(console_mode)):
        return False

    # 检查是否支持虚拟终端处理
    return (console_mode.value & 0x0004) != 0 or is_windows_10_or_higher


def set_console_mode(mode: int = 7) -> bool:
    """
    设置控制台输出模式。
    尝试启用控制台的 ANSI 转义序列支持。
    """
    try:
        kernel32 = ctypes.windll.kernel32
        # 获取标准输出句柄
        stdout_handle = kernel32.GetStdHandle(-11)
        if stdout_handle == wintypes.HANDLE(-1).value:
            return False

        # 设置控制台模式
        if not kernel32.SetConsoleMode(stdout_handle, mode):
            return False
    except Exception:
        return False
    return True

set_console_mode()

class Color:
    """
    提供终端颜色和样式配置功能。

    此类封装了 ANSI 转义序列，用于在支持的终端中显示颜色和样式。
    支持前景色、背景色、样式设置以及 RGB 颜色和 256 色模式。

    Attributes:
        _COLOR (bool): 表示是否启用颜色输出，默认为 True。

    Example:
        >>> Color._COLOR = is_ansi_supported()
        >>> print(f"{Color.RED}红色文本{Color.RESET}")
        # 输出红色文本，后跟重置代码
    """

    _COLOR = is_ansi_supported()  # 终端是否支持 ANSI 颜色

    def __getattribute__(self, name: str) -> str:
        """
        重写属性访问方法，根据 _COLOR 状态返回 ANSI 代码或空字符串。

        Args:
            name (str): 要访问的属性名称。

        Returns:
            str: 如果 _COLOR 为 True，返回对应的 ANSI 代码；否则返回空字符串。
        """
        if self._COLOR:
            return super().__getattribute__(name)
        else:
            return ""

    # 前景颜色
    BLACK = "\033[30m"
    '''# 前景-黑'''
    RED = "\033[31m"
    '''# 前景-红'''
    GREEN = "\033[32m"
    '''# 前景-绿'''
    YELLOW = "\033[33m"
    '''# 前景-黄'''
    BLUE = "\033[34m"
    '''# 前景-蓝'''
    MAGENTA = "\033[35m"
    '''# 前景-品红'''
    CYAN = "\033[36m"
    '''# 前景-青'''
    WHITE = "\033[37m"
    '''# 前景-白'''
    GRAY = "\033[90m"
    '''# 前景-灰'''

    # 背景颜色
    BG_BLACK = "\033[40m"
    '''# 背景-黑'''
    BG_RED = "\033[41m"
    '''# 背景-红
    BG_GREEN = "\033[42m"
    '''# 背景-绿'''
    BG_YELLOW = "\033[43m"
    '''# 背景-黄'''
    BG_BLUE = "\033[44m"
    '''# 背景-蓝'''
    BG_MAGENTA = "\033[45m"
    '''# 背景-品红'''
    BG_CYAN = "\033[46m"
    '''# 背景-青'''
    BG_WHITE = "\033[47m"
    '''# 背景-白'''
    BG_GRAY = "\033[100m"
    '''# 背景-灰'''

    # 样式
    RESET = "\033[0m"
    '''# 重置所有颜色和样式'''
    BOLD = "\033[1m"
    '''# 加粗'''
    UNDERLINE = "\033[4m"
    '''# 下划线'''
    REVERSE = "\033[7m"
    '''# 反转
    - 前景色和背景色互换'''
    ITALIC = "\033[3m"
    '''# 斜体'''
    BLINK = "\033[5m"
    '''# 闪烁'''
    STRIKE = "\033[9m"
    '''# 删除线'''

    @classmethod
    def from_rgb(cls, r: int, g: int, b: int, background: bool = False) -> str:
        """
        从 RGB 颜色代码创建颜色代码。

        Args:
            r (int): 红色分量 (0-255)
            g (int): 绿色分量 (0-255)
            b (int): 蓝色分量 (0-255)
            background (bool): 是否是背景颜色，默认为前景颜色

        Returns:
            str: 对应的 ANSI 颜色代码，或空字符串（如果颜色输出被禁用）

        Raises:
            ValueError: 如果 r、g 或 b 的值超出范围 0-255

        Example:
            >>> rgb_color = Color.from_rgb(255, 0, 0)
            >>> print(f"{rgb_color}纯红文本{Color.RESET}")
        """
        if not cls._COLOR:
            return ""
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("RGB 值超出范围 0-255")

        if background:
            return f"\033[48;2;{r};{g};{b}m"
        else:
            return f"\033[38;2;{r};{g};{b}m"

    @classmethod
    def rgb(cls, r: int, g: int, b: int) -> str:
        """
        创建前景 RGB 颜色。

        Args:
            r (int): 红色分量 (0-255)
            g (int): 绿色分量 (0-255)
            b (int): 蓝色分量 (0-255)

        Returns:
            str: 对应的前景 ANSI 颜色代码

        Example:
            >>> color = Color.rgb(0, 255, 0)
            >>> print(f"{color}绿色文本{Color.RESET}")
        """
        return cls.from_rgb(r, g, b, background=False)

    @classmethod
    def bg_rgb(cls, r: int, g: int, b: int) -> str:
        """
        创建背景 RGB 颜色。

        Args:
            r (int): 红色分量 (0-255)
            g (int): 绿色分量 (0-255)
            b (int): 蓝色分量 (0-255)

        Returns:
            str: 对应的背景 ANSI 颜色代码

        Example:
            >>> bg_color = Color.bg_rgb(0, 0, 255)
            >>> print(f"{bg_color}{Color.WHITE}蓝色背景文本{Color.RESET}")
        """
        return cls.from_rgb(r, g, b, background=True)

    @classmethod
    def color256(cls, color_code: int, background: bool = False) -> str:
        """
        使用 256 色模式创建颜色。

        Args:
            color_code (int): 256 色中的颜色编号 (0-255)
            background (bool): 是否是背景颜色，默认为前景颜色

        Returns:
            str: 对应的 ANSI 颜色代码，或空字符串（如果颜色输出被禁用）

        Raises:
            ValueError: 如果 color_code 的值超出范围 0-255

        Example:
            >>> color = Color.color256(196)  # 256 色中的红色
            >>> print(f"{color}256 色文本{Color.RESET}")
        """
        if not cls._COLOR:
            return ""
        if not 0 <= color_code <= 255:
            raise ValueError("颜色代码超出范围 0-255")

        if background:
            return f"\033[48;5;{color_code}m"
        else:
            return f"\033[38;5;{color_code}m"

    @classmethod
    def rgb256(cls, r: int, g: int, b: int, background: bool = False) -> str:
        """
        将 RGB 颜色转换为最接近的 256 色。

        使用特定算法将 RGB 值映射到 256 色模式中的颜色编号。

        Args:
            r (int): 红色分量 (0-255)
            g (int): 绿色分量 (0-255)
            b (int): 蓝色分量 (0-255)
            background (bool): 是否是背景颜色，默认为前景颜色

        Returns:
            str: 对应的 ANSI 256 色代码，或空字符串（如果颜色输出被禁用）

        Raises:
            ValueError: 如果 r、g 或 b 的值超出范围 0-255

        Example:
            >>> color = Color.rgb256(128, 0, 128)  # 紫色
            >>> print(f"{color}256 色近似紫色文本{Color.RESET}")
        """
        if not cls._COLOR:
            return ""
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError("RGB 值超出范围 0-255")

        # 将 RGB 转换为 256 色
        def rgb_to_256(r, g, b):
            if r == g == b:  # 灰度
                if r < 8:
                    return 16
                if r > 248:
                    return 231
                return round((r - 8) / 247 * 24) + 232
            return (
                16
                + (36 * round(r / 255 * 5))
                + (6 * round(g / 255 * 5))
                + round(b / 255 * 5)
            )

        color_code = rgb_to_256(r, g, b)
        return cls.color256(color_code, background)