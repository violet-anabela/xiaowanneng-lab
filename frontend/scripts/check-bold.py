"""查中文粗体的收尾标点问题：**xxx。**yyy 这种解析器认不出，会在页面上留下字面 **。

用法： .venv/bin/python frontend/scripts/check-bold.py
"""

import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "src" / "content"
# 粗体收尾前是中文标点，且收尾后紧跟非空白：**内容。**后面
PAT = re.compile(r"\*\*(?=\S)[^*\n]*?[。，、；：！？]\*\*(?=\S)")

bad = []
for f in sorted(DOCS.rglob("*.md")):
    for n, line in enumerate(f.read_text().splitlines(), 1):
        for m in PAT.finditer(line):
            bad.append(f"{f.relative_to(DOCS)}:{n}  {m.group()}")

if bad:
    print("这些粗体在页面上会漏出字面 **，把标点移到粗体外面：\n")
    print("\n".join(bad))
    sys.exit(1)
print("粗体写法检查通过")
