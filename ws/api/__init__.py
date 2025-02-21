from .message import MessageAPi
from .group import GroupApi
from .system import SystemApi
from .user import UserAPi


class Apis(MessageAPi, GroupApi, SystemApi, UserAPi):
    def __init__(self, client):
        self.ws_client = client

__all__ = [
    'Apis'
]