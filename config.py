EVENT_QUEUE_MAX_SIZE = 64  # 事件队列最大长度
PLUGINS_DIR = "./plugins"  # 插件目录
META_CONFIG_PATH = None  # 元数据，所有插件一份(只读)
PERSISTENT_DIR = "./data"  # 插件私有数据目录

OFFICIAL_GROUP_MESSAGE_EVENT = 'napcat.group'
OFFICIAL_PRIVATE_MESSAGE_EVENT = 'napcat.private'
OFFICIAL_REQUEST_EVENT = 'napcat.request'
OFFICIAL_NOTICE_EVENT = 'napcat.notice'