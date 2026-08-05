"""抠图适配层（方案 D4：网站后端 = 纯适配层）。

职责：上传接收、文件级大小硬限、真实格式/像素校验、调用核心、构造响应。
绝不把并发/网络协议逻辑塞进 Skill 核心。
"""

import asyncio
import io

from fastapi import HTTPException, Response, UploadFile

from ..schemas import SUPPORTED_FORMATS
from ..settings import settings
from remove_background_skill import remove_background


async def process_upload(file: UploadFile, session) -> Response:
    # 1) 文件级大小硬限：分块读取 UploadFile 并累计字节。
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_file_bytes:
            raise HTTPException(status_code=413, detail="Image too large")
        chunks.append(chunk)
    data = b"".join(chunks)

    # 2) 解码并校验真实格式 / 像素（不信任扩展名或 Content-Type）。
    try:
        img = io.BytesIO(data)
        pil = __import__("PIL").Image.open(img)
        fmt = pil.format
        if fmt not in SUPPORTED_FORMATS:
            raise HTTPException(status_code=415, detail=f"Unsupported image format: {fmt}")
        width, height = pil.size
        if width * height > settings.max_pixels:
            raise HTTPException(status_code=413, detail="Image dimensions too large")
        pil.verify()  # 确认非损坏
        # verify 后对象失效，需重新打开并转 RGB 供 rembg 使用。
        rgb = __import__("PIL").Image.open(io.BytesIO(data)).convert("RGB")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=422, detail="Cannot decode image")
    finally:
        try:
            await file.close()
        except Exception:
            pass

    # 3) 推理（阻塞型 ONNX 计算，交线程池；semaphore 在路由层已获取）。
    #    注意：HTTP 任务取消不保证终止后台 ONNX 计算（方案 §7）。
    result = await asyncio.to_thread(remove_background, rgb, session=session)

    # 4) 构造响应：透明 PNG，不缓存（方案 §8.16）。
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    png = buf.getvalue()
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": 'attachment; filename="remove-background.png"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
