import asyncio
from http.client import HTTPConnection
import json
from urllib.parse import urlparse, urlencode

class HttpClient:
    """
    一个简单的HTTP客户端，用于发送HTTP请求。
    支持POST、GET、PUT、PATCH 和 DELETE 等HTTP方法。
    """

    def __init__(self, uri: str, headers: dict = None):
        """
        初始化HTTP客户端。

        :param uri: 目标服务器的基础URI（例如 'http://api.example.com' 或 'https://api.example.com'）
        :param headers: 默认的请求头（可选）
        """
        self.uri = uri.rstrip('/')
        self.headers = headers or {}
        self.connection = None
        self._parse_uri()

    def _parse_uri(self):
        """
        解析URI，提取主机名、路径和查询参数。
        """
        parsed_uri = urlparse(self.uri)
        self.scheme = parsed_uri.scheme
        self.host = parsed_uri.netloc
        self.base_path = parsed_uri.path or '/'
        self.base_path = self.base_path.rstrip('/') if self.base_path != '/' else self.base_path

    def connect(self):
        """
        建立到目标服务器的HTTP连接。
        """
        if self.scheme.lower() == "https":
            raise NotImplementedError("目前不支持HTTPS连接")
        else:
            self.connection = HTTPConnection(self.host)
        self.connection.connect()

    def close(self):
        """
        关闭HTTP连接。
        """
        if self.connection:
            self.connection.close()

    def _build_request_path(self, addr: str, params: dict = None):
        """
        构建完整的请求路径，包括查询参数。

        :param addr: 相对路径或完整路径
        :param params: 查询参数（字典）
        :return: 带查询参数的完整路径
        """
        path = self.base_path.rstrip('/') + addr.lstrip('/') if self.base_path != '/' else addr
        if params:
            # 将查询参数编码为字符串
            query = urlencode(params)
            if '?' in path:
                path += '&' + query
            else:
                path += '?' + query
        return path

    def _send_request(self, method: str, addr: str, data=None, params: dict = None, headers: dict = None):
        """
        发送HTTP请求的内部方法。

        :param method: HTTP方法
        :param addr: 相对路径或完整路径
        :param data: 请求体数据
        :param params: 查询参数
        :param headers: 自定义请求头
        :return: 响应数据
        """
        final_headers = {**self.headers, **(headers or {})}

        # 解析目标地址，判断是否为完整URL
        parsed_addr = urlparse(addr)
        if parsed_addr.scheme:
            # 如果addr是完整URL，则提取host和path
            host = parsed_addr.netloc
            path = parsed_addr.path
            if parsed_addr.query:
                # 如果同时提供params参数，会导致重复的查询参数
                if params:
                    raise ValueError("如果addr是带有查询参数的完整URL，则不应提供params")
                path += '?' + parsed_addr.query
        else:
            host = self.host
            path = self._build_request_path(addr, params)

        # 建立连接
        self.connect()

        body = None
        if method.upper() in ["POST", "PUT", "PATCH"] and data is not None:
            # 根据数据类型生成请求体
            if isinstance(data, dict):
                body = json.dumps(data)
                final_headers["Content-Type"] = "application/json"
            elif isinstance(data, str):
                body = data
                final_headers["Content-Type"] = "text/plain"
            elif isinstance(data, bytes):
                body = data
                final_headers["Content-Type"] = "application/octet-stream"
            else:
                raise TypeError("Data must be a dictionary, string, or bytes.")

            # 设置Content-Length
            final_headers["Content-Length"] = str(len(body))

        try:
            # 发送请求
            self.connection.request(method.upper(), path, body=body, headers=final_headers)
            response = self.connection.getresponse()

            return {
                "status": response.status,
                "headers": dict(response.getheaders()),
                "body": response.read().decode("utf-8")
            }
        except Exception as e:
            self.close()  # 关闭连接以避免资源泄漏
            raise e
        finally:
            self.close()  # 确保连接始终被关闭

    def post(self, addr: str, data=None, params: dict = None, headers: dict = None):
        """
        发送POST请求。

        :param addr: 相对路径或完整URL
        :param data: 请求体数据
        :param params: 查询参数
        :param headers: 自定义请求头
        :return: 响应数据
        """
        return self._send_request("POST", addr, data=data, params=params, headers=headers)

    def get(self, addr: str, params: dict = None, headers: dict = None):
        """
        发送GET请求。

        :param addr: 相对路径或完整URL
        :param params: 查询参数
        :param headers: 自定义请求头
        :return: 响应数据
        """
        return self._send_request("GET", addr, params=params, headers=headers)

    def put(self, addr: str, data=None, params: dict = None, headers: dict = None):
        """
        发送PUT请求。

        :param addr: 相对路径或完整URL
        :param data: 请求体数据
        :param params: 查询参数
        :param headers: 自定义请求头
        :return: 响应数据
        """
        return self._send_request("PUT", addr, data=data, params=params, headers=headers)

    def patch(self, addr: str, data=None, params: dict = None, headers: dict = None):
        """
        发送PATCH请求。

        :param addr: 相对路径或完整URL
        :param data: 请求体数据
        :param params: 查询参数
        :param headers: 自定义请求头
        :return: 响应数据
        """
        return self._send_request("PATCH", addr, data=data, params=params, headers=headers)

    def delete(self, addr: str, params: dict = None, headers: dict = None):
        """
        发送DELETE请求。

        :param addr: 相对路径或完整URL
        :param params: 查询参数
        :param headers: 自定义请求头
        :return: 响应数据
        """
        return self._send_request("DELETE", addr, params=params, headers=headers)