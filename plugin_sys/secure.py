import ast

class CodeAnalyzer:
    def analyze(self, code: str) -> list:
        """
        分析代码，检查是否存在安全问题。
        
        :param code: 待分析的代码字符串
        :return: 包含安全问题描述的列表
        """
        forbidden_actions = []
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # 检查是否存在不安全的函数调用
                if self.is_insecure_function(node.func):
                    forbidden_actions.append(f"非法函数调用: {self.get_func_id(node.func)}")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # 检查是否存在不安全的模块导入
                if self.is_insecure_module(node):
                    forbidden_actions.append(f"导入受限模块: {self.get_module_name(node)}")
        return forbidden_actions

    def is_insecure_function(self, func: ast.expr) -> bool:
        """
        检查函数是否为禁止调用的内置函数。

        :param func: 函数节点
        :return: 是否为不安全的函数调用
        """
        return isinstance(func, ast.Name) and func.id in {'eval', 'exec'}

    def get_func_id(self, func) -> str:
        """
        获取函数的 ID 或字符串表示。

        :param func: 函数节点
        :return: 函数 ID
        """
        return getattr(func, 'id', str(func))

    def is_insecure_module(self, node) -> bool:
        """
        检查模块是否为禁止导入的模块。

        :param node: 模块导入节点
        :return: 是否为不安全的模块导入
        """
        if isinstance(node, ast.Import):
            return any(alias.name in {'os', 'sys', 'subprocess'} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            return node.module in {'os', 'sys', 'subprocess'}
        return False

    def get_module_name(self, node) -> str:
        """
        获取模块的名称。

        :param node: 模块导入节点
        :return: 模块名称
        """
        if isinstance(node, ast.Import):
            return ', '.join(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            return node.module
        return ''