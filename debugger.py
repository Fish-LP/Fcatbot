# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-03-30 14:22:37
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-29 15:37:08
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
import ast
import asyncio
import inspect
from random import randint
from time import time
from typing import TYPE_CHECKING
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

def pre_input_hook():
    """自定义回调函数，用于覆盖当前输入"""
    if readline.get_current_history_length() > 0:
        readline.redisplay()  # 重新显示当前行
        readline.insert_text(readline.get_history_item(readline.get_current_history_length()))  # 插入历史命令
        readline.redisplay()  # 再次重新显示当前行
if TYPE_CHECKING:
    from .client import BotClient
else:
    BotClient = object
# 设置回调函数
readline.set_pre_input_hook(pre_input_hook)

from .utils import Color
from .utils import get_log
from .utils import visualize_tree
from .data_models.message.message_chain import MessageChain
from .data_models.message.base_message import Sender
from .data_models import GroupMessage, PrivateMessage
from .config import (
    OFFICIAL_GROUP_COMMAND_EVENT,
    OFFICIAL_GROUP_MESSAGE_EVENT,  
    OFFICIAL_PRIVATE_COMMAND_EVENT,
    OFFICIAL_PRIVATE_MESSAGE_EVENT
)
from .plugin_system import Event

LOG = get_log('Debug')

def smart_convert(s: str):
    """尝试将字符串智能转换为最合适的 Python 类型。"""
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return s

# Debug命令处理器
debug_commands = {}

# 修改命令注册装饰器
def command(name):
    """命令注册装饰器
    支持将client作为第一个参数传入被装饰函数"""
    def decorator(func):
        debug_commands[name] = func
        return func
    return decorator

# 调试状态
debug_state = {
    'group_id': None,  # None表示私聊环境
    'user_id': 10086,
    'bot_id': 114514, 
    'user_role': 'member',
    'user_name': 'DEBUG_USER',
}

@command('help')
def cmd_help(*_):
    """显示所有可用的调试命令及其用法。
    
    用法: .help
    """
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
所有非.开头的输入都会被作为消息发送""")

@command('say')
def send_msg(client, msg, *arg):
    print(f"{Color.MAGENTA}>{Color.RESET} {msg}")
    send_simulated_message(client, msg)

@command('env')
def cmd_env(client, *args):
    """环境变量管理命令。
    
    用法:
        .env         - 显示当前环境变量
        .env set <key> <value> - 设置环境变量值
    
    参数:
        key: 环境变量名称
        value: 要设置的值
    
    示例:
        .env
        .env set user_id 10086
    """
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
def cmd_group(client, group_id=None, *_):
    """切换到指定的群聊环境。
    
    用法: .g <群号>
    
    参数:
        group_id: 目标群号
        
    示例:
        .g 123456 
    """
    if group_id:
        debug_state['group_id'] = int(group_id)
        print(f"{Color.GREEN}已切换到群 {group_id}{Color.RESET}")
    else:
        print(f"{Color.YELLOW}请指定群号{Color.RESET}")

@command('p')
def cmd_private(client, *args):
    """插件管理与私聊环境切换。
    
    用法:
        .p          - 切换到私聊环境
        .p list     - 显示已加载的插件列表
        .p info <插件名>  - 显示插件详细信息
        .p data <插件名>  - 查看插件数据
        .p set <插件名> <键> <值>  - 设置插件数据
        .p call <插件名> <方法名> [参数]  - 调用插件方法
        
    示例:
        .p
        .p list
        .p info demo
        .p data demo
        .p set demo key value
        .p call demo test arg1 arg2
    """
    if not args:
        debug_state['group_id'] = None
        print(f"{Color.GREEN}已切换到私聊环境{Color.RESET}")
        return

    subcmd = args[0]
    if subcmd == 'list':
        # 显示插件列表,添加更多信息
        print(f"{Color.CYAN}已加载的插件列表:{Color.RESET}")
        for name, plugin in client.plugin_sys.plugins.items():
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
        if name in client.plugin_sys.plugins:
            plugin = client.plugin_sys.plugins[name]
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
        if name in client.plugin_sys.plugins:
            plugin = client.plugin_sys.plugins[name]
            print(f"{Color.CYAN}插件 {name} 的数据:{Color.RESET}")
            if plugin.data:
                print('\n'.join(visualize_tree(plugin.data)))
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
        if name not in client.plugin_sys.plugins:
            print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
            return
            
        plugin = client.plugin_sys.plugins[name]
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
            print('\n'.join(visualize_tree(plugin.data)))
        except Exception as e:
            print(f"{Color.RED}操作失败: {e}{Color.RESET}")
            
    elif subcmd == 'call':
        if len(args) < 3:
            print(f"{Color.YELLOW}用法: .p call <插件名> <方法名> [参数...]{Color.RESET}")
            return
            
        name, func = args[1:3]
        if name not in client.plugin_sys.plugins:
            print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
            return
            
        plugin = client.plugin_sys.plugins[name]
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
def cmd_user(client, user_id=None, *name):
    """设置当前用户ID和昵称。
    
    用法: .u <用户ID> [昵称]
    
    参数:
        user_id: QQ号
        name: 可选的昵称
        
    示例:
        .u 10086
        .u 10086 测试用户
    """
    if user_id:
        debug_state['user_id'] = int(user_id)
        if name:
            debug_state['user_name'] = ' '.join(name)
        print(f"{Color.GREEN}已设置用户 {user_id} ({debug_state['user_name']}){Color.RESET}")
    else:
        print(f"{Color.YELLOW}请指定用户ID{Color.RESET}")

@command('r')
def cmd_role(client, role=None, *_):
    """设置当前用户的群角色。
    
    用法: .r <角色>
    
    参数:
        role: 角色名称,必须是 owner/admin/member 之一
        
    示例:
        .r admin
        .r member
    """
    if role in ('owner', 'admin', 'member'):
        debug_state['user_role'] = role
        print(f"{Color.GREEN}已设置用户角色为 {role}{Color.RESET}")
    else:
        print(f"{Color.YELLOW}角色必须是 owner/admin/member 之一{Color.RESET}")

@command('reload')
async def cmd_reload(client, name=None, *_):
    """重新加载插件。
    
    用法:
        .reload        - 重载所有插件
        .reload <插件名> - 重载指定插件
        
    参数:
        name: 可选的插件名称
        
    示例:
        .reload
        .reload demo
    """
    try:
        if name:
            if name in client.plugin_sys.plugins:
                await client.plugin_sys.reload_plugin(name)
                print(f"{Color.GREEN}已重载插件 {name}{Color.RESET}")
            else:
                print(f"{Color.RED}插件 '{name}' 未加载{Color.RESET}")
        else:
            client.plugin_sys.unload_all()
            await client.plugin_sys.load_plugins(api=client.ws)
            print(f"{Color.GREEN}已重载所有插件{Color.RESET}")
    except Exception as e:
        print(f"{Color.RED}重载失败: {e}{Color.RESET}")

def send_simulated_message(client, text: str) -> None:
    """模拟发送消息并处理响应"""
    msg_id = randint(0,9999999999)
    base_msg_data = {
        'id': msg_id,
        'self_id': int(debug_state['bot_id']),
        'real_seq': msg_id,
        'real_id': msg_id,
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
        if msg.raw_message.startswith(client.command_prefix):
            out = client.publish_sync(Event(OFFICIAL_GROUP_COMMAND_EVENT, msg))
        else:
            out = client.publish_sync(Event(OFFICIAL_GROUP_MESSAGE_EVENT, msg))
    else:
        # 私聊消息
        msg = PrivateMessage(
            **base_msg_data,
            message_type='private',
            sub_type='friend'
        )
        if msg.raw_message.startswith(client.command_prefix):
            out = client.publish_sync(Event(OFFICIAL_PRIVATE_COMMAND_EVENT, msg))
        else:
            out = client.publish_sync(Event(OFFICIAL_PRIVATE_MESSAGE_EVENT, msg))
            
    if out:
        print(f'{Color.CYAN}收集到的返回:{Color.RESET} {out}')

def start_debug_mode(client: BotClient):
    """启动调试模式"""
    async def debug_interceptor(action: str, params: dict) -> dict:
        """Debug模式下的API请求拦截器"""
        LOG.debug(f"Debug模式拦截API请求: {action} {params}")
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
        
        return {}

    # 设置debug模式的请求拦截器
    client.ws.set_request_interceptor(debug_interceptor)
    
    print(f"{Color.CYAN}输入 {Color.GREEN}.help{Color.CYAN} 查看调试命令帮助{Color.RESET}")
    try:
        while True:
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
                            result = debug_commands[cmd](client, *args)
                            if inspect.iscoroutinefunction(debug_commands[cmd]):
                                asyncio.run(result)
                        except Exception as e:
                            print(f"{Color.RED}命令执行出错: {e}{Color.RESET}")
                    continue
                
                # 处理消息发送
                send_simulated_message(client, text)
            
    except KeyboardInterrupt:
        print()
        LOG.info("退出调试模式")
        client.close()
        if readline_support:
            try:
                readline.write_history_file('.history.txt')
            except Exception:
                print('保存命令记录错误')
    except Exception as e:
        LOG.error(f"{Color.RED}调试模式错误: {e}{Color.RESET}")
    
    exit(0)