# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-10-03 11:37:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-10-03 11:49:01
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
import inspect
import shlex
from typing import Callable, Dict, List, Optional

from .utils import get_log

LOG = get_log('User')

class Router:
    """轻量级命令路由与参数解析器"""
    def __init__(self) -> None:
        self._cmds: Dict[str, Callable] = {}

    def register(
        self,
        name: str,
        *,
        alias: Optional[List[str]] = None,
        usage: str = "",
        desc: str = "",
    ):
        """装饰器：注册命令"""
        def deco(func: Callable) -> Callable:
            func._usage = usage            # type: ignore
            func._desc = desc              # type: ignore
            self._cmds[name] = func
            for a in alias or []:
                self._cmds[a] = func
            return func
        return deco

    async def dispatch(self, ctx, raw: str) -> None:
        """统一调度入口"""
        raw = raw.strip()
        if not raw:
            return
        # 解析 argv
        try:
            argv = shlex.split(raw)
        except ValueError:
            LOG.warning("命令解析失败，注意引号匹配")
            return
        cmd_name = argv[0].lower()
        handler = self._cmds.get(cmd_name)
        if not handler:
            LOG.warning("未知命令: %s", raw)
            return
        # 执行
        try:
            sig = inspect.signature(handler)
            if "argv" in sig.parameters:
                await handler(ctx, argv)
            else:
                await handler(ctx)
        except Exception as e:
            LOG.exception("命令 %s 执行失败: %s", cmd_name, e)

    def help_text(self) -> str:
        """自动生成帮助"""
        lines = ["内置命令："]
        done = set()
        for name, func in self._cmds.items():
            if func in done:
                continue
            done.add(func)
            lines.append(f"  {name:<12} {getattr(func, '_usage', '')}")
        return "\n".join(lines)