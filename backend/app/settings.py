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
    model_name: str = os.getenv("MODEL_NAME", "isnet-general-use")
    # Zeabur 注入的监听端口。
    port: int = int(os.getenv("PORT", "8000"))
    # ---- 观测站（中证1000 Kronos 每日预测）----
    # 输出目录：账本/图表落在这里。生产环境应把持久卷挂到 /data，否则重启丢账本。
    observatory_dir: str = os.getenv("OBSERVATORY_DIR", "/data/observatory")
    # vendored Kronos 模型代码位置（Docker 镜像内路径）。
    kronos_dir: str = os.getenv("KRONOS_DIR", "/app/vendor/kronos")
    # 预测脚本位置（与 csi1000-kronos-forecast Skill 同源）。
    observatory_script: str = os.getenv(
        "OBSERVATORY_SCRIPT", "/app/observatory/csi1000_live_forecast.py"
    )
    # 每日运行时刻（Asia/Shanghai，开盘前）。前一交易日日线早已收盘定格，
    # 08:00 留足缓冲（早于 9:15 集合竞价），当天开盘前就能看到最新观测。
    # 设 OBSERVATORY_ENABLED=0 可整体停用。
    observatory_schedule: str = os.getenv("OBSERVATORY_SCHEDULE", "08:00")
    observatory_enabled: bool = os.getenv("OBSERVATORY_ENABLED", "1") == "1"


settings = Settings()
