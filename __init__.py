__version__ = '0.0.1-dev'
# 版本号的格式为：主版本号.次版本号.修订号（MAJOR.MINOR.PATCH），其中每个部分都是非负整数，且禁止在数字前补零。
# 主版本号（MAJOR） ：表示软件的重大变更，通常涉及不兼容的 API 修改、重大功能新增或旧功能的废弃。当主版本号增加时，次版本号和修订号必须归零。
# 次版本号（MINOR） ：表示向后兼容的功能新增或改进。当次版本号增加时，修订号必须归零。
# 修订号（PATCH） ：表示向后兼容的问题修正或小的改进。
# 每次提交前请视情况修改版本号
# dev
# alpha
# bate
# release
from .client import BotClient
from .utils import get_log, UniversalDataIO
from .client import BotClient
from .models import GroupMessage, PrivateMessage
from .models import Nope
from .models import MessageChain
from .plugin_sys import PluginLoader
from .plugin_sys import Event
from .plugin_sys import CompatibleEnrollment
from .plugin_sys import BasePlugin
from .plugin_sys import EventBus

LOG = get_log('Bot')

__all__ = [
    'BotClient',
    'LOG',
    'get_log',
    'UniversalDataIO',
    'GroupMessage',
    'PrivateMessage',
    'MessageChain',
    'Nope',
    'PluginLoader',
    'BasePlugin',
    'Event',
    'EventBus',
    'CompatibleEnrollment',
]