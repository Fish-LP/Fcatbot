# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:41:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-22 21:51:42
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import logging
import os
import json
import warnings
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from tqdm import tqdm as tqdm_original
from .color import Color


# 定义自定义的 tqdm 类,继承自原生的 tqdm 类
class tqdm(tqdm_original):
    """
    自定义 tqdm 类的初始化方法。
    通过设置默认参数,确保每次创建 tqdm 进度条时都能应用统一的风格。

    参数说明: 
    :param args: 原生 tqdm 支持的非关键字参数（如可迭代对象等）。
    :param kwargs: 原生 tqdm 支持的关键字参数,用于自定义进度条的行为和外观。
        - bar_format (str): 进度条的格式化字符串。
        - ncols (int): 进度条的宽度（以字符为单位）。
        - colour (str): 进度条的颜色。
        - desc (str): 进度条的描述信息。
        - unit (str): 进度条的单位。
        - leave (bool): 进度条完成后是否保留显示。
    """
    _STYLE_MAP = {
        "BLACK": Color.BLACK,
        "RED": Color.RED,
        "GREEN": Color.GREEN,
        "YELLOW": Color.YELLOW,
        "BLUE": Color.BLUE,
        "MAGENTA": Color.MAGENTA,
        "CYAN": Color.CYAN,
        "WHITE": Color.WHITE,
    }
    
    def __init__(self, *args, **kwargs):
        # 保存颜色参数以便后续处理
        self._custom_colour = kwargs.get("colour", "GREEN")
        
        # 设置默认进度条格式
        kwargs.setdefault("bar_format", 
            f"{Color.CYAN}{{desc}}{Color.RESET} "
            f"{Color.WHITE}{{percentage:3.0f}}%{Color.RESET} "
            f"{Color.GRAY}[{{n_fmt}}]{Color.RESET}"
            f"{Color.WHITE}|{{bar:20}}|{Color.RESET}"
            f"{Color.BLUE}[{{elapsed}}]{Color.RESET}"
        )
        kwargs.setdefault("ncols", 80)
        kwargs.setdefault("colour", None)  # 避免基类处理颜色
        
        super().__init__(*args, **kwargs)
        
        # 在初始化完成后应用颜色
        self.colour = self._custom_colour
        
    @property
    def colour(self):
        return self._colour
        
    @colour.setter 
    def colour(self, color):
        # 确保颜色值有效
        if not color:
            color = "GREEN"
            
        color_upper = color.upper()
        valid_color = self._STYLE_MAP.get(color_upper, "GREEN")
        
        # 保存颜色值
        self._colour = color_upper
        
        # 更新描述信息颜色
        if hasattr(self, 'GREEN') and self.desc:
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
    """设置日志系统，支持根据记录器名称重定向到不同文件"""
    # 环境变量读取
    console_level = os.getenv("LOG_LEVEL", "INFO").upper()
    file_level = os.getenv("FILE_LOG_LEVEL", "DEBUG").upper()
    
    # 验证并转换日志级别
    console_log_level = _get_valid_log_level(console_level, "INFO")
    file_log_level = _get_valid_log_level(file_level, "DEBUG")
    
    # 日志格式配置
    console_log_format = os.getenv("LOG_FORMAT", 
        f"{Color.CYAN}[%(asctime)s]{Color.RESET} "
        f"%(colored_levelname)s "
        f"{Color.MAGENTA}%(name)s{Color.RESET} ➜ "
        f"{Color.WHITE}%(message)s{Color.RESET}"
    )
    
    file_log_format = os.getenv("LOG_FILE_FORMAT",
        "[%(asctime)s] %(levelname)-8s %(name)s ➜ %(message)s"
    )
    
    # 文件路径配置
    log_dir = os.getenv("LOG_FILE_PATH", "./logs")
    file_name = os.getenv("LOG_FILE_NAME", "bot_%Y_%m_%d.log")
    
    # 备份数量验证
    try:
        backup_count = int(os.getenv("BACKUP_COUNT", "7"))
    except ValueError:
        backup_count = 7
        warnings.warn("BACKUP_COUNT 为无效值,使用默认值 7")
        os.environ["BACKUP_COUNT"] = "7"

    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    root_file_path = os.path.join(log_dir, datetime.now().strftime(file_name))

    # ===== 1. 配置根记录器 =====
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 全局最低级别设为DEBUG
    
    # 控制台处理器 - 只添加到根记录器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_log_level)
    console_handler.setFormatter(ColoredFormatter(console_log_format, datefmt='%H:%M:%S'))
    
    # 根记录器的文件处理器
    root_file_handler = TimedRotatingFileHandler(
        filename=root_file_path,
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8"
    )
    root_file_handler.setLevel(file_log_level)
    root_file_handler.setFormatter(logging.Formatter(file_log_format))
    
    # 添加处理器到根记录器
    root_logger.handlers = [console_handler, root_file_handler]
    
    # ===== 2. 配置重定向记录器 =====
    # 从环境变量读取重定向配置
    redirect_rules_json = os.getenv("LOG_REDIRECT_RULES", "{}")
    try:
        redirect_rules = json.loads(redirect_rules_json)
    except json.JSONDecodeError:
        redirect_rules = {}
        warnings.warn("Invalid LOG_REDIRECT_RULES format. Using default rules.")
    
    # 默认重定向规则
    if not redirect_rules:
        redirect_rules = {
            # "database": "database.log",
            # "network": "network.log",
            # "security": "security.log"
        }
    
    # 为每个重定向规则创建记录器和处理器
    for logger_name, filename in redirect_rules.items():
        # 创建完整的文件路径
        redirect_file_path = os.path.join(log_dir, filename)
        
        # 创建文件处理器
        file_handler = TimedRotatingFileHandler(
            filename=redirect_file_path,
            when="midnight",
            interval=1,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(file_log_level)
        file_handler.setFormatter(logging.Formatter(file_log_format))
        
        # 创建记录器并添加处理器
        logger = logging.getLogger(logger_name)
        logger.setLevel(file_log_level)
        logger.addHandler(file_handler)
        
        # 关键：禁止传播到根记录器，避免重复记录
        logger.propagate = False


# 初始化日志配置
setup_logging()


def get_log(name='Logger'):
    """获取日志记录器"""
    return logging.getLogger(name)


# 示例用法
if __name__ == "__main__":
    from time import sleep
    from tqdm.contrib.logging import logging_redirect_tqdm

    # 获取不同记录器的日志
    root_logger = get_log()
    db_logger = get_log("database")
    net_logger = get_log("network")
    sec_logger = get_log("security")
    
    # 测试日志输出
    root_logger.debug("根记录器调试信息")
    root_logger.info("根记录器普通信息")
    db_logger.warning("数据库警告: 连接池接近满负荷")
    net_logger.error("网络错误: 连接超时")
    sec_logger.critical("安全警报: 检测到异常登录尝试")

    # 测试进度条日志集成
    with logging_redirect_tqdm():
        with tqdm(range(0, 100), desc="处理进度") as pbar:
            for i in pbar:
                if i % 10 == 0:
                    root_logger.info(f"当前进度: {i}%")
                    db_logger.debug(f"数据库查询 {i} 次")
                sleep(0.1)
    
    root_logger.info("所有任务已完成!")