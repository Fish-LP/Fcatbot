"""命令参数解析流与格式化工具。

分两层：

- **静态方法**：纯函数，任何地方可直接复用（``CommandArgs.parse_duration("30m")``）；
- **实例方法**：包装一段 token 列表，按位置顺序消费
  （``take_bool`` / ``take_duration`` / ``require`` …），
  不匹配则**不消费**，天然支持 ``[true|false] [时长]`` 这类可选位置参数。

典型用法::

    from fcatbot.kernel.args import ArgParseError, CommandArgs

    a = CommandArgs(rest)
    node = a.require("权限节点")
    value = a.take_bool(default=True)          # 非 bool → 不消费
    duration = a.take_duration(required=(action == "settemp"))
    ctx, extra = a.split_context()
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = ["ArgParseError", "CommandArgs"]

# ---------------------------------------------------------------------------
# 可复用的词表 / 单位
# ---------------------------------------------------------------------------

_BOOL_TRUE = frozenset({"true", "t", "yes", "y", "1", "allow"})
_BOOL_FALSE = frozenset({"false", "f", "no", "n", "0", "deny"})
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


class ArgParseError(ValueError):
    """参数解析失败（缺参、类型不符等）。"""


class CommandArgs:
    """命令参数解析流。

    实例包装一个 ``List[str]``，维护内部游标；所有 ``take_*`` 方法遵循同一约定：

    - **匹配则消费并返回解析结果**；
    - **不匹配则不消费、返回 default/None**（或按 ``required`` 抛 :class:`ArgParseError`）。

    因此可选位置参数（如 LuckPerms 的 ``[true|false] [时长]``）可以顺序取用而不必
    预先判断下一个 token 是什么类型。
    """

    # ------------------------------------------------------------------
    # 构造 / 状态
    # ------------------------------------------------------------------

    def __init__(self, tokens: Optional[Sequence[str]] = None) -> None:
        self._tokens: List[str] = list(tokens or [])
        self._index: int = 0

    @property
    def index(self) -> int:
        """当前游标（已消费 token 数）。"""
        return self._index

    def is_empty(self) -> bool:
        return self._index >= len(self._tokens)

    def remaining_count(self) -> int:
        return len(self._tokens) - self._index

    def peek(self) -> Optional[str]:
        """看一眼下一个 token（不消费）。"""
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]

    def remaining(self) -> List[str]:
        """未消费的 token 列表。"""
        return self._tokens[self._index :]

    def rest_join(self, sep: str = " ") -> str:
        """把剩余 token 拼接为字符串（消费它们）。"""
        text = sep.join(self._tokens[self._index :])
        self._index = len(self._tokens)
        return text

    # ------------------------------------------------------------------
    # 位置参数
    # ------------------------------------------------------------------

    def next(self) -> Optional[str]:
        """取下一个 token；耗尽返回 None。"""
        if self._index >= len(self._tokens):
            return None
        token = self._tokens[self._index]
        self._index += 1
        return token

    def require(self, label: str = "参数") -> str:
        """取下一个 token；缺失抛 :class:`ArgParseError`。"""
        token = self.next()
        if token is None:
            raise ArgParseError(f"缺少{label}")
        return token

    # ------------------------------------------------------------------
    # 类型化消费（不匹配则不消费）
    # ------------------------------------------------------------------

    def take_bool(self, *, default: Optional[bool] = None) -> Optional[bool]:
        """下一 token 是布尔词则消费；否则返回 ``default`` 且不消费。"""
        token = self.peek()
        if token is None:
            return default
        parsed = self.parse_bool(token)
        if parsed is None:
            return default
        self._index += 1
        return parsed

    def take_int(self, *, allow_negative: bool = True) -> Optional[int]:
        """下一 token 是整数则消费；否则返回 None 且不消费。"""
        token = self.peek()
        if token is None:
            return None
        parsed = self.parse_int(token, allow_negative=allow_negative)
        if parsed is None:
            return None
        self._index += 1
        return parsed

    def take_position(self) -> Optional[int]:
        """1-based 位置 → 0-based 索引；非正整数返回 None 且不消费。"""
        value = self.take_int(allow_negative=False)
        if value is None or value < 1:
            return None
        return value - 1

    def take_duration(
        self,
        *,
        required: bool = False,
        missing_msg: str = "缺少时长参数",
        invalid_msg: str = "无效时长: {token}（示例: 30s / 10m / 2h / 7d）",
    ) -> Optional[int]:
        """下一 token 是时长则消费并返回秒数。

        ``required=True`` 时缺失或格式非法都会抛 :class:`ArgParseError`；
        否则返回 None 且不消费。
        """
        token = self.peek()
        if token is None:
            if required:
                raise ArgParseError(missing_msg)
            return None
        parsed = self.parse_duration(token)
        if parsed is None:
            if required:
                raise ArgParseError(invalid_msg.format(token=token))
            return None
        self._index += 1
        return parsed

    # ------------------------------------------------------------------
    # 上下文（key=value）
    # ------------------------------------------------------------------

    def split_context(self) -> Tuple[Dict[str, str], List[str]]:
        """把剩余 token 拆成 ``(context, 未识别列表)``；会消费全部剩余 token。"""
        ctx, rest = self.parse_context(self._tokens[self._index :])
        self._index = len(self._tokens)
        return ctx, rest

    # ------------------------------------------------------------------
    # 静态：纯解析（不依赖实例，可任意复用）
    # ------------------------------------------------------------------

    @staticmethod
    def parse_bool(token: str) -> Optional[bool]:
        """``true/t/yes/y/1/allow`` → True；``false/f/no/n/0/deny`` → False。"""
        lowered = token.strip().lower()
        if lowered in _BOOL_TRUE:
            return True
        if lowered in _BOOL_FALSE:
            return False
        return None

    @staticmethod
    def parse_int(token: str, *, allow_negative: bool = True) -> Optional[int]:
        """严格整数解析；非整数返回 None（不抛错）。"""
        text = token.strip()
        if not text:
            return None
        if not allow_negative and text.startswith("-"):
            return None
        body = text.lstrip("-")
        if not body.isdigit():
            return None
        return int(text)

    @staticmethod
    def parse_duration(text: str) -> Optional[int]:
        """``1d2h30m`` → 秒；纯数字视为秒；支持 s/m/h/d/w；非法返回 None。"""
        text = text.strip().lower()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        total = 0
        number = ""
        for ch in text:
            if ch.isdigit():
                number += ch
                continue
            unit = _DURATION_UNITS.get(ch)
            if unit is None or not number:
                return None
            total += int(number) * unit
            number = ""
        if number:  # 结尾裸数字视为秒
            total += int(number)
        return total or None

    @staticmethod
    def parse_context(tokens: Iterable[str]) -> Tuple[Dict[str, str], List[str]]:
        """分离 ``key=value`` 上下文与未识别 token。"""
        ctx: Dict[str, str] = {}
        rest: List[str] = []
        for token in tokens:
            if "=" in token and not token.startswith("="):
                key, _, value = token.partition("=")
                if key:
                    ctx[key] = value
                    continue
            rest.append(token)
        return ctx, rest

    @staticmethod
    def normalize_context(context: Mapping[str, Any]) -> Dict[str, List[str]]:
        """与 ``Node.normalize_context`` 对齐的归一化（用于 clear 过滤）。"""
        normalized: Dict[str, List[str]] = {}
        for key, value in context.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            else:
                rendered = str(value)
            if rendered:
                normalized[key] = [rendered]
        return normalized

    # ------------------------------------------------------------------
    # 静态：格式化
    # ------------------------------------------------------------------

    @staticmethod
    def fmt_duration(seconds: int) -> str:
        """秒 → 最大可整除单位（``7200`` → ``2h``）。"""
        for unit, size in (
            ("w", 604800),
            ("d", 86400),
            ("h", 3600),
            ("m", 60),
            ("s", 1),
        ):
            if seconds % size == 0:
                return f"{seconds // size}{unit}"
        return f"{seconds}s"

    @staticmethod
    def fmt_remain(seconds: int) -> str:
        """剩余时长的近似展示（取最大可用单位，带 ``~`` 前缀）。"""
        for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
            if seconds >= size:
                return f"~{seconds // size}{unit}"
        return f"{seconds}s"

    @staticmethod
    def fmt_context(context: Mapping[str, Any]) -> str:
        """节点上下文 → ``" ctx={k=v, ...}"``；空上下文返回空串。"""
        if not context:
            return ""
        parts: List[str] = []
        for key, value in context.items():
            if isinstance(value, (list, tuple, set)):
                rendered = ",".join(str(item) for item in value)
            else:
                rendered = str(value)
            parts.append(f"{key}={rendered}")
        return " ctx={" + ", ".join(parts) + "}"

    # ------------------------------------------------------------------
    # 静态：verbose 过滤器
    # ------------------------------------------------------------------

    @staticmethod
    def match_verbose_filter(expr: str, user_id: str, node: str) -> bool:
        """``!term`` 取反；``|`` 分隔为"或"；term 按节点/用户前缀匹配。"""
        for term in expr.split("|"):
            term = term.strip()
            if not term:
                continue
            negate = term.startswith("!")
            if negate:
                term = term[1:].strip()
            hit = node.startswith(term) or user_id.startswith(term)
            if negate:
                hit = not hit
            if hit:
                return True
        return False
