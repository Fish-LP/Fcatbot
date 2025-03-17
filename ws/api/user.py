# -------------------------
# @Author       : Ncatbot
# @Date         : 2025-02-12 13:41:02
# @LastEditors  : Fish-LP fish.zh@outlook.com
# @LastEditTime : 2025-03-10 21:40:56
# @Description  : 当时确实是 MIT License 后来给改了
# @Copyright (c) 2025 by Ncatbot, MIT License 
# -------------------------
from ...data_models import Status
from typing import Union

class UserAPi:
    '''用户接口'''
    
    async def set_qq_profile(self, nickname: str, personal_note: str, sex: str):
        """
        :param nickname: 昵称
        :param personal_note: 个性签名
        :param sex: 性别
        :return: 设置账号信息
        """
        return await self.ws_client.api(
            "set_qq_profile",
            {
                "nickname": nickname,
                "personal_note": personal_note,
                "sex": sex},
        )

    async def get_user_card(self, user_id: str, phone_number: str):
        """
        :param user_id: QQ号
        :param phone_number: 手机号
        :return: 获取用户名片
        """
        return await self.ws_client.api(
            "ArkSharePeer",
            {
                "user_id": user_id,
                "phoneNumber": phone_number
            }
        )

    async def get_group_card(self, group_id: str, phone_number: str):
        """
        :param group_id: 群号
        :param phone_number: 手机号
        :return: 获取群名片
        """
        return await self.ws_client.api(
            "ArkSharePeer",
            {
                "group_id": group_id,
                "phoneNumber": phone_number
            }
        )

    async def get_share_group_card(self, group_id: str):
        """
        :param group_id: 群号
        :return: 获取群共享名片
        """
        return await self.ws_client.api(
            "ArkShareGroup",
            {"group_id": group_id}
        )

    async def set_online_status(self, status: str):
        """
        :param status: 在线状态
        :return: 设置在线状态
        """
        if hasattr(Status, status):
            status = getattr(Status, status)
        return await self.ws_client.api(
            "set_online_status",
            dict(status)
        )

    async def get_friends_with_category(self):
        """
        :return: 获取好友列表
        """
        return await self.ws_client.api(
            "get_friends_with_category",
            {}
        )

    async def set_qq_avatar(self, avatar: str):
        """
        :param avatar: 头像路径,支持本地路径和网络路径
        :return: 设置头像
        """
        return await self.ws_client.api(
            "set_qq_avatar",
            {"file": avatar}
        )

    async def send_like(self, user_id: str, times: int):
        """
        :param user_id: QQ号
        :param times: 次数
        :return: 发送赞
        """
        return await self.ws_client.api(
            "send_like",
            {
                "user_id": user_id,
                "times": times
            }
        )

    async def create_collection(self, rawdata: str, brief: str):
        """
        :param rawdata: 内容
        :param brief: 标题
        :return: 创建收藏
        """
        return await self.ws_client.api(
            "create_collection",
            {
                "rawData": rawdata,
                "brief": brief
            }
        )

    async def set_friend_add_request(self, flag: str, approve: bool, remark: str):
        """
        :param flag: 请求ID
        :param approve: 是否同意
        :param remark: 备注
        :return: 设置好友请求
        """
        return await self.ws_client.api(
            "set_friend_add_request",
            {
                "flag": flag,
                "approve": approve,
                "remark": remark},
        )

    async def set_self_long_nick(self, longnick: str):
        """
        :param longnick: 个性签名内容
        :return: 设置个性签名
        """
        return await self.ws_client.api(
            "set_self_longnick",
            {"longNick": longnick}
        )

    async def get_stranger_info(self, user_id: Union[int, str]):
        """
        :param user_id: QQ号
        :return: 获取陌生人信息
        """
        return await self.ws_client.api(
            "get_stranger_info",
            {"user_id": user_id}
        )

    async def get_friend_list(self, cache: bool):
        """
        :param cache: 是否使用缓存
        :return: 获取好友列表
        """
        return await self.ws_client.api(
            "get_friend_list",
            {"no_cache": cache}
        )

    async def get_profile_like(self):
        """
        :return: 获取个人资料卡点赞数
        """
        return await self.ws_client.api(
            "get_profile_like",
            {}
        )

    async def fetch_custom_face(self, count: int):
        """
        :param count: 数量
        :return: 获取收藏表情
        """
        return await self.ws_client.api(
            "fetch_custom_face",
            {"count": count}
        )

    async def upload_private_file(self, user_id: Union[int, str], file: str, name: str):
        """
        :param user_id: QQ号
        :param file: 文件路径
        :param name: 文件名
        :return: 上传私聊文件
        """
        return await self.ws_client.api(
            "upload_private_file",
            {
                "user_id": user_id,
                "file": file,
                "name": name
            }
        )

    async def delete_friend(
        self,
        user_id: Union[int, str],
        friend_id: Union[int, str],
        temp_block: bool,
        temp_both_del: bool,
    ):
        """
        :param user_id: QQ号
        :param friend_id: 好友ID
        :param temp_block: 拉黑
        :param temp_both_del: 双向删除
        :return: 删除好友
        """
        return await self.ws_client.api(
            "delete_friend",
            {
                "user_id": user_id,
                "friend_id": friend_id,
                "temp_block": temp_block,
                "temp_both_del": temp_both_del,
            }
        )

    async def nc_get_user_status(self, user_id: Union[int, str]):
        """
        :param user_id: QQ号
        :return: 获取用户状态
        """
        return await self.ws_client.api(
            "nc_get_user_status",
            {"user_id": user_id}
        )

    async def get_mini_app_ark(self, app_json: dict):
        """
        :param app_json: 小程序JSON
        :return: 获取小程序卡片
        """
        return await self.ws_client.api(
            "get_mini_app_ark",
            app_json
        )