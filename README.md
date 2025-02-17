# Fbot

一个基于 ncatbot 开发的聊天机器人/应用框架，支持插件扩展、日志管理等功能。

同功能项目[liyihao1110/ncatbot](https://github.com/liyihao1110/NcatBot)

本项目为新手的练习之作

## 项目特点

- pass

## 安装

确保已安装 Python（>= 3.10）。

1. 克隆仓库：

```sh
git clone https://github.com/Fish-LP/FBot.git
```

2. 安装(因为未发布pip包，使用开发模式安装)

```sh
pip install -e Fbot
```

## 使用

### 插件扩展

插件放置在 plugins 文件夹下

pass

### 日志配置

日志相关设置在 Logger.py 中定义，通过环境变量可以调整日志级别及格式，例如：

```sh
# 设置控制台日志级别为 DEBUG
export LOG_LEVEL=DEBUG

# 设置日志文件路径、文件名格式等
export LOG_FILE_PATH=./logs
export LOG_FILE_NAME=bot_%Y%m%d.log
```

## 开发与测试

- pass

## 许可证

本项目基于 MIT 许可证 开源，详细内容请参见许可证文件。

## 贡献

欢迎贡献代码、提交问题或提出新特性，更多详情请参考仓库中的贡献指南。（虽然还没有）

## 联系方式

- 作者：Fish-LP
- 邮箱：fish.zh@outlook.com
- 项目地址：[https://github.com/Fish-LP/FBot](https://github.com/Fish-LP/FBot)
