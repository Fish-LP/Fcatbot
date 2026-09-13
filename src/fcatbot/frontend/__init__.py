"""Fcatbot 前端层（架构 §2.3）: 控制台、Tab 补全、WebUI、终端渲染。

依赖规则（ADR-0001）: 前端只使用 ``app`` 暴露的公开 API 与事件/命令总线；
不 import ``kernel`` 之外的适配器实现，也不访问应用私有成员（ADR-0012）。
"""

__all__ = [
    "completer",
    "console",
    "term",
    "theme",
    "webui",
]
