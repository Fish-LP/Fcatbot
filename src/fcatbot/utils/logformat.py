from datetime import datetime

from fcatbot.utils.color import Color


class LogFormats:
    """日志格式系统 - 按风格分类，每种风格支持 message / notice / request / meta_event。

    调用方式: 
        LogFormats.Modern.message(...)
        LogFormats.Simple.notice(...)
        LogFormats.Professional.meta_event(...)
    """

    # ==================== 现代风格 ====================
    class Modern:
        """现代风格 - 简洁美观，使用 • 和 ▸ 作为视觉锚点。"""

        @staticmethod
        def message(group_id, nick, uid, msg, group_name=None):
            """群聊/私聊消息"""
            if group_id:
                return (
                    f"{Color.Green}{group_name or f'G{group_id}'}{Color.Reset} "
                    f"{Color.Gray}• {Color.Yellow}{nick} "
                    f"{Color.Gray}({uid}){Color.Cyan} ▸ {Color.Reset}{msg}{Color.Reset}"
                )
            return (
                f"{Color.Yellow}{nick} "
                f"{Color.Gray}({uid}){Color.Magenta} ▸ {Color.Reset}{msg}{Color.Reset}"
            )

        @staticmethod
        def notice(
            notice_type, user_id=None, group_id=None, group_name=None, detail=""
        ):
            """通知事件"""
            loc = (
                (
                    f"{Color.Green}{group_name or f'G{group_id}'}{Color.Reset} "
                    f"{Color.Gray}• {Color.Yellow}{notice_type} "
                    f"{Color.Gray}({user_id or '-'}){Color.Reset}"
                )
                if group_id
                else (
                    f"{Color.Yellow}{notice_type}{Color.Gray} "
                    f"({user_id or '-'}){Color.Reset}"
                )
            )
            detail_str = f"{Color.Gray} ▸ {Color.Reset}{detail}" if detail else ""
            return f"{Color.Blue}[NOTICE]{Color.Reset} {loc}{detail_str}"

        @staticmethod
        def request(request_type, user_id, comment=""):
            """请求事件"""
            detail = f"{Color.Gray} ▸ {Color.Reset}{comment}" if comment else ""
            return (
                f"{Color.Magenta}[REQUEST]{Color.Reset} "
                f"{Color.Yellow}{request_type}{Color.Gray} ({user_id}){Color.Reset}"
                f"{detail}"
            )

        @staticmethod
        def meta_event(sub_type, detail="", self_id=None):
            """元事件"""
            prefix = f"Bot.{self_id} " if self_id else ""
            detail_str = (
                f"{Color.Gray} ▸ {Color.Reset}{prefix}{detail}"
                if (detail or self_id)
                else ""
            )
            return (
                f"{Color.Gray}[META]{Color.Reset} "
                f"{Color.Yellow}{sub_type}{Color.Reset}{detail_str}"
            )

    # ==================== 极简风格 ====================
    class Simple:
        """极简风格 - 最高效，最少字符。"""

        @staticmethod
        def message(group_id, nick, uid, msg, group_name=None):
            if group_id:
                return (
                    f"{Color.Green}{group_name or f'G{group_id}'}{Color.Reset} | "
                    f"{Color.Yellow}{nick}{Color.Gray}({uid}){Color.Reset}: {msg}"
                )
            return (
                f"{Color.Magenta}PM{Color.Reset} | "
                f"{Color.Yellow}{nick}{Color.Gray}({uid}){Color.Reset}: {msg}"
            )

        @staticmethod
        def notice(
            notice_type, user_id=None, group_id=None, group_name=None, detail=""
        ):
            src = group_name or (f"G{group_id}" if group_id else "-")
            return (
                f"{Color.Blue}[N]{Color.Reset} {Color.Yellow}{notice_type}{Color.Reset} | "
                f"{Color.Green}{src}{Color.Reset} | "
                f"{Color.Gray}{user_id or '-'}{Color.Reset} | {detail}"
            )

        @staticmethod
        def request(request_type, user_id, comment=""):
            return (
                f"{Color.Magenta}[R]{Color.Reset} {Color.Yellow}{request_type}{Color.Reset} | "
                f"{Color.Gray}{user_id}{Color.Reset} | {comment}"
            )

        @staticmethod
        def meta_event(sub_type, detail="", self_id=None):
            sid = f"Bot.{self_id} " if self_id else ""
            return (
                f"{Color.Gray}[M]{Color.Reset} {Color.Yellow}{sub_type}{Color.Reset} | "
                f"{sid}{detail}"
            )

    # ==================== 专业风格 ====================
    class Professional:
        """专业风格 - 带时间戳，固定宽度对齐，适合监控。"""

        @staticmethod
        def _timestamp():
            return datetime.now().strftime("%H:%M:%S")

        @staticmethod
        def message(group_id, nick, uid, msg, group_name=None):
            ts = LogFormats.Professional._timestamp()
            if group_id:
                return (
                    f"{Color.Gray}{ts} {Color.Green}[MSG]{Color.Reset} "
                    f"{Color.White}{group_name or f'G{group_id}':<15} {Color.Yellow}{nick:<10} "
                    f"{Color.Gray}({uid}){Color.Reset} : {msg}"
                )
            return (
                f"{Color.Gray}{ts} {Color.Magenta}[PVT]{Color.Reset} "
                f"{Color.Yellow}{nick:<10} {Color.Gray}({uid}){Color.Reset} : {msg}"
            )

        @staticmethod
        def notice(
            notice_type, user_id=None, group_id=None, group_name=None, detail=""
        ):
            ts = LogFormats.Professional._timestamp()
            src = group_name or (f"G{group_id}" if group_id else "Private")
            return (
                f"{Color.Gray}{ts} {Color.Blue}[NTC]{Color.Reset} "
                f"{Color.Yellow}{notice_type:<12} {Color.White}{src:<15} "
                f"{Color.Gray}({user_id or '-':>10}){Color.Reset} : {detail}"
            )

        @staticmethod
        def request(request_type, user_id, comment=""):
            ts = LogFormats.Professional._timestamp()
            return (
                f"{Color.Gray}{ts} {Color.Magenta}[REQ]{Color.Reset} "
                f"{Color.Yellow}{request_type:<10} {Color.Gray}({user_id:>10}){Color.Reset} : {comment}"
            )

        @staticmethod
        def meta_event(sub_type, detail="", self_id=None):
            ts = LogFormats.Professional._timestamp()
            sid = f"Bot.{self_id} " if self_id else ""
            return (
                f"{Color.Gray}{ts} {Color.Gray}[MET]{Color.Reset} "
                f"{Color.Yellow}{sub_type:<12}{Color.Reset} : {sid}{detail}"
            )

    # ==================== 调试风格 ====================
    class Debug:
        """调试风格 - 字段完整，带毫秒时间戳。"""

        @staticmethod
        def _timestamp():
            return datetime.now().strftime("%H:%M:%S.%f")[:-3]

        @staticmethod
        def message(group_id, nick, uid, msg, group_name=None):
            ts = LogFormats.Debug._timestamp()
            if group_id:
                return (
                    f"{Color.Gray}{ts} | {Color.Blue}Type:Group{Color.Reset} | "
                    f"{Color.Green}Name:{group_name}{Color.Reset} | "
                    f"{Color.Yellow}User:{nick}{Color.Reset} | "
                    f"{Color.Cyan}UID:{uid}{Color.Reset} | "
                    f"{Color.White}Msg:{msg}{Color.Reset}"
                )
            return (
                f"{Color.Gray}{ts} | {Color.Magenta}Type:Private{Color.Reset} | "
                f"{Color.Yellow}User:{nick}{Color.Reset} | "
                f"{Color.Cyan}UID:{uid}{Color.Reset} | "
                f"{Color.Green}Msg:{msg}{Color.Reset}"
            )

        @staticmethod
        def notice(
            notice_type, user_id=None, group_id=None, group_name=None, detail=""
        ):
            ts = LogFormats.Debug._timestamp()
            return (
                f"{Color.Gray}{ts} | {Color.Blue}Type:Notice{Color.Reset} | "
                f"{Color.Yellow}SubType:{notice_type}{Color.Reset} | "
                f"{Color.Cyan}User:{user_id or '-'}{Color.Reset} | "
                f"{Color.Green}Group:{group_id or '-'}{Color.Reset} | "
                f"{Color.White}Data:{detail}{Color.Reset}"
            )

        @staticmethod
        def request(request_type, user_id, comment=""):
            ts = LogFormats.Debug._timestamp()
            return (
                f"{Color.Gray}{ts} | {Color.Magenta}Type:Request{Color.Reset} | "
                f"{Color.Yellow}SubType:{request_type}{Color.Reset} | "
                f"{Color.Cyan}User:{user_id}{Color.Reset} | "
                f"{Color.White}Comment:{comment}{Color.Reset}"
            )

        @staticmethod
        def meta_event(sub_type, detail="", self_id=None):
            ts = LogFormats.Debug._timestamp()
            sid = f"SelfID:{self_id} " if self_id else ""
            return (
                f"{Color.Gray}{ts} | {Color.Gray}Type:Meta{Color.Reset} | "
                f"{Color.Yellow}SubType:{sub_type}{Color.Reset} | "
                f"{sid}{Color.White}Data:{detail}{Color.Reset}"
            )

    # ==================== 协议风格 ====================
    class Protocol:
        """协议风格 - 类似网络协议键值对格式，多行结构化。"""

        @staticmethod
        def message(group_id, nick, uid, msg, group_name=None):
            msg_len = len(str(msg))
            if group_id:
                return (
                    f"{Color.Gray}[MESSAGE]{Color.Reset}\n"
                    f"{Color.Blue}  TYPE:   GROUP{Color.Reset}\n"
                    f"{Color.Green}  FROM:   {nick}{Color.Reset}\n"
                    f"{Color.Cyan}  UID:    {uid}{Color.Reset}\n"
                    f"{Color.Yellow}  GROUP:  {group_name or group_id}{Color.Reset}\n"
                    f"{Color.White}  LENGTH: {msg_len}{Color.Reset}\n"
                    f"{Color.Magenta}  DATA:   {msg}{Color.Reset}"
                )
            return (
                f"{Color.Gray}[MESSAGE]{Color.Reset}\n"
                f"{Color.Blue}  TYPE:   PRIVATE{Color.Reset}\n"
                f"{Color.Green}  FROM:   {nick}{Color.Reset}\n"
                f"{Color.Cyan}  UID:    {uid}{Color.Reset}\n"
                f"{Color.White}  LENGTH: {msg_len}{Color.Reset}\n"
                f"{Color.Magenta}  DATA:   {msg}{Color.Reset}"
            )

        @staticmethod
        def notice(
            notice_type, user_id=None, group_id=None, group_name=None, detail=""
        ):
            return (
                f"{Color.Gray}[NOTICE]{Color.Reset}\n"
                f"{Color.Blue}  TYPE:   {notice_type}{Color.Reset}\n"
                f"{Color.Green}  USER:   {user_id or '-'}{Color.Reset}\n"
                f"{Color.Yellow}  GROUP:  {group_name or group_id or '-'}{Color.Reset}\n"
                f"{Color.White}  DATA:   {detail}{Color.Reset}"
            )

        @staticmethod
        def request(request_type, user_id, comment=""):
            return (
                f"{Color.Gray}[REQUEST]{Color.Reset}\n"
                f"{Color.Blue}  TYPE:    {request_type}{Color.Reset}\n"
                f"{Color.Green}  USER:    {user_id}{Color.Reset}\n"
                f"{Color.White}  COMMENT: {comment}{Color.Reset}"
            )

        @staticmethod
        def meta_event(sub_type, detail="", self_id=None):
            sid = f"  SELF:    {self_id}\n" if self_id else ""
            return (
                f"{Color.Gray}[META_EVENT]{Color.Reset}\n"
                f"{Color.Blue}  TYPE:    {sub_type}{Color.Reset}\n"
                f"{sid}"
                f"{Color.White}  DATA:    {detail}{Color.Reset}"
            )

    # ==================== 标签风格 ====================
    class Tag:
        """标签风格 - 方括号类型标识，清晰明确。"""

        @staticmethod
        def message(group_id, nick, uid, msg, group_name=None):
            if group_id:
                return (
                    f"{Color.Gray}[{Color.Green}GROUP{Color.Gray}] "
                    f"{Color.Blue}{group_name or f'G{group_id}'}{Color.Gray}: "
                    f"{Color.Yellow}{nick}{Color.Gray}[{uid}]{Color.Reset} » {msg}"
                )
            return (
                f"{Color.Gray}[{Color.Magenta}PRIVATE{Color.Gray}] "
                f"{Color.Yellow}{nick}{Color.Gray}[{uid}]{Color.Reset} » {msg}"
            )

        @staticmethod
        def notice(
            notice_type, user_id=None, group_id=None, group_name=None, detail=""
        ):
            src = group_name or (f"G{group_id}" if group_id else "PRIVATE")
            return (
                f"{Color.Gray}[{Color.Blue}NOTICE{Color.Gray}] "
                f"{Color.Yellow}{notice_type}{Color.Gray}: "
                f"{Color.Green}{src}{Color.Gray}[{user_id or '-'}]{Color.Reset} » {detail}"
            )

        @staticmethod
        def request(request_type, user_id, comment=""):
            return (
                f"{Color.Gray}[{Color.Magenta}REQUEST{Color.Gray}] "
                f"{Color.Yellow}{request_type}{Color.Gray}: "
                f"{Color.Gray}[{user_id}]{Color.Reset} » {comment}"
            )

        @staticmethod
        def meta_event(sub_type, detail="", self_id=None):
            sid = f"[{self_id}] " if self_id else ""
            return (
                f"{Color.Gray}[{Color.Gray}META{Color.Gray}] "
                f"{Color.Yellow}{sub_type}{Color.Gray}: "
                f"{sid}{Color.Reset}» {detail}"
            )


# ================ 预览函数 ================
def preview_all_styles():
    """预览所有保留风格"""
    print(f"{Color.White}{Color.Bold}=== 日志风格预览 ==={Color.Reset}\n")

    test_msg = ("User123", 10001, "这是一个测试消息", "测试群组")
    test_notice = ("group_upload", 10001, 123456, "测试群组", "file=xxx.zip")
    test_request = ("friend", 20002, "你好，请求加好友")
    test_meta = ("lifecycle", "Bot.123456789 上线", "123456789")

    styles = [
        ("Modern", "现代风格"),
        ("Simple", "极简风格"),
        ("Professional", "专业风格"),
        ("Debug", "调试风格"),
        ("Protocol", "协议风格"),
        ("Tag", "标签风格"),
    ]

    for style_name, style_desc in styles:
        print(f"{Color.Cyan}{style_desc} ({style_name}):{Color.Reset}")
        Style = getattr(LogFormats, style_name)

        print(f"  {Color.Gray}message:{Color.Reset}")
        print(f"    {Style.message(123, *test_msg)}")

        print(f"  {Color.Gray}notice:{Color.Reset}")
        print(f"    {Style.notice(*test_notice)}")

        print(f"  {Color.Gray}request:{Color.Reset}")
        print(f"    {Style.request(*test_request)}")

        print(f"  {Color.Gray}meta_event:{Color.Reset}")
        print(f"    {Style.meta_event(*test_meta)}")

        print()


if __name__ == "__main__":
    preview_all_styles()
