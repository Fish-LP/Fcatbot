# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 13:41:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-22 21:51:42
# @Description  : 日志格式化 (Modernized + PascalCase)
# @Copyright (c) 2025 by Fish-LP, MIT 使用许可协议
# -------------------------

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
import time
import warnings
from contextvars import ContextVar
from dataclasses import dataclass, field
from logging.handlers import QueueListener, TimedRotatingFileHandler
from queue import Queue
from typing import Any, Dict, List, Optional, Union

from fcatbot.utils.color import Color

__author__ = "Fish-LP <Fish.zh@outlook.com>"
__version__ = "3.1.0"

# 上下文变量
RequestId: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
TraceId: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

# handler 的"本模块管理"标记，用于安全替换/清理
_MANAGED_FLAG = "_fcatbot_managed"


def set_request_id(rid: str) -> None:
    RequestId.set(rid)


def set_trace_id(tid: str) -> None:
    TraceId.set(tid)


@dataclass
class LogConfig:
    console_level: Union[int, str] = "INFO"
    file_level: Union[int, str] = "DEBUG"
    log_dir: str = "./logs"
    file_name: str = "bot.log"
    backup_count: int = 7
    use_color: bool = True
    use_json: bool = False
    # 默认本地时间，避免 datefmt 与 rollover 时区不一致的困扰
    utc: bool = False
    redirect_rules: Dict[str, str] = field(default_factory=dict)
    queue_size: int = 1000

    def __post_init__(self) -> None:
        if isinstance(self.console_level, str):
            self.console_level = self._parse_level(self.console_level, logging.INFO)
        if isinstance(self.file_level, str):
            self.file_level = self._parse_level(self.file_level, logging.DEBUG)
        if self.backup_count < 0:
            raise ValueError("backup_count 不能为负数")

    @staticmethod
    def _parse_level(level: str, default: int) -> int:
        val = getattr(logging, str(level).upper(), None)
        if not isinstance(val, int):
            warnings.warn(f"日志级别 '{level}' 无效，使用默认值。")
            return default
        return val

    @classmethod
    def from_env(cls) -> "LogConfig":
        redirect = os.getenv("LOG_REDIRECT_RULES", "{}")
        try:
            redirect_rules = json.loads(redirect)
            if not isinstance(redirect_rules, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            redirect_rules = {}
            warnings.warn("LOG_REDIRECT_RULES 格式无效，使用空规则")

        try:
            backup_count = int(os.getenv("BACKUP_COUNT", "7"))
        except ValueError:
            backup_count = 7
            warnings.warn("BACKUP_COUNT 无效，使用默认 7")

        return cls(
            console_level=os.getenv("LOG_LEVEL", "INFO"),
            file_level=os.getenv("FILE_LOG_LEVEL", "DEBUG"),
            log_dir=os.getenv("LOG_FILE_PATH", "./logs"),
            file_name=os.getenv("LOG_FILE_NAME", "bot.log"),
            backup_count=backup_count,
            use_json=os.getenv("LOG_JSON_FORMAT", "false").lower() == "true",
            utc=os.getenv("LOG_UTC", "false").lower() == "true",
            redirect_rules=redirect_rules,
        )


# ---------- 格式化器与过滤器 ----------
class _AnsiStripper:
    AnsiRe = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    @classmethod
    def strip(cls, text: str) -> str:
        return cls.AnsiRe.sub("", text)


class _NoColor:
    """无颜色占位: 任何属性访问都返回空串，避免反射式构造的脆弱性。"""

    def __getattr__(self, _name: str) -> str:
        return ""


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = RequestId.get() or ""
        record.trace_id = TraceId.get() or ""
        return True


class DynamicFormatter(logging.Formatter):
    LevelColors = {
        "DEBUG": Color.Cyan,
        "INFO": Color.Green,
        "WARNING": Color.Yellow,
        "ERROR": Color.Red,
        "CRITICAL": Color.Magenta + Color.Bold,
    }

    def __init__(
        self,
        fmt_dict: Dict[str, str],
        datefmt: Optional[str] = None,
        use_color: bool = True,
        strip_ansi_for_file: bool = False,
    ):
        super().__init__(datefmt=datefmt)
        self.use_color = use_color
        self.strip_ansi = strip_ansi_for_file
        self._formatters: Dict[str, logging.Formatter] = {
            level: logging.Formatter(fmt, datefmt=datefmt)
            for level, fmt in fmt_dict.items()
        }
        self._default = next(iter(self._formatters.values()))

    def format(self, record: logging.LogRecord) -> str:
        # 在副本上注入 extras，避免污染原始 record（多 handler / 未来异步场景更安全）
        rec = logging.makeLogRecord(record.__dict__)
        if self.use_color:
            color = self.LevelColors.get(record.levelname, "")
            rec.colored_levelname = f"{color}{record.levelname:8}{Color.Reset}"
            rec.colored_name = f"{Color.Magenta}{record.name}{Color.Reset}"
        else:
            rec.colored_levelname = record.levelname
            rec.colored_name = record.name

        formatter = self._formatters.get(record.levelname, self._default)
        msg = formatter.format(rec)

        if self.strip_ansi:
            msg = _AnsiStripper.strip(msg)
        return msg


class JsonFormatter(logging.Formatter):
    _StdRecordKeys = frozenset(
        {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "asctime", "taskName",
        }
    )

    def __init__(
        self,
        fmt_dict: Optional[Dict[str, str]] = None,
        datefmt: Optional[str] = None,
        extra_fields: Optional[List[str]] = None,
    ):
        super().__init__(datefmt=datefmt)
        self.extra_fields = extra_fields or [
            "request_id",
            "trace_id",
            "funcName",
            "threadName",
        ]

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "filename": record.filename,
            "lineno": record.lineno,
        }
        for key in self.extra_fields:
            value = getattr(record, key, None)
            if value:
                log_obj[key] = value

        for key, value in record.__dict__.items():
            if (
                key not in self._StdRecordKeys
                and key not in self.extra_fields
                and value is not None
            ):
                log_obj[key] = value

        return json.dumps(log_obj, ensure_ascii=False, default=str)


# ---------- 格式模板 ----------
def _make_formats(use_color: bool) -> Dict[str, Dict[str, str]]:
    c: Any = Color if use_color else _NoColor()
    return {
        "console": {
            "DEBUG": (
                f"{c.Cyan}[%(asctime)s.%(msecs)s]{c.Reset} "
                f"{c.Blue}%(colored_levelname)-8s{c.Reset} "
                f"{c.Gray}[%(threadName)s|%(processName)s]{c.Reset} "
                f"{c.Magenta}%(colored_name)s{c.Reset} "
                f"{c.Yellow}%(filename)s:%(lineno)d %(funcName)s{c.Reset} "
                f"| %(message)s"
            ),
            "INFO": (
                f"{c.Cyan}[%(asctime)s]{c.Reset} "
                f"{c.Green}%(colored_levelname)-8s{c.Reset} "
                f"{c.Magenta}%(colored_name)s{c.Reset} ➜ %(message)s"
            ),
            "WARNING": (
                f"{c.Cyan}[%(asctime)s]{c.Reset} "
                f"{c.Yellow}%(colored_levelname)-8s{c.Reset} "
                f"{c.Magenta}%(colored_name)s{c.Reset} "
                f"{c.Yellow}➜{c.Reset} %(message)s"
            ),
            "ERROR": (
                f"{c.Cyan}[%(asctime)s]{c.Reset} "
                f"{c.Red}%(colored_levelname)-8s{c.Reset} "
                f"{c.Gray}[%(filename)s:%(lineno)d]{c.Reset} "
                f"{c.Magenta}%(colored_name)s{c.Reset} "
                f"{c.Red}➜{c.Reset} %(message)s"
            ),
            "CRITICAL": (
                f"{c.Cyan}[%(asctime)s]{c.Reset} "
                f"{c.Red}{c.Bold}%(colored_levelname)-8s{c.Reset} "
                f"{c.Gray}{{%(module)s}}{c.Reset} "
                f"{c.Magenta}[%(filename)s]{c.Reset} "
                f"{c.Magenta}%(colored_name)s{c.Reset}:{c.Magenta}%(lineno)d{c.Reset} "
                f"{c.Red}➜{c.Reset} %(message)s"
            ),
        },
        "file": {
            "DEBUG": "[%(asctime)s] %(levelname)-8s [%(threadName)s|%(processName)s] %(name)s (%(filename)s:%(funcName)s:%(lineno)d) | %(message)s",
            "INFO": "[%(asctime)s] %(levelname)-8s %(name)s ➜ %(message)s",
            "WARNING": "[%(asctime)s] %(levelname)-8s %(name)s ➜ %(message)s",
            "ERROR": "[%(asctime)s] %(levelname)-8s [%(filename)s]%(name)s:%(lineno)d ➜ %(message)s",
            "CRITICAL": "[%(asctime)s] %(levelname)-8s {%(module)s}[%(filename)s]%(name)s:%(lineno)d ➜ %(message)s",
        },
    }


# ---------- handler 管理工具 ----------
_listener: Optional[QueueListener] = None
_redirect_logger_names: set[str] = set()


def _mark(h: logging.Handler) -> logging.Handler:
    setattr(h, _MANAGED_FLAG, True)
    return h


def _is_managed(h: logging.Handler) -> bool:
    return getattr(h, _MANAGED_FLAG, False)


def _remove_managed_handlers(
    logger: logging.Logger, handler_type: Optional[type] = None
) -> None:
    """只清理本模块创建的 handler，保留外部注入的 handler。"""
    for h in logger.handlers[:]:
        if _is_managed(h) and (handler_type is None or isinstance(h, handler_type)):
            logger.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass


def _make_file_formatter(
    config: "LogConfig", formats: Dict[str, Dict[str, str]]
) -> logging.Formatter:
    if config.use_json:
        return JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    return DynamicFormatter(
        fmt_dict=formats["file"],
        datefmt="%Y-%m-%d %H:%M:%S",
        use_color=False,
        strip_ansi_for_file=True,
    )


# ---------- 核心安装函数 ----------
def setup_logging(config: Optional[LogConfig] = None) -> Optional[QueueListener]:
    global _listener

    if config is None:
        config = LogConfig.from_env()

    os.makedirs(config.log_dir, exist_ok=True)
    formats = _make_formats(use_color=config.use_color and Color._ColorEnabled)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 1) 停旧 listener，并关闭它持有的 file handler（避免句柄泄漏）
    if _listener is not None:
        _listener.stop()
        for h in getattr(_listener, "handlers", ()):  # QueueListener.handlers 是公开属性
            try:
                h.close()
            except Exception:
                pass
        _listener = None

    # 2) 清理 root 上本模块管理过的 handler（含 queue handler），保留外部注入的
    _remove_managed_handlers(root)

    # 3) 清理上一次的重定向 logger
    for name in _redirect_logger_names:
        _remove_managed_handlers(logging.getLogger(name))
    _redirect_logger_names.clear()

    # converter: 让日期输出与 rollover 时区保持一致
    converter = time.gmtime if config.utc else time.localtime

    # 4) 控制台
    console_fmt = DynamicFormatter(
        fmt_dict=formats["console"],
        datefmt="%H:%M:%S",
        use_color=config.use_color,
    )
    console_fmt.converter = converter

    console_handler = _mark(logging.StreamHandler())
    console_handler.setLevel(config.console_level)
    console_handler.setFormatter(console_fmt)
    console_handler.addFilter(ContextFilter())

    # 5) 主文件
    root_file_path = os.path.join(config.log_dir, config.file_name)
    file_formatter = _make_file_formatter(config, formats)
    file_formatter.converter = converter

    file_handler = _mark(
        TimedRotatingFileHandler(
            filename=root_file_path,
            when="midnight",
            interval=1,
            backupCount=config.backup_count,
            encoding="utf-8",
            utc=config.utc,
        )
    )
    file_handler.setLevel(config.file_level)
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(ContextFilter())

    # 6) 重定向 logger（直接挂子 logger，不进队列，与原行为一致）
    for logger_name, filename in config.redirect_rules.items():
        redirect_path = os.path.join(config.log_dir, filename)
        redirect_handler = _mark(
            TimedRotatingFileHandler(
                filename=redirect_path,
                when="midnight",
                interval=1,
                backupCount=config.backup_count,
                encoding="utf-8",
                utc=config.utc,
            )
        )
        redirect_handler.setLevel(config.file_level)
        redirect_handler.setFormatter(file_formatter)
        redirect_handler.addFilter(ContextFilter())

        logger = logging.getLogger(logger_name)
        logger.setLevel(config.file_level)
        _remove_managed_handlers(logger)  # 只清本模块的，保留外部
        logger.addHandler(redirect_handler)
        logger.propagate = False
        _redirect_logger_names.add(logger_name)

    # 7) 挂到 root
    if config.queue_size > 0:
        from logging.handlers import QueueHandler

        log_queue: Queue = Queue(maxsize=config.queue_size)
        queue_handler = _mark(QueueHandler(log_queue))
        queue_handler.addFilter(ContextFilter())

        # 控制台同步输出（供 patch_stdout 等捕获），文件走队列
        root.addHandler(console_handler)
        root.addHandler(queue_handler)

        listener = QueueListener(
            log_queue, file_handler, respect_handler_level=True
        )
        listener.start()
        _listener = listener
        return listener

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    return None


def get_logger(
    name: str, extra: Optional[Dict[str, Any]] = None
) -> logging.LoggerAdapter:
    logger = logging.getLogger(name)
    # 拷贝一份，避免调用方后续修改污染
    return logging.LoggerAdapter(logger, dict(extra) if extra else {})


# ---------- 示例 ----------
if __name__ == "__main__":
    Color.init()
    cfg = LogConfig(console_level="DEBUG", use_json=False)
    listener = setup_logging(cfg)

    log = get_logger("modern_logger")
    set_request_id("req-0426-001")
    set_trace_id("trace-abc-123")

    log.debug("调试信息，带文件位置")
    log.info("普通信息，简洁格式")
    log.warning("警告信息")
    log.error("错误信息")
    log.critical("严重错误")

    if listener:
        listener.stop()