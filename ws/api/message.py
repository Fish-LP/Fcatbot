from typing import Union
from ...DataModels import MessageChain

class MessageAPi:
    '''消息接口'''
    
    async def mark_msg_as_read(self, group_id: Union[int, str] = None, user_id: Union[int, str] = None):
        """
        :param group_id: 群号, 二选一
        :param user_id: QQ号, 二选一
        :return: 设置消息已读
        """
        if group_id:
            return await self.ws_client.api("/mark_msg_as_read", {"group_id": group_id})
        elif user_id:
            return await self.ws_client.api("/mark_msg_as_read", {"user_id": user_id})

    async def mark_group_msg_as_read(self, group_id: Union[int, str]):
        """
        :param group_id: 群号
        :return: 设置群聊已读
        """
        return await self.ws_client.api("/mark_group_msg_as_read", {"group_id": group_id})

    async def mark_private_msg_as_read(self, user_id: Union[int, str]):
        """
        :param user_id: QQ号
        :return: 设置私聊已读
        """
        return await self.ws_client.api("/mark_private_msg_as_read", {"user_id": user_id})

    async def mark_all_as_read(self):
        """
        :return: 设置所有消息已读
        """
        return await self.ws_client.api("/_mark_all_as_read", {})

    async def delete_msg(self, message_id: Union[int, str]):
        """
        :param message_id: 消息ID
        :return: 删除消息
        """
        return await self.ws_client.api("/delete_msg", {"message_id": message_id})

    async def get_msg(self, message_id: Union[int, str]):
        """
        :param message_id: 消息ID
        :return: 获取消息
        """
        return await self.ws_client.api("/get_msg", {"message_id": message_id})

    async def get_image(self, image_id: str):
        """
        :param image_id: 图片ID
        :return: 获取图片消息详情
        """
        return await self.ws_client.api("/get_image", {"file_id": image_id})

    async def get_record(self, record_id: str, output_type: str = "mp3"):
        """
        :param record_id: 语音ID
        :param output_type: 输出类型，枚举值: mp3, amr, wma, m4a, spx, ogg, wav, flac，默认为mp3
        :return: 获取语音消息详情
        """
        return await self.ws_client.api(
            "/get_record", {"file_id": record_id, "out_format": output_type}
        )

    async def get_file(self, file_id: str):
        """
        :param file_id: 文件ID
        :return: 获取文件消息详情
        """
        return await self.ws_client.api("/get_file", {"file_id": file_id})

    async def get_group_msg_history(
        self,
        group_id: Union[int, str],
        message_seq: Union[int, str],
        count: int,
        reverse_order: bool,
    ):
        """
        :param group_id: 群号
        :param message_seq: 消息序号
        :param count: 数量
        :param reverse_order: 是否倒序
        :return: 获取群消息历史记录
        """
        return await self.ws_client.api(
            "/get_group_msg_history",
            {
                "group_id": group_id,
                "message_seq": message_seq,
                "count": count,
                "reverseOrder": reverse_order,
            },
        )

    async def set_msg_emoji_like(
        self, message_id: Union[int, str], emoji_id: int, emoji_set: bool
    ):
        """
        :param message_id: 消息ID
        :param emoji_id: 表情ID
        :param emoji_set: 设置
        :return: 设置消息表情点赞
        """
        return await self.ws_client.api(
            "/set_msg_emoji_like",
            {"message_id": message_id, "emoji_id": emoji_id, "set": emoji_set},
        )

    async def get_friend_msg_history(
        self,
        user_id: Union[int, str],
        message_seq: Union[int, str],
        count: int,
        reverse_order: bool,
    ):
        """
        :param user_id: QQ号
        :param message_seq: 消息序号
        :param count: 数量
        :param reverse_order: 是否倒序
        :return: 获取好友消息历史记录
        """
        return await self.ws_client.api(
            "/get_friend_msg_history",
            {
                "user_id": user_id,
                "message_seq": message_seq,
                "count": count,
                "reverseOrder": reverse_order,
            },
        )

    async def get_recent_contact(self, count: int):
        """
        获取的最新消息是每个会话最新的消息
        :param count: 会话数量
        :return: 最近消息列表
        """
        return await self.ws_client.api("/get_recent_contact", {"count": count})

    async def fetch_emoji_like(
        self,
        message_id: Union[int, str],
        emoji_id: str,
        emoji_type: str,
        group_id: Union[int, str] = None,
        user_id: Union[int, str] = None,
        count: int = None,
    ):
        """
        :param message_id: 消息ID
        :param emoji_id: 表情ID
        :param emoji_type: 表情类型
        :param group_id: 群号, 二选一
        :param user_id: QQ号, 二选一
        :param count: 数量, 可选
        :return: 获取贴表情详情
        """
        params = {
            "message_id": message_id,
            "emojiId": emoji_id,
            "emojiType": emoji_type,
        }
        if group_id:
            params["group_id"] = group_id
        elif user_id:
            params["user_id"] = user_id
        if count:
            params["count"] = count
        return await self.ws_client.api("/fetch_emoji_like", params)

    async def get_forward_msg(self, message_id: str):
        """
        :param message_id: 消息ID
        :return: 获取合并转发消息
        """
        return await self.ws_client.api("/get_forward_msg", {"message_id": message_id})

    async def send_poke(self, user_id: Union[int, str], group_id: Union[int, str] = None):
        """
        :param user_id: QQ号
        :param group_id: 群号, 可选，不填则为私聊
        :return: 发送戳一戳
        """
        params = {"user_id": user_id}
        if group_id:
            params["group_id"] = group_id
        return await self.ws_client.api("/send_poke", params)

    async def forward_friend_single_msg(self, message_id: str, user_id: Union[int, str]):
        """
        :param message_id: 消息ID
        :param user_id: 发送对象QQ号
        :return: 转发好友消息
        """
        return await self.ws_client.api(
            "/forward_friend_single_msg", {"user_id": user_id, "message_id": message_id}
        )

    async def send_private_forward_msg(self, user_id: Union[int, str], messages: MessageChain):
        """
        :param user_id: 发送对象QQ号
        :param messages: 消息列表
        :return: 合并转发私聊消息
        """
        if len(messages) == 0:
            return None
        
        return await self.ws_client.api(
            "/send_private_forward_msg",
            {
                "messages": messages.to_dict(),
                "user_id": user_id
                }
            )