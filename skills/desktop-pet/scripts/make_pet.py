#!/usr/bin/env python3
"""把一张透明背景 PNG 做成独立单文件桌宠（my-pet.html）。仅用 Python 标准库。

用法：
    python scripts/make_pet.py cutout.png --name 球球 --size 96 -o my-pet.html
    # 可选状态图（都要透明背景）：
    python scripts/make_pet.py idle.png --eat eat.png --sleep sleep.png \
        --drag drag.png --click click.png --name 球球 -o my-pet.html

输入应当是已经去除背景的 PNG（透明通道）。抠图可以用 remove-background Skill，
或小完能实验室的在线工具（https://violet.hk.cn/tools/remove-background）。
产物是一个自包含 HTML：图片以 base64 内嵌，双击浏览器打开即可。
"""

import argparse
import base64
import json
import mimetypes
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"


def to_data_url(path_str: str) -> str:
    path = pathlib.Path(path_str)
    if not path.is_file():
        print(f"找不到图片：{path}", file=sys.stderr)
        raise SystemExit(1)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成单文件桌宠 HTML")
    parser.add_argument("image", help="站立/溜达状态的透明背景图片（PNG/WebP，必填）")
    parser.add_argument("--eat", help="吃饭状态图片（可选）")
    parser.add_argument("--sleep", help="睡觉状态图片（可选）")
    parser.add_argument("--drag", help="被拎起来状态图片（可选）")
    parser.add_argument("--click", help="被点击状态图片（可选）")
    parser.add_argument("--name", default="小伙伴", help="宠物名字（默认：小伙伴）")
    parser.add_argument("--size", type=int, default=96, help="显示大小 px，48-200（默认 96）")
    parser.add_argument("-o", "--output", default="my-pet.html", help="输出文件（默认 my-pet.html）")
    args = parser.parse_args()

    images = {"idle": to_data_url(args.image)}
    for key in ("eat", "sleep", "drag", "click"):
        value = getattr(args, key)
        if value:
            images[key] = to_data_url(value)

    engine = (TEMPLATES / "xwn-pet.js").read_text(encoding="utf-8")
    template = (TEMPLATES / "pet.html").read_text(encoding="utf-8")

    config = json.dumps(
        {"images": images, "name": args.name, "size": max(48, min(200, args.size))},
        ensure_ascii=False,
    )

    html = (
        template
        .replace("/*__ENGINE__*/", engine)
        .replace("__PET_CONFIG__", config)
        .replace("__PET_NAME__", args.name)
    )

    out = pathlib.Path(args.output)
    out.write_text(html, encoding="utf-8")
    print(f"桌宠已生成：{out}（{out.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
