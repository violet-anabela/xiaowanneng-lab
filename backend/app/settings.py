"""运行配置：全部来自环境变量（Zeabur 注入），不入库秘密。"""

import os


def _csv_list(value: str | None, default):
    if not value:
        return default
    return [x.strip() for x in value.split(",") if x.strip()]


class Settings:
    # 两层大小限制（方案 §5.5 / §8）：
    # 请求总上限（multipart 解析前，ASGI 中间件）略大于文件上限，容纳边界与头部。
    max_request_bytes: int = int(os.getenv("MAX_REQUEST_BYTES", str(11 * 1024 * 1024)))  # 11 MiB
    max_file_bytes: int = int(os.getenv("MAX_FILE_BYTES", str(10 * 1024 * 1024)))        # 10 MiB
    # 解码后像素总数上限（防压缩炸弹），约 8000x5000。
    max_pixels: int = int(os.getenv("MAX_PIXELS", str(40_000_000)))
    # 并发上限分别设置（方案 §7/§8）：
    max_upload_concurrency: int = int(os.getenv("MAX_UPLOAD_CONCURRENCY", "4"))
    max_inference_concurrency: int = int(os.getenv("MAX_INFERENCE_CONCURRENCY", "2"))
    # CORS 白名单（仅正式站点域名 + 必要本地开发地址，不用 *）。
    allowed_origins: list[str] = _csv_list(os.getenv("ALLOWED_ORIGINS", ""), [])
    # rembg 模型名（v1 默认 u2net，实测后再定）。
    model_name: str = os.getenv("MODEL_NAME", "u2net")
    # Zeabur 注入的监听端口。
    port: int = int(os.getenv("PORT", "8000"))


settings = Settings()
