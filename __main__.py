# -------------------------
# @Author       : Fish-LP fish.zh@outlook.com
# @Date         : 2025-02-15 18:36:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-16 20:39:53
# @Description  : 喵喵喵, 我还没想好怎么介绍文件喵
# @Copyright (c) 2025 by Fish-LP, MIT License 
# -------------------------
def run():
    from Fcatbot import BotClient
    Client = BotClient('ws://192.168.3.14:3001')
    Client.run()

if __name__ == "__main__":
    run()