from .message import MessageAPi
from .group import GroupApi
from .system import SystemApi
from .user import UserAPi

from ..client import HttpClient

class Apis(MessageAPi, GroupApi, SystemApi, UserAPi):
    http_client: HttpClient
    def __init__(self, client: HttpClient):
        self.http_client = client

__all__ = [
    'MessageAPi',
    'GroupApi',
    'SystemApi',
    'SystemApi',
    'Apis',
]