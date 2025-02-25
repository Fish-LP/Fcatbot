from typing import Union
from ...DataModels import MessageChain

class GroupApi:
    '''群组接口'''

    async def set_group_kick(
        self,
        group_id: Union[int, str],
        user_id: Union[int, str],
        reject_add_request: bool = False,
    ):
        """
        :param group_id: 群号
        :param user_id: QQ号
        :param reject_add_request: 是否群拉黑
        :return: 踢出群成员
        """
        return await self.ws_client.api(
            "set_group_kick",
            {
                "group_id": group_id,
                "user_id": user_id,
                "reject_add_request": reject_add_request,
            },
        )

    async def set_group_ban(
        self, group_id: Union[int, str], user_id: Union[int, str], duration: int
    ):
        """
        :param group_id: 群号
        :param user_id: QQ号
        :param duration: 禁言时长,单位秒,0为取消禁言
        :return: 群组禁言
        """
        return await self.ws_client.api(
            "set_group_ban",
            {"group_id": group_id, "user_id": user_id, "duration": duration},
        )

    async def get_group_system_msg(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群系统消息
        """
        return await self.ws_client.api("get_group_system_msg", {"group_id": group_id})

    async def get_essence_msg_list(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取精华消息列表
        """
        return await self.ws_client.api("get_essence_msg_list", {"group_id": group_id})

    async def set_group_whole_ban(self, group_id: Union[int, str], enable: bool):
        """
        :param group_id: 群号
        :param enable: 是否禁言
        :return: 群组全员禁言
        """
        return await self.ws_client.api(
            "set_group_whole_ban", {"group_id": group_id, "enable": enable}
        )

    async def set_group_portrait(self, group_id: Union[int, str], file: str):
        """
        :param group_id: 群号
        :param file: 文件路径,支持网络路径和本地路径
        :return: 设置群头像
        """
        return await self.ws_client.api(
            "set_group_portrait", {"group_id": group_id, "file": file}
        )

    async def set_group_admin(
        self, group_id: Union[int, str], user_id: Union[int, str], enable: bool
    ):
        """
        :param group_id: 群号
        :param user_id: QQ号
        :param enable: 是否设置为管理
        :return: 设置群管理员
        """
        return await self.ws_client.api(
            "set_group_admin",
            {"group_id": group_id, "user_id": user_id, "enable": enable},
        )

    async def set_essence_msg(self, message_id: Union[int, str]):
        """
        :param message_id: 消息ID
        :return: 设置精华消息
        """
        return await self.ws_client.api("set_essence_msg", {"message_id": message_id})

    async def set_group_card(
        self, group_id: Union[int, str], user_id: Union[int, str], card: str
    ):
        """
        :param group_id: 群号
        :param user_id: QQ号
        :param card: 群名片,为空则为取消群名片
        :return: 设置群名片
        """
        return await self.ws_client.api(
            "set_group_card", {"group_id": group_id, "user_id": user_id, "card": card}
        )

    async def delete_essence_msg(self, message_id: Union[int, str]):
        """
        :param message_id: 消息ID
        :return: 删除精华消息
        """
        return await self.ws_client.api("delete_essence_msg", {"message_id": message_id})

    async def set_group_name(self, group_id: Union[int, str], group_name: str):
        """
        :param group_id: 群号
        :param group_name: 群名
        :return: 设置群名
        """
        return await self.ws_client.api(
            "set_group_name", {"group_id": group_id, "group_name": group_name}
        )

    async def set_group_leave(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 退出群组
        """
        return await self.ws_client.api("set_group_leave", {"group_id": group_id})

    async def send_group_notice(
        self, group_id: Union[int, str], content: str, image: str = None
    ):
        """
        :param group_id: 群号
        :param content: 内容
        :param image: 图片路径，可选
        :return: 发送群公告
        """
        if image:
            return await self.ws_client.api(
                "_send_group_notice",
                {"group_id": group_id, "content": content, "image": image},
            )
        else:
            return await self.ws_client.api(
                "_send_group_notice", {"group_id": group_id, "content": content}
            )

    async def get_group_notice(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群公告
        """
        return await self.ws_client.api("_get_group_notice", {"group_id": group_id})

    async def set_group_special_title(
        self, group_id: Union[int, str], user_id: Union[int, str], special_title: str
    ):
        """
        :param group_id: 群号
        :param user_id: QQ号
        :param special_title: 群头衔
        :return: 设置群头衔
        """
        return await self.ws_client.api(
            "set_group_special_title",
            {"group_id": group_id, "user_id": user_id, "special_title": special_title},
        )

    async def upload_group_file(
        self, group_id: Union[int, str], file: str, name: str, folder_id: str
    ):
        """
        :param group_id: 群号
        :param file: 文件路径
        :param name: 文件名
        :param folder_id: 文件夹ID
        :return: 上传群文件
        """
        return await self.ws_client.api(
            "upload_group_file",
            {"group_id": group_id, "file": file, "name": name, "folder_id": folder_id},
        )

    async def set_group_add_request(self, flag: str, approve: bool, reason: str = None):
        """
        :param flag: 请求flag
        :param approve: 是否同意
        :param reason: 拒绝理由
        :return: 处理加群请求
        """
        if approve:
            return await self.ws_client.api(
                "set_group_add_request", {"flag": flag, "approve": approve}
            )
        else:
            return await self.ws_client.api(
                "set_group_add_request",
                {"flag": flag, "approve": approve, "reason": reason},
            )

    async def get_group_info(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群信息
        """
        return await self.ws_client.api("get_group_info", {"group_id": group_id})

    async def get_group_info_ex(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群信息(拓展)
        """
        return await self.ws_client.api("get_group_info_ex", {"group_id": group_id})

    async def create_group_file_folder(
        self, group_id: Union[int, str], folder_name: str
    ):
        """
        :param group_id: 群号
        :param folder_name: 文件夹名
        :return: 创建群文件文件夹
        """
        return await self.ws_client.api(
            "create_group_file_folder",
            {"group_id": group_id, "folder_name": folder_name},
        )

    async def delete_group_file(self, group_id: Union[int, str], file_id: str):
        """
        :param group_id: 群号
        :param file_id: 文件ID
        :return: 删除群文件
        """
        return await self.ws_client.api(
            "delete_group_file", {"group_id": group_id, "file_id": file_id}
        )

    async def delete_group_folder(self, group_id: Union[int, str], folder_id: str):
        """
        :param group_id: 群号
        :param folder_id: 文件夹ID
        :return: 删除群文件文件夹
        """
        return await self.ws_client.api(
            "delete_group_folder", {"group_id": group_id, "folder_id": folder_id}
        )

    async def get_group_file_system_info(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群文件系统信息
        """
        return await self.ws_client.api(
            "get_group_file_system_info", {"group_id": group_id}
        )

    async def get_group_root_files(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群根目录文件列表
        """
        return await self.ws_client.api("get_group_root_files", {"group_id": group_id})

    async def get_group_files_by_folder(
        self, group_id: Union[int, str], folder_id: str, file_count: int
    ):
        """
        :param group_id: 群号
        :param folder_id: 文件夹ID
        :param file_count: 文件数量
        :return: 获取群文件列表
        """
        return await self.ws_client.api(
            "get_group_files_by_folder",
            {"group_id": group_id, "folder_id": folder_id, "file_count": file_count},
        )

    async def get_group_file_url(self, group_id: Union[int, str], file_id: str):
        """
        :param group_id: 群号
        :param file_id: 文件ID
        :return: 获取群文件URL
        """
        return await self.ws_client.api(
            "get_group_file_url", {"group_id": group_id, "file_id": file_id}
        )

    async def get_group_list(self, no_cache: bool = False):
        """
        :param no_cache: 不缓存，默认为false
        :return: 获取群列表
        """
        return await self.ws_client.api("get_group_list", {"no_cache": no_cache})

    async def get_group_member_info(
        self, group_id: Union[int, str], user_id: Union[int, str], no_cache: bool
    ):
        """
        :param group_id: 群号
        :param user_id: QQ号
        :param no_cache: 不缓存
        :return: 获取群成员信息
        """
        return await self.ws_client.api(
            "get_group_member_info",
            {"group_id": group_id, "user_id": user_id, "no_cache": no_cache},
        )

    async def get_group_member_list(
        self, group_id: Union[int, str], no_cache: bool = False
    ):
        """
        :param group_id: 群号
        :param no_cache: 不缓存
        :return: 获取群成员列表
        """
        return await self.ws_client.api(
            "get_group_member_list", {"group_id": group_id, "no_cache": no_cache}
        )

    async def get_group_honor_info(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群荣誉信息
        """
        return await self.ws_client.api("get_group_honor_info", {"group_id": group_id})

    async def get_group_at_all_remain(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群 @全体成员 剩余次数
        """
        return await self.ws_client.api("get_group_at_all_remain", {"group_id": group_id})

    async def get_group_ignored_notifies(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 获取群过滤系统消息
        """
        return await self.ws_client.api(
            "get_group_ignored_notifies", {"group_id": group_id}
        )

    async def set_group_sign(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 群打卡
        """
        return await self.ws_client.api("set_group_sign", {"group_id": group_id})

    async def send_group_sign(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 群打卡
        """
        return await self.ws_client.api("send_group_sign", {"group_id": group_id})

    async def get_ai_characters(
        self, group_id: Union[int, str], chat_type: Union[int, str]
    ):
        """
        :param group_id: 群号
        :param chat_type: 聊天类型
        :return: 获取AI语音人物
        """
        return await self.ws_client.api(
            "get_ai_characters", {"group_id": group_id, "chat_type": chat_type}
        )

    async def send_group_ai_record(
        self, group_id: Union[int, str], character: str, text: str
    ):
        """
        :param group_id: 群号
        :param character: AI语音人物,即character_id
        :param text: 文本
        :return: 发送群AI语音
        """
        return await self.ws_client.api(
            "send_group_ai_record",
            {"group_id": group_id, "character": character, "text": text},
        )

    async def get_ai_record(self, group_id: Union[int, str], character: str, text: str):
        """
        :param group_id: 群号
        :param character: AI语音人物,即character_id
        :param text: 文本
        :return: 获取AI语音
        """
        return await self.ws_client.api(
            "get_ai_record",
            {"group_id": group_id, "character": character, "text": text},
        )

    async def forward_group_single_msg(
        self, message_id: str, group_id: Union[int, str]
    ):
        """
        :param message_id: 消息ID
        :param group_id: 群号
        :return: 转发群聊消息
        """
        return await self.ws_client.api(
            "forward_group_single_msg",
            {"group_id": group_id, "message_id": message_id},
        )

    async def send_group_forward_msg(
        self, group_id: Union[int, str], messages: MessageChain
    ):
        """
        :param group_id: 群号
        :param messages: 消息列表
        :return: 合并转发的群聊消息
        """
        if len(messages) == 0:
            return None

        return await self.ws_client.api(
            "send_private_forward_msg",
            {
                "messages": MessageChain.to_dict(),
                "group_id": group_id
                }
        )