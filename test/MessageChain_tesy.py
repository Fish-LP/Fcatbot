import json
from Fcatbot import MessageChain
from Fcatbot.DataModels.message.Nope import *
from Fcatbot.utils import TestSuite, Color

def run_message_chain_tests():
    suite = TestSuite()

    # 测试消息链初始化
    elements = [
        {"type": "text", "data": {"text": "Hello"}},
        {"type": "at", "data": {"qq": "123456"}},
        {"type": "image", "data": {"file": "image.jpg"}}
    ]
    message_chain = MessageChain(elements)
    suite.add_test(
        description="消息链初始化",
        actual=len(message_chain),
        expected=3
    )

    # 测试添加单个元素
    message_chain = MessageChain()
    message_chain.add({"type": "text", "data": {"text": "Hello"}})
    message_chain.add(Text(text="World"))
    suite.add_test(
        description="添加单个元素",
        actual=len(message_chain),
        expected=2
    )

    # 测试添加多个元素
    message_chain = MessageChain()
    elements = [
        {"type": "text", "data": {"text": "Hello"}},
        Text(text="World"),
        Image(file="image.jpg")
    ]
    suite.add_test(
        description="添加多个元素",
        actual=len(message_chain),
        expected=3
    )

    # 测试移除指定类型的元素
    message_chain = MessageChain([
        {"type": "text", "data": {"text": "Hello"}},
        {"type": "at", "data": {"qq": "123456"}},
        {"type": "image", "data": {"file": "image.jpg"}}
    ])
    message_chain.remove(Text)
    suite.add_test(
        description="移除指定类型的元素",
        actual=len(message_chain),
        expected=2
    )

    # 测试保留指定类型的元素
    message_chain = MessageChain([
        {"type": "text", "data": {"text": "Hello"}},
        {"type": "at", "data": {"qq": "123456"}},
        {"type": "image", "data": {"file": "image.jpg"}}
    ])
    message_chain.filter([Text, Image])
    suite.add_test(
        description="保留指定类型的元素",
        actual=len(message_chain),
        expected=2
    )

    # 测试将消息链转换为字典列表
    message_chain = MessageChain([
        Text(text="Hello"),
        At(qq="123456"),
        Image(file="image.jpg")
    ])
    expected_dict = [
        {"type": "text", "data": {"text": "Hello"}},
        {"type": "at", "data": {"qq": "123456"}},
        {"type": "image", "data": {"file": "image.jpg"}}
    ]
    suite.add_test(
        description="将消息链转换为字典列表",
        actual=message_chain.to_dict(),
        expected=expected_dict
    )

    # 测试清空消息链
    message_chain = MessageChain([
        Text(text="Hello"),
        At(qq="123456")
    ])
    message_chain.clear()
    suite.add_test(
        description="清空消息链",
        actual=len(message_chain),
        expected=0
    )

    # 测试消息链的字符串表示
    message_chain = MessageChain([
        Text(text="Hello"),
        At(qq="123456")
    ])
    expected_json = json.dumps([
        {"type": "text", "data": {"text": "Hello"}},
        {"type": "at", "data": {"qq": "123456"}}
    ], ensure_ascii=False, indent=2)
    suite.add_test(
        description="消息链的字符串表示",
        actual=str(message_chain),
        expected=expected_json
    )

    # 测试消息链的迭代功能
    message_chain = MessageChain([
        Text(text="Hello"),
        At(qq="123456"),
        Image(file="image.jpg")
    ])
    texts = [element.text if isinstance(element, Text) else None for element in message_chain]
    suite.add_test(
        description="消息链的迭代功能",
        actual=texts,
        expected=["Hello", None, None]
    )

    # 测试通过索引访问元素
    message_chain = MessageChain([
        Text(text="Hello"),
        At(qq="123456"),
        Image(file="image.jpg")
    ])
    suite.add_test(
        description="通过索引访问元素",
        actual=message_chain[0].text,
        expected="Hello"
    )

    # 测试添加文本消息元素
    message_chain = MessageChain()
    message_chain.add_text("Hello")
    suite.add_test(
        description="添加文本消息元素",
        actual=message_chain[0].text,
        expected="Hello"
    )

    # 测试添加 @ 消息元素
    message_chain = MessageChain()
    message_chain.add_at("123456")
    suite.add_test(
        description="添加 @ 消息元素",
        actual=message_chain[0].qq,
        expected="123456"
    )

    # 测试添加 @全体消息元素
    message_chain = MessageChain()
    message_chain.add_at_all()
    suite.add_test(
        description="添加 @全体消息元素",
        actual=isinstance(message_chain[0], AtAll),
        expected=True
    )

    # 测试添加图片消息元素
    message_chain = MessageChain()
    message_chain.add_image("image.jpg")
    suite.add_test(
        description="添加图片消息元素",
        actual=message_chain[0].file,
        expected="image.jpg"
    )

    # 测试添加表情消息元素
    message_chain = MessageChain()
    message_chain.add_face("123")
    suite.add_test(
        description="添加表情消息元素",
        actual=message_chain[0].id,
        expected="123"
    )

    # 测试添加回复消息元素
    message_chain = MessageChain()
    message_chain.add_reply("reply_id")
    suite.add_test(
        description="添加回复消息元素",
        actual=message_chain[0].reply_to,
        expected="reply_id"
    )

    # 测试添加 JSON 消息元素
    message_chain = MessageChain()
    message_chain.add_json('{"key": "value"}')
    suite.add_test(
        description="添加 JSON 消息元素",
        actual=message_chain[0].data,
        expected='{"key": "value"}'
    )

    # 测试添加语音消息元素
    message_chain = MessageChain()
    message_chain.add_record("record.mp3")
    suite.add_test(
        description="添加语音消息元素",
        actual=message_chain[0].file,
        expected="record.mp3"
    )

    # 测试添加视频消息元素
    message_chain = MessageChain()
    message_chain.add_video("video.mp4")
    suite.add_test(
        description="添加视频消息元素",
        actual=message_chain[0].file,
        expected="video.mp4"
    )

    # 测试添加骰子消息元素
    message_chain = MessageChain()
    message_chain.add_dice()
    suite.add_test(
        description="添加骰子消息元素",
        actual=isinstance(message_chain[0], Dice),
        expected=True
    )

    # 测试添加猜拳消息元素
    message_chain = MessageChain()
    message_chain.add_rps()
    suite.add_test(
        description="添加猜拳消息元素",
        actual=isinstance(message_chain[0], Rps),
        expected=True
    )

    # 测试添加音乐分享消息元素
    message_chain = MessageChain()
    message_chain.add_music("type", "music_id")
    suite.add_test(
        description="添加音乐分享消息元素",
        actual=message_chain[0].music_type,
        expected="type"
    )
    suite.add_test(
        description="添加音乐分享消息元素",
        actual=message_chain[0].id,
        expected="music_id"
    )

    # 测试添加自定义音乐分享消息元素
    message_chain = MessageChain()
    message_chain.add_custom_music("url", "audio", "title", "image", "singer")
    suite.add_test(
        description="添加自定义音乐分享消息元素",
        actual=message_chain[0].url,
        expected="url"
    )
    suite.add_test(
        description="添加自定义音乐分享消息元素",
        actual=message_chain[0].audio,
        expected="audio"
    )
    suite.add_test(
        description="添加自定义音乐分享消息元素",
        actual=message_chain[0].title,
        expected="title"
    )
    suite.add_test(
        description="添加自定义音乐分享消息元素",
        actual=message_chain[0].image,
        expected="image"
    )
    suite.add_test(
        description="添加自定义音乐分享消息元素",
        actual=message_chain[0].singer,
        expected="singer"
    )

    # # 测试添加 Markdown 消息元素
    # message_chain = MessageChain()
    # message_chain.add_markdown({"key": "value"})
    # suite.add_test(
    #     description="添加 Markdown 消息元素",
    #     actual=message_chain[0].markdown,
    #     expected={"key": "value"}
    # )

    # 测试添加转发消息节点
    message_chain = MessageChain()
    content = MessageChain([Text(text="Hello")])
    message_chain.add_nope("user_id", "nickname", content)
    suite.add_test(
        description="添加转发消息节点",
        actual=message_chain[0].data.user_id,
        expected="user_id"
    )
    suite.add_test(
        description="添加转发消息节点",
        actual=message_chain[0].data.nickname,
        expected="nickname"
    )
    suite.add_test(
        description="添加转发消息节点",
        actual=message_chain[0].data.content.to_dict(),
        expected=[{"type": "text", "data": {"text": "Hello"}}]
    )

    suite.run()

if __name__ == "__main__":
    run_message_chain_tests()