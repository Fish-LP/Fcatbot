# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-07-24 19:11:46
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-07-25 10:41:18
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, Fcatbot使用许可协议 
# -------------------------
class TypeRegistry:
    """类型转换注册中心"""
    _handlers = {}

    @classmethod
    def register(cls, type_name: str):
        def decorator(handler_class):
            cls._handlers[type_name] = handler_class
            return handler_class
        return decorator

    @classmethod
    def get_handler(cls, type_name: str):
        return cls._handlers.get(type_name)

class DataHolder(dict):
    """纯数据容器,继承dict实现基础字典功能"""
    
    def __init__(self, data: dict = None):
        super().__init__()
        if data:
            self.update(data)
