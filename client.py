# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 12:38:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-05-16 20:16:59
# @Description  : 喵喵喵, 超多导入(超导)
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import os
import asyncio
import json
import time

from typing import Any, List

from .ws import WebSocketHandler

from .utils import get_log
from .debugger import start_debug_mode

from .data_models import GroupMessage
from .data_models import PrivateMessage
from .data_models import HeartbeatEvent
from .data_models import LifecycleEvent
from .data_models import GroupRequestEvent
from .data_models import FriendRequestEvent

from .plugin_system import EventBus
from .plugin_system import Event
from .plugin_system import PluginLoader

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

class BotClient:
    """QQ机器人客户端类.
    
    负责管理WebSocket连接、事件总线和插件系统。

    Attributes:
        event_bus: 事件总线实例
        plugin_sys: 插件加载器实例
        last_heartbeat: 最后一次心跳数据
        ws: WebSocket处理器实例
    """
    def __init__(self, uri: str, token: str = None, command_prefix: tuple[str] = ('/','#')):
        self.event_bus = EventBus()
        self.plugin_sys = PluginLoader(self.event_bus)
        self.last_heartbeat:dict = {}
        self.command_prefix = command_prefix
        
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.ws = WebSocketHandler(
            uri,
            headers,
            message_handler = self.on_message,
        )

    def exit(self):
        self.close()

    def close(self):
        LOG.info('用户主动触发关闭事件...')
        LOG.info('准备关闭所有插件...')
        self.plugin_sys.unload_all()
        LOG.info('Fcatbot 关闭完成')

    def link(self):
        '''仅连接'''
        self.ws.start()
        return self.ws

    def load_plugin(self, debug = False):
        '''仅加载插件'''
        if not os.path.exists(PLUGINS_DIR):
            os.makedirs(PLUGINS_DIR, exist_ok=True)
        # 设置插件系统的调试模式
        self.plugin_sys.set_debug(debug)
        asyncio.run(self.plugin_sys.load_plugins(api=self.ws))

    def run(self, load_plugins:bool = True, debug = False):
        '''连接并启用bot客户端'''
        if load_plugins:
            LOG.info('准备加载插件')
            self.load_plugin(debug)
        LOG.info('准备启动Fcatbot')
        if debug:
            LOG.warning('以 DEBUG 模式启动')
            LOG.warning('推荐配合 DEGUB 级别食用')
            start_debug_mode(self)
        else:
            try:
                self.ws.start()  # 启动 WebSocket 连接
                while True:
                    time.sleep(0)
            except KeyboardInterrupt:
                print()
                self.close()
                exit(0)

    async def api(self, action: str, **params) -> dict:
        """调用机器人API.

        Args:
            action: API名称
            **params: API参数

        Returns:
            dict: API响应数据
        """
        result = await self.ws.api(action, params, wait=True)
        return result
    
    def publish_sync(self, event: Event) -> List[Any]:
        """同步发布事件.

        Args:
            event: 要发布的事件

        Returns:
            List[Any]: 所有处理器返回的结果列表
        """
        return self.event_bus.publish_sync(event)

    async def publish_async(self, event: Event) -> List[Any]:
        """异步发布事件.

        Args:
            event: 要发布的事件

        Returns:
            List[Any]: 所有处理器返回的结果列表
        """
        return await self.event_bus.publish_async(event)
    
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
        msg = json.loads(data)
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
                    await self.event_bus.publish_async(Event(OFFICIAL_GROUP_COMMAND_EVENT, message))
                else:
                    await self.event_bus.publish_async(Event(OFFICIAL_GROUP_MESSAGE_EVENT, message))
            elif msg["message_type"] == "private":
                # 私聊消息
                message = PrivateMessage(**msg)
                _LOG.info(f"Bot.{message.self_id}: [{message.sender.nickname}({message.user_id})] -> {message.raw_message}")
                if message.raw_message.startswith(self.command_prefix):
                    await self.event_bus.publish_async(Event(OFFICIAL_PRIVATE_COMMAND_EVENT, message))
                else:
                    await self.event_bus.publish_async(Event(OFFICIAL_PRIVATE_MESSAGE_EVENT, message))
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
                await self.event_bus.publish_async(Event(OFFICIAL_NOTICE_EVENT, notice_event))
            
        elif msg["post_type"] == "request":
            if msg['request_type'] == 'friend':
                message = FriendRequestEvent(msg)
                await self.event_bus.publish_async(Event(OFFICIAL_FRIEND_REQUEST_EVENT, message))
            elif msg['request_type'] == 'group':
                message = GroupRequestEvent(msg)
                await self.event_bus.publish_async(Event(OFFICIAL_GROUP_REQUEST_EVENT, message))
        elif msg["post_type"] == "meta_event":
            if msg["meta_event_type"] == "lifecycle":
                message = LifecycleEvent(msg)
                _LOG.info(f"机器人 {msg.get('self_id')} 成功启动")
                await self.event_bus.publish_async(Event(OFFICIAL_LIFECYCLE_EVENT, message))
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
                await self.event_bus.publish_async(Event(OFFICIAL_HEARTBEAT_EVENT, message))
        else:
            _LOG.error("这是一个错误,请反馈给开发者\n" + str(msg))
            return False
        return True # 成功处理