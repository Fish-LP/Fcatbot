# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-24 20:45:19
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-09 14:48:57
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
from .Logger import Color

class TestSuite:
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
        print(f"{Color.CYAN}运行测试{Color.RESET}")
        print(f"{Color.CYAN}================================================================================{Color.RESET}")
        print(
            f"{Color.CYAN}{'测试描述'.ljust(40)}{Color.RESET} {Color.CYAN}{'实际结果'.center(15)}{Color.RESET} {Color.CYAN}{'期望结果'.center(15)}{Color.RESET} {Color.CYAN}{'状态'.center(10)}{Color.RESET}"
        )
        print(f"{Color.CYAN}--------------------------------------------------------------------------------{Color.RESET}")

        for test in self.tests:
            description = test["description"]
            actual = test["actual"]
            expected = test["expected"]
            status = f"{Color.GREEN}通过{Color.RESET}" if actual == expected else f"{Color.RED}失败{Color.RESET}"

            print(
                f"{description.ljust(40)} {str(actual).center(15)} {str(expected).center(15)} {status.center(10)}"
            )

            if status == f"{Color.RED}失败{Color.RESET}":
                self.failed += 1

        print(f"{Color.CYAN}--------------------------------------------------------------------------------{Color.RESET}")
        total_tests = len(self.tests)
        passed = total_tests - self.failed
        print(
            f"\n{Color.CYAN}{'测试总结'}{Color.RESET}: {Color.GREEN}{passed}{Color.RESET} 项通过, {Color.RED}{self.failed}{Color.RESET} 项失败 ({total_tests} 总测试项)"
        )
        print(f"{Color.CYAN}================================================================================{Color.RESET}")
        print("\n")