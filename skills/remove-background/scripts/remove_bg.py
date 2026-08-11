"""抠图 CLI 外壳。

基于自身文件位置把 Skill 根目录加入 sys.path，让下载者解压后直接可跑，
无需把 Skill 安装成包、也不写死任何用户机器绝对路径（方案 §5.3）。

核心逻辑全部委托给 remove_background_skill.remove_background，与网站后端同源。
"""

import argparse
import pathlib
import sys

SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from PIL import Image  # noqa: E402
from rembg import new_session  # noqa: E402
from remove_background_skill import remove_background  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="图片去背景，输出透明 PNG")
    parser.add_argument("input", help="输入图片路径")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出 PNG 路径（默认 <input 去后缀>-no-bg.png）",
    )
    parser.add_argument("--model", default="isnet-general-use", help="rembg 模型名（默认 isnet-general-use，抠白色/毛茸茸主体明显更干净）")
    args = parser.parse_args()

    out = args.output or (str(pathlib.Path(args.input).with_suffix("")) + "-no-bg.png")

    session = new_session(args.model)
    with Image.open(args.input) as img:
        src = img.convert("RGB")
        result = remove_background(src, session=session)
    result.save(out)
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
