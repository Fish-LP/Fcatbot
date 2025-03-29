from typing import Any, Dict, List, Callable, Optional, Tuple, Union, final

from uuid import UUID
from .event import EventBus, Event
from ..utils import TimeTaskScheduler

class EventHandlerMixin:
    
    _event_bus:EventBus
    _event_handlers:List[UUID]
    
    """事件处理相关功能"""
    @final
    def publish_sync(self, event: Event) -> List[Any]:
        return self._event_bus.publish_sync(event)

    @final
    def publish_async(self, event: Event):
        return self._event_bus.publish_async(event)

    @final
    def register_handler(self, event_type: str, handler: Callable[[Event], Any], priority: int = 0) -> UUID:
        handler_id = self._event_bus.subscribe(event_type, handler, priority)
        self._event_handlers.append(handler_id)
        return handler_id

    @final
    def unregister_handler(self, handler_id: UUID) -> bool:
        if handler_id in self._event_handlers:
            rest = self._event_bus.unsubscribe(handler_id)
            if rest:
                self._event_handlers.remove(handler_id)
                return True
        return False

    @final
    def unregister_handlers(self):
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
        job_info = {
            'name': name,
            'job_func': job_func,
            'interval': interval,
            'max_runs': max_runs,
            'run_count': 0,
            'conditions': conditions or [],
            'args': args,
            'kwargs': kwargs or {},
            'args_provider': args_provider,
            'kwargs_provider': kwargs_provider
        }
        return self._time_task_scheduler.add_job(**job_info)

    @final
    def remove_scheduled_task(self, task_name:str):
        return self._time_task_scheduler.remove_job(name = task_name)