# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-12 12:38:32
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-30 13:17:42
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
import os
try:
    # 尝试导入readline或pyreadline3
    try:
        import readline
    except ImportError:
        try:
            import pyreadline3 as readline # type: ignore
        except ImportError:
            readline = None
    readline_support = True if readline else False
except Exception:
    readline_support = False
    readline = None
import asyncio
import json
import inspect
import ast

from typing import Any, List

from .ws import WebSocketHandler

from .utils import get_log
from .utils import Color

from Fcatbot.data_models.message.base_message import Sender
from Fcatbot.data_models.message.message_chain import MessageChain
from Fcatbot.utils import visualize_tree

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

def smart_convert(s: str):
    """
    尝试将字符串智能转换为最合适的 Python 类型。
    """
    try:
        # 尝试使用 ast.literal_eval 安全地解析字符串
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        # 解析失败
        return s

class CommandCompleter:
    def __init__(self, options):
        self.options = sorted(options)
        self.matches = []

    def complete(self, text, state):
        print(f"Completing: {text} (state={state})")
        
        # 转换为小写进行匹配
        clean_text = text.lower()
        if text.startswith('.'):
            if state == 0:
                self.matches = [s for s in self.options if s.lower().startswith(clean_text)]
                print(f"Possible matches: {self.matches}")
            try:
                return self.matches[state]
            except IndexError:
                return None
        return None
    
    def __str__(self):
        return f"CommandCompleter({self.options})"

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
            # 设置插件系统的调试模式
            self.plugin_sys.set_debug(debug)
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
                    'group_id': None,  # None表示私聊环境
                    'user_id': 10086,
                    'bot_id': 114514,
                    'user_role': 'member',
                    'user_name': 'DEBUG_USER',
                }

                # 定义命令处理函数
                debug_commands = {}
                def command(name):
                    def decorator(func):
                        debug_commands[name] = func
                        return func
                    return decorator

                @command('help')
                def cmd_help(*_):
                    """显示帮助信息"""
                    print(f"""{Color.CYAN}调试命令帮助:{Color.RESET}
{Color.GREEN}.help{Color.RESET}                    - 显示此帮助
{Color.GREEN}.env{Color.RESET}                     - 显示当前调试环境
{Color.GREEN}.env set <key> <value>{Color.RESET}   - 设置环境变量
{Color.GREEN}.g <id>{Color.RESET}                  - 切换到指定群聊
{Color.GREEN}.p{Color.RESET}                       - 切换到私聊环境
{Color.GREEN}.p list{Color.RESET}                 - 显示已加载的插件
{Color.GREEN}.p info <name>{Color.RESET}          - 查看插件信息
{Color.GREEN}.p data <name>{Color.RESET}          - 查看插件数据
{Color.GREEN}.p set <name> <k> <v>{Color.RESET}   - 设置插件数据
{Color.GREEN}.p call <name> <func>{Color.RESET}   - 调用插件方法
{Color.GREEN}.reload [plugin]{Color.RESET}        - 重载插件(无参数时重载所有)
{Color.GREEN}.exit{Color.RESET}                   - 退出调试模式
所有非.开头的输入都会被作为消息发送""")

                @command('env')
                def cmd_env(*args):
                    """环境变量管理"""
                    if not args:
                        print(f"{Color.CYAN}当前环境:{Color.RESET}")
                        for k, v in debug_state.items():
                            print(f"{Color.GRAY}{k} = {v}{Color.RESET}")
                        return
                    
                    if args[0] == 'set' and len(args) >= 3:
                        key, value = args[1], smart_convert(' '.join(args[2:]))
                        if key in debug_state:
                            debug_state[key] = value
                            print(f"{Color.GREEN}已设置 {key} = {value}{Color.RESET}")

                @command('g')
                def cmd_group(group_id=None, *_):
                    """切换群聊"""
                    if group_id:
                        debug_state['group_id'] = int(group_id)
                        print(f"{Color.GREEN}已切换到群 {group_id}{Color.RESET}")
                    else:
                        print(f"{Color.YELLOW}请指定群号{Color.RESET}")

                @command('p')
                def cmd_private(*args):
                    """切换私聊/插件管理"""
                    if not args:
                        debug_state['group_id'] = None
                        print(f"{Color.GREEN}已切换到私聊环境{Color.RESET}")
                        return

                    subcmd = args[0]
                    if subcmd == 'list':
                        # 显示插件列表,添加更多信息
                        print(f"{Color.CYAN}已加载的插件列表:{Color.RESET}")
                        for name, plugin in self.plugin_sys.plugins.items():
                            print(f"{Color.YELLOW}- {Color.GREEN}{name}{Color.RESET} {Color.GRAY}v{plugin.version}{Color.RESET}")
                            print(f"  作者: {plugin.meta_data.get('author', '未知')}")
                            print(f"  描述: {plugin.meta_data.get('description', '无')}")
                            if plugin.dependencies:
                                print(f"  依赖: {', '.join(plugin.dependencies)}")
                            
                    elif subcmd == 'info':
                        if len(args) < 2:
                            print(f"{Color.YELLOW}用法: .p info <插件名>{Color.RESET}")
                            return
                        name = args[1]
                        if name in self.plugin_sys.plugins:
                            plugin = self.plugin_sys.plugins[name]
                            print(f"{Color.CYAN}插件详细信息:{Color.RESET}")
                            print(f"名称: {plugin.name}")
                            print(f"版本: {plugin.version}")
                            print(f"作者: {getattr(plugin,'author','None')}")
                            print(f"描述: {getattr(plugin,'info','None')}")
                            print(f"工作目录: {plugin._work_path}")
                            print(f"数据文件: {plugin._data_path}")
                            print(f"调试模式: {'启用' if plugin.debug else '禁用'}")
                            if plugin.dependencies:
                                print(f"依赖项: {', '.join(plugin.dependencies)}")
                        else:
                            print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
                            
                    elif subcmd == 'data':
                        if len(args) < 2:
                            print(f"{Color.YELLOW}用法: .p data <插件名>{Color.RESET}")
                            return
                        name = args[1]
                        if name in self.plugin_sys.plugins:
                            plugin = self.plugin_sys.plugins[name]
                            print(f"{Color.CYAN}插件 {name} 的数据:{Color.RESET}")
                            if plugin.data.data:
                                print('\n'.join(visualize_tree(plugin.data.data)))
                            else:
                                print(f"{Color.GRAY}(空){Color.RESET}")
                        else:
                            print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
                            
                    elif subcmd == 'set':
                        if len(args) < 3:
                            print(f"{Color.YELLOW}用法: .p set <插件名> <键> [值]{Color.RESET}")
                            print(f"提示: 不提供值时将删除该键")
                            return
                            
                        name = args[1]
                        if name not in self.plugin_sys.plugins:
                            print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
                            return
                            
                        plugin = self.plugin_sys.plugins[name]
                        key = args[2]
                        
                        try:
                            if len(args) > 3:
                                # 设置值
                                value = smart_convert(' '.join(args[3:]))
                                plugin.data[key] = value
                                print(f"{Color.GREEN}已设置 {name}.{key} = {value}{Color.RESET}")
                            else:
                                # 删除键
                                if key in plugin.data:
                                    del plugin.data[key]
                                    print(f"{Color.GREEN}已删除键 {name}.{key}{Color.RESET}")
                                else:
                                    print(f"{Color.YELLOW}键 {key} 不存在{Color.RESET}")
                            
                            # 显示更新后的数据
                            print(f"{Color.CYAN}当前数据:{Color.RESET}")
                            print('\n'.join(visualize_tree(plugin.data.data)))
                        except Exception as e:
                            print(f"{Color.RED}操作失败: {e}{Color.RESET}")
                            
                    elif subcmd == 'call':
                        if len(args) < 3:
                            print(f"{Color.YELLOW}用法: .p call <插件名> <方法名> [参数...]{Color.RESET}")
                            return
                            
                        name, func = args[1:3]
                        if name not in self.plugin_sys.plugins:
                            print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
                            return
                            
                        plugin = self.plugin_sys.plugins[name]
                        if not hasattr(plugin, func):
                            print(f"{Color.RED}方法 '{func}' 在插件中不存在{Color.RESET}")
                            # 显示可用方法
                            methods = [m for m in dir(plugin) if not m.startswith('_') 
                                     and callable(getattr(plugin, m))]
                            if methods:
                                print(f"{Color.YELLOW}可用方法: {', '.join(methods)}{Color.RESET}")
                            return
                            
                        fn = getattr(plugin, func)
                        try:
                            if inspect.iscoroutinefunction(fn):
                                result = asyncio.run(fn(*args[3:]))
                            else:
                                result = fn(*args[3:])
                            print(f"{Color.GREEN}返回值: {result}{Color.RESET}")
                        except Exception as e:
                            print(f"{Color.RED}调用出错: {e}{Color.RESET}")
                    else:
                        print(f"{Color.YELLOW}未知的子命令: {subcmd}{Color.RESET}")
                        print("可用子命令: list, info, data, set, call")

                @command('u')
                def cmd_user(user_id=None, *name):
                    """设置用户ID和昵称"""
                    if user_id:
                        debug_state['user_id'] = int(user_id)
                        if name:
                            debug_state['user_name'] = ' '.join(name)
                        print(f"{Color.GREEN}已设置用户 {user_id} ({debug_state['user_name']}){Color.RESET}")
                    else:
                        print(f"{Color.YELLOW}请指定用户ID{Color.RESET}")

                @command('r')
                def cmd_role(role=None, *_):
                    """设置用户角色"""
                    if role in ('owner', 'admin', 'member'):
                        debug_state['user_role'] = role
                        print(f"{Color.GREEN}已设置用户角色为 {role}{Color.RESET}")
                    else:
                        print(f"{Color.YELLOW}角色必须是 owner/admin/member 之一{Color.RESET}")

                @command('reload')
                async def cmd_reload(name=None, *_):
                    """重载插件"""
                    try:
                        if name:
                            if name in self.plugin_sys.plugins:
                                await self.plugin_sys.reload_plugin(name)
                                print(f"{Color.GREEN}已重载插件 {name}{Color.RESET}")
                            else:
                                print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
                        else:
                            self.plugin_sys.unload_all()
                            await self.plugin_sys.load_plugins(api=self.ws)
                            print(f"{Color.GREEN}已重载所有插件{Color.RESET}")
                    except Exception as e:
                        print(f"{Color.RED}重载失败: {e}{Color.RESET}")

                @command('exit')
                def cmd_exit(*_):
                    """退出调试模式"""
                    raise KeyboardInterrupt

                # 命令处理主循环
                print(f"{Color.CYAN}输入 {Color.GREEN}.help{Color.CYAN} 查看调试命令帮助{Color.RESET}")
                while True:
                    try:
                        text = input(f'{Color.MAGENTA}>{Color.RESET} ').strip()
                        if not text:
                            continue
                            
                        if text.startswith('.'):
                            parts = text[1:].split()
                            if not parts:
                                continue
                            cmd, *args = parts
                            
                            if cmd in debug_commands:
                                try:
                                    result = debug_commands[cmd](*args)
                                    if inspect.iscoroutinefunction(debug_commands[cmd]):
                                        asyncio.run(result)
                                except Exception as e:
                                    print(f"{Color.RED}命令执行出错: {e}{Color.RESET}")
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
                            'message': MessageChain().add_text(text),
                            'raw_message': text,
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
                            if msg.raw_message.startswith(self.command_prefix):
                                out = self.publish_sync(Event(OFFICIAL_GROUP_COMMAND_EVENT, msg))
                            else:
                                out = self.publish_sync(Event(OFFICIAL_GROUP_MESSAGE_EVENT, msg))
                        else:
                            # 私聊消息
                            msg = PrivateMessage(
                                **base_msg_data,
                                message_type='private',
                                sub_type='friend'
                            )
                            if msg.raw_message.startswith(self.command_prefix):
                                out = self.publish_sync(Event(OFFICIAL_PRIVATE_COMMAND_EVENT, msg))
                            else:
                                out = self.publish_sync(Event(OFFICIAL_PRIVATE_MESSAGE_EVENT, msg))
                        if out:
                            print(f'{Color.CYAN}收集到的返回:{Color.RESET} {out}')
                    except Exception as e:
                        LOG.error(f"{Color.RED}调试模式错误: {e}{Color.RESET}")
                        
            except KeyboardInterrupt:
                print()
                LOG.info("退出调试模式")
                if readline_support:
                    try:
                        readline.write_history_file('.history.txt')
                    except Exception:
                        pass
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