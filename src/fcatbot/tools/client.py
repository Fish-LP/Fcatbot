import functools
import inspect
import typing
from abc import ABC, ABCMeta, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Dict, Generic, Optional, TypeVar

T = TypeVar("T")


def _extract_invoke_return(cls: type) -> Any:
    for klass in cls.__mro__:
        # FIX: 避免在 APIClient 尚未进入全局命名空间时直接引用它
        if klass.__name__ == "APIClient":
            continue
        for base in getattr(klass, "__orig_bases__", ()):
            origin = typing.get_origin(base)
            # FIX: 同样使用名称比较
            if origin is not None and getattr(origin, "__name__", None) == "APIClient":
                args = typing.get_args(base)
                if args:
                    return args[0]
    return Any


@dataclass
class ApiRequest:
    activity: str
    data: Dict[str, Any] = field(default_factory=dict)
    headers: Optional[Dict[str, str]] = None


class ApiMeta(ABCMeta):
    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if not bases:
            return cls

        invoke_return = _extract_invoke_return(cls)
        processed = set()
        excluded = {"invoke", "call"}
        # 子类可声明不参与自动包装的方法名（如生命周期/通道绑定等同步方法）。
        excluded.update(getattr(cls, "_api_no_wrap", ()) or ())

        # 从最派生类到最基类遍历: 同一方法名只包装「实际生效的那份定义」。
        # 反序（基类优先）时，基类定义先被标记为 processed，子类覆写的版本会被跳过，
        # 于是 MRO 查找命中未包装的子类方法 → 静默返回原始 (action, params) 元组。
        for klass in cls.__mro__:
            if klass is object or klass.__name__ == "APIClient":
                continue
            for attr_name, attr_value in list(klass.__dict__.items()):
                if attr_name in processed:
                    continue
                if attr_name.startswith("_") or attr_name in excluded:
                    continue

                raw = attr_value
                if isinstance(attr_value, (staticmethod, classmethod)):
                    raw = attr_value.__func__
                if not inspect.isfunction(raw):
                    continue

                # 继承自基类的包装函数不再重复包装: 二次包装会把 invoke 的返回
                # 值（可能是 str）当成 action 再次 invoke。
                if getattr(raw, "__api_wrapped__", False):
                    processed.add(attr_name)
                    continue

                wrapper = mcs._make_wrapper(raw)
                if wrapper is not None:
                    wrapper.__annotations__["return"] = Awaitable[invoke_return]
                    functools.update_wrapper(wrapper, raw)
                    setattr(wrapper, "__api_wrapped__", True)

                    if isinstance(attr_value, staticmethod):
                        setattr(cls, attr_name, staticmethod(wrapper))
                    elif isinstance(attr_value, classmethod):
                        setattr(cls, attr_name, classmethod(wrapper))  # type: ignore[arg-type]
                    else:
                        setattr(cls, attr_name, wrapper)

                    processed.add(attr_name)

        return cls

    @staticmethod
    def _make_wrapper(orig):
        is_coro = inspect.iscoroutinefunction(orig)

        if is_coro:
            # FIX: 使用字符串 "APIClient" 作为前向引用，避免类尚未定义时的 NameError
            async def wrapper(self: "APIClient", *args, **kwargs):
                result = await orig(self, *args, **kwargs)
                return await self._dispatch_result(result)

            return wrapper
        else:

            async def wrapper(self: "APIClient", *args, **kwargs):
                result = orig(self, *args, **kwargs)
                return await self._dispatch_result(result)

            return wrapper


class APIClient(ABC, Generic[T], metaclass=ApiMeta):
    @abstractmethod
    async def invoke(self, request: ApiRequest) -> T:
        pass

    async def call(
        self,
        activity: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> T:
        return await self.invoke(ApiRequest(activity, data or {}, headers))

    async def _dispatch_result(self, result: Any) -> T:
        if isinstance(result, ApiRequest):
            return await self.invoke(result)
        elif isinstance(result, str):
            return await self.invoke(ApiRequest(result))
        elif isinstance(result, tuple) and 1 <= len(result) <= 3:
            return await self.invoke(ApiRequest(*result))
        else:
            return result  # type: ignore[return-value]

        # def __getattr__(self, name: str) -> Any:
        #     if name.startswith("_"):
        #         raise AttributeError(
        #             f"{self.__class__.__name__!r} object has no attribute {name!r}"
        #         )

        #     async def method(**kwargs) -> T:
        #         return await self.invoke(ApiRequest(name, kwargs))

        # return types.MethodType(method, self)
