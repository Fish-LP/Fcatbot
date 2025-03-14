# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:41:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-14 20:38:43
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
import logging
import os
import sys
import warnings
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from tqdm import tqdm as tqdm_original

import ctypes
from ctypes import wintypes

def is_ansi_supported():
    """
    检查系统是否支持 ANSI 转义序列。

    return:
        bool: 如果系统支持 ANSI 转义序列返回 True，否则返回 False。
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
        build_number = version_info[3]

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

def set_console_mode(mode=7):
    """
    设置控制台输出模式。

    Args
        mode (int): 控制台模式标志，默认为7（ENABLE_PROCESSED_OUTPUT | ENABLE_WRAP_AT_EOL_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING）。

    return:
        bool: 如果操作成功返回True，否则返回False。
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

class Color:
    """
    用于在终端中显示颜色和样式。

    包含以下功能:
    - 前景: 设置颜色
    - 背景: 设置背景颜色
    - 样式: 设置样式（如加粗、下划线、反转）
    - RESET: 重置所有颜色和样式
    - from_rgb: 从 RGB 代码创建颜色
    """
    _COLOR = True  # 假设终端支持 ANSI 颜色，实际使用时可能需要检测

    def __getattribute__(self, name):
        if self._COLOR:
            return super().__getattribute__(name)
        else:
            return ''

    # 前景颜色
    BLACK = "\033[30m"
    """前景-黑"""
    RED = "\033[31m"
    """前景-红"""
    GREEN = "\033[32m"
    """前景-绿"""
    YELLOW = "\033[33m"
    """前景-黄"""
    BLUE = "\033[34m"
    """前景-蓝"""
    MAGENTA = "\033[35m"
    """前景-品红"""
    CYAN = "\033[36m"
    """前景-青"""
    WHITE = "\033[37m"
    """前景-白"""
    GRAY = "\033[90m"
    """前景-灰"""

    # 背景颜色
    BG_BLACK = "\033[40m"
    """背景-黑"""
    BG_RED = "\033[41m"
    """背景-红"""
    BG_GREEN = "\033[42m"
    """背景-绿"""
    BG_YELLOW = "\033[43m"
    """背景-黄"""
    BG_BLUE = "\033[44m"
    """背景-蓝"""
    BG_MAGENTA = "\033[45m"
    """背景-品红"""
    BG_CYAN = "\033[46m"
    """背景-青"""
    BG_WHITE = "\033[47m"
    """背景-白"""
    BG_GRAY = "\033[100m"
    """背景-灰"""

    # 样式
    RESET = "\033[0m"
    """重置所有颜色和样式"""
    BOLD = "\033[1m"
    """加粗"""
    UNDERLINE = "\033[4m"
    """下划线"""
    REVERSE = "\033[7m"
    """反转（前景色和背景色互换）"""
    ITALIC = "\033[3m"
    """斜体"""
    BLINK = "\033[5m"
    """闪烁"""
    STRIKE = "\033[9m"
    """删除线"""

    @classmethod
    def from_rgb(cls, r, g, b, background=False):
        """
        从 RGB 颜色代码创建颜色代码。

        :param r: 红色分量 (0-255)
        :param g: 绿色分量 (0-255)
        :param b: 蓝色分量 (0-255)
        :param background: 是否是背景颜色，默认为前景颜色
        :return: ANSI 颜色代码
        """
        if not cls._COLOR:
            return ''
        if background:
            return f"\033[48;2;{r};{g};{b}m"
        else:
            return f"\033[38;2;{r};{g};{b}m"

    @classmethod
    def rgb(cls, r, g, b):
        """
        创建前景 RGB 颜色。

        :param r: 红色分量 (0-255)
        :param g: 绿色分量 (0-255)
        :param b: 蓝色分量 (0-255)
        :return: ANSI 前景颜色代码
        """
        return cls.from_rgb(r, g, b, background=False)

    @classmethod
    def bg_rgb(cls, r, g, b):
        """
        创建背景 RGB 颜色。

        :param r: 红色分量 (0-255)
        :param g: 绿色分量 (0-255)
        :param b: 蓝色分量 (0-255)
        :return: ANSI 背景颜色代码
        """
        return cls.from_rgb(r, g, b, background=True)

    # 256 色模式
    @classmethod
    def color256(cls, color_code, background=False):
        """
        使用 256 色模式创建颜色。

        :param color_code: 256 色中的颜色编号 (0-255)
        :param background: 是否是背景颜色，默认为前景颜色
        :return: ANSI 颜色代码
        """
        if not cls._COLOR:
            return ''
        if background:
            return f"\033[48;5;{color_code}m"
        else:
            return f"\033[38;5;{color_code}m"

    @classmethod
    def rgb256(cls, r, g, b, background=False):
        """
        将 RGB 颜色转换为最接近的 256 色。

        :param r: 红色分量 (0-255)
        :param g: 绿色分量 (0-255)
        :param b: 蓝色分量 (0-255)
        :param background: 是否是背景颜色，默认为前景颜色
        :return: ANSI 256 色代码
        """
        if not cls._COLOR:
            return ''
        # 将 RGB 转换为 256 色
        def rgb_to_256(r, g, b):
            if r == g == b:  # 灰度
                if r < 8:
                    return 16
                if r > 248:
                    return 231
                return round((r - 8) / 247 * 24) + 232
            return 16 + (36 * round(r / 255 * 5)) + (6 * round(g / 255 * 5)) + round(b / 255 * 5)
        
        color_code = rgb_to_256(r, g, b)
        return cls.color256(color_code, background)

# 定义自定义的 tqdm 类，继承自原生的 tqdm 类
class tqdm(tqdm_original):
    """
    自定义 tqdm 类的初始化方法。
    通过设置默认参数，确保每次创建 tqdm 进度条时都能应用统一的风格。

    参数说明: 
    :param args: 原生 tqdm 支持的非关键字参数（如可迭代对象等）。
    :param kwargs: 原生 tqdm 支持的关键字参数，用于自定义进度条的行为和外观。
        - bar_format (str): 进度条的格式化字符串。
        - ncols (int): 进度条的宽度（以字符为单位）。
        - colour (str): 进度条的颜色。
        - desc (str): 进度条的描述信息。
        - unit (str): 进度条的单位。
        - leave (bool): 进度条完成后是否保留显示。
    """
    _STYLE_MAP = {
        "BLACK,": Color.BLACK,
        "RED": Color.RED,
        "GREEN": Color.GREEN,
        "YELLOW": Color.YELLOW,
        "BLUE": Color.BLUE,
        "MAGENTA": Color.MAGENTA,
        "CYAN": Color.CYAN,
        "WHITE": Color.WHITE,
    }
    

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("bar_format", 
            f"{Color.CYAN}{{desc}}{Color.RESET} "
            f"{Color.WHITE}{{percentage:3.0f}}%{Color.RESET}"
            f"{Color.GRAY}[{{n_fmt}}]{Color.RESET}"
            f"{Color.WHITE}|{{bar:20}}|{Color.RESET}"
            f"{Color.BLUE}[{{elapsed}}]{Color.RESET}"
        )
        kwargs.setdefault("ncols", 80)
        kwargs.setdefault("colour", "green")
        super().__init__(*args, **kwargs)
        
    @property
    def colour(self):
        return self._colour
        
    @colour.setter 
    def colour(self, color):
        # 确保颜色值有效
        valid_color = self._STYLE_MAP.get(color, "GREEN")  # 如果无效，回退到 GREEN
        self._colour = valid_color
        self.desc = f"{getattr(Color, valid_color)}{self.desc}{Color.RESET}"


# 日志级别颜色映射
LOG_LEVEL_TO_COLOR = {
    "DEBUG": Color.CYAN,
    "INFO": Color.GREEN,
    "WARNING": Color.YELLOW,
    "ERROR": Color.RED,
    "CRITICAL": Color.MAGENTA,
}


# 定义彩色格式化器
class ColoredFormatter(logging.Formatter):
    use_color = True
    def format(self, record):
        try:
            # 动态颜色处理
            if self.use_color:
                record.colored_levelname = (
                    f"{LOG_LEVEL_TO_COLOR.get(record.levelname, Color.RESET)}"
                    f"{record.levelname:8}"
                    f"{Color.RESET}"
                )
                # 添加统一颜色字段
                record.colored_name = f"{Color.MAGENTA}{record.name}{Color.RESET}"
                record.colored_time = f"{Color.CYAN}{self.formatTime(record)}{Color.RESET}"
            else:
                record.colored_levelname = record.levelname
                record.colored_name = record.name
                record.colored_time = self.formatTime(record)

            return super().format(record)
        except Exception as e:
            warnings.warn(f"日志格式化错误: {str(e)}")
            return f"[FORMAT ERROR] {record.getMessage()}"


def _get_valid_log_level(level_name: str, default: str):
    """验证并获取有效的日志级别"""
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        warnings.warn(f"Invalid log level: {level_name}, using {default} instead.")
        return getattr(logging, default)
    return level


def setup_logging():
    """设置日志"""
    # 环境变量读取
    console_level = os.getenv("LOG_LEVEL", "INFO").upper()
    file_level = os.getenv("FILE_LOG_LEVEL", "DEBUG").upper()
    # 为了保证有效日志信息仅支持控制台
    console_log_format = os.getenv("LOG_FORMAT", None)
    
    # 验证并转换日志级别
    console_log_level = _get_valid_log_level(console_level, "INFO")
    file_log_level = _get_valid_log_level(file_level, "DEBUG")

    # 日志格式配置
    default_log_format = {
        "console": {
            "DEBUG": f"{Color.CYAN}[%(asctime)s.%(msecs)03d]{Color.RESET} "
                    f"{Color.BLUE}%(colored_levelname)-8s{Color.RESET} "
                    f"{Color.GRAY}[%(threadName)s|%(processName)s]{Color.RESET} "
                    f"{Color.MAGENTA}%(name)s{Color.RESET} "
                    f"{Color.YELLOW}%(filename)s:%(funcName)s:%(lineno)d{Color.RESET} "
                    "| %(message)s",
            
            "INFO": f"{Color.CYAN}[%(asctime)s.%(msecs)03d]{Color.RESET} "
                    f"{Color.GREEN}%(colored_levelname)-8s{Color.RESET} "
                    f"{Color.MAGENTA}%(name)s{Color.RESET} ➜ "
                    f"{Color.WHITE}%(message)s{Color.RESET}",
            
            "WARNING": f"{Color.CYAN}[%(asctime)s.%(msecs)03d]{Color.RESET} "
                    f"{Color.YELLOW}%(colored_levelname)-8s{Color.RESET} "
                    f"{Color.MAGENTA}%(name)s{Color.RESET} "
                    f"{Color.RED}➜{Color.RESET} "
                    f"{Color.YELLOW}%(message)s{Color.RESET}",
            
            "ERROR": f"{Color.CYAN}[%(asctime)s.%(mctime)s.%(msecs)03d]{Color.RESET} "
                    f"{Color.RED}%(colored_levelname)-8s{Color.RESET} "
                    f"{Color.GRAY}[%(filename)s]{Color.RESET}"
                    f"{Color.MAGENTA}%(name)s:%(lineno)d{Color.RESET} "
                    f"{Color.RED}➜{Color.RESET} "
                    f"{Color.RED}%(message)s{Color.RESET}",
            
            "CRITICAL": f"{Color.CYAN}[%(asctime)s.%(msecs)03d]{Color.RESET} "
                        f"{Color.BG_RED}{Color.WHITE}%(colored_levelname)-8s{Color.RESET} "
                        f"{Color.GRAY}{{%(module)s}}{Color.RESET}"
                        f"{Color.MAGENTA}[%(filename)s]{Color.RESET}"
                        f"{Color.MAGENTA}%(name)s:%(lineno)d{Color.RESET} "
                        f"{Color.BG_RED}➜{Color.RESET} "
                        f"{Color.BOLD}%(message)s{Color.RESET}"
        },
        "file": {
            "DEBUG": "[%(asctime)s.%(msecs)03d] %(levelname)-8s [%(threadName)s|%(processName)s] %(name)s (%(filename)s:%(funcName)s:%(lineno)d) | %(message)s",
            "INFO": "[%(asctime)s.%(msecs)03d] %(levelname)-8s %(name)s ➜ %(message)s",
            "WARNING": "[%(asctime)s.%(msecs)03d] %(levelname)-8s %(name)s ➜ %(message)s",
            "ERROR": "[%(asctime)s.%(msecs)03d] %(levelname)-8s [%(filename)s]%(name)s:%(lineno)d ➜ %(message)s",
            "CRITICAL": "[%(asctime)s.%(msecs)03d] %(levelname)-8s {%(module)s}[%(filename)s]%(name)s:%(lineno)d ➜ %(message)s",
        }
    }

    # 日志格式配置
    log_format = os.getenv(
        "LOG_FORMAT",
        console_log_format or default_log_format['console'][console_level]
    )
    file_format = os.getenv(
        "LOG_FILE_FORMAT",
        default_log_format['file'][file_level]
    )

    # 文件路径配置
    log_dir = os.getenv("LOG_FILE_PATH", "./logs")
    file_name = os.getenv("LOG_FILE_NAME", "bot_%Y_%m_%d.log")
    
    # 备份数量验证
    try:
        backup_count = int(os.getenv("BACKUP_COUNT", "7"))
    except ValueError:
        backup_count = 7
        warnings.warn("BACKUP_COUNT 为无效值，使用默认值 7")
        os.environ["BACKUP_COUNT"] = 7

    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    file_path = os.path.join(log_dir, datetime.now().strftime(file_name))

    # 配置根日志器
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # 全局最低级别设为DEBUG

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_log_level)
    console_handler.setFormatter(ColoredFormatter(log_format))

    # 文件处理器
    file_handler = TimedRotatingFileHandler(
        filename=file_path,
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_handler.setLevel(file_log_level)
    file_handler.setFormatter(logging.Formatter(file_format))

    # 初始化并添加处理器
    logger.handlers = []
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


# 初始化日志配置
setup_logging()


def get_log(name='Loger'):
    """获取日志记录器"""
    return logging.getLogger(name)



# 示例用法
if __name__ == "__main__":
    from time import sleep

    from tqdm.contrib.logging import logging_redirect_tqdm

    logger = get_log(__name__)
    logger.debug("这是一个调试信息")
    logger.info("这是一个普通信息")
    logger.warning("这是一个警告信息")
    logger.error("这是一个错误信息")
    logger.critical("这是一个严重错误信息")
    # 常见参数
    # total: 总进度数。
    # desc: 进度条描述。
    # ncols: 进度条宽度。
    # unit: 进度单位。
    # leave: 是否在完成后保留进度条。

    with logging_redirect_tqdm():
        with tqdm(range(0, 100)) as pbar:
            for i in pbar:
                if i % 10 == 0:
                    logger.info(f"now: {i}")
                sleep(0.1)