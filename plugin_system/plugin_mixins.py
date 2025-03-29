from typing import Any, Dict, List, Callable, Optional, Tuple, Union, final

from uuid import UUID
from .event import EventBus, Event
from ..utils import TimeTaskScheduler

class EventHandlerMixin:
    """事件处理混入类，提供事件发布和订阅功能。

    该类提供了同步和异步事件发布，以及事件处理器的注册和注销功能。作为一个Mixin类，
    它需要与具有 _event_bus 实例的类配合使用。

    Attributes:
        _event_bus (EventBus): 事件总线实例。
        _event_handlers (List[UUID]): 已注册的事件处理器ID列表。
    """
    
    _event_bus: EventBus
    _event_handlers: List[UUID]
    
    @final
    def publish_sync(self, event: Event) -> List[Any]:
        """同步发布事件。

        Args:
            event (Event): 要发布的事件对象。

        Returns:
            List[Any]: 所有事件处理器的返回值列表。
        """
        return self._event_bus.publish_sync(event)

    @final
    def publish_async(self, event: Event):
        """异步发布事件。

        Args:
            event (Event): 要发布的事件对象。

        Returns:
            None: 这个方法不返回任何值。
        """
        return self._event_bus.publish_async(event)

    @final
    def register_handler(self, event_type: str, handler: Callable[[Event], Any], priority: int = 0) -> UUID:
        """注册一个事件处理器。

        Args:
            event_type (str): 事件类型标识符。
            handler (Callable[[Event], Any]): 事件处理器函数。
            priority (int, optional): 处理器优先级，默认为0。优先级越高，越先执行。

        Returns:
            UUID: 处理器的唯一标识符。
        """
        handler_id = self._event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append(handler_id)
        return handler_id

    @final
    def unregister_handler(self, handler_id: UUID) -> bool:
        """注销一个事件处理器。

        Args:
            handler_id (UUID): 要注销的事件处理器的唯一标识符。

        Returns:
            bool: 如果注销成功返回True，否则返回False。
        """
        if handler_id in self._event_handlers:
            rest = self._event_bus.unsubscribe(handler_id)
            if rest:
                self._event_handlers.remove(handler_id)
                return True
        return False

    @final
    def unregister_handlers(self):
        """注销所有事件处理器。

        Returns:
            None: 这个方法不返回任何值。
        """
        for handler_id in self._event_handlers:
            self._event_bus.unsubscribe(handler_id)

class SchedulerMixin:
    """定时任务相关功能"""
    _time_task_scheduler: TimeTaskScheduler
    
    @final
    def add_scheduled_task(self,
                job_func: Callable,
                name: str,
                interval: Union[str, int, float],
                conditions: Optional[List[Callable[[], bool]]] = None,
                max_runs: Optional[int] = None,
                args: Optional[Tuple] = None,
                kwargs: Optional[Dict] = None,
                args_provider: Optional[Callable[[], Tuple]] = None,
                kwargs_provider: Optional[Callable[[], Dict[str, Any]]] = None) -> bool:
        """添加一个定时任务。

        Args:
            job_func (Callable): 要执行的任务函数。
            name (str): 任务名称。
            interval (Union[str, int, float]): 任务执行的时间间隔。
            conditions (Optional[List[Callable[[], bool]]], optional): 任务执行的条件列表。默认为None。
            max_runs (Optional[int], optional): 任务的最大执行次数。默认为None。
            args (Optional[Tuple], optional): 任务函数的位置参数。默认为None。
            kwargs (Optional[Dict], optional): 任务函数的关键字参数。默认为None。
            args_provider (Optional[Callable[[], Tuple]], optional): 提供任务函数位置参数的函数。默认为None。
            kwargs_provider (Optional[Callable[[], Dict[str, Any]]], optional): 提供任务函数关键字参数的函数。默认为None。

        Returns:
            bool: 如果任务添加成功返回True，否则返回False。
        """
        job_info = {
            'name': name,
            'job_func': job_func,
            'interval': interval,
            'max_runs': max_runs,
            'conditions': conditions or [],
            'args': args,
            'kwargs': kwargs or {},
            'args_provider': args_provider,
            'kwargs_provider': kwargs_provider
        }
        return self._time_task_scheduler.add_job(**job_info)

    @final
    def remove_scheduled_task(self, task_name: str):
        """移除一个定时任务。

        Args:
            task_name (str): 要移除的任务名称。

        Returns:
            bool: 如果任务移除成功返回True，否则返回False。
        """
        return self._time_task_scheduler.remove_job(name=task_name)