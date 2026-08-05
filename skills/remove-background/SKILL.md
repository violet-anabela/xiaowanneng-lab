---
name: remove-background
version: 1.0.0
description: 去除图片背景，返回带透明通道的 PNG。调用本地 rembg 推理，图片不出本机。
---

# 图片去背景（remove-background）

当用户要求「去背景 / 抠图 / 去掉图片背景 / 生成透明背景图」时启用本技能。

## 环境要求
- Python 3.10+
- 首次运行会下载 rembg 模型权重（约 176MB），存放于 `U2NET_HOME`（默认 `~/.u2net`）。
  模型权重**不**随本 Skill 分发（许可证与体积原因），由 rembg 首次使用时自动下载。

## 安装依赖
优先在 Agent 的隔离 Python 环境安装；人工使用建议先建虚拟环境，避免污染全局：

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 使用方式
解压技能包后，直接以脚本方式运行（无需安装成包，也不写死绝对路径）：

```bash
python scripts/remove_bg.py input.jpg -o output.png
# 不指定 -o 时默认输出 input-no-bg.png
```

也可在 Python 中复用核心函数（与网站后端**同一份源码**）：

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("scripts/remove_bg.py").resolve().parents[1]))
from remove_background_skill import remove_background
from rembg import new_session
from PIL import Image

session = new_session("u2net")
with Image.open("input.jpg") as img:
    result = remove_background(img.convert("RGB"), session=session)
result.save("output.png")
```

## 说明
- `remove_background_skill/` 与网站后端共用同一份核心源码，行为一致。
- 本技能只处理本地图片，不会自动上传到任何服务器。
