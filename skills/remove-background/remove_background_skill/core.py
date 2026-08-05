"""抠图核心（唯一真源）。

网站后端（backend/app）与 Skill CLI（scripts/remove_bg.py）都 import 本包；
下载 zip 也包含这份源码。改一处处处生效。

设计约束（方案 D3/D4）：
- 不碰文件、不打印、不依赖任何绝对路径或特定 Agent 的专属假设；
- 显式接收复用 session，不在模块 import 时隐式加载模型权重
  （否则 --help、测试导入、构建检查都会触发模型初始化）。
"""

from PIL import Image


def remove_background(image: Image.Image, *, session) -> Image.Image:
    """接收 PIL 图与复用的 rembg session，返回去背景（透明通道）的 PIL 图。

    Args:
        image: 已解码的 PIL 图片（建议 RGB/RGBA）。
        session: 由调用方创建并复用的 rembg session（``rembg.new_session``）。
    """
    from rembg import remove

    return remove(image, session=session)
