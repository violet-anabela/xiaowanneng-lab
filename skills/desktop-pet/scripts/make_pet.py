#!/usr/bin/env python3
"""把一张透明背景 PNG 做成独立单文件桌宠（my-pet.html）。仅用 Python 标准库。

用法：
    python scripts/make_pet.py cutout.png --name 球球 --size 96 -o my-pet.html

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


def main() -> int:
    parser = argparse.ArgumentParser(description="生成单文件桌宠 HTML")
    parser.add_argument("image", help="透明背景图片（PNG/WebP）")
    parser.add_argument("--name", default="小伙伴", help="宠物名字（默认：小伙伴）")
    parser.add_argument("--size", type=int, default=96, help="显示大小 px，48-200（默认 96）")
    parser.add_argument("-o", "--output", default="my-pet.html", help="输出文件（默认 my-pet.html）")
    args = parser.parse_args()

    image_path = pathlib.Path(args.image)
    if not image_path.is_file():
        print(f"找不到图片：{image_path}", file=sys.stderr)
        return 1

    mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
    data_url = f"data:{mime};base64," + base64.b64encode(image_path.read_bytes()).decode()

    engine = (TEMPLATES / "xwn-pet.js").read_text(encoding="utf-8")
    template = (TEMPLATES / "pet.html").read_text(encoding="utf-8")

    config = json.dumps(
        {"image": data_url, "name": args.name, "size": max(48, min(200, args.size))},
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
