"""终端宽度工具。

- 使用 wcwidth 库计算 Unicode 字符的显示宽度
- CJK / 全角 / Emoji 计 2 列，控制符计 0 列
- 所有 padding 操作在纯文本上完成，ANSI 颜色码最后注入
"""

from __future__ import annotations

import re
import shutil

try:
    from wcwidth import wcswidth as _wcswidth
except ImportError:
    def _wcswidth(s: str) -> int:
        # 回退: 无 wcwidth 库时，粗略估算
        import unicodedata
        w = 0
        for ch in s:
            if unicodedata.east_asian_width(ch) in ("W", "F"):
                w += 2
            elif unicodedata.category(ch).startswith("C"):
                pass
            else:
                w += 1
        return w

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def width(s: str) -> int:
    """字符串的显示宽度（不含 ANSI 转义序列）。"""
    clean = _ANSI_RE.sub("", s)
    return _wcswidth(clean)


def pad_end(s: str, target: int, pad: str = " ") -> str:
    """按显示宽度右侧补空格。"""
    w = width(s)
    if w >= target:
        return s
    return s + pad * (target - w)


def truncate(s: str, max_width: int, ellipsis: str = "…") -> str:
    """按显示宽度截断，超出部分用省略号替代。"""
    if width(s) <= max_width:
        return s
    target = max_width - width(ellipsis)
    if target <= 0:
        return ellipsis

    result = []
    w = 0
    for ch in s:
        cw = width(ch)
        if w + cw > target:
            break
        result.append(ch)
        w += cw
    return "".join(result) + ellipsis


def terminal_size() -> tuple[int, int]:
    """返回 (columns, lines)"""
    size = shutil.get_terminal_size((256, 256))
    return size.columns, size.lines