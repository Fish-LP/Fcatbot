# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 12:38:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-19 22:15:47
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import os
from typing import Any, List

from Fcatbot.data_models.message.base_message import Sender
from Fcatbot.data_models.message.message_chain import MessageChain
from Fcatbot.utils import visualize_tree
from .ws import WebSocketHandler
from .utils import get_log
from .utils import Color
from .data_models import GroupMessage
from .data_models import PrivateMessage
from .data_models import HeartbeatEvent
from .data_models import LifecycleEvent
from .data_models import GroupRequestEvent
from .data_models import FriendRequestEvent
from .plugin_system import EventBus, Event, PluginLoader
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

import asyncio
import json

LOG = get_log('FcatBot')

from .data_models import (
    GroupFileUpload, GroupAdminChange, GroupMemberDecrease, 
    GroupMemberIncrease, GroupBan, FriendAdd, GroupRecall,
    FriendRecall, PokeNotify, LuckyKingNotify, HonorNotify
)

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
            close_handler=self.close
        )

    def close(self):
        LOG.info('用户主动触发关闭事件...')
        LOG.info('准备关闭所有插件...')
        self.plugin_sys.unload_all()
        LOG.info('Fcatbot 关闭完成')

    def run(self, load_plugins:bool = True, debug = False):
        if load_plugins:
            LOG.info('准备加载插件')
            if not os.path.exists(PLUGINS_DIR):
                os.makedirs(PLUGINS_DIR, exist_ok=True)
            asyncio.run(self.plugin_sys.load_plugins(api=self.ws))
        LOG.info('准备启动Fcatbot')
        if debug:
            LOG.warning('以 DEBUG 模式启动')
            LOG.warning('推荐配合 DEGUB 级别食用')
            
            async def debug_interceptor(action: str, params: dict) -> dict:
                """Debug模式下的API请求拦截器"""
                LOG.debug(f"Debug模式拦截API请求: {action} {params}")
                
                # 模拟一些基础API响应
                if action == "get_group_info":
                    return {
                        "group_id": params.get("group_id", 0),
                        "group_name": "DEBUG群组",
                        "member_count": 100,
                        "max_member_count": 200
                    }
                elif action == "send_group_msg":
                    LOG.info(f"[Debug] 发送群消息到 {params.get('group_id')}: {params.get('message')}")
                    return {"message_id": 123456}
                elif action == "send_private_msg":
                    LOG.info(f"[Debug] 发送私聊消息到 {params.get('user_id')}: {params.get('message')}")
                    return {"message_id": 123456}
                
                # 其他API请求返回空数据
                return {}

            # 设置debug模式的请求拦截器
            self.ws.set_request_interceptor(debug_interceptor)
            
            try:
                from random import randint
                from time import time
                
                debug_state = {
                    'group_id': 2233,
                    'user_id': 10086,
                    'bot_id': 114514,
                    'user_role': 'member',
                    'user_name': 'DEBUG_USER',
                    'group_name': 'DEBUG_GROUP',
                }
                
                def process_debug_command(cmd: str):
                    """处理调试命令"""
                    cmd = cmd.strip()
                    if cmd.startswith('.'):
                        parts = cmd[1:].split()
                        if not parts:
                            return None
                            
                        command = parts[0]
                        args = parts[1:]
                        
                        if command == 'help':
                            print(f"""{Color.CYAN}调试命令帮助:{Color.RESET}
{Color.GREEN}.help{Color.RESET}               - 显示此帮助
{Color.GREEN}.state{Color.RESET}             - 显示当前状态
{Color.GREEN}.set <key> <value>{Color.RESET} - 设置状态值
{Color.GREEN}.group <id/none>{Color.RESET}   - 切换群聊/私聊环境
{Color.GREEN}.user <id>{Color.RESET}         - 设置用户ID
{Color.GREEN}.name <name>{Color.RESET}       - 设置用户昵称
{Color.GREEN}.role <role>{Color.RESET}       - 设置用户角色(owner/admin/member)
{Color.GREEN}.reload <plugin>{Color.RESET}   - 重载指定插件(all表示重载所有)
{Color.GREEN}.plugins{Color.RESET}           - 显示已加载的插件列表 
{Color.GREEN}.exit{Color.RESET}              - 退出调试模式
{Color.YELLOW}所有非.开头的输入都会被视为消息内容发送{Color.RESET}""")
                            return None

                        elif command == 'plugins':
                            print(f"{Color.CYAN}已加载的插件:{Color.RESET}")
                            for name, plugin in self.plugin_sys.plugins.items():
                                print(f"{Color.GREEN}- {name}{Color.RESET} {Color.GRAY}v{plugin.version}{Color.RESET}")
                            return None

                        elif command == 'reload':
                            if not args:
                                print(f"{Color.YELLOW}请指定要重载的插件名称,使用 all 重载所有插件{Color.RESET}")
                                return None
                            try:
                                plugin_name = args[0]
                                if plugin_name == 'all':
                                    print(f"{Color.YELLOW}正在重载所有插件...{Color.RESET}")
                                    self.plugin_sys.unload_all()
                                    asyncio.run(self.plugin_sys.load_plugins(api=self.ws))
                                    print(f"{Color.GREEN}已重载所有插件{Color.RESET}")
                                else:
                                    if plugin_name not in self.plugin_sys.plugins:
                                        print(f"{Color.RED}插件 '{plugin_name}' 未加载{Color.RESET}")
                                        return None
                                    print(f"{Color.YELLOW}正在重载插件 {plugin_name}...{Color.RESET}")
                                    asyncio.run(self.plugin_sys.reload_plugin(plugin_name))
                                    print(f"{Color.GREEN}已重载插件 {plugin_name}{Color.RESET}")
                            except Exception as e:
                                print(f"{Color.RED}重载插件时出错: {e}{Color.RESET}")
                            return None

                        elif command == 'state':
                            print(f"{Color.CYAN}当前状态{Color.RESET}")
                            print('\n'.join(f"{Color.GRAY}{line}{Color.RESET}" for line in visualize_tree(debug_state)))
                            return None
                            
                        elif command == 'set' and len(args) >= 2:
                            key, value = args[0], ' '.join(args[1:])
                            if key in debug_state:
                                debug_state[key] = value
                                print(f"{Color.GREEN}已设置 {key} = {value}{Color.RESET}")
                            return None
                            
                        elif command == 'group':
                            if not args:
                                debug_state['group_id'] = None
                                print(f"{Color.GREEN}已切换到私聊环境{Color.RESET}")
                            elif args:
                                debug_state['group_id'] = args[0]
                                print(f"{Color.GREEN}已切换到群 {args[0]}{Color.RESET}")
                            return None
                            
                        elif command == 'user':
                            if args:
                                debug_state['user_id'] = args[0]
                                print(f"{Color.GREEN}已设置用户ID为 {args[0]}{Color.RESET}")
                            return None
                            
                        elif command == 'name':
                            if args:
                                debug_state['user_name'] = ' '.join(args)
                                print(f"{Color.GREEN}已设置用户名为 {debug_state['user_name']}{Color.RESET}")
                            return None
                            
                        elif command == 'role':
                            if args and args[0] in ('owner', 'admin', 'member'):
                                debug_state['user_role'] = args[0]
                                print(f"{Color.GREEN}已设置用户角色为 {args[0]}{Color.RESET}")
                            else:
                                print(f"{Color.YELLOW}角色必须是 owner/admin/member 之一{Color.RESET}")
                            return None
                            
                        elif command == 'exit':
                            raise KeyboardInterrupt
                            
                    return cmd  # 返回非命令内容作为消息

                print(f"{Color.CYAN}输入 {Color.GREEN}.help{Color.CYAN} 查看调试命令帮助{Color.RESET}")
                while True:
                    try:
                        text = input(f'{Color.MAGENTA}>{Color.RESET} ')
                        msg_text = process_debug_command(text)
                        if msg_text is None:
                            continue
                            
                        msg_id = randint(0,9999999999)
                        base_msg_data = {
                            'id': msg_id,
                            'self_id': int(debug_state['bot_id']),
                            'real_seq': msg_id,
                            'reply_to': None,
                            'time': int(time() * 1000),
                            'post_type': 'message',
                            'sender': Sender(
                                user_id=int(debug_state['user_id']),
                                nickname=debug_state['user_name'],
                                role=debug_state['user_role']
                            ),
                            'message': MessageChain().add_text(msg_text),
                            'raw_message': msg_text,
                            'message_id': msg_id,
                            'user_id': int(debug_state['user_id'])
                        }
                        
                        if debug_state['group_id']:
                            # 群聊消息
                            msg = GroupMessage(
                                **base_msg_data,
                                message_type='group',
                                group_id=int(debug_state['group_id']),
                                sub_type='normal'
                            )
                            out = self.publish_sync(Event(OFFICIAL_GROUP_MESSAGE_EVENT, msg))
                        else:
                            # 私聊消息
                            msg = PrivateMessage(
                                **base_msg_data,
                                message_type='private',
                                sub_type='friend'
                            )
                            out = self.publish_sync(Event(OFFICIAL_PRIVATE_MESSAGE_EVENT, msg))
                        if out:
                            print(f'{Color.CYAN}收集到的返回:{Color.RESET} {out}')
                    except Exception as e:
                        LOG.error(f"{Color.RED}调试模式错误: {e}{Color.RESET}")
                        
            except KeyboardInterrupt:
                print()
                LOG.info("退出调试模式")
                exit(0)
        else:
            try:
                self.ws.start()  # 启动 WebSocket 连接
            except KeyboardInterrupt:
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
        self.event_bus.publish_sync(event)

    async def publish_async(self, event: Event) -> List[Any]:
        """异步发布事件.

        Args:
            event: 要发布的事件

        Returns:
            List[Any]: 所有处理器返回的结果列表
        """
        await self.event_bus.publish_async(event)
    
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
                    self.ping = abs(self.last_heartbeat['time'] + self.last_heartbeat['interval'] - msg['time'])
                    self.last_heartbeat = msg
                    if 'status' in msg:
                        status: dict = msg['status']
                        if all(status.values()):
                            _LOG.debug(f'Status: {status}')
                        else:
                            _LOG.error(f'Status: {status}')
                except Exception:
                    self.last_heartbeat = msg
                await self.event_bus.publish_async(Event(OFFICIAL_HEARTBEAT_EVENT, message))
        else:
            _LOG.error("这是一个错误,请反馈给开发者\n" + str(msg))