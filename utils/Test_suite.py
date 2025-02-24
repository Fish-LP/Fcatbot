# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-24 20:45:19
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-02-24 20:59:55
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from termcolor import colored as c
from termcolor._types import Attribute, Color, Highlight
from collections.abc import Iterable

class TestSuite:
    colored: c
    def __init__(self):
        self.tests = []
        self.failed = 0

    def add_test(self, description, actual, expected):
        self.tests.append({
            "description": description,
            "actual": actual,
            "expected": expected
        })

    def run(self):
        print("\n")
        print(c("运行测试", "cyan"))
        print(c("================================================================================", "cyan"))
        print(
            c("测试描述".ljust(40), "cyan") + 
            c("实际结果".center(15), "cyan") + 
            c("期望结果".center(15), "cyan") + 
            c("状态".center(10), "cyan")
        )
        print(c("--------------------------------------------------------------------------------", "cyan"))

        for test in self.tests:
            description = test["description"]
            actual = test["actual"]
            expected = test["expected"]
            status = c("通过", "green") if actual == expected else c("失败", "red")

            print(
                f"{description.ljust(40)} {str(actual).center(15)} {str(expected).center(15)} {status.center(10)}"
            )

            if status == c("失败", "red"):
                self.failed += 1

        print(c("--------------------------------------------------------------------------------", "cyan"))
        total_tests = len(self.tests)
        passed = total_tests - self.failed
        print(
            f"\n{c('测试总结', 'cyan')}: {c(passed, 'green')} 项通过, {c(self.failed, 'red')} 项失败 ({total_tests} 总测试项)"
        )
        print(c("================================================================================", "cyan"))
        print("\n")