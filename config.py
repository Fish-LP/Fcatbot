# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-11 17:32:53
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-19 21:24:06
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议
# -------------------------
from .utils import UniversalLoader

# 读取配置文件
def load_config(config_path="config.yaml"):
    try:
        with UniversalLoader(config_path) as f:
            return f.load()
    except FileNotFoundError:
        return {}

# 加载配置
config = load_config()

# 使用配置
EVENT_QUEUE_MAX_SIZE = config.get("EVENT_QUEUE_MAX_SIZE", 64)  # 事件队列最大长度
PLUGINS_DIR = config.get("PLUGINS_DIR", "./plugins")  # 插件目录
META_CONFIG_PATH = config.get("META_CONFIG_PATH", None)  # 元数据,所有插件一份(只读)
PERSISTENT_DIR = config.get("PERSISTENT_DIR", "./data")  # 插件私有数据目录

# 消息事件
OFFICIAL_GROUP_MESSAGE_EVENT = config.get("OFFICIAL_GROUP_MESSAGE_EVENT", 'system.bot.group.message')      # 群聊消息事件
OFFICIAL_GROUP_COMMAND_EVENT = config.get("OFFICIAL_GROUP_COMMAND_EVENT", 'system.bot.group.command')      # 群聊命令事件
OFFICIAL_PRIVATE_MESSAGE_EVENT = config.get("OFFICIAL_PRIVATE_MESSAGE_EVENT", 'system.bot.private.message')  # 私聊消息事件
OFFICIAL_PRIVATE_COMMAND_EVENT = config.get("OFFICIAL_PRIVATE_COMMAND_EVENT", 'system.bot.private.command')  # 私聊命令事件

# 请求事件
OFFICIAL_FRIEND_REQUEST_EVENT = config.get("OFFICIAL_FRIEND_REQUEST_EVENT", 'system.bot.request.friend')    # 好友请求事件
OFFICIAL_GROUP_REQUEST_EVENT = config.get("OFFICIAL_GROUP_REQUEST_EVENT", 'system.bot.request.group')       # 群请求事件

# 通知事件
OFFICIAL_NOTICE_EVENT = config.get("OFFICIAL_NOTICE_EVENT", 'system.bot.notice')                           # 通用通知事件

# 元事件
OFFICIAL_LIFECYCLE_EVENT = config.get("OFFICIAL_LIFECYCLE_EVENT", 'system.bot.lifecycle')                  # 生命周期事件
OFFICIAL_HEARTBEAT_EVENT = config.get("OFFICIAL_HEARTBEAT_EVENT", 'system.bot.heartbeat')                  # 心跳事件