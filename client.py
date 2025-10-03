# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 12:38:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-10-03 14:09:12
# @Description  : 喵喵喵, 超多导入(超导)
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import os
import asyncio
import json
from prompt_toolkit.patch_stdout import patch_stdout   # 日志不打断输入行PromptSession
from prompt_toolkit import PromptSession
from pathlib import Path
import sys
from typing import Any, List

from .webclient import NcatbotClient
from .command import Router
from .utils import get_log
from .debugger import start_debug_mode

from .data_models import GroupMessage
from .data_models import PrivateMessage
from .data_models import HeartbeatEvent
from .data_models import LifecycleEvent
from .data_models import GroupRequestEvent
from .data_models import FriendRequestEvent

from .plugins.abc import ConcurrentEventBus as EventBus
from .plugins import Event
from .plugins import PluginManager

from .config import OFFICIAL_HEARTBEAT_EVENT
from .config import OFFICIAL_LIFECYCLE_EVENT
from .config import OFFICIAL_PRIVATE_MESSAGE_EVENT
from .config import OFFICIAL_GROUP_MESSAGE_EVENT
from .config import OFFICIAL_GROUP_REQUEST_EVENT
from .config import OFFICIAL_GROUP_COMMAND_EVENT
from .config import OFFICIAL_FRIEND_REQUEST_EVENT
from .config import OFFICIAL_PRIVATE_COMMAND_EVENT
from .config import OFFICIAL_NOTICE_EVENT
from .config import PLUGINS_DIR

from .data_models import GroupFileUpload
from .data_models import GroupAdminChange
from .data_models import GroupMemberDecrease
from .data_models import GroupMemberIncrease
from .data_models import GroupBan
from .data_models import FriendAdd
from .data_models import GroupRecall
from .data_models import FriendRecall
from .data_models import PokeNotify
from .data_models import LuckyKingNotify
from .data_models import HonorNotify

LOG = get_log('FcatBot')
session = PromptSession()

class BotClient:
    """QQ机器人客户端类.
    
    负责管理WebSocket连接、事件总线和插件系统。

    Attributes:
        event_bus: 事件总线实例
        plugin_sys: 插件加载器实例
        last_heartbeat: 最后一次心跳数据
        ws: WebSocket处理器实例
    """
    def __init__(self, uri: str, token: str = None, command_prefix: tuple[str] = ('/','#'), debug: bool = False):
        self.event_bus = EventBus()
        self.plugin_sys = PluginManager(
            plugin_dirs=[PLUGINS_DIR],
            config_base_dir=Path('./config'),
            data_base_dir=Path('./data'),
            event_bus=self.event_bus,
        )
        self.last_heartbeat:dict = {}
        self.command_prefix = command_prefix
        self.debug = debug
        self.router = Router()
        self._register_builtin()
        auth = None
        if token:
            auth = {
                "Authorization": f"Bearer {token}"
            }
        self.ws = NcatbotClient(
            uri,
            headers = {"Content-Type": "application/json"},
            auth = auth,
        )

    async def close(self):
        LOG.info('准备关闭所有插件...')
        await self.plugin_sys.close()
        LOG.info('准备关闭连接...')
        self.ws.close()
        LOG.info('Fcatbot 关闭完成')

    def link(self):
        '''仅连接'''
        self.ws.start()
        return self.ws

    async def load_plugin(self):
        '''仅加载插件'''
        if not os.path.exists(PLUGINS_DIR):
            os.makedirs(PLUGINS_DIR, exist_ok=True)
        # 设置插件系统的调试模式
        await self.plugin_sys.load_plugins(
            client=self,
            api=self.ws
            )

    def run(self, load_plugins: bool = True):
        """连接并启用 bot 客户端（手动事件循环版本）"""
        LOG.info('准备启动 Fcatbot')
        if self.debug:
            LOG.warning('以 DEBUG 模式启动')
            LOG.warning('推荐配合 DEBUG 级别食用')
            start_debug_mode(self)
            return

        self.ws.start()          # 启动 WebSocket
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 把消息循环做成任务
        main_task = loop.create_task(self.loop(load_plugins))
        # 把控制台循环做成任务
        self._start_console_task()

        try:
            loop.run_until_complete(main_task)   # 这里只 wait 主任务
        except KeyboardInterrupt:
            LOG.info('用户按 Ctrl-C，准备退出……')
        finally:
            # 给事件循环一次清理机会
            if not loop.is_closed():
                loop.run_until_complete(self.close())
                loop.close()

    async def loop(self, load_plugins:bool = True):
        if load_plugins:
            LOG.info('准备加载插件')
            await self.load_plugin()
        listener = self.ws.create_listener(64)
        loop = asyncio.get_running_loop()
        while self.ws.connected:
            try:
                data = await loop.run_in_executor(
                    None, self.ws.get_message, listener
                )
            except KeyboardInterrupt:
                print()
                LOG.info('用户主动触发关闭事件...')
                await self.close()
                return
            except Exception:
                await asyncio.sleep(0)
                continue
            if data:
                # print(data)
                try:
                    await self.on_message(data)
                except Exception as e:
                    LOG.exception("处理消息时发生错误: {e}")
            await asyncio.sleep(0)
        # for data in listener.iter_messages():
        #     print(f"接收到消息: {data}")
        #     if data:
        #         await self.on_message(data)

    async def api(self, action: str, **params) -> dict:
        """调用机器人API.

        Args:
            action: API名称
            **params: API参数

        Returns:
            dict: API响应数据
        """
        result = await self.ws.api(action, **params)
        return result
    
    def publish(self, event: Event) -> List[Any]:
        """发布事件.

        Args:
            event: 要发布的事件

        Returns:
            List[Any]: 所有处理器返回的结果列表
        """
        return self.event_bus.publish(event)
    
    async def on_message(self, data: str):
        """处理接收到的WebSocket消息.

        处理以下消息类型:
            - message/message_sent: 群聊/私聊消息
            - notice: 通知事件  
            - request: 请求事件
            - meta_event: 元事件(生命周期、心跳)

        Args:
            data: 接收到的消息数据(JSON格式)
        """
        msg = data if isinstance(data, dict) else json.loads(data)
        if 'post_type' not in msg:
            return
        _LOG = get_log(f"Bot.{msg['self_id']}")
        if msg["post_type"] == "message" or msg["post_type"] == "message_sent":
            if msg["message_type"] == "group":
                # 群消息
                message = GroupMessage(**msg)
                group_info = await self.api('get_group_info', group_id=message.group_id)
                _LOG.info(f"[{group_info['group_name']}({message.group_id})] {message.sender.nickname}({message.user_id}) -> {message.raw_message}")
                if message.raw_message.startswith(self.command_prefix):
                    self.event_bus.publish(Event(OFFICIAL_GROUP_COMMAND_EVENT, message))
                else:
                    self.event_bus.publish(Event(OFFICIAL_GROUP_MESSAGE_EVENT, message))
            elif msg["message_type"] == "private":
                # 私聊消息
                message = PrivateMessage(**msg)
                _LOG.info(f"Bot.{message.self_id}: [{message.sender.nickname}({message.user_id})] -> {message.raw_message}")
                if message.raw_message.startswith(self.command_prefix):
                    self.event_bus.publish(Event(OFFICIAL_PRIVATE_COMMAND_EVENT, message))
                else:
                    self.event_bus.publish(Event(OFFICIAL_PRIVATE_MESSAGE_EVENT, message))
        elif msg["post_type"] == "notice":
            # 处理不同类型的通知事件
            notice_type = msg.get("notice_type")
            notice_event = None
            
            if notice_type == "group_upload":
                notice_event = GroupFileUpload(**msg)
                _LOG.info(f"群 {notice_event.group_id} 文件上传: {notice_event.file.get('name', 'unknown')}")
            
            elif notice_type == "group_admin":
                notice_event = GroupAdminChange(**msg)
                action = "设置" if notice_event.sub_type == "set" else "取消"
                _LOG.info(f"群 {notice_event.group_id} {action}管理员: {notice_event.user_id}")
            
            elif notice_type == "group_decrease":
                notice_event = GroupMemberDecrease(**msg)
                _LOG.info(f"群 {notice_event.group_id} 成员减少: {notice_event.user_id}")
            
            elif notice_type == "group_increase":
                notice_event = GroupMemberIncrease(**msg)
                _LOG.info(f"群 {notice_event.group_id} 成员增加: {notice_event.user_id}")
            
            elif notice_type == "group_ban":
                notice_event = GroupBan(**msg)
                action = "禁言" if notice_event.sub_type == "ban" else "解除禁言"
                _LOG.info(f"群 {notice_event.group_id} {action}: {notice_event.user_id}")
            
            elif notice_type == "friend_add":
                notice_event = FriendAdd(**msg)
                _LOG.info(f"好友添加: {notice_event.user_id}")
            
            elif notice_type == "group_recall":
                notice_event = GroupRecall(**msg)
                _LOG.info(f"群 {notice_event.group_id} 消息撤回: {notice_event.message_id}")
            
            elif notice_type == "friend_recall":
                notice_event = FriendRecall(**msg)
                _LOG.info(f"好友 {notice_event.user_id} 消息撤回: {notice_event.message_id}")
            
            elif notice_type == "notify":
                sub_type = msg.get("sub_type")
                if sub_type == "poke":
                    notice_event = PokeNotify(**msg)
                    _LOG.info(f"群 {notice_event.group_id} 戳一戳: {notice_event.user_id} -> {notice_event.target_id}")
                elif sub_type == "lucky_king":
                    notice_event = LuckyKingNotify(**msg)
                    _LOG.info(f"群 {notice_event.group_id} 运气王: {notice_event.target_id}")
                elif sub_type == "honor":
                    notice_event = HonorNotify(**msg)
                    _LOG.info(f"群 {notice_event.group_id} 荣誉变更: {notice_event.user_id}")

            if notice_event:
                self.event_bus.publish(Event(OFFICIAL_NOTICE_EVENT, notice_event))
            
        elif msg["post_type"] == "request":
            if msg['request_type'] == 'friend':
                message = FriendRequestEvent(msg)
                self.event_bus.publish(Event(OFFICIAL_FRIEND_REQUEST_EVENT, message))
            elif msg['request_type'] == 'group':
                message = GroupRequestEvent(msg)
                self.event_bus.publish(Event(OFFICIAL_GROUP_REQUEST_EVENT, message))
        elif msg["post_type"] == "meta_event":
            if msg["meta_event_type"] == "lifecycle":
                message = LifecycleEvent(msg)
                _LOG.info(f"机器人 {msg.get('self_id')} 成功启动")
                self.event_bus.publish(Event(OFFICIAL_LIFECYCLE_EVENT, message))
            elif msg["meta_event_type"] == "heartbeat":
                message = HeartbeatEvent(msg)
                try:
                    self.ping = abs(self.last_heartbeat.time + self.last_heartbeat.interval - message.time)
                    self.last_heartbeat: HeartbeatEvent = message
                    if message.status:
                        status: dict = message.status
                        if all(status.values()):
                            _LOG.debug(f'Status: {status}')
                        else:
                            _LOG.error(f'Status: {status}')
                except Exception:
                    self.last_heartbeat: HeartbeatEvent = message
                self.event_bus.publish(Event(OFFICIAL_HEARTBEAT_EVENT, message))
        else:
            _LOG.error("这是一个错误,请反馈给开发者\n" + str(msg))
            return False
        return True # 成功处理
    # ========== 控制台后台任务 ==========
    async def console_loop(self):
        """独立协程：一直读控制台，解析后执行命令。"""
        while self.ws.connected:
            try:
                with patch_stdout(raw=True):
                    cmd = await session.prompt_async('> ', handle_sigint=True)
            except (EOFError, KeyboardInterrupt) as e:          # Ctrl-D / Ctrl-C
                if isinstance(e, EOFError):
                    LOG.info("控制台退出；输入 q 或 quit 可完全关闭机器人")
                    cmd = 'EOF'
                if isinstance(e, KeyboardInterrupt):
                    await self.close()
                    break
            
            if cmd:
                try:
                    await self.command(cmd)
                except Exception as e:
                    LOG.warning("未知命令: %s", cmd)

    def _start_console_task(self):
        """把 console_loop 作为后台任务丢进当前事件循环"""
        loop = asyncio.get_event_loop()
        self._console_task = loop.create_task(self.console_loop())
    
    # ---------- 路由主入口 ----------
    async def command(self, raw: str) -> None:
        await self.router.dispatch(self, raw)
    
    # ---------- 内置命令 ----------
    def _register_builtin(self):
        r = self.router

        @r.register("quit", alias=["q", "exit"], usage="q|quit|exit", desc="优雅退出")
        async def _(ctx: "BotClient", _: List[str]) -> None:
            LOG.info("收到退出指令，准备关闭机器人…")
            await ctx.close()

        @r.register("ping", usage="ping", desc="测试 websocket 连通性")
        async def _(ctx: "BotClient") -> None:
            LOG.info("pong! websocket 状态: %s", ctx.ws.connected)

        @r.register("send", usage="send private|group id 内容", desc="发送消息")
        async def _(ctx: "BotClient", argv: List[str]) -> None:
            if len(argv) < 4:
                LOG.warning("用法: send private|group id 内容")
                return
            msg_type, target, text = argv[1], argv[2], argv[3:]
            text = " ".join(*text)
            if msg_type == "private":
                await ctx.api("send_private_msg", user_id=int(target), message=text)
                LOG.info("已发送私聊消息给 %s: %s", target, text)
            elif msg_type == "group":
                await ctx.api("send_group_msg", group_id=int(target), message=text)
                LOG.info("已发送群消息到 %s: %s", target, text)
            else:
                LOG.warning("send 用法: send private|group id 内容")

        @r.register("reload", usage="reload", desc="重载插件")
        async def _(ctx: "BotClient") -> None:
            LOG.info("重载插件…")
            await ctx.load_plugin()

        @r.register("help", usage="help", desc="查看帮助")
        async def _(ctx: "BotClient") -> None:
            LOG.info("\n" + ctx.router.help_text())