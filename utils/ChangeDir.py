import os
from contextlib import ContextDecorator


class ChangeDir(ContextDecorator):
    """
    一个上下文管理器，用于暂时切换工作路径。
    """
    def __init__(self, new_path):
        """
        初始化工作路径切换器。
        
        参数:
            new_path (str): 新的工作路径
        """
        self.new_path = new_path
        self.origin_path = os.getcwd()

    def __enter__(self):
        """
        进入上下文时，切换到新的工作路径
        """
        # 检查路径是否存在
        if not os.path.exists(self.new_path):
            raise FileNotFoundError(f"目录不存在: {self.new_path}")
        # 切换到新目录
        os.chdir(self.new_path)
        return self  # 返回对象本身

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        退出上下文时，恢复到原始工作路径
        """
        os.chdir(self.origin_path)
        if exc_type:
            raise exc_type
        return True  # 阻止异常传播
