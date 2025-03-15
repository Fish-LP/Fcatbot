# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-24 20:45:19
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-15 17:02:39
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from .Color import Color

class StringFormatter:
    """处理字符串的视觉对齐问题,支持中英文混合字符串"""

    @staticmethod
    def get_visual_width(text):
        """计算字符串的视觉宽度（中文字符算2,其他字符算1）"""
        width = 0
        for char in text:
            # 中文字符范围
            if '\u4e00' <= char <= '\u9fff':
                width += 2
            else:
                width += 1
        return width

    @classmethod
    def visual_center(cls, text, width, fillchar=' '):
        """视觉居中对齐"""
        visual_width = cls.get_visual_width(text)
        if visual_width >= width:
            return text[:width]  # 超出宽度则截断
        space_needed = width - visual_width
        left_pad = space_needed // 2
        right_pad = space_needed - left_pad
        return fillchar * left_pad + text + fillchar * right_pad

    @classmethod
    def visual_ljust(cls, text, width, fillchar=' '):
        """视觉左对齐"""
        visual_width = cls.get_visual_width(text)
        if visual_width >= width:
            return text[:width]
        space_needed = width - visual_width
        return text + fillchar * space_needed

    @classmethod
    def visual_rjust(cls, text, width, fillchar=' '):
        """视觉右对齐"""
        visual_width = cls.get_visual_width(text)
        if visual_width >= width:
            return text[:width]
        space_needed = width - visual_width
        return fillchar * space_needed + text

class TestSuite:
    """测试套件,用于管理和运行多个测试用例,支持静态值和动态函数执行。

    属性:
        tests (list): 存储所有测试用例的列表。
        failed (int): 记录失败的测试用例数量。

    示例:
    >>> suite = TestSuite()
    >>> # 添加静态测试用例
    >>> suite.add_test(description="测试加法结果", actual=1+1, expected=2)
    >>> # 添加动态测试用例（函数执行）
    >>> suite.add_test(description="测试加法函数", actual=lambda a,b: a+b, 
    ...               expected=3, args=(1,2))
    >>> # 添加异常测试用例
    >>> suite.add_test(description="测试除以零异常", actual=lambda: 1/0,
    ...               expected=ZeroDivisionError)
    >>> suite.run()
    """

    def __init__(self, test_name = 'test'):
        """初始化测试套件,清空测试用例和失败计数器"""
        self.tests = []
        self.failed = 0
        self.test_name = test_name

    def add_test(self, description, actual, expected, args=(), kwargs=None):
        """添加单个测试用例到测试套件

        Args:
            description (str): 测试用例描述（建议40字符内）
            actual (Any/Callable): 实际值或可调用的测试对象
            expected (Any): 预期结果值或异常类型
            args (tuple): 测试函数的位置参数（当actual为可调用时生效）
            kwargs (dict): 测试函数的关键字参数（当actual为可调用时生效）
        """
        self.tests.append({
            "description": description,
            "actual": actual,
            "expected": expected,
            "args": args,
            "kwargs": kwargs or {}
        })

    def _truncate(self, text, length):
        """字符串截断处理,超过长度显示省略号"""
        text = str(text)
        return (text[:length-3] + "...") if len(text) > length else text

    def _eval_actual(self, test_case):
        """执行测试获取实际结果,处理异常情况"""
        actual = test_case["actual"]
        # 处理可调用测试对象
        if callable(actual):
            try:
                return actual(*test_case["args"], **test_case["kwargs"]), None
            except Exception as e:
                return e, e  # 返回异常对象和异常实例
        # 处理静态值
        return actual, None

    def run(self):
        """执行所有测试用例并输出美观的结果报告"""
        print(f"\n🚀 {Color.CYAN}开始执行测试: {Color.RESET}{self.test_name}")
        print(f"{Color.CYAN + "═"*120 + Color.RESET}")
        
        # 打印表头
        header = (f"{Color.CYAN}{StringFormatter.visual_center('测试描述', 40)}{Color.RESET}|"
                f"{Color.CYAN}{StringFormatter.visual_center('实际结果', 40)}{Color.RESET}|"
                f"{Color.CYAN}{StringFormatter.visual_center('预期结果', 20)}{Color.RESET}|"
                f"{Color.CYAN}{StringFormatter.visual_center('状态', 10)}{Color.RESET}")
        print(header)
        print(f"{Color.CYAN}-"*120 + Color.RESET)

        # 遍历所有测试用例
        for case in self.tests:
            # 获取测试结果
            computed, exception = self._eval_actual(case)
            expected = case["expected"]

            # 判断测试结果
            if isinstance(expected, type) and issubclass(expected, BaseException):
                success = isinstance(computed, expected)
            else:
                success = (computed == expected)

            # 处理结果显示
            status = "通过" if success else "失败"
            desc = self._truncate(case["description"], 40)
            desc = StringFormatter.visual_center(desc, 40)
            
            # 异常情况特殊处理(暂时不需要)
            if exception:
                actual_str = str(computed)
                # actual_str = f"{exception.__class__.__name__}: {str(exception)}"
            else:
                actual_str = str(computed)
            
            # 格式化输出列
            actual_col = self._truncate(actual_str, 40)
            actual_col = StringFormatter.visual_center(actual_col, 40)
            expect_col = self._truncate(str(expected), 20)
            expect_col = StringFormatter.visual_center(expect_col, 20)
            status_col = StringFormatter.visual_center(status, 10)
            
            # 打印单行结果
            print(f"{Color.BLUE if success else Color.RED}{desc}{Color.CYAN}|{Color.RESET}"
                f"{actual_col}{Color.CYAN}|{Color.RESET}"
                f"{expect_col}{Color.CYAN}|{Color.RESET}"
                f"{Color.GREEN if success else Color.RED}{status_col}{Color.RESET}")

            # 统计失败案例
            if not success:
                self.failed += 1

        # 打印汇总报告
        total = len(self.tests)
        passed = total - self.failed
        print(f"{Color.CYAN}-"*120 + Color.RESET)
        print(f"{Color.CYAN}📊 测试汇总{Color.RESET}: "
            f"{Color.GREEN}通过 {passed}{Color.RESET}    "
            f"{Color.RED}失败 {self.failed}{Color.RESET}    "
            f"总计 {total} 项")
        print(f"{Color.CYAN}═"*120 + Color.RESET + "\n")