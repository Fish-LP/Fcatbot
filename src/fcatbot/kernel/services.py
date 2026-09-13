"""插件间服务注册表。

设计要点:
- 服务名全局唯一。同名服务重复注册抛 ServiceConflict（可用 force=True 覆盖）。
- 插件通过类属性 provides 声明自己提供的服务。
- 消费方通过 require_service(name) 获取服务实例。
- 插件卸载时其服务自动注销。
- 提供 wait_for(name) 用于跨插件异步依赖（当依赖关系无法通过 depends_on 静态表达时）。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("fcatbot.services")


class ServiceError(RuntimeError):
    """服务注册表异常基类。"""


class ServiceNotFound(ServiceError):
    """请求的服务不存在。"""

    def __init__(self, name: str, *, available: list[str] | None = None):
        msg = f"Service '{name}' not found"
        if available:
            msg += f". Available: {available}"
        super().__init__(msg)
        self.name = name
        self.available = available or []


class ServiceConflict(ServiceError):
    """同名服务已被其他插件注册。"""

    def __init__(self, name: str, existing_provider: str):
        super().__init__(
            f"Service '{name}' already registered by '{existing_provider}'"
        )
        self.name = name
        self.existing_provider = existing_provider


@dataclass
class ServiceInfo:
    name: str
    provider: str
    instance: Any
    version: str = "1.0.0"


class ServiceRegistry:
    """插件间服务注册表。"""

    def __init__(self) -> None:
        self._services: dict[str, ServiceInfo] = {}
        self._by_provider: dict[str, set[str]] = {}
        self._waiters: dict[str, list[asyncio.Future]] = {}

    # ---------- 注册 ----------
    def register(
        self,
        name: str,
        instance: Any,
        *,
        provider: str,
        version: str = "1.0.0",
        force: bool = False,
    ) -> ServiceInfo:
        if name in self._services and not force:
            raise ServiceConflict(name, self._services[name].provider)

        info = ServiceInfo(
            name=name, provider=provider, instance=instance, version=version
        )

        if name in self._services:
            old = self._services[name]
            self._by_provider.get(old.provider, set()).discard(name)

        self._services[name] = info
        self._by_provider.setdefault(provider, set()).add(name)

        # 唤醒等待者
        for fut in self._waiters.pop(name, []):
            if not fut.done():
                fut.set_result(instance)

        log.debug("Service registered: %s@%s by %s", name, version, provider)
        return info

    def unregister_by_provider(self, provider: str) -> list[str]:
        """插件卸载时调用，注销该插件注册的所有服务。"""
        names = list(self._by_provider.pop(provider, set()))
        for name in names:
            self._services.pop(name, None)
        if names:
            log.debug("Unregistered %d service(s) from %s", len(names), provider)
        return names

    # ---------- 查询 ----------
    def resolve(self, name: str) -> Any | None:
        """宽松查询: 不存在返回 None。"""
        info = self._services.get(name)
        return info.instance if info else None

    def require(self, name: str) -> Any:
        """严格查询: 不存在抛 ServiceNotFound。"""
        info = self._services.get(name)
        if info is None:
            raise ServiceNotFound(name, available=list(self._services.keys()))
        return info.instance

    def has(self, name: str) -> bool:
        return name in self._services

    def resolve_info(self, name: str) -> ServiceInfo | None:
        return self._services.get(name)

    def list_services(self) -> list[ServiceInfo]:
        return list(self._services.values())

    def list_by_provider(self, provider: str) -> list[ServiceInfo]:
        names = self._by_provider.get(provider, set())
        return [self._services[n] for n in names if n in self._services]

    async def wait_for(self, name: str, *, timeout: float | None = None) -> Any:
        """异步等待服务注册。"""
        if name in self._services:
            return self._services[name].instance

        fut = asyncio.get_running_loop().create_future()
        self._waiters.setdefault(name, []).append(fut)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            waiters = self._waiters.get(name, [])
            if fut in waiters:
                waiters.remove(fut)
            raise

    # ---------- 从插件声明注册 ----------
    def register_from_plugin(self, plugin: Any) -> None:
        """读取插件的 provides 类属性，注册所有声明的服务。

        provides 值可以是:
        - None            → 用插件实例自身作为服务
        - "attr_name"     → 用 plugin.attr_name 作为服务
        - SomeType        → 实例化 SomeType 并挂到同名短名属性，再注册
        - 其他对象         → 直接作为服务实例
        """
        provides = getattr(type(plugin), "provides", None) or {}
        if not provides:
            return

        for svc_name, contract in provides.items():
            try:
                instance = self._resolve_instance(plugin, svc_name, contract)
                self.register(
                    svc_name,
                    instance,
                    provider=plugin.name,
                    version=getattr(plugin, "version", "1.0.0"),
                )
            except ServiceConflict:
                log.exception(
                    "Service '%s' from plugin '%s' conflicts with existing",
                    svc_name,
                    plugin.name,
                )
            except Exception:
                log.exception(
                    "Failed to register service '%s' from plugin '%s'",
                    svc_name,
                    plugin.name,
                )

    @staticmethod
    def _resolve_instance(plugin: Any, svc_name: str, contract: Any) -> Any:
        short_name = svc_name.split(".")[-1]

        if contract is None:
            return plugin

        if isinstance(contract, str):
            instance = getattr(plugin, contract, None)
            if instance is None:
                raise ServiceError(
                    f"provides['{svc_name}'] points to missing attribute "
                    f"'{contract}' on plugin '{plugin.name}'"
                )
            return instance

        if isinstance(contract, type):
            instance = contract()
            setattr(plugin, short_name, instance)
            return instance

        return contract
