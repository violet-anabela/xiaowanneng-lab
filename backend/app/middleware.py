"""ASGI 中间件：在 multipart 解析前按原始请求体累计字节，实施请求级硬上限。

为什么需要（方案 §5.5 / §8）：Starlette 在把 UploadFile 交给路由前通常已完成
multipart 解析，因此路由内分块读取不能替代解析前的请求级限制，也无法保证
“超过 10MB 时立即断开客户端”。本中间件在 ASGI receive 层边收边卡，超限即切断。

上层还有 Zeabur 代理层的请求体上限作为双重保险；Content-Length 可能缺失或伪造，
因此本限制以“实际累计字节”为准，不依赖声明值。
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODY_TOO_LARGE = b"Request body too large"


async def _send_413(send: Send) -> None:
    try:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _BODY_TOO_LARGE})
    except Exception:  # 客户端可能已断开，忽略
        pass


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        received = 0
        exceeded = False

        async def wrapped_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    exceeded = True
                    # 停止转发更多 body，通知下游断开
                    return {"type": "http.disconnect"}
            return message

        async def wrapped_send(message: Message) -> None:
            # 超限后吞掉内层（Starlette multipart 等）可能自发的错误响应，
            # 改由本中间件统一回 413。
            if exceeded:
                return
            await send(message)

        await self.app(scope, wrapped_receive, wrapped_send)

        # 超限时由本中间件权威地回 413（内层响应已被吞掉）。
        if exceeded:
            await _send_413(send)
