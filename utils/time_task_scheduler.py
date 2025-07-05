# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-03-21 20:40:12
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-06-30 21:49:14
# @Description  : 增强版异步任务调度器 - 支持任务依赖和Cron表达式
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
import asyncio
import re
import logging
import functools
from typing import Callable, Optional, Dict, Any, Union, Awaitable, Coroutine, List, Set
from datetime import datetime, timedelta
from enum import Enum
# import croniter

logger = logging.getLogger('EnhancedTaskScheduler')


class TaskType(Enum):
    """任务类型枚举"""
    INTERVAL = 'interval'
    DAILY = 'daily'
    SINGLE = 'single'
    CRON = 'cron'  # 新增Cron类型


class AsyncTask:
    """异步任务类，封装单个定时任务的所有属性和行为"""
    
    def __init__(
        self,
        name: str,
        action: Union[Callable, Coroutine, Awaitable],
        task_type: TaskType,
        schedule_value: Any,
        *,
        static_params: Optional[Dict[str, Any]] = None,
        dynamic_params: Optional[Callable[[], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]] = None,
        condition: Optional[Callable[["AsyncTask"], Union[bool, Awaitable[bool]]]] = None,
        max_runs: Optional[int] = None,
        dependencies: Optional[List[str]] = None
    ):
        """
        初始化异步任务
        
        Args:
            name (str): 任务唯一标识
            action (Union[Callable, Coroutine, Awaitable]): 任务执行函数
            task_type (TaskType): 任务类型
            schedule_value (Any): 调度值
            static_params (Optional[Dict]): 静态参数
            dynamic_params (Optional[Callable]): 动态参数生成函数
            condition (Optional[Callable]): 执行条件函数，接受任务实例作为参数
            max_runs (Optional[int]): 最大执行次数
            dependencies (Optional[List[str]]): 依赖的任务名称列表
        """
        self.name = name
        self.action = action
        self.task_type = task_type
        self.schedule_value = schedule_value
        self.static_params = static_params or {}
        self.dynamic_params = dynamic_params
        self.condition = condition
        self.max_runs = max_runs
        self.dependencies = dependencies or []
        
        # 运行时状态
        self.run_count = 0
        self.active = True
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.last_error: Optional[Exception] = None
        self.dependency_met = False  # 依赖是否满足
        
        # 验证至少有一个触发条件
        if task_type != TaskType.SINGLE and not schedule_value and not condition:
            raise ValueError("任务必须至少有一个触发条件（schedule_value 或 condition）")
        
        # 计算首次执行时间
        self._calculate_next_run()
    
    def _calculate_next_run(self) -> None:
        """计算下次执行时间"""
        now = datetime.now()
        
        if self.task_type == TaskType.INTERVAL:
            # 间隔任务
            if not self.schedule_value:
                # 如果没有设置间隔时间，则使用默认值（1小时）
                self.schedule_value = timedelta(hours=1)
                logger.warning(f"任务 {self.name} 未设置间隔时间，使用默认值 1小时")
            
            interval_seconds = self._parse_interval(self.schedule_value)
            self.next_run = now + timedelta(seconds=interval_seconds)
        
        elif self.task_type == TaskType.DAILY:
            # 每日任务
            if not self.schedule_value:
                # 如果没有设置时间，则使用默认值（午夜）
                self.schedule_value = "00:00"
                logger.warning(f"任务 {self.name} 未设置每日时间，使用默认值 00:00")
            
            if not isinstance(self.schedule_value, str):
                raise ValueError("每日任务需要字符串格式的时间")
            
            # 解析时间字符串
            parts = self.schedule_value.split(':')
            hour, minute = int(parts[0]), int(parts[1])
            second = int(parts[2]) if len(parts) > 2 else 0
            
            # 计算今天执行时间
            today_run = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
            
            # 如果今天时间已过，则安排到明天
            if today_run < now:
                self.next_run = today_run + timedelta(days=1)
            else:
                self.next_run = today_run
        
        elif self.task_type == TaskType.SINGLE:
            # 一次性任务
            if not self.schedule_value:
                # 如果没有设置时间，则使用默认值（立即执行）
                self.schedule_value = datetime.now()
                logger.warning(f"任务 {self.name} 未设置执行时间，立即执行")
            
            if isinstance(self.schedule_value, datetime):
                self.next_run = self.schedule_value
            elif isinstance(self.schedule_value, (int, float)):
                self.next_run = now + timedelta(seconds=self.schedule_value)
            else:
                raise ValueError("一次性任务需要datetime对象或秒数")
                
        # elif self.task_type == TaskType.CRON:
        #     # Cron表达式任务
        #     if not self.schedule_value:
        #         # 如果没有设置Cron表达式，则使用默认值（每分钟执行）
        #         self.schedule_value = "* * * * *"
        #         logger.warning(f"任务 {self.name} 未设置Cron表达式，使用默认值 '* * * * *'")
            
        #     try:
        #         # 使用croniter计算下次执行时间
        #         cron = croniter.croniter(self.schedule_value, now)
        #         self.next_run = cron.get_next(datetime)
        #     except Exception as e:
        #         raise ValueError(f"无效的Cron表达式: {self.schedule_value} - {str(e)}")
    
    async def should_run(self, scheduler: "AsyncTaskScheduler") -> bool:
        """检查任务是否应该执行（异步）"""
        # 检查激活状态
        if not self.active:
            return False
        
        # 检查执行次数限制
        if self.max_runs is not None and self.run_count >= self.max_runs:
            return False
        
        # 检查执行时间
        if self.next_run is None or datetime.now() < self.next_run:
            return False
        
        # 检查任务依赖
        if self.dependencies:
            # 检查所有依赖任务是否至少执行过一次
            for dep_name in self.dependencies:
                dep_task = await scheduler.get_task(dep_name)
                if not dep_task or dep_task.run_count == 0:
                    return False
                # 对于周期性任务，检查依赖任务是否在本周期内执行过
                if (self.last_run and dep_task.last_run and 
                    dep_task.last_run < self.last_run):
                    return False
        
        # 检查执行条件
        if self.condition:
            try:
                # 支持同步和异步条件函数
                if asyncio.iscoroutinefunction(self.condition):
                    result = await self.condition(self)  # 传递任务实例
                else:
                    result = self.condition(self)  # 传递任务实例
                
                if not result:
                    return False
            except Exception as e:
                logger.error(f"任务 {self.name} 条件检查失败: {str(e)}")
                return False
        
        return True
    
    async def execute(self) -> bool:
        """执行任务（异步）"""
        try:
            # 合并参数
            params = {**self.static_params}
            if self.dynamic_params:
                try:
                    # 支持同步和异步参数生成
                    if asyncio.iscoroutinefunction(self.dynamic_params):
                        dynamic_args = await self.dynamic_params()
                    else:
                        dynamic_args = self.dynamic_params()
                    
                    params.update(dynamic_args)
                except Exception as e:
                    logger.error(f"任务 {self.name} 动态参数生成失败: {str(e)}")
            
            # 执行任务
            if asyncio.iscoroutinefunction(self.action):
                await self.action(**params)
            elif asyncio.iscoroutine(self.action):
                await self.action
            else:
                # 同步函数在事件循环中执行
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, functools.partial(self.action, **params))
            
            # 更新状态
            self.last_run = datetime.now()
            self.run_count += 1
            self.last_error = None
            
            # 一次性任务执行后禁用
            if self.task_type == TaskType.SINGLE:
                self.active = False
            
            # 重新计算下次执行时间（除一次性任务外）
            if self.task_type != TaskType.SINGLE:
                self._calculate_next_run()
            
            logger.info(f"任务 {self.name} 执行成功")
            return True
        
        except Exception as e:
            self.last_error = e
            logger.error(f"任务 {self.name} 执行失败: {str(e)}")
            return False
    
    def update_params(
        self,
        static_params: Optional[Dict[str, Any]] = None,
        dynamic_params: Optional[Callable[[], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]] = None
    ) -> None:
        """更新任务参数"""
        if static_params is not None:
            self.static_params = static_params
        
        if dynamic_params is not None:
            self.dynamic_params = dynamic_params
    
    def pause(self) -> None:
        """暂停任务"""
        self.active = False
    
    def resume(self) -> None:
        """恢复任务"""
        self.active = True
        # 重新计算下次执行时间
        self._calculate_next_run()
    
    def get_info(self) -> Dict[str, Any]:
        """获取任务信息"""
        return {
            'name': self.name,
            'type': self.task_type.value,
            'active': self.active,
            'last_run': self.last_run,
            'next_run': self.next_run,
            'run_count': self.run_count,
            'max_runs': self.max_runs,
            'static_params': self.static_params,
            'has_dynamic_params': self.dynamic_params is not None,
            'has_condition': self.condition is not None,
            'dependencies': self.dependencies,
            'last_error': str(self.last_error) if self.last_error else None
        }
    
    @staticmethod
    def _parse_interval(interval: Union[str, int, float, timedelta]) -> float:
        """
        解析间隔时间为秒数
        
        Args:
            interval (Union[str, int, float, timedelta]): 间隔时间

        Returns:
            float: 总秒数
        """
        # 处理timedelta对象
        if isinstance(interval, timedelta):
            return interval.total_seconds()
        
        # 处理数字
        if isinstance(interval, (int, float)):
            return float(interval)
        
        # 单位映射
        units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
        
        # 单位组合格式 (如2h30m)
        if re.match(r'^[\d.]+[dhms]$', interval, re.IGNORECASE):
            num = float(re.search(r'[\d.]+', interval).group())
            unit = re.search(r'[dhms]', interval, re.IGNORECASE).group().lower()
            return num * units[unit]

        # 多单位组合格式 (如2h30m15s)
        multi_unit_match = re.findall(r'([\d.]+)\s*([dhms])', interval, re.IGNORECASE)
        if multi_unit_match:
            total_seconds = 0.0
            for num, unit in multi_unit_match:
                total_seconds += float(num) * units[unit.lower()]
            return total_seconds

        # 冒号分隔格式 (如01:30:00)
        if ':' in interval:
            parts = list(map(float, interval.split(':')))
            if len(parts) > 4:
                raise ValueError("时间格式过于复杂")
            
            # 倒序处理(秒、分、时、天)
            multipliers = [1, 60, 3600, 86400]
            total_seconds = 0.0
            for i, part in enumerate(reversed(parts)):
                if i >= len(multipliers):
                    break
                total_seconds += part * multipliers[i]
            return total_seconds

        # 自然语言格式 (如2天3小时5秒)
        lang_match = re.findall(r'(\d+)\s*(天|小时|分钟|秒)', interval)
        if lang_match:
            time_map = {'天': 86400, '小时': 3600, '分钟': 60, '秒': 1}
            total_seconds = 0.0
            for num, unit in lang_match:
                total_seconds += int(num) * time_map[unit]
            return total_seconds

        # 纯数字格式 (默认为秒)
        try:
            return float(interval)
        except ValueError:
            raise ValueError(f"无法识别的间隔时间格式: {interval}")


class AsyncTaskScheduler:
    """异步任务调度器，管理多个异步任务"""
    
    def __init__(self, max_concurrent: int = 10):
        """
        初始化调度器
        
        Args:
            max_concurrent (int): 最大并发任务数
        """
        self.tasks: Dict[str, AsyncTask] = {}
        self.scheduler_task: Optional[asyncio.Task] = None
        self.running = False
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.lock = asyncio.Lock()
    
    async def add_interval_task(
        self,
        name: str,
        action: Union[Callable, Coroutine, Awaitable],
        interval: Union[str, int, float, timedelta, None] = None,
        *,
        static_params: Optional[Dict[str, Any]] = None,
        dynamic_params: Optional[Callable[[], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]] = None,
        condition: Optional[Callable[[AsyncTask], Union[bool, Awaitable[bool]]]] = None,
        max_runs: Optional[int] = None,
        dependencies: Optional[List[str]] = None
    ) -> AsyncTask:
        """
        添加间隔执行任务
        
        Args:
            name (str): 任务唯一标识
            action (Union[Callable, Coroutine, Awaitable]): 任务执行函数
            interval (Union[str, int, float, timedelta, None]): 间隔时间（可选）
            static_params (Optional[Dict]): 静态参数
            dynamic_params (Optional[Callable]): 动态参数生成函数
            condition (Optional[Callable]): 执行条件函数
            max_runs (Optional[int]): 最大执行次数
            dependencies (Optional[List[str]]): 依赖的任务名称列表

        Returns:
            AsyncTask: 创建的任务对象
        """
        async with self.lock:
            if name in self.tasks:
                raise ValueError(f"任务名称 '{name}' 已存在")
            
            task = AsyncTask(
                name=name,
                action=action,
                task_type=TaskType.INTERVAL,
                schedule_value=interval,
                static_params=static_params,
                dynamic_params=dynamic_params,
                condition=condition,
                max_runs=max_runs,
                dependencies=dependencies
            )
            
            self.tasks[name] = task
            logger.info(f"已添加间隔任务: {name}")
            return task
    
    async def add_daily_task(
        self,
        name: str,
        action: Union[Callable, Coroutine, Awaitable],
        time_str: Optional[str] = None,
        *,
        static_params: Optional[Dict[str, Any]] = None,
        dynamic_params: Optional[Callable[[], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]] = None,
        condition: Optional[Callable[[AsyncTask], Union[bool, Awaitable[bool]]]] = None,
        max_runs: Optional[int] = None,
        dependencies: Optional[List[str]] = None
    ) -> AsyncTask:
        """
        添加每日定点任务
        
        Args:
            name (str): 任务唯一标识
            action (Union[Callable, Coroutine, Awaitable]): 任务执行函数
            time_str (Optional[str]): 每日执行时间（可选）
            static_params (Optional[Dict]): 静态参数
            dynamic_params (Optional[Callable]): 动态参数生成函数
            condition (Optional[Callable]): 执行条件函数
            max_runs (Optional[int]): 最大执行次数
            dependencies (Optional[List[str]]): 依赖的任务名称列表

        Returns:
            AsyncTask: 创建的任务对象
        """
        async with self.lock:
            if name in self.tasks:
                raise ValueError(f"任务名称 '{name}' 已存在")
            
            task = AsyncTask(
                name=name,
                action=action,
                task_type=TaskType.DAILY,
                schedule_value=time_str,
                static_params=static_params,
                dynamic_params=dynamic_params,
                condition=condition,
                max_runs=max_runs,
                dependencies=dependencies
            )
            
            self.tasks[name] = task
            logger.info(f"已添加每日任务: {name} 时间: {time_str or '未设置，使用默认值'}")
            return task
    
    async def add_single_task(
        self,
        name: str,
        action: Union[Callable, Coroutine, Awaitable],
        run_at: Union[str, datetime, int, float, None] = None,
        *,
        static_params: Optional[Dict[str, Any]] = None,
        dynamic_params: Optional[Callable[[], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]] = None,
        condition: Optional[Callable[[AsyncTask], Union[bool, Awaitable[bool]]]] = None,
        dependencies: Optional[List[str]] = None
    ) -> AsyncTask:
        """
        添加一次性任务
        
        Args:
            name (str): 任务唯一标识
            action (Union[Callable, Coroutine, Awaitable]): 任务执行函数
            run_at (Union[str, datetime, int, float, None]): 执行时间（可选）
            static_params (Optional[Dict]): 静态参数
            dynamic_params (Optional[Callable]): 动态参数生成函数
            condition (Optional[Callable]): 执行条件函数
            dependencies (Optional[List[str]]): 依赖的任务名称列表

        Returns:
            AsyncTask: 创建的任务对象
        """
        # 处理不同格式的时间输入
        if isinstance(run_at, str):
            if re.match(r'^\d{4}:\d{2}:\d{2}-\d{2}:\d{2}:\d{2}$', run_at):
                dt_str = run_at.replace(':', '-', 2).replace('-', ' ', 1)
                run_at = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
            else:
                run_at = datetime.strptime(run_at, "%Y-%m-%d %H:%M:%S")
        
        async with self.lock:
            if name in self.tasks:
                raise ValueError(f"任务名称 '{name}' 已存在")
            
            task = AsyncTask(
                name=name,
                action=action,
                task_type=TaskType.SINGLE,
                schedule_value=run_at,
                static_params=static_params,
                dynamic_params=dynamic_params,
                condition=condition,
                max_runs=1,  # 一次性任务固定执行一次
                dependencies=dependencies
            )
            
            self.tasks[name] = task
            logger.info(f"已添加一次性任务: {name} 时间: {run_at or '未设置，立即执行'}")
            return task
    
    # async def add_cron_task(
    #     self,
    #     name: str,
    #     action: Union[Callable, Coroutine, Awaitable],
    #     cron_expression: str,
    #     *,
    #     static_params: Optional[Dict[str, Any]] = None,
    #     dynamic_params: Optional[Callable[[], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]] = None,
    #     condition: Optional[Callable[[AsyncTask], Union[bool, Awaitable[bool]]]] = None,
    #     max_runs: Optional[int] = None,
    #     dependencies: Optional[List[str]] = None
    # ) -> AsyncTask:
    #     """
    #     添加Cron表达式任务
        
    #     Args:
    #         name (str): 任务唯一标识
    #         action (Union[Callable, Coroutine, Awaitable]): 任务执行函数
    #         cron_expression (str): Cron表达式
    #         static_params (Optional[Dict]): 静态参数
    #         dynamic_params (Optional[Callable]): 动态参数生成函数
    #         condition (Optional[Callable]): 执行条件函数
    #         max_runs (Optional[int]): 最大执行次数
    #         dependencies (Optional[List[str]]): 依赖的任务名称列表

    #     Returns:
    #         AsyncTask: 创建的任务对象
    #     """
    #     async with self.lock:
    #         if name in self.tasks:
    #             raise ValueError(f"任务名称 '{name}' 已存在")
            
    #         task = AsyncTask(
    #             name=name,
    #             action=action,
    #             task_type=TaskType.CRON,
    #             schedule_value=cron_expression,
    #             static_params=static_params,
    #             dynamic_params=dynamic_params,
    #             condition=condition,
    #             max_runs=max_runs,
    #             dependencies=dependencies
    #         )
            
    #         self.tasks[name] = task
    #         logger.info(f"已添加Cron任务: {name} Cron表达式: {cron_expression}")
    #         return task
    
    async def remove_task(self, name: str) -> bool:
        """
        移除任务
        
        Args:
            name (str): 任务名称
            
        Returns:
            bool: 是否成功移除
        """
        async with self.lock:
            if name in self.tasks:
                del self.tasks[name]
                logger.info(f"已移除任务: {name}")
                return True
            return False
    
    async def pause_task(self, name: str) -> bool:
        """
        暂停任务
        
        Args:
            name (str): 任务名称
            
        Returns:
            bool: 是否成功暂停
        """
        async with self.lock:
            task = self.tasks.get(name)
            if task:
                task.pause()
                logger.info(f"已暂停任务: {name}")
                return True
            return False
    
    async def resume_task(self, name: str) -> bool:
        """
        恢复任务
        
        Args:
            name (str): 任务名称
            
        Returns:
            bool: 是否成功恢复
        """
        async with self.lock:
            task = self.tasks.get(name)
            if task:
                task.resume()
                logger.info(f"已恢复任务: {name}")
                return True
            return False
    
    async def update_task_params(
        self,
        name: str,
        static_params: Optional[Dict[str, Any]] = None,
        dynamic_params: Optional[Callable[[], Union[Dict[str, Any], Awaitable[Dict[str, Any]]]]] = None
    ) -> bool:
        """
        更新任务参数
        
        Args:
            name (str): 任务名称
            static_params (Optional[Dict]): 新的静态参数
            dynamic_params (Optional[Callable]): 新的动态参数生成函数
            
        Returns:
            bool: 是否更新成功
        """
        async with self.lock:
            task = self.tasks.get(name)
            if task:
                task.update_params(static_params, dynamic_params)
                logger.info(f"已更新任务参数: {name}")
                return True
            return False
    
    async def get_task(self, name: str) -> Optional[AsyncTask]:
        """
        获取任务对象
        
        Args:
            name (str): 任务名称
            
        Returns:
            Optional[AsyncTask]: 任务对象
        """
        async with self.lock:
            return self.tasks.get(name)
    
    async def list_tasks(self) -> Dict[str, AsyncTask]:
        """
        获取所有任务
        
        Returns:
            Dict[str, AsyncTask]: 任务名称到任务对象的映射
        """
        async with self.lock:
            return self.tasks.copy()
    
    async def start(self) -> None:
        """启动调度器"""
        if self.running:
            logger.warning("调度器已在运行中")
            return
        
        self.running = True
        self.scheduler_task = asyncio.create_task(self._run_scheduler())
        logger.info("异步任务调度器已启动")
    
    async def stop(self) -> None:
        """停止调度器"""
        if not self.running:
            logger.warning("调度器未运行")
            return
        
        self.running = False
        if self.scheduler_task and not self.scheduler_task.done():
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("异步任务调度器已停止")
    
    async def _run_scheduler(self) -> None:
        """调度器主循环（异步）"""
        while self.running:
            try:
                # 复制任务列表以避免迭代过程中修改
                async with self.lock:
                    tasks = list(self.tasks.values())
                
                # 检查每个任务是否需要执行
                for task in tasks:
                    if await task.should_run(self):  # 传递调度器实例以检查依赖
                        # 使用信号量控制并发
                        async with self.semaphore:
                            # 创建异步任务执行
                            asyncio.create_task(self._execute_task(task))
                
                # 计算最短等待时间
                next_run_time = min(
                    (task.next_run for task in tasks if task.active and task.next_run),
                    default=None
                )
                
                # 计算需要等待的时间
                sleep_time = 0.5  # 默认等待时间
                if next_run_time:
                    now = datetime.now()
                    if next_run_time > now:
                        sleep_time = min((next_run_time - now).total_seconds(), 1.0)
                
                # 异步等待
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                logger.info("调度器被取消")
                break
            except Exception as e:
                logger.error(f"调度器运行时错误: {str(e)}")
                await asyncio.sleep(1)  # 防止错误循环
    
    async def _execute_task(self, task: AsyncTask) -> None:
        """执行单个任务（带错误处理）"""
        try:
            await task.execute()
        except Exception as e:
            logger.error(f"任务 {task.name} 执行过程中发生错误: {str(e)}")
    
    async def __aenter__(self):
        """支持异步上下文管理器"""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        """支持异步上下文管理器"""
        await self.stop()


# # 使用示例
# async def main():
#     # 示例任务：数据收集
#     async def data_collection_task():
#         print("执行数据收集任务...")
#         await asyncio.sleep(1)
#         print("数据收集完成")
    
#     # 示例任务：数据处理（依赖数据收集）
#     async def data_processing_task():
#         print("执行数据处理任务...")
#         await asyncio.sleep(1.5)
#         print("数据处理完成")
    
#     # 示例任务：报告生成（依赖数据处理）
#     async def report_generation_task():
#         print("执行报告生成任务...")
#         await asyncio.sleep(0.8)
#         print("报告生成完成")
    
#     # 示例任务：备份（Cron表达式）
#     async def backup_task():
#         print("执行备份任务...")
#         await asyncio.sleep(2)
#         print("备份完成")
    
#     # 创建调度器（使用异步上下文管理器）
#     async with AsyncTaskScheduler(max_concurrent=5) as scheduler:
#         # 添加数据收集任务（每30秒执行）
#         await scheduler.add_interval_task(
#             name="data_collection",
#             action=data_collection_task,
#             interval=30
#         )
        
#         # 添加数据处理任务（依赖数据收集）
#         await scheduler.add_interval_task(
#             name="data_processing",
#             action=data_processing_task,
#             interval=35,
#             dependencies=["data_collection"]  # 依赖数据收集任务
#         )
        
#         # 添加报告生成任务（每天下午5点执行，依赖数据处理）
#         await scheduler.add_daily_task(
#             name="report_generation",
#             action=report_generation_task,
#             time_str="17:00",
#             dependencies=["data_processing"]  # 依赖数据处理任务
#         )
        
#         # # 添加备份任务（使用Cron表达式：每天凌晨1点执行）
#         # await scheduler.add_cron_task(
#         #     name="backup",
#         #     action=backup_task,
#         #     cron_expression="0 1 * * *"  # 每天凌晨1点
#         # )
        
#         # 添加一次性任务（依赖报告生成任务）
#         await scheduler.add_single_task(
#             name="final_notification",
#             action=lambda: print("所有任务完成，发送通知！"),
#             dependencies=["report_generation"]
#         )
        
#         # 运行10分钟
#         await asyncio.sleep(600)

# if __name__ == "__main__":
#     asyncio.run(main())