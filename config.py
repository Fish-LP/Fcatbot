from .utils import UniversalLoader

# 读取配置文件
def load_config(config_path="config.yaml"):
    with UniversalLoader(config_path) as f:
        return f.load(f)

# 加载配置
config: UniversalLoader = load_config()

# 使用配置
EVENT_QUEUE_MAX_SIZE = config.get("EVENT_QUEUE_MAX_SIZE", 64)  # 事件队列最大长度
PLUGINS_DIR = config.get("PLUGINS_DIR", "./plugins")  # 插件目录
META_CONFIG_PATH = config.get("META_CONFIG_PATH", None)  # 元数据，所有插件一份(只读)
PERSISTENT_DIR = config.get("PERSISTENT_DIR", "./data")  # 插件私有数据目录

OFFICIAL_GROUP_MESSAGE_EVENT = config.get("OFFICIAL_GROUP_MESSAGE_EVENT", 'meta.bot.group')
OFFICIAL_PRIVATE_MESSAGE_EVENT = config.get("OFFICIAL_PRIVATE_MESSAGE_EVENT", 'meta.bot.private')
OFFICIAL_REQUEST_EVENT = config.get("OFFICIAL_REQUEST_EVENT", 'meta.bot.request')
OFFICIAL_NOTICE_EVENT = config.get("OFFICIAL_NOTICE_EVENT", 'meta.bot.notice')