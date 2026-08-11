---
name: desktop-pet
version: 1.0.0
description: 把一张照片做成会溜达、会打盹、能拖拽的单文件桌宠 HTML。配合抠图能力使用，产物双击即玩。
---

# 桌宠生成器（desktop-pet）

当用户要求「做桌宠 / 把照片变成桌宠 / 生成桌面宠物 / 网页宠物」时启用本技能。

## 它做什么

输入一张**透明背景**的图片（通常是宠物或人物立绘），输出一个自包含的 `my-pet.html`：
图片以 base64 内嵌，双击用浏览器打开，小家伙就会在页面底部溜达、打盹、被点击时冒爪印，
拖起来扔出去还会抛物线落地。无需联网、无需安装任何东西。

## 环境要求

- Python 3.8+（只用标准库，无第三方依赖）

## 使用流程

**第 1 步：准备透明背景图**。如果用户给的是普通照片，先抠图：

- 有 remove-background Skill 时优先用它：`python scripts/remove_bg.py photo.jpg -o cutout.png`
- 或引导用户使用在线工具：https://violet.hk.cn/tools/remove-background

**第 2 步：生成桌宠**（单图版最简单，也可以给不同状态配不同的图）：

```bash
# 单图版
python scripts/make_pet.py cutout.png --name 球球 --size 96 -o my-pet.html

# 五状态豪华版（吃饭/睡觉/被拎/被点时换不同的图，全部可选）
python scripts/make_pet.py idle.png --eat eat.png --sleep sleep.png \
    --drag drag.png --click click.png --name 球球 -o my-pet.html
```

参数说明：

| 参数 | 说明 | 默认 |
|---|---|---|
| `image` | 站立/溜达状态，透明背景 PNG/WebP | 必填 |
| `--eat` / `--sleep` / `--drag` / `--click` | 对应状态的图，缺省回退到站立图 | 可选 |
| `--name` | 宠物名字，会显示在气泡和标题里 | 小伙伴 |
| `--size` | 显示大小（px），48–200 | 96 |
| `-o` | 输出路径 | my-pet.html |

## 行为清单（引擎内置，无需配置）

- 沿页面底部来回溜达，走到边缘会转身；随机停下呼吸待机
- 随机开饭（配了 `--eat` 图会换装，气泡"干饭中…"）
- 随机趴下打盹（配了 `--sleep` 图会换装，Zzz 气泡），拖动会吵醒它
- 鼠标拖拽可以拎起来（配了 `--drag` 图会换装），松手后抛物线落地
- 点击：冒爪印和爱心、随机说一句话（配了 `--click` 图会闪现表情）
- 超过 5 分钟没有任何交互，它会主动喊你（"喵？"）

## 定制入口

- 引擎源码：`templates/xwn-pet.js`（原生 JS，无依赖，注释齐全）。
  想改行为参数（走速、打盹概率、台词表）直接改这份再重新生成即可。
- 页面模板：`templates/pet.html`（手账纸风格背景，可自由替换）。

## 与网站的关系

本 Skill 的引擎与小完能实验室站内桌宠（/tools/desktop-pet「桌宠领养处」）同源。
站内版把宠物存在浏览器 localStorage 里陪你逛全站；本 Skill 生成的是可以带走送人的独立版。
