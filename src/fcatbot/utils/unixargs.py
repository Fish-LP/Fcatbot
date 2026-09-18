"""unixargs —— 通用 Unix 风格参数解析器。

两个入口：

1. 函数式（选项集合运行时才知，适合包装器 / 透传）：
     r = parse_unix(argv, bool_options={...}, value_options={...})
     r.flags, r.options, r.positionals, r.extra

2. 链式（选项固定，对标 argparse 手感）：
     r = (UnixParser()
          .flag("-v", "--verbose")
          .option("-o", "--output", required=True)
          .optional("-O")
          .parse(argv))
     r.verbose, r.output, r.level, r.positionals, r.extra
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Iterable, Mapping

__all__ = [
    "ArgParseError",
    "ParsedArgs",
    "Result",
    "parse_unix",
    "UnixParser",
]


# =========================================================================== #
# 错误类型
# =========================================================================== #
class ArgParseError(ValueError):
    """带出错 token 的解析错误。"""

    def __init__(self, msg: str, token: str | None = None):
        self.token = token
        super().__init__(f"{msg}: {token!r}" if token is not None else msg)


# =========================================================================== #
# 函数式 API 的结果对象
# =========================================================================== #
@dataclass(slots=True)
class ParsedArgs:
    """通用解析结果（四个桶）。

    flags:       布尔 / 计数选项，如 {'-v': 2}
    options:     带值选项，如 {'-o': ['out.txt']}（保留全部出现）
    positionals: 位置参数，按原序
    extra:       未识别的原始 token，保序（供包装器透传）
    """

    flags: dict[str, int] = field(default_factory=dict)
    options: dict[str, list[str]] = field(default_factory=dict)
    positionals: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    # ---- 查询 ---------------------------------------------------------- #
    def has(self, name: str) -> bool:
        return name in self.flags or name in self.options

    def count(self, name: str) -> int:
        return self.flags.get(name, 0)

    def get(self, name: str, default: str | None = None) -> str | None:
        vals = self.options.get(name)
        return vals[-1] if vals else default

    def get_all(self, name: str) -> list[str]:
        return list(self.options.get(name, ()))

    def bind(self, spec: Mapping[str, str]) -> dict[str, object]:
        """spec: {'verbose': '-v', 'out': '--output'} -> {'verbose': 2, 'out': 'x'}"""
        out: dict[str, object] = {}
        for key, opt in spec.items():
            if opt in self.flags:
                out[key] = self.flags[opt]
            elif opt in self.options:
                out[key] = self.options[opt][-1]
        return out


# =========================================================================== #
# 函数式 API
# =========================================================================== #
def parse_unix(
    argv: Iterable[str],
    *,
    bool_options: Iterable[str] = (),
    value_options: Iterable[str] = (),
    optional_value_options: Iterable[str] = (),
    stop_at_first_positional: bool = False,
    allow_unknown: bool = True,
) -> ParsedArgs:
    """Unix 风格通用参数解析（无声明式）。

    bool_options           : 纯开关 / 可累加计数，如 '-v', '--verbose'
    value_options          : 必须带值的选项，如 '-o', '--output'
    optional_value_options : 值可缺省的选项（`-O`、`-O2` 都合法）
    stop_at_first_positional: 遇首个位置参数即停（POSIXLY_CORRECT）
    allow_unknown          : False 时遇未知选项抛 ArgParseError
    """
    bool_set = frozenset(bool_options)
    value_set = frozenset(value_options)
    optval_set = frozenset(optional_value_options)

    res = ParsedArgs()
    tokens = list(argv)
    n = len(tokens)
    i = 0
    only_pos = False

    while i < n:
        tok = tokens[i]
        i += 1

        # 位置参数 / POSIX 停止
        if only_pos or len(tok) <= 1 or tok[0] != "-":
            res.positionals.append(tok)
            if stop_at_first_positional and not only_pos:
                only_pos = True
            continue

        # `--` 之后一律当字面量
        if tok == "--":
            only_pos = True
            continue

        # ---- 长选项 --name / --name=value --------------------------- #
        if tok[1] == "-":
            name, eq, value = tok[2:].partition("=")
            key = "--" + name

            if key in bool_set:
                if eq:
                    raise ArgParseError("option does not take a value", key)
                res.flags[key] = res.flags.get(key, 0) + 1
                continue

            if key in value_set or key in optval_set:
                if eq:
                    res.options.setdefault(key, []).append(value)
                elif i < n:
                    res.options.setdefault(key, []).append(tokens[i])
                    i += 1
                elif key in value_set:
                    raise ArgParseError("option requires an argument", key)
                else:  # optional 缺省
                    res.options.setdefault(key, [])
                continue

            if not allow_unknown:
                raise ArgParseError("unknown option", key)
            res.extra.append(tok)
            continue

        # ---- 短选项簇 -abc / -ovalue / -o value --------------------- #
        chars = tok[1:]
        j = 0
        while j < len(chars):
            ch = chars[j]
            skey = "-" + ch

            if skey in bool_set:
                res.flags[skey] = res.flags.get(skey, 0) + 1
                j += 1
                continue

            if skey in value_set or skey in optval_set:
                rest = chars[j + 1 :]
                if rest:  # -ovalue
                    res.options.setdefault(skey, []).append(rest)
                elif i < n:  # -o value
                    res.options.setdefault(skey, []).append(tokens[i])
                    i += 1
                elif skey in value_set:
                    raise ArgParseError("option requires an argument", skey)
                else:  # optional 缺省
                    res.options.setdefault(skey, [])
                break  # 本簇结束
            if not allow_unknown:
                raise ArgParseError("unknown option", skey)
            res.extra.append(skey)
            j += 1

    return res


# =========================================================================== #
# 链式 API
# =========================================================================== #
class _Spec:
    __slots__ = ("names", "dest", "action", "default", "required", "metavar")

    def __init__(self, names, dest, action, default, required, metavar):
        self.names = names
        self.dest = dest
        self.action = action
        self.default = default
        self.required = required
        self.metavar = metavar

    @property
    def takes_value(self) -> bool:
        return self.action in ("store", "append", "optional")

    @property
    def value_optional(self) -> bool:
        return self.action == "optional"


def _derive_dest(names: tuple[str, ...]) -> str:
    for n in names:  # 优先长名
        if n.startswith("--"):
            return n[2:].replace("-", "_")
    for n in names:  # 否则短名
        if n.startswith("-"):
            return n[1:].replace("-", "_")
    return names[0].replace("-", "_")


class Result:
    """链式解析结果：选项按 dest 成为属性，另有 positionals / extra。"""

    def __init__(self, values: dict, positionals: list[str], extra: list[str]):
        self._values = values
        self.positionals = positionals
        self.extra = extra

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(name) from None

    def get(self, name: str, default=None):
        return self._values.get(name, default)

    def as_dict(self) -> dict:
        return dict(self._values)

    def __repr__(self):
        return (
            f"Result({self._values!r}, "
            f"positionals={self.positionals!r}, extra={self.extra!r})"
        )


class UnixParser:
    """链式 Unix 风格参数解析器（对标 argparse.add_argument）。"""

    def __init__(self, prog: str | None = None, description: str | None = None):
        self.prog = prog or (sys.argv[0] if sys.argv else None)
        self.description = description
        self._specs: list[_Spec] = []
        self._by_name: dict[str, _Spec] = {}
        self._allow_unknown = True
        self._posix = False

    # ---------------- 声明：全部返回 self ---------------- #
    def add_argument(
        self,
        *names,
        dest=None,
        action="store",
        default=None,
        required=False,
        metavar=None,
    ):
        if not names:
            raise ValueError("at least one option name is required")
        for n in names:
            if not n.startswith("-"):
                raise ValueError(f"option name must start with '-': {n!r}")
            if n in self._by_name:
                raise ValueError(f"duplicate option: {n!r}")
        dest = dest or _derive_dest(names)
        if action == "count" and default is None:
            default = 0
        spec = _Spec(tuple(names), dest, action, default, required, metavar)
        self._specs.append(spec)
        for n in names:
            self._by_name[n] = spec
        return self

    # 便捷封装
    def flag(self, *names, dest=None, default=0):
        """布尔 / 计数开关（-v / -vv）。"""
        return self.add_argument(*names, dest=dest, action="count", default=default)

    def option(
        self,
        *names,
        dest=None,
        action="store",
        default=None,
        required=False,
        metavar=None,
    ):
        """必须带值的选项（action: store / append）。"""
        return self.add_argument(
            *names,
            dest=dest,
            action=action,
            default=default,
            required=required,
            metavar=metavar,
        )

    def optional(self, *names, dest=None, default=None, metavar=None):
        """值可缺省的选项，如 -O / -O2。"""
        return self.add_argument(
            *names, dest=dest, action="optional", default=default, metavar=metavar
        )

    # 策略开关
    def allow_unknown(self, yes: bool = True):
        self._allow_unknown = yes
        return self

    def posix(self, yes: bool = True):
        self._posix = yes
        return self

    # ---------------- 解析 ---------------- #
    def parse(self, argv=None) -> Result:
        if argv is None:
            argv = sys.argv[1:]
        tokens = list(argv)
        n = len(tokens)
        i = 0
        only_pos = False

        values = {s.dest: s.default for s in self._specs}
        positionals: list[str] = []
        extra: list[str] = []

        while i < n:
            tok = tokens[i]
            i += 1

            if only_pos or len(tok) <= 1 or tok[0] != "-":
                positionals.append(tok)
                if self._posix and not only_pos:
                    only_pos = True
                continue

            if tok == "--":
                only_pos = True
                continue

            # ---- 长选项 --------------------------------------------- #
            if tok[1] == "-":
                name, eq, val = tok[2:].partition("=")
                key = "--" + name
                spec = self._by_name.get(key)
                if spec is None:
                    if not self._allow_unknown:
                        raise ArgParseError("unknown option", key)
                    extra.append(tok)
                    continue
                if not spec.takes_value:
                    if eq:
                        raise ArgParseError("option does not take a value", key)
                    values[spec.dest] = (values.get(spec.dest) or 0) + 1
                    continue
                if eq:
                    v = val
                elif i < n:
                    v = tokens[i]
                    i += 1
                elif spec.value_optional:
                    v = None
                else:
                    raise ArgParseError("option requires an argument", key)
                self._store(values, spec, v)
                continue

            # ---- 短选项簇 ------------------------------------------- #
            chars = tok[1:]
            j = 0
            while j < len(chars):
                ch = chars[j]
                skey = "-" + ch
                spec = self._by_name.get(skey)
                if spec is None:
                    if not self._allow_unknown:
                        raise ArgParseError("unknown option", skey)
                    extra.append(skey)
                    j += 1
                    continue
                if not spec.takes_value:
                    values[spec.dest] = (values.get(spec.dest) or 0) + 1
                    j += 1
                    continue
                rest = chars[j + 1 :]
                if rest:
                    v = rest
                elif i < n:
                    v = tokens[i]
                    i += 1
                elif spec.value_optional:
                    v = None
                else:
                    raise ArgParseError("option requires an argument", skey)
                self._store(values, spec, v)
                break

        # required 校验
        for s in self._specs:
            if not s.required:
                continue
            v = values.get(s.dest)
            if v is None or (isinstance(v, list) and not v):
                raise ArgParseError("the following argument is required: " + s.names[0])

        return Result(values, positionals, extra)

    # argparse 习惯的别名
    parse_args = parse

    @staticmethod
    def _store(values: dict, spec: _Spec, v):
        if spec.action == "append":
            if values.get(spec.dest) is None:
                values[spec.dest] = []
            values[spec.dest].append(v)
        else:
            values[spec.dest] = v


# =========================================================================== #
# 演示
# =========================================================================== #
if __name__ == "__main__":
    import shlex

    demo = "-vvo out.txt --file=a.c --file b.c -O2 main.o util.o -- --tail"

    print("== 函数式 API ==")
    r1 = parse_unix(
        shlex.split(demo),
        bool_options={"-v", "--verbose"},
        value_options={"-o", "--output", "-f", "--file"},
        optional_value_options={"-O"},
    )
    print(r1)
    print("  verbose =", r1.count("-v"))
    print("  output  =", r1.get("--output"))
    print("  files   =", r1.get_all("--file"))
    print("  extra   =", r1.extra)
    print("  bind    =", r1.bind({"v": "-v", "o": "--output"}))

    print("\n== 链式 API ==")
    p = (
        UnixParser(prog="demo")
        .flag("-v", "--verbose", dest="verbose")
        .option("-o", "--output", dest="output", required=True)
        .option("-f", "--file", dest="files", action="append")
        .optional("-O", dest="level")
        .allow_unknown(True)
    )
    r2 = p.parse(shlex.split(demo))
    print(r2)
    print("  verbose =", r2.verbose)
    print("  output  =", r2.output)
    print("  files   =", r2.files)
    print("  level   =", r2.level)
