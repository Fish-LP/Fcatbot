import json
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING
import aiofiles
from .base import BaseMixin

if TYPE_CHECKING:
    from ..abc import run_any, PluginContext

__all__ = ["AutoConfigMixin"]


class AutoConfigMixin(BaseMixin):
    """
    纯净混入：自动保存/读取 config。
    全程只使用 PluginContext 的 data_dir 与 extra_params，
    生命周期仅依赖 __init__ 与 __close__，绝不污染用户 on_load/on_close
    """

    # ---------- 工具 ----------
    @staticmethod
    def _ns(ctx: "PluginContext") -> Dict[str, Any]:
        """返回混入在 context.extra_params 中的专属命名空间"""
        return ctx.extra_params.setdefault("auto_config", {})

    @classmethod
    def _path(cls, ctx: "PluginContext", filename: str = "config.json") -> Path:
        return ctx.data_dir / filename

    # ---------- 公有 API ----------
    async def ac_save(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        """异步落盘（默认 self.config）"""
        cfg = self.config if cfg is None else cfg
        ctx = self.context
        ns = self._ns(ctx)
        fname = ns.get("file_name", "config.json")
        path = self._path(ctx, fname)
        path.parent.mkdir(parents=True, exist_ok=True)

        encoding = ns.get("encoding", "utf-8")
        async with aiofiles.open(path, "w", encoding=encoding) as f:
            await f.write(json.dumps(cfg, ensure_ascii=False, indent=2))

    async def ac_load(self) -> Dict[str, Any]:
        """异步读盘，无文件返回 {}"""
        ctx = self.context
        ns = self._ns(ctx)
        fname = ns.get("file_name", "config.json")
        path = self._path(ctx, fname)
        if not path.exists():
            return {}
        encoding = ns.get("encoding", "utf-8")
        async with aiofiles.open(path, "r", encoding=encoding) as f:
            return json.loads(await f.read())

    # ---------- 混入生命周期 ----------
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)          # 此时 context & config 已就绪

        ctx = self.context
        ns = self._ns(ctx)

        # 1. 读盘并与当前 config 合并（代码兜底）
        if ns.get("auto_load", True):
            # 必须在事件循环里跑，因此 create_task
            asyncio.create_task(self._ac_merge())

    async def _ac_merge(self) -> None:
        """异步合并磁盘配置"""
        try:
            disk_cfg = await self.ac_load()
            disk_cfg.update(self.config)  # 代码层兜底
            self.config.update(disk_cfg)  # 回写
        except Exception as e:
            self.status.error = e         # 仅记录，不阻断

    def __close__(self, close: bool = False) -> None:
        """同步落盘后再把关闭链传递下去"""
        # 这里用 run_any 把异步的 ac_save 跑成同步
        try:
            run_any(self.ac_save())
        except Exception as e:
            self.status.error = e
        # 继续关闭链
        super().__close__(close=close)