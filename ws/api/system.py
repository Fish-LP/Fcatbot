# -------------------------
# @Author       : Ncatbot
# @Date         : 2025-02-12 13:41:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-10 21:40:56
# @Description  : 当时确实是 MIT License 后来给改了
# @Copyright (c) 2025 by Ncatbot, MIT License 
# -------------------------
from typing import Union, List, Dict, Optional

class SystemApi:
    '''系统接口'''
    
    async def get_client_key(self):
        """
        :return: 获取 client_key
        """
        return await self.ws_client.api("get_clientkey", {})

    async def get_robot_uin_range(self):
        """
        :return: 获取机器人 QQ 号范围
        """
        return await self.ws_client.post("get_robot_uin_range", {})

    async def ocr_image(self, image: str):
        """
        :param image: 图片路径，支持本地路径和网络路径
        :return: OCR 图片识别
        """
        return await self.ws_client.post("ocr_image", {"image": image})

    async def ocr_image_new(self, image: str):
        """
        :param image: 图片路径，支持本地路径和网络路径
        :return: OCR 图片识别
        """
        return await self.ws_client.post(".ocr_image", {"image": image})

    async def translate_en2zh(self, words: List[str]):
        """
        :param words: 待翻译的单词列表
        :return: 英文翻译为中文
        """
        return await self.ws_client.post("translate_en2zh", {"words": words})

    async def get_login_info(self):
        """
        :return: 获取登录号信息
        """
        return await self.ws_client.post("get_login_info", {})

    async def set_input_status(self, event_type: int, user_id: Union[int, str]):
        """
        :param event_type: 状态类型
        :param user_id: QQ 号
        :return: 设置输入状态
        """
        return await self.ws_client.post(
            "set_input_status", {"eventType": event_type, "user_id": user_id}
        )

    async def download_file(
        self,
        thread_count: int,
        headers: Union[Dict, str],
        base64: Optional[str] = None,
        url: Optional[str] = None,
        name: Optional[str] = None,
    ):
        """
        :param thread_count: 下载线程数
        :param headers: 请求头
        :param base64: base64 编码的图片，二选一
        :param url: 图片 URL，二选一
        :param name: 文件名（可选）
        :return: 下载文件
        """
        params = {
            "thread_count": thread_count,
            "headers": headers,
        }
        if base64:
            params["base64"] = base64
            if name:
                params["name"] = name
        elif url:
            params["url"] = url
            if name:
                params["name"] = name
        return await self.ws_client.post("download_file", params)

    async def get_cookies(self, domain: str):
        """
        :param domain: 域名
        :return: 获取 cookies
        """
        return await self.ws_client.post("get_cookies", {"domain": domain})

    async def handle_quick_operation(self, context: Dict, operation: Dict):
        """
        :param context: 事件数据对象
        :param operation: 快速操作对象
        :return: 对事件执行快速操作
        """
        return await self.ws_client.post(
            ".handle_quick_operation", {"context": context, "operation": operation}
        )

    async def get_csrf_token(self):
        """
        :return: 获取 CSRF Token
        """
        return await self.ws_client.post("get_csrf_token", {})

    async def del_group_notice(self, group_id: Union[int, str], notice_id: str):
        """
        :param group_id: 群号
        :param notice_id: 通知 ID
        :return: 删除群公告
        """
        return await self.ws_client.post(
            "_del_group_notice", {"group_id": group_id, "notice_id": notice_id}
        )

    async def get_credentials(self, domain: str):
        """
        :param domain: 域名
        :return: 获取 QQ 相关接口凭证
        """
        return await self.ws_client.post("get_credentials", {"domain": domain})

    async def get_model_show(self, model: str):
        """
        :param model: 模型名
        :return: 获取模型显示
        """
        return await self.ws_client.post("_get_model_show", {"model": model})

    async def can_send_image(self):
        """
        :return: 检查是否可以发送图片
        """
        return await self.ws_client.post("can_send_image", {})

    async def nc_get_packet_status(self):
        """
        :return: 获取 packet 状态
        """
        return await self.ws_client.post("nc_get_packet_status", {})

    async def can_send_record(self):
        """
        :return: 检查是否可以发送语音
        """
        return await self.ws_client.post("can_send_record", {})

    async def get_status(self):
        """
        :return: 获取状态
        """
        return await self.ws_client.post("get_status", {})

    async def nc_get_rkey(self):
        """
        :return: 获取 rkey
        """
        return await self.ws_client.post("nc_get_rkey", {})

    async def get_version_info(self):
        """
        :return: 获取版本信息
        """
        return await self.ws_client.post("get_version_info", {})

    async def get_group_shut_list(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群禁言列表
        """
        return await self.ws_client.post("get_group_shut_list", {"group_id": group_id})

    async def post_group_msg(
        self,
        group_id: Union[int, str],
        message: Union[str, List[Dict]] = None,
    ):
        """
        :param group_id: 群号
        :param message: 消息内容
        :return: 发送群消息
        """
        if not message:
            return {"code": 0, "msg": "消息不能为空"}
        return await self.ws_client.post(
            "send_group_msg", {"group_id": group_id, "message": message}
        )

    async def post_private_msg(
        self,
        user_id: Union[int, str],
        message: Union[str, List[Dict]] = None,
    ):
        """
        :param user_id: QQ 号
        :param message: 消息内容
        :return: 发送私聊消息
        """
        if not message:
            return {"code": 0, "msg": "消息不能为空"}
        return await self.ws_client.post(
            "send_private_msg", {"user_id": user_id, "message": message}
        )

    async def post_group_file(
        self,
        group_id: Union[int, str],
        file: str,
        name: str,
        folder: Optional[str] = None,
    ):
        """
        :param group_id: 群号
        :param file: 文件路径
        :param name: 上传后的文件名
        :param folder: 上传的文件夹路径（可选）
        :return: 发送群文件
        """
        return await self.ws_client.post(
            "upload_group_file",
            {"group_id": group_id, "file": file, "name": name, "folder": folder},
        )

    async def post_private_file(
        self,
        user_id: Union[int, str],
        file: str,
        name: str,
    ):
        """
        :param user_id: QQ 号
        :param file: 文件路径
        :param name: 上传后的文件名
        :return: 发送私聊文件
        """
        return await self.ws_client.post(
            "upload_private_file",
            {"user_id": user_id, "file": file, "name": name},
        )