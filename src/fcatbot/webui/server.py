"""Web 管理界面后端。

提供:
- 插件列表 + 启用/禁用开关（含依赖检查）
- YAML 配置文件读取/保存
- 插件重载
- WebSocket 控制台（执行命令 + 转发日志）
- 登录认证（Cookie + 内存会话缓存）
- 静态资源与 API 路由保护

认证参数来自 ``config/app.yaml → webui``（见 ``FcatbotApp._build_webui_config``）。
未配置 ``password`` 时启动即随机生成 12 位密码，并由宿主在 ``start()`` **之前**
调用 ``report_access_password()`` 打印到本地可信控制台（不走 logging，
否则会被 ``_WebLogHandler`` 广播给 WebSocket 客户端）。

路由:
  GET  /                              主页（未登录 → 重定向 /login）
  GET  /login                         登录页
  POST /api/login                     登录（设置 Cookie）
  POST /api/logout                    退出登录（清除 Cookie）
  GET  /api/auth/status               查询当前登录状态
  GET  /static/*                      静态资源
  GET  /api/plugins                   插件列表
  POST /api/plugins/rescan            重扫描插件目录
  POST /api/plugins/{name}/toggle     切换启用状态
  GET  /api/plugins/{name}/config     读取 YAML
  PUT  /api/plugins/{name}/config     保存 YAML
  POST /api/plugins/{name}/reload     重载插件
  GET  /api/commands                  命令列表
  GET  /api/console                   WebSocket 控制台
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import logging
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from aiohttp import WSMsgType, web

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

log = logging.getLogger("fcatbot.webui")

STATIC_DIR = Path(__file__).parent / "static"

# 自动生成访问密码: 12 位，字符集剔除易混淆字符（O/o/l/I）
_GENERATED_PASSWORD_LENGTH = 12
_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ" "abcdefghijkmnpqrstuvwxyz" "0123456789"

# 插件名校验: 与插件类 ``name`` 的字符集一致，禁掉路径分隔符与 ".."。
# 用于 URL 路径参数拼进文件名前的前置校验，阻止路径穿越。
_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")

# 登录限速: 每 IP 在滑动窗口内最多失败多少次
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW_SECONDS = 60


# ==================== 依赖字段读取 ====================
#
# 统一规则: **``depends_on`` 是唯一权威字段**（PluginForge BasePlugin 原生）。
# ``dependencies`` 仅作历史兼容别名，读到即发一次性警告，下个大版本移除。
#
# 支持声明形态（与 PluginForge 一致）:
#     depends_on = ["foo", "bar"]                # list / tuple / set
#     depends_on = {"foo": ">=1.0", "bar": None} # dict: 键为依赖名
#     depends_on = None                          # 显式无依赖
#
# 已按插件名去重的警告集合（同一插件只警告一次，避免日志刷屏）。
_DEPRECATED_DEPS_WARNED: set[str] = set()


def _read_depends_on(obj: Any, *, plugin_name: str) -> list[str]:
    """从插件实例/类读取依赖名列表；统一到 PluginForge 的 ``depends_on``。

    优先取 ``depends_on``；为 ``None`` 时尝试读 ``dependencies``（弃用别名，
    发一次性警告）。显式空列表 ``[]`` **不会**被视为"未声明"，因此不会
    回退到别名 —— 这修掉了原 `or` 短路写法的误判。

    Returns:
        依赖名列表；未声明或非法形态时返回空列表。
    """
    raw = getattr(obj, "depends_on", None)

    if raw is None:
        legacy = getattr(obj, "dependencies", None)
        if legacy is not None:
            if plugin_name not in _DEPRECATED_DEPS_WARNED:
                _DEPRECATED_DEPS_WARNED.add(plugin_name)
                log.warning(
                    "插件 %r 使用已弃用的 ``dependencies`` 属性；"
                    "请改用 PluginForge 原生的 ``depends_on``（下个大版本将移除兼容）",
                    plugin_name,
                )
            raw = legacy

    if raw is None:
        return []
    if isinstance(raw, dict):
        return list(raw.keys())
    if isinstance(raw, (list, tuple, set)):
        return list(raw)
    return []


# ==================== 路由表 ====================
# 格式: (method, path, handler_method_name)
# - path 支持 aiohttp 原生 ``{name}`` 路径参数（会被传给 handler 的 match_info）。
# - handler_method_name 必须是 WebUI 实例上的方法名。
# - 新增 / 调整接口，只改这一个表。
_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("GET", "/", "_serve_index"),
    ("GET", "/login", "_serve_login"),
    ("POST", "/api/login", "_api_login"),
    ("POST", "/api/logout", "_api_logout"),
    ("GET", "/api/auth/status", "_api_auth_status"),
    ("GET", "/api/plugins", "_api_plugins"),
    ("POST", "/api/plugins/rescan", "_api_rescan"),
    ("POST", "/api/plugins/{name}/toggle", "_api_toggle"),
    ("GET", "/api/plugins/{name}/config", "_api_get_config"),
    ("PUT", "/api/plugins/{name}/config", "_api_put_config"),
    ("POST", "/api/plugins/{name}/reload", "_api_reload"),
    ("GET", "/api/commands", "_api_commands"),
    ("GET", "/api/console", "_ws_console"),
)


# ==================== 未登录放行路径 ====================
# 每条模式支持三种写法:
#   1) "re:..."         → 直接作为正则编译（"re:" 之后的部分）
#   2) 含 * / ** / {x}  → 通配符展开
#        *   单段内匹配（不含 /）
#        **  跨段匹配（含 /）
#        {x} 与 * 等价，仅作可读性占位
#   3) 其它             → 精确匹配
#
# 说明: 登录页外链 CSS 后，浏览器请求 /static/css/*.css 时尚未携带有效 Cookie，
# 若仍走鉴权，会被重定向回 /login?next=/static/... → 死循环。
# 因此登录页依赖的最小样式集必须放行。用通配符一条覆盖所有 CSS，
# 后续新增样式文件无需再改这里。
_PUBLIC_PATTERNS: tuple[str, ...] = (
    "/login",
    "/api/login",
    "/api/auth/status",
    # 登录页依赖的样式: static/css/*.css
    "/static/css/*.css",
    # 若以后需要放行登录页依赖的 JS，取消下面这行的注释即可:
    # "/static/js/login*.js",
    # 示例: 放行整目录
    # "/static/login/**",
    # 示例: 需要精细约束时用正则
    # r"re:^/static/(?:css|js)/login[-_.\w]*\.(?:css|js)$",
)


class WebUI:
    def __init__(
        self,
        app,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        log_handler: logging.Handler | None = None,
        access_log_level: int = logging.WARNING,
        # -------- 认证相关 --------
        auth_enabled: bool = True,
        password: str | None = None,
        secret_key: str | bytes | None = None,
        session_ttl: int = 7 * 24 * 3600,
        cookie_name: str = "fcatbot_session",
        cookie_secure: bool = False,
    ):
        self._app = app
        self._host = host
        self._port = port
        self._config_dir = app._config_path.parent / "plugins"
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._log_handler: logging.Handler | None = None
        self._log_handler_template = log_handler
        self._access_log_level = access_log_level

        # -------- 认证状态 --------
        # auth_enabled=False 时完全跳过认证: 不生成密码、不校验 Cookie。
        # 仅建议在本机/可信内网调试场景使用。
        self._auth_enabled = bool(auth_enabled)
        if self._auth_enabled:
            # fail-closed: 未配置密码 → 随机生成 12 位
            # 生成的密码只在启动前经 report_access_password() 打印到本地可信控制台，
            # 绝不写日志（日志会被 _WebLogHandler 广播给 WebSocket 客户端）。
            self._password_generated = not password
            self._password: str = password or self._generate_password()
        else:
            # 关闭认证时保留字段以避免属性访问崩溃，但不参与任何校验
            self._password_generated = False
            self._password = ""
        self._password_reported = False
        if isinstance(secret_key, str):
            secret_key = secret_key.encode("utf-8")
        self._secret_key: bytes = secret_key or secrets.token_bytes(32)
        self._session_ttl = max(60, int(session_ttl))
        self._cookie_name = cookie_name
        self._cookie_secure = bool(cookie_secure)
        # token -> 过期时间戳（惰性清理）
        self._sessions: dict[str, float] = {}

        # -------- 加载错误忽略集合 --------
        self._dismissed_errors: set[str] = set()

        # -------- 登录限速（per-remote） --------
        # remote_ip -> [失败时间戳, ...]，滑动窗口，惰性清理
        self._login_attempts: dict[str, list[float]] = {}

        # -------- 预编译公开路径匹配器 --------
        self._public_matchers: tuple[re.Pattern[str], ...] = tuple(
            self._compile_path_matcher(p) for p in _PUBLIC_PATTERNS
        )

    # ==================== 路径模式编译 ====================

    @staticmethod
    def _compile_path_matcher(pattern: str) -> re.Pattern[str]:
        """把路径模式编译为正则。

        - ``re:`` 前缀       → 直接按正则编译剩余部分
        - ``**``             → 跨段通配（含 ``/``）
        - ``*``              → 单段内通配（不含 ``/``）
        - ``{x}``            → 单段匹配，与 ``*`` 等价
        - 其它字符           → 原样转义（精确匹配）
        """
        if pattern.startswith("re:"):
            return re.compile(pattern[3:])

        parts: list[str] = []
        i, n = 0, len(pattern)
        while i < n:
            ch = pattern[i]
            if ch == "*":
                if i + 1 < n and pattern[i + 1] == "*":
                    parts.append(".*")
                    i += 2
                else:
                    parts.append("[^/]*")
                    i += 1
            elif ch == "{":
                end = pattern.find("}", i)
                if end == -1:
                    parts.append(re.escape(ch))
                    i += 1
                else:
                    parts.append("[^/]+")
                    i = end + 1
            else:
                parts.append(re.escape(ch))
                i += 1
        return re.compile("^" + "".join(parts) + "$")

    def _is_public_path(self, path: str) -> bool:
        """路径是否命中未登录放行集合。"""
        return any(m.match(path) for m in self._public_matchers)

    # ==================== 访问凭据 ====================

    @staticmethod
    def _generate_password(length: int = _GENERATED_PASSWORD_LENGTH) -> str:
        """生成 ``length`` 位随机访问密码（字符集已剔除易混淆字符）。"""
        return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))

    @property
    def auth_enabled(self) -> bool:
        """是否启用了登录认证。"""
        return self._auth_enabled

    @property
    def password_generated(self) -> bool:
        """访问密码是否为本次启动自动生成（而非来自配置文件）。"""
        return self._password_generated

    def report_access_password(self) -> str:
        """把**自动生成**的访问密码打印到本地可信控制台。

        必须满足两点，否则等同于把密码广播出去:
        1. **不经 logging**: ``_WebLogHandler`` 会把日志转发给所有 WebSocket
        客户端，密码一旦成为日志记录即泄露。此处直接写本地终端 stdout
        （``console_print``），不产生日志记录。
        2. **在 ``start()`` 之前调用**: ``start()`` 会安装 ``_WebLogHandler``
        并开始对外服务，密码不该在服务已可访问时才出现。

        手工配置的密码不打印（由运维自行保管）。幂等: 重复调用只打印一次。
        ``auth_enabled=False`` 时不做任何输出。

        返回实际打印的密码（未打印则为空串）。
        """
        if not self._auth_enabled:
            return ""
        if not self._password_generated or self._password_reported:
            return ""
        self._password_reported = True

        from fcatbot.frontend.console import console_print

        console_print(
            "\n"
            "┌─ WebUI 访问凭据\n"
            f"│  地址: http://{self._host}:{self._port}\n"
            f"│  密码: {self._password}\n"
            "└─ 如需固定密码，请在 config/app.yaml → webui.password 中配置\n"
        )
        return self._password

    # ==================== 插件名校验 ====================

    @staticmethod
    def _validate_plugin_name(name: str) -> str | None:
        """校验 URL 传入的插件名。

        返回错误消息；合法时返回 None。
        拒掉路径分隔符与 ".."，防止 ``name`` 拼进路径后穿越 ``plugins/`` 目录。
        """
        if not name or not _PLUGIN_NAME_RE.match(name):
            return "非法插件名"
        return None

    # ==================== 生命周期 ====================

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()

        # 静默 aiohttp 的 access 日志
        logging.getLogger("aiohttp.access").setLevel(self._access_log_level)

        @web.middleware
        async def auth_middleware(request: web.Request, handler):
            return await self._dispatch_with_auth(request, handler)

        web_app = web.Application(middlewares=[auth_middleware])

        # ---- 从声明表批量注册普通路由 ----
        for method, pattern, handler_name in _ROUTES:
            web_app.router.add_route(method, pattern, getattr(self, handler_name))

        # ---- 静态资源（static/css/*.css 等） ----
        web_app.router.add_static("/static", STATIC_DIR, name="static")

        self._runner = web.AppRunner(web_app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

        self._install_log_handler()
        log.info("WebUI 运行在 http://%s:%d", self._host, self._port)
        if self._auth_enabled:
            log.info(
                "WebUI 已启用登录认证（Cookie: %s，有效期 %d 秒）",
                self._cookie_name,
                self._session_ttl,
            )
            if self._password_generated:
                log.info("访问密码为本次启动自动生成，已打印到本地控制台")
        else:
            log.warning(
                "WebUI 未启用登录认证（auth_enabled=False），"
                "请确保仅监听可信网络（当前 %s:%d）",
                self._host,
                self._port,
            )

    async def stop(self) -> None:
        self._remove_log_handler()
        for ws in list(self._ws_clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_clients.clear()
        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    # ==================== 认证 ====================

    def _make_session_token(self) -> str:
        """生成无状态签名 token: ``nonce.ts.sig``。"""
        nonce = secrets.token_urlsafe(24)
        ts = str(int(time.time()))
        payload = f"{nonce}.{ts}"
        sig = hmac.new(
            self._secret_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:32]
        return f"{payload}.{sig}"

    def _verify_session_token(self, token: str) -> bool:
        """校验 token: 先查缓存，未命中再验签名（可跨进程重启）。"""
        if not token:
            return False
        now = time.time()

        # 1) 内存缓存命中
        exp = self._sessions.get(token)
        if exp is not None:
            if exp > now:
                return True
            self._sessions.pop(token, None)
            return False

        # 2) 验签
        try:
            nonce, ts_str, sig = token.rsplit(".", 2)
        except ValueError:
            return False
        payload = f"{nonce}.{ts_str}"
        expected = hmac.new(
            self._secret_key, payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return False
        try:
            issued = int(ts_str)
        except ValueError:
            return False
        if now - issued > self._session_ttl:
            return False

        # 加入缓存，后续快速命中
        self._sessions[token] = issued + self._session_ttl
        self._gc_sessions()
        return True

    def _gc_sessions(self) -> None:
        now = time.time()
        dead = [k for k, exp in self._sessions.items() if exp <= now]
        for k in dead:
            self._sessions.pop(k, None)

    def _check_password(self, password: str) -> bool:
        try:
            return hmac.compare_digest(password, self._password)
        except Exception:
            return False

    def _is_authed(self, request: web.Request) -> bool:
        token = request.cookies.get(self._cookie_name)
        return self._verify_session_token(token) if token else False

    # ---------- 登录限速 ----------

    def _login_rate_ok(self, remote: str) -> bool:
        now = time.time()
        attempts = self._login_attempts.setdefault(remote or "unknown", [])
        attempts[:] = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
        return len(attempts) < _LOGIN_MAX_ATTEMPTS

    def _login_record_failure(self, remote: str) -> None:
        self._login_attempts.setdefault(remote or "unknown", []).append(time.time())

    async def _dispatch_with_auth(self, request: web.Request, handler):
        # 关闭认证 → 直接放行所有请求（含 / 与 /api/*）
        if not self._auth_enabled:
            return await handler(request)

        path = request.path

        # 公开路径：登录页、登录接口、auth 状态查询、登录页依赖的静态资源……
        if self._is_public_path(path):
            # 已登录再访问 /login → 直接回首页
            if path == "/login" and self._is_authed(request):
                raise web.HTTPFound("/")
            return await handler(request)

        # 其余全部需要登录
        if self._is_authed(request):
            return await handler(request)

        if path.startswith("/api/"):
            return web.json_response(
                {"ok": False, "message": "未登录或登录已过期", "need_login": True},
                status=401,
            )
        raise web.HTTPFound(f"/login?next={path}")

    # ---------- 认证相关路由 ----------

    async def _serve_login(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "login.html")

    async def _api_login(self, request: web.Request) -> web.Response:
        if not self._auth_enabled:
            return web.json_response({"ok": True, "message": "认证已关闭"})

        remote = request.remote or "unknown"
        if not self._login_rate_ok(remote):
            log.warning("WebUI 登录限速触发（来源 %s）", remote)
            return web.json_response(
                {"ok": False, "message": "尝试过于频繁，请稍后再试"}, status=429
            )

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "message": "无效请求"}, status=400)
        password = str(body.get("password", ""))

        if not self._check_password(password):
            self._login_record_failure(remote)
            # 固定延迟，缓解暴力破解
            await asyncio.sleep(0.25)
            log.warning("WebUI 登录失败（来源 %s）", remote)
            return web.json_response({"ok": False, "message": "密码错误"}, status=401)

        # 成功 → 清掉该 IP 的失败记录，避免正常用户被自己之前的失败拖累
        self._login_attempts.pop(remote, None)

        token = self._make_session_token()
        self._sessions[token] = time.time() + self._session_ttl
        self._gc_sessions()

        resp = web.json_response({"ok": True, "message": "登录成功"})
        resp.set_cookie(
            self._cookie_name,
            token,
            max_age=self._session_ttl,
            httponly=True,
            samesite="Lax",
            secure=self._cookie_secure,
            path="/",
        )
        log.info("WebUI 登录成功（来源 %s）", remote)
        return resp

    async def _api_logout(self, request: web.Request) -> web.Response:
        token = request.cookies.get(self._cookie_name)
        if token:
            self._sessions.pop(token, None)
        resp = web.json_response({"ok": True, "message": "已退出登录"})
        resp.del_cookie(self._cookie_name, path="/")
        return resp

    async def _api_auth_status(self, request: web.Request) -> web.Response:
        authed = self._is_authed(request) if self._auth_enabled else True
        return web.json_response(
            {
                "ok": True,
                "authenticated": authed,
                "auth_required": self._auth_enabled,
            }
        )

    # ==================== 静态 ====================

    async def _serve_index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    # ==================== 插件状态 ====================

    def _current_load_errors(self) -> dict[str, str]:
        """当前仍应展示的加载错误。

        过滤规则:
          1. 已经在 active 中的插件 → 视为加载成功，移除其历史错误；
          2. 本次会话中被明确处理过的插件（成功启用 / 正常停用）→ 移除残留错误。
        """
        try:
            errors = dict(self._app._pm.get_load_errors())
        except Exception:
            log.exception("读取 load_errors 失败")
            return {}

        # 正在运行 → 一定没有加载错误
        for p in self._app._pm.get_active_plugins():
            errors.pop(p.name, None)

        # 本次会话已明确处理过的插件 → 不再展示旧错误
        if self._dismissed_errors:
            for name in self._dismissed_errors:
                errors.pop(name, None)

        return errors

    def _get_plugin_dependencies(self, name: str) -> list[str]:
        """获取插件声明的依赖名列表（可能为空）。

        唯一权威字段是 PluginForge 的 ``depends_on``。历史别名
        ``dependencies`` 仍可读，但会触发一次性弃用警告（见模块级
        :func:`_read_depends_on`）。

        优先读活跃实例（实例属性可能被运行时覆盖），再退回已发现的类。
        """
        pm = self._app._pm

        for p in pm.get_active_plugins():
            if p.name == name:
                return _read_depends_on(p, plugin_name=name)

        cls = self._app.discovered_plugins.get(name)
        if cls is None:
            return []
        return _read_depends_on(cls, plugin_name=name)

    def _unmet_dependencies(self, name: str) -> list[str]:
        """返回尚未启用/激活的依赖名。"""
        deps = self._get_plugin_dependencies(name)
        if not deps:
            return []
        enabled = set(self._read_enabled_list())
        active = {p.name for p in self._app._pm.get_active_plugins()}
        return [d for d in deps if d not in enabled and d not in active]

    # ==================== 插件 API ====================

    async def _api_plugins(self, request: web.Request) -> web.Response:
        pm = self._app._pm
        active = {p.name: p for p in pm.get_active_plugins()}
        enabled = set(self._read_enabled_list())

        discovered: dict[str, type] = self._app.discovered_plugins
        all_names = set(active) | set(discovered) | enabled
        errors = self._current_load_errors()

        plugins_data = []
        for name in sorted(all_names):
            plugin = active.get(name)
            cls = discovered.get(name)
            meta = plugin if plugin is not None else cls

            deps = self._get_plugin_dependencies(name)
            missing = [d for d in deps if d not in enabled and d not in active]

            plugins_data.append(
                {
                    "name": name,
                    "version": getattr(meta, "version", "-") if meta else "-",
                    "description": getattr(meta, "description", "") if meta else "",
                    "activated": name in active,  # 运行中实例
                    "enabled": name in enabled,  # app.yaml 白名单
                    "has_config": (self._config_dir / f"{name}.yaml").exists(),
                    "error": errors.get(name, ""),
                    "dependencies": deps,
                    "missing_dependencies": missing,
                }
            )

        return web.json_response({"plugins": plugins_data})

    # ---------- 重扫描宿主接口的探测 ----------
    def _resolve_rescan_callable(self):
        """只查宿主 FcatbotApp 上的重扫描方法。

        刻意不 fallback 到 PluginManager：
          - discover_plugins() / rediscover() 会连带激活插件，
            不符合「先发现、用户再决定」的语义
          - 且 PluginManager 不允许改动，不依赖其内部实现
        找不到 → 返回 None → 接口 501，不做任何猜测。
        """
        for attr in ("rescan_plugins", "scan_plugins"):
            fn = getattr(self._app, attr, None)
            if callable(fn):
                return fn
        return None

    async def _api_rescan(self, request: web.Request) -> web.Response:
        """重新扫描插件目录，动态加载新增/移除插件。

        - 只重扫「已发现插件」列表，不做任何 enable/disable 副作用；
          实际启用仍走 /toggle。
        - 前后做 diff，把新增/移除结果返回给前端。
        - 扫描成功后会清掉已消失插件的忽略标记，避免残留脏状态。
        """
        rescan = self._resolve_rescan_callable()
        if rescan is None:
            return web.json_response(
                {
                    "ok": False,
                    "message": (
                        "宿主未提供插件扫描接口。"
                        "请在 FcatbotApp / PluginManager 上暴露 "
                        "rescan_plugins() / scan_plugins() / discover_plugins() 之一。"
                    ),
                },
                status=501,
            )

        # 记录扫描前的插件集合（读一次快照，避免边扫边变）
        before = set(self._app.discovered_plugins.keys())

        try:
            result = rescan()
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            log.exception("重扫描插件失败")
            return web.json_response(
                {"ok": False, "message": f"重扫描失败: {exc}"},
                status=500,
            )

        # 重新读取（扫描可能替换了字典对象）
        after = set(self._app.discovered_plugins.keys())
        added = sorted(after - before)
        removed = sorted(before - after)

        # 消失的插件：清掉它的忽略标记 & 历史错误缓存
        for name in removed:
            self._dismissed_errors.discard(name)

        if added and removed:
            msg = f"重扫描完成：新增 {len(added)} 个（{', '.join(added)}），移除 {len(removed)} 个（{', '.join(removed)}）"
        elif added:
            msg = f"重扫描完成：新增 {len(added)} 个（{', '.join(added)}）"
        elif removed:
            msg = f"重扫描完成：移除 {len(removed)} 个（{', '.join(removed)}）"
        else:
            msg = "重扫描完成：未发现变化"

        log.info("WebUI 重扫描插件 -> %s", msg)
        return web.json_response(
            {
                "ok": True,
                "message": msg,
                "added": added,
                "removed": removed,
                "total": len(after),
            }
        )

    async def _api_toggle(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if (err := self._validate_plugin_name(name)) is not None:
            return web.json_response({"ok": False, "message": err}, status=400)

        body = await request.json()
        enabled = bool(body.get("enabled"))
        force = bool(body.get("force", False))

        # 启用前先做依赖检查（force=True 时跳过）
        if enabled and not force:
            missing = self._unmet_dependencies(name)
            if missing:
                return web.json_response(
                    {
                        "ok": False,
                        "message": (
                            f"依赖未满足，无法启用 {name}: "
                            f"请先启用 {', '.join(missing)}"
                        ),
                        "missing": missing,
                    }
                )

        # 1. 运行时装卸: 走宿主生命周期
        if enabled:
            ok, msg = await self._app.enable_plugin(name)
        else:
            ok, msg = await self._app.disable_plugin(name)

        if not ok:
            # 启用/停用失败: 让插件重新暴露（若有）加载错误
            self._dismissed_errors.discard(name)
            return web.json_response({"ok": False, "message": msg})

        # 2. 操作成功 → 更新错误忽略集合
        #    - 成功启用: 插件已在 active 中，错误会被过滤，同时清掉忽略标记
        #    - 正常停用: 写入忽略集合，让历史加载错误不再展示
        if enabled:
            self._dismissed_errors.discard(name)
        else:
            self._dismissed_errors.add(name)

        # 3. 写入 config/app.yaml（下次启动的权威配置）
        try:
            changed = self._set_enabled(name, enabled)
        except Exception as exc:
            log.exception("写入 app 配置失败")
            return web.json_response(
                {"ok": False, "message": f"{msg}，但写入配置失败: {exc}"}
            )
        if changed:
            msg = f"{msg}（已写入 config/app.yaml，重启后保持）"

        return web.json_response({"ok": True, "message": msg})

    async def _api_reload(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if (err := self._validate_plugin_name(name)) is not None:
            return web.json_response({"ok": False, "message": err}, status=400)

        ok, msg = await self._app.reload_plugin(name)

        # 重载无论成败，都应清除“忽略”标记:
        #   - 成功 → 插件进入 active，错误自动隐藏
        #   - 失败 → 若确有加载错误，应重新展示
        self._dismissed_errors.discard(name)

        return web.json_response({"ok": ok, "message": msg})

    # ==================== 配置 API ====================

    async def _api_get_config(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if (err := self._validate_plugin_name(name)) is not None:
            return web.json_response({"ok": False, "message": err}, status=400)

        path = self._config_dir / f"{name}.yaml"

        # 只读: 不存在就返回空串，不在磁盘上制造文件
        content = path.read_text(encoding="utf-8") if path.exists() else ""

        return web.json_response(
            {
                "name": name,
                "path": str(path),
                "content": content,
                "exists": path.exists(),
            }
        )

    async def _api_put_config(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if (err := self._validate_plugin_name(name)) is not None:
            return web.json_response({"ok": False, "message": err}, status=400)

        body = await request.json()
        content = body.get("content", "")

        path = self._config_dir / f"{name}.yaml"

        # 空内容 + 文件本来就不存在 → 什么都不做
        if not content.strip() and not path.exists():
            return web.json_response({"ok": True, "message": "无内容，未创建文件"})

        # 校验 YAML 语法
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            return web.json_response(
                {"ok": False, "message": f"YAML 语法错误: {e}"}, status=400
            )

        # 与磁盘现有内容一致 → 跳过写入
        if path.exists():
            try:
                if path.read_text(encoding="utf-8") == content:
                    return web.json_response({"ok": True, "message": "无修改"})
            except OSError:
                log.exception("读取现有配置失败，继续执行写入")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        # 尝试刷新配置
        refresh = getattr(self._app._pm, "refresh_config", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                log.exception("refresh_config failed")

        return web.json_response({"ok": True, "message": "已保存"})

    # ==================== 命令 API ====================

    async def _api_commands(self, request: web.Request) -> web.Response:
        specs = self._app._commands.all_roots()
        return web.json_response(
            {
                "commands": [
                    {
                        "name": s.name,
                        "usage": s.usage_text(),
                        "help": s.help,
                        "plugin": s.plugin,
                        "permission": s.resolved_permission(),
                    }
                    for s in specs
                ]
            }
        )

    # ==================== WebSocket 控制台 ====================

    async def _ws_console(self, request: web.Request) -> web.WebSocketResponse:
        # heartbeat 让 aiohttp 自己定期 ping，客户端死连接能更早被识别
        ws = web.WebSocketResponse(heartbeat=30.0, autoping=True)
        await ws.prepare(request)
        self._ws_clients.add(ws)

        try:
            await ws.send_json(
                {
                    "type": "info",
                    "text": "控制台已连接。输入 help 查看命令。",
                }
            )
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                    except Exception:
                        continue
                    if data.get("type") == "command":
                        await self._exec_command(ws, data.get("text", ""))
                elif msg.type == WSMsgType.ERROR:
                    break
        except (ConnectionResetError, asyncio.CancelledError):
            # 客户端强制断连 / 服务停止 → 静默退出
            pass
        finally:
            self._ws_clients.discard(ws)
            # 主动 close 时也要吞掉 10054
            if not ws.closed:
                try:
                    await ws.close()
                except (ConnectionResetError, OSError):
                    pass
        return ws

    async def _exec_command(self, ws: web.WebSocketResponse, text: str) -> None:
        text = text.strip()
        if not text:
            return
        try:
            await ws.send_json({"type": "prompt", "text": f"> {text}"})
            log.info("WebConsole: %s", text)
            tokens = text.split()
            spec, args = self._app._commands.find(tokens)
            if spec is None:
                log.info("WebConsole: unknown command: %s", text)
                await ws.send_json({"type": "error", "text": f"未知命令: {text}"})
                return
            if spec.handler is None:
                log.info("WebConsole: command needs subcommand: %s", text)
                await ws.send_json({"type": "info", "text": "(该命令需要子命令)"})
                return
            result = spec.handler(args)
            if inspect.isawaitable(result):
                result = await result
            if result:
                await ws.send_json({"type": "output", "text": str(result)})
        except Exception as exc:
            log.exception("Command execution failed: %s", str(exc))
            await ws.send_json({"type": "error", "text": str(exc)})

    # ==================== 日志流 ====================

    def _install_log_handler(self) -> None:
        root = logging.getLogger()
        handler = _WebLogHandler(self)

        tmpl = self._log_handler_template
        if tmpl is None:
            for h in root.handlers:
                if (
                    isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)
                    and h.formatter is not None
                ):
                    tmpl = h
                    break

        if tmpl is not None:
            handler.setFormatter(tmpl.formatter)
            for f in tmpl.filters:
                handler.addFilter(f)
        else:
            handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] %(levelname)-8s %(name)s ➜ %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
        handler.setLevel(root.level or logging.INFO)
        root.addHandler(handler)
        self._log_handler = handler

    def _remove_log_handler(self) -> None:
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            self._log_handler = None

    def _schedule_broadcast(self, text: str) -> None:
        loop = self._loop
        if (
            not self._ws_clients
            or loop is None
            or loop.is_closed()
            or not loop.is_running()
        ):
            return
        try:
            loop.call_soon_threadsafe(self._do_broadcast, text)
        except RuntimeError:
            pass

    def _do_broadcast(self, text: str) -> None:
        for ws in list(self._ws_clients):
            if ws.closed:
                continue
            asyncio.create_task(self._safe_send(ws, text))

    @staticmethod
    async def _safe_send(ws: web.WebSocketResponse, text: str) -> None:
        if ws.closed:
            return
        try:
            await ws.send_json({"type": "log", "text": text})
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        except Exception:
            # 其他异常仍然记 debug，方便排查
            log.debug("WebSocket 发送失败", exc_info=True)

    # ==================== config/app.yaml 读写 ====================

    def _read_app_config(self) -> dict:
        path = self._app._config_path
        if not path.exists():
            return {}
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            log.exception("Failed to read app config")
            return {}

    def _write_app_config(self, data: dict) -> None:
        path = self._app._config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    def _read_raw_plugins_config(self) -> dict:
        """返回 app.yaml 中的 ``plugins`` 段（不展开 None 语义）。"""
        data = self._read_app_config()
        return data.get("plugins") or {}

    def _read_enabled_list(self) -> list[str]:
        """当前「显式启用」的插件名集合。

        ``plugins.enabled`` 缺省（None）时返回**全部已知插件**——这是为了
        让 UI 上每个插件都能正确渲染 ``enabled=True``。真正写入时使用
        :meth:`_set_enabled` 的原始语义（区分 None 与 []）。
        """
        plugins = self._read_raw_plugins_config()
        raw = plugins.get("enabled")
        if raw is None:
            # 缺省语义: enabled 为 None → 全部通过
            return self._known_plugin_names()
        return list(raw)

    def _read_disabled_list(self) -> list[str]:
        plugins = self._read_raw_plugins_config()
        return list(plugins.get("disabled") or [])

    def _known_plugin_names(self) -> list[str]:
        """当前已知的插件名（活跃 + 发现）。"""
        names = {p.name for p in self._app._pm.get_active_plugins()}
        names |= set(self._app.discovered_plugins)
        return sorted(names)

    def _set_enabled(self, name: str, enabled: bool) -> bool:
        """写入 ``plugins.enabled`` / ``plugins.disabled``；返回是否真正发生变更。

        语义保留 ``enabled=None``（全启用）:
        - 若 ``enabled`` 为 None，禁用走 ``disabled`` 黑名单；
        - 若 ``enabled`` 是列表，禁用/启用维护该列表。
        这样既保持与 PluginForge 一致的缺省语义，也不会在首次切换时把
        所有已知插件意外写进白名单。
        """
        data = self._read_app_config()
        plugins = data.setdefault("plugins", {})
        raw_enabled = plugins.get("enabled")
        raw_disabled = list(plugins.get("disabled") or [])

        changed = False
        if enabled:
            # 启用: 从 disabled 黑名单移除；若 enabled 是白名单则加入
            if name in raw_disabled:
                raw_disabled.remove(name)
                changed = True
            if raw_enabled is not None and name not in raw_enabled:
                plugins["enabled"] = list(raw_enabled) + [name]
                changed = True
        else:
            # 停用: enabled 是 None（全启用）→ 走黑名单；否则从白名单移除
            if raw_enabled is None:
                if name not in raw_disabled:
                    raw_disabled.append(name)
                    changed = True
            else:
                if name in raw_enabled:
                    plugins["enabled"] = [n for n in raw_enabled if n != name]
                    changed = True

        if raw_disabled:
            plugins["disabled"] = raw_disabled
        elif "disabled" in plugins:
            # 空的黑名单不落盘
            del plugins["disabled"]

        if changed:
            self._write_app_config(data)
        return changed


class _WebLogHandler(logging.Handler):
    """把日志推送到所有 WebSocket 客户端。"""

    def __init__(self, ui: WebUI):
        super().__init__()
        self._ui = ui

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            return
        self._ui._schedule_broadcast(msg)
